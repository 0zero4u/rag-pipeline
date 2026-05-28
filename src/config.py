"""
LightRAG Configuration
====================
Configures LightRAG with OpenRouter API for embeddings and LLM.
"""

import os
import asyncio
from typing import List, Optional, Callable
from pathlib import Path
import numpy as np

from dotenv import load_dotenv
load_dotenv()


def get_openai_client():
    """Get OpenAI client configured for OpenRouter."""
    from openai import OpenAI

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        default_headers={
            "HTTP-Referer": "https://github.com/0zero4u/rag-pipeline",
            "X-OpenRouter-Title": "RAG Pipeline for Academic PDFs",
        }
    )


def create_embedding_func(model: str = "qwen/qwen3-embedding-8b") -> dict:
    """
    Create async embedding function using OpenRouter.

    Args:
        model: Embedding model name on OpenRouter

    Returns:
        dict with embedding_func, embedding_dim, max_token_size
    """
    from lightrag.utils import EmbeddingFunc

    client = get_openai_client()

    async def embed_func(texts: list[str]) -> np.ndarray:
        """Embed texts using OpenRouter."""
        if isinstance(texts, str):
            texts = [texts]

        response = client.embeddings.create(
            model=model,
            input=texts
        )

        return np.array([item.embedding for item in response.data])

    return EmbeddingFunc(
        embedding_dim=1024,
        max_token_size=8192,
        func=embed_func,
    )


def create_llm_func(
    model: str = "deepseek/deepseek-v4-flash",
    temperature: float = 0.0,
    max_tokens: int = 2048
) -> Callable:
    """
    Create async LLM function using OpenRouter.

    Args:
        model: LLM model name on OpenRouter
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate

    Returns:
        Async callable that takes prompt and returns response text
    """
    client = get_openai_client()

    import asyncio
    import time
    last_call_time = [0.0]  # Mutable container for closure

    async def generate(
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: list = [],
        **kwargs
    ) -> str:
        """Generate response using OpenRouter with rate limiting."""
        # Rate limit: min 0.3s between calls
        elapsed = time.time() - last_call_time[0]
        if elapsed < 0.3:
            await asyncio.sleep(0.3 - elapsed)
        last_call_time[0] = time.time()

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.extend(history_messages)
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        content = response.choices[0].message.content
        if content is None:
            content = ""
        return content

    return generate


async def initialize_lightrag(
    working_dir: str = "./working_dir",
    embedding_model: str = "perplexity/pplx-embed-v1-0.6b",
    llm_model: str = "deepseek/deepseek-v4-flash",
    chunk_token_size: int = 2000,
    language: str = "English"
) -> dict:
    """
    Initialize LightRAG with configuration.

    Args:
        working_dir: Directory for LightRAG working data
        embedding_model: OpenRouter embedding model
        llm_model: OpenRouter LLM model
        chunk_token_size: Token size for text chunking
        language: Language for entity extraction

    Returns:
        dict with LightRAG instance and helper functions
    """
    from lightrag import LightRAG

    working_dir = Path(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)

    embedding_func = create_embedding_func(embedding_model)
    llm_func = create_llm_func(llm_model)
    
    # Wrap LLM with GLiNER for fast entity extraction
    try:
        from gliner_extractor import create_gliner_llm_func
        llm_func = create_gliner_llm_func(llm_func)
        print("GLiNER enabled for entity extraction")
    except ImportError:
        print("GLiNER not available, using LLM for entity extraction")

    rag = LightRAG(
        working_dir=str(working_dir),
        llm_model_func=llm_func,
        embedding_func=embedding_func,
        kv_storage="JsonKVStorage",
        vector_storage="NanoVectorDBStorage",
        graph_storage="NetworkXStorage",
        enable_llm_cache_for_entity_extract=True,
        cosine_better_than_threshold=0.1,
    )

    await rag.initialize_storages()

    return {
        "rag": rag,
        "embedding_func": embedding_func,
        "llm_func": llm_func,
        "embedding_model": embedding_model,
        "llm_model": llm_model
    }


async def extract_metadata_batch(docs: list, llm_func: callable, batch_size: int = 5) -> list:
    """
    Extract metadata for multiple parsed PDFs using LLM.

    Args:
        docs: List of ParsedPDF objects
        llm_func: Async LLM function
        batch_size: Number of docs to process per batch (rate limit protection)

    Returns:
        List of docs with metadata filled in
    """
    import json, re, asyncio, time

    async def extract_one(doc) -> dict:
        prompt = f"""You are a research librarian. Extract metadata from this academic paper.
Return ONLY valid JSON with these exact keys:
- "title": paper title (string)
- "authors": list of author names (list of strings)
- "year": publication year (string or null)
- "abstract": first paragraph/sentence (string or null)
- "references": list of reference strings from the references section

=== START OF PAPER ===
{doc.start_snippet[:4000] if doc.start_snippet else doc.first_page_snippet[:2000]}
=== END OF PAPER ===
{doc.end_snippet[-4000:] if doc.end_snippet else ''}

Return JSON with all fields above. If year/abstract not found, use null. If no references, use empty list."""

        response = await llm_func(prompt)
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"title": None, "authors": [], "year": None, "abstract": None, "references": []}

    results = []
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        print(f"  Extracting metadata for batch {i//batch_size + 1}/{(len(docs) + batch_size - 1)//batch_size}...")

        metas = await asyncio.gather(*[extract_one(doc) for doc in batch], return_exceptions=True)

        for doc, meta in zip(batch, metas):
            if isinstance(meta, Exception):
                print(f"    Warning: Failed to extract metadata for {doc.filename}: {meta}")
                meta = {"title": None, "authors": [], "year": None, "abstract": None, "references": []}

            doc.metadata.title = meta.get('title') or doc.filename
            doc.metadata.authors = meta.get('authors', [])
            doc.metadata.year = meta.get('year')
            doc.metadata.abstract = meta.get('abstract') or ''
            doc.metadata.source = 'llm'
            doc.metadata.confidence = 'high' if meta.get('title') else 'low'
            results.append(doc)

        if i + batch_size < len(docs):
            time.sleep(1)

    return results


async def query_with_citations(
    rag,
    llm_func: callable,
    query: str,
    citation_map_path: str = "citation_map.json",
    top_k: int = 5
) -> dict:
    """
    Query LightRAG and return structured answer with verified citations.

    Args:
        rag: LightRAG instance
        llm_func: Async LLM function
        query: User question
        citation_map_path: Path to citation_map.json
        top_k: Number of chunks to retrieve

    Returns:
        dict with answer and validated citations
    """
    import json, re

    # Load citation map
    try:
        with open(citation_map_path, 'r', encoding='utf-8') as f:
            citation_map = json.load(f)
    except FileNotFoundError:
        citation_map = {}

    # Build reference_id -> filename mapping from rag's doc_status storage
    # reference_id is 1-indexed position in insertion order
    ref_id_to_filename = {}
    try:
        doc_status_path = os.path.join(rag.working_dir, 'kv_store_doc_status.json')
        with open(doc_status_path, 'r') as f:
            doc_status_data = json.load(f)
        # Sort by created_at to get insertion order
        sorted_docs = sorted(
            doc_status_data.items(),
            key=lambda x: x[1].get('created_at', '')
        )
        for idx, (doc_id, status) in enumerate(sorted_docs, 1):
            if isinstance(status, dict) and 'file_path' in status:
                ref_id_to_filename[str(idx)] = status['file_path']
    except Exception:
        pass

    # Get chunks from LightRAG (only context, not full answer)
    from lightrag import QueryParam
    result = await rag.aquery(query, param=QueryParam(mode='naive', top_k=top_k, only_need_context=True))
    context = str(result)

    # Parse LightRAG context - JSON objects, one per line inside code block
    chunks = []
    try:
        code_block_match = re.search(r'```json\s*(.*?)\s*```', context, re.DOTALL)
        if code_block_match:
            json_text = code_block_match.group(1)
            for line in json_text.strip().split('\n'):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        item = json.loads(line)
                        ref_id = str(item.get('reference_id', 'unknown'))
                        content = item.get('content', '')
                        chunks.append({'ref_id': ref_id, 'content': content[:500]})
                    except json.JSONDecodeError:
                        pass
    except Exception:
        chunks = [{'ref_id': '1', 'content': context[:1000]}]

    # Build context text for Gemini
    context_for_llm = ""
    for i, chunk in enumerate(chunks):
        context_for_llm += f"[CHUNK {i+1}]\n{chunk['content']}\n\n"

    # Ask Gemini for structured JSON answer
    system_prompt = """You are an academic research assistant. Answer based ONLY on chunks.
Return ONLY valid JSON with no markdown formatting:
{"answer": "...", "citations": [{"chunk_id": 1, "quote": "..."}]}"""

    prompt = f"""Question: {query}

Context:
{context_for_llm}

Answer using ONLY chunks above. Return ONLY raw JSON, no markdown."""

    response = await llm_func(prompt, system_prompt=system_prompt)

    # Parse JSON response - handle both raw JSON and markdown code block
    json_text = response.strip()
    if '```json' in json_text:
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', json_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
    else:
        json_match = re.search(r'(\{.*\})', json_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)

    try:
        structured = json.loads(json_text)
    except json.JSONDecodeError:
        structured = {"answer": response, "citations": []}

    # Validate citations against citation_map
    validated_citations = []
    for cit in structured.get('citations', []):
        try:
            chunk_id = int(cit.get('chunk_id', 1)) - 1
        except (ValueError, TypeError):
            chunk_id = 0
        if 0 <= chunk_id < len(chunks):
            ref_id = chunks[chunk_id]['ref_id']
            filename = ref_id_to_filename.get(ref_id, ref_id)
        else:
            filename = 'unknown'

        citation_data = citation_map.get(filename, {})
        authors = citation_data.get('authors', [])
        year = citation_data.get('year', 'n.d.')
        title = citation_data.get('title', filename)

        if authors:
            if len(authors) == 1:
                author_str = authors[0]
            elif len(authors) == 2:
                author_str = f"{authors[0]} & {authors[1]}"
            else:
                author_str = f"{authors[0]} et al."
        else:
            author_str = filename.split('.')[0]

        validated_citations.append({
            'chunk_id': chunk_id + 1,
            'source': filename,
            'author': author_str,
            'year': year,
            'title': title[:80] + '...' if len(title) > 80 else title,
            'quote': cit.get('quote', '')[:150]
        })

    return {
        'answer': structured.get('answer', response),
        'citations': validated_citations
    }


if __name__ == "__main__":
    print("Testing LightRAG configuration...")

    config = asyncio.run(initialize_lightrag())

    print("OpenRouter client configured")
    print(f"  Embedding model: {config['embedding_model']}")
    print(f"  LLM model: {config['llm_model']}")
    print("LightRAG initialized")
    print(f"  Working directory: {config['rag'].working_dir}")
