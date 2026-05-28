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
│     │   • OCR for scanned PDFs (Tesseract)                       │
│     │   • No GPU required                                      │
│     │                                                           │
│     └─► Metadata Extraction (Start + End)                        │
│         ├─► LLM (DeepSeek v4 Flash)                            │
│         │   • First 4000 chars (title, authors, abstract)       │
│         │   • Last 4000 chars (references, conclusion)           │
│         │   • 2 calls per PDF (not per chunk)                    │
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
  ├─► extract_references_with_pdfx() → references             │
  │                                                             │
  └─► start_snippet (first 4000 chars)                        │
      end_snippet (last 4000 chars)                            │
                                                                 │
  ▼
extract_metadata_batch() ─────────────────────────────────────┐
  │                                                             │
  └─► LLM (DeepSeek v4 Flash)                                  │
        • Start 4000 + End 4000 chars per PDF                 │
        • Extracts: title, authors, year, abstract, refs      │
        • 1 call per PDF (reduced from 8)                      │
                                                                 │
  ▼
Build citation_map.json ──────────────────────────────────────┐
  │                                                             │
  └─► {filename: {title, authors, year, abstract, ...}}        │
      • Source of truth for citation validation                 │
                                                                 │
  ▼
LightRAG.ainsert() ────────────────────────────────────────────┐
  │                                                             │
  ├─► Perplexity pplx-embed-v1-0.6b (1024-dim embeddings)     │
  │                                                             │
  └─► Entity extraction via LLM (DeepSeek)                    │
        • 8 chunks per PDF = 8 LLM calls                      │
        • Creates knowledge graph                               │
                                                                 │
  ▼
query_writer.py ──────────────────────────────────────────────┐
   │                                                             │
   ├─► LightRAG.aquery() → chunks with reference_id            │
   │                                                             │
   └─► Returns JSON: [{chunk_index, ref_id, content}, ...]     │
         • chunk_index: 1-based position for [CHUNK-N] citations│
         • ref_id: document-level reference (same for all chunks│
           from same file)                                       │
                                                                 │
  ▼
validate_citations.py ────────────────────────────────────────┐
   │                                                             │
   ├─► Validates [CHUNK-N] citations against max_chunks         │
   │     • Rejects [CHUNK-N] where N > returned chunks          │
   │                                                             │
   ├─► Checks filename exists in citation_map.json              │
   │                                                             │
   └─► Flags hallucinated citations with specific error          │
         • Human reviews and corrects                            │
                                                                           │
   Usage: validate_citations.py /tmp/draft.md --max-chunks N
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

### Error Handling

When citation validation fails, the system follows this protocol:

| Failure Type | System Response | User Action |
|--------------|-----------------|-------------|
| Non-existent chunk citation | Citation marked as `[CHUNK-unverified]` | Verify against source PDF manually |
| Wrong author name | Replaced with correct name from citation_map.json | Review corrected citation |
| Missing/invalid year | Replaced with "n.d." | Add year if found in source |
| Unverifiable claim | Text flagged, writer instructed: "I don't have sufficient information about [topic]" | Re-write claim or provide source |

#### validate_citations.py Protocol

```python
# When validation detects hallucination:
1. Log the invalid citation with reference_id and reason
2. Mark chunk as [CHUNK-unverified] in output
3. Do NOT remove citation from prose - flag for review
4. Continue processing remaining citations

# User override:
- If citation is valid but flagged, user can dismiss false positive
- Citation remains with warning flag for human review
```

#### Recovery Workflow

```
Hallucination Detected
    ↓
Flag citation as [CHUNK-unverified]
    ↓
Log to validation_report.json
    ↓
User reviews flagged citation
    ↓
Either: Correct citation with source evidence
   Or: Remove/re-write claim without citation
    ↓
Continue dissertation writing
```

**Key Principle:** Never suppress citations - always flag and let human verify. The tool prevents hallucinations, but human has final authority.

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
| Title extraction | ✅ LLM | Start 4000 + End 4000 chars |
| Author extraction | ✅ LLM | Handles multiple authors |
| Year extraction | ✅ LLM | From start/end of paper |
| Abstract extraction | ✅ LLM | First paragraph from start |
| References list | ✅ LLM + PDFx | From end of paper |
| LLM calls per PDF | 2 (reduced from 8) | Start + End feeding |

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

**Source file:** `src/validate_citations.py`

This script validates `[CHUNK-N]` citations in prose against the indexed chunks:
```bash
python3 src/validate_citations.py /path/to/draft.md
```

Output: JSON report of valid/invalid citations with correction suggestions.

---

## Working Pipeline (E2E Verified)

### Full Flow

```
1. INDEXING
   python main.py --mode index --pdf-dir ./data/raw
   │
   ├─► Parse PDFs (pymupdf4llm)
   │     └─► Extract start_snippet (4000 chars) + end_snippet (4000 chars)
   │
   ├─► Build citation_map.json
   │     └─► 1 LLM call per PDF for metadata
   │
   └─► Index to LightRAG
         └─► Embed with Perplexity pplx-embed-v1-0.6b
         └─► Entity extraction via DeepSeek (8 chunks = 8 calls)

2. QUERYING (via Agent)
   python query_writer.py "topic" 5
   │
   └─► LightRAG.aquery() → chunks with chunk_index and ref_id
         └─► Returns: [{chunk_index: 1, ref_id: "1", content: "..."}, ...]

3. WRITING (via Agent)
   │
   ├─► Agent writes with [CHUNK-N] citations (using chunk_index)
   │
   └─► Save to /tmp/draft.md

4. VALIDATION
   python validate_citations.py /tmp/draft.md --max-chunks N
   │
   ├─► Check each [CHUNK-N] where N ≤ max_chunks
   ├─► Verify filename in citation_map.json
   └─► Flag invalid citations with specific error message
```

### E2E Test Results (Verified 2026-05-28)

| Stage | Time | Status |
|-------|------|--------|
| Parse PDF | 4.14s | ✅ 41005 chars, 7 pages |
| Metadata (start+end) | 12.94s | ✅ Title, authors, year extracted |
| LightRAG init | 0.85s | ✅ |
| Query | 0.92s | ✅ Returns 8 chunks with chunk_index |
| Validation | 0.07s | ✅ Works with --max-chunks |

**Hallucination Fix (2026-05-28):**

Root cause: Agent saw 8 chunks all with ref_id=1, hallucinated chunk numbers [CHUNK-4/5/7].

Fix applied:
1. **query_writer.py**: Returns `chunk_index` (1-based position) for [CHUNK-N] citations
2. **validate_citations.py**: New `--max-chunks N` flag rejects citations exceeding returned chunks
3. **lightrag-writer-agent.md**: Updated prompt to clarify chunk_index vs ref_id

**E2E Test (After Fix):**

Prose written:
> "Khushwant Singh's writing is characterized by straightforwardness, vivid imagery, and an unafraid approach to delicate subjects, employing satire and comedy to engage readers [CHUNK-5]. His style reflects a harmonious fusion of liberal humanism and scientific rationality shaped by both Indian and Western traditions [CHUNK-1]. Train to Pakistan represents his first work to truthfully depict the Partition era, driven by a personal sense of guilt over his failure to intervene during the violence [CHUNK-4]."

Result: ✅ All 3 citations valid (CHUNK-1,4,5 ≤ 5 chunks returned)

**Verified Citation Metadata (7-8-14-837.pdf):**
| Field | Value |
|-------|-------|
| Author | Suman Rani, Dr. Pawan Kumar Sharma |
| Year | 2024 |
| Title | A critical study of the portrayal of satire in Khushwant Singh's selected novels |

### Key Insight

All chunks from same document share the same `reference_id` (file-level citation). In naive mode, LightRAG returns multiple text segments but they reference the same document ID.

**IMPORTANT: Use chunk_index for [CHUNK-N] citations**, not ref_id. The chunk_index is the 1-based position in the returned list, unique per retrieved chunk.

---

## Pitfalls and Common Issues

### 1. Path Mismatches

**Issue**: Different components use different working directory paths.

| Component | Expected Path |
|-----------|---------------|
| `main.py` | `./working_dir` (relative to src/) |
| `query_writer.py` | `/home/arshhtripathi/rag-pipeline/src/working_dir` |
| `validate_citations.py` | `/home/arshhtripathi/rag-pipeline/src/working_dir` |

**Fix**: All paths are now absolute or correctly relative to src/. Always use:
```python
working_dir = Path(__file__).parent / "working_dir"  # For scripts in src/
```

### 2. Cache Stale Data

**Issue**: `all_parsed.json` caches parsed PDFs. When re-indexing different PDFs, old cached data is used.

**Symptom**: Query returns content from wrong PDF despite fresh indexing.

**Fix**: `main.py` now saves fresh cache on each run. Use `--reindex` flag to force fresh parsing.

### 3. LightRAG Duplicate Detection

**Issue**: LightRAG hashes content and refuses to re-index same PDF twice.

**Symptom**: "Duplicate document detected" warning, no new chunks created.

**Fix**: Delete working_dir contents before re-indexing same PDF:
```bash
rm -rf /home/arshhtripathi/rag-pipeline/src/working_dir/*
```

### 4. top_k vs Actual Chunks

**Issue**: `top_k=5` does NOT guarantee 5 chunks returned. LightRAG returns all matching chunks (typically 5-8).

**Symptom**: Agent uses [CHUNK-6] but only asked for 5 chunks.

**Fix**: Always count actual chunks in JSON response. Use `--max-chunks N` where N = actual count.

### 5. Metadata Extraction Failures

**Issue**: Non-standard PDF formats (poor OCR, unusual layouts) fail LLM metadata extraction.

**Symptom**: `citation_map.json` has empty authors, year=null, title=filename.

**Fix**: Manually edit citation_map.json for problematic PDFs, or use PDFs with standard academic format.

### 6. Chunk Index vs Reference ID

**Issue**: All chunks from same file share `ref_id="1"`. Using `ref_id` for citations gives wrong results.

**Symptom**: [CHUNK-2] validated as "ref_id=2" which doesn't exist.

**Fix**: Use `chunk_index` (1-based position) for [CHUNK-N] citations. Validation maps chunk_index to ref_id="1" for filename lookup.

### 7. Naive Mode Single Document Limitation

**Issue**: In naive mode, all chunks come from same document → all have ref_id="1".

**Fix**: The citation validation uses effective_ref_id="1" for all chunk_index lookups since naive mode only indexes one document at a time.

### 8. Multi-PDF Retrieval Behavior

**Behavior**: When multiple PDFs are indexed, `top_k=5` returns the 5 most similar chunks from **ALL indexed PDFs**, not top 5 per PDF.

**Example with 2 PDFs indexed:**
```
top_k=5 might return 9 chunks:
├── ref_id=1 (Partition_Violence...pdf): [CHUNK-1, 2, 3, 4, 6, 7]
└── ref_id=2 (Portrayal of Violence...pdf): [CHUNK-5, 8, 9]
```

**Note**: LightRAG may return more than `top_k` due to:
- Tied similarity scores
- Internal chunk_top_k setting
- Same-document chunk grouping

**Fix**: Always count actual chunks in JSON array for `--max-chunks`.

### 9. top_k vs Actual Returned Chunks

**Issue**: `top_k` parameter is a hint, not a guarantee.

| top_k | Actual Chunks | Reason |
|-------|---------------|--------|
| 5 | 5-9 | Ties, internal grouping |
| 10 | 10-15 | Similar behavior |

**Recommendation**: With 100 PDFs, use `top_k=10-20` for better coverage. LLM has 1M context, cost is minimal for text chunks.

### 10. Cache Freshness Rules

**Current indexed state** (as of 2026-05-28):
| Location | Count | PDFs |
|---------|-------|------|
| `working_dir/` | 2 | 7th + 8th smallest |
| `data/processed/` | 2 | Same 2 PDFs |

**When is cache fresh vs stale?**

| Scenario | Cache Fresh? | Action Required |
|----------|--------------|----------------|
| Fresh start with new PDFs only | ✅ Fresh | Clear working_dir + data/processed first |
| Adding PDFs to existing index | ⚠️ Mixed | Clear working_dir, keep data/processed |
| Same PDF re-indexed | ❌ Stale | LightRAG duplicate detection prevents re-index |
| New PDF with `--reindex` | ✅ Fresh | main.py saves fresh cache |

**When to use --reindex:**
- Adding new PDFs to existing index
- Ensures fresh parsing

**When to clear manually:**
```bash
rm -rf working_dir/* data/processed/*
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

query_writer.py returns chunks with both `chunk_index` and `reference_id`:

```json
[
  {"chunk_index": 1, "ref_id": "1", "content": "First chunk text..."},
  {"chunk_index": 2, "ref_id": "1", "content": "Second chunk text..."}
]
```

- **chunk_index**: 1-based position in returned list → use for [CHUNK-N] citations
- **ref_id**: document-level reference (same for all chunks from same file)

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

## What We DON'T Need

### Cohere Rerank
- **Not needed** ❌
- Adds latency and cost
- LightRAG cosine similarity + LLM's 1M context is sufficient
- Rerank warning appears in logs but can be ignored

### auditor.py
- **Not integrated** ❌
- Standalone CitationAuditor class exists but not used
- We use `validate_citations.py` for citation validation instead

---

## 3-Agent Citation Pipeline

### Workflow

```
1. LightRAGWriterAgent
   └── Writes prose with [CHUNK-N] markers
       └── Uses RAG via query_writer.py

2. HumanizeAgent
    └── Paraphrases prose, removes AI patterns
        └── PRESERVES [CHUNK-N] markers
            └── Does NOT use RAG (receives ready content)

3. CitationAdderAgent
    └── Converts [CHUNK-N] to MLA inline citations
        └── Reads citation_map.json for metadata
            └── Does NOT use RAG

4. Validation (check_citations.py)
    └── Verifies no orphaned [CHUNK-N] remain
```

### Agent Files

| Agent | Location |
|-------|----------|
| LightRAGWriterAgent | `~/.config/opencode/agents/lightrag-writer-agent.md` |
| HumanizeAgent | `~/.config/opencode/agents/humanize-agent.md` |
| CitationAdderAgent | `~/.config/opencode/agents/citation-adder-agent.md` |

### MLA Citation Format

```(Author. Title. Publisher, Year.)```

**Example:**
```
[CHUNK-5] → (Butalia, Urvashi. The Other Side of Silence. Penguin Books, 1998.)
```

### Validation Script

```bash
python3 check_citations.py /tmp/final_draft.md
# Output: OK: No orphaned [CHUNK-N] markers found.
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
| Embeddings | ✅ Complete | perplexity/pplx-embed-v1-0.6b |
| query_writer.py | ✅ Complete | chunk_index for citations |
| validate_citations.py | ✅ Complete | --max-chunks flag |
| check_citations.py | ✅ Complete | orphaned [CHUNK-N] validator |
| LightRAGWriterAgent | ✅ Complete | writes with [CHUNK-N] |
| HumanizeAgent | ✅ Complete | paraphrase, preserve markers |
| CitationAdderAgent | ✅ Complete | MLA conversion |
| Cohere Rerank | ❌ Not needed | LightRAG similarity sufficient |
| auditor.py | ❌ Not used | validate_citations.py in use |

**Architecture: 100% Resolved**

---

## References

- [pymupdf4llm GitHub](https://github.com/pymupdf/pymupdf4llm)
- [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
- [PDFx Documentation](https://github.com/metachris/pdfx)
- [OpenRouter API](https://openrouter.ai/docs)

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| `RIPPLE_DEPENDENCIES.md` | Track changes that ripple across multiple files |
| `chapter_plan.md` | Dissertation structure for Train to Pakistan study |
| `PLAN.md` | Implementation plan for LightRAGWriterAgent |

---

## Last Updated

2026-05-28 (top_k=150, enhanced HumanizeAgent, ripple dependencies doc)
