# LightRAG Writer Agent - Implementation Plan

## Status: ✅ COMPLETED

**Date**: 2026-05-28
**Agent Working**: Yes - `LightRAGWriterAgent` is registered and operational

---

## Architecture Overview

```
User → LightRAGWriterAgent (OpenCode subagent)
              ↓
         skill("lightrag-pull") → LightRAG pipeline (query_writer.py)
              ↓
         Retrieved chunks with [CHUNK-N] markers
              ↓
         Write academic prose with [CHUNK-N] citations
              ↓
         validate_citations.py (bash) → Verify against citation_map.json
              ↓
         Skill chain: humanizer → academic-writing → formal-writing
              ↓
         Final output (verified, AI-detection safe)
```

---

## Components Implemented

### 1. lightrag-pull Skill
- **Location**: `~/.opencode/skills/lightrag-pull/SKILL.md`
- **Purpose**: Wrapper skill to query LightRAG pipeline
- **Usage**: `skill("lightrag-pull", query="topic search")`

### 2. LightRAGWriterAgent
- **Location**: `~/.config/opencode/agents/lightrag-writer-agent.md`
- **Model**: minimax-m2.7
- **Permissions**: 
  - tool: bash
  - skill: lightrag-pull, humanizer, formal-writing, academic-writing
- **Invocation**: `task(subagent_type="LightRAGWriterAgent", ...)`

### 3. RAG Pipeline Wrapper Scripts
- **query_writer.py**: `/home/arshhtripathi/rag-pipeline/src/query_writer.py`
  - Queries LightRAG and returns structured chunks
  - Usage: `python3 query_writer.py "search query" [top_k]`
  
- **validate_citations.py**: `/home/arshhtripathi/rag-pipeline/src/validate_citations.py`
  - Validates [CHUNK-N] citations against citation_map.json
  - Usage: `python3 validate_citations.py /path/to/prose.md`

### 4. Supporting Files
- **thesis_state.py**: `/home/arshhtripathi/rag-pipeline/src/thesis_state.py`
  - Cross-section state tracking for multi-section writing
  - Tracks claims, contradictions, section progress

- **write_agent.py**: `/home/arshhtripathi/rag-pipeline/src/write_agent.py`
  - Python module for constrained generation (not yet integrated with agent)

---

## Registration Details

### oh-my-openagent.json (agent model config)
```json
"lightrag-writer-agent": {
  "model": "opencode-go/minimax-m2.7"
}
```

### agent-metadata.json (registry entry)
```json
"lightrag-writer-agent": {
  "id": "lightrag-writer-agent",
  "name": "LightRAGWriterAgent",
  "category": "subagents/research",
  "type": "subagent",
  "version": "1.0.0",
  "author": "arshhtripathi",
  "tags": ["writing", "rag", "lightrag", "academic"],
  "dependencies": ["skill:lightrag-pull", "skill:humanizer", "skill:formal-writing", "skill:academic-writing"]
}
```

---

## Citation Format

| Type | Format | Example |
|------|--------|---------|
| Chunk marker | `[CHUNK-N]` | `[CHUNK-1]`, `[CHUNK-2]` |
| MLA inline | `(Author Year, p. #)` | `(Singh 1956, p. 3)` |

**Critical**: Every factual claim MUST cite `[CHUNK-N]`. Unsupported claims → "I don't have sufficient information about [topic]."

---

## Usage Examples

### Via OpenCode CLI
```python
# Write a section
task(subagent_type="LightRAGWriterAgent", 
 prompt="Write section 1.1 on Partition historical background of 1947")

# Write with specific focus
task(subagent_type="LightRAGWriterAgent",
 prompt="Write 500 words on Khushwant Singh's portrayal of communal violence in Train to Pakistan")
```

### Direct RAG Query (via bash)
```bash
cd /home/arshhtripathi/rag-pipeline/src
python3 query_writer.py "Train to Pakistan partition violence" 5
```

### Validate Citations (via bash)
```bash
cd /home/arshhtripathi/rag-pipeline/src
python3 validate_citations.py /tmp/draft.md
```

---

## Skill Chain Workflow

```
Draft Content
    ↓
[1] Load /academic-writing → IMRAD structure, citations check
    ↓
[2] Load /humanizer → Remove 29 AI patterns (preserve [CHUNK-N])
    ↓
[3] Load /formal-writing → Style polish, formal voice
    ↓
Final Verified Output
```

---

## AI Detection Triggers to AVOID

| Category | AVOID | USE INSTEAD |
|----------|-------|-------------|
| Significance | "pivotal", "monumental", "landmark" | Be specific |
| -ing filler | "highlighting", "showcasing", "underscoring" | State directly |
| Copula | "serves as", "stands as", "represents" | "is", "has", "shows" |
| Filler | "In order to", "Due to the fact that" | "To", "Because" |
| Signposting | "Let's explore", "Diving into" | Start with content |

---

## Dissertation Chapter Structure (Target)

```
Chapter 1: Introduction
├── 1.1 Historical Background (Partition 1947)
├── 1.2 Khushwant Singh (bio + literary contributions)
├── 1.3 Train to Pakistan (novel introduction)
├── 1.4 Film Adaptation
├── 1.5 Aim and Objectives
├── 1.6 Research Methodology
└── 1.7 Thesis Statement
```

---

## Next Steps (If Needed)

1. **Test with real dissertation writing** - invoke agent for actual content
2. **Index more PDFs** - ensure RAG has sufficient evidence for target topics
3. **Build orchestration** - for multi-section chapter generation with thesis_state tracking
4. **Verify MLA formatting** - ensure output citation_map.json supports MLA 9th format

---

## File Locations Summary

| Component | Path |
|-----------|------|
| Agent definition | `~/.config/opencode/agents/lightrag-writer-agent.md` |
| lightrag-pull skill | `~/.opencode/skills/lightrag-pull/SKILL.md` |
| RAG pipeline | `/home/arshhtripathi/rag-pipeline/` |
| query_writer.py | `/home/arshhtripathi/rag-pipeline/src/query_writer.py` |
| validate_citations.py | `/home/arshhtripathi/rag-pipeline/src/validate_citations.py` |
| citation_map.json | `/home/arshhtripathi/rag-pipeline/data/processed/citation_map.json` |
| Working index | `/home/arshhtripathi/rag-pipeline/working_dir/` |
| Agent metadata | `~/.opencode/config/agent-metadata.json` |
| Model config | `~/.config/opencode/oh-my-openagent.json` |

---

## Verification

**Agent loads successfully:**
```
Available agents: ..., LightRAGWriterAgent, ...
```

**Agent responds to task:**
```
task(subagent_type="LightRAGWriterAgent", prompt="...")
→ Agent generates content with RAG-constrained claims
```

---

## Notes

- Agent uses LightRAG (not FAISS) - different from existing `AcademicWriterAgent`
- Citation validation ensures no hallucinated citations
- Skill chain ensures AI-detection safe output
- Multi-section coherence requires thesis_state tracking (module ready)

---

**Last Updated**: 2026-05-28