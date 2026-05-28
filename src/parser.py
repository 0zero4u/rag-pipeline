"""
PDF Parser Module
=================
Parses PDFs using Docling (content) and PDFx (metadata).
Produces structured output for LightRAG ingestion.
"""

import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from tqdm import tqdm

# PDF processing
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

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


def parse_pdf_with_docling(pdf_path: str, max_pages: Optional[int] = None) -> dict:
    """
    Parse PDF using Docling to extract content and structure.
    
    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum number of pages to process (None for all)
    
    Returns:
        dict with 'content', 'page_count', 'has_tables', 'has_formulas'
    """
    try:
        # Configure pipeline options
        pipeline_options = PdfPipelineOptions()
        
        # Create converter
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        
        # Convert PDF
        result = converter.convert(pdf_path)
        doc = result.document
        
        # Export to markdown for content
        content = doc.export_to_markdown()
        
        # Get page count
        page_count = len(doc.pages) if hasattr(doc, 'pages') else 0
        
        # Check for tables and formulas
        has_tables = False
        has_formulas = False
        
        # Count elements
        if hasattr(doc, 'elements'):
            for elem in doc.elements:
                elem_type = str(type(elem).__name__).lower()
                if 'table' in elem_type:
                    has_tables = True
                if 'formula' in elem_type or 'equation' in elem_type:
                    has_formulas = True
        
        return {
            'content': content,
            'page_count': page_count,
            'has_tables': has_tables,
            'has_formulas': has_formulas
        }
    
    except Exception as e:
        print(f"Error parsing {pdf_path} with Docling: {e}")
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
    Parse a single PDF using both Docling and PDFx.
    
    Args:
        pdf_path: Path to PDF file
        extract_metadata: Whether to extract metadata with PDFx
    
    Returns:
        ParsedPDF object
    """
    pdf_path = str(pdf_path)
    filename = Path(pdf_path).name
    
    # Parse content with Docling
    docling_result = parse_pdf_with_docling(pdf_path)
    
    # Extract metadata with PDFx if requested
    metadata = None
    if extract_metadata and PDFX_AVAILABLE:
        metadata = extract_metadata_with_pdfx(pdf_path)
    
    return ParsedPDF(
        filename=filename,
        content=docling_result['content'],
        metadata=metadata,
        page_count=docling_result['page_count'],
        has_tables=docling_result['has_tables'],
        has_formulas=docling_result['has_formulas']
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
