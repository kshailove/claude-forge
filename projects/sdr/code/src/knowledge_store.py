"""
knowledge_store.py — ChromaDB wrapper for incremental knowledge base ingestion and semantic search.

Uses MD5 hash-based change detection to avoid redundant re-embeddings.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import chromadb
import tiktoken
from langchain_openai import OpenAIEmbeddings


CHUNK_SIZE = 500      # tokens
CHUNK_OVERLAP = 50    # tokens


@dataclass
class IngestResult:
    """Result returned by KnowledgeStore.run_ingestion_check()."""

    ingested_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    total_new_chunks: int = 0


class KnowledgeStore:
    """
    Wraps ChromaDB for incremental knowledge base ingestion and cosine similarity search.

    Each company gets its own persistent ChromaDB collection at
    ``persist_dir/<company_name>/`` named ``<company_name>_knowledge``.
    """

    def __init__(self, company_name: str, persist_dir: str = "chroma_db") -> None:
        """
        Initialise (or open) the ChromaDB PersistentClient and get/create the collection.

        Args:
            company_name: The selling company name (e.g. "hiver").
            persist_dir: Root directory for ChromaDB persistence. Defaults to "chroma_db".

        Raises:
            SystemExit: If ChromaDB raises InvalidDimensionException or cannot be opened.
        """
        self.company_name = company_name
        self.collection_name = f"{company_name}_knowledge"
        db_path = str(Path(persist_dir) / company_name)

        try:
            self._client = chromadb.PersistentClient(path=db_path)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            if "InvalidDimensionException" in type(exc).__name__ or "dimension" in str(exc).lower():
                print(
                    f"Error: ChromaDB collection dimension mismatch for '{self.collection_name}'. "
                    f"Delete '{db_path}/' and re-run to re-ingest.",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    f"Error: Could not open ChromaDB at '{db_path}': {exc}",
                    file=sys.stderr,
                    flush=True,
                )
            sys.exit(1)

        self._embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self._enc = tiktoken.get_encoding("cl100k_base")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_ingestion_check(self, knowledge_dir: str) -> IngestResult:
        """
        Scan all *.md files in knowledge_dir and incrementally ingest changed/new files.

        For each file:
          - Compute MD5 hash.
          - Check whether a chunk with the same source_file + file_hash already exists.
          - If yes -> skip.
          - If no -> delete old chunks for that file, re-chunk, embed, and upsert.

        Args:
            knowledge_dir: Path to the directory containing *.md files.

        Returns:
            IngestResult with lists of ingested/skipped filenames and total new chunk count.
        """
        result = IngestResult()
        md_files = sorted(Path(knowledge_dir).glob("*.md"))

        for md_path in md_files:
            filename = md_path.name
            current_hash = hashlib.md5(md_path.read_bytes()).hexdigest()

            # Check if any chunk already exists with the current hash
            existing = self._collection.get(
                where={
                    "$and": [
                        {"source_file": {"$eq": filename}},
                        {"file_hash": {"$eq": current_hash}},
                    ]
                },
                limit=1,
            )

            if existing["ids"]:
                result.skipped_files.append(filename)
                continue

            # Hash mismatch or new file — delete old chunks and re-ingest
            try:
                self._collection.delete(where={"source_file": {"$eq": filename}})
            except Exception:
                # Collection may have no chunks for this file yet — that's fine
                pass

            text = md_path.read_text(encoding="utf-8")
            chunks = self._chunk_text(text)
            if not chunks:
                result.skipped_files.append(filename)
                continue

            # Embed all chunks in one batch
            embeddings = self._embeddings.embed_documents(chunks)

            ids = [f"{filename}::{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "source_file": filename,
                    "file_hash": current_hash,
                    "chunk_index": i,
                    "company_name": self.company_name,
                }
                for i in range(len(chunks))
            ]

            self._collection.upsert(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            result.ingested_files.append(filename)
            result.total_new_chunks += len(chunks)
            print(f"  Re-ingested {filename} ({len(chunks)} new chunks)", flush=True)

        return result

    def similarity_search(self, query: str, n_results: int = 20) -> list[str]:
        """
        Embed the query with text-embedding-3-small and return the n_results most similar chunks.

        Args:
            query: The search query string.
            n_results: Maximum number of chunks to return. Defaults to 20.

        Returns:
            List of document strings. May be shorter than n_results if the collection is small.
        """
        query_embedding = self._embeddings.embed_query(query)
        collection_count = self._collection.count()
        effective_n = min(n_results, collection_count) if collection_count > 0 else 0
        if effective_n == 0:
            return []

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=effective_n,
            include=["documents"],
        )
        return results["documents"][0]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> list[str]:
        """
        Chunk text into segments of CHUNK_SIZE tokens with CHUNK_OVERLAP token overlap.

        Uses the cl100k_base tiktoken encoder.

        Args:
            text: The raw text to chunk.

        Returns:
            List of decoded text chunks.
        """
        all_tokens = self._enc.encode(text)
        chunks: list[str] = []
        i = 0
        step = CHUNK_SIZE - CHUNK_OVERLAP  # 450 tokens per advance
        while i < len(all_tokens):
            chunk_tokens = all_tokens[i : i + CHUNK_SIZE]
            chunks.append(self._enc.decode(chunk_tokens))
            i += step
        return chunks
