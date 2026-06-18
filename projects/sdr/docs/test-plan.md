# Test Plan — SDR Presentation Utility

**Version:** 1.0  
**Date:** 2026-06-18  
**Stage:** 7 — Test Write  
**Author:** Test-Write Agent (ClaudeForge)  
**Status:** Draft

---

## Overview

The test strategy focuses on unit-testing every pure function and tool method in isolation first, using `unittest.mock.patch` to prevent any network or disk I/O during the fast test suite. Integration tests cover the three scenarios where multiple components interact: fresh vs. cached ingestion, end-to-end crew execution with mocked external APIs, and the `--dry-run` CLI flag. All unit tests must pass without live API keys; integration tests are gated behind a `pytest.mark.integration` marker and require `OPENAI_API_KEY` and `TAVILY_API_KEY` to be present.

Target: ≥80% overall line coverage. Pure-function modules (`main.py` helpers, `tools.py` helpers, `knowledge_store._chunk_text`) target 100%.

---

## Unit Tests

### Summary Table

| Test file | Function / class under test | # test cases |
|---|---|---|
| `tests/test_main.py` | `derive_prospect_name` | 8 |
| `tests/test_main.py` | `validate_html_sections` | 6 |
| `tests/test_main.py` | `format_error_line` | 3 |
| `tests/test_main.py` | `format_section_warning` | 2 |
| `tests/test_main.py` | `append_error_log` | 3 |
| `tests/test_tools.py` | `extract_google_font_name` | 6 |
| `tests/test_tools.py` | `WebsiteThemeScraper._run` | 4 |
| `tests/test_tools.py` | `KnowledgeSearchTool._run` | 3 |
| `tests/test_knowledge_store.py` | `KnowledgeStore._chunk_text` | 5 |

---

### `tests/test_main.py`

#### `derive_prospect_name`

**Fixture / mock needed:** None (pure function).

---

**`test_derive_prospect_name_plain_domain`**  
Scenario: two-label domain with no subdomain.  
Input: `"stripe.com"` → Expected: `"Stripe"`  
Asserts: return value equals `"Stripe"`.

---

**`test_derive_prospect_name_plain_two_label_tld`**  
Scenario: domain with an uncommon TLD; no subdomain stripping should occur because there are only two labels.  
Input: `"notion.so"` → Expected: `"Notion"`  
Asserts: return value equals `"Notion"`.

---

**`test_derive_prospect_name_www_stripped`**  
Scenario: three-label domain whose first label is `"www"` — must be stripped.  
Input: `"www.freshdesk.com"` → Expected: `"Freshdesk"`  
Asserts: return value equals `"Freshdesk"`.

---

**`test_derive_prospect_name_app_subdomain_stripped`**  
Scenario: first label is `"app"`, which is in `KNOWN_STRIP_SUBDOMAINS`.  
Input: `"app.notion.so"` → Expected: `"Notion"`  
Asserts: return value equals `"Notion"`. Verifies `"app"` is not included in the result.

---

**`test_derive_prospect_name_go_subdomain_stripped`**  
Scenario: first label is `"go"`.  
Input: `"go.gong.io"` → Expected: `"Gong"`  
Asserts: return value equals `"Gong"`.

---

**`test_derive_prospect_name_my_subdomain_stripped`**  
Scenario: first label is `"my"`.  
Input: `"my.salesforce.com"` → Expected: `"Salesforce"`  
Asserts: return value equals `"Salesforce"`.

---

**`test_derive_prospect_name_hyphenated_stem`**  
Scenario: the company name stem itself contains a hyphen; the hyphen must be replaced with a space and each word title-cased.  
Input: `"open-ai.com"` → Expected: `"Open Ai"`  
Asserts: return value equals `"Open Ai"` (title-case per word).  
Note: this verifies the `.replace("-", " ").title()` step works on multi-word stems.

---

**`test_derive_prospect_name_co_uk_tld_unaffected`**  
Scenario: two-part TLD (`co.uk`) should not interfere — company name is in `labels[0]`.  
Input: `"freshdesk.co.uk"` → Expected: `"Freshdesk"`  
Asserts: return value equals `"Freshdesk"`.

---

#### `validate_html_sections`

**Fixtures needed:** Sample HTML strings (defined as module-level constants or pytest fixtures — see Fixtures section).

---

**`test_validate_html_sections_correct_count`**  
Scenario: HTML contains a `<div class="slides">` with exactly 10 direct `<section>` children.  
Mock: None (pure function over a string fixture).  
Asserts: return value equals `10`.

---

**`test_validate_html_sections_wrong_count_eight`**  
Scenario: HTML contains only 8 `<section>` children inside `<div class="slides">`.  
Asserts: return value equals `8`.

---

**`test_validate_html_sections_container_not_found`**  
Scenario: HTML has no `<div class="slides">` element at all.  
Asserts: return value equals `-1`.

---

**`test_validate_html_sections_nested_sections_not_counted`**  
Scenario: HTML has 10 direct `<section>` children inside `<div class="slides">`, plus 3 nested `<section>` elements inside those slides. Only direct children should be counted.  
Input: HTML where one slide contains a nested `<section>`.  
Asserts: return value equals `10` (not `13`).

---

**`test_validate_html_sections_custom_selector`**  
Scenario: caller passes `container_selector="main.deck"` and the HTML uses `<main class="deck">` as the container.  
Asserts: return value equals `10` when the correct container exists. Also verifies that passing the parameter does not raise `TypeError`.

---

**`test_validate_html_sections_malformed_html`**  
Scenario: HTML is a short malformed string (e.g. `"<div class='slides'><not valid xml"`) that still contains slides. Verifies that BeautifulSoup's fallback parser is invoked and does not raise.  
Input: Deliberately malformed HTML string with a `<div class="slides">` that BeautifulSoup can still partially parse.  
Asserts: return value is an integer (not an exception).

---

#### `format_error_line`

**Fixtures / mocks needed:** Patch `datetime.now` in `main` module to return a fixed UTC datetime so timestamp assertions are deterministic.

---

**`test_format_error_line_output_format`**  
Scenario: Standard exception with a single-line message.  
Setup: `exc = ValueError("Connection timeout")`. Patch `datetime.now` → fixed datetime `2026-06-18T10:00:00Z`.  
Asserts:
- Return value equals `"2026-06-18T10:00:00Z | stripe.com | ValueError | Connection timeout"`.
- Return value does not end with `"\n"`.

---

**`test_format_error_line_message_truncated_at_200`**  
Scenario: Exception message is longer than 200 characters.  
Setup: `exc = RuntimeError("x" * 300)`.  
Asserts: The message segment in the returned string is exactly 200 characters (the `[:200]` slice is applied).

---

**`test_format_error_line_multiline_message_uses_first_line_only`**  
Scenario: Exception message contains newline characters.  
Setup: `exc = OSError("first line\nsecond line\nthird line")`.  
Asserts: Returned string contains `"OSError | first line"` and does not contain `"second line"`.

---

#### `format_section_warning`

**Fixtures / mocks needed:** Patch `datetime.now` in `main` module to return a fixed UTC datetime.

---

**`test_format_section_warning_both_counts_in_output`**  
Scenario: Both `first_count` and `retry_count` must appear in the log line.  
Setup: `format_section_warning("notion.so", 8, 7)` with fixed datetime `2026-06-18T10:00:00Z`.  
Asserts:
- Return value contains `"SECTION_COUNT_WARNING"`.
- Return value contains `"got 8"`.
- Return value contains `"retry produced 7"`.
- Return value contains `"notion.so"`.

---

**`test_format_section_warning_different_counts_reported_separately`**  
Scenario: Verify that when first_count and retry_count are the same value, both still appear explicitly.  
Setup: `format_section_warning("stripe.com", 9, 9)`.  
Asserts: Return value contains `"got 9"` and `"retry produced 9"`.

---

#### `append_error_log`

**Fixtures needed:** `tmp_path` (built-in pytest fixture for a temporary directory).

---

**`test_append_error_log_creates_file_if_absent`**  
Scenario: Target log path does not exist before the call.  
Setup: `log_path = tmp_path / "errors.log"` (not created beforehand).  
Action: Call `append_error_log(str(log_path), "test line")`.  
Asserts: `log_path.exists()` is `True`; `log_path.read_text()` equals `"test line\n"`.

---

**`test_append_error_log_appends_to_existing_file`**  
Scenario: File already exists with one line; a second call appends without overwriting.  
Setup: Write `"first line\n"` to `log_path` before calling.  
Action: Call `append_error_log(str(log_path), "second line")`.  
Asserts: `log_path.read_text()` equals `"first line\nsecond line\n"`.

---

**`test_append_error_log_newline_always_appended`**  
Scenario: Verify the function always terminates the line with `"\n"`, even if the caller's line string already looks complete.  
Setup: Call `append_error_log(str(log_path), "single entry")`.  
Asserts: `log_path.read_text()` ends with `"\n"`.

---

### `tests/test_tools.py`

#### `extract_google_font_name`

**Fixtures / mocks needed:** None (pure function).

---

**`test_extract_google_font_name_css2_with_weight`**  
Scenario: URL with `css2` path and weight suffix.  
Input: `"https://fonts.googleapis.com/css2?family=Inter:wght@400;600"`  
Asserts: Return value equals `"Inter"`. Weight suffix `:wght@400;600` is stripped.

---

**`test_extract_google_font_name_css1_plus_encoded_space`**  
Scenario: Older `css` path with `+` encoding for space in multi-word font name.  
Input: `"https://fonts.googleapis.com/css?family=Roboto+Condensed"`  
Asserts: Return value equals `"Roboto Condensed"`. `+` is replaced with space.

---

**`test_extract_google_font_name_open_sans_with_display_param`**  
Scenario: URL with `display=swap` parameter after the family.  
Input: `"https://fonts.googleapis.com/css2?family=Open+Sans&display=swap"`  
Asserts: Return value equals `"Open Sans"`. The `&display=swap` suffix does not contaminate the name.

---

**`test_extract_google_font_name_no_match_returns_none`**  
Scenario: URL that does not reference `fonts.googleapis.com`.  
Input: `"https://cdn.example.com/styles/main.css"`  
Asserts: Return value is `None`.

---

**`test_extract_google_font_name_url_without_family_param_returns_none`**  
Scenario: URL that references `fonts.googleapis.com` but has no `family=` parameter.  
Input: `"https://fonts.googleapis.com/icon?family=Material+Icons"` — wait, this does have `family=`. Use instead: `"https://fonts.googleapis.com/earlyaccess/notosansjp.css"` (no `?family=` in query string).  
Asserts: Return value is `None`.

---

**`test_extract_google_font_name_protocol_relative_url`**  
Scenario: Protocol-relative URL (starts with `//`) — see tech-spec R4 note.  
Input: `"//fonts.googleapis.com/css2?family=Lato:wght@300;400"`  
Asserts: Return value equals `"Lato"`. Regex matches without `https:` prefix.

---

#### `WebsiteThemeScraper._run`

**Fixtures / mocks needed:** `unittest.mock.patch("tools.requests.Session.get")` (patches `requests.Session.get` inside the `tools` module). Alternatively patch `tools._make_session_with_redirects` to return a mock session.

---

**`test_website_theme_scraper_returns_json_with_all_keys`**  
Scenario: Successful scrape — `requests.Session.get` returns a minimal HTML page with a `<meta name="theme-color">` tag and a Google Fonts link.  
Mock: Patch `Session.get` to return a `Mock` with `status_code=200`, `.text` = HTML fixture containing `<meta name="theme-color" content="#3c3c3c">` and `<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400" rel="stylesheet">`. Also return `status_code=200` and empty text for any CSS fetches.  
Asserts:
- Return value is valid JSON (no `json.JSONDecodeError`).
- Parsed dict has all 5 keys: `"primary_color"`, `"secondary_color"`, `"background_color"`, `"font_family"`, `"accent_color"`.
- `"font_family"` equals `"Inter"` (Google Font detected).
- `"primary_color"` equals `"#3c3c3c"` (from `<meta theme-color>`).

---

**`test_website_theme_scraper_returns_fallback_on_connection_error`**  
Scenario: `requests.Session.get` raises `requests.exceptions.ConnectionError`.  
Mock: Patch `Session.get` to raise `requests.exceptions.ConnectionError("DNS failure")`.  
Asserts:
- Return value is valid JSON.
- Parsed dict equals `NEUTRAL_FALLBACK_THEME` exactly (the `_run` method's outer `try/except` catches the error).
- No exception propagates to the caller.

---

**`test_website_theme_scraper_returns_fallback_on_http_403`**  
Scenario: Server returns HTTP 403 (access denied). `raise_for_status()` raises `requests.exceptions.HTTPError`.  
Mock: Patch `Session.get` to return a `Mock` with `status_code=403` whose `.raise_for_status()` raises `requests.exceptions.HTTPError`.  
Asserts:
- Return value is valid JSON.
- Parsed dict equals `NEUTRAL_FALLBACK_THEME` exactly.

---

**`test_website_theme_scraper_fills_missing_fields_from_fallback`**  
Scenario: Scrape succeeds and detects a primary colour from CSS but no font and no secondary/accent colours (CSS has fewer than 2 distinct colours).  
Mock: Return a minimal HTML page with one linked stylesheet containing only one non-excluded hex colour (`"#1a73e8"`). No Google Fonts link. No `<meta theme-color>`.  
Asserts:
- `"primary_color"` equals `"#1a73e8"`.
- `"secondary_color"` equals `NEUTRAL_FALLBACK_THEME["secondary_color"]` (fallback applied).
- `"font_family"` equals `NEUTRAL_FALLBACK_THEME["font_family"]` (fallback applied).
- All 5 keys are present.

---

#### `KnowledgeSearchTool._run`

**Fixtures / mocks needed:** A mock `KnowledgeStore` object (created with `unittest.mock.MagicMock(spec=KnowledgeStore)`). The `similarity_search` method is configured per test.

---

**`test_knowledge_search_tool_delegates_to_similarity_search`**  
Scenario: `similarity_search` returns 3 chunks; verify the tool calls it with the correct arguments and formats the output.  
Mock: `mock_store.similarity_search.return_value = ["chunk A", "chunk B", "chunk C"]`.  
Action: Instantiate `KnowledgeSearchTool(knowledge_store=mock_store)` and call `._run("test research summary")`.  
Asserts:
- `mock_store.similarity_search` was called once with `("test research summary", n_results=5)`.
- Return value contains `"[Chunk 1]"`, `"[Chunk 2]"`, `"[Chunk 3]"`.
- Return value contains `"---"` separators between chunks.

---

**`test_knowledge_search_tool_returns_empty_message_when_no_chunks`**  
Scenario: `similarity_search` returns an empty list (collection is empty or query matched nothing).  
Mock: `mock_store.similarity_search.return_value = []`.  
Asserts: Return value equals `"No relevant knowledge base content found."`.

---

**`test_knowledge_search_tool_returns_error_message_on_exception`**  
Scenario: `similarity_search` raises an exception (e.g. ChromaDB connection error).  
Mock: `mock_store.similarity_search.side_effect = RuntimeError("ChromaDB unavailable")`.  
Asserts:
- Return value starts with `"Knowledge base search failed:"`.
- No exception propagates out of `_run`.

---

### `tests/test_knowledge_store.py`

#### `KnowledgeStore._chunk_text`

**Fixtures / mocks needed:** A `KnowledgeStore` instance is needed to call the private method. To avoid instantiating ChromaDB and OpenAI in unit tests, create the instance in a fixture that patches both `chromadb.PersistentClient` and `langchain_openai.OpenAIEmbeddings` so the constructor succeeds without any real connections.

Fixture `knowledge_store_instance` (session-scoped):
```python
@pytest.fixture
def knowledge_store_instance(monkeypatch):
    """Return a KnowledgeStore with mocked ChromaDB and embeddings."""
    with (
        patch("knowledge_store.chromadb.PersistentClient") as mock_client,
        patch("knowledge_store.OpenAIEmbeddings"),
        patch("knowledge_store.tiktoken.get_encoding") as mock_enc,
    ):
        mock_client.return_value.get_or_create_collection.return_value = MagicMock()
        # Use a real tiktoken encoder so _chunk_text logic is tested end-to-end
        import tiktoken as _tiktoken
        mock_enc.return_value = _tiktoken.get_encoding("cl100k_base")
        store = KnowledgeStore("testco", persist_dir="/tmp/test_chroma")
    return store
```

Note: if patching `tiktoken.get_encoding` causes issues, an alternative is to call `_chunk_text` directly on an already-constructed instance by patching at `__init__` time.

---

**`test_chunk_text_produces_correct_chunk_size`**  
Scenario: Input text that tokenises to exactly 1000 tokens. With chunk size 500 and overlap 50 (step 450), expect 3 chunks: tokens 0–499, 450–949, 900–999.  
Setup: Generate a string that encodes to exactly 1000 tokens using `tiktoken.get_encoding("cl100k_base")` (e.g. repeat a known token `N` times).  
Asserts:
- `len(chunks)` equals `3`.
- Decoded token count for each chunk is `≤500`.

---

**`test_chunk_text_overlap_is_correct`**  
Scenario: Verify that the tail of chunk N equals the head of chunk N+1 for a 50-token overlap.  
Setup: Tokenise a 600-token string. Chunk 1 covers tokens 0–499; chunk 2 covers tokens 450–599.  
Action: Re-encode the last 50 tokens of chunk 1 and the first 50 tokens of chunk 2.  
Asserts: Both produce the same token ids (the overlap region is identical).

---

**`test_chunk_text_empty_string_returns_empty_list`**  
Scenario: Edge case — empty string input.  
Input: `text = ""`.  
Asserts: Return value equals `[]`.

---

**`test_chunk_text_short_text_under_chunk_size_returns_one_chunk`**  
Scenario: Text that tokenises to fewer tokens than `CHUNK_SIZE` (e.g. 10 tokens).  
Asserts:
- Return value is a list of length `1`.
- The single chunk decodes to the original text (round-trip fidelity).

---

**`test_chunk_text_exact_chunk_size_returns_one_chunk`**  
Scenario: Text that tokenises to exactly `CHUNK_SIZE` (500) tokens.  
Asserts: Return value is a list of length `1` (no second chunk because `i` starts at 0, advances to 450, but `all_tokens[450:950]` has only 50 tokens — wait, this produces 2 chunks). Correct assertion: length is `2` (first chunk: tokens 0–499; second chunk: tokens 450–499, 50 tokens).  
Verifies the boundary condition at exactly `CHUNK_SIZE` tokens is handled without error.

---

## Integration Tests

Integration tests are marked `@pytest.mark.integration` and skipped unless `OPENAI_API_KEY` and `TAVILY_API_KEY` are set in the environment. They use real ChromaDB `EphemeralClient` (in-memory, no disk) and mock only external LLM/search API calls.

---

### INT-1 — Ingestion: fresh ChromaDB ingests, re-run skips

**Scenario:** Point `KnowledgeStore` at a temporary directory containing two small `.md` files. Call `run_ingestion_check` twice.

**Setup:**
- Create a `tmp_path` directory with `products.md` (50-word content) and `overview.md` (30-word content).
- Instantiate `KnowledgeStore("testco", persist_dir=str(tmp_path / "chroma"))` using `chromadb.EphemeralClient` by patching `chromadb.PersistentClient` to return `chromadb.EphemeralClient()`. Patch `OpenAIEmbeddings` to return deterministic fake embeddings (a mock that returns `[[0.1] * 1536]` per document).

**First call assertions:**
- `result.ingested_files` contains both filenames.
- `result.skipped_files` is empty.
- `result.total_new_chunks` is greater than 0.

**Second call (no file changes) assertions:**
- `result.ingested_files` is empty.
- `result.skipped_files` contains both filenames.
- `result.total_new_chunks` equals `0`.

**Modify one file, third call assertions:**
- `result.ingested_files` contains only the modified file.
- `result.skipped_files` contains the unmodified file.

---

### INT-2 — Full crew run with mocked OpenAI and Tavily returns valid HTML

**Scenario:** Call `run_for_prospect` with all external API calls mocked. Verify the returned string contains a `<div class="slides">` with 10 `<section>` elements.

**Setup:**
- Patch `langchain_openai.ChatOpenAI.__call__` (or the relevant `invoke` method) to return a fake `AIMessage` whose content is a fixture HTML string containing exactly 10 `<section>` elements inside `<div class="slides">`.
- Patch `langchain_community.tools.tavily_search.TavilySearchResults._run` to return a list of 3 fake search result dicts.
- Patch `tools.requests.Session.get` to return a fake response with the neutral fallback theme HTML.
- Use an in-memory `KnowledgeStore` (EphemeralClient) pre-populated with one chunk via direct `collection.add`.

**Assertions:**
- `run_for_prospect` returns a string (not `None`, not empty).
- `validate_html_sections(html)` equals `10`.
- The returned string contains the prospect name (e.g. `"Stripe"`) — confirms template substitution occurred.

---

### INT-3 — `--dry-run` flag exits 0 and prints cost estimate without touching ChromaDB

**Scenario:** Invoke the CLI via `subprocess.run` or `sys.argv` monkeypatching with `--dry-run` flag.

**Setup:**
- Create a minimal `knowledge/testco/products.md` file in a temporary directory.
- Create a minimal `input/prospects.txt` with two domains.
- Set `OPENAI_API_KEY=sk-fake-test` and `TAVILY_API_KEY=tvly-fake-test` in the subprocess environment.
- Run `python src/main.py --company testco --dry-run` from the `projects/sdr/code/` directory (or monkeypatch `sys.argv`).

**Assertions:**
- Exit code equals `0`.
- Captured stdout contains `"Dry run"`.
- Captured stdout contains `"Prospects: 2"`.
- Captured stdout contains `"Estimated total cost"`.
- The `chroma_db/` directory is not created (ChromaDB is never initialised).
- `KnowledgeStore.__init__` is not called (lazy import is not triggered before `sys.exit(0)`).

---

## Fixtures and Mocks

### pytest Fixtures

**`html_10_sections`** (module-scoped, in `conftest.py`):  
A complete HTML5 string with `<div class="slides">` containing exactly 10 `<section>` child elements. Each section has minimal content. Used by `validate_html_sections` tests and INT-2.

```python
HTML_10_SECTIONS = """<!DOCTYPE html>
<html><head><title>Test</title></head><body>
<div class="slides">
  <section>Slide 1</section>
  <section>Slide 2</section>
  <section>Slide 3</section>
  <section>Slide 4</section>
  <section>Slide 5</section>
  <section>Slide 6</section>
  <section>Slide 7</section>
  <section>Slide 8</section>
  <section>Slide 9</section>
  <section>Slide 10</section>
</div>
</body></html>"""
```

**`html_9_sections`** (module-scoped):  
Same structure as above but with only 9 `<section>` elements. Used to test wrong-count detection.

**`html_no_container`** (module-scoped):  
Valid HTML5 document with no `<div class="slides">` element at all (container entirely absent). Used to test the `-1` return path.

**`html_nested_sections`** (module-scoped):  
HTML with 10 direct `<section>` children plus 2 nested `<section>` elements inside `Slide 1`. Used to verify `recursive=False` behaviour.

**`sample_knowledge_md_content`** (module-scoped):  
A 200-word Markdown string simulating a company product description. Used in `_chunk_text` tests and INT-1.

**`mock_knowledge_store`** (function-scoped):  
A `MagicMock(spec=KnowledgeStore)` with `similarity_search` pre-configured to return `["chunk A", "chunk B", "chunk C", "chunk D", "chunk E"]`. Used in `KnowledgeSearchTool._run` tests.

**`knowledge_store_instance`** (function-scoped):  
A real `KnowledgeStore` object constructed with patched `chromadb.PersistentClient` and `OpenAIEmbeddings`. The tiktoken encoder is real (not mocked) so `_chunk_text` logic is exercised without modification. Used in `_chunk_text` unit tests.

---

### `unittest.mock.patch` Targets

| Target path | Used in |
|---|---|
| `knowledge_store.chromadb.PersistentClient` | `knowledge_store_instance` fixture, INT-1 |
| `knowledge_store.OpenAIEmbeddings` | `knowledge_store_instance` fixture, INT-1 |
| `tools.requests.Session.get` | `WebsiteThemeScraper._run` tests, INT-2 |
| `main.datetime` (to fix UTC timestamp) | `format_error_line` and `format_section_warning` tests |
| `langchain_openai.ChatOpenAI` | INT-2 |
| `langchain_community.tools.tavily_search.TavilySearchResults._run` | INT-2 |
| `crew.run_for_prospect` | Any test of `_validate_and_maybe_retry` that should not invoke the real crew |

---

## Commands

```bash
# Install test deps (add to requirements-dev.txt)
pip install pytest pytest-mock

# Run all tests
pytest tests/ -v

# Run only unit tests (fast, no network, no ChromaDB writes)
pytest tests/test_main.py tests/test_tools.py tests/test_knowledge_store.py -v

# Run only integration tests (requires OPENAI_API_KEY and TAVILY_API_KEY)
pytest tests/ -v -m integration

# Skip integration tests explicitly
pytest tests/ -v -m "not integration"

# Run with line coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run with HTML coverage report
pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# Run a single test function
pytest tests/test_main.py::test_derive_prospect_name_www_stripped -v

# Run all tests matching a keyword
pytest tests/ -v -k "derive_prospect_name"
```

---

## Coverage Targets

| Module / function | Target | Notes |
|---|---|---|
| `main.py::derive_prospect_name` | 100% | Pure function; 8 test cases cover all branches |
| `main.py::validate_html_sections` | 100% | Pure function; 6 test cases cover all 3 branches (`-1`, container found, nested section guard) |
| `main.py::format_error_line` | 100% | Pure function; 3 test cases cover format, truncation, and multi-line inputs |
| `main.py::format_section_warning` | 100% | Pure function; 2 test cases cover both-counts-present |
| `main.py::append_error_log` | 100% | 3 test cases cover file creation, append, and newline |
| `tools.py::extract_google_font_name` | 100% | Pure function; 6 test cases cover all 3 branches (match with weight, match without, no match) |
| `tools.py::WebsiteThemeScraper._run` (fallback path) | Covered | Covered by `test_website_theme_scraper_returns_fallback_on_connection_error` and the 403 test |
| `tools.py::KnowledgeSearchTool._run` | 100% | 3 test cases cover delegate path, empty result, and exception path |
| `knowledge_store.py::KnowledgeStore._chunk_text` | 100% | 5 test cases cover normal chunking, overlap, empty input, short input, exact-boundary input |
| **Overall line coverage** | **≥80%** | Crew, agents, and tasks modules are excluded from unit coverage but partially covered by INT-2 |

### Coverage exclusions

Add the following to `pyproject.toml` or `setup.cfg` to exclude files not targeted by unit tests:

```ini
[tool:pytest]
addopts = --cov-config=.coveragerc

# .coveragerc
[report]
exclude_lines =
    pragma: no cover
    if __name__ == .__main__.:
    raise SystemExit
    def main\(\)
```

Integration-only paths (`crew.py`, `agents.py`, `tasks.py`) are not excluded but will accrue coverage from INT-2 when integration tests are run. The ≥80% overall target is achievable from unit tests alone (unit test files cover the majority of `main.py`, `tools.py`, and `knowledge_store.py` line counts).

---

*End of Test Plan — SDR Presentation Utility v1.0*
