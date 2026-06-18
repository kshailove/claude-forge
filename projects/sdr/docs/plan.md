# Project Plan — SDR Presentation Utility

**Date:** 2026-06-18
**Stage:** 2 — Plan
**Author:** Plan Agent (ClaudeForge)

---

## 1. Project Goals

### Primary Goal

Build a CLI utility that takes a selling company's knowledge base and a list of prospect domains and produces a personalised, brand-matched 10-slide HTML presentation for each prospect — fully automated via a 4-agent CrewAI pipeline.

### Success Metrics

| Metric | Target |
|--------|--------|
| Time to generate one presentation | < 60 seconds end-to-end on a standard developer laptop |
| Batch of 10 prospects completes without crash | 100% — per-prospect error handling ensures one failure does not abort the batch |
| HTML structure validity | Every output file contains exactly 10 `<section>` tags (verified via BeautifulSoup post-generation check) |
| Brand colour extraction success rate | >= 60% of prospect homepages yield at least one non-fallback colour (measured in spike) |
| Value props are prospect-specific | Agent 3 output references at least one specific feature name from the knowledge base (manual spot-check on 5 runs) |
| Knowledge base re-ingestion skipped correctly | Running `main.py` twice on unchanged files skips ingestion on the second run (verified by absence of "Ingesting..." log line) |
| Cost per prospect | < $0.15 at standard `gpt-4o-mini` rates |

---

## 2. Scope

### In Scope (v1)

- `src/knowledge_store.py` — ChromaDB wrapper: ingest markdown files with MD5 change detection, 500-token chunks, 50-token overlap, `text-embedding-3-small` embeddings, cosine similarity, top-5 retrieval
- `src/tools.py` — Two custom tools:
  - `WebsiteThemeScraper`: requests + BeautifulSoup, browser-like header set, CSS `<link>` tag + `<meta theme-color>` parsing, Google Fonts detection, neutral fallback theme on any failure
  - `KnowledgeSearchTool`: embeds research summary, queries ChromaDB, returns top-5 chunks as formatted string
- `src/agents.py` — 4 CrewAI agent definitions (Researcher, Brand Analyst, Value Prop Strategist, Presentation Designer) with `gpt-4o-mini` as default model (configurable via `.env`)
- `src/tasks.py` — 4 task definitions with `context=` chaining (task 3 receives task 1; task 4 receives tasks 1, 2, 3); Agent 1 output capped at ~1,500 tokens before passing downstream
- `src/crew.py` — Sequential `Crew` assembly; instantiated fresh per prospect
- `src/main.py` — CLI entry point: `--company` flag, knowledge path validation, `.env` loading, ingestion check, per-prospect `try/except` loop, HTML write, progress printing
- HTML output validation: BeautifulSoup `<section>` tag count check after Agent 4 generation; log a warning (do not crash) if count != 10
- `requirements.txt` with pinned `chromadb==1.5.9` (or latest stable at implementation time)
- `.env.example` with `OPENAI_API_KEY`, `TAVILY_API_KEY`, and `OPENAI_MODEL` (default `gpt-4o-mini`)
- `README.md` covering setup, knowledge base format guide, and `--company` usage
- Verification run: `knowledge/hiver/` sample data, 3 prospect domains, full end-to-end check

### Out of Scope (v1)

- Gradio / Hugging Face web UI
- LinkedIn message or email copy generation
- PostgreSQL or any external database
- Parallel prospect processing (asyncio / threading)
- Email sending or CRM push
- Headless browser (Playwright/Selenium) for JavaScript-rendered CSS extraction
- `--dry-run` cost estimation flag (deferred)
- Multi-language presentation output
- PDF export of the HTML presentation
- CRM integrations (HubSpot, Salesforce, etc.)

### Future Scope (v2+)

- Gradio UI on Hugging Face Spaces
- `--dry-run` flag with token/cost estimate
- Parallel batch processing for large prospect lists
- LinkedIn personalised outreach message as a 5th agent output
- Headless browser fallback for Cloudflare-protected sites
- PPTX export alongside HTML

---

## 3. User Personas

### Persona 1 — Frontline SDR (Primary)

**Name:** Mike, SDR at a 50-person B2B SaaS company
**Goal:** Walk into every discovery call with a deck that speaks to the prospect's specific business — without spending 30 minutes researching and building slides manually
**Jobs-to-be-done:**
- Quickly generate a personalised deck for each prospect on their daily call list
- Trust that the value props referenced are grounded in their company's actual product capabilities
- Open the HTML file directly in a browser for the call, or share a link

**Pain points with current tools:** Existing decks are generic; personalisation is surface-level (logo swap, company name). No tool combines research + knowledge base + brand extraction automatically.

### Persona 2 — Sales Enablement / RevOps Lead (Secondary)

**Name:** Maya, Sales Enablement Manager
**Goal:** Codify the company's competitive positioning and product knowledge into a reusable, always-current knowledge base that feeds every generated deck
**Jobs-to-be-done:**
- Maintain and update `knowledge/<company>/` markdown files as the product evolves
- Verify that generated presentations reflect current messaging, not outdated claims
- Measure how often the utility is used vs. manual deck creation

**Pain points:** Seller knowledge is locked in individuals' heads or stale slides. No mechanism to propagate updated messaging into the hands of every SDR automatically.

### Persona 3 — Technical Evaluator / DevOps (Tertiary)

**Name:** Priya, an engineer or technical co-founder at an early-stage B2B startup
**Goal:** Evaluate whether this utility is worth deploying for their small sales team
**Jobs-to-be-done:**
- Clone the repo, set up `.env`, run against 2–3 prospects in under 15 minutes
- Confirm it works with their own knowledge base files
- Understand the cost per run before committing API budget

**Pain points:** Most AI sales tools are cloud SaaS with opaque pipelines and steep pricing. This persona values local execution and cost transparency.

---

## 4. Milestones

| Milestone | What it includes | Rough Effort |
|-----------|-----------------|--------------|
| **M0: Spikes (pre-work)** | (1) CSS extraction reliability test across 10 real SaaS homepages — measure fallback rate. (2) CrewAI `context=` chaining smoke test with a 2-agent crew to confirm `Task` object chaining works in v1.14.x | 1–2 days |
| **M1: Foundation** | Project layout (all directories), `requirements.txt` (pinned versions), `.env.example`, `knowledge_store.py` (ingest + retrieve), `tools.py` (`WebsiteThemeScraper` with browser headers + fallback, `KnowledgeSearchTool`), unit smoke tests for both tools | 3–4 days |
| **M2: Agent & Crew Assembly** | `agents.py` (4 agent definitions, `gpt-4o-mini` default, model configurable), `tasks.py` (4 tasks with `context=` chaining, Agent 1 output truncation at ~1,500 tokens), `crew.py` (sequential crew, per-prospect instantiation), HTML `<section>` validation after Agent 4 | 3–4 days |
| **M3: Main Loop + Error Handling** | `main.py` (CLI arg parsing, knowledge path validation, `.env` load, ingestion check, per-prospect `try/except`, HTML write, progress print, summary line), output directory auto-creation | 2 days |
| **M4: End-to-End Verification + README** | Verification run with `knowledge/hiver/` + 3 domains (`stripe.com`, `notion.so`, `freshdesk.com`), manual QA of HTML output (10 slides, brand colours, specific value props), `README.md` (setup guide, knowledge base format, cost note) | 2 days |

**Total estimated effort:** ~2 weeks for a single engineer

---

## 5. Key Decisions

The tech spec stage must make these decisions explicitly:

1. **Model string and configurability:** Confirm `gpt-4o-mini` as the default model identifier in `ChatOpenAI`. Define the `.env` variable name (`OPENAI_MODEL`), its default value, and which agents respect it (all 4, or only generation agents). Decide whether `gpt-4o-mini-mini` is a supported option with any prompt adjustments needed.

2. **Agent 1 output truncation mechanism:** Decide exactly how the ~1,500-token cap on Agent 1's research summary is enforced before passing it as `context=` to Tasks 3 and 4. Options: (a) truncate the raw string in `tasks.py` before passing, (b) instruct Agent 1 via its task `expected_output` to produce a summary of max 1,500 tokens, (c) post-process with a token counter (`tiktoken`). Pick one approach and specify the token-counting library.

3. **CrewAI crew instantiation strategy:** Decide whether to instantiate one `Crew` object per prospect (fresh state each run) or reuse and re-run. Per-prospect instantiation is safer for state isolation; confirm this is the pattern in v1.14.x and there are no performance penalties.

4. **HTML validation failure handling:** After Agent 4 produces HTML and the `<section>` count check fails (not 10), decide the response: (a) log a warning and write the file anyway, (b) retry Agent 4 once with a stricter prompt, (c) skip writing and log an error. Define the maximum retry count if option (b) is chosen.

5. **Browser-like header set for `WebsiteThemeScraper`:** Define the exact headers dict to include in all `requests.get()` calls — `User-Agent`, `Accept`, `Accept-Language`, `Accept-Encoding`, `Referer` — and the `timeout` value. This should be a constant in `tools.py`.

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| CSS extraction blocked by Cloudflare / anti-bot on majority of SaaS prospects | High (~50%) | Medium — brand colours missing | Browser-like headers on all requests; graceful fallback to neutral professional theme; spike M0 measures actual failure rate |
| CrewAI `context=` task chaining behaviour differs from expectations in v1.14.x | Medium | High — downstream agents get wrong context | M0 spike confirms behaviour with a minimal 2-task test before full implementation |
| Agent 1 research summary too long — pushes Agent 4 close to context window or inflates cost | Low–Medium | Medium — cost spike or run failure | Explicit 1,500-token cap on Agent 1 output before passing downstream; use `tiktoken` to measure |
| ChromaDB breaking change on version upgrade | Low (if pinned) | Medium — re-ingestion required, data loss risk | Pin `chromadb==1.5.9` exactly; document upgrade procedure (delete collection, re-ingest) |
| Tavily returns sparse/empty results for obscure prospect domains | Medium | Medium — generic research summary, weak value props | Agent 1 task prompt must explicitly handle low-result scenarios with graceful degradation instructions |
| Agent 4 generates syntactically invalid or structurally incomplete HTML | Low | High — unusable output | Post-generation BeautifulSoup validation; retry logic (1 retry) before logging failure |
| Per-prospect crew run crashes mid-batch, corrupting entire output | Low–Medium | High — batch failure | `try/except` per prospect in `main.py`; write error to `output/<company>/errors.log` without stopping the loop |
| OpenAI API rate limit hit on a large batch (>20 prospects) | Low (for most tiers) | Medium — throttled/failed runs | Sequential processing keeps RPM low; document rate limit tiers in README |

---

## 7. Dependencies & Assumptions

### External Dependencies (not controlled by this project)

| Dependency | Version / Status | Risk |
|------------|-----------------|------|
| OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`) | Stable, June 2026 pricing confirmed | API key required; model deprecation possible but no signals |
| Tavily Search API | Operational post-Nebius acquisition | API key required; pricing/limits may change; 1,000 free credits/month sufficient for dev |
| CrewAI | 1.14.7 (June 2026) | Sequential crew + `context=` chaining must be confirmed in spike |
| ChromaDB | 1.5.9 (May 2026) | Pin exact version; do not upgrade without testing persistent data migration |
| BeautifulSoup4 | 4.x stable | No version concerns |
| requests | 2.x stable | No version concerns |

### Assumptions

1. The user running the utility has valid `OPENAI_API_KEY` and `TAVILY_API_KEY` available and funded — the utility does not validate budget or quota before running a batch.
2. The `knowledge/<company_name>/` directory contains at least one `.md` file with meaningful product/capability content. Sparse or empty knowledge files will produce generic value props; this is a garbage-in/garbage-out limitation, not a code bug.
3. Prospect domains in `input/prospects.txt` are valid, publicly accessible web domains. The utility does not validate DNS resolution before attempting scraping.
4. The user is running Python 3.11+ on a machine with internet access and sufficient disk space for the ChromaDB persistent store (~10–50 MB per company knowledge base).
5. All 4 CrewAI agents run sequentially on the same machine in the same Python process — no distributed execution, no message queue.
6. The HTML output is intended for direct browser viewing. The utility is not responsible for email-safe rendering, PDF conversion, or CMS upload.
7. Company name passed via `--company` must exactly match the subfolder name under `knowledge/` — case-sensitive on Linux/macOS. This is a known sharp edge; document clearly in README.
