"""Shared test helpers: a service over the sample docs with a fake model."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from docqa.config import Settings
from docqa.llm import FakeAnswerModel
from docqa.service import DocQAService
from docqa.store import Store

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DOCS = ROOT / "examples" / "docs"


class CountingFactory:
    """Model factory that records how often it was called."""

    def __init__(self, model: FakeAnswerModel | None = None) -> None:
        self.model = model or FakeAnswerModel()
        self.calls = 0

    def __call__(self) -> FakeAnswerModel:
        self.calls += 1
        return self.model


def make_service(
    tmp_path: Path, *, ingest: bool = True, factory: CountingFactory | None = None
) -> tuple[DocQAService, CountingFactory]:
    settings = replace(Settings.from_env(), db_path=tmp_path / "docqa.db", ingest_root=ROOT)
    factory = factory or CountingFactory()
    service = DocQAService.from_settings(settings, model_factory=factory)
    if ingest:
        service.ingest(SAMPLE_DOCS)
    return service, factory


__all__ = ["SAMPLE_DOCS", "CountingFactory", "Store", "make_service"]
