# Local Config Backup

**Date**: 2026-05-28
**Purpose**: Backup of all local configs and settings

---

## Working Directory Config

**File**: `src/working_dir/config.json`

```json
{
  "embedding_model": "qwen/qwen3-embedding-8b",
  "llm_model": "deepseek/deepseek-v4-flash"
}
```

---

## Environment Variables

**File**: `.env`

```
OPENROUTER_API_KEY=sk-or-v1-... (see .env file)
DATA_DIR=./data/raw
PROCESSED_DIR=./data/processed
WORKING_DIR=./working_dir
```

---

## Git Status

**Branch**: `cpu-entity-extraction`
**Last commit**: `8b142a9` - Update docs for E2E verification

### Commits on this branch:

| Commit | Description |
|--------|-------------|
| `8b142a9` | Update docs for E2E verification |
| `aa53192` | E2E test verified - all agents working |
| `3aa016d` | Enhance GLiNER with academic labels |
| `4cf1825` | Switch to Qwen3 embedding (4096 dims) |
| `3b7318d` | Fix vague query issue - lower cosine threshold |
| `fe1159b` | Fix metadata extraction and citation map |
| `f5aadb4` | Update docs for GLiNER integration |
| `9ad7778` | Fix GLiNER integration - works now |
| `a78f36b` | Add GLiNER for fast entity extraction |

---

## Models in Use

| Component | Model | Provider | Purpose |
|-----------|-------|----------|---------|
| Embedding | `qwen/qwen3-embedding-8b` | OpenRouter | 4096-dim vectors |
| Entity Extraction | `urchade/gliner_small-v2.1` | Local CPU | 12 academic labels |
| LLM | `deepseek/deepseek-v4-flash` | OpenRouter | Metadata, queries |

---

## Key Configs

### Rate Limiting
- **Delay**: 0.3s between LLM calls
- **Location**: `src/config.py:82-97`

### Cosine Threshold
- **Value**: 0.2 (default)
- **Location**: LightRAG config

### top_k
- **Value**: 150 chunks per query
- **Location**: `src/query_writer.py:21`

### GLiNER Labels (12 total)
```python
["Person", "Organization", "Location", "Event", "Date",
 "Book", "Concept", "Theme", "Technique", "Symbol",
 "ViolenceType", "HistoricalPeriod"]
```

---

## Disk Space

- **Available**: ~3.6GB
- **GLiNER model**: ~500MB
- **Working dir**: ~50MB

---

## To Restore After Shutdown

1. Clone repo: `git clone -b cpu-entity-extraction https://github.com/0zero4u/rag-pipeline.git`
2. Copy `.env` file with API key
3. Install deps: `pip install -r requirements.txt`
4. Install GLiNER: `pip install gliner torch --index-url https://download.pytorch.org/whl/cpu`
5. Re-index PDFs: `python main.py --mode index --pdf-dir ./data/raw`
