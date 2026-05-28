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
    """Structured metadata from PDFx."""
    title: str
    authors: list[str]
    year: Optional[str]
    doi: str
    references: list[dict]


@dataclass
class ParsedPDF:
    """Combined result from Docling + PDFx."""
    filename: str
    content: str
    metadata: Optional[PDFMetadata]
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


def extract_metadata_with_pdfx(pdf_path: str) -> Optional[PDFMetadata]:
    """
    Extract metadata using PDFx.
    
    Args:
        pdf_path: Path to PDF file
    
    Returns:
        PDFMetadata object or None if extraction fails
    """
    if not PDFX_AVAILABLE:
        return None
    
    try:
        pdfx = PDFxExtractor(pdf_path)
        
        # Get metadata
        metadata = pdfx.get_metadata()
        
        # Get references
        try:
            references = pdfx.get_references()
        except Exception:
            references = []
        
        return PDFMetadata(
            title=metadata.get('Title', 'Unknown'),
            authors=metadata.get('Authors', []) or [],
            year=metadata.get('Year', None),
            doi=metadata.get('DOI', ''),
            references=references
        )
    
    except Exception as e:
        print(f"Warning: Could not extract metadata from {pdf_path}: {e}")
        return None


def parse_single_pdf(pdf_path: str, extract_metadata: bool = True) -> ParsedPDF:
    """
    Parse a single PDF using pymupdf4llm and PDFx.
    """
    pdf_path = str(pdf_path)
    filename = Path(pdf_path).name
    
    result = parse_pdf_with_pymupdf4llm(pdf_path)
    
    # Extract metadata with PDFx if requested
    metadata = None
    if extract_metadata and PDFX_AVAILABLE:
        metadata = extract_metadata_with_pdfx(pdf_path)
    
    return ParsedPDF(
        filename=filename,
        content=result['content'],
        metadata=metadata,
        page_count=result['page_count'],
        has_tables=result['has_tables'],
        has_formulas=result['has_formulas']
    )


def parse_pdfs(
    pdf_dir: str,
    output_dir: str,
    extract_metadata: bool = True,
    recursive: bool = True
) -> list[ParsedPDF]:
    """
    Parse all PDFs in a directory.
    
    Args:
        pdf_dir: Directory containing PDFs
        output_dir: Directory to save parsed results
        extract_metadata: Whether to extract metadata with PDFx
        recursive: Whether to search recursively
    
    Returns:
        List of ParsedPDF objects
    """
    pdf_dir = Path(pdf_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all PDFs
    if recursive:
        pdf_paths = list(pdf_dir.rglob("*.pdf"))
    else:
        pdf_paths = list(pdf_dir.glob("*.pdf"))
    
    print(f"Found {len(pdf_paths)} PDFs in {pdf_dir}")
    
    # Parse each PDF with progress bar
    parsed_pdfs = []
    
    for pdf_path in tqdm(pdf_paths, desc="Parsing PDFs"):
        try:
            parsed = parse_single_pdf(str(pdf_path), extract_metadata=extract_metadata)
            parsed_pdfs.append(parsed)
            
            # Save individual result
            output_file = output_dir / f"{Path(pdf_path).stem}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(parsed), f, indent=2, ensure_ascii=False)
        
        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")
            continue
    
    # Save combined results
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
