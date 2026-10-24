import itertools
from pathlib import Path

import pytest

from docqa.errors import IngestError
from docqa.ingest import Page, chunk_text, load_file

FIXTURES = Path(__file__).parent / "fixtures"


def _words(n: int) -> str:
    # varying word lengths so window edges fall inside words
    return " ".join(f"w{i}" + "x" * (i % 11) for i in range(n))


def test_short_text_is_one_chunk() -> None:
    spans = chunk_text("Hello world.")
    assert len(spans) == 1
    assert (spans[0].start, spans[0].end, spans[0].text) == (0, 12, "Hello world.")


def test_empty_and_whitespace_only_give_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n\t ") == []


def test_chunks_respect_size_overlap_and_word_boundaries() -> None:
    text = _words(500)  # ~5000 chars
    spans = chunk_text(text, size=800, overlap=150)
    assert len(spans) >= 5
    for span in spans:
        assert 0 < len(span.text) <= 800
        assert span.text == text[span.start : span.end]
        assert span.text == span.text.strip()
        # never cut in the middle of a word
        assert span.start == 0 or text[span.start - 1] == " "
        assert span.end == len(text) or text[span.end] == " "
    for prev, nxt in itertools.pairwise(spans):
        overlap = prev.end - nxt.start
        assert 0 < overlap <= 150
    # the whole text is covered
    assert spans[0].start == 0
    assert spans[-1].end == len(text)


def test_text_without_whitespace_is_cut_hard() -> None:
    text = "x" * 2000
    spans = chunk_text(text, size=800, overlap=150)
    assert [len(s.text) for s in spans][:2] == [800, 800]
    assert spans[1].start == 650
    assert spans[-1].end == 2000


def test_crlf_is_normalised() -> None:
    spans = chunk_text("line one\r\nline two\rline three")
    assert spans[0].text == "line one\nline two\nline three"


def test_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        chunk_text("abc", size=100, overlap=100)
    with pytest.raises(ValueError):
        chunk_text("abc", size=0, overlap=0)


def test_load_markdown_and_text(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("# Title\n\nBody text.", encoding="utf-8")
    txt = tmp_path / "b.txt"
    txt.write_bytes("caf\xc3\xa9 \xff ok".encode("latin-1"))
    assert load_file(md) == [Page(number=None, text="# Title\n\nBody text.")]
    pages = load_file(txt)
    assert pages[0].number is None
    assert pages[0].text.startswith("café") and "�" in pages[0].text


def test_load_pdf_keeps_page_numbers() -> None:
    pages = load_file(FIXTURES / "two_pages.pdf")
    assert [p.number for p in pages] == [1, 2]
    assert "release train" in pages[0].text
    assert "Rollback drills happen monthly." in pages[1].text


def test_pdf_without_text_is_rejected() -> None:
    with pytest.raises(IngestError, match="no extractable text"):
        load_file(FIXTURES / "no_text.pdf")


def test_corrupt_pdf_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(IngestError, match="unreadable PDF"):
        load_file(bad)


def test_empty_text_file_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("  \n", encoding="utf-8")
    with pytest.raises(IngestError, match="empty"):
        load_file(empty)


def test_unsupported_extension(tmp_path: Path) -> None:
    other = tmp_path / "image.png"
    other.write_bytes(b"\x89PNG")
    with pytest.raises(IngestError, match="unsupported"):
        load_file(other)
