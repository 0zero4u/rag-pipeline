"""Integration tests for the RAG pipeline component interactions.

Tests the data flow between:
  1. parser.parse_single_pdf → citation_map.build_citation_map
  2. citation_map → validate_citations.validate_citations_in_prose
  3. Full end-to-end validation with orphaned-marker checking

All external dependencies (file I/O, LightRAG, LLM) are mocked — no real
APIs, PDFs, or API keys required.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src/ to sys.path so that pipeline modules can be imported.
# (conftest.py also does this, but we keep it here for standalone running.)
_src = str(Path(__file__).resolve().parent.parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from citation_map import CitationMap, build_citation_map

# ---------------------------------------------------------------------------
# Helper: dict-based doc_status to avoid depending on conftest fixtures that
# return file paths instead of the dict that load_doc_status must return.
# ---------------------------------------------------------------------------

_CITATION_MAP_DICT = {
    "CET-JJ21-8-Dr-Unrmila-Devi.pdf": {
        "title": "SOCIAL AND POLITICAL ASPECTS BY KHUSHWANT SINGH",
        "authors": ["Dr Urmila Devi"],
        "year": "2021",
    },
    "English.pdf": {
        "title": "Exploring the Literary Contributions of Kushwant Singh",
        "authors": ["Naved Alam", "Md. Rizwan Khan"],
        "year": None,
    },
}

_DOC_STATUS_DICT = {
    "doc_001": {
        "file_path": "CET-JJ21-8-Dr-Unrmila-Devi.pdf",
        "created_at": "2024-01-01T00:00:00",
    },
    "doc_002": {
        "file_path": "English.pdf",
        "created_at": "2024-01-02T00:00:00",
    },
}


# ---------------------------------------------------------------------------
# Flow 1: parser → citation_map
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_parse_to_citation_map_flow(sample_parsed_pdf):
    """Parser output feeds into citation map builder.

    Mocks ``parser.parse_single_pdf`` to return a controlled ``ParsedPDF``
    instance, then feeds that into ``citation_map.build_citation_map`` and
    verifies that the resulting ``CitationMap`` correctly contains the
    parsed PDF's metadata.

    Uses module-level import (``import parser``) so the mock replacement of
    ``parser.parse_single_pdf`` is visible when calling through the module
    reference — a ``from parser import parse_single_pdf`` local binding
    would bypass the patch.
    """
    import parser

    with patch("parser.parse_single_pdf", return_value=sample_parsed_pdf):
        parsed = parser.parse_single_pdf("/fake/test_paper.pdf")

    citation_map = build_citation_map([parsed])

    assert isinstance(citation_map, CitationMap)
    assert "test_paper.pdf" in citation_map.citations

    entry = citation_map.citations["test_paper.pdf"]
    assert entry.filename == "test_paper.pdf"
    assert entry.title == "Test Paper on Machine Learning"
    assert entry.authors == ["Alice Researcher", "Bob Scholar"]
    assert entry.year == "2023"
    assert entry.doi == "10.1234/test.ml.2023"
    assert entry.reference_keys == ["Smith-2021", "Jones-2022"]


# ---------------------------------------------------------------------------
# Flow 2: citation_map → validate_citations
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_citation_map_to_validation_flow():
    """Citation map validates against prose successfully.

    Builds a ``validate_citations_in_prose`` call with mocked file-loading
    functions (``load_citation_map`` and ``load_doc_status``) and verifies
    that a simple ``[CHUNK-1]`` marker resolves to a valid citation with
    the correct metadata.
    """
    from validate_citations import validate_citations_in_prose

    prose = "Machine learning has transformed data analysis [CHUNK-1]."

    with (
        patch("validate_citations.load_citation_map", return_value=_CITATION_MAP_DICT),
        patch("validate_citations.load_doc_status", return_value=_DOC_STATUS_DICT),
    ):
        results = validate_citations_in_prose(
            prose=prose,
            citation_map_path="/fake/citation_map.json",
            working_dir="/fake/working_dir",
        )

    assert len(results) == 1
    assert results[0].valid is True
    assert results[0].chunk_id == "1"
    assert results[0].message == "Citation verified"
    assert results[0].source_file == "CET-JJ21-8-Dr-Unrmila-Devi.pdf"
    assert results[0].author == "Dr Urmila Devi"
    assert results[0].year == "2021"
    assert results[0].title == (
        "SOCIAL AND POLITICAL ASPECTS BY KHUSHWANT SINGH"
    )


# ---------------------------------------------------------------------------
# Flow 3: Full end-to-end validation with orphaned-marker check
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_full_validation_flow():
    """End-to-end validation from citation check to orphaned-marker audit.

    Creates prose containing multiple ``[CHUNK-N]`` citation markers,
    validates all of them against a mocked citation map, and then
    simulates the post-validation check for orphaned markers (via
    ``check_citations.find_orphaned_citations``).  Verifies that every
    citation is valid AND no markers remain orphaned.
    """
    from validate_citations import validate_citations_in_prose

    prose = (
        "Recent advances in machine learning have shown promising results "
        "[CHUNK-1]. "
        "Deep learning architectures, in particular, have revolutionized "
        "the field [CHUNK-2]. "
        "However, interpretability remains a key challenge [CHUNK-3]."
    )

    # --- Step 1: validate all citations ---
    with (
        patch("validate_citations.load_citation_map", return_value=_CITATION_MAP_DICT),
        patch("validate_citations.load_doc_status", return_value=_DOC_STATUS_DICT),
    ):
        validations = validate_citations_in_prose(
            prose=prose,
            citation_map_path="/fake/citation_map.json",
            working_dir="/fake/working_dir",
        )

    # Every citation should pass (both docs exist in citation_map)
    assert len(validations) == 3
    assert all(v.valid for v in validations), (
        f"Expected all citations valid, got: "
        f"{[(v.chunk_id, v.message) for v in validations]}"
    )
    assert {v.chunk_id for v in validations} == {"1", "2", "3"}

    # --- Step 2: check that no orphaned [CHUNK-N] markers remain ---
    # (simulates what check_citations.main() does after CitationAdderAgent)
    with patch("check_citations.find_orphaned_citations", return_value=[]) as mock_find:
        orphaned = mock_find("/fake/final_draft.md")
        assert len(orphaned) == 0, "Expected zero orphaned citation markers"

    # Combined assertion: all citations valid AND no orphans
    assert all(v.valid for v in validations)
    mock_find.assert_called_once_with("/fake/final_draft.md")
