# Research Report — SDR Presentation Utility

**Date:** 2026-06-18
**Stage:** 1 — Research
**Project:** SDR Presentation Utility (projects/sdr)

---

## 1. Problem Space

### What problem is actually being solved?

Sales Development Representatives spend a disproportionate amount of their working time on pre-call preparation — researching the prospect's business, extracting their brand identity, and assembling a slide deck that feels personalised. Industry data from 2026 puts the cost at roughly 30 hours per rep per month just on content creation, or ~18,000 hours/year for a 50-person sales team. The output is usually a generic deck with a prospect's logo pasted in.

The SDR Presentation Utility collapses this into a fully automated pipeline: one CLI command produces a 10-slide HTML presentation that is genuinely tailored — it uses RAG over the selling company's knowledge base to map real capabilities to each prospect's specific pain points, and mirrors the prospect's own brand colours and fonts.

### Who has this problem and how painful is it?

- **Primary users:** SDRs and Account Executives at B2B SaaS companies
- **Pain level: High.** The manual workflow is error-prone, time-consuming, and produces low-quality output. Personalisation that goes beyond inserting a company name is rare at scale.
- **Secondary users:** Sales enablement / RevOps teams who want to codify seller knowledge into a reusable knowledge base

### What do users currently do instead?

1. **Google the prospect manually**, skim 3–5 pages, take notes
2. **Copy-paste into a slide template** in Google Slides or PowerPoint
3. **Manually adjust colours** or leave them generic
4. **Ask a designer/SE to help** for strategic accounts only
5. **Use a generic deck** for everyone else

---

## 2. Existing Solutions & Competitors

### Direct competitors (AI-powered sales deck tools)

| Tool | Strengths | Weaknesses | Gap |
|---|---|---|---|
| **Pitch** | Team collaboration, HubSpot CRM sync, engagement tracking | Cloud-only, no per-prospect brand scraping, generic AI | No RAG over your own knowledge base |
| **Beautiful.ai** | Auto-layout, brand guardrails, templates | No prospect research, no web scraping, output is PPTX not HTML | Requires all content pre-written |
| **Gamma** | Fast generation from a text prompt, clean output | No CRM integration, no brand extraction, one-size-fits-all | Not SDR-workflow aware |
| **Slidebean** | Founder-centric, auto-formats content | 2024 era AI, no prospect intelligence | No research agent |
| **Alai** | Context-aware narrative generation for sales | Cloud SaaS, opaque pipeline, vendor lock-in | No custom knowledge base |

### Adjacent tools (prospect research)

| Tool | Strengths | Weaknesses |
|---|---|---|
| **Apollo.io** | Deep contact data, signals | No presentation generation |
| **Clay** | Data enrichment, waterfall lookups | No slides, expensive |
| **Gong / Chorus** | Post-call intelligence | Not pre-call research |
| **6sense** | Intent data | No presentation layer |

### What gap does this project fill?

None of the above tools combine: (a) automated prospect research, (b) RAG over a custom selling company knowledge base, (c) brand colour/font extraction, and (d) self-hosted, code-level control — all in a single CLI utility producing a ready-to-open HTML file with zero cloud dependency beyond API calls.

---

## 3. Technology Landscape

### Agent Framework — CrewAI

**Current version:** 1.14.7 (June 11, 2026; released to PyPI)
**Python requirement:** >=3.10, <3.14

CrewAI is the right choice for this project. The 4-agent sequential pattern the brief specifies (Researcher → Brand Analyst → Value Prop Strategist → Presentation Designer) is exactly the role-based delegation model CrewAI was designed for.

**Strengths relevant to this project:**
- Sequential `Process` with `context=` task chaining is built-in and idiomatic
- Very low boilerplate vs LangGraph for a fixed linear workflow
- Custom tools integrate cleanly via the `BaseTool` decorator
- Active development; v1.x has stabilised the API substantially from earlier 0.x releases

**Known issues / things to watch:**
- Context window creep in long sequential chains: each task's output is concatenated into downstream task context. A verbose Agent 1 research summary can push Agent 4 close to GPT-4o's 128k input limit if not managed
- `context=` requires task objects (not strings); a common mistake is passing string descriptions instead of `Task` instances
- Default in-memory execution means a mid-run crash loses all prior agent outputs — acceptable for this CLI utility (just re-run), but worth noting
- Production crews can exhibit runaway tool retry loops if tool error handling is not explicit

**Alternatives considered and rejected:**
- **LangGraph** — more flexible but steeper learning curve; overkill for a fixed 4-step linear flow with no branching or human-in-the-loop requirements
- **AutoGen** — Microsoft has shifted it to maintenance mode (Feb 2026); community momentum is declining

### Vector Store — ChromaDB

**Current version:** 1.5.9 (May 5, 2026)
**Python requirement:** >=3.9

ChromaDB in embedded/persistent mode (`PersistentClient`) is the correct choice for a local CLI utility — zero infrastructure overhead, data persists to disk, cosine similarity is the default and suits semantic search well.

**Strengths:**
- Embedded mode requires no separate process to run
- Persistent storage to `./chroma_db/<company>` works exactly as the brief specifies
- `upsert` + metadata filtering (MD5 hash for change detection) is supported natively
- Collection isolation per company name is straightforward

**Known issues:**
- Schema migration is not backwards compatible on major upgrades: upgrading from <0.5.x to 1.x rewrites the persistent data format irreversibly. Pin the version in `requirements.txt`
- `chromadb` and `chromadb-client` are separate PyPI packages; accidentally installing `chromadb-client` instead of `chromadb` causes a `RuntimeError` on `PersistentClient` creation
- `InvalidDimensionException` will be thrown if the collection was previously created with a different embedding model dimension. If a user switches from one embedding model to another, they must delete the existing collection first
- Concurrent access to the same PersistentClient from multiple processes is not safe — not a concern here since the CLI is single-process

### Search — Tavily

**Current status:** Acquired by Nebius Group (February 2026) for up to $400M; API continues to operate under the Tavily brand
**Pricing (June 2026):**
- Free tier: 1,000 credits/month
- Basic search: 1 credit/request; Advanced search: 2 credits/request
- Rate limit: 100 RPM (free), 1,000 RPM (paid)
- Paid plans: $30/month (Researcher), $100/month (Startup, ~15,000 searches/month)

**Relevant notes:**
- `langchain_community.tools.tavily_search.TavilySearchResults` is the exact integration the brief specifies
- The `k` parameter controls max results returned; 3–5 results is appropriate for a research task
- The `TAVILY_API_KEY` env var is required; requests without it fail immediately
- The acquisition by Nebius introduces minor uncertainty about long-term pricing/availability, but the API is currently stable and has no announced changes

**Risk:** If a prospect domain is obscure or very new, Tavily may return sparse results. The agent prompt must handle empty or low-quality search results gracefully.

### LLM — OpenAI GPT-4o via `langchain_openai`

**Current GPT-4o pricing (June 2026):**
- Input: $2.50 / 1M tokens
- Output: $10.00 / 1M tokens
- Batch API: 50% discount for async workloads

**Note on the brief:** The brief specifies `GPT-4` but the current canonical model identifier is `gpt-4o`. As of June 2026, `gpt-4-turbo` and legacy `gpt-4` variants are still accessible but GPT-4o offers better price/performance. The implementation should use `gpt-4o` as the default model string, or make it configurable via `.env`.

**Cost estimation per prospect:**
- Agent 1 (research): ~2,000 tokens input + ~1,000 output ≈ $0.015
- Agent 2 (brand): ~500 input + ~200 output ≈ $0.003
- Agent 3 (value props): ~3,000 input (context + RAG chunks) + ~800 output ≈ $0.016
- Agent 4 (presentation): ~5,000 input + ~4,000 output ≈ $0.053
- **Rough total: ~$0.09/prospect** at standard GPT-4o rates

For a batch of 10 prospects, expect ~$0.90 per run. Acceptable.

### Embeddings — OpenAI `text-embedding-3-small`

**Pricing (June 2026):** $0.02 / 1M tokens
**Dimensions:** 1,536 (default), supports Matryoshka embedding (can reduce to 512 or 256)

For a typical knowledge base of 10–20 markdown files chunked at 500 tokens with 50-token overlap, total embedding cost at ingestion time will be well under $0.01. This is a negligible cost line.

The model is stable, performant, and the standard choice for RAG workloads. No meaningful alternative warrants consideration for this use case.

### Web Scraping — `requests` + `BeautifulSoup4`

**Current BeautifulSoup4 version:** 4.x (latest as of June 2026 per PyPI)
**requests:** 2.x (stable, widely used)

**Strengths for this use case:**
- Simple HTTP GET + HTML parse is sufficient for extracting CSS `<link>` tags and `<meta>` theme-color tags from homepages
- No JavaScript rendering required for static `<head>` content on most corporate sites
- Zero infrastructure overhead

**Critical known risk — anti-bot / Cloudflare:**
In 2026, a significant fraction (~40–60%) of SaaS company websites are protected by Cloudflare or similar CDN-based bot detection. Cloudflare's bot score system evaluates TLS fingerprint, HTTP/2 frame headers, Canvas rendering fingerprint, and behavioural signals. A plain `requests.get()` call:
- Will be blocked (HTTP 403 or redirect to challenge page) on Cloudflare-protected sites
- Will not execute JavaScript, so CSS loaded via JS (`styled-components`, `emotion`, CSS-in-JS) will not appear in the raw HTML response
- Will miss dynamically injected theme variables

**Mitigation strategy (within scope):** The `WebsiteThemeScraper` must:
1. Set a realistic `User-Agent` header mimicking a modern browser
2. Set `Accept`, `Accept-Language`, `Accept-Encoding` headers
3. Implement a `try/except` with a neutral fallback theme (as the brief already specifies)
4. Optionally, try fetching `https://<domain>/favicon.ico` or `<meta property="og:image">` as a colour extraction fallback via palette analysis

**What to avoid:** Do not attempt to bypass Cloudflare with headless browser automation in v1. The fallback neutral theme is the correct failure mode.

---

## 4. Integration Landscape

### Tavily Search API

- **Auth:** `TAVILY_API_KEY` in `.env` — straightforward
- **LangChain integration:** `from langchain_community.tools.tavily_search import TavilySearchResults` — well-documented, no known breaking changes in recent releases
- **Rate limits:** 100 RPM on free tier; the sequential crew runs 2–3 searches per prospect, so even the free tier comfortably handles a batch of 10 prospects
- **Data quality:** Tavily returns structured search results (URL, title, content snippet). The research agent should be prompted to synthesise across results rather than echo raw snippets
- **Gotcha:** The `include_raw_content=True` parameter returns full page text and increases credit usage to 2/request. Avoid for cost efficiency unless the snippet quality is insufficient

### OpenAI API (GPT-4o + text-embedding-3-small)

- **Auth:** `OPENAI_API_KEY` in `.env`
- **langchain_openai:** `ChatOpenAI` and `OpenAIEmbeddings` are the standard wrappers; both are well-maintained. The `model` parameter should be `"gpt-4o"` not `"gpt-4"` for current models
- **Rate limits:** Tier-dependent. A typical developer account (Tier 1) has 500 RPM and 300,000 TPM for GPT-4o. For a 10-prospect batch run sequentially, this is not a concern
- **Context window:** GPT-4o supports 128k input tokens. The main risk is Agent 4 receiving cumulative context from Agents 1, 2, and 3. A verbose Agent 1 summary (1,500–2,000 tokens) + 5 RAG chunks (500 tokens each) + brand data (200 tokens) = ~4,700 tokens of context, well within limits
- **Embeddings rate limit:** 1M TPM for `text-embedding-3-small` on most tiers. Not a concern for this ingestion volume

### ChromaDB (local embedded)

- **No API key required** — fully local
- **Persistence path:** `chroma_db/<company_name>/` — the brief's layout is clean
- **Collection isolation:** One collection per company (`<company_name>_knowledge`) prevents cross-contamination between different sellers
- **Change detection via MD5 hash:** Store the hash in ChromaDB document metadata; on startup, compute current file hash and compare. If different, delete + re-add the document chunks. This is the correct pattern

### BeautifulSoup4 / requests (scraping)

- **No API key required**
- **Dependency:** `lxml` is the recommended parser for performance; `html.parser` is built-in and sufficient as a fallback
- **CSS stylesheet fetching:** `<link rel="stylesheet" href="...">` may be relative or absolute. The scraper must resolve relative URLs using `urllib.parse.urljoin`
- **Font detection:** `Google Fonts` links (`https://fonts.googleapis.com/css2?family=...`) in `<link>` tags are a reliable font signal on modern corporate sites
- **Timeout handling:** `requests.get(url, timeout=10)` — always set a timeout to prevent hanging on slow/dead hosts

---

## 5. Risks & Unknowns

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Website scraping blocked by Cloudflare / anti-bot** | High (~50% of SaaS sites) | Medium — brand colours missing | Neutral fallback theme (already in spec). Add browser-like headers |
| **CSS loaded via JavaScript (CSS-in-JS / styled-components)** | Medium (~30% of modern sites) | Medium — colours not extractable from raw HTML | Fall back to `og:image` palette or neutral theme |
| **CrewAI context accumulation exceeding 128k token limit** | Low (for 4-agent sequential) | High — run fails mid-generation | Monitor token usage; truncate Agent 1 summary if > 2,000 tokens |
| **ChromaDB version migration breaking persistent data** | Low (if version is pinned) | Medium — re-ingestion required | Pin exact chromadb version in requirements.txt |
| **Tavily returning sparse/empty results for obscure prospects** | Medium | Medium — weak research summary | Agent 1 prompt must instruct graceful degradation |
| **GPT-4o generating non-parseable HTML** | Low (well-instructed LLM) | High — unusable output | Agent 4 prompt must specify exact HTML structure; include a validation pass |
| **OpenAI API outage during a run** | Low | Medium — partial output | Graceful error handling per-prospect; don't abort the whole batch on one failure |

### Product Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Value props are generic despite RAG** | Medium | High — defeats the purpose | Improve Agent 3 prompt to force specific product feature references from retrieved chunks |
| **Brand colours look wrong or clash** | Medium | Low-Medium — aesthetics issue | Limit palette to 2–3 colours; always provide a legible neutral fallback |
| **10-slide structure feels formulaic** | Medium | Low — users still save time vs manual | The spec already gives AI latitude on slide flow within guardrails |
| **Knowledge base content is poor quality** | Medium | High — garbage-in, garbage-out | Document the knowledge base quality requirements in README |

### What needs a spike before committing

1. **CSS extraction reliability:** Write a quick scraper test against 5–10 real SaaS homepages (stripe.com, notion.so, freshdesk.com, etc.) to measure how often raw HTML `<link>` + CSS gives usable colour data vs. how often it fails silently
2. **CrewAI context chaining in practice:** Verify that passing `context=[task1]` to task3 actually injects the right output text — the API behaviour changed between 0.x and 1.x; confirm with a minimal test

---

## 6. Recommended Direction

### Approach

Proceed with the tech stack exactly as specified in the brief. The choices are well-matched to the problem:

- **CrewAI 1.x sequential crew** is idiomatic for a fixed 4-agent linear pipeline
- **ChromaDB embedded persistent** is the right call for a local CLI with no infrastructure overhead
- **Tavily** for prospect research is the best search tool for agentic use in 2026 (designed for LLM agents, returns structured results, has a generous free tier)
- **OpenAI GPT-4o** (not legacy `gpt-4`) for generation, `text-embedding-3-small` for embeddings — both stable, well-priced
- **requests + BeautifulSoup4** for brand extraction with a well-specified fallback neutral theme

### Key decisions the planning stage should make

1. **Model string:** Confirm `gpt-4o` as the default (not `gpt-4`); make it configurable via `.env` or CLI arg so users can switch to `gpt-4o-mini` for cost savings
2. **CrewAI task output truncation:** Define a max token budget for Agent 1's output before it is passed as context to Agent 3 and Agent 4 (recommend 1,500 tokens max)
3. **Scraper header set:** Define the minimal browser-like header set for `requests` to maximise scrape success rate before falling back
4. **HTML output validation:** After Agent 4 produces the HTML string, add a lightweight parse step (e.g. `BeautifulSoup(html, 'html.parser')` to count `<section>` tags) to catch malformed output before writing to disk
5. **ChromaDB version pinning strategy:** Pin `chromadb==1.5.9` (or latest stable at implementation time) in `requirements.txt` and document the re-ingestion procedure for upgrades
6. **Error handling per prospect:** The main loop should `try/except` around each prospect's crew run and write a short error log rather than crashing the entire batch
7. **Cost guardrail (optional):** For users with tight API budgets, consider a `--dry-run` flag that reports how many prospects will be processed without running the LLM

### Summary

The technical architecture described in the brief is sound and implementable. The biggest implementation risk is the CSS/brand extraction failing silently on Cloudflare-protected sites — this is well-mitigated by the fallback theme already in the spec. The planning stage should focus on: prompt engineering for Agents 1 and 3 (research quality and value prop specificity are the core product differentiators), robust error handling in `main.py`, and a clean knowledge base format guide so SDRs know what to put in `knowledge/<company>/`.
