# Model Card — RAG Pipeline

**Last Updated**: 2026-05-28

---

## Models Used

| Component | Model | Provider | Purpose | File |
|-----------|-------|----------|---------|------|
| **Embedding** | `perplexity/pplx-embed-v1-0.6b` | OpenRouter | Vector embeddings (1024-dim) | `config.py:111` |
| **Entity Extraction** | `urchade/gliner_small-v2.1` | Local (CPU) | Fast entity extraction | `gliner_extractor.py` |
| **LLM** | `deepseek/deepseek-v4-flash` | OpenRouter | Metadata, query answering | `config.py:112`, `main.py:29` |

---

## Model Details

### Embedding: perplexity/pplx-embed-v1-0.6b

| Property | Value |
|----------|-------|
| Dimension | 1024 |
| Max tokens | 8192 |
| Use case | Document chunk embedding |
| Speed | Fast |
| Cost | Low |

**Where used**: `config.py` → `create_embedding_func()`

---

### Entity Extraction: GLiNER (Local CPU)

| Property | Value |
|----------|-------|
| Model | `urchade/gliner_small-v2.1` |
| Size | ~500MB |
| Speed | ~0.2s/chunk |
| Cost | Free (local) |
| Labels | Person, Organization, Location, Event, Date, Book, Concept |

**Where used**: `gliner_extractor.py` → `extract_entities_gliner()`

**Performance comparison:**

| Method | Speed | Cost | Quality |
|--------|-------|------|---------|
| **GLiNER** | ~0.2s/chunk | Free | Good |
| **LLM** | ~8s/chunk | $0.01-0.15/M tokens | Excellent |

---

### LLM: deepseek/deepseek-v4-flash

| Property | Value |
|----------|-------|
| Context window | 128K tokens |
| Use case | Metadata extraction, query answering |
| Speed | Fast |
| Cost | Low |

**Where used**:
- `config.py:135` → `create_llm_func()` — creates LLM function
- `main.py:29` → `run_pipeline()` — default parameter
- `main.py:226` → CLI argument `--llm-model`

---

## Model Selection Logic

```
CLI argument (--llm-model)
    ↓ (overrides)
run_pipeline() default
    ↓ (overrides)
initialize_lightrag() default
    ↓
create_llm_func(model)
    ↓
OpenRouter API
```

**Priority**: CLI > run_pipeline() > initialize_lightrag()

---

## Rate Limits

### OpenRouter (Our Provider)

**Your Account**: $4 balance, $6.71 total spent → **Paid tier**

| Tier | Requests/Day | Requests/Min |
|------|--------------|--------------|
| Free (no payments) | 50 | 20 |
| **Paid ($10+ purchased)** | **1000** | **20** |
| Paid models | No OpenRouter limit | Upstream may throttle |

**Source**: [OpenRouter Rate Limits](https://openrouter.zendesk.com/hc/en-us/articles/39501163636379)

### DeepSeek Upstream (Our Model Provider)

| Model | Concurrency | Source |
|-------|-------------|--------|
| `deepseek-v4-flash` | 2500 concurrent | [DeepSeek Docs](https://api-docs.deepseek.com/quick_start/rate_limit) |

**Important**: 429 errors are likely **upstream DeepSeek throttling**, not OpenRouter limits.

### If Rate Limited (429 Error)

1. Check `X-RateLimit-Remaining` header
2. Wait for `X-RateLimit-Reset` timestamp
3. Reduce concurrent workers in `config.py`
4. Add delay between requests (currently 0.5s)
5. Consider switching to `deepseek-v4-pro` (500 concurrent vs 2500)

---

## Adding New Models

1. Find model on [OpenRouter Models](https://openrouter.ai/models)
2. Update default in `config.py` and `main.py`
3. Update this model card
4. Test with 2 PDFs before full index

---

## Previous Models (Not Recommended)

| Model | Status | Reason |
|-------|--------|--------|
| `google/gemini-3.5-flash` | ❌ Deprecated | Rate limits too strict |
