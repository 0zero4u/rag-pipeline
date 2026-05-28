"""Unit tests for the citation validation module.

Tests validate_citations_in_prose, load_citation_map, load_doc_status,
format_mla_citation, and the CitationValidation dataclass.
All file I/O is mocked — no real files, API keys, or LightRAG required.
"""

import json
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

# Add src to path so the module can be imported
_src = str(Path(__file__).resolve().parent.parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from validate_citations import (
    CitationValidation,
    format_mla_citation,
    load_citation_map,
    load_doc_status,
    validate_citations_in_prose,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_prose_with_citations():
    """Prose containing multiple [CHUNK-N] markers, including a duplicate."""
    return (
        "In recent studies [CHUNK-1], researchers found significant evidence.\n"
        "Further analysis [CHUNK-2] supports this conclusion.\n"
        "Additional validation [CHUNK-3] confirms the hypothesis.\n"
        "The same source [CHUNK-1] appears twice."
    )


@pytest.fixture
def sample_citation_map_json():
    """Sample citation_map.json data keyed by filename.

    Structure matches real output from LightRAG's citation extraction.
    """
    return {
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


@pytest.fixture
def sample_doc_status():
    """Sample kv_store_doc_status.json mapping document IDs to file paths.

    Sorted by created_at to control ref_id → filename resolution.
    """
    return {
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
# validate_citations_in_prose
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_validate_citations_finds_all_chunk_markers(
    sample_prose_with_citations,
    sample_citation_map_json,
    sample_doc_status,
):
    """Verify ALL distinct [CHUNK-N] markers are detected.

    The prose contains [CHUNK-1], [CHUNK-2], and [CHUNK-3] (CHUNK-1 appears
    twice but should be deduplicated), so exactly three validations must be
    returned, each flagged valid.
    """
    with (
        patch("validate_citations.load_citation_map", return_value=sample_citation_map_json),
        patch("validate_citations.load_doc_status", return_value=sample_doc_status),
    ):
        results = validate_citations_in_prose(
            prose=sample_prose_with_citations,
            citation_map_path="/fake/map.json",
            working_dir="/fake/wd",
        )

    assert len(results) == 3, "Expected 3 unique chunk references"
    chunk_ids = {r.chunk_id for r in results}
    assert chunk_ids == {"1", "2", "3"}
    assert all(r.valid for r in results), "All citations should be valid"


@pytest.mark.unit
def test_validate_citations_no_markers(sample_citation_map_json, sample_doc_status):
    """Confirm that prose without any [CHUNK-N] markers returns an empty list."""
    plain_prose = "This is ordinary prose with no citation markers whatsoever."

    with (
        patch("validate_citations.load_citation_map", return_value=sample_citation_map_json),
        patch("validate_citations.load_doc_status", return_value=sample_doc_status),
    ):
        results = validate_citations_in_prose(
            prose=plain_prose,
            citation_map_path="/fake/map.json",
            working_dir="/fake/wd",
        )

    assert results == [], "No markers should yield empty validation list"


@pytest.mark.unit
def test_validate_citations_checks_max_chunks(
    sample_prose_with_citations,
    sample_citation_map_json,
    sample_doc_status,
):
    """Check citations exceeding *max_chunks* are flagged invalid.

    With max_chunks=2, reference [CHUNK-3] exceeds the limit and must be
    marked invalid with an explanatory message.
    """
    with (
        patch("validate_citations.load_citation_map", return_value=sample_citation_map_json),
        patch("validate_citations.load_doc_status", return_value=sample_doc_status),
    ):
        results = validate_citations_in_prose(
            prose=sample_prose_with_citations,
            citation_map_path="/fake/map.json",
            working_dir="/fake/wd",
            max_chunks=2,
        )

    assert len(results) == 3
    valid = [r for r in results if r.valid]
    invalid = [r for r in results if not r.valid]
    assert len(valid) == 2, "[CHUNK-1] and [CHUNK-2] should be valid"
    assert len(invalid) == 1, "[CHUNK-3] should be invalid"

    exceeded = invalid[0]
    assert exceeded.chunk_id == "3"
    assert "exceeds" in exceeded.message.lower()
    assert exceeded.max_chunks == 2


@pytest.mark.unit
def test_validate_citations_verifies_filename_in_citation_map(
    sample_prose_with_citations,
    sample_doc_status,
):
    """Ensure citations mapping to files *absent* from citation_map are invalid.

    Using an empty citation_map, every resolved filename will be missing,
    producing invalid results with a descriptive message.
    """
    empty_citation_map = {}

    with (
        patch("validate_citations.load_citation_map", return_value=empty_citation_map),
        patch("validate_citations.load_doc_status", return_value=sample_doc_status),
    ):
        results = validate_citations_in_prose(
            prose=sample_prose_with_citations,
            citation_map_path="/fake/map.json",
            working_dir="/fake/wd",
        )

    assert len(results) > 0
    assert all(not r.valid for r in results)
    assert "not in citation_map.json" in results[0].message


@pytest.mark.unit
def test_validate_citations_valid_citation(
    sample_prose_with_citations,
    sample_citation_map_json,
    sample_doc_status,
):
    """Verify a valid citation returns correct author, year, title, source_file.

    The first document in doc_status (sorted by created_at) is
    CET-JJ21-8-Dr-Unrmila-Devi.pdf, which exists in citation_map with known
    metadata.
    """
    with (
        patch("validate_citations.load_citation_map", return_value=sample_citation_map_json),
        patch("validate_citations.load_doc_status", return_value=sample_doc_status),
    ):
        results = validate_citations_in_prose(
            prose=sample_prose_with_citations,
            citation_map_path="/fake/map.json",
            working_dir="/fake/wd",
        )

    valid_results = [r for r in results if r.valid]
    assert len(valid_results) > 0

    r = valid_results[0]
    assert r.valid is True
    assert r.message == "Citation verified"
    assert r.source_file == "CET-JJ21-8-Dr-Unrmila-Devi.pdf"
    assert r.author == "Dr Urmila Devi"
    assert r.year == "2021"
    assert r.title == "SOCIAL AND POLITICAL ASPECTS BY KHUSHWANT SINGH"


# ---------------------------------------------------------------------------
# load_citation_map
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_load_citation_map_extracts_citations_dict():
    """Verify *load_citation_map* returns the 'citations' sub-dict when present.

    The real citation_map.json wraps entries under a ``citations`` key alongside
    ``author_index`` and ``year_index``. The function must extract only the
    ``citations`` value. When that key is absent it should return the full data.
    """
    # Case 1: JSON with 'citations' key
    nested_data = {
        "citations": {"paper.pdf": {"title": "T", "authors": ["A"], "year": "2020"}},
        "author_index": {},
        "year_index": {},
    }
    with patch("builtins.open", mock_open(read_data=json.dumps(nested_data))):
        result = load_citation_map("/fake/map.json")
    assert result == nested_data["citations"]

    # Case 2: Flat JSON without 'citations' key
    flat_data = {"paper.pdf": {"title": "T", "authors": ["A"], "year": "2020"}}
    with patch("builtins.open", mock_open(read_data=json.dumps(flat_data))):
        result = load_citation_map("/fake/map.json")
    assert result == flat_data

    # Case 3: FileNotFoundError → empty dict
    with patch("builtins.open", side_effect=FileNotFoundError):
        result = load_citation_map("/nonexistent.json")
    assert result == {}

    # Case 4: JSONDecodeError → empty dict
    with patch("builtins.open", mock_open(read_data="not-json")):
        result = load_citation_map("/bad.json")
    assert result == {}


# ---------------------------------------------------------------------------
# load_doc_status
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_load_doc_status_maps_ref_id_to_filename():
    """Verify *load_doc_status* loads the full KV store dict correctly.

    The returned dict should preserve ref_id → file_path mappings so that
    downstream code can resolve chunk indices to source filenames.
    """
    fake_status = {
        "doc_001": {"file_path": "alpha.pdf", "created_at": "2024-01-01T00:00:00"},
        "doc_002": {"file_path": "beta.pdf", "created_at": "2024-01-02T00:00:00"},
    }
    with patch("builtins.open", mock_open(read_data=json.dumps(fake_status))):
        result = load_doc_status("/fake/wd")

    assert result == fake_status
    assert result["doc_001"]["file_path"] == "alpha.pdf"
    assert result["doc_002"]["file_path"] == "beta.pdf"

    # FileNotFoundError → empty dict
    with patch("builtins.open", side_effect=FileNotFoundError):
        result = load_doc_status("/missing")
    assert result == {}

    # JSONDecodeError → empty dict
    with patch("builtins.open", mock_open(read_data="broken")):
        result = load_doc_status("/bad")
    assert result == {}


# ---------------------------------------------------------------------------
# format_mla_citation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_format_mla_citation_valid():
    """Produce '(Author Year)' MLA format for a valid citation with both fields."""
    v = CitationValidation(
        chunk_id="1",
        valid=True,
        message="Citation verified",
        author="Dr Urmila Devi",
        year="2021",
    )
    assert format_mla_citation(v) == "(Dr Urmila Devi 2021)"


@pytest.mark.unit
def test_format_mla_citation_no_author():
    """Fall back to bracketed chunk notation when author is missing.

    With valid=True but author=None the else-branch returns ``[CHUNK-{id}]``.
    """
    v = CitationValidation(
        chunk_id="2",
        valid=True,
        message="Citation verified",
        author=None,
        year="2021",
    )
    assert format_mla_citation(v) == "[CHUNK-2]"

    # Also verify author present but no year → "(Author, n.d.)"
    v2 = CitationValidation(
        chunk_id="3",
        valid=True,
        message="Citation verified",
        author="Some Author",
        year=None,
    )
    assert format_mla_citation(v2) == "(Some Author, n.d.)"

    # Invalid citation → "(unverified)" suffix
    v3 = CitationValidation(
        chunk_id="4",
        valid=False,
        message="Not found",
    )
    assert format_mla_citation(v3) == "[CHUNK-4] (unverified)"
