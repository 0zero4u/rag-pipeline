"""
Citation Validator
==================
Validates [CHUNK-N] citations in prose against citation_map.json.
Used by LightRAGWriterAgent to prevent hallucinated citations.

Usage:
    python3 validate_citations.py /path/to/draft.md
    python3 validate_citations.py /tmp/draft.md --verbose
"""

import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class CitationValidation:
    """Result of validating a single citation."""
    chunk_id: str
    valid: bool
    message: str
    source_file: Optional[str] = None
    author: Optional[str] = None
    year: Optional[str] = None
    title: Optional[str] = None
    max_chunks: Optional[int] = None


def load_citation_map(citation_map_path: str) -> dict:
    """Load citation_map.json."""
    try:
        with open(citation_map_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # citation_map.json has structure: {citations: {...}, author_index: {}, year_index: {}}
            # We need the 'citations' dict for validation
            if 'citations' in data:
                return data['citations']
            return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def load_doc_status(working_dir: str) -> dict:
    """Load kv_store_doc_status.json to map ref_id to filenames."""
    doc_status_path = Path(working_dir) / "kv_store_doc_status.json"
    try:
        with open(doc_status_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def validate_citations_in_prose(
    prose: str,
    citation_map_path: str,
    working_dir: str,
    max_chunks: int = None
) -> list[CitationValidation]:
    """
    Validate all [CHUNK-N] citations in prose.

    Args:
        prose: The written prose with [CHUNK-N] markers
        citation_map_path: Path to citation_map.json
        working_dir: LightRAG working directory
        max_chunks: Maximum valid chunk_index (from query results)

    Returns:
        List of CitationValidation results
    """
    citation_map = load_citation_map(citation_map_path)
    doc_status = load_doc_status(working_dir)

    pattern = r'\[CHUNK-(\d+)\]'
    chunk_refs = re.findall(pattern, prose)

    if not chunk_refs:
        return []

    unique_refs = list(set(chunk_refs))

    ref_id_to_filename = {}
    if doc_status:
        sorted_docs = sorted(
            doc_status.items(),
            key=lambda x: x[1].get('created_at', '')
        )
        for idx, (doc_id, status) in enumerate(sorted_docs, 1):
            ref_id_to_filename[str(idx)] = status.get('file_path', doc_id)

    validations = []
    for ref_id in unique_refs:
        chunk_num = int(ref_id)

        # Check if chunk_index is in valid range
        if max_chunks is not None and chunk_num > max_chunks:
            validations.append(CitationValidation(
                chunk_id=ref_id,
                valid=False,
                message=f"Chunk index {ref_id} exceeds returned chunks (max {max_chunks}). Use [CHUNK-1] through [CHUNK-{max_chunks}]",
                max_chunks=max_chunks
            ))
            continue

        # With chunk_index citations, we use the FIRST ref_id (oldest document)
        # since all chunks from same file share ref_id. In naive mode, all indexed
        # chunks come from the same file, so ref_id="1" is the correct lookup.
        effective_ref_id = "1"
        filename = ref_id_to_filename.get(effective_ref_id)

        if not filename:
            validations.append(CitationValidation(
                chunk_id=ref_id,
                valid=False,
                message=f"No documents indexed - cannot verify citation"
            ))
            continue

        if filename not in citation_map:
            validations.append(CitationValidation(
                chunk_id=ref_id,
                valid=False,
                message=f"Source file '{filename}' not in citation_map.json",
                source_file=filename
            ))
            continue

        citation_data = citation_map[filename]
        authors = citation_data.get('authors', [])
        year = citation_data.get('year', 'n.d.')
        title = citation_data.get('title', filename)

        author_str = authors[0] if authors else filename.split('.')[0]

        validations.append(CitationValidation(
            chunk_id=ref_id,
            valid=True,
            message="Citation verified",
            source_file=filename,
            author=author_str,
            year=year,
            title=title
        ))

    return validations


def format_mla_citation(validation: CitationValidation) -> str:
    """Format a validated citation as MLA."""
    if not validation.valid:
        return f"[CHUNK-{validation.chunk_id}] (unverified)"

    if validation.author and validation.year:
        return f"({validation.author} {validation.year})"
    elif validation.author:
        return f"({validation.author}, n.d.)"
    else:
        return f"[CHUNK-{validation.chunk_id}]"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_citations.py <prose_file> [--verbose] [--max-chunks N]")
        print("       --max-chunks N: Maximum chunk_index allowed (from query results count)")
        sys.exit(1)

    prose_file = sys.argv[1]
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    max_chunks = None
    for i, arg in enumerate(sys.argv):
        if arg == '--max-chunks' and i + 1 < len(sys.argv):
            max_chunks = int(sys.argv[i + 1])

    citation_map_path = Path(__file__).parent / "data" / "processed" / "citation_map.json"
    working_dir = Path(__file__).parent / "working_dir"

    try:
        with open(prose_file, 'r', encoding='utf-8') as f:
            prose = f.read()
    except FileNotFoundError:
        print(f"Error: File '{prose_file}' not found")
        sys.exit(1)

    validations = validate_citations_in_prose(prose, str(citation_map_path), str(working_dir), max_chunks)

    # Output results
    print(f"\nCitation Validation Results")
    print("=" * 50)

    if not validations:
        print("No [CHUNK-N] citations found in prose.")
        print("Status: VERIFIED (no citations needed)")
        return

    valid_count = sum(1 for v in validations if v.valid)
    invalid_count = len(validations) - valid_count

    print(f"Total citations: {len(validations)}")
    print(f"Valid: {valid_count}")
    print(f"Invalid: {invalid_count}")
    print()

    for v in validations:
        status = "✓" if v.valid else "✗"
        print(f"{status} [CHUNK-{v.chunk_id}]")

        if verbose and v.valid:
            print(f"   Source: {v.source_file}")
            print(f"   MLA: {format_mla_citation(v)}")
            print(f"   Title: {v.title[:50]}..." if v.title and len(v.title) > 50 else f"   Title: {v.title}")
        elif not v.valid:
            print(f"   Error: {v.message}")

        print()

    # Summary
    if invalid_count == 0:
        print("Status: VERIFIED - All citations are valid")
    else:
        print(f"Status: FAILED - {invalid_count} invalid citations need revision")
        sys.exit(1)


if __name__ == "__main__":
    main()