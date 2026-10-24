"""Lexical retrieval with SQLite FTS5 / BM25 behind a small protocol (ADR 0002)."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from docqa.models import Chunk
from docqa.store import Store

# Small fixed English stopword list. It deliberately contains every chat reference word
# (see chat.REFERENCE_WORDS, ADR 0005) so those words never match documents on their own.
STOPWORDS = frozenset(
    # A whitespace-separated block reads better than ~70 one-per-line literals.
    """
    a about after all also an and any are as at be been but by can could did do does for from
    had has have how if in into is was were what when where which who whom why will with would
    of on or our should so than the then there to up us we you your me my not no yes just more
    most much very please tell
    it its this that these those they them their other another one ones same else former latter
    """.split()  # noqa: SIM905
)
MIN_TOKEN_LENGTH = 2
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

_SEARCH_SQL = """
SELECT c.id, d.source, c.chunk_index, c.start_char, c.end_char, c.page, c.text,
       -bm25(chunks_fts) AS score
FROM chunks_fts
JOIN chunks c ON c.id = chunks_fts.rowid
JOIN documents d ON d.id = c.document_id
WHERE chunks_fts MATCH ?
ORDER BY score DESC
LIMIT ?
"""


@runtime_checkable
class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[Chunk]:
        """Return at most ``k`` chunks with enough evidence, best first ([] when none)."""
        ...


def content_tokens(text: str) -> list[str]:
    """Lowercased word tokens without stopwords or very short tokens, first occurrence order."""
    seen: dict[str, None] = {}
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        if len(token) >= MIN_TOKEN_LENGTH and token not in STOPWORDS and token not in seen:
            seen[token] = None
    return list(seen)


def to_match_expression(tokens: list[str]) -> str:
    """Quote every token as an FTS5 string so user input can never act as an operator."""
    return " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)


class FTS5Retriever:
    """BM25 ranking over the FTS5 index, gated by ``min_score``.

    ``min_score`` is an evidence gate: if even the best chunk scores below it, the result is
    empty (-> "not found", no LLM call). Otherwise the full top-k is returned, including
    weaker chunks, so the model sees related passages (e.g. both plans for "the other one").
    See docs/adr/0002 (calibration).
    """

    def __init__(self, store: Store, min_score: float) -> None:
        self.store = store
        self.min_score = min_score

    def search(self, query: str, k: int) -> list[Chunk]:
        tokens = content_tokens(query)
        if not tokens or k < 1:
            return []
        with self.store.lock:
            rows = self.store.conn.execute(_SEARCH_SQL, (to_match_expression(tokens), k)).fetchall()
        if not rows or rows[0]["score"] < self.min_score:
            return []
        return [
            Chunk(
                id=row["id"],
                source=row["source"],
                chunk_index=row["chunk_index"],
                start_char=row["start_char"],
                end_char=row["end_char"],
                page=row["page"],
                text=row["text"],
                score=float(row["score"]),
            )
            for row in rows
        ]
