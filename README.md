# RAG Pipeline for Academic Research PDFs

End-to-end pipeline to process academic papers, build a knowledge graph, and query with **validated citations** that catch LLM hallucinations.

## Quick Start

```bash
# 1. Clone and enter repo
git clone https://github.com/0zero4u/rag-pipeline.git
cd rag-pipeline

# 2. Set up environment
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run pipeline
python -m src.main \
    --pdf-dir /path/to/your/pdfs \
    --output-dir ./data/processed \
    --working-dir ./working_dir
```

## API Keys

Only **OpenRouter** is needed (single key for everything):
- Get key: https://openrouter.ai/keys
- Models used:
  - `qwen/qwen3-embedding-8b` (embeddings)
  - `google/gemini-3.5-flash` (LLM for metadata + queries)
  - `cohere/rerank-4-fast` (reranking, optional)

## Key Features

### 1. Content Extraction (pymupdf4llm)
- Fast Markdown conversion
- Table structure (Markdown tables)
- Formula detection (LaTeX output)
- OCR for scanned PDFs
- No GPU required

### 2. Metadata Extraction (LLM)
- Title, authors, year, abstract from first page
- Batched async extraction (~$0.001/paper)
- PDFx for bibliography references

### 3. Citation Validation (Catches Hallucinations)
- `citation_map.json` - ground truth metadata
- LLM returns JSON citations with chunk_id + quote
- Validated against citation_map to catch:
  - Wrong author names
  - Wrong/missing years
  - Non-existent chunk citations

### 4. Query with Citations

```python
import asyncio
from src.config import (
    initialize_lightrag,
    create_llm_func,
    query_with_citations
)

async def main():
    config = await initialize_lightrag("./working_dir")
    rag = config["rag"]
    llm_func = config["llm_func"]

    result = await query_with_citations(
        rag, llm_func,
        "What are the main themes?",
        citation_map_path="citation_map.json"
    )

    print(result["answer"])
    for cit in result["citations"]:
        print(f"  [{cit['chunk_id']}] {cit['author']} ({cit['year']})")
        print(f"      {cit['title']}")
```

**Output:**
```
The main themes of the papers include...

CITATIONS:
  [1] Dr Urmila Devi (2021)
      Social and Political Aspects by Khushwant Singh
  [2] Naved Alam et al. (None)
      Exploring the Literary Contributions of Kushwant Singh...
```

## Project Structure

```
rag-pipeline/
├── src/
│   ├── __init__.py
│   ├── parser.py         # pymupdf4llm + PDFx parsing
│   ├── citation_map.py   # Build citation map
│   ├── config.py         # LightRAG + OpenRouter config
│   │                       # query_with_citations() function
│   └── main.py           # Main pipeline
├── data/
│   └── processed/        # Parsed output + citation_map.json
├── working_dir/          # LightRAG index
├── requirements.txt
└── .env.example
```

## Citation Validation Flow

```
Query → LightRAG → Chunks with reference_id
              ↓
        Gemini LLM → JSON: {answer, citations:[{chunk_id, quote}]}
              ↓
        Validate against citation_map.json
              ↓
        Author/Year/Title from ground truth
              ↓
        Final answer with verified citations
```

## Hallucination Detection

| Problem | Detection |
|---------|-----------|
| LLM cites non-existent chunk | Check chunk_id bounds |
| LLM cites wrong chunk | Match to actual reference_id |
| Wrong author name | Lookup filename in citation_map → replace |
| Wrong/missing year | Lookup in citation_map → replace with "n.d." if null |

---

## Last Updated

2026-05-28
