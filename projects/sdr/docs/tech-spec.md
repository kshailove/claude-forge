# Technical Specification — SDR Presentation Utility

**Version:** 1.0  
**Date:** 2026-06-18  
**Stage:** 4 — Tech Spec  
**Author:** Tech Spec Agent (ClaudeForge)  
**Status:** Draft

---

## 1. Architecture Overview

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CLI: python src/main.py --company <company_name>                           │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │        main.py             │
                    │  - arg parse & validation  │
                    │  - .env load               │
                    │  - ingestion check         │
                    │  - prospect loop           │
                    └──────┬─────────────┬───────┘
                           │             │
           ┌───────────────▼──┐    ┌─────▼──────────────────┐
           │  knowledge_store │    │       crew.py           │
           │  - MD5 check     │    │  - build_crew()         │
           │  - chunking      │    │  - run_for_prospect()   │
           │  - embed         │    └──────┬──────────────────┘
           │  - upsert        │           │
           └───────┬──────────┘    ┌──────▼──────────────────────────────────┐
                   │               │   CrewAI Sequential Crew (fresh/prospect) │
                   │               │                                           │
                   │               │  Agent 1 (Researcher)                    │
                   │               │    └─► TavilySearchResults(k=3)          │
                   │               │          │                                │
                   │               │  Agent 2 (Brand Analyst)  [parallel slot]│
                   │               │    └─► WebsiteThemeScraper               │
                   │               │          │                                │
                   │               │  Agent 3 (Value Prop Strategist)         │
                   │               │    └─► KnowledgeSearchTool               │
                   │               │    context=[research_task]               │
                   │               │          │                                │
                   │               │  Agent 4 (Presentation Designer)         │
                   │               │    context=[research_task, brand_task,   │
                   │               │             value_prop_task]             │
                   │               └──────┬──────────────────────────────────┘
                   │                      │
                   │               ┌──────▼──────────┐
                   │               │  HTML Validator  │  (BeautifulSoup post-gen)
                   │               │  count <section> │
                   │               └──────┬──────────┘
                   │                      │
       ┌───────────▼──┐           ┌───────▼──────────────────┐
       │  ChromaDB     │          │  output/<company>/        │
       │  (embedded,   │          │  presentation_<p>.html    │
       │   persistent) │          │  errors.log               │
       └───────────────┘          └───────────────────────────┘

External Services:
  [OpenAI API]   ◄─── ChatOpenAI (gpt-4o-mini default) + OpenAIEmbeddings
  [Tavily API]   ◄─── TavilySearchResults (Agent 1 only)
  [Prospect site] ◄── requests.get() (Agent 2, read-only scrape)
  [fonts.googleapis.com] ◄── <link> tag injected by Agent 4 (runtime, not build-time)
```

### Key Components

| Component | File | Responsibility |
|---|---|---|
| Entry point | `src/main.py` | CLI arg parsing, .env loading, ingestion gate, batch loop, error isolation, output writing |
| Knowledge store | `src/knowledge_store.py` | MD5-based incremental ingestion, ChromaDB operations, similarity search |
| Agent definitions | `src/agents.py` | 4 CrewAI `Agent` instances constructed from env config |
| Task definitions | `src/tasks.py` | 4 `Task` instances with `context=` chaining and truncation guard |
| Custom tools | `src/tools.py` | `WebsiteThemeScraper` + `KnowledgeSearchTool` |
| Crew assembly | `src/crew.py` | `build_crew(prospect_domain, company_name, knowledge_store)` factory |

### Data Flow (per prospect)

```
input/prospects.txt
      │
      ▼  derive prospect_name
main.py loop
      │
      ├──► knowledge_store.search(research_summary)  ← called by KnowledgeSearchTool
      │           │
      │           ▼
      │      ChromaDB cosine query → top-5 chunks
      │
      └──► crew.py build_crew() → Crew.kickoff()
                │
                ├── Agent 1: Tavily API → research_summary (≤1,500 tokens)
                ├── Agent 2: requests.get(domain) → theme_dict
                ├── Agent 3: KnowledgeSearchTool(research_summary) → value_props
                └── Agent 4: HTML string (10 slides)
                              │
                              ▼
                     HTML validation (BeautifulSoup)
                              │
                      ┌───────┴────────┐
                  valid (=10)     invalid (!= 10)
                      │               │
                      │          retry once
                      │               │
                      ▼               ▼
              write .html      write .html + append errors.log
```

---

## 2. Tech Stack Decisions

### Language

**Choice:** Python 3.11  
**Alternatives considered:** Python 3.12 (slightly faster), Python 3.10  
**Rationale:** CrewAI 1.14.7 specifies `>=3.10, <3.14`. Python 3.11 is the widest-compatibility stable release as of June 2026 across the dependency tree (chromadb, langchain_openai, tiktoken). Pin `python_requires = ">=3.11,<3.14"` in any packaging manifest.

---

### Agent Framework

**Choice:** CrewAI 1.14.7  
**Alternatives considered:** LangGraph 0.2.x (rejected — overkill for fixed linear flow; no branching needed), AutoGen (rejected — maintenance mode Feb 2026)  
**Rationale:** Sequential `Process` with `context=` task chaining is idiomatic; custom `BaseTool` integration is clean; v1.x API is stable. Fresh `Crew` per prospect (see Q2 resolution, Section 5).

---

### LLM

**Choice:** OpenAI `gpt-4o-mini` (default), configurable via `OPENAI_MODEL` env var  
**Alternatives considered:** `gpt-4o` (higher quality, ~6x more expensive), `gpt-4` legacy (deprecated path)  
**Rationale:** `gpt-4o-mini` ($0.15/1M input, $0.60/1M output as of June 2026) keeps per-prospect cost well under $0.05. All 4 agents use the same model via `os.environ.get("OPENAI_MODEL", "gpt-4o-mini")`. `ChatOpenAI` from `langchain_openai 0.3.x`.

---

### Embeddings

**Choice:** OpenAI `text-embedding-3-small` (1,536 dimensions, default)  
**Alternatives considered:** `text-embedding-3-large` (overkill), local models (adds infrastructure)  
**Rationale:** Semantic search quality sufficient for RAG over markdown files; $0.02/1M tokens is negligible for this volume; no model switch needed.

---

### Vector Database

**Choice:** ChromaDB 1.5.9 (embedded persistent mode, `PersistentClient`)  
**Alternatives considered:** Qdrant local, Faiss (no metadata filtering), pgvector (requires PostgreSQL)  
**Rationale:** Zero infrastructure, disk-persistent, cosine similarity default, per-company collection isolation, MD5 metadata filtering supported natively. Pin exactly: `chromadb==1.5.9`.

---

### Search

**Choice:** Tavily Search API via `langchain_community.tools.tavily_search.TavilySearchResults`, `k=3`  
**Alternatives considered:** SerpAPI (paid, no free tier), DuckDuckGo (no official API), Bing (additional key)  
**Rationale:** Designed for LLM agents; structured results; generous free tier (1,000 credits/month); `TAVILY_API_KEY` is the only auth requirement.

---

### Web Scraping

**Choice:** `requests 2.32.x` + `beautifulsoup4 4.12.x` + `lxml` parser  
**Alternatives considered:** Playwright (headless, defeats v1 scope constraint), httpx (async, not needed)  
**Rationale:** Static HTML `<head>` parsing is sufficient for CSS `<link>` tags and `<meta>` theme-color. `lxml` is 3–5x faster than `html.parser`. Fall back to `html.parser` if `lxml` is unavailable.

---

### Token Counting

**Choice:** `tiktoken 0.7.x`  
**Rationale:** OpenAI's own tokeniser; used to enforce 1,500-token cap on Agent 1 output (Q1 resolution). Encoding: `cl100k_base` (matches GPT-4o-mini tokeniser).

---

### Environment Config

**Choice:** `python-dotenv 1.0.x` (loads `.env` at startup)  
**Rationale:** Simple, zero-dependency env file loading. No secrets in source.

---

### Observability

**Choice:** LangFuse (self-hosted via Docker)  
**Alternatives considered:** LangSmith (cloud-only, vendor lock-in), Helicone (no self-hosted), no observability (acceptable for v1 but loses cost/quality visibility)  
**Rationale:** LangFuse is open-source, self-hostable, and has a native LangChain `CallbackHandler` — zero CrewAI-specific patching needed. Covers all 4 observability goals: cost per prospect, per-agent latency, full prompt/response logging, and error rate tracking. **Optional:** if `LANGFUSE_PUBLIC_KEY` is absent from `.env`, tracing is silently disabled with no impact on the core pipeline.

---

### CI/CD and Hosting

**Choice:** None (v1 is a local CLI tool; no server, no container, no CI pipeline required)  
**Rationale:** Out of v1 scope. A `Makefile` with `make test` is the only automation target. A `docker-compose.yml` for LangFuse self-hosting is included separately.

---

## 3. Data Models

### ChromaDB Collection Schema

There is one ChromaDB collection per selling company. Collections are not relational; the schema below describes the document metadata fields stored with each embedding.

```
Collection: <company_name>_knowledge
  (e.g. "hiver_knowledge" for --company hiver)

Document fields (per chunk):
  - id:           str  — "{source_filename}::{chunk_index}"
                         e.g. "products.md::3"
                         Deterministic: same file + index = same id (enables upsert)
  - document:     str  — The raw text of the chunk (≤500 tokens, 50-token overlap with adjacent)
  - embedding:    list[float]  — 1,536-dim vector from text-embedding-3-small
                                 (stored by ChromaDB; not explicitly set by caller)

Metadata fields (per chunk):
  - source_file:  str  — Filename only, no path (e.g. "products.md")
  - file_hash:    str  — MD5 hex digest of the full source file at ingestion time
                         (e.g. "d41d8cd98f00b204e9800998ecf8427e")
  - chunk_index:  int  — 0-based index of this chunk within the source file
  - company_name: str  — Selling company name (e.g. "hiver")

Indexes:
  - ChromaDB maintains an HNSW index over embeddings by default; no additional index required.
  - Metadata filtering by source_file is used during re-ingestion (delete old chunks before upserting new ones).
```

### Prospect Name Derivation (in-memory, not persisted)

The domain-to-name mapping is computed in `main.py` and passed as a string to `crew.py`. It is not stored. See Section 5 (`main.py`, `derive_prospect_name`) for the algorithm.

### Output Files (filesystem, not a database)

```
output/<company_name>/
  presentation_<prospect_name_lower>.html
    — Self-contained HTML file; no schema beyond what Agent 4 generates.
    — File is overwritten on each run (idempotent).

  errors.log
    — Plain text, one line per error event, UTF-8 encoded.
    — Appended (not overwritten) across runs.
    — Line format defined in Section 7 (Q7 resolution).
```

### Environment Variables (`.env`)

```
OPENAI_API_KEY   required  str  — OpenAI secret key; loaded by python-dotenv
TAVILY_API_KEY   required  str  — Tavily secret key; loaded by python-dotenv
OPENAI_MODEL     optional  str  — Default: "gpt-4o-mini"
                                  Override: any valid OpenAI chat model id
```

---

## 4. API Contracts

This is a CLI-only tool with no REST API. This section documents internal module interfaces (function signatures) and the external API contracts consumed.

### 4.1 Internal Module Interfaces

#### `knowledge_store.py` — `KnowledgeStore`

```python
class KnowledgeStore:
    def __init__(self, company_name: str, persist_dir: str = "chroma_db") -> None:
        """
        Initialises (or opens) the ChromaDB PersistentClient at
        persist_dir/<company_name>/ and gets/creates collection
        "<company_name>_knowledge".
        """

    def run_ingestion_check(self, knowledge_dir: str) -> IngestResult:
        """
        Scans *.md files in knowledge_dir.
        For each file:
          - Computes MD5 hash.
          - Queries collection metadata for existing file_hash.
          - If hash differs or file is new: deletes all chunks for that
            source_file, re-chunks, embeds, upserts.
          - If hash matches: skips.
        Returns IngestResult with fields:
          ingested_files: list[str]    — filenames that were re-ingested
          skipped_files:  list[str]    — filenames that were skipped
          total_new_chunks: int        — total chunks upserted this run
        Prints progress to stdout as side effect.
        """

    def similarity_search(self, query: str, n_results: int = 5) -> list[str]:
        """
        Embeds query with text-embedding-3-small.
        Queries the collection for the n_results most similar chunks (cosine).
        Returns list of document strings (not metadata).
        """
```

```python
@dataclass
class IngestResult:
    ingested_files: list[str]
    skipped_files: list[str]
    total_new_chunks: int
```

#### `tools.py` — `WebsiteThemeScraper`

```python
class WebsiteThemeScraper(BaseTool):
    name: str = "WebsiteThemeScraper"
    description: str = (
        "Fetches a website's homepage and extracts brand colours and font "
        "families from CSS stylesheets and meta tags. Input: domain string "
        "(e.g. 'stripe.com'). Output: JSON string with keys primary_color, "
        "secondary_color, background_color, font_family, accent_color."
    )

    def _run(self, domain: str) -> str:
        """
        Returns JSON-encoded ThemeDict.
        Never raises — returns NEUTRAL_FALLBACK_THEME on any error.
        """
```

```python
ThemeDict = TypedDict("ThemeDict", {
    "primary_color":    str,   # hex, e.g. "#1a1a2e"
    "secondary_color":  str,
    "background_color": str,
    "font_family":      str,   # CSS font-family value or Google Fonts name
    "accent_color":     str,
})
```

#### `tools.py` — `KnowledgeSearchTool`

```python
class KnowledgeSearchTool(BaseTool):
    name: str = "KnowledgeSearchTool"
    description: str = (
        "Searches the selling company's knowledge base for content relevant "
        "to a prospect's pain points. Input: research summary string. "
        "Output: formatted string of top-5 knowledge chunks."
    )
    knowledge_store: KnowledgeStore   # injected at construction

    def _run(self, research_summary: str) -> str:
        """
        Calls knowledge_store.similarity_search(research_summary, n_results=5).
        Returns chunks joined by "\n\n---\n\n".
        """
```

#### `crew.py`

```python
def build_crew(
    prospect_domain: str,
    prospect_name: str,
    company_name: str,
    knowledge_store: KnowledgeStore,
) -> Crew:
    """
    Constructs and returns a fresh Crew instance for a single prospect.
    Agents, tasks, and tools are all instantiated inside this function.
    Process: Process.sequential
    """

def run_for_prospect(
    prospect_domain: str,
    prospect_name: str,
    company_name: str,
    knowledge_store: KnowledgeStore,
) -> str:
    """
    Calls build_crew(), then crew.kickoff().
    Extracts HTML output from the final task's output.
    Returns raw HTML string.
    Raises on unrecoverable crew errors (caught by main.py).
    """
```

#### `main.py`

```python
def derive_prospect_name(domain: str) -> str:
    """
    See Section 5 (Q6 algorithm). Returns title-cased prospect name.
    """

def validate_html_sections(html: str, container_selector: str = "div.slides") -> int:
    """
    Parses html with BeautifulSoup.
    Finds the container matching container_selector (see Q3 resolution).
    Returns count of direct <section> children of that container.
    Returns -1 if container not found.
    """

def append_error_log(errors_log_path: str, line: str) -> None:
    """
    Opens errors_log_path in append mode, writes line + newline.
    Creates file if it does not exist (os.makedirs is called by caller).
    """
```

### 4.2 External API Contracts Consumed

#### OpenAI Chat Completions (via `langchain_openai.ChatOpenAI`)

```
POST https://api.openai.com/v1/chat/completions
Auth: Bearer $OPENAI_API_KEY
Model: os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
Max retries: 2 (langchain_openai default)
Timeout: 60s per request (langchain_openai default)

Request shape (handled by LangChain internally):
  {
    "model": "gpt-4o-mini",
    "messages": [...],
    "temperature": 0.7   // CrewAI default
  }

Response 200:
  { "choices": [{ "message": { "content": "<agent output>" } }] }

Error handling:
  - RateLimitError (429): LangChain retries with exponential backoff (built-in)
  - AuthenticationError (401): Propagates to per-prospect try/except in main.py
  - APIConnectionError: Propagates to per-prospect try/except in main.py
```

#### OpenAI Embeddings (via `langchain_openai.OpenAIEmbeddings`)

```
POST https://api.openai.com/v1/embeddings
Auth: Bearer $OPENAI_API_KEY
Model: text-embedding-3-small
Dimensions: 1536 (default)

Called by:
  - KnowledgeStore.run_ingestion_check() — at startup, for changed files only
  - KnowledgeSearchTool._run() — once per prospect (Agent 3's tool call)

Error handling: Propagates to caller (ingestion or per-prospect try/except).
```

#### Tavily Search (via `langchain_community.tools.TavilySearchResults`)

```
POST https://api.tavily.com/search
Auth: X-Api-Key: $TAVILY_API_KEY
k: 3 results per call
include_raw_content: False (basic search, 1 credit/request)

Called by: Agent 1 only, 2–3 times per prospect.

Error handling:
  - Empty result list: Agent 1 prompt instructs graceful degradation.
  - HTTP error / connection error: Propagates to per-prospect try/except in main.py.
```

#### Prospect Homepage Scrape (via `requests.get`)

```
GET https://<prospect_domain>/
Headers: (browser-like set; see Section 5 WebsiteThemeScraper)
Timeout: 10 seconds
Max redirects: 2 (requests default is 30; override: allow_redirects=True, max_redirects=2)

Error handling: Any exception → return NEUTRAL_FALLBACK_THEME. Never propagates.
```

---

## 5. Component Breakdown

### `main.py` — Entry Point

**Purpose:** Orchestrates the full pipeline for a given company: validate inputs, run ingestion, loop over prospects, write output.

**Inputs:**
- CLI argument `--company <company_name>` (required)
- `input/prospects.txt` (one domain per line)
- `.env` file

**Outputs:**
- `output/<company_name>/presentation_<prospect>.html` (one per prospect)
- `output/<company_name>/errors.log` (appended on errors)
- stdout progress lines

**Key logic:**

```
1. argparse: --company required; --dry-run optional (nice-to-have F13)
2. Validate knowledge/<company_name>/ exists and contains ≥1 *.md file.
   → If not: print error to stderr, sys.exit(1)
3. load_dotenv(); validate OPENAI_API_KEY and TAVILY_API_KEY present.
   → If either missing: print error to stderr, sys.exit(1)
4. KnowledgeStore(company_name).run_ingestion_check("knowledge/<company_name>/")
5. Read input/prospects.txt → list of domain strings (strip whitespace, skip blank lines)
6. os.makedirs("output/<company_name>", exist_ok=True)
7. For each domain in prospects:
   a. prospect_name = derive_prospect_name(domain)
   b. try:
        html = run_for_prospect(domain, prospect_name, company_name, store)
        html = validate_and_maybe_retry(html, domain, prospect_name, company_name, store)
        write html to output/<company_name>/presentation_<prospect_name.lower()>.html
        success_count += 1
        print(f"✓ Done: {prospect_name}")
      except Exception as e:
        append_error_log(errors_log_path, format_error_line(domain, e))
        fail_count += 1
        print(f"✗ Failed: {prospect_name} — see errors.log")
8. Print summary line.
```

**`derive_prospect_name(domain)` algorithm (Q6 resolution):**

```python
def derive_prospect_name(domain: str) -> str:
    """
    Algorithm:
    1. Lowercase and strip whitespace.
    2. Strip leading "www." (case-insensitive).
    3. Strip any other common subdomain prefix (up to first label) ONLY if
       the remaining string contains at least one dot. For any subdomain
       other than "www.", keep the subdomain as part of the name unless
       it exactly matches "app", "go", "my", "login", "signup" — in which
       case strip it. (This prevents "app.notion.so" → "App".)
    4. Extract the leftmost label (up to but NOT including the first dot).
       This is the prospect name stem.
       Examples:
         stripe.com       → "stripe"
         notion.so        → "notion"
         freshdesk.com    → "freshdesk"
         www.hubspot.com  → "hubspot"
         app.notion.so    → "notion"   (strip "app" per rule 3)
         go.gong.io       → "gong"     (strip "go" per rule 3)
         my.salesforce.com → "salesforce" (strip "my")
         mail.google.com  → "mail-google"  (unknown subdomain: join with hyphen)

    Wait — revised algorithm for clarity:

    KNOWN_STRIP_SUBDOMAINS = {"www", "app", "go", "my", "login", "signup", "portal"}

    1. domain = domain.strip().lower()
    2. labels = domain.split(".")
    3. if len(labels) >= 3 and labels[0] in KNOWN_STRIP_SUBDOMAINS:
           labels = labels[1:]
    4. # labels[0] is now the prospect company name stem
       stem = labels[0]
    5. # Handle hyphens: replace with space, title-case each word
       name = stem.replace("-", " ").title()
    6. return name

    Edge cases:
      - "co.uk" TLDs: the two-part TLD is in labels[1:] and never in labels[0],
        so the algorithm is unaffected. "freshdesk.co.uk" → "freshdesk" → "Freshdesk".
      - Numeric stems (e.g. "24sessions.com"): title() does not alter digits.
        "24sessions" → "24sessions" (acceptable).
      - All-hyphen or all-digit domains: pass through title() as-is.
    """
```

**`validate_and_maybe_retry` logic (F7):**

```
html = run_for_prospect(...)
count = validate_html_sections(html, container_selector="div.slides")
if count == 10:
    return html
# count != 10: retry once
html2 = run_for_prospect(..., strict=True)  # crew.py adds stricter prompt when strict=True
count2 = validate_html_sections(html2, container_selector="div.slides")
if count2 == 10:
    return html2
# Both failed: write first attempt (not the retry), log warning
append_error_log(path, format_section_warning(prospect_name, count))
return html
```

**Dependencies:** `argparse`, `os`, `sys`, `pathlib`, `dotenv`, `knowledge_store.KnowledgeStore`, `crew.run_for_prospect`, `tools.WebsiteThemeScraper` (indirect), `tiktoken` (indirect, via tasks.py)

---

### `knowledge_store.py` — `KnowledgeStore`

**Purpose:** Wraps ChromaDB for incremental knowledge base ingestion and semantic search.

**Inputs:**
- `company_name: str` (constructor)
- `persist_dir: str` (constructor, default `"chroma_db"`)

**Outputs:**
- `IngestResult` from `run_ingestion_check()`
- `list[str]` of document chunks from `similarity_search()`

**Key logic — chunking:**

```python
# Tokeniser: tiktoken.get_encoding("cl100k_base")
# Chunk size: 500 tokens
# Overlap: 50 tokens
# Algorithm: sliding window over token ids
#   i = 0
#   while i < len(all_tokens):
#       chunk_tokens = all_tokens[i : i + 500]
#       chunks.append(tokeniser.decode(chunk_tokens))
#       i += (500 - 50)   # advance by 450 tokens
```

**Key logic — MD5 change detection:**

```python
# For each .md file f in knowledge_dir:
#   current_hash = hashlib.md5(f.read_bytes()).hexdigest()
#   existing = collection.get(
#       where={"$and": [{"source_file": {"$eq": f.name}},
#                       {"file_hash": {"$eq": current_hash}}]},
#       limit=1
#   )
#   if existing["ids"]:            # hash match → skip
#       continue
#   # hash mismatch or new file → delete old, re-ingest
#   collection.delete(where={"source_file": {"$eq": f.name}})
#   # chunk, embed, upsert new chunks
#   collection.upsert(ids=[...], documents=[...], metadatas=[...])
```

**Key logic — similarity search:**

```python
# embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
# query_embedding = embeddings.embed_query(query)
# results = collection.query(
#     query_embeddings=[query_embedding],
#     n_results=n_results,
#     include=["documents"]
# )
# return results["documents"][0]   # list of str, length = min(n_results, collection_size)
```

**Dependencies:** `chromadb 1.5.9`, `langchain_openai.OpenAIEmbeddings`, `tiktoken 0.7.x`, `hashlib`, `pathlib`

---

### `agents.py` — 4 CrewAI Agents

**Purpose:** Defines and returns the 4 `Agent` instances. Agents are created inside `build_crew()` (not module-level) so that fresh LLM instances are created per prospect run.

**Key logic — model construction:**

```python
model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
# LangFuse callback — optional, silently skipped if keys not set
langfuse_handler = _make_langfuse_handler(prospect_name, company_name)  # returns None if unconfigured
callbacks = [langfuse_handler] if langfuse_handler else []
llm = ChatOpenAI(model=model_name, temperature=0.7, callbacks=callbacks)
# All 4 agents share the same llm instance (and callback) within a single build_crew() call.
```

**Agent definitions:**

```python
# Agent 1 — Business Intelligence Researcher
Agent(
    role="Senior Business Intelligence Researcher",
    goal=(
        "Deeply understand {prospect_name}'s business model, industry verticals, "
        "key customer segments, and top operational pain points."
    ),
    backstory="You are a senior analyst who synthesises market intelligence...",
    tools=[TavilySearchResults(k=3)],
    llm=llm,
    verbose=False,
    max_iter=5,
)

# Agent 2 — Brand Analyst
Agent(
    role="Web Design and Brand Analyst",
    goal="Extract the visual identity of {prospect_name}'s website.",
    backstory="You specialise in reverse-engineering brand design from live websites...",
    tools=[WebsiteThemeScraper()],
    llm=llm,
    verbose=False,
    max_iter=3,
)

# Agent 3 — Value Proposition Strategist
Agent(
    role="Solution Consultant for {company_name}",
    goal=(
        "Using retrieved knowledge chunks about {company_name}'s capabilities, "
        "produce a prioritised list of value propositions specific to {prospect_name}."
    ),
    backstory="You are a trusted advisor who connects product capabilities to customer needs...",
    tools=[KnowledgeSearchTool(knowledge_store=knowledge_store)],
    llm=llm,
    verbose=False,
    max_iter=3,
)

# Agent 4 — Presentation Designer
Agent(
    role="B2B SaaS Creative Director",
    goal=(
        "Author a complete, beautifully formatted 10-slide HTML presentation "
        "positioning {company_name} as the solution to {prospect_name}'s pain points."
    ),
    backstory="You are an award-winning creative director who writes flawless HTML...",
    tools=[],
    llm=llm,
    verbose=False,
    max_iter=3,
)
```

**Dependencies:** `crewai 1.14.7`, `langchain_openai 0.3.x`, `tools.py`, `os`

---

### `tasks.py` — 4 CrewAI Tasks

**Purpose:** Defines `Task` instances. Assembled inside `build_crew()`.

**Key logic — Agent 1 output truncation (Q1 resolution):**

Decision: **Post-process with tiktoken truncation in `crew.py`** after the crew completes.

Rationale: CrewAI 1.x `expected_output` instructions are advisory — the LLM may still produce verbose output that exceeds the limit. `context=` injection in CrewAI concatenates the full prior task output string. Therefore, the truncation must happen at the string level before that output is used as context. The cleanest place to enforce this deterministically is in `run_for_prospect()` in `crew.py`, not in the task definition.

Implementation:

```python
# In crew.py, after crew.kickoff():
# CrewAI 1.x exposes task outputs via crew.tasks[i].output.raw
research_output = crew.tasks[0].output.raw   # Agent 1's raw text output

# Truncate to 1,500 tokens
enc = tiktoken.get_encoding("cl100k_base")
tokens = enc.encode(research_output)
if len(tokens) > 1500:
    research_output = enc.decode(tokens[:1500])

# Rebuild context injection for tasks 3 and 4 by modifying the task
# description to embed the truncated research inline, OR:
# Re-run tasks 3 and 4 with the truncated context.
```

Wait — this approach requires re-running the crew or restructuring. The correct mechanism in CrewAI 1.x `context=` is evaluated at crew kickoff, not after. Therefore the truncation must be applied **before** the relevant downstream tasks execute.

**Revised decision:** Use a two-phase approach within `run_for_prospect()`:

```python
# Phase 1: Run a mini-crew with only tasks 1 and 2 (independent, no context chain)
mini_crew = Crew(agents=[researcher, brand_analyst], tasks=[research_task, brand_task],
                 process=Process.sequential)
mini_result = mini_crew.kickoff(inputs={"prospect_name": ..., "company_name": ...})

# Truncate Agent 1 output
research_raw = research_task.output.raw
enc = tiktoken.get_encoding("cl100k_base")
tokens = enc.encode(research_raw)
truncated_research = enc.decode(tokens[:1500]) if len(tokens) > 1500 else research_raw

# Phase 2: Run tasks 3 and 4 with the truncated research injected via task description interpolation
# Patch the value_prop_task and presentation_task descriptions to embed truncated_research inline
# rather than relying on context= object chaining.
value_prop_task_final = Task(
    description=value_prop_task.description + f"\n\nResearch context:\n{truncated_research}",
    agent=value_prop_strategist, expected_output=..., tools=[knowledge_search_tool]
)
presentation_task_final = Task(
    description=presentation_task.description +
        f"\n\nResearch context:\n{truncated_research}" +
        f"\n\nBrand theme:\n{brand_task.output.raw}",
    context=[value_prop_task_final],
    agent=presentation_designer, expected_output=...
)
final_crew = Crew(
    agents=[value_prop_strategist, presentation_designer],
    tasks=[value_prop_task_final, presentation_task_final],
    process=Process.sequential
)
final_result = final_crew.kickoff(inputs={"prospect_name": ..., "company_name": ...})
```

This guarantees the 1,500-token cap is enforced deterministically. The two mini-crew pattern also avoids context window inflation from parallel-capable tasks 1 and 2 feeding into 3 and 4.

**Task definitions (base, before phase split):**

```python
# research_task
Task(
    description=(
        "Search for information about {prospect_name} ({prospect_domain}). "
        "Conduct 2–3 targeted searches covering: (1) business model and revenue streams, "
        "(2) key customer segments and verticals, (3) operational pain points and growth challenges. "
        "If Tavily returns no results, write: 'Limited information found for {prospect_domain}. "
        "Proceeding with general industry context.' "
        "Write a structured summary. Be concise."
    ),
    expected_output=(
        "A structured text summary (≤800 words) covering business model, customer segments, "
        "and 3–5 specific pain points for {prospect_name}."
    ),
    agent=researcher,
)

# brand_task
Task(
    description=(
        "Use the WebsiteThemeScraper tool to extract the brand colours and fonts "
        "from {prospect_domain}. Report the JSON theme object returned by the tool."
    ),
    expected_output=(
        "A JSON object with keys: primary_color, secondary_color, background_color, "
        "font_family, accent_color."
    ),
    agent=brand_analyst,
)

# value_prop_task (base — description patched in phase 2)
Task(
    description=(
        "Using the KnowledgeSearchTool, search {company_name}'s knowledge base "
        "for the top 20 capabilities most relevant to the prospect's pain points described in "
        "the research context below. Produce a prioritised list of 5 value propositions. "
        "Each value prop MUST cite a specific product feature or metric from the retrieved chunks."
    ),
    expected_output=(
        "A numbered list of 5 value propositions. Each must: (1) name the prospect pain point, "
        "(2) name the specific {company_name} capability that addresses it, "
        "(3) include a concrete metric or outcome if available in the knowledge base."
    ),
    agent=value_prop_strategist,
    tools=[knowledge_search_tool],
)

# presentation_task (base — description patched in phase 2)
Task(
    description=(
        "Generate a complete 10-slide HTML presentation. Requirements:\n"
        "- Pure HTML with all CSS inline or in a <style> block in <head>\n"
        "- No external CSS or JS file dependencies\n"
        "- All slides are <section> elements, direct children of <div class='slides'>\n"
        "- Each <section> has style='height:100vh; ...'\n"
        "- Apply the brand colours from the brand theme context\n"
        "- If font_family is a Google Fonts name, add a <link> tag to fonts.googleapis.com\n"
        "- Mandatory slides: title/hook, who is {company_name}, "
        "  ≥2 slides on {prospect_name} pain points, ≥3 slides on {company_name} value/fit, "
        "  1 ROI/social proof slide, 1 CTA/next steps slide\n"
        "- Include both {prospect_name} and {company_name} by name in the deck\n"
        "OUTPUT: Only the complete HTML document. No preamble, no explanation."
    ),
    expected_output=(
        "A complete, valid HTML5 document. The <div class='slides'> element must contain "
        "exactly 10 <section> child elements."
    ),
    agent=presentation_designer,
    context=[value_prop_task_final],   # set in phase 2
)
```

**Strict retry variant** (used by `validate_and_maybe_retry` on section count failure):

The `presentation_task_final.description` has this appended:

```
"\n\nCRITICAL: Your previous output had the wrong number of <section> elements. "
"You MUST output exactly 10 <section> elements as direct children of <div class='slides'>. "
"Count them before outputting. Do not include any other <section> tags in the document."
```

**Dependencies:** `crewai 1.14.7`, `tiktoken 0.7.x`

---

### `tools.py` — `WebsiteThemeScraper`

**Purpose:** HTTP scrape of prospect homepage to extract brand colours and fonts.

**Inputs:** `domain: str` (e.g. `"stripe.com"`)

**Outputs:** JSON string of `ThemeDict`

**Neutral fallback theme (Q4 resolution — canonical hex values):**

```python
NEUTRAL_FALLBACK_THEME: ThemeDict = {
    "primary_color":    "#2563eb",   # Accessible blue (WCAG AA on white)
    "secondary_color":  "#1e40af",   # Darker blue variant
    "background_color": "#ffffff",   # White
    "font_family":      "system-ui, -apple-system, sans-serif",
    "accent_color":     "#f59e0b",   # Amber — readable accent
}
```

Rationale: `#2563eb` (Tailwind blue-600) is a professional, accessible blue that reads well on white backgrounds. `#f59e0b` (amber-500) provides sufficient contrast for accents and CTAs. This palette avoids the dark navy from the PRD placeholder (which would require white text everywhere) in favour of a balanced light-background theme.

**Browser-like headers (sent on every request):**

```python
SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
```

**CSS colour extraction logic:**

```python
# 1. Fetch homepage HTML: requests.get(f"https://{domain}/", headers=..., timeout=10,
#                                        allow_redirects=True, max_redirects=2)
# 2. Parse with BeautifulSoup(html, "lxml") (fallback: "html.parser")
# 3. Check <meta name="theme-color" content="#..."> → primary_color candidate
# 4. Find all <link rel="stylesheet"> hrefs
#    - Resolve relative URLs: urllib.parse.urljoin(f"https://{domain}", href)
#    - Fetch each CSS URL (timeout=5s); skip on error
# 5. Concatenate all CSS text
# 6. Extract hex colours via: re.findall(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', css_text)
#    Filter: exclude pure black (#000000, #000) and pure white (#ffffff, #fff)
#    Take the first distinct hex as primary_color, second as secondary_color,
#    third as accent_color.
# 7. Extract background-color: regex r'background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})'
# 8. For font_family: check Google Fonts link tags first (see Q5 below),
#    then regex r'font-family\s*:\s*["\']?([^;"\']+)' from CSS; strip quotes, take first value.
# 9. If any field is still unset after all extraction: fill from NEUTRAL_FALLBACK_THEME.
```

**Google Fonts font name extraction (Q5 resolution — exact regex):**

```python
GOOGLE_FONTS_PATTERN = re.compile(
    r'fonts\.googleapis\.com/css[^"\']*[?&]family=([^&:"\'>\s]+)'
)

def extract_google_font_name(url: str) -> str | None:
    """
    Matches URLs like:
      https://fonts.googleapis.com/css2?family=Inter:wght@400;600
      https://fonts.googleapis.com/css?family=Roboto+Condensed
      https://fonts.googleapis.com/css2?family=Open+Sans&display=swap

    Extraction steps:
    1. Apply GOOGLE_FONTS_PATTERN.search(url)
    2. Capture group 1: the raw family value, e.g. "Inter:wght@400;600"
    3. Split on ":" and take [0]: "Inter"
    4. Replace "+" with " ": "Open Sans" (URL-encoded space)
    5. Return the clean font name: e.g. "Inter", "Roboto Condensed", "Open Sans"

    Returns None if no match.

    The extracted name is used:
    - As the font_family value in ThemeDict (the clean name only, e.g. "Inter")
    - By Agent 4 to construct the <link> tag:
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap"
              rel="stylesheet">
      Agent 4 receives the clean name; it constructs its own <link> tag using standard weights.
    """
```

**Dependencies:** `requests 2.32.x`, `beautifulsoup4 4.12.x`, `lxml`, `re`, `urllib.parse`, `crewai.tools.BaseTool`

---

### `tools.py` — `KnowledgeSearchTool`

**Purpose:** Semantic search over the selling company's ChromaDB collection.

**Inputs:** `research_summary: str` (Agent 3 passes the truncated research text)

**Outputs:** Formatted string of top-5 chunks

**Key logic:**

```python
def _run(self, research_summary: str) -> str:
    chunks = self.knowledge_store.similarity_search(research_summary, n_results=5)
    if not chunks:
        return "No relevant knowledge base content found."
    parts = [f"[Chunk {i+1}]\n{chunk}" for i, chunk in enumerate(chunks)]
    return "\n\n---\n\n".join(parts)
```

**Dependencies:** `knowledge_store.KnowledgeStore`, `crewai.tools.BaseTool`

---

### `crew.py` — Crew Assembly

**Purpose:** Constructs and runs the two-phase crew for a single prospect.

**CrewAI instantiation pattern (Q2 resolution):**

**Decision: Fresh `Crew` instantiation per prospect.** CrewAI 1.14.x does not support resetting or re-running a `Crew` instance after `kickoff()` has been called — the internal state (task outputs, agent memory) is mutated in-place during execution. Attempting to call `kickoff()` again on the same instance produces stale `context=` from the previous run, which would contaminate subsequent prospects' outputs. The correct and idiomatic pattern is to instantiate fresh `Agent`, `Task`, and `Crew` objects for every prospect inside `build_crew()`.

Performance implication: Python object instantiation cost is negligible (<1ms) compared to LLM API call latency (2–60s per agent). There is no performance argument for reusing instances.

```python
def build_crew(
    prospect_domain: str,
    prospect_name: str,
    company_name: str,
    knowledge_store: KnowledgeStore,
    strict: bool = False,
) -> tuple[Crew, Crew, Task, Task]:
    """
    Returns (mini_crew_12, final_crew_34, research_task, brand_task)
    because the two-phase pattern requires access to task outputs between phases.
    strict=True appends the section-count warning to presentation_task description.
    """
    # Build tools
    tavily_tool = TavilySearchResults(k=3)
    theme_tool = WebsiteThemeScraper()
    knowledge_tool = KnowledgeSearchTool(knowledge_store=knowledge_store)

    # Build LLM
    model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0.7)

    # Build agents
    researcher = make_researcher_agent(llm, tavily_tool)
    brand_analyst = make_brand_agent(llm, theme_tool)
    value_prop_strategist = make_value_prop_agent(llm, knowledge_tool)
    presentation_designer = make_presentation_agent(llm)

    # Build tasks
    inputs = {"prospect_name": prospect_name, "prospect_domain": prospect_domain,
              "company_name": company_name}
    research_task = make_research_task(researcher, inputs)
    brand_task = make_brand_task(brand_analyst, inputs)

    mini_crew = Crew(
        agents=[researcher, brand_analyst],
        tasks=[research_task, brand_task],
        process=Process.sequential,
        verbose=False,
    )
    # (final_crew built after phase 1 completes and research is truncated)
    return mini_crew, research_task, brand_task, value_prop_strategist, presentation_designer, inputs, llm
```

**`_make_langfuse_handler` helper (defined in `crew.py`):**

```python
def _make_langfuse_handler(prospect_name: str, company_name: str):
    """
    Returns a LangFuse CallbackHandler if LANGFUSE_PUBLIC_KEY is set, else None.
    Each prospect run gets its own handler so traces are keyed per prospect.
    """
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    if not public_key:
        return None
    from langfuse.callback import CallbackHandler
    return CallbackHandler(
        public_key=public_key,
        secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
        host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
        trace_name=f"{company_name}/{prospect_name}",
        tags=[company_name, prospect_name],
    )
```

**Dependencies:** `crewai 1.14.7`, `langchain_openai 0.3.x`, `tiktoken 0.7.x`, `langfuse` (optional), `agents.py`, `tasks.py`, `tools.py`, `knowledge_store.py`

---

## 6. Integration Details

### OpenAI API

- **Auth:** `OPENAI_API_KEY` env var; loaded by `python-dotenv` before any `ChatOpenAI` or `OpenAIEmbeddings` instantiation.
- **Rate limits:** GPT-4o-mini Tier 1: 500 RPM, 200k TPM. Sequential processing of 10 prospects at ~4 LLM calls each = 40 calls; well within limits.
- **Error handling:** `langchain_openai` retries `RateLimitError` (429) with exponential backoff up to 2 times by default. All other errors (`AuthenticationError`, `APIConnectionError`, `APITimeoutError`) propagate to the per-prospect `try/except` in `main.py`.
- **Local dev mock:** Set `OPENAI_API_KEY=sk-test-fake` and point to a local OpenAI-compatible server (e.g. `ollama` with `OPENAI_BASE_URL` override) for offline testing. Alternatively, record/replay with `pytest-recording` (VCR cassettes).

### Tavily API

- **Auth:** `TAVILY_API_KEY` env var; `TavilySearchResults` reads it automatically.
- **Rate limits:** Free tier: 100 RPM, 1,000 credits/month. A 10-prospect batch uses 30 credits (3 searches × 10). Not a concern.
- **Error handling:** Sparse results → handled by Agent 1 prompt. Network error → propagates to per-prospect `try/except`.
- **Local dev mock:** `unittest.mock.patch("langchain_community.tools.tavily_search.TavilySearchResults._run", return_value=[...])` in unit tests.

### ChromaDB (local embedded)

- **Auth:** None. Fully local.
- **Persistence path:** `chroma_db/<company_name>/` relative to the working directory (i.e., the `projects/sdr/` root). `PersistentClient(path="chroma_db/<company_name>")`.
- **Concurrent access:** Single-process CLI; no concurrency concerns.
- **Error handling:** `InvalidDimensionException` if collection was created with a different embedding model. Mitigation: if this error is raised during `KnowledgeStore.__init__`, print a descriptive error instructing the user to delete `chroma_db/<company_name>/` and re-run. `sys.exit(1)`.
- **Version migration:** `chromadb==1.5.9` is pinned. If the user upgrades and sees a `DatabaseError` on `PersistentClient` creation, the README documents: "Delete `chroma_db/` and re-run to re-ingest."
- **Local dev mock:** Use `chromadb.EphemeralClient()` in unit tests (in-memory, no disk I/O).

### Web Scraping (requests + BeautifulSoup4)

- **Auth:** None. Public HTTP GET.
- **Rate limits:** N/A — one request per prospect (plus CSS fetches). Not a concern.
- **Retry strategy:** No retry on scraping. Single attempt with `timeout=10`. Any failure → `NEUTRAL_FALLBACK_THEME`. The SDR user experience degrades gracefully (neutral colours) rather than failing.
- **Redirect policy:** `requests.get(..., allow_redirects=True)` with a custom adapter capping redirects at 2 (set via `requests.Session` with `max_redirects=2`).
- **CSS fetch timeout:** 5 seconds per CSS file (separate from the 10-second homepage timeout). If a CSS file fetch times out, skip it and continue with others.
- **Local dev:** Mock `requests.get` with pre-recorded HTML fixtures for deterministic tests.

### LangFuse (self-hosted observability)

- **Auth:** `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` env vars. If `LANGFUSE_PUBLIC_KEY` is absent, the integration is entirely skipped — no error, no warning.
- **Host:** `LANGFUSE_HOST` env var, default `http://localhost:3000`. Set to your self-hosted instance URL.
- **Self-hosted setup:** A `docker-compose.yml` in the project root starts LangFuse + PostgreSQL + ClickHouse. Run `docker compose up -d` once before using the utility with tracing enabled.
- **Trace structure:** One LangFuse trace per prospect run, named `{company_name}/{prospect_name}`. The trace contains 4 child spans — one per agent LLM call — automatically created by the `CallbackHandler`.
- **What is captured per span:**
  - Full prompt (system + human messages)
  - Full LLM response text
  - Token counts (prompt, completion, total)
  - Latency (ms)
  - Model name
  - Auto-computed cost (LangFuse knows `gpt-4o-mini` pricing)
  - Error status if the LLM call raises an exception
- **Error tracking:** LangFuse marks spans as errored automatically when the LangChain callback receives an `on_llm_error` event. No manual instrumentation needed.
- **Rate limits / quotas:** Self-hosted — no external rate limits. All data stays on your machine.
- **Local dev without observability:** Remove or omit `LANGFUSE_PUBLIC_KEY` from `.env`. The pipeline runs identically without any tracing overhead.

---

### Google Fonts CDN (runtime, client-side only)

- **Integration:** Agent 4 injects a `<link>` tag pointing to `fonts.googleapis.com` in the generated HTML `<head>`. This is a browser-side request when the HTML is opened, not a server-side request made by the utility.
- **Fallback:** If the font is not a recognised Google Font or no font was detected, Agent 4 uses `system-ui, -apple-system, sans-serif` (no `<link>` tag).
- **No auth required.**

---

## 7. Non-Functional Implementation

### Error Handling Conventions

1. **Per-prospect isolation:** `main.py` wraps every `run_for_prospect()` call in `try/except Exception as e`. No exception kills the batch.
2. **Scraper fallback:** `WebsiteThemeScraper._run()` catches all exceptions with a bare `except Exception` and returns `NEUTRAL_FALLBACK_THEME`. No exception ever leaves the tool.
3. **ChromaDB init errors:** `KnowledgeStore.__init__` catches `chromadb.errors.InvalidDimensionException` and `Exception` during client creation, prints a human-readable message, and calls `sys.exit(1)`.
4. **Missing env vars:** `main.py` checks for `OPENAI_API_KEY` and `TAVILY_API_KEY` immediately after `load_dotenv()`. If either is missing: `print("Error: OPENAI_API_KEY is required.", file=sys.stderr); sys.exit(1)`.
5. **Tool errors in CrewAI:** All `BaseTool._run()` implementations catch exceptions internally and return an error string (not raise). This prevents CrewAI from entering an infinite retry loop.

### Logging and Observability

**`errors.log` format (Q7 resolution — exact line format):**

```
{ISO8601_TIMESTAMP} | {PROSPECT_DOMAIN} | {EXCEPTION_CLASS} | {ONE_LINE_MESSAGE}
```

Example lines:

```
2026-06-18T14:23:11Z | notion.so | APIConnectionError | Connection timeout after 30s
2026-06-18T14:31:05Z | hubspot.com | SECTION_COUNT_WARNING | Expected 10 sections, got 8 (retry also produced 8)
```

Implementation:

```python
def format_error_line(domain: str, exc: Exception) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    exc_class = type(exc).__name__
    message = str(exc).split("\n")[0][:200]   # first line, max 200 chars
    return f"{ts} | {domain} | {exc_class} | {message}"

def format_section_warning(domain: str, count: int) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"{ts} | {domain} | SECTION_COUNT_WARNING | "
        f"Expected 10 sections, got {count} (retry also produced {count})"
    )
```

**stdout progress:** All progress lines go to `stdout` (not `stderr`). Errors go to `stderr` (for `sys.exit` cases) and also to `errors.log` (for per-prospect failures).

**No file rotation:** `errors.log` is appended indefinitely. For v1, users are expected to manage log size manually (typically small: <100 runs/day).

**LangFuse observability (when enabled):** The LangFuse dashboard at `http://localhost:3000` provides:
- Per-trace view: all 4 agent spans for a single `{company_name}/{prospect_name}` run
- Cost breakdown: per-agent and per-run USD cost computed from token counts
- Latency breakdown: time spent per agent, identifying bottlenecks
- Full prompt/response inspection: debug poor-quality outputs by examining exact inputs
- Error rate: filter traces by error status to identify patterns in failures

No additional logging code is required — the `CallbackHandler` captures all of this automatically via LangChain's callback system.

### `<section>` Count Validation Scope (Q3 resolution)

**Decision: Count direct `<section>` children of `<div class="slides">`.**

Rationale: A full HTML document (with `<header>`, `<footer>`, or other structural `<section>` elements) could contain more than 10 `<section>` tags in total. Counting all of them would produce false failures. The Agent 4 task prompt instructs it to place all slide sections as direct children of `<div class="slides">`. Validation targets only that container.

Implementation:

```python
def validate_html_sections(html: str) -> int:
    """
    Returns count of direct <section> children of <div class="slides">.
    Returns -1 if <div class="slides"> is not found in the document.
    """
    soup = BeautifulSoup(html, "lxml")
    container = soup.find("div", class_="slides")
    if container is None:
        return -1
    return len(container.find_all("section", recursive=False))
```

Note: `recursive=False` ensures only direct children are counted, not nested `<section>` elements within slides.

### Caching Strategy

- **No runtime caching.** Tavily results, scraper output, and LLM responses are not cached between runs. Each run is a fresh pipeline execution.
- **Effective caching via ChromaDB persistence:** Knowledge base embeddings persist across runs and are only recomputed when file content changes (MD5 detection). This is the only "cache" in the system.
- **No TTL policy:** ChromaDB data persists indefinitely until the user deletes `chroma_db/<company_name>/`.

### Security

- `.gitignore` must include: `.env`, `chroma_db/`, `output/`.
- `WebsiteThemeScraper` never sends cookies, authentication headers, or credentials to external domains.
- API key values are never logged to stdout, stderr, or `errors.log`. Error messages from OpenAI/Tavily APIs may contain contextual information but not the raw key value (OpenAI and Tavily APIs do not echo keys in error responses).

### Database Migrations

- Not applicable (no relational database).
- ChromaDB schema changes (new metadata fields) are handled by deleting the collection (`chroma_db/<company_name>/`) and re-running ingestion. Document this in README.
- If a future version adds new metadata fields to chunks, a migration script (`scripts/migrate_chroma.py`) should be provided; not required for v1.

---

## 8. Implementation Order

Build in this order. Each step is testable in isolation before the next begins.

### Step 1 — Project Scaffold and Dependencies (Day 1, ~2h)

Set up the directory structure exactly as in `brief.md`. Create `requirements.txt` with pinned versions (see below). Create `.env.example`. Verify `pip install -r requirements.txt` succeeds in a clean Python 3.11 venv.

**Testable:** `python -c "import crewai, chromadb, tiktoken, bs4, langchain_openai"` passes.

### Step 2 — `knowledge_store.py` (Day 1–2, ~4h)

Implement `KnowledgeStore` with `run_ingestion_check()` and `similarity_search()`. No agents, no CLI.

**Testable:**
- Unit test: ingest 2 small markdown files into `EphemeralClient`, verify chunk count.
- Unit test: modify one file, re-run ingestion, verify only that file's chunks are updated.
- Unit test: `similarity_search("customer support pain points")` returns 5 strings.

### Step 3 — `tools.py` — `WebsiteThemeScraper` (Day 2, ~3h)

Implement scraper with browser headers, CSS extraction, Google Fonts detection (Q5 regex), and neutral fallback.

**Testable:**
- Unit test with mocked `requests.get`: verify ThemeDict structure returned.
- Unit test: HTTP 403 response → NEUTRAL_FALLBACK_THEME returned.
- Unit test: Google Fonts URL → correct font name extracted.
- Manual test: `WebsiteThemeScraper()._run("stripe.com")` → inspect output.

### Step 4 — `tools.py` — `KnowledgeSearchTool` (Day 2, ~1h)

Implement `KnowledgeSearchTool` (depends on Step 2).

**Testable:** Unit test with a populated `EphemeralClient`: verify tool returns formatted string of 5 chunks.

### Step 5 — `agents.py` and `tasks.py` (Day 3, ~4h)

Implement all 4 agent and task factory functions. No crew assembly yet.

**Testable:** Unit test: `make_researcher_agent(llm, tool)` returns a `crewai.Agent` instance with the correct role string. (No LLM call needed for this test.)

### Step 6 — `crew.py` — Two-Phase Crew (Day 3–4, ~5h)

Implement `build_crew()` and `run_for_prospect()` with the two-phase truncation pattern. Integration test with real OpenAI + Tavily API keys.

**Testable:**
- Spike test: Run `run_for_prospect("stripe.com", "Stripe", "hiver", store)` end-to-end with a populated knowledge store. Verify HTML string is returned and `<div class="slides">` is present.
- Verify Agent 1 output is truncated to ≤1,500 tokens (assert `len(enc.encode(research_raw)) <= 1500`).

### Step 7 — `main.py` — CLI and Batch Loop (Day 4, ~4h)

Implement the full `main.py`: arg parsing, validation, ingestion gate, prospect loop, HTML validation + retry, file writing, error isolation.

**Testable:**
- Unit test: `derive_prospect_name("stripe.com")` == `"Stripe"`.
- Unit test: `derive_prospect_name("app.notion.so")` == `"Notion"`.
- Unit test: `derive_prospect_name("www.freshdesk.com")` == `"Freshdesk"`.
- Unit test: missing `--company` → exit code 1.
- Integration test: run full CLI against 2 prospects with real API keys.

### Step 8 — HTML Validation and Retry (Day 4–5, ~2h)

Implement `validate_html_sections()` and integrate retry logic into `main.py`.

**Testable:**
- Unit test: HTML with correct `<div class="slides">` containing 10 `<section>` children → returns 10.
- Unit test: HTML without `<div class="slides">` → returns -1.
- Unit test: retry is triggered exactly once on first bad count.

### Step 9 — README, .env.example, and End-to-End Verification (Day 5, ~3h)

Write `README.md` and `.env.example`. Run the full verification plan from `brief.md` (Section: Verification Plan).

**Testable:** All 7 verification steps in `brief.md` pass.

### Step 10 — Edge Case Polish (Day 5–6, ~3h)

- Test `derive_prospect_name` with hyphenated, numeric, and subdomain edge cases.
- Test ChromaDB `InvalidDimensionException` path.
- Test `errors.log` format output.
- Verify `--dry-run` flag (F13, nice-to-have) if time permits.

---

## 9. Open Technical Questions

All 8 PRD open questions are resolved in this spec. The following residual questions remain for implementation-time validation:

### R1 — CrewAI 1.14.x `context=` behaviour in two-phase crews (confirmed at Step 6 spike)

The spec adopts a two-phase crew pattern to enforce token truncation deterministically. The assumption is that `Task.output.raw` is accessible after `Crew.kickoff()` completes in CrewAI 1.14.7. **Verify during the Step 6 spike** that `task.output.raw` (not `.output.result` or another attribute) is the correct field name in v1.14.7.

If `output.raw` is unavailable: fall back to parsing `crew.kickoff()` return value (the `CrewOutput` object exposes `.raw` on the overall result, but per-task access may differ).

### R2 — `lxml` availability in target environments

`lxml` requires a C extension; it is available as a wheel on all major platforms (macOS, Linux, Windows) via PyPI. However, some minimal Docker images may require `apt-get install libxml2-dev libxslt1-dev`. Add to README: "If `lxml` fails to install, remove it from `requirements.txt`; BeautifulSoup will fall back to `html.parser` automatically."

### R3 — Tavily `TavilySearchResults` constructor signature in `langchain_community 0.3.x`

The `k` parameter is confirmed in `langchain_community 0.2.x`. Verify it remains `k` (not `num_results` or similar) in the version pinned in `requirements.txt`. If renamed, update the tool instantiation call.

### R4 — CSS fetching from `<link rel="stylesheet">` on HTTPS-only sites

Some sites return a `<link>` tag with a `//`-prefixed href (protocol-relative). `urllib.parse.urljoin("https://stripe.com", "//fonts.googleapis.com/...")` correctly resolves to `https://fonts.googleapis.com/...`. Verify this with a unit test using a fixture with a protocol-relative stylesheet href.

---

## Appendix A — `requirements.txt` (pinned)

```
crewai==1.14.7
langchain-openai==0.3.16
langchain-community==0.3.24
chromadb==1.5.9
tiktoken==0.7.0
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.2.2
python-dotenv==1.0.1
langfuse>=2.0.0  # optional — omit if not using observability
```

Note: `langchain-openai` and `langchain-community` versions should be confirmed compatible with `crewai 1.14.7` at installation time. CrewAI's `pyproject.toml` specifies its LangChain dependency bounds; the versions above are current as of June 2026.

---

## Appendix B — `.env.example`

```dotenv
# Required: Your OpenAI API key
OPENAI_API_KEY=your_openai_api_key_here

# Required: Your Tavily Search API key
# Get one at https://app.tavily.com
TAVILY_API_KEY=your_tavily_api_key_here

# Optional: OpenAI model to use for all 4 agents
# Default: gpt-4o-mini (recommended for cost efficiency ~$0.05/prospect)
# Override: gpt-4o (higher quality, ~$0.15/prospect)
OPENAI_MODEL=gpt-4o-mini

# Optional: LangFuse observability (self-hosted)
# Leave unset to disable tracing entirely — the pipeline runs normally without it.
# Run `docker compose up -d` first to start the local LangFuse instance.
# Get keys from http://localhost:3000 after first launch.
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=http://localhost:3000
```

---

## Appendix C — Open Question Resolution Summary

| Q# | Question | Resolution |
|---|---|---|
| Q1 | Agent 1 output truncation mechanism | Post-process with `tiktoken cl100k_base` after phase-1 crew completes; inject truncated text (≤1,500 tokens) into phase-2 task descriptions directly rather than via `context=` chaining |
| Q2 | CrewAI crew instantiation per prospect | Fresh `Crew` instantiation per prospect, every time. No reuse. Instantiation cost is negligible vs. API latency. |
| Q3 | `<section>` count validation scope | Count direct `<section>` children of `<div class="slides">` using `soup.find("div", class_="slides").find_all("section", recursive=False)` |
| Q4 | Neutral fallback theme hex values | `primary_color: #2563eb`, `secondary_color: #1e40af`, `background_color: #ffffff`, `font_family: system-ui, -apple-system, sans-serif`, `accent_color: #f59e0b` |
| Q5 | Google Fonts font name extraction regex | `re.compile(r'fonts\.googleapis\.com/css[^"\']*[?&]family=([^&:"\'>\s]+)')` — capture group 1, split on `:`, replace `+` with space |
| Q6 | Prospect name derivation edge cases | Strip known subdomain prefixes (`www`, `app`, `go`, `my`, `login`, `signup`, `portal`); take leftmost remaining label; replace `-` with space; title-case. |
| Q7 | `errors.log` format | `{ISO8601_UTC} \| {domain} \| {ExceptionClass} \| {first line of message, max 200 chars}` |
| Q8 | ChromaDB version | Pin `chromadb==1.5.9` — confirmed latest stable as of June 2026 |

---

*End of Tech Spec — SDR Presentation Utility v1.0*
