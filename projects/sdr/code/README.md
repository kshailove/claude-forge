# SDR Presentation Utility

A multi-agent pipeline that generates personalised, brand-matched HTML sales presentations for B2B prospects. Given a list of prospect domains, it researches each company, extracts their brand colours, maps your product's capabilities to their pain points, and produces a self-contained 10-slide HTML deck.

---

## Quick Start

```bash
# 1. Clone the repository (or navigate to the project directory)
git clone <your-repo-url>
cd projects/sdr/code

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and fill in OPENAI_API_KEY and TAVILY_API_KEY

# 5. Add your product knowledge base
# (knowledge/hiver/products.md is a placeholder — replace with real content)

# 6. Add your target prospects
# Edit input/prospects.txt — one domain per line

# 7. Run a dry run to check your setup and estimate cost
python src/main.py --company hiver --dry-run

# 8. Generate presentations
python src/main.py --company hiver
```

Output HTML files are written to `output/hiver/presentation_<prospect>.html`.

---

## Prerequisites

- Python 3.11 or later (3.11 recommended)
- An [OpenAI API key](https://platform.openai.com/api-keys)
- A [Tavily Search API key](https://app.tavily.com) (free tier available)
- Docker (optional — only needed for LangFuse observability)

---

## Installation

### 1. Python dependencies

```bash
pip install -r requirements.txt
```

Key packages installed:

| Package | Version | Purpose |
|---|---|---|
| crewai | 1.14.7 | Multi-agent orchestration |
| langchain-openai | 0.3.16 | LLM and embedding client |
| langchain-community | 0.3.24 | Tavily search tool |
| chromadb | 1.5.9 | Local vector database |
| tiktoken | 0.7.0 | Token counting and truncation |
| requests / beautifulsoup4 / lxml | latest | Website scraping |
| python-dotenv | 1.0.1 | .env loading |
| langfuse | >=2.0.0 | Observability (optional) |

### 2. Environment variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI secret key |
| `TAVILY_API_KEY` | Your Tavily Search API key |

Optional variables:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model for all 4 agents |
| `LANGFUSE_PUBLIC_KEY` | (unset) | LangFuse public key (disables tracing if unset) |
| `LANGFUSE_SECRET_KEY` | (unset) | LangFuse secret key |
| `LANGFUSE_HOST` | `http://localhost:3000` | LangFuse server URL |

---

## Knowledge Base Format

The knowledge base is a directory of Markdown files located at `knowledge/<company_name>/`.

**Important:** The `--company` flag must exactly match the folder name under `knowledge/` — it is case-sensitive. For example, `--company hiver` reads from `knowledge/hiver/`.

### What files to place here

Only `.md` (Markdown) files are ingested. Place files covering:

| File | Contents |
|---|---|
| `products.md` | Product features, capabilities, integrations |
| `use_cases.md` | Customer use cases and success stories |
| `competitive.md` | Competitive positioning and differentiation |
| `pricing.md` | Pricing tiers, ROI metrics, proof points |

### How ingestion works

- On first run, all `.md` files are chunked (500-token chunks, 50-token overlap) and embedded using OpenAI `text-embedding-3-small`.
- On subsequent runs, files are re-ingested only if their MD5 hash has changed. Unchanged files are skipped — no redundant API calls.
- ChromaDB stores embeddings locally in `chroma_db/<company_name>/`.

### Example structure

```
knowledge/
  hiver/
    products.md
    use_cases.md
    competitive.md
    pricing.md
```

Write in plain Markdown. Use headings, bullet points, and tables. Include real metrics ("reduces response time by 60%") — Agent 3 retrieves these and cites them in value propositions.

---

## CLI Usage

### Basic run

```bash
python src/main.py --company <company_name>
```

All commands must be run from the `code/` directory (where `knowledge/`, `input/`, and `output/` are located).

### Dry run (no API calls)

```bash
python src/main.py --company hiver --dry-run
```

Prints prospect count, model, and estimated cost, then exits. No API calls are made.

### Adding prospects

Edit `input/prospects.txt`:

```
# One domain per line. Comments are ignored.
stripe.com
notion.so
freshdesk.com
www.hubspot.com    # www. prefix is stripped automatically
app.intercom.com   # app. prefix is stripped automatically
```

Domain name parsing rules:
- Known subdomain prefixes (`www`, `app`, `go`, `my`, `login`, `signup`, `portal`) are stripped automatically.
- The stem is title-cased: `stripe.com` becomes "Stripe", `go.gong.io` becomes "Gong".

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API secret key |
| `TAVILY_API_KEY` | Yes | — | Tavily search API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Model for all 4 agents. Use `gpt-4o` for higher quality. |
| `LANGFUSE_PUBLIC_KEY` | No | (unset) | LangFuse public key. Tracing is disabled when unset. |
| `LANGFUSE_SECRET_KEY` | No | (unset) | LangFuse secret key. |
| `LANGFUSE_HOST` | No | `http://localhost:3000` | LangFuse server URL. |

---

## LangFuse Observability

LangFuse provides a local dashboard to inspect every LLM call, token count, and latency per prospect run.

### Start the local LangFuse stack

```bash
docker compose up -d
```

This starts LangFuse and a PostgreSQL database. First launch may take 30–60 seconds.

### Configure

1. Open `http://localhost:3000` in your browser.
2. Create an account (local only).
3. Create a new project and copy the public/secret keys.
4. Add the keys to your `.env` file:

```dotenv
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

### Disable tracing

Leave `LANGFUSE_PUBLIC_KEY` unset (or remove it from `.env`). The pipeline runs normally without it — no errors, no warnings.

---

## Output Structure

```
output/
  <company_name>/
    presentation_stripe.html
    presentation_notion.html
    presentation_freshdesk.html
    errors.log              # created only if errors occurred
```

Each HTML file is a self-contained 10-slide presentation:
- All CSS is inline or in a `<style>` block — no external dependencies.
- Brand colours and fonts extracted from the prospect's live website are applied.
- Opens in any modern browser. No build step required.

The `errors.log` file (if present) contains one line per failure or warning, in the format:

```
2026-06-18T10:23:45Z | stripe.com | TimeoutError | Connection timed out after 10s
2026-06-18T10:31:02Z | notion.so | SECTION_COUNT_WARNING | Expected 10 sections, got 9 (retry also produced 9)
```

---

## Cost Estimate

Costs as of June 2026 (OpenAI pricing):

| Model | Estimated cost per prospect | Notes |
|---|---|---|
| `gpt-4o-mini` (default) | ~$0.05 | Recommended for batch runs |
| `gpt-4o` | ~$0.15 | Higher quality presentations |

These estimates include all 4 agent calls plus 5 ChromaDB embedding lookups per prospect. Actual costs vary with prospect research verbosity and knowledge base size.

Use `--dry-run` for an upfront estimate before processing a large batch.

---

## Troubleshooting

### "Error: Knowledge directory 'knowledge/hiver' does not exist"

The `--company` value must exactly match the folder name under `knowledge/`, including case. Check that `knowledge/hiver/` exists and contains at least one `.md` file.

### "Error: OPENAI_API_KEY is required"

Copy `.env.example` to `.env` and fill in your key. Ensure you're running from the `code/` directory so `.env` is found.

### ChromaDB dimension mismatch error

This happens when you upgrade ChromaDB and the stored embeddings are incompatible with the new version. Fix:

```bash
rm -rf chroma_db/
python src/main.py --company hiver
```

This re-ingests all knowledge base files. The embedding cost is minimal (< $0.01 for typical knowledge bases).

### Presentations have wrong number of slides

The pipeline automatically retries with a stricter prompt if the section count is not 10. If both attempts fail, the first attempt is saved and a warning is appended to `errors.log`. Open the HTML file — it will still be a usable presentation, just with a different slide count.

### Tavily returns no results for a prospect

Agent 1 is instructed to proceed with general industry context when Tavily finds nothing. The presentation will be less specific but still generated. Check `TAVILY_API_KEY` is set correctly if this happens for every prospect.

### Docker / LangFuse won't start

Ensure Docker Desktop is running and port 3000 is free:

```bash
lsof -i :3000
docker compose down && docker compose up -d
```

LangFuse first-launch database migrations take ~30 seconds. Wait before opening `http://localhost:3000`.
