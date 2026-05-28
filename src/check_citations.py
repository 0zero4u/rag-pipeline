"""
Citation Marker Validator
========================
Checks that no [CHUNK-N] markers remain after CitationAdderAgent.

Usage:
    python3 check_citations.py /tmp/final_draft.md
    echo $?  # 0 = clean, 1 = orphaned markers found
"""

import sys
import re
from pathlib import Path


def find_orphaned_citations(file_path: str) -> list[str]:
    """Find all [CHUNK-N] markers in text."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = r'\[CHUNK-(\d+)\]'
    matches = re.findall(pattern, content)
    return matches


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 check_citations.py <file.md>")
        sys.exit(1)

    file_path = sys.argv[1]

    if not Path(file_path).exists():
        print(f"Error: File '{file_path}' not found")
        sys.exit(1)

    orphaned = find_orphaned_citations(file_path)

    if orphaned:
        print(f"ERROR: Found {len(orphaned)} orphaned [CHUNK-N] markers:")
        for marker in orphaned:
            print(f"  [CHUNK-{marker}]")
        print("\nThese must be converted to MLA format.")
        sys.exit(1)
    else:
        print("OK: No orphaned [CHUNK-N] markers found.")
        print("All citations properly converted to MLA format.")
        sys.exit(0)


if __name__ == "__main__":
    main()
