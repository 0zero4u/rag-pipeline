# Ripple Dependencies — Change Tracking

**Purpose**: Track all changes that ripple across multiple files. When modifying one component, check this doc to update all dependent files.

**Last Updated**: 2026-05-28

---

## Change: Resume Functionality (Parser)

**Date**: 2026-05-28  
**Reason**: Indexing 32 PDFs takes ~15 min; interrupting lost all progress

### Behavior

| Scenario | Before | After |
|----------|--------|-------|
| First run | Parse all, save all | Parse all, save all |
| Interrupt at PDF #15 | 0 saved (all lost) | 15 saved individually |
| Resume after interrupt | Re-parse all 32 | Skip 15 cached, parse remaining 17 |
| Corrupted cache file | Crash | Re-parse that PDF |

### How It Works

1. **Individual JSON files** saved per PDF in `data/processed/{stem}.json`
2. **Before parsing**, check if JSON exists → load from cache if valid
3. **After all PDFs**, save combined `all_parsed.json`
4. **On resume**, cached PDFs are skipped, only new ones parsed

### Cache Locations

| Location | Contents | Survives Interrupt? |
|----------|----------|---------------------|
| `data/processed/*.json` | Individual parsed PDFs | ✅ YES (saved per PDF) |
| `data/processed/all_parsed.json` | Combined parse output | ❌ NO (saved at end) |
| `src/working_dir/` | LightRAG index | ❌ NO (built incrementally) |

### Files Changed

| # | File | Change |
|---|------|--------|
| 1 | `src/parser.py` | `parse_pdfs()` now checks for cached JSON before parsing |

### Manual Cache Clear

```bash
# Clear all cache (full re-index required)
rm -rf data/processed/*.json src/working_dir/*

# Clear only LightRAG index (keep parsed PDFs)
rm -rf src/working_dir/*

# Clear only parsed cache (re-parse PDFs, keep index)
rm -rf data/processed/*.json
```

### Verify Cache State

```bash
# Count parsed PDFs
ls data/processed/*.json | wc -l

# Should show 32 when complete
```

---

## How to Use

1. Before making a change, search this doc for related dependencies
2. After making a change, update this doc with new dependencies
3. When onboarding new developers, review this doc first

---

## Change: top_k (5 → 150)

**Date**: 2026-05-28  
**Reason**: Chapter writing needs broader evidence (150 chunks per query)

### Files Changed

| # | File | Line(s) | Change |
|---|------|---------|--------|
| 1 | `src/query_writer.py` | 21 | `top_k: int = 5` → `top_k: int = 150` |
| 2 | `src/query_writer.py` | 94 | `else 5` → `else 150` |
| 3 | `~/.config/opencode/agents/lightrag-writer-agent.md` | 33 | `python3 query_writer.py "..." 5` → `... 150` |
| 4 | `~/.config/opencode/agents/lightrag-writer-agent.md` | 48 | Example: "5 chunks" → "150 chunks" |
| 5 | `~/.config/opencode/agents/lightrag-writer-agent.md` | 70 | Doc text updated |
| 6 | `~/.config/opencode/agents/lightrag-writer-agent.md` | 126 | Workflow step: `5` → `150` |
| 7 | `~/.config/opencode/agents/lightrag-writer-agent.md` | 151 | Example: `5` → `150` |
| 8 | `tests/integration/test_query_writer.py` | 93 | `top_k=5` → `top_k=150` |
| 9 | `tests/integration/test_query_writer.py` | 159 | `top_k=5` → `top_k=150` |

### Dependent Components

| Component | Depends On | Impact |
|-----------|------------|--------|
| `validate_citations.py` | `--max-chunks N` | Must pass actual chunk count, not top_k |
| `citation-adder-agent.md` | chunk_index order | No change needed (reads citation_map.json) |
| `humanize-agent.md` | [CHUNK-N] preservation | No change needed (preserves markers) |

### Verification

- [x] All 41 tests pass
- [x] Agent prompts updated
- [x] Examples updated

---

## Change: HumanizeAgent Enhanced Rules

**Date**: 2026-05-28  
**Reason**: Improve academic writing quality while preserving pipeline rules

### Files Changed

| # | File | Change |
|---|------|--------|
| 1 | `~/.config/opencode/agents/humanize-agent.md` | Added academic writing standards section |
| 2 | `~/.config/opencode/agents/humanize-agent.md` | Added hard prohibitions |
| 3 | `~/.config/opencode/agents/humanize-agent.md` | Added quality checklist |

### Pipeline-Critical Rules (UNCHANGED)

| Rule | Status |
|------|--------|
| Preserve [CHUNK-N] markers | ✅ UNCHANGED |
| No renumbering | ✅ UNCHANGED |
| No spaces in markers | ✅ UNCHANGED |
| Output to `/tmp/humanized_draft.md` | ✅ UNCHANGED |
| No RAG queries | ✅ UNCHANGED |

### Verification

- [x] HumanizeAgent reviewed updated prompt
- [x] No conflicts with pipeline rules
- [x] Workflow intact

---

## Change: Chapter Plan Added

**Date**: 2026-05-28  
**Reason**: Dissertation structure for Train to Pakistan study

### Files Changed

| # | File | Change |
|---|------|--------|
| 1 | `chapter_plan.md` | New file: 6 chapters with section outlines |

### Dependent Components

| Component | Depends On | Impact |
|-----------|------------|--------|
| LightRAGWriterAgent | chapter_plan.md | Queries based on section topics |
| Section queries | top_k=150 | Each section needs 150 chunks |

---

## Future Changes — Check These First

Before modifying any of these, check RIPPLE_DEPENDENCIES.md:

| Component | File | Dependent Files |
|-----------|------|-----------------|
| **top_k** | `src/query_writer.py` | Agent prompts, tests, docs |
| **Chunk format** | `src/query_writer.py` | All agents, validation |
| **Citation format** | `src/validate_citations.py` | Agent prompts, check_citations |
| **Output paths** | Agent prompts | All pipeline scripts |
| **Working dir** | `src/config.py` | Agent env vars, scripts |

---

## Dependency Map

```
src/query_writer.py (top_k=150)
    ├── lightrag-writer-agent.md (bash commands)
    ├── tests/integration/test_query_writer.py (test calls)
    └── validate_citations.py (--max-chunks must match actual)

src/validate_citations.py
    ├── citation_map.json (source of truth)
    ├── kv_store_doc_status.json (ref_id mapping)
    └── lightrag-writer-agent.md (validation step)

~/.config/opencode/agents/lightrag-writer-agent.md
    ├── src/query_writer.py (bash call)
    ├── src/validate_citations.py (validation)
    └── chapter_plan.md (section topics)

~/.config/opencode/agents/humanize-agent.md
    ├── Receives from: lightrag-writer-agent.md
    ├── Sends to: citation-adder-agent.md
    └── Pipeline rules: [CHUNK-N] preservation

~/.config/opencode/agents/citation-adder-agent.md
    ├── Reads: citation_map.json
    ├── Receives from: humanize-agent.md
    └── Outputs: MLA format
```

---

## Quick Reference

### When changing top_k:
1. Update `src/query_writer.py` (default parameter + CLI fallback)
2. Update `lightrag-writer-agent.md` (all bash commands + examples)
3. Update tests in `tests/integration/test_query_writer.py`
4. Update this doc

### When changing citation format:
1. Update `src/validate_citations.py`
2. Update `lightrag-writer-agent.md` (citation rules)
3. Update `citation-adder-agent.md` (conversion rules)
4. Update tests
5. Update this doc

### When changing output paths:
1. Update all agent prompts (env vars + workflow steps)
2. Update scripts that read/write those paths
3. Update this doc
