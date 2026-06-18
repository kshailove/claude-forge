"""
test_knowledge_store.py — unit tests for KnowledgeStore._chunk_text.

conftest.py patches chromadb / langchain_openai before import.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import tiktoken

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_real_enc = tiktoken.get_encoding("cl100k_base")

from knowledge_store import KnowledgeStore  # noqa: E402


# ===========================================================================
# KnowledgeStore._chunk_text
# ===========================================================================

class TestChunkText:
    """Tests for KnowledgeStore._chunk_text using the knowledge_store_instance fixture."""

    def test_chunk_text_empty_string_returns_empty_list(self, knowledge_store_instance):
        result = knowledge_store_instance._chunk_text("")
        assert result == []

    def test_chunk_text_short_text_under_chunk_size_returns_one_chunk(self, knowledge_store_instance):
        enc = _real_enc
        # Build a small text (well under 500 tokens)
        text = "hello world this is a short text snippet"
        result = knowledge_store_instance._chunk_text(text)
        assert len(result) == 1
        assert result[0] == text

    def test_chunk_text_produces_correct_chunk_size(self, knowledge_store_instance):
        # Build exactly 1000-token text
        enc = _real_enc
        word = "hello "
        big_text = ""
        while len(enc.encode(big_text)) < 1000:
            big_text += word
        tokens_1000 = enc.encode(big_text)[:1000]
        text_1000 = enc.decode(tokens_1000)

        result = knowledge_store_instance._chunk_text(text_1000)
        # step = CHUNK_SIZE - CHUNK_OVERLAP = 500 - 50 = 450
        # chunks start at: 0, 450, 900 → 3 chunks
        assert len(result) == 3
        for chunk in result:
            assert len(enc.encode(chunk)) <= 500

    def test_chunk_text_overlap_is_correct(self, knowledge_store_instance):
        # Build exactly 600 tokens
        enc = _real_enc
        word = "hello "
        big_text = ""
        while len(enc.encode(big_text)) < 600:
            big_text += word
        tokens_600 = enc.encode(big_text)[:600]
        text_600 = enc.decode(tokens_600)

        result = knowledge_store_instance._chunk_text(text_600)
        # chunk 0: tokens[0:500], chunk 1: tokens[450:600]
        assert len(result) >= 2

        enc0 = enc.encode(result[0])
        enc1 = enc.encode(result[1])

        # tail of chunk 0 (last 50 tokens) == head of chunk 1 (first 50 tokens)
        tail_of_0 = enc0[-50:]
        head_of_1 = enc1[:50]
        assert tail_of_0 == head_of_1

    def test_chunk_text_exact_chunk_size_returns_two_chunks(self, knowledge_store_instance):
        # Exactly 500 tokens
        enc = _real_enc
        word = "hello "
        big_text = ""
        while len(enc.encode(big_text)) < 500:
            big_text += word
        tokens_500 = enc.encode(big_text)[:500]
        text_500 = enc.decode(tokens_500)

        result = knowledge_store_instance._chunk_text(text_500)
        # chunk 0: tokens[0:500] (500 tokens)
        # next start: i=450, chunk 1: tokens[450:500] (50 tokens)
        assert len(result) == 2
        assert len(enc.encode(result[0])) == 500
        assert len(enc.encode(result[1])) == 50
