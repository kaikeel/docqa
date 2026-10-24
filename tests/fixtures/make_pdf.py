"""Build tiny text PDFs without extra dependencies (used for test fixtures and the sample PDF).

Run `uv run python -m tests.fixtures.make_pdf` to regenerate the committed fixtures.
"""

from __future__ import annotations

from pathlib import Path


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(pages: list[list[str]]) -> bytes:
    """Return PDF bytes with one page per item; each page is a list of text lines (Helvetica 11)."""
    objects: list[bytes] = []
    n_pages = len(pages)
    font_id = 3 + 2 * n_pages
    page_ids = [3 + 2 * i for i in range(n_pages)]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    for i, lines in enumerate(pages):
        content_id = page_ids[i] + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        ops = ["BT", "/F1 11 Tf", "14 TL", "72 740 Td"]
        for line in lines:
            ops.append(f"({_escape(line)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1") if lines else b""
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


FIXTURES = Path(__file__).parent

TWO_PAGES = [
    ["Kaikeel test PDF, page one.", "The release train leaves every Thursday."],
    ["Page two talks about rollback drills.", "Rollback drills happen monthly."],
]


def main() -> None:
    (FIXTURES / "two_pages.pdf").write_bytes(build_pdf(TWO_PAGES))
    (FIXTURES / "no_text.pdf").write_bytes(build_pdf([[]]))


if __name__ == "__main__":
    main()
