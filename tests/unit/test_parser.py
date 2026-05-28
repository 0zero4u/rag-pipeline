"""
Unit tests for the PDF parser module (src/parser.py).

Tests parse_single_pdf, parse_pdfs, extract_references_with_pdfx,
and verifies ParsedPDF / PDFMetadata dataclass contracts.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from parser import (
    ParsedPDF,
    PDFMetadata,
    extract_references_with_pdfx,
    parse_pdfs,
    parse_single_pdf,
)


# ---------------------------------------------------------------------------
# parse_single_pdf
# ---------------------------------------------------------------------------


@pytest.mark.unit
@patch("parser.extract_references_with_pdfx")
@patch("parser.parse_pdf_with_pymupdf4llm")
def test_parse_single_pdf_returns_parsed_pdf_object(
    mock_parse_pdf, mock_extract_refs
):
    """Verify parse_single_pdf returns a ParsedPDF with all required fields populated."""
    mock_parse_pdf.return_value = {
        "content": "Relevant paper content. " * 500,
        "page_count": 5,
        "has_tables": True,
        "has_formulas": False,
    }
    mock_extract_refs.return_value = [
        {"type": "article", "text": "Some reference"}
    ]

    result = parse_single_pdf("/fake/path/test.pdf")

    assert isinstance(result, ParsedPDF)
    assert result.filename == "test.pdf"
    assert result.page_count == 5
    assert result.has_tables is True
    assert result.has_formulas is False
    assert isinstance(result.metadata, PDFMetadata)
    assert len(result.metadata.references) == 1


@pytest.mark.unit
@patch("parser.extract_references_with_pdfx")
@patch("parser.parse_pdf_with_pymupdf4llm")
def test_parse_single_pdf_extracts_content(mock_parse_pdf, mock_extract_refs):
    """Verify parsed content is a non-empty string with correct snippet extraction."""
    content = "Paper content with formulas $$E=mc^2$$ and tables."
    mock_parse_pdf.return_value = {
        "content": content,
        "page_count": 3,
        "has_tables": False,
        "has_formulas": True,
    }
    mock_extract_refs.return_value = []

    result = parse_single_pdf("/fake/path/paper.pdf")

    assert isinstance(result.content, str)
    assert len(result.content) > 0
    assert result.content == content
    # Snippet boundaries
    assert result.start_snippet == content[:4000]
    assert result.end_snippet == content[-4000:]
    assert result.first_page_snippet == content[:2000]
    assert result.has_formulas is True


@pytest.mark.unit
@patch("parser.extract_references_with_pdfx")
@patch("parser.parse_pdf_with_pymupdf4llm")
def test_parse_single_pdf_handles_missing_file(mock_parse_pdf, mock_extract_refs):
    """Verify graceful handling when PDF does not exist returns ParsedPDF with empty content."""
    mock_parse_pdf.return_value = {
        "content": "",
        "page_count": 0,
        "has_tables": False,
        "has_formulas": False,
    }
    mock_extract_refs.return_value = []

    result = parse_single_pdf("/nonexistent/file.pdf")

    assert isinstance(result, ParsedPDF)
    assert result.content == ""
    assert result.page_count == 0
    assert result.has_tables is False
    assert result.has_formulas is False
    assert result.first_page_snippet == ""
    assert result.start_snippet == ""
    assert result.end_snippet == ""


# ---------------------------------------------------------------------------
# parse_pdfs
# ---------------------------------------------------------------------------


@pytest.mark.unit
@patch("parser.parse_single_pdf")
def test_parse_pdfs_creates_output_files(mock_parse_single, tmp_path):
    """Verify parse_pdfs writes individual JSON and all_parsed.json to output_dir."""
    pdf_dir = tmp_path / "pdfs"
    output_dir = tmp_path / "output"
    pdf_dir.mkdir()

    # Create fake .pdf files so the glob discovers them
    (pdf_dir / "doc1.pdf").touch()
    (pdf_dir / "doc2.pdf").touch()

    mock_parse_single.side_effect = [
        ParsedPDF(
            filename="doc1.pdf",
            content="Content 1",
            metadata=PDFMetadata(
                title="Doc 1",
                authors=[],
                year=None,
                doi="",
                abstract="",
                references=[],
                source="pending",
                confidence="low",
            ),
            page_count=1,
        ),
        ParsedPDF(
            filename="doc2.pdf",
            content="Content 2",
            metadata=PDFMetadata(
                title="Doc 2",
                authors=[],
                year=None,
                doi="",
                abstract="",
                references=[],
                source="pending",
                confidence="low",
            ),
            page_count=2,
        ),
    ]

    results = parse_pdfs(str(pdf_dir), str(output_dir), recursive=False)

    # Individual JSON files
    assert (output_dir / "doc1.json").exists()
    assert (output_dir / "doc2.json").exists()

    # Combined JSON
    combined = output_dir / "all_parsed.json"
    assert combined.exists()

    with open(combined) as f:
        data = json.load(f)
    assert len(data) == 2
    assert data[0]["filename"] == "doc1.pdf"
    assert data[1]["filename"] == "doc2.pdf"

    assert len(results) == 2


# ---------------------------------------------------------------------------
# extract_references_with_pdfx
# ---------------------------------------------------------------------------


@pytest.mark.unit
@patch("parser.PDFxExtractor")
def test_extract_references_with_pdfx_handles_error(mock_extractor):
    """Verify extract_references_with_pdfx returns empty list when PDFx raises."""
    with patch("parser.PDFX_AVAILABLE", True):
        mock_extractor.side_effect = Exception("PDFx connection error")
        result = extract_references_with_pdfx("/fake/path.pdf")
        assert result == []


# ---------------------------------------------------------------------------
# PDFMetadata dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pdfmetadata_dataclass():
    """Verify PDFMetadata dataclass stores and returns all required fields."""
    meta = PDFMetadata(
        title="Test Title",
        authors=["Author One", "Author Two"],
        year="2024",
        doi="10.1234/test",
        abstract="Test abstract.",
        references=[{"id": "1", "text": "Some reference"}],
        source="llm",
        confidence="high",
    )

    assert meta.title == "Test Title"
    assert meta.authors == ["Author One", "Author Two"]
    assert meta.year == "2024"
    assert meta.doi == "10.1234/test"
    assert meta.abstract == "Test abstract."
    assert meta.references == [{"id": "1", "text": "Some reference"}]
    assert meta.source == "llm"
    assert meta.confidence == "high"
