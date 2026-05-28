"""
Citation Map Builder
====================
Builds a citation map from parsed PDFs for academic citation tracking.
Maps file names to full metadata and reference keys.
"""

import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class CitationEntry:
    """Single citation entry from a PDF."""
    filename: str
    title: str
    authors: list[str]
    year: str
    doi: str
    journal: str
    volume: str
    issue: str
    pages: str
    publisher: str
    reference_keys: list[str]


@dataclass 
class CitationMap:
    """Complete citation map for all parsed PDFs."""
    citations: dict[str, CitationEntry]
    author_index: dict[str, list[str]]  # author -> filenames
    year_index: dict[str, list[str]]   # year -> filenames


def build_reference_key(reference) -> str:
    """
    Build a unique key for a reference.
    
    Args:
        reference: dict with author, title, year info OR string reference
    
    Returns:
        String key in format "Author-Year" or "Author-nd" if no year
    """
    # Handle string references (URLs, plain text)
    if isinstance(reference, str):
        # Extract from URL or text
        import re
        match = re.search(r'(\w+)\s*\((\d{4})\)', reference)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return f"Unknown-n.d."
    
    authors = reference.get('authors', ['Unknown'])
    first_author = authors[0] if authors else 'Unknown'
    
    # Extract last name
    if ',' in first_author:
        last_name = first_author.split(',')[0].strip()
    else:
        # Handle "First Last" format
        parts = first_author.split()
        last_name = parts[-1] if parts else 'Unknown'
    
    year = reference.get('year', 'n.d.')
    
    return f"{last_name}-{year}"


def build_citation_map( parsed_pdfs: list[dict], output_path: Optional[str] = None) -> CitationMap:
    """
    Build citation map from parsed PDF results.
    
    Args:
        parsed_pdfs: List of ParsedPDF dicts (from parser.py output)
        output_path: Optional path to save citation map JSON
    
    Returns:
        CitationMap object
    """
    citations = {}
    author_index = defaultdict(list)
    year_index = defaultdict(list)
    
    for parsed in parsed_pdfs:
        # Support both dict and object formats
        if isinstance(parsed, dict):
            filename = parsed.get('filename', '')
            metadata = parsed.get('metadata')
        else:
            filename = getattr(parsed, 'filename', '')
            metadata = getattr(parsed, 'metadata', None)
        
        # Skip if no metadata
        if not metadata:
            continue
        
        # Handle metadata as dict or object
        if hasattr(metadata, 'get'):
            meta_dict = metadata
        elif hasattr(metadata, '__dict__'):
            meta_dict = metadata.__dict__
        else:
            continue
        
        # Build reference keys
        reference_keys = []
        for ref in meta_dict.get('references', []):
            key = build_reference_key(ref)
            reference_keys.append(key)
        
        # Create citation entry
        entry = CitationEntry(
            filename=filename,
            title=meta_dict.get('title', 'Unknown'),
            authors=meta_dict.get('authors', []) or [],
            year=meta_dict.get('year', 'n.d.'),
            doi=meta_dict.get('doi', ''),
            journal=meta_dict.get('journal', ''),
            volume=meta_dict.get('volume', ''),
            issue=meta_dict.get('issue', ''),
            pages=meta_dict.get('pages', ''),
            publisher=meta_dict.get('publisher', ''),
            reference_keys=reference_keys
        )
        
        citations[filename] = entry
        
        # Update indices
        for author in entry.authors:
            author_index[author].append(filename)
        
        if entry.year:
            year_index[entry.year].append(filename)
    
    citation_map = CitationMap(
        citations=citations,
        author_index=dict(author_index),
        year_index=dict(year_index)
    )
    
    # Save to file
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(citation_map), f, indent=2, ensure_ascii=False)
        print(f"Citation map saved to {output_path}")
    
    return citation_map


def load_citation_map(citation_map_path: str) -> CitationMap:
    """
    Load citation map from JSON file.
    
    Args:
        citation_map_path: Path to citation_map.json
    
    Returns:
        CitationMap object
    """
    with open(citation_map_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Convert citations dicts to CitationEntry objects
    citations = {}
    for filename, citation_data in data['citations'].items():
        if isinstance(citation_data, dict):
            citations[filename] = CitationEntry(
                filename=filename,
                title=citation_data.get('title', 'Unknown'),
                authors=citation_data.get('authors', []),
                year=citation_data.get('year', 'n.d.'),
                doi=citation_data.get('doi', ''),
                journal=citation_data.get('journal', ''),
                volume=citation_data.get('volume', ''),
                issue=citation_data.get('issue', ''),
                pages=citation_data.get('pages', ''),
                publisher=citation_data.get('publisher', ''),
                reference_keys=citation_data.get('reference_keys', [])
            )
        else:
            citations[filename] = citation_data
    
    return CitationMap(
        citations=citations,
        author_index=data['author_index'],
        year_index=data['year_index']
    )


def find_citing_papers(citation_map: CitationMap, reference_key: str) -> list[str]:
    """
    Find all papers that cite a given reference.
    
    Args:
        citation_map: CitationMap object
        reference_key: Key in format "Author-Year"
    
    Returns:
        List of filenames that cite this reference
    """
    citing = []
    
    for filename, entry in citation_map.citations.items():
        if reference_key in entry.reference_keys:
            citing.append(filename)
    
    return citing


def enrich_results(results: list[dict], citation_map: CitationMap) -> list[dict]:
    """
    Enrich query results with full citation metadata.
    
    Args:
        results: List of result dicts with 'source' (filename) field
        citation_map: CitationMap object
    
    Returns:
        Enriched results with citation metadata added
    """
    enriched = []
    
    for result in results:
        source = result.get('source', '')
        
        if source in citation_map.citations:
            citation = citation_map.citations[source]
            enriched_result = {
                **result,
                'citation': {
                    'title': citation.title,
                    'authors': citation.authors,
                    'year': citation.year,
                    'doi': citation.doi
                }
            }
        else:
            enriched_result = result
        
        enriched.append(enriched_result)
    
    return enriched


def print_citation_map_stats(citation_map: CitationMap):
    """Print statistics about the citation map."""
    print("\n=== Citation Map Statistics ===")
    print(f"Total papers: {len(citation_map.citations)}")
    print(f"Unique authors: {len(citation_map.author_index)}")
    print(f"Year coverage: {min(citation_map.year_index.keys()) if citation_map.year_index else 'N/A'} - {max(citation_map.year_index.keys()) if citation_map.year_index else 'N/A'}")
    
    # Top cited authors
    author_freq = [(author, len(filenames)) for author, filenames in citation_map.author_index.items()]
    author_freq.sort(key=lambda x: x[1], reverse=True)
    
    print("\nTop 10 cited authors:")
    for author, count in author_freq[:10]:
        print(f"  {author}: {count} citations")
    
    print(f"\nTotal unique references: {sum(len(e.reference_keys) for e in citation_map.citations.values())}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python citation_map.py <all_parsed.json> [output.json]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Load parsed PDFs
    with open(input_file, 'r', encoding='utf-8') as f:
        parsed_pdfs = json.load(f)
    
    # Build citation map
    citation_map = build_citation_map(parsed_pdfs, output_file)
    
    # Print stats
    print_citation_map_stats(citation_map)
