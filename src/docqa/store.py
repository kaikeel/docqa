"""SQLite storage: documents, chunks and an external-content FTS5 index kept in sync by triggers."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from docqa.errors import DocQAError

# Bumped whenever SCHEMA changes incompatibly (stored in PRAGMA user_version).
# 2: porter stemming in the FTS5 tokenizer (ADR 0007).
# 3: documents keyed by the file's resolved path, so equal relative names do not collide.
SCHEMA_VERSION = 3

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,  -- resolved file path: the identity of a document
    source      TEXT NOT NULL,         -- path relative to the ingested folder, shown in citations
    sha256      TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_char  INTEGER NOT NULL,
    end_char    INTEGER NOT NULL,
    page        INTEGER,
    text        TEXT NOT NULL,
    UNIQUE (document_id, chunk_index)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""


@dataclass(frozen=True)
class NewChunk:
    """A chunk about to be written (the database assigns its id)."""

    chunk_index: int
    start_char: int
    end_char: int
    page: int | None
    text: str


class Store:
    """One SQLite file holding the whole index."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # FastAPI runs sync endpoints in a thread pool, so one connection is shared across
        # threads; every use of it must hold ``lock``.
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.RLock()
        self.conn.row_factory = sqlite3.Row
        self._check_version()
        self.conn.executescript(SCHEMA)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _check_version(self) -> None:
        """Refuse an index written by another schema version instead of misreading it."""
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        has_tables = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'documents'"
        ).fetchone()
        if has_tables and version != SCHEMA_VERSION:
            self.conn.close()
            raise DocQAError(
                f"The index {self.path} was created by another DocQA version "
                f"(schema {version}, expected {SCHEMA_VERSION}); delete {self.path} and "
                "ingest again."
            )

    def __enter__(self) -> Store:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def document_sha(self, path: str) -> str | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT sha256 FROM documents WHERE path = ?", (path,)
            ).fetchone()
        return None if row is None else str(row["sha256"])

    def replace_document(
        self, source: str, sha256: str, chunks: list[NewChunk], *, path: str | None = None
    ) -> None:
        """Replace the document stored under ``path`` (default: ``source``) in one transaction.

        ``path`` identifies the document (ingest passes the resolved file path); ``source`` is
        the display name used in citations.
        """
        key = source if path is None else path
        with self.lock, self.conn:
            self.conn.execute(
                "DELETE FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE path = ?)",
                (key,),
            )
            self.conn.execute("DELETE FROM documents WHERE path = ?", (key,))
            cur = self.conn.execute(
                "INSERT INTO documents (path, source, sha256, ingested_at) VALUES (?, ?, ?, ?)",
                (key, source, sha256, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            doc_id = cur.lastrowid
            self.conn.executemany(
                "INSERT INTO chunks (document_id, chunk_index, start_char, end_char, page, text) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(doc_id, c.chunk_index, c.start_char, c.end_char, c.page, c.text) for c in chunks],
            )

    def chunk_count(self) -> int:
        with self.lock:
            return int(self.conn.execute("SELECT count(*) FROM chunks").fetchone()[0])

    def document_count(self) -> int:
        with self.lock:
            return int(self.conn.execute("SELECT count(*) FROM documents").fetchone()[0])
