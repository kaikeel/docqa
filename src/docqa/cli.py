"""Command-line interface: `docqa ingest`, `docqa ask`, `docqa eval`."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from docqa.config import Settings
from docqa.errors import AnswerError, DocQAError, IngestError
from docqa.models import Answer
from docqa.service import DocQAService, ModelFactory

app = typer.Typer(
    name="docqa",
    help="docqa: ask questions about your documents and get answers with citations.",
    no_args_is_help=True,
    add_completion=False,
)

# Tests replace this with a fake model factory; None means "use Claude".
MODEL_FACTORY: ModelFactory | None = None

DbOption = Annotated[
    Path | None, typer.Option("--db", help="SQLite file (default: $DOCQA_DB or ./docqa.db).")
]


@app.callback()
def main() -> None:
    """docqa: ask questions about your documents and get answers with citations."""


def _fail(message: str, code: int) -> typer.Exit:
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(code)


def _service(db: Path | None) -> DocQAService:
    try:
        settings = Settings.from_env()
    except DocQAError as exc:
        raise _fail(str(exc), 1) from None
    if db is not None:
        settings = replace(settings, db_path=db)
    return DocQAService.from_settings(settings, model_factory=MODEL_FACTORY)


def answer_payload(answer: Answer) -> dict[str, object]:
    """The JSON shape shared by `docqa ask --json` and `POST /ask`."""
    return {
        "answer": answer.text,
        "citations": [{"source": c.source, "quote": c.quote} for c in answer.citations],
        "found": answer.found,
    }


@app.command()
def ingest(
    directory: Annotated[Path, typer.Argument(help="Folder with .md, .txt and .pdf files.")],
    db: DbOption = None,
) -> None:
    """Index every supported file in DIRECTORY (recursively)."""
    service = _service(db)
    try:
        report = service.ingest(directory)
    except IngestError as exc:
        raise _fail(str(exc), 1) from None
    unchanged = f" ({report.unchanged} unchanged)" if report.unchanged else ""
    skipped = ", ".join(report.skipped) if report.skipped else "none"
    typer.echo(
        f"Ingested {report.documents} documents, {report.chunks} chunks{unchanged}; "
        f"skipped: {skipped}"
    )


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="Your question, in quotes.")],
    k: Annotated[int | None, typer.Option("--k", min=1, max=20, help="Chunks to use.")] = None,
    db: DbOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the /ask JSON.")] = False,
) -> None:
    """Answer QUESTION from the indexed documents, with citations."""
    service = _service(db)
    try:
        answer = service.ask(question, k)
    except AnswerError as exc:
        raise _fail(str(exc), 2) from None
    if as_json:
        typer.echo(json.dumps(answer_payload(answer), ensure_ascii=False))
        return
    typer.echo(answer.text)
    for number, citation in enumerate(answer.citations, start=1):
        quote = " ".join(citation.quote.split())
        typer.echo(f'[{number}] {citation.source} — "{quote}"')
