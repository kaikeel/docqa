"""Command-line interface for DocQA."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="docqa",
    help="docqa: ask questions about your documents and get answers with citations.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """docqa: ask questions about your documents and get answers with citations."""
