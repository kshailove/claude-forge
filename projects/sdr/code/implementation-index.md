# SDR Presentation Utility — Implementation Index

This document lists every file in the project with a one-line description.

---

## Source Files (`src/`)

| File | Description |
|---|---|
| `src/__init__.py` | Empty package marker — makes `src/` a Python package. |
| `src/knowledge_store.py` | ChromaDB wrapper with MD5 hash-based incremental ingestion and cosine similarity search. |
| `src/tools.py` | CrewAI BaseTool implementations: `WebsiteThemeScraper` (brand extraction) and `KnowledgeSearchTool` (RAG search). |
| `src/agents.py` | Factory functions for all 4 CrewAI agents: Researcher, Brand Analyst, Value Prop Strategist, Presentation Designer. |
| `src/tasks.py` | Factory functions for all 4 CrewAI tasks, including Phase 2 inline research injection and strict retry flag. |
| `src/crew.py` | Two-phase crew orchestration: Phase 1 (research + brand), token truncation, Phase 2 (value props + HTML). |
| `src/main.py` | CLI entry point — argument parsing, env validation, knowledge ingestion, prospect batch loop, error isolation. |

## Configuration Files

| File | Description |
|---|---|
| `requirements.txt` | Python package dependencies pinned by major version. |
| `.env.example` | Template for environment variables — copy to `.env` and fill in API keys. |
| `.gitignore` | Git ignore rules excluding `.env`, `chroma_db/`, `output/`, and Python build artefacts. |
| `docker-compose.yml` | Self-hosted LangFuse observability stack (LangFuse server + PostgreSQL). |

## Documentation

| File | Description |
|---|---|
| `README.md` | Full project documentation: quick start, installation, knowledge base format, CLI usage, cost estimates, troubleshooting. |
| `implementation-index.md` | This file — inventory of all project files with one-line descriptions. |

## Input / Data Files

| File | Description |
|---|---|
| `input/prospects.txt` | Example prospect list with 3 domains (stripe.com, notion.so, freshdesk.com). |
| `knowledge/hiver/products.md` | Placeholder knowledge base file — replace with real product documentation before running. |

## Runtime-Generated Directories (not committed)

| Directory | Description |
|---|---|
| `chroma_db/` | ChromaDB persistent storage — created on first run, excluded by `.gitignore`. |
| `output/` | Generated HTML presentations and errors.log — created on first run, excluded by `.gitignore`. |
| `.venv/` | Python virtual environment — excluded by `.gitignore`. |
