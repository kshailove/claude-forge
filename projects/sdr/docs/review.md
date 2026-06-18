# Code Review — SDR Presentation Utility

**Reviewer:** Code Review Agent (ClaudeForge Stage 6)  
**Date:** 2026-06-18  
**Verdict:** APPROVE_WITH_CHANGES  
**Issue counts:** 🔴 0 CRITICAL · 🟠 4 MAJOR · 🟡 5 MINOR · 🔵 3 SUGGESTION

---

## Review Summary

The codebase is well-structured, readable, and follows the two-phase crew pattern from the tech spec. Security posture is clean — no hardcoded secrets, all keys via env vars, `.gitignore` covers `.env`/`chroma_db/`/`output/`. Error handling is solid overall: tools never propagate exceptions, per-prospect isolation works, ChromaDB init errors are handled gracefully.

Four MAJOR issues require fixes before proceeding:

1. The `format_section_warning` function uses `count2` (the retry count) in its message but the code passes `count2` correctly — however the *first-attempt count* is silently lost from the log (minor information loss), and more critically, `count` vs `count2` inconsistency in log messages can mislead debugging.
2. Agent 3 (Value Prop Strategist) does not receive Agent 1's research via `context=` chaining as required by PRD acceptance criterion F5-AC3 — instead research is injected inline into the task description, which satisfies the intent but directly contradicts a checked acceptance criterion.
3. The `validate_html_sections` function signature in the codebase does not match the tech spec API contract — the spec defines `container_selector: str = "div.slides"` as a parameter; the implementation omits this parameter entirely and hardcodes the selector.
4. `_validate_and_maybe_retry` in `main.py` calls `from crew import run_for_prospect` inside the function body (a local import). While this avoids a circular import concern, it also means every call to this function re-executes the import machinery. More critically, `_validate_and_maybe_retry` is called *inside* the per-prospect `try/except` block — if `run_for_prospect` raises during the retry, the exception is caught by the inner `except Exception` in `_validate_and_maybe_retry` itself and swallowed, then the *first* (invalid) HTML is returned and written to disk without raising. This is the intended fallback behaviour per spec, so the logic is correct, but the exception is logged as a generic error line rather than a `SECTION_COUNT_WARNING`, making the log misleading.

---

## Issues

---

### 🟠 MAJOR — PRD F5-AC3: Agent 3 does not receive research via `context=` chaining

**Location:** `src/tasks.py:105–121`, `src/crew.py:177–179`  
**Issue:** PRD Section 4, F5 Acceptance Criterion 3 states: "Agent 3 receives Agent 1's task output via `context=[research_task]` in the CrewAI task definition." The implementation instead injects the truncated research directly into the `Task.description` string and passes no `context=` parameter to `make_value_prop_task`. The `Task` object created for Agent 3 has `context` entirely absent.  
**Why it matters:** This is a named PRD acceptance criterion that reviewers or testers will check. While the functional behaviour is equivalent (the research text reaches Agent 3 either way), a literal AC check against the generated task object will fail. If CrewAI 1.14.x `context=` handling is ever needed for trace/observability, it will not be wired up. It is also an undocumented deviation from the spec.  
**Recommendation:** The two-phase truncation pattern is the correct approach (and `context=` chaining cannot enforce the token cap). Update the PRD AC3 in the next revision to read: "Agent 3 receives Agent 1's research context via direct injection into the task description (≤1,500 tokens, tiktoken-enforced) rather than `context=` object chaining, to enforce the token cap deterministically." This is an approval gate item — either fix the AC or note the intentional deviation in `tasks.py` with a clear comment.

---

### 🟠 MAJOR — `format_section_warning` logs the wrong section count after retry

**Location:** `src/main.py:112–127`, `src/main.py:257`  
**Issue:** When both attempts produce invalid HTML, `_validate_and_maybe_retry` calls `format_section_warning(prospect_domain, count2)` — using the *retry* count only. The *first-attempt count* (`count`) is discarded. The log message therefore reads "Expected 10 sections, got {count2} (retry also produced {count2})" even when the two runs produced different counts (e.g., first attempt 8 sections, retry 7 sections). This is misleading: a user reading the log sees "retry also produced 7" without knowing the original attempt produced 8.  
**Why it matters:** The errors.log is the primary debugging artifact for production runs. Misleading section counts make it harder to assess whether the retry is helping.  
**Recommendation:** Change `format_section_warning` to accept both counts:
```python
def format_section_warning(domain: str, first_count: int, retry_count: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"{ts} | {domain} | SECTION_COUNT_WARNING | "
        f"Expected 10 sections, got {first_count} (retry produced {retry_count})"
    )
```
Update the call site at `main.py:257` to pass both `count` and `count2`.

---

### 🟠 MAJOR — `validate_html_sections` signature deviates from tech spec API contract

**Location:** `src/main.py:72–90`  
**Issue:** The tech spec Section 4.1 defines the function signature as:
```python
def validate_html_sections(html: str, container_selector: str = "div.slides") -> int:
```
The implementation omits the `container_selector` parameter entirely and hardcodes `soup.find("div", class_="slides")`. This is not a functional bug for v1 (the selector is always `div.slides`), but it breaks the published API contract and makes the function untestable with alternative selectors.  
**Why it matters:** The tech spec API contract is the interface expected by integration tests (Step 8 in the implementation order). If test code passes `container_selector="div.slides"` as specified, it will receive a `TypeError`. The spec's API contract documents an important extension point.  
**Recommendation:** Add the `container_selector` parameter with default value and use it in the implementation:
```python
def validate_html_sections(html: str, container_selector: str = "div.slides") -> int:
    ...
    tag, _, cls = container_selector.partition(".")
    container = soup.find(tag, class_=cls) if cls else soup.find(tag)
    ...
```
Or for v1, simply accept but ignore the parameter to avoid the `TypeError`.

---

### 🟠 MAJOR — `EXCLUDED_COLOURS` set contains redundant and incorrect entries

**Location:** `src/tools.py:61–66`  
**Issue:** The `EXCLUDED_COLOURS` set is defined as:
```python
EXCLUDED_COLOURS = {
    "#000000", "#000",
    "#ffffff", "#fff",
    "#FFFFFF", "#FFF",
    "#000000".lower(), "#ffffff".lower(),
}
```
The normalisation loop below converts all extracted colours to lowercase before checking `if norm not in EXCLUDED_COLOURS`. But `EXCLUDED_COLOURS` contains mixed-case entries (`"#FFFFFF"`, `"#FFF"`) that will *never* match the lowercased `norm`. The set also contains `"#000000".lower()` and `"#ffffff".lower()` which are the same as `"#000000"` and `"#ffffff"` already in the set. The effective check works (the lowercase forms are present), but the set has dead entries that create a false impression of correctness.

More importantly: the 3-digit forms `"#fff"` and `"#000"` are in the set but the regex `HEX_COLOUR_PATTERN` matches both 3- and 6-digit colours. The `norm = colour.lower()` step normalises captured colours but does not expand 3-digit forms. So `"#FFF"` extracted from CSS becomes `"#fff"` after normalisation — and IS excluded correctly. This part works. But a colour like `"#EEE"` (light grey, essentially white) is not excluded. This is an edge case, not a bug.  
**Why it matters:** The dead entries in `EXCLUDED_COLOURS` suggest the exclusion logic was written without fully reasoning through the normalisation flow. A future developer may trust the set definition and introduce a regression.  
**Recommendation:** Simplify the set to only the lowercase canonical forms that the normalised `norm` can actually match:
```python
EXCLUDED_COLOURS = {"#000000", "#000", "#ffffff", "#fff"}
```
Remove `"#FFFFFF"`, `"#FFF"`, and the `.lower()` duplicates.

---

### 🟡 MINOR — `main.py` progress lines missing Unicode tick/cross markers from spec

**Location:** `src/main.py:367`, `src/main.py:372`  
**Issue:** PRD F11 acceptance criteria specify progress lines:
- "✓ Done: {prospect_name}" 
- "✗ Failed: {prospect_name} — see errors.log"

The implementation prints:
- `f"Done: {prospect_name}"` (no ✓)
- `f"Failed: {prospect_name} — see errors.log"` (no ✗)

**Why it matters:** F11 AC1 and AC2 will fail a literal string-match check. The README also shows the ✓/✗ format. The visual differentiation is useful for SDRs scanning terminal output.  
**Recommendation:** Add the Unicode markers back:
```python
print(f"✓ Done: {prospect_name}")
print(f"✗ Failed: {prospect_name} — see errors.log")
```

---

### 🟡 MINOR — `main.py:334` prints "Knowledge base up to date" even when some files were ingested

**Location:** `src/main.py:334–341`  
**Issue:** The progress printing logic is:
```python
if result.ingested_files:
    print(f"Ingested {result.total_new_chunks} chunks from ...")
if result.skipped_files:
    print("Knowledge base up to date")
```
When a run ingests 1 new file AND skips 2 unchanged files, both branches execute. The output reads:
```
Ingested 12 chunks from 1 file(s): products.md
Knowledge base up to date
```
The second line is misleading — the knowledge base was NOT entirely up to date (one file was re-ingested). PRD F11-AC4 says: "When the knowledge base ingestion is skipped (files unchanged), the line `Knowledge base up to date` is printed." This implies the message should only appear when ALL files are skipped.  
**Recommendation:** Only print "Knowledge base up to date" if `not result.ingested_files`:
```python
if result.ingested_files:
    print(f"Ingested {result.total_new_chunks} chunks from {len(result.ingested_files)} file(s): ...")
elif result.skipped_files:
    print("Knowledge base up to date")
```

---

### 🟡 MINOR — `knowledge_store.py` error output goes to stdout instead of stderr

**Location:** `src/knowledge_store.py:65–74`  
**Issue:** Fatal errors in `KnowledgeStore.__init__` are printed with `print(..., flush=True)` (stdout). The spec and standard CLI conventions state that errors should go to `sys.stderr`. The `main.py` pattern for fatal errors consistently uses `print(..., file=sys.stderr)`.  
**Why it matters:** Scripts that capture stdout for processing will accidentally capture error messages. Log aggregators and CI pipelines typically distinguish stdout/stderr.  
**Recommendation:** Change both `print(...)` calls in the `except` block to `print(..., file=sys.stderr, flush=True)`.

---

### 🟡 MINOR — `README.md` Python version requirement inconsistency

**Location:** `README.md:44`  
**Issue:** The README states: "Python 3.10 or later". The tech spec (Section 2) pins `python_requires = ">=3.11,<3.14"` because CrewAI 1.14.7 and the dependency tree are best supported on 3.11+. A user running Python 3.10 may encounter subtle incompatibilities.  
**Why it matters:** Users following the README who install on Python 3.10 may hit dependency issues not caught by the README's guidance.  
**Recommendation:** Update README prerequisites to "Python 3.11 or later (3.11 recommended; 3.10 may work but is untested with this dependency set)."

---

### 🟡 MINOR — `_validate_and_maybe_retry` inner exception swallows retry failure with wrong log format

**Location:** `src/main.py:260–263`  
**Issue:** When the retry `run_for_prospect()` call itself raises an exception (e.g., API error during retry), the inner `except` block logs it as a generic error line via `format_error_line`. This appears in `errors.log` indistinguishable from a primary prospect failure, but the primary HTML was already generated and WILL be written to disk. A user reading the log will see what looks like a complete failure for that prospect, but actually has a file on disk.  
**Why it matters:** False alarm in the error log for a prospect that ultimately succeeded (with a potentially wrong slide count).  
**Recommendation:** Use a distinct log format prefix like `RETRY_ERROR` instead of re-using `format_error_line`:
```python
append_error_log(errors_log_path, 
    f"{ts} | {prospect_domain} | RETRY_ERROR | {str(retry_exc)[:200]}")
```

---

### 🔵 SUGGESTION — `KnowledgeSearchTool.knowledge_store` typed as `Any`

**Location:** `src/tools.py:274`  
**Issue:** The `knowledge_store` field is typed `Any` with the comment "KnowledgeStore — typed as Any to avoid Pydantic issues". This is a reasonable workaround for Pydantic v2 arbitrary type restrictions, but the comment does not explain *why* `KnowledgeStore` causes Pydantic issues or how to properly configure it.  
**Recommendation:** Add `model_config = ConfigDict(arbitrary_types_allowed=True)` to `KnowledgeSearchTool` and restore the proper type annotation. This is the idiomatic Pydantic v2 approach. If the CrewAI `BaseTool` base class prevents this, document the constraint explicitly.

---

### 🔵 SUGGESTION — Two-phase crew pattern creates duplicate LLM instance across phases

**Location:** `src/crew.py:144–175`  
**Issue:** `_build_llm()` is called once at line 144. The same `llm` instance is reused for both phase-1 agents (researcher, brand_analyst) and phase-2 agents (value_prop_strategist, presentation_designer). This is correct and efficient. However, the LangFuse `CallbackHandler` is also instantiated once (inside `_build_llm`). CrewAI 1.14.x may create separate internal LangChain chains per agent — if the callback handler is stateful (it tracks trace names), sharing it across 4 agents in 2 separate `Crew.kickoff()` calls may interleave trace spans under a single trace rather than creating clean per-agent spans.  
**Recommendation:** Verify during integration testing that LangFuse traces show 4 distinct spans when enabled. If spans interleave incorrectly, move `_build_llm()` to be called per-crew phase, or pass the handler through fresh `ChatOpenAI` instances for phase 2.

---

### 🔵 SUGGESTION — `_get_task_output` fallback uses `str(task.output)` which may include object repr noise

**Location:** `src/crew.py:201–220`  
**Issue:** If `task.output.raw` is `None` but `task.output` exists (some edge case in CrewAI 1.14.x), the fallback `str(output)` will return something like `<crewai.types.TaskOutput object at 0x...>` — useless as HTML input. Agent 4's HTML output would be silently lost.  
**Recommendation:** Add a log/warning when the fallback is triggered:
```python
if raw is not None:
    return str(raw)
# Fallback: log a warning before returning str(output)
import warnings
warnings.warn(f"task.output.raw is None; falling back to str(output). Check CrewAI version.")
return str(output)
```

---

## Review Checklist

### Spec Compliance
- [x] All 6 source modules match the tech spec component breakdown (Section 5)
- [x] `KnowledgeStore` interface matches spec Section 4.1 (run_ingestion_check, similarity_search, IngestResult)
- [x] `WebsiteThemeScraper` interface matches spec Section 4.1
- [x] `KnowledgeSearchTool` interface matches spec Section 4.1
- [x] `build_crew` / `run_for_prospect` signatures match spec Section 4.1
- [ ] `validate_html_sections` signature deviates from spec (missing `container_selector` param) — see MAJOR #3
- [x] Two-phase crew pattern implemented correctly per spec Section 5 (tasks.py)
- [x] tiktoken truncation at 1,500 tokens implemented in `crew.py:_truncate_to_tokens`
- [x] HTML validation + retry logic implemented in `main.py:_validate_and_maybe_retry`
- [x] LangFuse optional integration correctly guarded by env var presence
- [x] Neutral fallback theme canonical values match spec Section 5 (tools.py:27–33)
- [x] Google Fonts regex matches spec Section 5 pattern
- [x] `derive_prospect_name` algorithm matches spec Section 5 (KNOWN_STRIP_SUBDOMAINS, title-case)
- [x] ChromaDB MD5 change detection matches spec Section 5 algorithm
- [x] Chunking at 500 tokens / 50-token overlap matches spec
- [ ] PRD F5-AC3 (`context=[research_task]`) not met as written — see MAJOR #1

### Correctness
- [x] No obvious logic errors in chunking algorithm
- [x] `similarity_search` guards against `n_results > collection_count` (line 174–177)
- [x] `_scrape_theme` correctly falls back to NEUTRAL_FALLBACK_THEME on any exception
- [x] Section count validation uses `recursive=False` — only direct children counted
- [x] Prospect loop continues on exception (per-prospect isolation works)
- [x] `run_for_prospect` receives `strict=True` on retry — stricter prompt injected
- [ ] `format_section_warning` logs `count2` only, discarding `count` — see MAJOR #2
- [x] `_read_prospects` skips blank lines and comment lines (startswith "#")
- [x] `output_dir.mkdir(parents=True, exist_ok=True)` — correct idempotent directory creation
- [x] `errors_log_path` created automatically by `append_error_log`'s open("a") call

### Security
- [x] No API keys hardcoded in any source file
- [x] All API keys loaded from `.env` via `python-dotenv`
- [x] `.gitignore` includes `.env`, `chroma_db/`, `output/`
- [x] `WebsiteThemeScraper` sends no cookies or credentials to external domains
- [x] Max 2 redirects enforced on scraper session
- [x] CSS fetch uses 5-second timeout; homepage fetch uses 10-second timeout
- [x] API key values are not included in error messages (exception messages from OpenAI/Tavily do not echo keys)
- [x] LangFuse import is guarded with `try/except` — import failure is silently handled

### Code Quality
- [x] Functions are small and single-purpose throughout
- [x] Module structure matches spec (6 modules with clear responsibilities)
- [x] Naming is clear and consistent (snake_case throughout, descriptive names)
- [x] No dead code observed
- [x] Docstrings on all public functions and classes
- [ ] `EXCLUDED_COLOURS` has dead entries — see MAJOR #4
- [x] Constants are module-level, not magic inline values
- [x] `__init__.py` present in `src/` (correct package structure)

### Testability
- [x] `KnowledgeStore` accepts `persist_dir` — can be pointed at `EphemeralClient` surrogate in tests
- [x] `WebsiteThemeScraper._run` is a thin wrapper over `_scrape_theme` — mockable at `requests.get`
- [x] `derive_prospect_name` is a pure function — fully unit-testable
- [x] `validate_html_sections` is a pure function — fully unit-testable
- [x] `format_error_line` and `format_section_warning` are pure functions
- [x] `_truncate_to_tokens` is a pure function
- [x] `run_for_prospect` accepts `knowledge_store` as injection point — mockable
- [ ] `validate_html_sections` cannot be called with a custom `container_selector` as spec intends — see MAJOR #3

---

## Files Reviewed

| File | Lines | Assessment |
|------|-------|------------|
| `src/main.py` | 387 | Well-structured. 3 issues (2 MAJOR, 1 MINOR). |
| `src/knowledge_store.py` | 210 | Clean implementation. 1 MINOR (stdout vs stderr). |
| `src/tools.py` | 296 | Solid. 1 MAJOR (EXCLUDED_COLOURS). 1 SUGGESTION. |
| `src/agents.py` | 147 | Clean. No issues. |
| `src/tasks.py` | 185 | Correct two-phase implementation. 1 MAJOR (AC deviation). |
| `src/crew.py` | 221 | Clean two-phase pattern. 2 SUGGESTIONS. |
| `requirements.txt` | 10 | Matches spec exactly. |
| `.gitignore` | 15 | All required paths covered. |
| `.env.example` | 19 | Complete. All 6 variables documented. |
| `README.md` | 297 | Comprehensive. 1 MINOR (Python version). |

---

*Review complete. Verdict: APPROVE_WITH_CHANGES*  
*4 MAJOR issues must be resolved before proceeding to Stage 7 (test-write).*
