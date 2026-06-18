"""
conftest.py — shared pytest fixtures for the SDR test suite.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Patch heavy dependencies that are not installed in test environment
# before any src module is imported.
_mock_chromadb = MagicMock()
_mock_openai_embeddings = MagicMock()
_mock_langchain_openai = MagicMock()
_mock_langchain_openai.OpenAIEmbeddings = _mock_openai_embeddings
_mock_crewai = MagicMock()
_mock_crewai_tools = MagicMock()

# Provide a plain-Python BaseTool so tools.py can define subclasses
_fake_base_tool_cls = type(
    "BaseTool",
    (),
    {"__init_subclass__": classmethod(lambda cls, **kw: None)},
)
_mock_crewai.tools.BaseTool = _fake_base_tool_cls
_mock_crewai_tools.BaseTool = _fake_base_tool_cls

sys.modules.setdefault("chromadb", _mock_chromadb)
sys.modules.setdefault("langchain_openai", _mock_langchain_openai)
sys.modules.setdefault("crewai", _mock_crewai)
sys.modules.setdefault("crewai.tools", _mock_crewai_tools)

from knowledge_store import KnowledgeStore  # noqa: E402


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

def _make_slides_html(n: int) -> str:
    sections = "\n".join(f'    <section>Slide {i + 1}</section>' for i in range(n))
    return f'<html><body><div class="slides">\n{sections}\n</div></body></html>'


@pytest.fixture
def html_10_sections() -> str:
    return _make_slides_html(10)


@pytest.fixture
def html_9_sections() -> str:
    return _make_slides_html(9)


@pytest.fixture
def html_no_container() -> str:
    return "<html><body><div class='deck'><section>S1</section></div></body></html>"


@pytest.fixture
def html_nested_sections() -> str:
    """10 direct sections + 2 nested inside the first section."""
    inner = "<section>Nested A</section><section>Nested B</section>"
    sections = [
        f"    <section>Slide {i + 1}{inner if i == 0 else ''}</section>"
        for i in range(10)
    ]
    return (
        '<html><body><div class="slides">\n'
        + "\n".join(sections)
        + "\n</div></body></html>"
    )


# ---------------------------------------------------------------------------
# KnowledgeStore fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def knowledge_store_instance():
    """
    A KnowledgeStore with chromadb and OpenAIEmbeddings patched out, but using
    a REAL tiktoken encoder so _chunk_text tests work correctly.
    """
    import tiktoken as _tiktoken
    import knowledge_store as _ks_module

    real_enc = _tiktoken.get_encoding("cl100k_base")

    mock_collection = MagicMock()
    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    with patch.object(_mock_chromadb, "PersistentClient", return_value=mock_client), \
         patch.object(_mock_langchain_openai, "OpenAIEmbeddings", return_value=MagicMock()), \
         patch("knowledge_store.tiktoken.get_encoding", return_value=real_enc):
        store = KnowledgeStore("test_company", persist_dir="/tmp/test_chroma")

    return store


@pytest.fixture
def mock_knowledge_store():
    """A MagicMock KnowledgeStore that returns 5 dummy chunks from similarity_search."""
    mock = MagicMock(spec=KnowledgeStore)
    mock.similarity_search.return_value = [
        "chunk one",
        "chunk two",
        "chunk three",
        "chunk four",
        "chunk five",
    ]
    return mock
