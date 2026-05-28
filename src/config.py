"""
LightRAG Configuration
=====================
Configures LightRAG with OpenRouter API for embeddings and LLM.
"""

import os
from typing import List, Optional, Callable
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def get_openai_client():
    """Get OpenAI client configured for OpenRouter."""
    from openai import OpenAI
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        defaultHeaders={
            "HTTP-Referer": "https://github.com/0zero4u/rag-pipeline",
            "X-OpenRouter-Title": "RAG Pipeline for Academic PDFs",
        }
    )


def create_embedding_function(model: str = "qwen/qwen3-embedding-8b") -> Callable:
    """
    Create embedding function using OpenRouter.
    
    Args:
        model: Embedding model name on OpenRouter
    
    Returns:
        Callable that takes text and returns embedding vector
    """
    client = get_openai_client()
    
    def embed(texts: List[str]) -> List[List[float]]:
        """Embed texts using OpenRouter."""
        if isinstance(texts, str):
            texts = [texts]
        
        response = client.embeddings.create(
            model=model,
            input=texts
        )
        
        return [item.embedding for item in response.data]
    
    return embed


def create_llm_function(
    model: str = "google/gemini-2.0-flash",
    temperature: float = 0.0,
    max_tokens: int = 2048
) -> Callable:
    """
    Create LLM function using OpenRouter.
    
    Args:
        model: LLM model name on OpenRouter
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
    
    Returns:
        Callable that takes prompt and returns response text
    """
    client = get_openai_client()
    
    def generate(prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response using OpenRouter."""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content
    
    return generate


def create_rerank_function(model: str = "cohere/rerank-4-fast") -> Callable:
    """
    Create rerank function using Cohere via OpenRouter.
    
    Args:
        model: Rerank model name on OpenRouter
    
    Returns:
        Callable that takes query, documents, top_n and returns reranked results
    """
    client = get_openai_client()
    
    def rerank(query: str, documents: List[str], top_n: int = 5) -> List[dict]:
        """Rerank documents using Cohere via OpenRouter.
        
        Note: OpenRouter's Cohere rerank uses chat completions endpoint
        with the rerank model. We simulate reranking by getting relevance scores.
        """
        if not documents:
            return []
        
        try:
            # Use OpenAI-compatible chat endpoint for reranking via OpenRouter
            # Cohere rerank-4-fast is available on OpenRouter
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a relevance scorer. Rate how relevant each document is to the query on a scale of 0-1."},
                    {"role": "user", "content": f"Query: {query}\n\nDocuments:\n" + "\n".join([f"{i}. {doc[:200]}" for i, doc in enumerate(documents)]) + "\n\nReturn relevance scores as JSON list."}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            
            # Try to parse scores from response
            import json
            import re
            
            # Look for JSON array in response
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                scores = json.loads(json_match.group())
                results = []
                for i, score in enumerate(scores[:top_n]):
                    results.append({
                        "index": i,
                        "document": {"text": documents[i]},
                        "relevance_score": float(score)
                    })
                # Sort by relevance score descending
                results.sort(key=lambda x: x["relevance_score"], reverse=True)
                return results
            else:
                # Fallback: return original order
                return [{"index": i, "document": {"text": doc}} for i, doc in enumerate(documents[:top_n])]
        
        except Exception as e:
            print(f"Warning: Reranking failed: {e}")
            return [{"index": i, "document": {"text": doc}} for i, doc in enumerate(documents[:top_n])]
    
    return rerank


def initialize_lightrag(
    working_dir: str = "./working_dir",
    embedding_model: str = "qwen/qwen3-embedding-8b",
    llm_model: str = "google/gemini-2.0-flash",
    chunk_token_size: int = 1000,
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
    
    # Create working directory
    working_dir = Path(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    
    # Create helper functions
    embedding_func = create_embedding_function(embedding_model)
    llm_func = create_llm_function(llm_model)
    
    # Initialize LightRAG
    rag = LightRAG(
        working_dir=str(working_dir),
        llm_model_func=llm_func,
        embedding_func=embedding_func,
        addon_params={
            "chunk_token_size": chunk_token_size,
            "language": language,
        },
    )
    
    return {
        "rag": rag,
        "embedding_func": embedding_func,
        "llm_func": llm_func,
        "embedding_model": embedding_model,
        "llm_model": llm_model
    }


if __name__ == "__main__":
    # Test initialization
    print("Testing LightRAG configuration...")
    
    config = initialize_lightrag()
    
    print("OpenRouter client configured")
    print(f"  Embedding model: {config['embedding_model']}")
    print(f"  LLM model: {config['llm_model']}")
    print("LightRAG initialized")
    print(f"  Working directory: {config['rag'].working_dir}")
