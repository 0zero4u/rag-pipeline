# RAG Pipeline for Academic Research PDFs

End-to-end pipeline to process academic papers, build a knowledge graph, and query with proper citations.

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
python src/main.py \
    --pdf-dir /path/to/your/pdfs \
    --output-dir ./data/processed \
    --working-dir ./working_dir
```

## API Keys

Only **OpenRouter** is needed (single key for everything):
- Get key: https://openrouter.ai/keys
- Models used:
  - `qwen/qwen3-embedding-8b` (embeddings)
  - `google/gemini-2.0-flash` (LLM)
  - `cohere/rerank-4-fast` (reranking)

## Usage

### Full Pipeline (parse + index + interactive query)

```bash
python src/main.py \
    --pdf-dir /home/arshhtripathi/research_work \
    --output-dir ./data/processed \
    --working-dir ./working_dir \
    --interactive
```

### Parse Only

```bash
python src/main.py --mode parse \
    --pdf-dir /path/to/pdfs \
    --output-dir ./data/processed
```

### Interactive Query

```bash
python src/main.py --mode query \
    --output-dir ./data/processed \
    --working-dir ./working_dir \
    --interactive
```

## Project Structure

```
rag-pipeline/
├── src/
│   ├── __init__.py
│   ├── parser.py         # Docling + PDFx parsing
│   ├── citation_map.py   # Build citation map
│   ├── config.py        # LightRAG + OpenRouter config
│   └── main.py          # Main pipeline
├── data/
│   ├── raw/             # Put PDFs here
│   └── processed/       # Parsed output goes here
├── working_dir/          # LightRAG index
├── requirements.txt
└── .env.example
```

## Features

- **Docling**: Multi-column text extraction, tables, formulas
- **PDFx**: Authors, references, DOIs extraction
- **LightRAG**: Knowledge graph + vector search
- **Citation Map**: Enriches answers with full citations
- **Reranking**: Improved retrieval quality
