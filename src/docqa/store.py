"""SQLite storage: documents, chunks and an external-content FTS5 index kept in sync by triggers."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL UNIQUE,
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
    tokenize='unicode61 remove_diacritics 2'
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
        self.conn.executescript(SCHEMA)

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

    def document_sha(self, source: str) -> str | None:
        row = self.conn.execute(
            "SELECT sha256 FROM documents WHERE source = ?", (source,)
        ).fetchone()
        return None if row is None else str(row["sha256"])

    def replace_document(self, source: str, sha256: str, chunks: list[NewChunk]) -> None:
        """Delete any previous version of ``source`` and insert the new one in one transaction."""
        with self.lock, self.conn:
            self.conn.execute(
                "DELETE FROM chunks WHERE document_id IN "
                "(SELECT id FROM documents WHERE source = ?)",
                (source,),
            )
            self.conn.execute("DELETE FROM documents WHERE source = ?", (source,))
            cur = self.conn.execute(
                "INSERT INTO documents (source, sha256, ingested_at) VALUES (?, ?, ?)",
                (source, sha256, datetime.now(UTC).isoformat(timespec="seconds")),
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
