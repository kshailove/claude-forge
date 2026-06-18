# SDR Presentation Utility — Project Brief

## Problem

Sales Development Representatives (SDRs) spend significant time manually researching prospects and crafting personalised pitch materials. This utility automates that workflow: given a selling company name and a list of prospect domains, it researches each prospect, maps the seller's capabilities to their pain points via RAG, extracts their brand colours/fonts, and produces a ready-to-use HTML presentation deck — all driven by CrewAI agents.

The utility is fully generic — it works for any company, not just Hiver.

---

## Users & Roles

- **SDR (Sales Development Representative)**: Primary user. Provides the selling company name, the knowledge base files, and the prospect list. Runs the utility and uses the generated HTML presentations for outreach.

---

## Tech Stack

- **Language**: Python 3.11+
- **Agent Framework**: CrewAI (sequential crew)
- **LLM**: OpenAI GPT-4 (via `langchain_openai`)
- **Search**: Tavily Search API (`langchain_community.tools.tavily_search`)
- **Web scraping**: `requests` + `BeautifulSoup4` (CSS/font extraction)
- **Vector DB**: ChromaDB (local, embedded, persistent to disk)
- **Embeddings**: OpenAI `text-embedding-3-small`
- **Interface**: CLI v1 (Gradio on Huggingface deferred to v2)
- **Observability**: LangFuse (self-hosted via Docker) — optional, traces per-prospect LLM calls
- **Storage**: File system + ChromaDB (no external database)

---

## Project Layout

```
projects/sdr/
├── knowledge/
│   └── <company_name>/       ← subfolder named after the selling company
│       ├── products.md       ← (example) user populates with product knowledge
│       └── *.md              ← any number of markdown files
├── input/
│   └── prospects.txt         ← one domain per line (e.g. stripe.com)
├── output/
│   └── <company_name>/       ← output subfolder per selling company
│       └── presentation_<prospect>.html
├── chroma_db/
│   └── <company_name>/       ← ChromaDB collection isolated per company
├── src/
│   ├── knowledge_store.py    ← ChromaDB wrapper: ingest, similarity search
│   ├── agents.py             ← 4 CrewAI agent definitions
│   ├── tasks.py              ← 4 task definitions (with context chaining)
│   ├── tools.py              ← WebsiteThemeScraper + KnowledgeSearchTool
│   ├── crew.py               ← crew assembly + run logic per prospect
│   └── main.py               ← entry point: ingest check, read input, loop, save output
├── requirements.txt
├── .env.example
└── README.md
```

---

## RAG Architecture

### Ingestion (`knowledge_store.py`)
- Runs at startup in `main.py` — auto-skipped if knowledge files are unchanged
- Change detection: stores an MD5 hash of each knowledge file in ChromaDB metadata; re-ingests if hash differs
- Chunking: **500-token chunks, 50-token overlap**
- Embedding model: `text-embedding-3-small` via OpenAI API
- ChromaDB collection name: `<company_name>_knowledge` (dynamic, isolated per company)
- Knowledge files read from: `knowledge/<company_name>/*.md`

### Retrieval (`KnowledgeSearchTool`)
- Query: the research summary produced by Agent 1
- Similarity metric: cosine (ChromaDB default)
- **Top-k: 5 chunks** returned to Agent 3
- Retrieved chunks (not the full document) are injected into Agent 3's task context

---

## CrewAI Architecture — 4 Agents, Sequential Process

### Agent 1 — Business Intelligence Researcher
- **Role**: Senior business research analyst
- **Goal**: Deeply understand the prospect's business model, industry verticals, key customer segments, and operational pain points
- **Tool**: `TavilySearchResults` (2–3 targeted searches per prospect)

### Agent 2 — Brand Analyst
- **Role**: Web design and brand analyst
- **Goal**: Extract the visual identity of the prospect's website — primary/secondary colours and font families — so the presentation feels native to their brand
- **Tool**: Custom `WebsiteThemeScraper` tool

### Agent 3 — Value Proposition Strategist
- **Role**: Solution consultant for `{company_name}`
- **Goal**: Using the retrieved knowledge chunks most relevant to this prospect's pain points, produce a prioritised list of value propositions that map `{company_name}`'s specific capabilities to the prospect's needs
- **Tool**: Custom `KnowledgeSearchTool` (queries ChromaDB with research summary, returns top-5 chunks)
- **Context input**: output of Agent 1

### Agent 4 — Presentation Designer
- **Role**: B2B SaaS creative director
- **Goal**: Author a complete, beautifully formatted 10-slide HTML presentation — positioning `{company_name}` as the solution to this prospect's pain points — using the research, value props, and brand theme. AI decides the optimal slide flow per prospect.
- **Tools**: None (pure LLM generation)
- **Context input**: outputs of Agents 1, 2, and 3

---

## Task Flow (Sequential)

| # | Task | Agent | Context From |
|---|------|-------|-------------|
| 1 | `research_task` — search business model, use cases, pain points | Researcher | — |
| 2 | `brand_task` — scrape CSS/meta for colours + fonts | Brand Analyst | — |
| 3 | `value_prop_task` — RAG search knowledge base, map to pain points | Value Prop Strategist | Task 1 |
| 4 | `presentation_task` — generate 10-slide HTML with brand theme | Presentation Designer | Tasks 1, 2, 3 |

Tasks 1 and 2 have no dependencies on each other; their outputs feed into tasks 3 and 4.

---

## Custom Tools

### `WebsiteThemeScraper`
- Fetches homepage HTML via `requests`
- Parses `<link rel="stylesheet">` → fetches CSS → regex-extracts `color:`, `background-color:`, `font-family:`
- Also checks `<meta name="theme-color">` and `<meta property="og:...">` tags
- Returns: `{ primary_color, secondary_color, background_color, font_family, accent_color }`
- Fallback: returns a neutral professional theme if scraping fails

### `KnowledgeSearchTool`
- Takes the research summary string as input
- Embeds it with `text-embedding-3-small`
- Queries the `<company_name>_knowledge` ChromaDB collection
- Returns top-5 most relevant chunks as a single formatted string
- Used by Agent 3 to ground value props in the selling company's actual capabilities

---

## Input Format

File: `input/prospects.txt` — one domain per line:
```
stripe.com
notion.so
freshdesk.com
```
Company name derived by stripping `www.` prefix and TLD (e.g. `stripe.com` → `Stripe`).

---

## Output Format

- File: `output/<company_name>/presentation_<prospect_name>.html`
- Pure HTML with inline CSS (no external dependencies, no JavaScript required)
- 10 slides as `<section>` divs with full-viewport height
- Fonts loaded via Google Fonts if a font name is detected, else system fallback
- Brand colours applied to headings, backgrounds, and accents

---

## CLI Usage

```bash
python src/main.py --company <company_name>
```

`--company` is the only required argument. It must match the subfolder name under `knowledge/`.

## Main Loop (`main.py`)

```
1. Parse CLI arg: --company <company_name>
2. Validate that knowledge/<company_name>/ exists and contains at least one .md file
3. Load .env (OPENAI_API_KEY, TAVILY_API_KEY)
4. Run knowledge ingestion check for this company:
   - If chroma_db/<company_name>/ empty or knowledge file hashes differ → re-ingest
   - Else → skip ("Knowledge base up to date")
5. Read domains from input/prospects.txt
6. For each domain:
   a. Derive prospect name from domain
   b. Instantiate and run the crew (passing company_name as context)
   c. Capture the HTML output from Agent 4
   d. Write to output/<company_name>/presentation_<prospect_name>.html
   e. Print progress: "✓ Done: <prospect_name>"
7. Print summary: "N presentations generated in output/<company_name>/"
```

---

## Slide Structure (AI-decided per prospect)

The Presentation Designer agent decides the optimal 10-slide flow per prospect. Guardrails ensure every deck includes:
- A title/hook slide
- A "who is `{company_name}`" slide
- At least 2 slides on prospect-specific pain points
- At least 3 slides on `{company_name}`'s fit/value for this prospect
- A ROI/social proof slide
- A clear CTA/next steps slide

---

## Environment Variables

```
OPENAI_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
```

---

## Verification Plan

1. Create `knowledge/hiver/` and populate it with sample Hiver product markdown files
2. Add 2–3 domains to `input/prospects.txt` (e.g. `stripe.com`, `notion.so`)
3. Run `python src/main.py --company hiver` with empty `chroma_db/` — verify ingestion runs and prints chunk count
4. Run again — verify ingestion is skipped ("Knowledge base up to date")
5. Check `output/hiver/` for generated HTML files
6. Open each HTML file in a browser — verify:
   - 10 slides present
   - Brand colours match the prospect's website visually
   - Value props are specific to that prospect (not generic)
   - No broken layout or missing CSS
7. Repeat with a different `--company` value to confirm full genericity

---

## Out of Scope (v1)

- Gradio UI (planned for v2)
- LinkedIn message generation
- PostgreSQL / any external database
- Parallel processing
- Email sending
