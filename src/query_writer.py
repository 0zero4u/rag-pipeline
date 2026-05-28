"""
Query Writer Script
==================
Wrapper script for LightRAGWriterAgent to query LightRAG and return chunks.
Called via bash from the OpenCode agent.

Usage:
    python3 query_writer.py "your query here"
    python3 query_writer.py "Train to Pakistan Partition violence" 5
"""

import asyncio
import json
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def query_chunks(query: str, top_k: int = 5) -> list[dict]:
    """
    Query LightRAG and return relevant chunks.

    Args:
        query: Search query
        top_k: Number of chunks to retrieve

    Returns:
        List of dicts with chunk_index, ref_id, and content
        IMPORTANT: chunk_index is 1-based position in returned list
        IMPORTANT: ref_id is the document/file reference - same for all chunks from same file
    """
    from config import initialize_lightrag, create_llm_func

    working_dir = "/home/arshhtripathi/rag-pipeline/src/working_dir"

    try:
        config = await initialize_lightrag(working_dir=str(working_dir))
    except Exception as e:
        return [{"ref_id": "error", "content": f"Failed to initialize LightRAG: {e}"}]

    rag = config["rag"]

    from lightrag import QueryParam
    try:
        result = await rag.aquery(
            query,
            param=QueryParam(mode="naive", top_k=top_k, only_need_context=True)
        )
    except Exception as e:
        return [{"ref_id": "error", "content": f"Query failed: {e}"}]

    chunks = []
    result_str = str(result)

    code_block_match = re.search(r'```json\s*(.*?)\s*```', result_str, re.DOTALL)
    if code_block_match:
        json_text = code_block_match.group(1)
        for idx, line in enumerate(json_text.strip().split('\n'), 1):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    item = json.loads(line)
                    ref_id = item.get('reference_id', item.get('id', '?'))
                    content = item.get('content', item.get('text', ''))
                    if len(content) > 800:
                        content = content[:800] + "..."
                    # chunk_index is 1-based position for citation
                    # ref_id is document-level reference (same for all chunks from same file)
                    chunks.append({
                        'chunk_index': idx,
                        'ref_id': str(ref_id),
                        'content': content
                    })
                except json.JSONDecodeError:
                    pass

    if not chunks:
        if len(result_str) > 50:
            chunks = [{'chunk_index': 1, 'ref_id': '1', 'content': result_str[:800]}]
        else:
            chunks = [{'chunk_index': 1, 'ref_id': '1', 'content': 'No content retrieved'}]

    return chunks


def main():
    if len(sys.argv) < 2:
        print(json.dumps([{"ref_id": "usage", "content": "Usage: python3 query_writer.py 'your query' [top_k]"}]))
        return

    query = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    chunks = asyncio.run(query_chunks(query, top_k))
    print(json.dumps(chunks, indent=2))


if __name__ == "__main__":
    main()