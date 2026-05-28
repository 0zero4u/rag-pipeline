# Model Card — RAG Pipeline

**Last Updated**: 2026-05-28

---

## Models Used

| Component | Model | Provider | Purpose | File |
|-----------|-------|----------|---------|------|
| **Embedding** | `perplexity/pplx-embed-v1-0.6b` | OpenRouter | Vector embeddings (1024-dim) | `config.py:111` |
| **LLM (Primary)** | `deepseek/deepseek-v4-flash` | OpenRouter | Entity extraction, metadata | `config.py:112`, `main.py:29`, `main.py:226` |
| **LLM (Query)** | `deepseek/deepseek-v4-flash` | OpenRouter | Query answering, citations | `config.py:112` |

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

### LLM: deepseek/deepseek-v4-flash

| Property | Value |
|----------|-------|
| Context window | 128K tokens |
| Use case | Entity extraction, metadata extraction, query answering |
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

| Model | Limit | Notes |
|-------|-------|-------|
| `deepseek/deepseek-v4-flash` | Concurrent requests | Check X-RateLimit headers |
| `google/gemini-3.5-flash` | Concurrent requests | Rate limited (avoid) |

**If rate limited (429 error)**:
1. Wait for reset (check `X-RateLimit-Reset` header)
2. Reduce concurrent workers in `config.py`
3. Add delay between requests (currently 0.5s)

### DeepSeek Direct API (Reference)

| Model | Concurrency | Source |
|-------|-------------|--------|
| `deepseek-v4-pro` | 500 concurrent | [DeepSeek Docs](https://api-docs.deepseek.com/quick_start/rate_limit) |
| `deepseek-v4-flash` | 2500 concurrent | [DeepSeek Docs](https://api-docs.deepseek.com/quick_start/rate_limit) |

**Note**: We use OpenRouter, not DeepSeek directly. OpenRouter aggregates multiple providers.

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
