"""
main.py — CLI entry point for the SDR Presentation Utility.

Usage:
    python src/main.py --company <company_name>

Orchestrates: env validation -> knowledge ingestion -> prospect loop ->
HTML validation with retry -> file writing -> error isolation.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE_DIR = "knowledge"
INPUT_PROSPECTS_FILE = "input/prospects.txt"
OUTPUT_BASE_DIR = "output"
CHROMA_PERSIST_DIR = "chroma_db"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

KNOWN_STRIP_SUBDOMAINS = {"www", "app", "go", "my", "login", "signup", "portal"}


def derive_prospect_name(domain: str) -> str:
    """
    Derive a human-readable company name from a domain string.

    Algorithm:
      1. Lowercase and strip whitespace.
      2. Split on ".".
      3. If >= 3 labels and the first label is in KNOWN_STRIP_SUBDOMAINS, strip it.
      4. Take the leftmost remaining label as the stem.
      5. Replace hyphens with spaces and title-case.

    Examples:
      stripe.com         -> "Stripe"
      notion.so          -> "Notion"
      www.freshdesk.com  -> "Freshdesk"
      app.notion.so      -> "Notion"
      go.gong.io         -> "Gong"
      my.salesforce.com  -> "Salesforce"

    Args:
        domain: The prospect's domain string (may include subdomains).

    Returns:
        Title-cased company name string.
    """
    domain = domain.strip().lower()
    labels = domain.split(".")
    if len(labels) >= 3 and labels[0] in KNOWN_STRIP_SUBDOMAINS:
        labels = labels[1:]
    stem = labels[0]
    return stem.replace("-", " ").title()


def validate_html_sections(html: str, container_selector: str = "div.slides") -> int:
    """
    Count the number of direct <section> children of the slide container element.

    Args:
        html: The raw HTML string to parse.
        container_selector: CSS-style selector for the slide container, e.g. "div.slides".
            Must be in "tag.classname" or "tag" format.

    Returns:
        Number of direct <section> children, or -1 if the container is not found.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    tag, _, cls = container_selector.partition(".")
    container = soup.find(tag, class_=cls) if cls else soup.find(tag)
    if container is None:
        return -1
    return len(container.find_all("section", recursive=False))


def format_error_line(domain: str, exc: Exception) -> str:
    """
    Format a one-line error log entry.

    Format: {ISO8601_UTC} | {domain} | {ExceptionClass} | {message[:200]}

    Args:
        domain: The prospect domain that failed.
        exc: The exception that was raised.

    Returns:
        Formatted log line string (no trailing newline).
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    exc_class = type(exc).__name__
    message = str(exc).split("\n")[0][:200]
    return f"{ts} | {domain} | {exc_class} | {message}"


def format_section_warning(domain: str, first_count: int, retry_count: int) -> str:
    """
    Format a section count warning log entry after both generation attempts failed.

    Args:
        domain: The prospect domain.
        first_count: The <section> count from the first generation attempt.
        retry_count: The <section> count from the strict-prompt retry attempt.

    Returns:
        Formatted log line string (no trailing newline).
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"{ts} | {domain} | SECTION_COUNT_WARNING | "
        f"Expected 10 sections, got {first_count} (retry produced {retry_count})"
    )


def append_error_log(errors_log_path: str, line: str) -> None:
    """
    Append a line to the errors log file, creating it if necessary.

    Args:
        errors_log_path: Absolute or relative path to the errors.log file.
        line: The log line to append (a newline is added automatically).
    """
    with open(errors_log_path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _validate_environment() -> None:
    """
    Check that required environment variables are set. Exits with code 1 if not.
    """
    for key in ("OPENAI_API_KEY", "TAVILY_API_KEY"):
        if not os.environ.get(key):
            print(f"Error: {key} is required. Add it to your .env file.", file=sys.stderr)
            sys.exit(1)


def _validate_knowledge_dir(company_name: str) -> Path:
    """
    Validate that the knowledge directory exists and contains at least one .md file.

    Args:
        company_name: The company name from --company argument.

    Returns:
        Path to the knowledge directory.

    Raises:
        SystemExit: With code 1 if the directory is missing or empty.
    """
    knowledge_path = Path(KNOWLEDGE_BASE_DIR) / company_name
    if not knowledge_path.exists() or not knowledge_path.is_dir():
        print(
            f"Error: Knowledge directory '{knowledge_path}' does not exist. "
            f"Create it and add .md files before running.",
            file=sys.stderr,
        )
        sys.exit(1)

    md_files = list(knowledge_path.glob("*.md"))
    if not md_files:
        print(
            f"Error: No .md files found in '{knowledge_path}'. "
            "Add at least one Markdown file to the knowledge base.",
            file=sys.stderr,
        )
        sys.exit(1)

    return knowledge_path


def _read_prospects(company_name: str) -> list[str]:
    """
    Read the prospect domain list from input/prospects.txt.

    Args:
        company_name: Used only for error message context.

    Returns:
        List of domain strings (stripped, non-empty).

    Raises:
        SystemExit: With code 1 if the file does not exist or is empty.
    """
    prospects_path = Path(INPUT_PROSPECTS_FILE)
    if not prospects_path.exists():
        print(
            f"Error: Prospects file '{INPUT_PROSPECTS_FILE}' not found. "
            "Create it with one domain per line.",
            file=sys.stderr,
        )
        sys.exit(1)

    lines = [l.strip() for l in prospects_path.read_text(encoding="utf-8").splitlines()]
    domains = [l for l in lines if l and not l.startswith("#")]
    if not domains:
        print(
            f"Error: '{INPUT_PROSPECTS_FILE}' is empty or contains only comments.",
            file=sys.stderr,
        )
        sys.exit(1)

    return domains


def _validate_and_maybe_retry(
    html: str,
    prospect_domain: str,
    prospect_name: str,
    company_name: str,
    knowledge_store: object,
    errors_log_path: str,
) -> str:
    """
    Validate the section count and retry once with a strict prompt if needed.

    Args:
        html: The initial HTML output from Agent 4.
        prospect_domain: The prospect's domain.
        prospect_name: Human-readable prospect name.
        company_name: Selling company name.
        knowledge_store: The initialised KnowledgeStore.
        errors_log_path: Path to the errors log file.

    Returns:
        The validated (or best-available) HTML string.
    """
    from crew import run_for_prospect  # Local import to avoid circular dependencies

    count = validate_html_sections(html)
    if count == 10:
        return html

    # Retry once with strict=True
    try:
        html2 = run_for_prospect(
            prospect_domain, prospect_name, company_name, knowledge_store, strict=True
        )
        count2 = validate_html_sections(html2)
        if count2 == 10:
            return html2
        # Both failed — log warning and return first attempt
        warning = format_section_warning(prospect_domain, count, count2)
        append_error_log(errors_log_path, warning)
        return html  # Return the first attempt as-is
    except Exception as retry_exc:
        # Retry itself failed — log with RETRY_ERROR prefix and return first attempt
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        msg = str(retry_exc).split("\n")[0][:200]
        retry_line = f"{ts} | {prospect_domain} | RETRY_ERROR | {type(retry_exc).__name__}: {msg}"
        append_error_log(errors_log_path, retry_line)
        return html


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Main CLI entry point. Parses arguments, validates inputs, runs the pipeline.
    """
    parser = argparse.ArgumentParser(
        description="SDR Presentation Utility — generate personalised prospect decks."
    )
    parser.add_argument(
        "--company",
        required=True,
        help=(
            "Selling company name. Must match the folder name under knowledge/ "
            "(case-sensitive)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Print cost estimate and prospect count without making any API calls, "
            "then exit."
        ),
    )
    args = parser.parse_args()
    company_name: str = args.company

    # Load environment variables from .env
    load_dotenv()

    # Validate knowledge directory
    _validate_knowledge_dir(company_name)

    # Validate required env vars
    _validate_environment()

    # Read prospects file
    domains = _read_prospects(company_name)

    # Handle --dry-run
    if args.dry_run:
        est_tokens_per_prospect = 8000
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        est_cost_per_prospect = 0.05 if "mini" in model else 0.15
        total_est = len(domains) * est_cost_per_prospect
        print(f"Dry run — no API calls will be made.")
        print(f"  Prospects: {len(domains)}")
        print(f"  Model: {model}")
        print(f"  Estimated tokens/prospect: ~{est_tokens_per_prospect:,}")
        print(f"  Estimated cost/prospect: ~${est_cost_per_prospect:.2f}")
        print(f"  Estimated total cost: ~${total_est:.2f}")
        sys.exit(0)

    # Lazy import here to avoid loading heavy deps before dry-run check
    from knowledge_store import KnowledgeStore
    from crew import run_for_prospect

    # Initialise knowledge store and run ingestion check
    store = KnowledgeStore(company_name, persist_dir=CHROMA_PERSIST_DIR)
    knowledge_dir = str(Path(KNOWLEDGE_BASE_DIR) / company_name)
    print(f"Checking knowledge base for '{company_name}'...")
    result = store.run_ingestion_check(knowledge_dir)

    if result.ingested_files:
        print(
            f"Ingested {result.total_new_chunks} chunks from "
            f"{len(result.ingested_files)} file(s): "
            f"{', '.join(result.ingested_files)}"
        )
    elif result.skipped_files:
        print("Knowledge base up to date")

    # Set up output directory
    output_dir = Path(OUTPUT_BASE_DIR) / company_name
    output_dir.mkdir(parents=True, exist_ok=True)
    errors_log_path = str(output_dir / "errors.log")

    # Batch loop
    success_count = 0
    fail_count = 0
    total = len(domains)

    print(f"\nProcessing {total} prospect(s)...\n")

    for domain in domains:
        prospect_name = derive_prospect_name(domain)
        output_filename = f"presentation_{prospect_name.lower().replace(' ', '_')}.html"
        output_path = output_dir / output_filename

        try:
            html = run_for_prospect(domain, prospect_name, company_name, store)
            html = _validate_and_maybe_retry(
                html, domain, prospect_name, company_name, store, errors_log_path
            )
            output_path.write_text(html, encoding="utf-8")
            success_count += 1
            print(f"✓ Done: {prospect_name}")
        except Exception as exc:
            line = format_error_line(domain, exc)
            append_error_log(errors_log_path, line)
            fail_count += 1
            print(f"✗ Failed: {prospect_name} — see errors.log")

    # Summary
    print()
    if fail_count == 0:
        print(f"{success_count} presentations generated in {output_dir}/")
    else:
        print(
            f"{success_count}/{total} presentations generated. "
            f"{fail_count} failed — see {errors_log_path}"
        )


if __name__ == "__main__":
    main()
