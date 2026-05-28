"""
Main Pipeline Script
====================
End-to-end RAG pipeline for academic research PDFs.
Combines parsing, citation mapping, and LightRAG retrieval.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from tqdm import tqdm

# Local modules
from parser import parse_pdfs, ParsedPDF
from citation_map import build_citation_map, load_citation_map, enrich_results
from config import initialize_lightrag
import asyncio


async def run_pipeline(
    pdf_dir: str,
    output_dir: str,
    working_dir: str = "./working_dir",
    embedding_model: str = "qwen/qwen3-embedding-8b",
    llm_model: str = "deepseek/deepseek-v4-flash",
    reindex: bool = False
):
    """
    Run the complete RAG pipeline.
    """
    pdf_dir = Path(pdf_dir)
    output_dir = Path(output_dir)
    working_dir = Path(working_dir)
    
    print("=" * 60)
    print("RAG Pipeline for Academic Research PDFs")
    print("=" * 60)
    
    # Step 1: Parse PDFs
    print("\n[1/4] Parsing PDFs with pymupdf4llm + PDFx...")
    parsed_pdfs = parse_pdfs(
        pdf_dir=str(pdf_dir),
        output_dir=str(output_dir)
    )
    print(f"Parsed {len(parsed_pdfs)} PDFs")

    # Step 2: Build citation map
    print("\n[2/4] Building citation map...")
    citation_map_path = output_dir / "citation_map.json"
    citation_map = build_citation_map(
        parsed_pdfs=[p if isinstance(p, dict) else p.__dict__ for p in parsed_pdfs],
        output_path=str(citation_map_path)
    )
    print(f"Citation map built with {len(citation_map.citations)} papers")
    
    # Step 3: Initialize LightRAG
    print("\n[3/4] Initializing LightRAG...")
    config = await initialize_lightrag(
        working_dir=str(working_dir),
        embedding_model=embedding_model,
        llm_model=llm_model
    )
    rag = config["rag"]
    print(f"Using embedding model: {embedding_model}")
    print(f"Using LLM model: {llm_model}")
    
    # Step 4: Index documents
    import time
    print("\n[4/4] Indexing documents into LightRAG...")
    t_start = time.time()

    # Load parsed results - use freshly parsed PDFs, not stale cache
    all_parsed_path = output_dir / "all_parsed.json"
    if all_parsed_path.exists() and not reindex:
        with open(all_parsed_path, 'r', encoding='utf-8') as f:
            all_parsed = json.load(f)
    else:
        from dataclasses import asdict
        from parser import PDFEncoder
        all_parsed = [p if isinstance(p, dict) else asdict(p) for p in parsed_pdfs]
        with open(all_parsed_path, 'w', encoding='utf-8') as f:
            json.dump(all_parsed, f, indent=2, ensure_ascii=False, cls=PDFEncoder)
    
    print(f"  Load parsed: {time.time() - t_start:.1f}s")
    
    # Insert documents with file paths
    documents = []
    file_paths = []
    
    for parsed in tqdm(all_parsed, desc="Preparing documents"):
        content = parsed.get('content', '')
        filename = parsed.get('filename', '')
        
        if content and filename:
            documents.append(content)
            file_paths.append(filename)
    
    print(f"  Prepare docs: {time.time() - t_start:.1f}s")
    
    if documents:
        print(f"Inserting {len(documents)} documents...")
        t_insert = time.time()
        await rag.ainsert(documents, file_paths=file_paths)
        print(f"  Insert: {time.time() - t_insert:.1f}s")
        print("Indexing complete!")
    else:
        print("No documents to index")
    
    print(f"  Total indexing: {time.time() - t_start:.1f}s")
    
    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("=" * 60)
    
    return {
        "rag": rag,
        "citation_map": citation_map,
        "config": config
    }


def query_pipeline(
    query: str,
    rag,
    citation_map,
    mode: str = "mix",
    top_k: int = 5,
    use_rerank: bool = False
):
    """
    Query the RAG pipeline with citation enrichment.
    
    Args:
        query: Search query
        rag: LightRAG instance
        citation_map: CitationMap instance
        mode: Query mode (local, global, hybrid, mix, naive)
        top_k: Number of results to return
        use_rerank: Whether to use reranking
    
    Returns:
        dict with answer and enriched citations
    """
    from lightrag import QueryParam
    
    # Get query results
    result = rag.query(
        query,
        param=QueryParam(mode=mode, top_k=top_k)
    )
    
    # Enrich with citations
    if isinstance(result, dict) and 'sources' in result:
        sources = result['sources']
    else:
        sources = []
    
    enriched = enrich_results(
        [{"source": s} for s in sources] if isinstance(sources, list) else sources,
        citation_map
    )
    
    return {
        "query": query,
        "answer": result if isinstance(result, str) else result.get('answer', str(result)),
        "sources": enriched
    }


def interactive_query(rag, citation_map):
    """
    Interactive query loop.
    """
    print("\n" + "=" * 60)
    print("Interactive Query Mode")
    print("Type 'exit' or 'quit' to stop")
    print("=" * 60)
    
    while True:
        query = input("\nQuery: ").strip()
        
        if query.lower() in ['exit', 'quit', 'q']:
            print("Goodbye!")
            break
        
        if not query:
            continue
        
        try:
            result = query_pipeline(query, rag, citation_map)
            
            print("\n--- Answer ---")
            print(result['answer'])
            
            if result['sources']:
                print("\n--- Citations ---")
                for i, source in enumerate(result['sources'], 1):
                    citation = source.get('citation', {})
                    print(f"{i}. {citation.get('title', 'Unknown')}")
                    print(f"   Authors: {', '.join(citation.get('authors', ['Unknown']))}")
                    print(f"   Year: {citation.get('year', 'n.d.')}")
                    if citation.get('doi'):
                        print(f"   DOI: {citation.get('doi')}")
        
        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            print(f"Error: {e}")


async def main():
    parser = argparse.ArgumentParser(description="RAG Pipeline for Academic PDFs")
    
    # Mode selection
    parser.add_argument('--mode', choices=['parse', 'index', 'query', 'all'],
                        default='all', help='Pipeline mode')
    
    # Paths
    parser.add_argument('--pdf-dir', default='./data/raw',
                        help='Directory containing PDFs')
    parser.add_argument('--output-dir', default='./data/processed',
                        help='Directory for processed output')
    parser.add_argument('--working-dir', default='./working_dir',
                        help='Directory for LightRAG index')
    parser.add_argument('--citation-map', default=None,
                        help='Path to existing citation map')
    
    # Models
    parser.add_argument('--embedding-model', default='perplexity/pplx-embed-v1-0.6b',
                        help='OpenRouter embedding model')
    parser.add_argument('--llm-model', default='deepseek/deepseek-v4-flash',
                        help='OpenRouter LLM model')
    
    # Options
    parser.add_argument('--reindex', action='store_true',
                        help='Reindex existing parsed PDFs')
    parser.add_argument('--interactive', action='store_true',
                        help='Interactive query mode')
    
    args = parser.parse_args()
    
    if args.mode == 'parse':
        parse_pdfs(args.pdf_dir, args.output_dir)
    
    elif args.mode == 'index':
        await run_pipeline(
            pdf_dir=args.pdf_dir,
            output_dir=args.output_dir,
            working_dir=args.working_dir,
            embedding_model=args.embedding_model,
            llm_model=args.llm_model,
            reindex=args.reindex
        )
    
    elif args.mode == 'query':
        citation_map = load_citation_map(args.citation_map or f"{args.output_dir}/citation_map.json")
        config = await initialize_lightrag(working_dir=args.working_dir)
        rag = config['rag']
        
        if args.interactive:
            interactive_query(rag, citation_map)
        else:
            print("Use --interactive for query mode")
    
    else:  # 'all'
        result = await run_pipeline(
            pdf_dir=args.pdf_dir,
            output_dir=args.output_dir,
            working_dir=args.working_dir,
            embedding_model=args.embedding_model,
            llm_model=args.llm_model,
            reindex=args.reindex
        )
        
        print("\nPipeline complete!")
        print(f"Output directory: {args.output_dir}")
        print(f"Working directory: {args.working_dir}")
        
        if args.interactive:
            interactive_query(result['rag'], result['citation_map'])


if __name__ == "__main__":
    asyncio.run(main())
