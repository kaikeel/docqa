import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from docqa.errors import IngestError
from docqa.ingest import ingest_dir
from docqa.store import NewChunk, Store

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "test.db")


def fts_hits(store: Store, word: str) -> int:
    row = store.conn.execute(
        "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?", (f'"{word}"',)
    ).fetchone()
    return int(row[0])


def make_corpus(root: Path) -> None:
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("# Alpha\n\nThe alpha document mentions pineapples.", "utf-8")
    (root / "sub" / "b.txt").write_text("Bravo text about bananas. " * 60, "utf-8")
    shutil.copy(FIXTURES / "two_pages.pdf", root / "c.pdf")
    (root / ".hidden.md").write_text("secret notes", "utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config.md").write_text("ignored", "utf-8")
    (root / "image.png").write_bytes(b"\x89PNG")
    (root / "empty.txt").write_text("", "utf-8")
    shutil.copy(FIXTURES / "no_text.pdf", root / "scan.pdf")


def test_fts5_is_available(store: Store) -> None:
    tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master")}
    assert {"documents", "chunks", "chunks_fts"} <= tables
    assert store.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_store_replace_document_is_atomic_and_synced(store: Store) -> None:
    store.replace_document("x.md", "h1", [NewChunk(0, 0, 5, None, "hello mango")])
    assert store.document_sha("x.md") == "h1"
    assert store.chunk_count() == 1
    assert fts_hits(store, "mango") == 1
    store.replace_document("x.md", "h2", [NewChunk(0, 0, 5, None, "hello kiwi")])
    assert store.document_count() == 1
    assert fts_hits(store, "mango") == 0
    assert fts_hits(store, "kiwi") == 1


def test_failed_replace_rolls_back(store: Store) -> None:
    store.replace_document("x.md", "h1", [NewChunk(0, 0, 5, None, "hello mango")])
    duplicate_index = [NewChunk(0, 0, 5, None, "a"), NewChunk(0, 5, 9, None, "b")]
    with pytest.raises(sqlite3.IntegrityError):
        store.replace_document("x.md", "h2", duplicate_index)
    assert store.document_sha("x.md") == "h1"
    assert fts_hits(store, "mango") == 1


def test_ingest_dir_counts_and_skips(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "docs"
    make_corpus(root)
    report = ingest_dir(store, root)
    assert report.documents == 3
    assert report.chunks == store.chunk_count() >= 4
    assert report.unchanged == 0
    assert report.skipped == [
        ".git: hidden",
        ".hidden.md: hidden",
        "empty.txt: empty file",
        "image.png: unsupported file type",
        "scan.pdf: no extractable text — OCR not supported",
    ]
    sources = {r[0] for r in store.conn.execute("SELECT source FROM documents")}
    assert sources == {"a.md", "sub/b.txt", "c.pdf"}
    pages = store.conn.execute(
        "SELECT DISTINCT page FROM chunks JOIN documents d ON d.id = document_id "
        "WHERE d.source = 'c.pdf' ORDER BY page"
    ).fetchall()
    assert [p[0] for p in pages] == [1, 2]
    assert fts_hits(store, "secret") == 0


def test_reingest_is_idempotent(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "docs"
    make_corpus(root)
    ingest_dir(store, root)
    ids_before = store.conn.execute("SELECT id FROM chunks ORDER BY id").fetchall()
    report = ingest_dir(store, root)
    assert (report.documents, report.chunks, report.unchanged) == (0, 0, 3)
    assert store.conn.execute("SELECT id FROM chunks ORDER BY id").fetchall() == ids_before


def test_changed_file_replaces_chunks(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "docs"
    make_corpus(root)
    ingest_dir(store, root)
    (root / "a.md").write_text("Now about grapefruit only.", "utf-8")
    report = ingest_dir(store, root)
    assert (report.documents, report.unchanged) == (1, 2)
    assert fts_hits(store, "pineapples") == 0
    assert fts_hits(store, "grapefruit") == 1


def test_missing_directory(store: Store, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="not a directory"):
        ingest_dir(store, tmp_path / "nope")


def test_store_context_manager(tmp_path: Path) -> None:
    with Store(tmp_path / "cm.db") as s:
        assert s.chunk_count() == 0
    with pytest.raises(sqlite3.ProgrammingError):
        s.chunk_count()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read files with mode 000")
def test_unreadable_file_is_skipped(store: Store, tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    locked = root / "locked.md"
    locked.write_text("cannot read me", "utf-8")
    locked.chmod(0)
    try:
        report = ingest_dir(store, root)
    finally:
        locked.chmod(0o644)
    assert report.skipped == ["locked.md: unreadable (PermissionError)"]


def test_concurrent_search_and_ingest_are_safe(store: Store, tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from docqa.retriever import FTS5Retriever

    root = tmp_path / "docs"
    make_corpus(root)
    retriever = FTS5Retriever(store, min_score=0.0)

    def work(i: int) -> None:
        for _ in range(30):
            if i == 0:
                (root / "a.md").write_text(f"pineapples version {_}", "utf-8")
                ingest_dir(store, root)
            retriever.search("pineapples bananas", k=3)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(work, range(6)))
    assert store.document_count() == 3
    assert hasattr(store, "lock")
