from pathlib import Path

import pytest
from typer.testing import CliRunner

from docqa import cli
from docqa.config import DEFAULT_MIN_COVERAGE
from docqa.errors import DocQAError
from docqa.eval import EvalCase, load_cases, run_full_eval, run_retrieval_eval
from docqa.llm import FakeAnswerModel
from tests.helpers import ROOT, SAMPLE_DOCS, make_service

EVAL_FILE = ROOT / "examples" / "eval.jsonl"
HOLDOUT_FILE = ROOT / "examples" / "eval_holdout.jsonl"
runner = CliRunner()


def test_load_cases_reads_sample_file() -> None:
    cases = load_cases(EVAL_FILE)
    assert len(cases) == 39
    assert cases[0] == EvalCase(
        question="How long is the warranty on a fixed-price project?",
        expected_sources=("warranty-policy.md",),
        answerable=True,
    )


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        '{"question": "q"}',
        '{"question": "", "expected_sources": [], "answerable": false}',
        '{"question": "q", "expected_sources": "a.md", "answerable": true}',
        '{"question": "q", "expected_sources": [], "answerable": "yes"}',
        '{"question": "q", "expected_sources": [], "answerable": true}',
        "[1, 2]",
    ],
)
def test_load_cases_rejects_bad_lines(tmp_path: Path, line: str) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"question": "ok", "expected_sources": ["a.md"], "answerable": true}\n' + line)
    with pytest.raises(DocQAError, match="line 2"):
        load_cases(path)


def test_load_cases_missing_or_empty_file(tmp_path: Path) -> None:
    with pytest.raises(DocQAError, match="cannot read"):
        load_cases(tmp_path / "missing.jsonl")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n\n")
    with pytest.raises(DocQAError, match="no cases"):
        load_cases(empty)


@pytest.mark.parametrize("path", [EVAL_FILE, HOLDOUT_FILE], ids=["dev", "holdout"])
def test_retrieval_targets_on_dev_and_holdout(tmp_path: Path, path: Path) -> None:
    # Targets from the QA fix round (ADR 0007): hit@3 >= 0.8 and >= 90% of unanswerable
    # questions rejected, on the dev set used for calibration and on the untouched holdout.
    service, factory = make_service(tmp_path)
    assert service.settings.min_coverage == DEFAULT_MIN_COVERAGE
    report = run_retrieval_eval(service.retriever, load_cases(path), k=3)
    assert report.hit_rate >= 0.8
    assert report.unanswerable >= 5
    assert report.unanswerable_rejected / report.unanswerable >= 0.9
    assert factory.calls == 0


@pytest.mark.parametrize(
    ("question", "source"),
    [
        ("What is the warranty?", "warranty-policy.md"),
        ("What support plans do you have?", "support-plan-starter.md"),
        ("What is a change request?", "estimates-and-change-requests.md"),
        ("How do you estimate?", "estimates-and-change-requests.md"),
        ("gitleaks", "security-checklist.txt"),
    ],
)
def test_short_natural_questions_pass_the_gate(tmp_path: Path, question: str, source: str) -> None:
    service, _ = make_service(tmp_path)
    answer = service.ask(question)
    assert answer.found is True
    assert answer.citations[0].source == source


def test_unanswerable_questions_are_not_found_by_service(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    for case in load_cases(EVAL_FILE):
        if not case.answerable:
            assert service.ask(case.question).found is False, case.question
    assert factory.calls == 0


def test_full_eval_with_fake_model(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    report = run_full_eval(service, load_cases(EVAL_FILE), k=3)
    assert report.hit_rate >= 0.8
    assert report.citation_rate is not None and report.citation_rate >= 0.8
    assert report.not_found_accuracy == 1.0


def test_cli_eval_retrieval_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCQA_DB", str(tmp_path / "e.db"))
    assert runner.invoke(cli.app, ["ingest", str(SAMPLE_DOCS)]).exit_code == 0
    result = runner.invoke(cli.app, ["eval", str(EVAL_FILE), "--retrieval-only", "--k", "3"])
    assert result.exit_code == 0, result.output
    assert "cases: 39" in result.output
    assert "hit@3: 0.968 (30/31 answerable)" in result.output
    assert "unanswerable rejected: 8/8" in result.output
    assert "citation_rate" not in result.output


def test_cli_eval_full_with_fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCQA_DB", str(tmp_path / "e.db"))
    fake = FakeAnswerModel()
    monkeypatch.setattr(cli, "MODEL_FACTORY", lambda: fake)
    runner.invoke(cli.app, ["ingest", str(SAMPLE_DOCS)])
    result = runner.invoke(cli.app, ["eval", str(EVAL_FILE)])
    assert result.exit_code == 0, result.output
    assert "citation_rate:" in result.output
    assert "not_found_accuracy: 1.00" in result.output
    assert fake.calls


def test_cli_eval_bad_file_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCQA_DB", str(tmp_path / "e.db"))
    bad = tmp_path / "bad.jsonl"
    bad.write_text("nope\n")
    result = runner.invoke(cli.app, ["eval", str(bad), "--retrieval-only"])
    assert result.exit_code == 1
    assert "line 1" in result.stderr


def test_cli_eval_full_without_key_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from docqa.errors import LLMAuthError
    from docqa.models import Answer, ChatTurn, Chunk

    class NoKey:
        def answer(
            self, question: str, chunks: list[Chunk], history: tuple[ChatTurn, ...] = ()
        ) -> Answer:
            raise LLMAuthError()

    monkeypatch.setenv("DOCQA_DB", str(tmp_path / "e.db"))
    monkeypatch.setattr(cli, "MODEL_FACTORY", NoKey)
    runner.invoke(cli.app, ["ingest", str(SAMPLE_DOCS)])
    result = runner.invoke(cli.app, ["eval", str(EVAL_FILE)])
    assert result.exit_code == 2
    assert "ANTHROPIC_API_KEY" in result.stderr
