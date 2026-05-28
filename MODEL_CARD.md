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

| Model | Provider | Limit | Reset |
|-------|----------|-------|-------|
| `deepseek/deepseek-v4-flash` | OpenRouter | Varies | Check headers |
| `google/gemini-3.5-flash` | OpenRouter | Varies | Check headers |

**If rate limited**:
1. Wait for reset (check `X-RateLimit-Reset` header)
2. Switch model via `--llm-model` flag
3. Reduce concurrent requests in `config.py`

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
