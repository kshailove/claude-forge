"""
test_main.py — unit tests for src/main.py utility functions.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import main  # noqa: E402
from main import (  # noqa: E402
    derive_prospect_name,
    validate_html_sections,
    format_error_line,
    format_section_warning,
    append_error_log,
)

# ---------------------------------------------------------------------------
# Fixed datetime for patching
# ---------------------------------------------------------------------------
FIXED_DT = datetime(2026, 6, 18, 10, 0, 0, tzinfo=timezone.utc)
FIXED_TS = "2026-06-18T10:00:00Z"


# ===========================================================================
# derive_prospect_name
# ===========================================================================

class TestDeriveProspectName:
    def test_derive_prospect_name_plain_domain(self):
        assert derive_prospect_name("stripe.com") == "Stripe"

    def test_derive_prospect_name_plain_two_label_tld(self):
        assert derive_prospect_name("notion.so") == "Notion"

    def test_derive_prospect_name_www_stripped(self):
        assert derive_prospect_name("www.freshdesk.com") == "Freshdesk"

    def test_derive_prospect_name_app_subdomain_stripped(self):
        assert derive_prospect_name("app.notion.so") == "Notion"

    def test_derive_prospect_name_go_subdomain_stripped(self):
        assert derive_prospect_name("go.gong.io") == "Gong"

    def test_derive_prospect_name_my_subdomain_stripped(self):
        assert derive_prospect_name("my.salesforce.com") == "Salesforce"

    def test_derive_prospect_name_hyphenated_stem(self):
        assert derive_prospect_name("open-ai.com") == "Open Ai"

    def test_derive_prospect_name_co_uk_tld_unaffected(self):
        assert derive_prospect_name("freshdesk.co.uk") == "Freshdesk"


# ===========================================================================
# validate_html_sections
# ===========================================================================

class TestValidateHtmlSections:
    def test_validate_html_sections_correct_count(self, html_10_sections):
        assert validate_html_sections(html_10_sections) == 10

    def test_validate_html_sections_wrong_count_eight(self):
        sections = "\n".join(f"    <section>Slide {i + 1}</section>" for i in range(8))
        html = f'<html><body><div class="slides">\n{sections}\n</div></body></html>'
        assert validate_html_sections(html) == 8

    def test_validate_html_sections_container_not_found(self, html_no_container):
        assert validate_html_sections(html_no_container) == -1

    def test_validate_html_sections_nested_sections_not_counted(self, html_nested_sections):
        # Only direct children should be counted — the 2 nested ones must not be counted
        assert validate_html_sections(html_nested_sections) == 10

    def test_validate_html_sections_custom_selector(self):
        sections = "\n".join(f"    <section>Slide {i + 1}</section>" for i in range(10))
        html = f'<html><body><main class="deck">\n{sections}\n</main></body></html>'
        assert validate_html_sections(html, container_selector="main.deck") == 10

    def test_validate_html_sections_malformed_html(self):
        html = '<div class="slides"><section>S1</section><section>S2'
        result = validate_html_sections(html)
        assert isinstance(result, int)


# ===========================================================================
# format_error_line
# ===========================================================================

class TestFormatErrorLine:
    def _patched(self):
        mock_dt = MagicMock()
        mock_dt.now.return_value = FIXED_DT
        return mock_dt

    def test_format_error_line_output_format(self):
        from unittest.mock import MagicMock
        exc = ValueError("something went wrong")
        mock_dt = MagicMock()
        mock_dt.now.return_value = FIXED_DT
        with patch("main.datetime", mock_dt):
            line = format_error_line("stripe.com", exc)
        assert line == f"{FIXED_TS} | stripe.com | ValueError | something went wrong"

    def test_format_error_line_message_truncated_at_200(self):
        from unittest.mock import MagicMock
        long_msg = "x" * 300
        exc = RuntimeError(long_msg)
        mock_dt = MagicMock()
        mock_dt.now.return_value = FIXED_DT
        with patch("main.datetime", mock_dt):
            line = format_error_line("example.com", exc)
        parts = line.split(" | ")
        assert len(parts[3]) == 200

    def test_format_error_line_multiline_message_uses_first_line_only(self):
        from unittest.mock import MagicMock
        exc = Exception("first line\nsecond line\nthird line")
        mock_dt = MagicMock()
        mock_dt.now.return_value = FIXED_DT
        with patch("main.datetime", mock_dt):
            line = format_error_line("example.com", exc)
        assert "second line" not in line
        assert "first line" in line


# ===========================================================================
# format_section_warning
# ===========================================================================

class TestFormatSectionWarning:
    def test_format_section_warning_both_counts_in_output(self):
        from unittest.mock import MagicMock
        mock_dt = MagicMock()
        mock_dt.now.return_value = FIXED_DT
        with patch("main.datetime", mock_dt):
            line = format_section_warning("example.com", 8, 7)
        assert "SECTION_COUNT_WARNING" in line
        assert "got 8" in line
        assert "retry produced 7" in line
        assert "example.com" in line

    def test_format_section_warning_different_counts_reported_separately(self):
        from unittest.mock import MagicMock
        mock_dt = MagicMock()
        mock_dt.now.return_value = FIXED_DT
        with patch("main.datetime", mock_dt):
            line = format_section_warning("test.com", 9, 9)
        assert "got 9" in line
        assert "retry produced 9" in line


# ===========================================================================
# append_error_log
# ===========================================================================

class TestAppendErrorLog:
    def test_append_error_log_creates_file_if_absent(self, tmp_path):
        log_path = str(tmp_path / "errors.log")
        append_error_log(log_path, "first line")
        assert Path(log_path).exists()
        assert Path(log_path).read_text() == "first line\n"

    def test_append_error_log_appends_to_existing_file(self, tmp_path):
        log_path = tmp_path / "errors.log"
        log_path.write_text("existing\n")
        append_error_log(str(log_path), "new line")
        content = log_path.read_text()
        assert "existing\n" in content
        assert "new line\n" in content

    def test_append_error_log_newline_always_appended(self, tmp_path):
        log_path = str(tmp_path / "errors.log")
        append_error_log(log_path, "no trailing newline in input")
        content = Path(log_path).read_text()
        assert content.endswith("\n")
