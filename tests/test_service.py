from dataclasses import replace
from pathlib import Path

from docqa.config import Settings
from docqa.llm import ClaudeAnswerModel
from docqa.service import NOT_FOUND_TEXT, DocQAService
from tests.helpers import SAMPLE_DOCS, make_service


def test_ingest_reports_sample_docs(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path, ingest=False)
    report = service.ingest(SAMPLE_DOCS)
    assert report.documents == 10
    assert report.skipped == []


def test_ask_returns_citation_from_expected_file(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    answer = service.ask("How long is the warranty on a fixed-price project?")
    assert answer.found is True
    assert answer.citations[0].source == "warranty-policy.md"
    question, chunks, history = factory.model.calls[0]
    assert question == "How long is the warranty on a fixed-price project?"
    assert 1 <= len(chunks) <= 5 and history == ()


def test_not_found_does_not_call_model(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    answer = service.ask("What is the airspeed of an unladen swallow?")
    assert (answer.text, answer.citations, answer.found) == (NOT_FOUND_TEXT, [], False)
    assert factory.calls == 0
    assert factory.model.calls == []


def test_k_limits_chunks_sent_to_model(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    service.ask("warranty defect report", k=2)
    assert len(factory.model.calls[0][1]) <= 2


def test_model_is_created_once(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    service.ask("How quickly are critical defects fixed?")
    service.ask("rollback drill")
    assert factory.calls == 1


def test_found_requires_citations(tmp_path: Path) -> None:
    from docqa.models import Answer, ChatTurn, Chunk

    class SilentModel:
        def answer(
            self, question: str, chunks: list[Chunk], history: tuple[ChatTurn, ...] = ()
        ) -> Answer:
            return Answer(text="Not mentioned.", citations=[], found=True)

    service, _ = make_service(tmp_path)
    service.model_factory = SilentModel
    answer = service.ask("How quickly are critical defects fixed?")
    assert (answer.text, answer.found) == ("Not mentioned.", False)


def test_default_factory_builds_claude_model(tmp_path: Path) -> None:
    settings = replace(Settings.from_env(), db_path=tmp_path / "x.db")
    service = DocQAService.from_settings(settings)
    model = service.model_factory()
    assert isinstance(model, ClaudeAnswerModel)
    assert (model.model, model.effort) == (settings.model, settings.effort)
