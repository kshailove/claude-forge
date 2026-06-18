"""
tools.py — Custom CrewAI BaseTool implementations.

WebsiteThemeScraper: Scrapes a prospect's homepage for brand colours and fonts.
KnowledgeSearchTool: Searches the selling company's ChromaDB knowledge base.
"""

from __future__ import annotations

import json
import re
from typing import Optional
from typing_extensions import TypedDict
import urllib.parse

import requests
from bs4 import BeautifulSoup
from crewai.tools import BaseTool
from pydantic import ConfigDict

from knowledge_store import KnowledgeStore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEUTRAL_FALLBACK_THEME: dict[str, str] = {
    "primary_color": "#2563eb",
    "secondary_color": "#1e40af",
    "background_color": "#ffffff",
    "font_family": "system-ui, -apple-system, sans-serif",
    "accent_color": "#f59e0b",
}

SCRAPER_HEADERS: dict[str, str] = {
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

GOOGLE_FONTS_PATTERN = re.compile(
    r'fonts\.googleapis\.com/css[^"\']*[?&]family=([^&:"\'>\s]+)'
)

# Hex colour regex — matches 3 or 6 hex digit colours
HEX_COLOUR_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

# Pure black and pure white to exclude (colours are normalised to lowercase before comparison)
EXCLUDED_COLOURS = {"#000000", "#000", "#ffffff", "#fff"}


class ThemeDict(TypedDict):
    """Brand theme dictionary returned by WebsiteThemeScraper."""

    primary_color: str
    secondary_color: str
    background_color: str
    font_family: str
    accent_color: str


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def extract_google_font_name(url: str) -> Optional[str]:
    """
    Extract a clean font family name from a Google Fonts CSS URL.

    Example:
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;600" -> "Inter"
        "https://fonts.googleapis.com/css?family=Roboto+Condensed"    -> "Roboto Condensed"
        "https://fonts.googleapis.com/css2?family=Open+Sans&display=swap" -> "Open Sans"

    Args:
        url: A URL string to inspect.

    Returns:
        The clean font family name, or None if no Google Fonts family is found.
    """
    match = GOOGLE_FONTS_PATTERN.search(url)
    if not match:
        return None
    raw_family = match.group(1)
    name_part = raw_family.split(":")[0]
    return name_part.replace("+", " ")


def _make_session_with_redirects(max_redirects: int = 2) -> requests.Session:
    """Create a requests.Session with a capped redirect limit."""
    session = requests.Session()
    session.max_redirects = max_redirects
    return session


# ---------------------------------------------------------------------------
# WebsiteThemeScraper
# ---------------------------------------------------------------------------

class WebsiteThemeScraper(BaseTool):
    """
    CrewAI tool that fetches a prospect's homepage and extracts brand theme data.

    Input: domain string (e.g. "stripe.com").
    Output: JSON-encoded ThemeDict with keys primary_color, secondary_color,
            background_color, font_family, accent_color.

    Never raises — returns NEUTRAL_FALLBACK_THEME on any error.
    """

    name: str = "WebsiteThemeScraper"
    description: str = (
        "Fetches a website's homepage and extracts brand colours and font "
        "families from CSS stylesheets and meta tags. Input: domain string "
        "(e.g. 'stripe.com'). Output: JSON string with keys primary_color, "
        "secondary_color, background_color, font_family, accent_color."
    )

    def _run(self, domain: str) -> str:
        """
        Scrape the prospect's homepage and extract brand theme data.

        Args:
            domain: The prospect's domain (e.g. "stripe.com").

        Returns:
            JSON string containing the ThemeDict. Returns NEUTRAL_FALLBACK_THEME on any error.
        """
        try:
            return self._scrape_theme(domain.strip())
        except Exception:
            return json.dumps(NEUTRAL_FALLBACK_THEME)

    def _scrape_theme(self, domain: str) -> str:
        """Internal scraping logic — may raise; caller must catch."""
        url = f"https://{domain}/"
        session = _make_session_with_redirects(max_redirects=2)

        try:
            response = session.get(
                url,
                headers=SCRAPER_HEADERS,
                timeout=10,
                allow_redirects=True,
            )
            response.raise_for_status()
        except Exception:
            return json.dumps(NEUTRAL_FALLBACK_THEME)

        html_text = response.text

        # Parse with lxml, fall back to html.parser
        try:
            soup = BeautifulSoup(html_text, "lxml")
        except Exception:
            soup = BeautifulSoup(html_text, "html.parser")

        theme: dict[str, str] = {}

        # --- Step 3: <meta name="theme-color"> ---
        meta_theme = soup.find("meta", attrs={"name": "theme-color"})
        if meta_theme and meta_theme.get("content", "").startswith("#"):
            theme["primary_color"] = meta_theme["content"].strip()

        # --- Step 8: Google Fonts check (before CSS fetch) ---
        font_family: Optional[str] = None
        for link_tag in soup.find_all("link"):
            href = link_tag.get("href", "")
            gf_name = extract_google_font_name(href)
            if gf_name:
                font_family = gf_name
                break

        # --- Steps 4–8: Fetch and parse linked stylesheets ---
        css_texts: list[str] = []
        for link_tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r):
            href = link_tag.get("href", "")
            if not href or "fonts.googleapis.com" in href:
                continue
            abs_url = urllib.parse.urljoin(f"https://{domain}", href)
            try:
                css_resp = session.get(
                    abs_url,
                    headers=SCRAPER_HEADERS,
                    timeout=5,
                    allow_redirects=True,
                )
                if css_resp.status_code == 200:
                    css_texts.append(css_resp.text)
            except Exception:
                continue  # Skip this CSS file, keep going

        combined_css = "\n".join(css_texts)

        # --- Step 6: Extract hex colours from CSS ---
        hex_colours = HEX_COLOUR_PATTERN.findall(combined_css)
        # Normalise to lowercase and filter out pure black/white
        distinct_colours: list[str] = []
        seen: set[str] = set()
        for colour in hex_colours:
            norm = colour.lower()
            if norm not in EXCLUDED_COLOURS and norm not in seen:
                seen.add(norm)
                distinct_colours.append(colour)

        if "primary_color" not in theme and len(distinct_colours) >= 1:
            theme["primary_color"] = distinct_colours[0]
        if len(distinct_colours) >= 2:
            theme["secondary_color"] = distinct_colours[1]
        if len(distinct_colours) >= 3:
            theme["accent_color"] = distinct_colours[2]

        # --- Step 7: background-color from CSS ---
        bg_match = re.search(
            r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})", combined_css
        )
        if bg_match:
            theme["background_color"] = bg_match.group(1)

        # --- Step 8 continued: font-family from CSS if no Google Fonts ---
        if not font_family:
            font_match = re.search(
                r"font-family\s*:\s*[\"']?([^;\"']+)", combined_css
            )
            if font_match:
                font_family = font_match.group(1).strip().strip("\"'")

        if font_family:
            theme["font_family"] = font_family

        # --- Step 9: Fill missing fields from NEUTRAL_FALLBACK_THEME ---
        for key, fallback_val in NEUTRAL_FALLBACK_THEME.items():
            if not theme.get(key):
                theme[key] = fallback_val

        return json.dumps(theme)


# ---------------------------------------------------------------------------
# TavilyWebSearch
# ---------------------------------------------------------------------------

class TavilyWebSearch(BaseTool):
    """
    CrewAI-native wrapper around LangChain's TavilySearchResults.

    Input: search query string.
    Output: formatted string of search results.
    """

    name: str = "TavilyWebSearch"
    description: str = (
        "Search the web for recent information about a company, product, or topic. "
        "Input: a focused search query string."
    )
    k: int = 3

    def _run(self, query: str) -> str:
        from langchain_community.tools.tavily_search import TavilySearchResults
        results = TavilySearchResults(k=self.k).run(query)
        return str(results)


# ---------------------------------------------------------------------------
# KnowledgeSearchTool
# ---------------------------------------------------------------------------

class KnowledgeSearchTool(BaseTool):
    """
    CrewAI tool that performs semantic search over the selling company's ChromaDB collection.

    Input: research summary string.
    Output: formatted string of top-5 knowledge chunks, separated by "---".
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "KnowledgeSearchTool"
    description: str = (
        "Searches the selling company's knowledge base for content relevant "
        "to a prospect's pain points. Input: research summary string. "
        "Output: formatted string of top-5 knowledge chunks."
    )
    knowledge_store: KnowledgeStore

    def _run(self, research_summary: str) -> str:
        """
        Search the knowledge base for chunks relevant to the research summary.

        Args:
            research_summary: The prospect research text to query against.

        Returns:
            Formatted string of up to 20 chunks, or a fallback message if empty.
        """
        try:
            chunks = self.knowledge_store.similarity_search(research_summary, n_results=20)
        except Exception as exc:
            return f"Knowledge base search failed: {exc}"

        if not chunks:
            return "No relevant knowledge base content found."

        parts = [f"[Chunk {i + 1}]\n{chunk}" for i, chunk in enumerate(chunks)]
        return "\n\n---\n\n".join(parts)
