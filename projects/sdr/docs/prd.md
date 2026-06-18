# Product Requirements Document — SDR Presentation Utility

**Version:** 1.0  
**Date:** 2026-06-18  
**Stage:** 3 — PRD  
**Author:** PRD Agent (ClaudeForge)  
**Status:** Draft — awaiting human gate approval

---

## 1. Overview

### Problem Statement

Sales Development Representatives at B2B SaaS companies spend approximately 30 hours per rep per month manually researching prospects and assembling personalised pitch decks. The output is typically a generic slide deck with a company logo swapped in — not grounded in the prospect's actual business context or the seller's specific product capabilities.

### Solution Summary

The SDR Presentation Utility is a CLI tool that accepts a selling company name and a list of prospect domains, then automatically produces a 10-slide HTML presentation for each prospect. It runs a 4-agent CrewAI pipeline — researching the prospect's business via Tavily, extracting their brand colours/fonts via web scraping, grounding value propositions in the seller's knowledge base via RAG (ChromaDB + `text-embedding-3-small`), and generating a complete HTML presentation deck using `gpt-4o-mini`. The utility is fully generic and works for any selling company whose knowledge files are placed in `knowledge/<company_name>/`.

### Who This Is For

- **Primary:** SDRs and Account Executives at B2B SaaS companies who run daily prospecting and need personalised decks without manual research effort.
- **Secondary:** Sales Enablement / RevOps managers who maintain and evolve the company knowledge base that feeds every generated deck.
- **Tertiary:** Technical evaluators (engineers, technical co-founders) who evaluate whether to deploy this utility for their team and need a clean, self-hosted, cost-transparent setup.

---

## 2. Goals & Non-Goals

### Goals

1. Reduce the time to produce a personalised, prospect-specific presentation from ~30 minutes (manual) to under 60 seconds (automated).
2. Ground every generated deck's value propositions in the selling company's actual knowledge base content — not generic LLM-generated marketing language.
3. Produce HTML output that visually mirrors the prospect's brand colours and fonts where extractable.
4. Process a batch of N prospects without crashing — one prospect failure must not abort the rest of the batch.
5. Be fully self-hosted and generic: no hardcoded company-specific content anywhere in the codebase.
6. Be cost-transparent: under $0.15 per prospect at `gpt-4o-mini` standard rates.

### Non-Goals

- No Gradio or web UI in v1 (deferred to v2).
- No LinkedIn message generation, email copy, or CRM push in v1.
- No parallel/async processing of prospects in v1 (sequential only).
- No PDF export or PPTX export in v1.
- No headless browser (Playwright/Selenium) for JavaScript-rendered CSS extraction in v1.
- No email sending or CRM integration (HubSpot, Salesforce, etc.) in v1.
- No built-in cost estimation or `--dry-run` flag in v1.
- No validation of API key quota or remaining budget before running a batch.
- No multi-language presentation output.

---

## 3. User Personas

Three personas are defined in [`plan.md`](./plan.md) (Section 3). Summaries:

### Persona 1 — Frontline SDR (Primary) — "Mike"

SDR at a 50-person B2B SaaS company. Wants a personalised deck for each prospect on his daily call list without spending 30 minutes on research and slide assembly. Will open the HTML output in a browser during or before the call. Values specificity of value props over visual perfection.

**Key need:** Run the CLI once and get a ready-to-use deck. Trust that value props are grounded in real product knowledge, not hallucinated.

### Persona 2 — Sales Enablement / RevOps Lead (Secondary) — "Maya"

Sales Enablement Manager who owns the `knowledge/<company>/` markdown files. Wants to ensure generated decks reflect current product messaging and competitive positioning. Does not run the CLI daily but is responsible for keeping the knowledge base accurate.

**Key need:** Update knowledge files and have the next CLI run automatically pick up the changes via hash-based re-ingestion.

### Persona 3 — Technical Evaluator (Tertiary) — "Priya"

Engineer or technical co-founder evaluating the utility for a small sales team. Must be able to clone the repo, configure `.env`, and run a successful end-to-end test against 2–3 prospects in under 15 minutes. Values local execution, zero infrastructure overhead, and visible cost per run.

**Key need:** Clean setup path, clear README, and no dependency on external infrastructure beyond API keys.

---

## 4. Features

---

#### F1 — CLI Entry Point with Company Scoping

**Priority:** Must-have  
**Description:** The utility is invoked via `python src/main.py --company <company_name>`. The `--company` argument is the only required CLI parameter and controls which knowledge base, ChromaDB collection, and output directory are used. If the corresponding `knowledge/<company_name>/` directory does not exist or contains no `.md` files, the utility exits with a non-zero return code and a descriptive error message before any API calls are made.  
**User Story:** As an SDR (Mike), I want to run a single CLI command specifying my company name so that I can generate decks without editing any code.  
**Acceptance Criteria:**
- [ ] Running `python src/main.py --company hiver` with a valid `knowledge/hiver/` directory completes without raising an unhandled exception.
- [ ] Running `python src/main.py` without `--company` prints a usage error to stderr and exits with return code 1.
- [ ] Running `python src/main.py --company nonexistent_company` (no matching `knowledge/` subfolder) prints an error message containing the missing path and exits with return code 1.
- [ ] Running `python src/main.py --company empty_company` where `knowledge/empty_company/` exists but contains zero `.md` files exits with return code 1 and a message stating no knowledge files were found.
- [ ] The `--company` value is used verbatim as the ChromaDB collection prefix (`<company_name>_knowledge`) and as the output subdirectory name (`output/<company_name>/`).

---

#### F2 — Knowledge Base Ingestion with MD5 Change Detection

**Priority:** Must-have  
**Description:** At startup, the utility checks each `.md` file in `knowledge/<company_name>/` by computing its MD5 hash and comparing it against the hash stored in ChromaDB document metadata. Files with a changed or absent hash are re-ingested (chunked at 500 tokens, 50-token overlap, embedded with `text-embedding-3-small`). Unchanged files are skipped. If the ChromaDB collection for this company is empty, all files are ingested.  
**User Story:** As a Sales Enablement Lead (Maya), I want the knowledge base to be automatically re-ingested when I update a file so that generated decks always reflect the latest product messaging.  
**Acceptance Criteria:**
- [ ] On first run with an empty `chroma_db/<company_name>/` directory, the utility ingests all `.md` files and prints the total chunk count to stdout (e.g., `Ingested 47 chunks from 3 files`).
- [ ] On a second run with no changes to knowledge files, the ingestion step is skipped and the message `Knowledge base up to date` is printed to stdout. No embedding API calls are made on the second run.
- [ ] After modifying one knowledge file (change at least 1 character), the next run re-ingests only that file and prints a message identifying the file that was updated.
- [ ] Chunks are stored with a `source_file` metadata field containing the filename and a `file_hash` metadata field containing the MD5 hash.
- [ ] The ChromaDB collection name used is exactly `<company_name>_knowledge` (e.g., `hiver_knowledge` for `--company hiver`).
- [ ] Each chunk is at most 500 tokens; adjacent chunks overlap by exactly 50 tokens.

---

#### F3 — Prospect Business Intelligence Research (Agent 1)

**Priority:** Must-have  
**Description:** For each prospect domain, Agent 1 (Business Intelligence Researcher) runs 2–3 targeted Tavily searches to produce a structured research summary covering the prospect's business model, industry verticals, key customer segments, and operational pain points. The output is capped at approximately 1,500 tokens before being passed downstream to avoid context window inflation.  
**User Story:** As an SDR (Mike), I want the tool to automatically research each prospect so that I do not have to manually Google them before generating a deck.  
**Acceptance Criteria:**
- [ ] Agent 1 produces a non-empty text output for every prospect that Tavily returns at least one result for.
- [ ] Agent 1 output passed as context to downstream tasks does not exceed 1,500 tokens (verified via `tiktoken` token count).
- [ ] When Tavily returns zero results for a prospect domain, Agent 1 produces a graceful fallback output (e.g., `"Limited information found for <domain>. Proceeding with general industry context."`) rather than raising an exception.
- [ ] Agent 1 uses the `TavilySearchResults` tool from `langchain_community` with `k=3` (3 results per query).
- [ ] The `TAVILY_API_KEY` environment variable is loaded from `.env` before any search call; if absent, the utility exits with return code 1 before starting the crew.

---

#### F4 — Brand Colour and Font Extraction (Agent 2)

**Priority:** Must-have  
**Description:** Agent 2 (Brand Analyst) uses the `WebsiteThemeScraper` custom tool to fetch the prospect's homepage HTML via `requests`, parse CSS `<link>` stylesheets, and extract primary/secondary/background colours and font families. The scraper also checks `<meta name="theme-color">` and Google Fonts `<link>` tags. If scraping fails for any reason (HTTP error, timeout, Cloudflare block), the tool returns a neutral professional fallback theme rather than raising an exception.  
**User Story:** As an SDR (Mike), I want generated decks to visually match the prospect's brand so that presentations feel native and credible to the recipient.  
**Acceptance Criteria:**
- [ ] `WebsiteThemeScraper` returns a dictionary with at minimum the keys `primary_color`, `secondary_color`, `background_color`, `font_family`, and `accent_color` on every invocation — never raises an unhandled exception.
- [ ] When the HTTP request to the prospect's homepage returns a non-200 status code or times out after 10 seconds, the tool returns the hardcoded neutral fallback theme (`{"primary_color": "#1a1a2e", "secondary_color": "#16213e", "background_color": "#ffffff", "font_family": "system-ui, sans-serif", "accent_color": "#0f3460"}`).
- [ ] The scraper sends browser-like headers on every request: `User-Agent` (modern Chrome), `Accept`, `Accept-Language`, `Accept-Encoding`, and `Referer` headers are all present.
- [ ] When a Google Fonts URL is found in a `<link>` tag (URL contains `fonts.googleapis.com`), the extracted font family name is included in the `font_family` field.
- [ ] The `requests.get()` call uses `timeout=10` (seconds); no request hangs for more than 10 seconds.
- [ ] Agent 2 runs independently of Agent 1 (no `context=` dependency on Agent 1's task object).

---

#### F5 — RAG-Grounded Value Proposition Generation (Agent 3)

**Priority:** Must-have  
**Description:** Agent 3 (Value Proposition Strategist) uses the `KnowledgeSearchTool` to query the selling company's ChromaDB collection with the research summary produced by Agent 1. The tool returns the top-5 most semantically relevant chunks. Agent 3 then produces a prioritised list of value propositions that explicitly map the selling company's capabilities (cited from the retrieved chunks) to the prospect's specific pain points.  
**User Story:** As an SDR (Mike), I want the deck's value props to be grounded in my company's actual product capabilities — not generic talking points — so that I can trust the content when speaking to prospects.  
**Acceptance Criteria:**
- [ ] `KnowledgeSearchTool` returns exactly 5 chunks (or fewer only if the collection contains fewer than 5 chunks total) as a single formatted string on every invocation.
- [ ] Agent 3's output references at least one specific term drawn from the retrieved knowledge chunks (verified by checking that a substring from any returned chunk appears in Agent 3's output text).
- [ ] Agent 3 receives Agent 1's research summary via inline injection into the task description (not via `context=[research_task]` chaining). The research is tiktoken-truncated to ≤1,500 tokens before injection so the context budget for value prop generation is predictable. See tech spec §5 (two-phase crew pattern) for rationale.
- [ ] The embedding used for the ChromaDB query in `KnowledgeSearchTool` is generated by `text-embedding-3-small` (not any other model).
- [ ] Agent 3 does not access the internet (no web search tool assigned to this agent).

---

#### F6 — 10-Slide HTML Presentation Generation (Agent 4)

**Priority:** Must-have  
**Description:** Agent 4 (Presentation Designer) generates a complete, self-contained 10-slide HTML presentation. Each slide is a `<section>` element with full-viewport height and inline CSS. Brand colours and fonts from Agent 2 are applied to headings, backgrounds, and accents. The agent decides the optimal slide flow per prospect but must include guardrail slides: title/hook, "who is `{company_name}`", at least 2 slides on prospect-specific pain points, at least 3 slides on value/fit, 1 ROI/social proof slide, and 1 CTA/next steps slide. Fonts detected as Google Fonts are loaded via a `<link>` tag to `fonts.googleapis.com`; if no specific font is detected, system fonts are used.  
**User Story:** As an SDR (Mike), I want a complete, browser-ready HTML deck that I can open immediately and use on my next call — without any post-processing.  
**Acceptance Criteria:**
- [ ] The generated HTML file contains exactly 10 `<section>` elements at the top level of the slide container (verified by BeautifulSoup post-generation parse counting direct `<section>` children).
- [ ] The generated HTML file has no external CSS or JavaScript file dependencies — all styles are inline or in a `<style>` block within `<head>`.
- [ ] The brand `primary_color` value from Agent 2's output appears at least once in the HTML file's `style` attributes or `<style>` block.
- [ ] When the detected font family matches a known Google Fonts name, the HTML `<head>` contains a `<link>` tag referencing `fonts.googleapis.com`.
- [ ] The HTML file opens in a modern browser (Chrome, Firefox, Safari) without JavaScript errors and renders all 10 slides navigable by scrolling.
- [ ] Agent 4 receives context from all three prior agents: `context=[research_task, brand_task, value_prop_task]`.
- [ ] The output HTML contains at least one `<section>` whose text content includes the prospect's company name (case-insensitive match).
- [ ] The output HTML contains at least one `<section>` whose text content includes the selling company's name (case-insensitive match).

---

#### F7 — Post-Generation HTML Validation with Retry

**Priority:** Must-have  
**Description:** After Agent 4 produces the HTML string, a validation step counts the number of `<section>` elements using BeautifulSoup. If the count is not exactly 10, the crew is re-run once with a stricter prompt for Agent 4. If the retry also produces an invalid count, the output is written to disk as-is and a warning is logged to `output/<company_name>/errors.log` (the batch continues with the next prospect).  
**User Story:** As an SDR (Mike), I want the tool to self-correct malformed output so that I don't have to manually validate each file.  
**Acceptance Criteria:**
- [ ] When Agent 4's first output has fewer or more than 10 `<section>` elements, a retry is triggered exactly once (not zero times, not two or more times automatically).
- [ ] When the retry produces valid HTML with exactly 10 `<section>` elements, the file is written normally and no error is logged.
- [ ] When both the first attempt and the retry produce HTML with a `<section>` count other than 10, the file is still written to disk (not silently discarded), and a line containing the prospect name and actual section count is appended to `output/<company_name>/errors.log`.
- [ ] The `errors.log` file is created automatically if it does not exist when the first error is written.
- [ ] The presence of an HTML validation failure for one prospect does not abort processing of subsequent prospects.

---

#### F8 — Per-Prospect Error Isolation

**Priority:** Must-have  
**Description:** The main batch loop in `main.py` wraps each prospect's crew run in a `try/except` block. If a prospect's crew raises any unhandled exception (network error, API error, ChromaDB error, etc.), the error is caught, a one-line error message is appended to `output/<company_name>/errors.log`, and the loop continues with the next prospect. The utility prints a failure indicator for that prospect (e.g., `✗ Failed: <prospect_name> — see errors.log`) and continues.  
**User Story:** As an SDR (Mike), I want a batch of 10 prospects to finish even if 1 or 2 fail, so that I don't lose work on the successful ones due to an unrelated error.  
**Acceptance Criteria:**
- [ ] When one prospect's crew run raises a `RuntimeError` (simulated in a test), the loop continues and processes all remaining prospects without raising an unhandled exception at the top level.
- [ ] The error log entry for a failed prospect includes: the prospect domain, the exception class name, and a one-line excerpt of the exception message.
- [ ] After a batch completes, the summary line printed to stdout states the number of successes and failures (e.g., `3/4 presentations generated. 1 failed — see output/hiver/errors.log`).
- [ ] A successful prospect's HTML file is not overwritten or corrupted by a subsequent prospect's failure.
- [ ] The `output/<company_name>/` directory is created automatically by `main.py` before the loop if it does not already exist.

---

#### F9 — Configurable LLM Model via Environment Variable

**Priority:** Must-have  
**Description:** The LLM model used by all 4 CrewAI agents is set by the `OPENAI_MODEL` environment variable in `.env`. The default value (used if `OPENAI_MODEL` is not set) is `gpt-4o-mini`. The `.env.example` file documents this variable. Changing `OPENAI_MODEL` to any valid OpenAI model identifier (e.g., `gpt-4o`) requires no code changes — only an `.env` update.  
**User Story:** As a Technical Evaluator (Priya), I want to control which OpenAI model is used so that I can balance output quality against API cost for my team's budget.  
**Acceptance Criteria:**
- [ ] When `OPENAI_MODEL` is not present in `.env`, the utility runs using `gpt-4o-mini` for all 4 agents.
- [ ] When `OPENAI_MODEL=gpt-4o` is set in `.env`, the utility runs using `gpt-4o` for all 4 agents without any code change.
- [ ] The `.env.example` file contains `OPENAI_MODEL=gpt-4o-mini` with a comment explaining the variable.
- [ ] All 4 `ChatOpenAI` instantiations in `agents.py` read the model name from `os.environ.get("OPENAI_MODEL", "gpt-4o-mini")` (or equivalent) rather than a hardcoded string.

---

#### F10 — Output File Structure and Naming

**Priority:** Must-have  
**Description:** Each generated HTML presentation is written to `output/<company_name>/presentation_<prospect_name>.html`. The prospect name is derived from the domain by stripping the `www.` prefix and the TLD (e.g., `stripe.com` → `Stripe`, `notion.so` → `Notion`). Filenames are lowercased for the prospect component. The output directory is created automatically if it does not exist.  
**User Story:** As an SDR (Mike), I want output files to be consistently named and organised so that I can easily find the right deck for each prospect.  
**Acceptance Criteria:**
- [ ] After processing `stripe.com`, the file `output/<company_name>/presentation_stripe.html` exists on disk.
- [ ] After processing `notion.so`, the file `output/<company_name>/presentation_notion.html` exists on disk.
- [ ] After processing `www.freshdesk.com`, the file `output/<company_name>/presentation_freshdesk.html` exists on disk (the `www.` prefix is stripped).
- [ ] Running the utility twice for the same company and same prospect list overwrites existing output files without raising an error.
- [ ] The `output/<company_name>/` directory is created with `os.makedirs(..., exist_ok=True)` — the utility does not crash if the directory already exists.

---

#### F11 — Progress and Summary Printing

**Priority:** Must-have  
**Description:** During a batch run, `main.py` prints a progress line to stdout after each prospect completes (success or failure). After the full batch, a one-line summary is printed. No progress is printed to stderr except genuine error messages.  
**User Story:** As an SDR (Mike), I want to see the utility's progress while it runs so that I know it hasn't hung and can estimate when it will finish.  
**Acceptance Criteria:**
- [ ] After each successful prospect, the line `✓ Done: <prospect_name>` is printed to stdout.
- [ ] After each failed prospect, the line `✗ Failed: <prospect_name> — see errors.log` is printed to stdout.
- [ ] After all prospects are processed, a summary line of the form `N presentations generated in output/<company_name>/` is printed to stdout, where N is the count of successfully written files.
- [ ] When the knowledge base ingestion is skipped (files unchanged), the line `Knowledge base up to date` is printed to stdout before the prospect loop begins.
- [ ] When fresh ingestion runs, a line of the form `Ingested X chunks from Y files` is printed to stdout.

---

#### F12 — Environment Setup and README

**Priority:** Must-have  
**Description:** The repository includes a `.env.example` file with all required environment variables documented, and a `README.md` covering: installation (`pip install -r requirements.txt`), environment setup, knowledge base format guide, CLI usage, expected output, and a note on approximate cost per prospect.  
**User Story:** As a Technical Evaluator (Priya), I want complete setup documentation so that I can have the utility running in under 15 minutes from a fresh clone.  
**Acceptance Criteria:**
- [ ] `.env.example` contains entries for `OPENAI_API_KEY`, `TAVILY_API_KEY`, and `OPENAI_MODEL` with inline comments explaining each.
- [ ] `README.md` includes a "Quick Start" section with commands to clone, install dependencies, configure `.env`, populate `knowledge/<company>/`, and run the utility.
- [ ] `README.md` specifies that `--company` must exactly match the folder name under `knowledge/` (case-sensitive).
- [ ] `README.md` documents the knowledge base format: what files to place in `knowledge/<company>/`, recommended structure (e.g., `products.md`, `use_cases.md`), and that only `.md` files are ingested.
- [ ] `README.md` includes a cost estimate note: approximately $0.05–$0.15 per prospect at `gpt-4o-mini` rates (June 2026).
- [ ] `requirements.txt` is present and specifies `chromadb==1.5.9` (pinned exact version) and pinned versions for `crewai`, `langchain_openai`, `langchain_community`, `beautifulsoup4`, `requests`, and `tiktoken`.

---

#### F13 — `--dry-run` Cost Estimation Flag

**Priority:** Nice-to-have  
**Description:** An optional `--dry-run` flag causes the utility to print the number of prospects in `input/prospects.txt`, the estimated token usage per prospect, and the estimated total cost at current model rates — then exit without making any LLM or search API calls.  
**User Story:** As a Technical Evaluator (Priya), I want to see an estimated cost before committing API budget for a large batch.  
**Acceptance Criteria:**
- [ ] Running with `--dry-run` prints a cost estimate and exits with return code 0 without any calls to OpenAI, Tavily, or ChromaDB.
- [ ] The estimate includes: prospect count, estimated tokens per prospect, and estimated total cost in USD.

---

#### F14 — Gradio Web UI

**Priority:** Future  
**Description:** A Gradio interface hosted on Hugging Face Spaces that allows non-technical users to upload knowledge files, enter a list of prospect domains, and download generated HTML presentations via a browser — without any CLI or Python knowledge.  
**User Story:** As an SDR (Mike), I want a browser-based UI so that I don't need to run a terminal to use the utility.  
**Acceptance Criteria:**
- [ ] (Deferred — no acceptance criteria defined for v1)

---

## 5. User Flows

### Flow 1 — First Run (New Company, Fresh Knowledge Base)

```
User runs: python src/main.py --company hiver
  → main.py validates knowledge/hiver/ exists and contains .md files
  → .env loaded: OPENAI_API_KEY, TAVILY_API_KEY, OPENAI_MODEL read
  → Ingestion check: chroma_db/hiver/ is empty → ingest all .md files
      → Each file chunked at 500 tokens, 50-token overlap
      → Chunks embedded via text-embedding-3-small
      → Stored in ChromaDB collection "hiver_knowledge" with MD5 hash metadata
      → Prints: "Ingested 47 chunks from 3 files"
  → Reads input/prospects.txt → ["stripe.com", "notion.so", "freshdesk.com"]
  → For each prospect (e.g., stripe.com):
      → Derives prospect name: "Stripe"
      → Instantiates fresh Crew
      → Agent 1 (Researcher): 2–3 Tavily searches → research summary (≤1,500 tokens)
      → Agent 2 (Brand Analyst): scrapes stripe.com → extracts colours and fonts
          → If scraping fails → neutral fallback theme returned
      → Agent 3 (Value Prop Strategist): KnowledgeSearchTool queries ChromaDB
          → Top-5 relevant chunks returned → Agent maps to Stripe's pain points
      → Agent 4 (Presentation Designer): generates 10-slide HTML using research +
          brand theme + value props
      → HTML validation: BeautifulSoup counts <section> tags
          → If count != 10 → retry once with stricter prompt
          → If retry still invalid → write file anyway + log to errors.log
      → Writes output/hiver/presentation_stripe.html
      → Prints: "✓ Done: Stripe"
  → Prints: "3 presentations generated in output/hiver/"
```

### Flow 2 — Second Run (Knowledge Base Unchanged)

```
User runs: python src/main.py --company hiver (same files in knowledge/hiver/)
  → Ingestion check: MD5 hashes match stored hashes → skip ingestion
  → Prints: "Knowledge base up to date"
  → Proceeds directly to prospect loop
  → (same crew execution as Flow 1 for each prospect)
```

### Flow 3 — Knowledge Base Update

```
Maya edits knowledge/hiver/products.md (adds new feature section)
User runs: python src/main.py --company hiver
  → Ingestion check: MD5 of products.md differs from stored hash
  → Deletes existing chunks for products.md from ChromaDB
  → Re-ingests products.md only
  → Prints: "Re-ingested products.md (32 new chunks)"
  → Prints: "Knowledge base up to date" for unchanged files
  → Proceeds to prospect loop
```

### Flow 4 — Per-Prospect Error Isolation

```
User runs: python src/main.py --company hiver with 4 prospects
  → Prospect 1 (stripe.com): succeeds → "✓ Done: Stripe"
  → Prospect 2 (notion.so): Agent 1 raises APIConnectionError (Tavily unreachable)
      → Exception caught in try/except
      → Error appended to output/hiver/errors.log
      → Prints: "✗ Failed: Notion — see errors.log"
  → Prospect 3 (freshdesk.com): succeeds → "✓ Done: Freshdesk"
  → Prospect 4 (hubspot.com): succeeds → "✓ Done: Hubspot"
  → Prints: "3/4 presentations generated. 1 failed — see output/hiver/errors.log"
```

### Flow 5 — Brand Scraping Blocked (Cloudflare)

```
Agent 2 runs WebsiteThemeScraper for a Cloudflare-protected domain
  → requests.get() returns HTTP 403 (or redirect to challenge page)
  → except block catches non-200 response
  → Returns neutral fallback theme:
      {"primary_color": "#1a1a2e", "secondary_color": "#16213e",
       "background_color": "#ffffff", "font_family": "system-ui, sans-serif",
       "accent_color": "#0f3460"}
  → Agent 4 receives fallback theme → presentation generated with neutral palette
  → No exception propagated; no retry on scraping failure
```

---

## 6. Data Requirements

### Input Data

| Data | Source | Format | Freshness |
|------|--------|--------|-----------|
| Selling company knowledge base | User-maintained files in `knowledge/<company_name>/` | `.md` files (Markdown) | Stale until user updates files; MD5 change detection triggers re-ingestion automatically on next run |
| Prospect domain list | User-maintained file `input/prospects.txt` | Plain text, one domain per line | Current at run time; no caching — read fresh on every invocation |
| Prospect business intelligence | Tavily Search API (live web search) | Structured search result JSON (URL, title, content snippet) | Live at run time — fetched fresh per prospect per run |
| Prospect brand assets | Prospect's public homepage (HTTP GET) | Raw HTML + linked CSS stylesheets | Live at run time — fetched fresh per prospect per run |
| OpenAI API keys | User's `.env` file | Environment variable string | N/A — credentials, not data |
| Tavily API key | User's `.env` file | Environment variable string | N/A — credentials, not data |

### Stored Data

| Data | Storage | Location | Lifecycle |
|------|---------|---------|-----------|
| Embedded knowledge chunks | ChromaDB persistent (local disk) | `chroma_db/<company_name>/` | Persists across runs; updated incrementally via MD5 hash comparison; must be deleted manually before upgrading ChromaDB major version |
| Generated HTML presentations | Local filesystem | `output/<company_name>/presentation_<prospect>.html` | Written at run time; overwritten on re-run; not version-controlled by default |
| Error log | Local filesystem | `output/<company_name>/errors.log` | Appended on each run; not rotated automatically |

### Data Freshness Requirements

- **Prospect research:** Must be fetched live at run time. There is no caching of Tavily results between runs. An SDR running the same prospect twice on the same day will incur two Tavily API calls but may get slightly different results.
- **Knowledge base:** Stale-until-updated model. The utility does not poll for knowledge file changes; MD5 re-ingestion only triggers at startup when a new run is initiated.
- **Brand data:** Fetched live per run. There is no caching of scraped brand colours. If a prospect's site is temporarily down, the fallback neutral theme is used silently.

### Data Sensitivity

- `OPENAI_API_KEY` and `TAVILY_API_KEY` are sensitive credentials. They must not be committed to version control. `.gitignore` must include `.env`.
- Knowledge base files in `knowledge/<company_name>/` may contain proprietary product and competitive positioning information. The user is responsible for access control on the local filesystem.
- Generated HTML presentations may contain synthesised claims about a prospect's business. The user is responsible for reviewing content accuracy before using in outreach.

---

## 7. Non-Functional Requirements

### Performance

- **Single prospect, end-to-end:** Complete in under 60 seconds on a standard developer laptop (defined as: 8-core CPU, 16 GB RAM, standard residential broadband). This includes all 4 agent calls + Tavily searches + ChromaDB retrieval.
- **Batch of 10 prospects:** Complete in under 12 minutes (sequential processing, ~60s/prospect + overhead).
- **Knowledge base ingestion:** A knowledge base of 20 `.md` files totalling 50,000 tokens must ingest (chunk + embed + store) in under 60 seconds.
- **ChromaDB retrieval latency:** `KnowledgeSearchTool` must return top-5 results in under 2 seconds for a collection of up to 200 chunks.
- **Scraper timeout:** All `requests.get()` calls must complete or time out within 10 seconds. The utility must not block indefinitely on an unresponsive host.

### Security

- API keys (`OPENAI_API_KEY`, `TAVILY_API_KEY`) are loaded exclusively from `.env` via `python-dotenv`. They must never be hardcoded in source files.
- `.gitignore` must include `.env`, `chroma_db/`, and `output/` to prevent accidental commit of credentials or generated content.
- The utility does not authenticate users, implement access control, or log API keys to stdout/stderr. If an API key is invalid, the error from the upstream API (OpenAI or Tavily) is propagated to the per-prospect error handler without exposing the key value.
- The `WebsiteThemeScraper` makes outbound HTTP GET requests to prospect-controlled domains. The scraper does not follow more than 2 redirects and must not send any credentials or cookies to external domains.

### Scalability

- **v1 design limit:** Sequential processing of prospects supports batches up to approximately 100 prospects per run before hitting practical constraints (runtime ~100 minutes, Tavily free tier at 1,000 credits/month covering ~333 prospects/month at 3 searches/prospect).
- **ChromaDB collection size:** Designed for knowledge bases up to 500 chunks per company (~50 files of ~10 chunks each). Performance at this scale is well within ChromaDB embedded mode's supported range.
- **Multi-company isolation:** Multiple companies' knowledge bases are stored in separate ChromaDB collections (`<company_name>_knowledge`) and separate output directories. There is no cross-contamination. A single ChromaDB installation can host multiple companies.

### Reliability

- **Per-prospect error isolation:** A failure on any single prospect (API error, parsing error, ChromaDB error) must not terminate the batch. The `try/except` in `main.py` ensures the loop always completes. (See F8.)
- **HTML validation with 1 retry:** Agent 4 HTML structure failures trigger one automatic retry. (See F7.)
- **No recovery from mid-run crash:** If the Python process is killed during a run, partially written output files may be corrupt. The user must re-run from scratch. ChromaDB persistent data is safe (writes are transactional at the collection level).
- **Idempotency:** Running `main.py` twice with the same inputs produces functionally equivalent output (same structure, potentially different LLM-generated text). Existing output files are overwritten silently.
- **ChromaDB version pinning:** `requirements.txt` pins `chromadb==1.5.9` (or latest stable at implementation time) to prevent breaking changes from automatic upgrades. Upgrading ChromaDB major versions requires deleting the `chroma_db/` directory and re-running ingestion.

### Observability

- **LangFuse (optional, self-hosted):** When `LANGFUSE_PUBLIC_KEY` is set in `.env`, every prospect run is traced in LangFuse with one trace per prospect (`{company_name}/{prospect_name}`) and one span per agent.
- **What is captured:** full prompt/response for each agent, per-agent token counts and latency, auto-computed USD cost, and error status on failures.
- **Graceful degradation:** if LangFuse keys are absent or the self-hosted instance is unreachable, the pipeline continues normally without tracing — no crash, no warning.
- **Self-hosted setup:** LangFuse runs locally via `docker compose up -d`. No data leaves the user's machine.

---

## 8. Open Questions

These must be resolved during the Tech Spec stage (Stage 4).

| # | Question | Context | Decision Needed By |
|---|----------|---------|-------------------|
| Q1 | **Agent 1 output truncation mechanism:** How exactly is the ~1,500-token cap enforced before passing Agent 1's output as `context=` to Tasks 3 and 4? Options: (a) truncate raw string in `tasks.py` using `tiktoken`; (b) instruct Agent 1 via `expected_output` to write a max-1,500-token summary; (c) post-process with a token counter. | Plan.md decision #2. The plan defers to the spec. | Tech Spec |
| Q2 | **CrewAI v1.14.x crew instantiation per prospect:** Confirm whether instantiating a fresh `Crew` object for each prospect in the batch loop is the correct and performant pattern in v1.14.x, or whether there is a supported way to reset/re-run a single `Crew` instance. | Plan.md decision #3. CrewAI API changed significantly from 0.x to 1.x. | Tech Spec (M0 spike) |
| Q3 | **HTML `<section>` count validation scope:** The brief says "10 slides as `<section>` divs with full-viewport height". Clarify whether the count check should target `<section>` elements that are direct children of a specific container element (e.g., a `<main>` or `<div id="slides">` wrapper), or all `<section>` elements in the document. A document with a header `<section>` would fail the count otherwise. | Ambiguity in brief.md and plan.md. | Tech Spec |
| Q4 | **Neutral fallback theme exact values:** The fallback theme is referenced in F4 but the exact hex values are not specified in the brief. The PRD uses placeholder values (`#1a1a2e`, `#16213e`, etc.). Should the tech spec define the canonical fallback palette? | Product decision — affects visual quality of ~40–60% of prospects where scraping fails. | Tech Spec (or product owner input) |
| Q5 | **Google Fonts font name matching:** `WebsiteThemeScraper` detects fonts from `fonts.googleapis.com` URLs. Define the exact regex or parsing logic for extracting the font family name from URLs like `https://fonts.googleapis.com/css2?family=Inter:wght@400;600`. Should it extract `Inter`, `Inter:wght@400;600`, or the full `family=` parameter? | Impacts correctness of Agent 4's `<link>` tag injection. | Tech Spec |
| Q6 | **Prospect name derivation — edge cases:** The brief specifies stripping `www.` prefix and TLD. Define behaviour for: (a) multi-part TLDs (`freshdesk.com` → `Freshdesk` vs. `co.uk` domains); (b) numeric or hyphenated domain names; (c) subdomains other than `www.` (e.g., `app.notion.so`). | F10 acceptance criteria assume simple single-TLD domains. | Tech Spec |
| Q7 | **`errors.log` format:** Define the exact log line format for errors (timestamp? prospect domain? exception class + message? stack trace?). This affects debuggability for power users running large batches. | F8 specifies "exception class name and one-line excerpt" but does not specify timestamp or ordering. | Tech Spec |
| Q8 | **ChromaDB version at implementation time:** The plan pins `chromadb==1.5.9` (May 2026 release). Confirm this is still the latest stable release at implementation time or update the pin. | Technical dependency — affects `requirements.txt`. | Tech Spec (implementation phase) |

---

*End of PRD — SDR Presentation Utility v1.0*
