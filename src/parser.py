"""
PDF Parser Module
=================
Parses PDFs using pymupdf4llm (content) and PDFx (metadata).
Produces structured output for LightRAG ingestion.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, asdict
from tqdm import tqdm


class PDFEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, re.Pattern):
            return obj.pattern
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)

# pymupdf4llm for content extraction (tables, formulas, OCR)
try:
    import pymupdf4llm
    PYMUPDF4LLM_AVAILABLE = True
except ImportError:
    print("Warning: pymupdf4llm not installed. Using PyMuPDF only.")
    PYMUPDF4LLM_AVAILABLE = False
    import pymupdf

# Metadata extraction
try:
    from pdfx import PDFx as PDFxExtractor
    PDFX_AVAILABLE = True
except ImportError:
    print("Warning: pdfx not installed. References extraction will be skipped.")
    PDFX_AVAILABLE = False


@dataclass
class PDFMetadata:
    """Metadata extracted from PDF (LLM + PDFx references)."""
    title: str
    authors: list[str]
    year: Optional[str]
    doi: str
    abstract: str
    references: list[dict]
    source: str  # 'llm', 'pdfx', 'filename'
    confidence: str  # 'high', 'medium', 'low'


def extract_metadata_with_llm(start_text: str, end_text: str, llm_func: callable) -> dict:
    """
    Extract metadata via LLM from start and end of paper.
    Start: title, authors, year, abstract
    End: references, conclusion summary

    Args:
        start_text: First ~4000 chars (title, authors, abstract)
        end_text: Last ~4000 chars (conclusion, references)
        llm_func: LLM function from config.py

    Returns:
        dict with title, authors, year, abstract, references
    """
    import json, re
    import asyncio

    prompt = f"""You are a research librarian. Extract metadata from this academic paper.
Return ONLY valid JSON with these exact keys:
- "title": paper title (string)
- "authors": list of author names (list of strings)
- "year": publication year (string or null)
- "abstract": first paragraph/sentence (string or null)
- "references": list of reference strings from the references section

=== START OF PAPER ===
{start_text[:4000]}
=== END OF PAPER ===
{end_text[-4000:]}

Return JSON with all fields above. If year/abstract not found, use null. If no references, use empty list."""

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, llm_func(prompt))
                response = future.result()
        else:
            response = asyncio.run(llm_func(prompt))
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"title": None, "authors": [], "year": None, "abstract": None, "references": []}
    except Exception as e:
        print(f"Warning: LLM metadata extraction failed: {e}")
        return {"title": None, "authors": [], "year": None, "abstract": None, "references": []}


@dataclass
class ParsedPDF:
    """Parsed PDF with content and pending metadata extraction."""
    filename: str
    content: str
    metadata: Optional[PDFMetadata]
    first_page_snippet: str = ""
    start_snippet: str = ""
    end_snippet: str = ""
    page_count: int = 0
    has_tables: bool = False
    has_formulas: bool = False


def parse_pdf_with_pymupdf4llm(pdf_path: str) -> dict:
    """
    Parse PDF using pymupdf4llm for Markdown conversion with tables/formulas.
    Falls back to plain PyMuPDF if pymupdf4llm unavailable.
    """
    try:
        if PYMUPDF4LLM_AVAILABLE:
            md = pymupdf4llm.to_markdown(pdf_path)
            content = md
        else:
            import pymupdf
            doc = pymupdf.open(pdf_path)
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text("text"))
            content = "\n\n".join(text_parts)
        
        import pymupdf
        doc = pymupdf.open(pdf_path)
        page_count = len(doc)
        
        return {
            'content': content,
            'page_count': page_count,
            'has_tables': '|' in content and '---' in content,
            'has_formulas': '$$' in content or '\\(' in content
        }
    except Exception as e:
        print(f"Error parsing {pdf_path}: {e}")
        return {
            'content': '',
            'page_count': 0,
            'has_tables': False,
            'has_formulas': False
        }


def extract_references_with_pdfx(pdf_path: str) -> list[dict]:
    """
    Extract references from PDF using PDFx.
    PDFx extracts the bibliography/references from the end of the paper.

    Args:
        pdf_path: Path to PDF file

    Returns:
        List of reference dicts (type, id, text)
    """
    if not PDFX_AVAILABLE:
        return []

    try:
        pdfx = PDFxExtractor(pdf_path)
        references = pdfx.get_references()
        if isinstance(references, set):
            references = list(references)
        # Convert Reference objects to dicts
        serialized = []
        for ref in (references or []):
            if hasattr(ref, '__dict__'):
                serialized.append(ref.__dict__)
            else:
                serialized.append(str(ref))
        return serialized
    except Exception as e:
        print(f"Warning: PDFx reference extraction failed for {pdf_path}: {e}")
        return []


def parse_single_pdf(pdf_path: str) -> ParsedPDF:
    """
    Parse a single PDF using pymupdf4llm.
    Returns content and references only. Metadata extraction is done separately.

    Args:
        pdf_path: Path to PDF file
    """
    pdf_path = str(pdf_path)
    filename = Path(pdf_path).name

    result = parse_pdf_with_pymupdf4llm(pdf_path)
    content = result['content']

    # Get references via PDFx
    references = extract_references_with_pdfx(pdf_path)

    # First 4000 chars (title, authors, abstract)
    start_snippet = content[:4000] if content else ""
    
    # Last 4000 chars (conclusion, references)
    end_snippet = content[-4000:] if content else ""
    
    # Also keep short first_page for backwards compatibility
    first_page_snippet = content[:2000] if content else ""

    metadata = PDFMetadata(
        title=filename,
        authors=[],
        year=None,
        doi='',
        abstract='',
        references=references,
        source='pending',
        confidence='low'
    )

    return ParsedPDF(
        filename=filename,
        content=content,
        metadata=metadata,
        first_page_snippet=first_page_snippet,
        start_snippet=start_snippet,
        end_snippet=end_snippet,
        page_count=result['page_count'],
        has_tables=result['has_tables'],
        has_formulas=result['has_formulas']
    )


def parse_pdfs(pdf_dir: str, output_dir: str, recursive: bool = True) -> list[ParsedPDF]:
    """
    Parse all PDFs in a directory. Supports resume — skips already-parsed PDFs.

    Args:
        pdf_dir: Directory containing PDFs
        output_dir: Directory to save parsed results
        recursive: Whether to search recursively

    Returns:
        List of ParsedPDF objects
    """
    pdf_dir = Path(pdf_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if recursive:
        pdf_paths = list(pdf_dir.rglob("*.pdf"))
    else:
        pdf_paths = list(pdf_dir.glob("*.pdf"))

    print(f"Found {len(pdf_paths)} PDFs in {pdf_dir}")

    # Resume: load already-parsed PDFs
    parsed_pdfs = []
    skipped = 0
    for pdf_path in pdf_paths:
        output_file = output_dir / f"{Path(pdf_path).stem}.json"
        if output_file.exists():
            # Load cached parse
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                parsed_pdfs.append(ParsedPDF(**data))
                skipped += 1
                continue
            except Exception:
                pass  # Corrupted cache, re-parse

        try:
            parsed = parse_single_pdf(str(pdf_path))
            parsed_pdfs.append(parsed)

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(parsed), f, indent=2, ensure_ascii=False, cls=PDFEncoder)

        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")
            continue

    # Save combined output
    combined_output = output_dir / "all_parsed.json"
    with open(combined_output, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in parsed_pdfs], f, indent=2, ensure_ascii=False, cls=PDFEncoder)

    print(f"Saved {len(parsed_pdfs)} PDFs ({skipped} cached, {len(parsed_pdfs) - skipped} newly parsed)")
    return parsed_pdfs


if __name__ == "__main__":
    import sys
    
    # Example usage
    if len(sys.argv) < 3:
        print("Usage: python parser.py <pdf_dir> <output_dir>")
        sys.exit(1)
    
    pdf_dir = sys.argv[1]
    output_dir = sys.argv[2]
    
    parse_pdfs(pdf_dir, output_dir)
