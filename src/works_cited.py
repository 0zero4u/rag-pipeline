"""
Works Cited Generator
====================
Generates MLA 9th edition Works Cited section from citation_map.json.
"""

from citation_map import CitationMap, CitationEntry


def format_authors_mla(authors: list[str]) -> str:
    """Format author names in MLA style."""
    if not authors:
        return "Unknown"
    
    if len(authors) == 1:
        return authors[0]
    elif len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    else:
        return f"{authors[0]} et al."


def format_mla_entry(entry: CitationEntry) -> str:
    """Format a single citation entry in MLA 9th edition."""
    authors = format_authors_mla(entry.authors)
    year = entry.year or "n.d."
    title = entry.title or "Untitled"
    
    # Convert title to title case (first letter of each major word capitalized)
    title = title.title()
    
    if entry.journal:
        # Journal article format: Author. "Title." *Journal*, vol. #, Year, pp. #-#.
        volume = f", vol. {entry.volume}" if entry.volume else ""
        issue = f", no. {entry.issue}" if entry.issue else ""
        pages = f", pp. {entry.pages}" if entry.pages else ""
        journal = entry.journal.title()  # Italicize journal name
        return f'{authors}. "{title}." *{journal}*{volume}{issue}, {year}{pages}.'
    elif entry.publisher:
        # Book format: Author. *Title*. Publisher, Year.
        return f'{authors}. *{title}*. {entry.publisher}, {year}.'
    elif entry.doi:
        # DOI-only format: Author. "Title." Year. DOI.
        return f'{authors}. "{title}." {year}. {entry.doi}.'
    else:
        # Fallback format: Author. "Title." Year.
        return f'{authors}. "{title}." {year}.'


def generate_works_cited(citation_map: CitationMap, used_sources: set[str] = None) -> str:
    """Generate Works Cited section from citation map.
    
    Args:
        citation_map: CitationMap with all citations
        used_sources: Optional set of filenames that were actually cited.
                     If None, includes all sources.
    
    Returns:
        Formatted Works Cited section as string
    """
    entries = []
    
    for filename, entry in citation_map.citations.items():
        if used_sources is None or filename in used_sources:
            entries.append(format_mla_entry(entry))
    
    # Sort alphabetically by first author's last name
    entries.sort()
    
    if not entries:
        return ""
    
    return "Works Cited\n\n" + "\n\n".join(entries)


def get_used_sources_from_prose(prose: str, citation_map: CitationMap) -> set[str]:
    """Extract which sources were cited in the prose.
    
    Args:
        prose: The written prose with MLA citations
        citation_map: CitationMap with citation metadata
    
    Returns:
        Set of filenames that were cited
    """
    import re
    
    used_sources = set()
    
    # Find all inline citations: (Author. Title. Year.)
    # This is a simplified approach - in practice, we'd track during writing
    for filename, entry in citation_map.citations.items():
        # Check if author name appears in parentheses citations
        for author in entry.authors:
            last_name = author.split()[-1] if author else ""
            if last_name and f"({last_name}" in prose:
                used_sources.add(filename)
                break
    
    return used_sources
