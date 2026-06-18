"""
test_tools.py — unit tests for src/tools.py.

Heavy deps (crewai, chromadb, langchain_openai) are patched at the conftest
level before any src import happens, so we can import tools directly here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# conftest.py has already inserted mock modules for crewai / chromadb /
# langchain_openai into sys.modules before this file is collected.
from knowledge_store import KnowledgeStore  # noqa: E402
from tools import (  # noqa: E402
    NEUTRAL_FALLBACK_THEME,
    WebsiteThemeScraper,
    KnowledgeSearchTool,
    extract_google_font_name,
)


# ===========================================================================
# extract_google_font_name
# ===========================================================================

class TestExtractGoogleFontName:
    def test_extract_google_font_name_css2_with_weight(self):
        url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;600"
        assert extract_google_font_name(url) == "Inter"

    def test_extract_google_font_name_css1_plus_encoded_space(self):
        url = "https://fonts.googleapis.com/css?family=Roboto+Condensed"
        assert extract_google_font_name(url) == "Roboto Condensed"

    def test_extract_google_font_name_open_sans_with_display_param(self):
        url = "https://fonts.googleapis.com/css2?family=Open+Sans&display=swap"
        assert extract_google_font_name(url) == "Open Sans"

    def test_extract_google_font_name_no_match_returns_none(self):
        url = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"
        assert extract_google_font_name(url) is None

    def test_extract_google_font_name_url_without_family_param_returns_none(self):
        url = "https://fonts.googleapis.com/earlyaccess/notosansjp.css"
        assert extract_google_font_name(url) is None

    def test_extract_google_font_name_protocol_relative_url(self):
        url = "//fonts.googleapis.com/css2?family=Lato:wght@300;400"
        assert extract_google_font_name(url) == "Lato"


# ===========================================================================
# WebsiteThemeScraper._run
# ===========================================================================

def _make_scraper():
    """Create scraper bypassing Pydantic/CrewAI BaseTool validation."""
    scraper = object.__new__(WebsiteThemeScraper)
    scraper.name = "WebsiteThemeScraper"
    scraper.description = "test"
    return scraper


class TestWebsiteThemeScraper:
    def test_website_theme_scraper_returns_json_with_all_keys(self):
        html = (
            "<html><head>"
            '<meta name="theme-color" content="#3c3c3c">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400">'
            "</head><body></body></html>"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status.return_value = None

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        scraper = _make_scraper()
        with patch("tools._make_session_with_redirects", return_value=mock_session):
            result_str = scraper._run("example.com")

        result = json.loads(result_str)
        assert set(result.keys()) == {
            "primary_color", "secondary_color", "background_color",
            "font_family", "accent_color",
        }
        assert result["font_family"] == "Inter"
        assert result["primary_color"] == "#3c3c3c"

    def test_website_theme_scraper_returns_fallback_on_connection_error(self):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.ConnectionError("connection refused")

        scraper = _make_scraper()
        with patch("tools._make_session_with_redirects", return_value=mock_session):
            result_str = scraper._run("down.example.com")

        result = json.loads(result_str)
        assert result == NEUTRAL_FALLBACK_THEME

    def test_website_theme_scraper_returns_fallback_on_http_403(self):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        scraper = _make_scraper()
        with patch("tools._make_session_with_redirects", return_value=mock_session):
            result_str = scraper._run("forbidden.example.com")

        result = json.loads(result_str)
        assert result == NEUTRAL_FALLBACK_THEME

    def test_website_theme_scraper_fills_missing_fields_from_fallback(self):
        """CSS with a single non-excluded colour; no Google Fonts. primary_color should
        come from CSS; other missing fields filled from NEUTRAL_FALLBACK_THEME."""
        html = (
            "<html><head>"
            '<link rel="stylesheet" href="/style.css">'
            "</head><body></body></html>"
        )
        css_content = "body { color: #1a73e8; }"

        main_response = MagicMock()
        main_response.status_code = 200
        main_response.text = html
        main_response.raise_for_status.return_value = None

        css_response = MagicMock()
        css_response.status_code = 200
        css_response.text = css_content

        mock_session = MagicMock()
        mock_session.get.side_effect = [main_response, css_response]

        scraper = _make_scraper()
        with patch("tools._make_session_with_redirects", return_value=mock_session):
            result_str = scraper._run("example.com")

        result = json.loads(result_str)
        assert result["primary_color"] == "#1a73e8"
        assert result["secondary_color"] == NEUTRAL_FALLBACK_THEME["secondary_color"]


# ===========================================================================
# KnowledgeSearchTool._run
# ===========================================================================

def _make_knowledge_tool(mock_store):
    tool = object.__new__(KnowledgeSearchTool)
    tool.name = "KnowledgeSearchTool"
    tool.description = "test"
    tool.knowledge_store = mock_store
    return tool


class TestKnowledgeSearchTool:
    def test_knowledge_search_tool_delegates_to_similarity_search(self, mock_knowledge_store):
        mock_knowledge_store.similarity_search.return_value = [
            "chunk A", "chunk B", "chunk C"
        ]
        tool = _make_knowledge_tool(mock_knowledge_store)
        result = tool._run("test query")

        assert "[Chunk 1]" in result
        assert "[Chunk 2]" in result
        assert "[Chunk 3]" in result
        assert "---" in result
        mock_knowledge_store.similarity_search.assert_called_once_with("test query", n_results=5)

    def test_knowledge_search_tool_returns_empty_message_when_no_chunks(self, mock_knowledge_store):
        mock_knowledge_store.similarity_search.return_value = []
        tool = _make_knowledge_tool(mock_knowledge_store)
        result = tool._run("query with no results")
        assert result == "No relevant knowledge base content found."

    def test_knowledge_search_tool_returns_error_message_on_exception(self, mock_knowledge_store):
        mock_knowledge_store.similarity_search.side_effect = RuntimeError("db error")
        tool = _make_knowledge_tool(mock_knowledge_store)
        result = tool._run("query that triggers error")
        assert result.startswith("Knowledge base search failed:")
