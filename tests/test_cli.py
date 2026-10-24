import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from docqa import cli
from docqa.errors import LLMAuthError
from docqa.llm import FakeAnswerModel
from docqa.models import Answer, ChatTurn, Chunk
from tests.helpers import SAMPLE_DOCS

runner = CliRunner()


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "cli.db"
    monkeypatch.setenv("DOCQA_DB", str(path))
    return path


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeAnswerModel:
    model = FakeAnswerModel()
    monkeypatch.setattr(cli, "MODEL_FACTORY", lambda: model)
    return model


def ingest(*extra: str) -> None:
    result = runner.invoke(cli.app, ["ingest", str(SAMPLE_DOCS), *extra])
    assert result.exit_code == 0, result.output


def test_ingest_prints_summary(db: Path) -> None:
    result = runner.invoke(cli.app, ["ingest", str(SAMPLE_DOCS)])
    assert result.exit_code == 0
    assert result.output.startswith("Ingested 10 documents, ")
    assert "skipped: none" in result.output
    assert db.exists()
    again = runner.invoke(cli.app, ["ingest", str(SAMPLE_DOCS)])
    assert "Ingested 0 documents, 0 chunks (10 unchanged)" in again.output


def test_ingest_lists_skipped_files(db: Path, tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("hello world", "utf-8")
    (docs / "b.png").write_bytes(b"x")
    result = runner.invoke(cli.app, ["ingest", str(docs)])
    assert "skipped: b.png: unsupported file type" in result.output


def test_ingest_missing_dir_exits_1(db: Path, tmp_path: Path) -> None:
    result = runner.invoke(cli.app, ["ingest", str(tmp_path / "missing")])
    assert result.exit_code == 1
    assert "not a directory" in result.stderr


def test_db_option_overrides_env(db: Path, tmp_path: Path) -> None:
    other = tmp_path / "other.db"
    ingest("--db", str(other))
    assert other.exists() and not db.exists()


def test_ask_prints_answer_and_citations(db: Path, fake: FakeAnswerModel) -> None:
    ingest()
    result = runner.invoke(cli.app, ["ask", "How long is the warranty on a fixed-price project?"])
    assert result.exit_code == 0
    assert '[1] warranty-policy.md — "' in result.output


def test_ask_json_matches_api_schema(db: Path, fake: FakeAnswerModel) -> None:
    ingest()
    result = runner.invoke(cli.app, ["ask", "--json", "--k", "2", "rollback drill"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data) == {"answer", "citations", "found"}
    assert data["found"] is True
    assert set(data["citations"][0]) == {"source", "quote"}
    assert len(fake.calls[0][1]) <= 2


def test_ask_not_found_exits_0_without_model(db: Path, fake: FakeAnswerModel) -> None:
    ingest()
    result = runner.invoke(cli.app, ["ask", "--json", "What is the airspeed of a swallow?"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "answer": "Not found in the provided documents.",
        "citations": [],
        "found": False,
    }
    assert fake.calls == []


def test_ask_not_found_works_without_api_key_or_override(db: Path) -> None:
    ingest()
    result = runner.invoke(cli.app, ["ask", "zeppelin airships"])
    assert result.exit_code == 0
    assert "Not found in the provided documents." in result.output


def test_llm_error_exits_2_with_clear_message(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Failing:
        def answer(
            self, question: str, chunks: list[Chunk], history: tuple[ChatTurn, ...] = ()
        ) -> Answer:
            raise LLMAuthError()

    monkeypatch.setattr(cli, "MODEL_FACTORY", Failing)
    ingest()
    result = runner.invoke(cli.app, ["ask", "warranty"])
    assert result.exit_code == 2
    assert "ANTHROPIC_API_KEY is missing or invalid" in result.stderr
    assert "Traceback" not in result.output


def test_bad_env_config_exits_1(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCQA_TOP_K", "lots")
    result = runner.invoke(cli.app, ["ask", "warranty"])
    assert result.exit_code == 1
    assert "DOCQA_TOP_K" in result.stderr
