"""
Unit tests for check_citations.py — citation marker detector.

Tests the find_orphaned_citations function which detects
remaining [CHUNK-N] markers in processed markdown files.
"""

import sys
from pathlib import Path

import pytest

# Add src to path so we can import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from check_citations import find_orphaned_citations


@pytest.mark.unit
def test_find_orphaned_citations_finds_all_markers(tmp_path: Path) -> None:
    """Verify that all [CHUNK-N] markers are returned as a list of
    chunk-number strings when multiple markers exist in the file."""
    content = (
        "Some text [CHUNK-1] and more [CHUNK-3]\n"
        "and [CHUNK-7] at the end.\n"
    )
    file_path = tmp_path / "draft.md"
    file_path.write_text(content)

    result = find_orphaned_citations(str(file_path))

    assert result == ["1", "3", "7"]


@pytest.mark.unit
def test_find_orphaned_citations_no_markers(tmp_path: Path) -> None:
    """Verify that an empty list is returned when the file contains
    no [CHUNK-N] markers (e.g. all citations already converted to MLA)."""
    content = (
        "This is a clean MLA citation (Smith 23).\n"
        "Nothing to see here.\n"
    )
    file_path = tmp_path / "clean_draft.md"
    file_path.write_text(content)

    result = find_orphaned_citations(str(file_path))

    assert result == []


@pytest.mark.unit
def test_find_orphaned_citations_handles_missing_file(tmp_path: Path) -> None:
    """Verify that FileNotFoundError is raised when the given path
    does not correspond to an existing file on disk."""
    non_existent = tmp_path / "does_not_exist.md"

    with pytest.raises(FileNotFoundError):
        find_orphaned_citations(str(non_existent))


@pytest.mark.unit
def test_find_orphaned_citations_extracts_numbers(tmp_path: Path) -> None:
    """Verify that only the digit portion of [CHUNK-N] markers is
    returned, stripping the 'CHUNK-' prefix and brackets."""
    content = (
        "Reference [CHUNK-42] and [CHUNK-99] and [CHUNK-7].\n"
        "Also [CHUNK-100] for good measure.\n"
    )
    file_path = tmp_path / "numbers_test.md"
    file_path.write_text(content)

    result = find_orphaned_citations(str(file_path))

    # Each returned string should be pure digits, no "CHUNK-" prefix
    for r in result:
        assert r.isdigit(), f"Expected digit string, got {r!r}"
    assert result == ["42", "99", "7", "100"]
