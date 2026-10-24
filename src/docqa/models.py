"""Immutable data objects shared across DocQA modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Chunk:
    """A stored piece of a document, optionally with its retrieval score."""

    id: int
    source: str  # path relative to the ingested directory, e.g. "pricing.md"
    chunk_index: int  # position within the source file
    start_char: int  # offset in the extracted text (per page for PDFs)
    end_char: int
    page: int | None  # 1-based page number for PDFs, None for md/txt
    text: str
    score: float = 0.0  # -bm25(): higher means a better match


@dataclass(frozen=True)
class Citation:
    """A verbatim quote from a source document that supports an answer."""

    source: str
    quote: str
    chunk_id: int


@dataclass(frozen=True)
class Answer:
    """An answer and the citations backing it. ``found`` is False when there is no evidence."""

    text: str
    citations: list[Citation]
    found: bool


@dataclass(frozen=True)
class IngestReport:
    """Summary of an ingest run.

    ``documents``/``chunks`` count what was (re)indexed in this run; files whose content hash
    did not change are counted in ``unchanged`` and left untouched.
    """

    documents: int
    chunks: int
    skipped: list[str]  # "path: reason" for hidden, unsupported, empty or unreadable files
    unchanged: int = 0


@dataclass(frozen=True)
class ChatTurn:
    """One message of a client-held chat history (the server keeps no sessions)."""

    role: Literal["user", "assistant"]
    content: str
