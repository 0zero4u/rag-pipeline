"""
PDF Parser Module
=================
Parses PDFs using pymupdf4llm (content) and PDFx (metadata).
Produces structured output for LightRAG ingestion.
"""

import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from tqdm import tqdm

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
    print("Warning: pdfx not installed. Metadata extraction will be skipped.")
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


def extract_metadata_with_llm(first_page_text: str, llm_func: callable) -> dict:
    """
    Extract metadata via LLM from first-page text.
    NOTE: This is a sync wrapper for use in async batch processing.

    Args:
        first_page_text: First ~2000 chars of first page
        llm_func: LLM function from config.py

    Returns:
        dict with title, authors, year, abstract
    """
    import json, re
    import asyncio

    prompt = f"""You are a research librarian. Extract metadata from this academic paper's first page.
Return ONLY valid JSON with these exact keys:
- "title": paper title (string)
- "authors": list of author names (list of strings)
- "year": publication year (string or null)
- "abstract": first paragraph/sentence (string or null)

Paper text:\n\n{first_page_text[:2000]}"""

    try:
        response = asyncio.get_event_loop().run_until_complete(llm_func(prompt))
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"title": None, "authors": [], "year": None, "abstract": None}
    except Exception as e:
        print(f"Warning: LLM metadata extraction failed: {e}")
        return {"title": None, "authors": [], "year": None, "abstract": None}


@dataclass
class ParsedPDF:
    """Parsed PDF with content and pending metadata extraction."""
    filename: str
    content: str
    metadata: Optional[PDFMetadata]
    first_page_snippet: str = ""
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
        return references if references else []
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

    # First page text for later metadata extraction
    first_page_snippet = ""
    if content:
        parts = content.split('\n\n')
        for part in parts:
            first_page_snippet += part + "\n\n"
            if len(first_page_snippet) >= 1500:
                break
    first_page_snippet = first_page_snippet[:2000]

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
        page_count=result['page_count'],
        has_tables=result['has_tables'],
        has_formulas=result['has_formulas']
    )


def parse_pdfs(pdf_dir: str, output_dir: str, recursive: bool = True) -> list[ParsedPDF]:
    """
    Parse all PDFs in a directory. Metadata extraction is done separately via extract_metadata_batch.

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

    parsed_pdfs = []

    for pdf_path in tqdm(pdf_paths, desc="Parsing PDFs"):
        try:
            parsed = parse_single_pdf(str(pdf_path))
            parsed_pdfs.append(parsed)

            output_file = output_dir / f"{Path(pdf_path).stem}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(parsed), f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")
            continue

    combined_output = output_dir / "all_parsed.json"
    with open(combined_output, 'w', encoding='utf-8') as f:
        json.dump([asdict(p) for p in parsed_pdfs], f, indent=2, ensure_ascii=False)

    print(f"Saved results to {output_dir}")
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
