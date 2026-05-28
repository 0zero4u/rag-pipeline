"""
Citation Auditor
===============
Automatically checks if LLM hallucinations occur in citations.
Validates that cited chunks exist and metadata is correct.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

from src.config import initialize_lightrag, create_llm_func
from src.parser import parse_single_pdf


class CitationAuditor:
    """
    Audits LLM-generated citations for hallucinations.

    Checks:
    1. Cited chunk_ids actually exist
    2. Author names match citation_map
    3. Years match citation_map
    4. Quotes match actual chunk content
    """

    def __init__(self, working_dir: str, citation_map_path: str):
        self.working_dir = working_dir
        self.citation_map_path = citation_map_path
        self.citation_map = None
        self.chunks = None
        self.ref_id_to_filename = None

    async def setup(self):
        """Initialize LightRAG and load citation map."""
        # Load citation map
        with open(self.citation_map_path, 'r') as f:
            self.citation_map = json.load(f)

        # Initialize LightRAG
        config = await initialize_lightrag(self.working_dir)
        self.rag = config["rag"]

        # Build ref_id -> filename mapping
        self.ref_id_to_filename = {}
        doc_status_path = os.path.join(self.rag.working_dir, 'kv_store_doc_status.json')
        with open(doc_status_path, 'r') as f:
            doc_status_data = json.load(f)
        sorted_docs = sorted(
            doc_status_data.items(),
            key=lambda x: x[1].get('created_at', '')
        )
        for idx, (doc_id, status) in enumerate(sorted_docs, 1):
            if isinstance(status, dict) and 'file_path' in status:
                self.ref_id_to_filename[str(idx)] = status['file_path']

        # Load chunks from LightRAG text_chunks storage
        self.chunks = []
        chunks_path = os.path.join(self.rag.working_dir, 'kv_store_text_chunks.json')
        if os.path.exists(chunks_path):
            with open(chunks_path, 'r') as f:
                chunks_data = json.load(f)
            # Build list of chunks in order
            for chunk_id, chunk_data in chunks_data.items():
                self.chunks.append({
                    'chunk_id': chunk_id,
                    'content': chunk_data.get('content', '')
                })

    def check_chunk_exists(self, chunk_id: int) -> tuple[bool, str]:
        """Check if cited chunk exists. Returns (exists, message)."""
        if self.chunks is None:
            return False, "Chunks not loaded"

        if 1 <= chunk_id <= len(self.chunks):
            return True, "OK"
        else:
            return False, f"Chunk {chunk_id} out of bounds (have {len(self.chunks)} chunks)"

    def check_author_hallucination(self, citation: dict) -> tuple[bool, str]:
        """Check if author name is hallucinated. Returns (is_hallucination, message)."""
        source = citation.get('source', '')
        claimed_author = citation.get('author', '')

        if source not in self.citation_map:
            return True, f"Unknown source: {source}"

        expected_authors = self.citation_map[source].get('authors', [])
        if not expected_authors:
            return False, "No authors in citation_map (OK if paper has no author)"

        # Normalize for comparison
        def normalize(name):
            return name.lower().strip().replace('.', '')

        claimed = normalize(claimed_author)
        for expected in expected_authors:
            if normalize(expected) in claimed or claimed in normalize(expected):
                return False, f"OK (matched {expected})"

        return True, f"Hallucination: claimed '{claimed_author}' but expected one of {expected_authors}"

    def check_year_hallucination(self, citation: dict) -> tuple[bool, str]:
        """Check if year is hallucinated or wrong. Returns (is_hallucination, message)."""
        source = citation.get('source', '')
        claimed_year = citation.get('year', 'n.d.')

        if source not in self.citation_map:
            return True, f"Unknown source: {source}"

        expected_year = self.citation_map[source].get('year')

        if expected_year is None:
            # Year not available in paper
            if claimed_year in ['n.d.', 'None', None, 'null', '']:
                return False, "OK (year not available)"
            else:
                return True, f"Hallucination: claimed '{claimed_year}' but year unavailable"

        if str(claimed_year) == str(expected_year):
            return False, "OK"

        return True, f"Hallucination: claimed '{claimed_year}' but expected '{expected_year}'"

    def check_quote_match(self, citation: dict) -> tuple[bool, float]:
        """Check if quote is actually in the chunk. Returns (matches, similarity_score)."""
        quote = citation.get('quote', '').lower()
        chunk_id = citation.get('chunk_id', 0) - 1

        if not quote:
            return False, 0.0

        if self.chunks is None or chunk_id < 0 or chunk_id >= len(self.chunks):
            return False, 0.0

        chunk_content = self.chunks[chunk_id].get('content', '').lower()

        # Simple word overlap check
        quote_words = set(quote.split())
        chunk_words = set(chunk_content.split())

        if not quote_words:
            return False, 0.0

        overlap = len(quote_words & chunk_words) / len(quote_words)
        return overlap > 0.5, overlap

    def audit_citation(self, citation: dict) -> dict:
        """Audit a single citation. Returns audit result."""
        chunk_id = citation.get('chunk_id', 0)

        issues = []

        # Check 1: Chunk exists
        exists, msg = self.check_chunk_exists(chunk_id)
        if not exists:
            issues.append(f"Chunk existence: {msg}")

        # Check 2: Author hallucination
        is_halluc, msg = self.check_author_hallucination(citation)
        if is_halluc:
            issues.append(f"Author: {msg}")

        # Check 3: Year hallucination
        is_halluc, msg = self.check_year_hallucination(citation)
        if is_halluc:
            issues.append(f"Year: {msg}")

        # Check 4: Quote match
        matches, score = self.check_quote_match(citation)
        if not matches and exists:
            issues.append(f"Quote: Low match ({score:.2f})")

        return {
            "chunk_id": chunk_id,
            "source": citation.get('source'),
            "author": citation.get('author'),
            "year": citation.get('year'),
            "issues": issues,
            "is_hallucinated": len(issues) > 0
        }

    async def audit_query(self, query: str, top_k: int = 5) -> dict:
        """Run a query and audit all citations. Returns full audit report."""
        from lightrag import QueryParam
        from src.config import query_with_citations as qwc
        from src.config import create_llm_func

        # Get query result
        llm_func = create_llm_func()
        result = await qwc(
            self.rag, llm_func,
            query,
            citation_map_path=self.citation_map_path,
            top_k=top_k
        )

        # Audit each citation
        audit_results = [self.audit_citation(cit) for cit in result.get('citations', [])]

        hallucinated = [r for r in audit_results if r['is_hallucinated']]

        return {
            "query": query,
            "answer": result.get('answer', ''),
            "citations": audit_results,
            "total_citations": len(audit_results),
            "hallucinated_count": len(hallucinated),
            "is_clean": len(hallucinated) == 0
        }

    async def audit_batch(self, queries: list[str], top_k: int = 5) -> dict:
        """Audit multiple queries. Returns summary."""
        results = []
        for query in queries:
            result = await self.audit_query(query, top_k)
            results.append(result)

        total_citations = sum(r['total_citations'] for r in results)
        total_hallucinated = sum(r['hallucinated_count'] for r in results)

        return {
            "queries": results,
            "summary": {
                "total_queries": len(queries),
                "total_citations": total_citations,
                "hallucinated_citations": total_hallucinated,
                "accuracy": 1 - (total_hallucinated / max(total_citations, 1))
            }
        }


async def main():
    """CLI for citation auditor."""
    if len(sys.argv) < 3:
        print("Usage: python auditor.py <working_dir> <citation_map.json> [query]")
        print("Example:")
        print("  python auditor.py ./working_dir citation_map.json 'What are the main themes?'")
        sys.exit(1)

    working_dir = sys.argv[1]
    citation_map_path = sys.argv[2]
    query = sys.argv[3] if len(sys.argv) > 3 else "What are the main themes?"

    print(f"=== Citation Auditor ===")
    print(f"Working dir: {working_dir}")
    print(f"Citation map: {citation_map_path}")
    print(f"Query: {query}")
    print()

    auditor = CitationAuditor(working_dir, citation_map_path)
    await auditor.setup()

    result = await auditor.audit_query(query)

    print(f"=== Audit Result ===")
    print(f"Total citations: {result['total_citations']}")
    print(f"Hallucinated: {result['hallucinated_count']}")
    print(f"Clean: {result['is_clean']}")
    print()

    for cit in result['citations']:
        status = "❌" if cit['is_hallucinated'] else "✅"
        print(f"{status} Chunk {cit['chunk_id']}: {cit['author']} ({cit['year']})")
        if cit['issues']:
            for issue in cit['issues']:
                print(f"   - {issue}")
        print()

    if result['is_clean']:
        print("✅ All citations validated - no hallucinations detected!")
    else:
        print(f"❌ {result['hallucinated_count']} hallucination(s) detected")


if __name__ == "__main__":
    asyncio.run(main())
