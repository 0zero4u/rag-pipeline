"""Unit tests for the citation map module.

Tests cover:
  - build_citation_map        (creation, entry fields, index population)
  - build_reference_key       (format, edge cases for missing year / comma names)
  - load_citation_map         (normal load, missing file)
  - find_citing_papers        (matched and unmatched references)
  - enrich_results            (metadata injection, unknown sources)
"""

import json
from pathlib import Path

import pytest

# sys.path is already set up by tests/conftest.py
from citation_map import (
    build_citation_map,
    build_reference_key,
    enrich_results,
    find_citing_papers,
    load_citation_map,
    CitationEntry,
    CitationMap,
)

# ---------------------------------------------------------------------------
# build_citation_map
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_citation_map_creates_citation_map_object(sample_parsed_pdf):
    """Verify build_citation_map returns a CitationMap with the expected
    top-level containers (citations, author_index, year_index)."""
    result = build_citation_map([sample_parsed_pdf])

    assert isinstance(result, CitationMap)
    assert isinstance(result.citations, dict)
    assert isinstance(result.author_index, dict)
    assert isinstance(result.year_index, dict)
    assert len(result.citations) == 1


@pytest.mark.unit
def test_build_citation_map_creates_citation_entries(sample_parsed_pdf):
    """Verify a ParsedPDF input produces a CitationEntry with correct fields:
    filename, title, authors, year, doi, reference_keys."""
    result = build_citation_map([sample_parsed_pdf])

    entry = result.citations["test_paper.pdf"]
    assert isinstance(entry, CitationEntry)
    assert entry.filename == "test_paper.pdf"
    assert entry.title == "Test Paper on Machine Learning"
    assert entry.authors == ["Alice Researcher", "Bob Scholar"]
    assert entry.year == "2023"
    assert entry.doi == "10.1234/test.ml.2023"
    assert entry.reference_keys == ["Smith-2021", "Jones-2022"]


@pytest.mark.unit
def test_build_citation_map_populates_indices(sample_parsed_pdf):
    """Verify author_index and year_index are correctly built from entries."""
    result = build_citation_map([sample_parsed_pdf])

    assert "Alice Researcher" in result.author_index
    assert result.author_index["Alice Researcher"] == ["test_paper.pdf"]

    assert "Bob Scholar" in result.author_index
    assert result.author_index["Bob Scholar"] == ["test_paper.pdf"]

    assert "2023" in result.year_index
    assert result.year_index["2023"] == ["test_paper.pdf"]


# ---------------------------------------------------------------------------
# build_reference_key (standalone helper)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_reference_key_format():
    """Verify build_reference_key produces 'Author-Year' format when both
    author and year are present."""
    ref = {"authors": ["Smith, John"], "title": "A Paper", "year": "2023"}
    key = build_reference_key(ref)
    assert key == "Smith-2023"


@pytest.mark.unit
def test_build_reference_key_handles_no_year():
    """Verify build_reference_key uses empty string when year is present but
    empty, and 'n.d.' when the year key is entirely missing."""
    # Year key exists but is empty -> .get('year', 'n.d.') returns ''
    ref = {"authors": ["Brown, Charlie"], "title": "Undated", "year": ""}
    key = build_reference_key(ref)
    assert key == "Brown-"

    # Year key is missing entirely -> falls back to 'n.d.'
    ref2 = {"authors": ["Green, Eve"], "title": "No Year Key"}
    key2 = build_reference_key(ref2)
    assert key2 == "Green-n.d."


@pytest.mark.unit
def test_build_reference_key_handles_comma_name():
    """Verify build_reference_key correctly extracts the last name from
    'Last, First' format authors."""
    ref = {"authors": ["Doe, Jane"], "title": "Comma Name", "year": "2020"}
    key = build_reference_key(ref)
    assert key == "Doe-2020"


@pytest.mark.unit
def test_build_reference_key_handles_first_last_name():
    """Verify build_reference_key handles 'First Last' format by taking the
    last word as the surname."""
    ref = {"authors": ["Alice Wonderland"], "title": "Test", "year": "2021"}
    key = build_reference_key(ref)
    assert key == "Wonderland-2021"


@pytest.mark.unit
def test_build_reference_key_handles_unknown_author():
    """Verify build_reference_key falls back to 'Unknown' and 'n.d.' when
    author and year are both missing."""
    ref = {"title": "Orphan Reference"}
    key = build_reference_key(ref)
    assert key == "Unknown-n.d."


# ---------------------------------------------------------------------------
# load_citation_map
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_citation_map(sample_citation_map_json):
    """Verify load_citation_map reads a JSON file and returns a CitationMap
    with the correct data.

    Note: entries are reconstructed as plain dicts (json.load does not
    re-create dataclass instances), so fields are accessed via dict keys.
    """
    result = load_citation_map(sample_citation_map_json)

    assert isinstance(result, CitationMap)
    assert "test_paper.pdf" in result.citations

    entry = result.citations["test_paper.pdf"]
    assert entry["title"] == "Test Paper on Machine Learning"
    assert entry["year"] == "2023"
    assert entry["authors"] == ["Alice Researcher", "Bob Scholar"]
    assert entry["reference_keys"] == ["Researcher-2023"]

    assert "Alice Researcher" in result.author_index
    assert "2023" in result.year_index


@pytest.mark.unit
def test_load_citation_map_handles_missing_file():
    """Verify load_citation_map raises FileNotFoundError when the given path
    does not exist."""
    with pytest.raises(FileNotFoundError):
        load_citation_map("/non/existent/path.json")


# ---------------------------------------------------------------------------
# find_citing_papers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_find_citing_papers(sample_citation_map):
    """Verify find_citing_papers returns filenames of all papers that cite a
    given reference key."""
    citing = find_citing_papers(sample_citation_map, "Researcher-2023")
    assert citing == ["test_paper.pdf"]


@pytest.mark.unit
def test_find_citing_papers_no_matches(sample_citation_map):
    """Verify find_citing_papers returns an empty list when no paper cites
    the given reference."""
    citing = find_citing_papers(sample_citation_map, "Zeldovich-1999")
    assert citing == []


# ---------------------------------------------------------------------------
# enrich_results
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_enrich_results_adds_citation_metadata(sample_citation_map):
    """Verify enrich_results adds a 'citation' dict with title, authors, year,
    and doi for results whose source is present in the citation map."""
    results = [
        {"source": "test_paper.pdf", "score": 0.95, "text": "Some content"},
    ]

    enriched = enrich_results(results, sample_citation_map)

    assert len(enriched) == 1
    assert "citation" in enriched[0]
    assert enriched[0]["citation"]["title"] == "Test Paper on Machine Learning"
    assert enriched[0]["citation"]["authors"] == ["Alice Researcher", "Bob Scholar"]
    assert enriched[0]["citation"]["year"] == "2023"
    assert enriched[0]["citation"]["doi"] == "10.1234/test.ml.2023"
    # Original fields preserved
    assert enriched[0]["score"] == 0.95
    assert enriched[0]["text"] == "Some content"


@pytest.mark.unit
def test_enrich_results_handles_unknown_source(sample_citation_map):
    """Verify enrich_results returns the result dict unchanged (no 'citation'
    key) when the source is not present in the citation map."""
    results = [
        {"source": "unknown.pdf", "score": 0.5, "text": "Orphan result"},
    ]

    enriched = enrich_results(results, sample_citation_map)

    assert len(enriched) == 1
    assert "citation" not in enriched[0]
    assert enriched[0]["source"] == "unknown.pdf"
    assert enriched[0]["score"] == 0.5


@pytest.mark.unit
def test_enrich_results_preserves_extra_fields(sample_citation_map):
    """Verify enrich_results keeps all original result fields intact,
    adding the citation dict alongside existing keys without mutation."""
    results = [
        {"source": "test_paper.pdf", "score": 0.95, "page": 3, "chunk_id": "c001"},
    ]

    enriched = enrich_results(results, sample_citation_map)

    assert enriched[0]["score"] == 0.95
    assert enriched[0]["page"] == 3
    assert enriched[0]["chunk_id"] == "c001"
    assert enriched[0]["citation"]["doi"] == "10.1234/test.ml.2023"
