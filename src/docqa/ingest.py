"""Load documents (.md, .txt, .pdf) and split them into overlapping chunks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from docqa.errors import IngestError

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
# When a window ends mid-word, look back at most this far for whitespace to cut at.
BOUNDARY_LOOKBACK = 100
TEXT_SUFFIXES = frozenset({".md", ".txt"})
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".pdf"}


@dataclass(frozen=True)
class Page:
    """Extracted text of a file (number=None) or of one PDF page (1-based number)."""

    number: int | None
    text: str


@dataclass(frozen=True)
class Span:
    """A chunk of text and its [start, end) offsets in the normalised source text."""

    start: int
    end: int
    text: str


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Span]:
    """Split text into windows of at most ``size`` chars that overlap by up to ``overlap`` chars.

    Cuts are moved back to whitespace (within BOUNDARY_LOOKBACK chars) so words are not split,
    and each new window starts at a word boundary when possible. Blank chunks are dropped.
    """
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("chunk size must be > 0 and 0 <= overlap < size")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    spans: list[Span] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n and not text[end].isspace():
            floor = max(start + 1, end - BOUNDARY_LOOKBACK)
            cut = _last_space(text, floor, end)
            if cut is not None:
                end = cut
        piece = text[start:end]
        stripped = piece.strip()
        if stripped:
            s = start + (len(piece) - len(piece.lstrip()))
            spans.append(Span(s, s + len(stripped), stripped))
        if end >= n:
            break
        start = _next_start(text, start, end, overlap)
    return spans


def _last_space(text: str, floor: int, end: int) -> int | None:
    for i in range(end - 1, floor - 1, -1):
        if text[i].isspace():
            return i
    return None


def _next_start(text: str, start: int, end: int, overlap: int) -> int:
    nxt = max(end - overlap, start + 1)
    j = nxt
    while j < end and not text[j - 1].isspace():
        j += 1
    return j if j < end else nxt


def load_file(path: Path) -> list[Page]:
    """Return the non-empty text pages of a supported file, or raise IngestError with a reason."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise IngestError("unsupported file type")
    if suffix == ".pdf":
        return _load_pdf(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise IngestError("empty file")
    return [Page(number=None, text=text)]


def _load_pdf(path: Path) -> list[Page]:
    try:
        reader = PdfReader(path)
        raw_pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, KeyError, OSError) as exc:
        raise IngestError(f"unreadable PDF ({type(exc).__name__})") from None
    pages = [Page(number=i, text=t) for i, t in enumerate(raw_pages, start=1) if t.strip()]
    if not pages:
        raise IngestError("no extractable text — OCR not supported")
    return pages
