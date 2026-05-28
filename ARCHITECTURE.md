# RAG Pipeline for Academic Research PDFs

## Overview

A production-ready RAG pipeline designed to process 100+ academic research PDFs, extract structured metadata, build a knowledge graph, and provide accurate answers with **validated citations**.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG PIPELINE FOR ACADEMIC PDFs               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. PARSING LAYER                                               │
│     ├─► pymupdf4llm                                             │
│     │   • Fast Markdown conversion                              │
│     │   • Table structure (markdown tables)                      │
│     │   • Formula detection (LaTeX output)                      │
│     │   • OCR for scanned PDFs                                 │
│     │   • No GPU required                                      │
│     │                                                           │
│     └─► Metadata Extraction                                      │
│         ├─► LLM (gemini-3.5-flash)                            │
│         │   • First ~1500 chars of content                     │
│         │   • Extracts: title, authors, year, abstract         │
│         │                                                       │
│         └─► PDFx (references only)                              │
│             • Bibliography extraction                            │
│                                                                 │
│  2. CITATION MAP                                                │
│     └─► citation_map.json                                       │
│         • filename → {title, authors, year, abstract}           │
│         • Source of truth for citation validation                │
│                                                                 │
│  3. RAG ENGINE                                                  │
│     ├─► LightRAG (naive mode)                                 │
│     │   • Vector similarity search                              │
│     │   • Returns chunks with reference_id                      │
│     │                                                           │
│     └─► gemini-3.5-flash                                       │
│         • Second LLM call for structured answer                │
│                                                                 │
│  4. CITATION VALIDATION                                          │
│     └─► query_with_citations()                                 │
│         • Validates LLM citations against citation_map.json     │
│         • Catches hallucinations                                │
│         • Returns structured answer with verified citations     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
PDFs
  │
  ▼
parse_single_pdf() ──────────────────────────────────────────┐
  │                                                             │
  ├─► pymupdf4llm.to_markdown() → content                      │
  │                                                             │
  ├─► extract_references_with_pdfx() → references               │
  │                                                             │
  └─► first_page_snippet (for metadata extraction)               │
                                                                │
  ▼
extract_metadata_batch() ─────────────────────────────────────┐
  │                                                             │
  └─► LLM (gemini-3.5-flash)                                  │
        • Extracts: title, authors, year, abstract             │
        • Returns ParsedPDF with metadata                       │
                                                                │
  ▼
Build citation_map.json ──────────────────────────────────────┐
  │                                                             │
  └─► {filename: {title, authors, year, abstract, ...}}        │
      • Source of truth for citation validation                 │
                                                                │
  ▼
LightRAG.insert() ────────────────────────────────────────────┐
  │                                                             │
  └─► Chunks indexed with qwen/qwen3-embedding-8b              │
                                                                │
  ▼
query_with_citations() ──────────────────────────────────────┐
  │                                                             │
  ├─► LightRAG.aquery() → chunks with reference_id             │
  │                                                             │
  ├─► LLM (gemini-3.5-flash)                                  │
  │     • "Return JSON: {answer, citations:[{chunk_id, quote}]}" │
  │                                                             │
  └─► VALIDATION against citation_map.json                     │
        • Maps reference_id → filename → {title, authors, year} │
        • Catches hallucinations (LLM may cite wrong chunk)     │
        • Returns structured answer with verified citations     │
```

---

## Citation Validation Flow

### Problem
LLM may hallucinate citations - cite chunks that don't exist, wrong authors, or wrong metadata.

### Solution
Two-layer validation:

1. **Chunk existence check**: LLM cites `chunk_id` → verify chunk exists in retrieved chunks
2. **Metadata validation**: filename → lookup in `citation_map.json` → verify author/year/title

### Example

**LLM returned:**
```json
{
  "answer": "The main themes include... [1], [2]",
  "citations": [
    {"chunk_id": 1, "quote": "Some text about..."},
    {"chunk_id": 5, "quote": "More text..."}
  ]
}
```

**Validation process:**
```
chunk_id=1 → ref_id from chunk → filename → citation_map.json
  → Authors: ["Dr Urmila Devi"], Year: "2021"
  → Validated: [Dr Urmila Devi (2021)]

chunk_id=5 → ref_id from chunk → filename → citation_map.json
  → Authors: ["Naved Alam", "Md. Rizwan Khan", ...], Year: null
  → Validated: [Naved Alam et al. (n.d.)]
```

### Hallucination Detection

| Hallucination Type | Detection Method | Result |
|--------------------|-----------------|--------|
| LLM cites non-existent chunk | Check chunk_id < len(chunks) | Flag as "unknown" |
| LLM cites wrong chunk_id | Match chunk_id to actual ref_id | Use actual filename |
| Author name wrong | Compare to citation_map.json | Replace with correct |
| Year wrong/missing | Compare to citation_map.json | Replace with correct (or "n.d.") |

---

## Component Details

### 1. Parsing Layer

#### pymupdf4llm (Primary Content Extractor)

| Feature | Status |
|---------|--------|
| Multi-column text extraction | ✅ Supported |
| Table structure extraction | ✅ Markdown tables |
| Formula recognition | ✅ LaTeX output |
| OCR for scanned PDFs | ✅ Supported |
| Fast conversion | ✅ 10-250× faster than vision-based |
| No GPU required | ✅ |

#### Metadata Extraction (LLM + PDFx)

| Feature | Status | Notes |
|---------|--------|-------|
| Title extraction | ✅ LLM | First ~1500 chars |
| Author extraction | ✅ LLM | Handles multiple authors |
| Year extraction | ✅ LLM | From first page text |
| Abstract extraction | ✅ LLM | First paragraph |
| References list | ✅ PDFx | Bibliography extraction |
| PDF metadata fields | ❌ Empty | Academic papers rarely fill these |

**Key Finding:** Academic papers leave PDF metadata fields empty. Metadata lives in paper text.

**Cost:** ~$0.001 per paper (gemini-3.5-flash)

---

### 2. Citation Map

#### citation_map.json

Built from parsed PDFs, serves as ground truth for citation validation.

```json
{
  "CET-JJ21-8-Dr-Unrmila-Devi.pdf": {
    "title": "Social and Political Aspects by Khushwant Singh",
    "authors": ["Dr Urmila Devi"],
    "year": "2021",
    "abstract": "Social and political worries in his works...",
    "references": []
  },
  "English.pdf": {
    "title": "Exploring the Literary Contributions of Kushwant Singh...",
    "authors": ["Naved Alam", "Md. Rizwan Khan", "Faizur Rehman Sherwani", "Rehan Khan"],
    "year": null,
    "abstract": "This research paper aims to analyze...",
    "references": []
  }
}
```

---

### 3. RAG Engine

#### LightRAG (Naive Mode)

Used for vector similarity search. Naive mode = no entity extraction = faster indexing.

| Feature | Status |
|---------|--------|
| Vector similarity search | ✅ |
| Chunk retrieval | ✅ Returns chunks with reference_id |
| Naive mode (no KG) | ✅ Faster for Q&A |

#### Query Response Format

LightRAG returns context with `reference_id`:

```json
[
  {"reference_id": "1", "content": "First chunk text..."},
  {"reference_id": "2", "content": "Second chunk text..."}
]
```

---

### 4. Citation Validation

#### query_with_citations()

Main function for querying with validated citations.

```python
async def query_with_citations(
    rag,
    llm_func,
    query: str,
    citation_map_path: str = "citation_map.json",
    top_k: int = 5
) -> dict:
    """
    Returns:
        {
            "answer": "The main themes are...",
            "citations": [
                {
                    "chunk_id": 1,
                    "source": "CET-JJ21-8-Dr-Unrmila-Devi.pdf",
                    "author": "Dr Urmila Devi",
                    "year": "2021",
                    "title": "Social and Political Aspects...",
                    "quote": "Relevant quote from chunk..."
                }
            ]
        }
    """
```

---

## Configuration

### Environment

```bash
OPENROUTER_API_KEY=your_key
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `parse_single_pdf(pdf_path)` | Parse PDF, extract content + references |
| `extract_metadata_batch(docs, llm_func)` | Async batch metadata extraction |
| `initialize_lightrag(working_dir)` | Initialize LightRAG |
| `query_with_citations(rag, llm_func, query)` | Query with validated citations |

### Usage Example

```python
import asyncio
from src.config import (
    initialize_lightrag,
    create_llm_func,
    extract_metadata_batch
)
from src.parser import parse_single_pdf

async def main():
    # 1. Parse and extract metadata
    doc = parse_single_pdf("paper.pdf")
    llm_func = create_llm_func()
    docs = await extract_metadata_batch([doc], llm_func)

    # 2. Build citation_map.json
    citation_map = {d.filename: {
        "title": d.metadata.title,
        "authors": d.metadata.authors,
        "year": d.metadata.year,
        ...
    } for d in docs}
    json.dump(citation_map, open("citation_map.json", "w"))

    # 3. Initialize LightRAG and insert
    config = await initialize_lightrag("./working_dir")
    rag = config["rag"]
    await rag.ainsert(doc.content, file_paths=[doc.filename])

    # 4. Query with citations
    result = await query_with_citations(
        rag, llm_func,
        "What are the main themes?",
        citation_map_path="citation_map.json"
    )

    print(result["answer"])
    for cit in result["citations"]:
        print(f"  [{cit['chunk_id']}] {cit['author']} ({cit['year']})")
        print(f"      {cit['title']}")

asyncio.run(main())
```

---

## Status Summary

| Component | Status | Notes |
|----------|--------|-------|
| pymupdf4llm | ✅ Complete | Primary content extractor |
| LLM metadata | ✅ Complete | gemini-3.5-flash |
| PDFx references | ✅ Complete | Bibliography only |
| citation_map.json | ✅ Complete | Ground truth for validation |
| LightRAG | ✅ Complete | Naive mode for Q&A |
| Embeddings | ✅ Complete | qwen/qwen3-embedding-8b |
| Citation validation | ✅ Complete | Catches hallucinations |
| query_with_citations | ✅ Complete | Returns structured citations |

**Architecture: 100% Resolved**

---

## References

- [pymupdf4llm GitHub](https://github.com/pymupdf/pymupdf4llm)
- [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
- [PDFx Documentation](https://github.com/metachris/pdfx)
- [OpenRouter API](https://openrouter.ai/docs)

---

## Last Updated

2026-05-28
