"""Lexical retrieval with SQLite FTS5 / BM25 behind a small protocol (ADR 0002)."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
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
    long often many quickly soon get got need want know happen happens
    """.split()  # noqa: SIM905
)
# The last line above holds question fillers ("How long...", "How often...", "What happens...")
# that carry no topic; added with the coverage gate (ADR 0007).
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
# Chunks containing the token, and whether the given chunk is one of them.
_TOKEN_SQL = """
SELECT count(*) AS df, coalesce(max(rowid = ?), 0) AS present
FROM chunks_fts WHERE chunks_fts MATCH ?
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
    """BM25 ranking over the FTS5 index, behind an evidence gate on query coverage.

    The gate (ADR 0007) looks at the best-ranked chunk and asks how much of the question it
    covers: the share of the question's content words found in that chunk, each word weighted
    by its inverse document frequency (rare words and words absent from the corpus weigh the
    most). Below ``min_coverage`` the result is empty (-> "not found", no LLM call). Otherwise
    the full top-k is returned, including weaker chunks, so the model sees related passages
    (e.g. both plans for "the other one"). Unlike a raw BM25 threshold, this does not punish
    short questions: "What is the warranty?" is fully covered by the warranty chunk.
    """

    def __init__(self, store: Store, min_coverage: float) -> None:
        if not 0.0 <= min_coverage <= 1.0:  # also rejects NaN
            raise ValueError(f"min_coverage must be between 0 and 1, got {min_coverage}")
        self.store = store
        self.min_coverage = min_coverage

    def search(self, query: str, k: int) -> list[Chunk]:
        tokens = content_tokens(query)
        if not tokens or k < 1:
            return []
        with self.store.lock:
            rows = self.store.conn.execute(_SEARCH_SQL, (to_match_expression(tokens), k)).fetchall()
            if not rows or self.coverage(tokens, rows[0]["id"]) < self.min_coverage:
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

    def coverage(self, tokens: Sequence[str], chunk_id: int) -> float:
        """IDF-weighted share of ``tokens`` that occur in chunk ``chunk_id`` (0.0 to 1.0).

        Matching goes through FTS5, so it uses the same tokenizer (stemming, diacritics) as
        the search itself. IDF is the BM25 form ``ln(1 + (N - df + 0.5) / (df + 0.5))``.
        """
        if not tokens:
            return 0.0
        with self.store.lock:
            total = self.store.chunk_count()
            covered = weight_sum = 0.0
            for token in tokens:
                row = self.store.conn.execute(
                    _TOKEN_SQL, (chunk_id, to_match_expression([token]))
                ).fetchone()
                df = int(row["df"])
                weight = math.log(1 + (total - df + 0.5) / (df + 0.5))
                weight_sum += weight
                covered += weight if row["present"] else 0.0
        return covered / weight_sum
