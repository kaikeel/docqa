import dataclasses
from pathlib import Path

import pytest

from docqa import config
from docqa.config import Settings
from docqa.errors import (
    AnswerError,
    DocQAError,
    IngestError,
    LLMAuthError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMUnavailableError,
)
from docqa.models import Answer, Chunk, Citation, IngestReport

ENV_VARS = [
    "DOCQA_MODEL",
    "DOCQA_EFFORT",
    "DOCQA_DB",
    "DOCQA_TOP_K",
    "DOCQA_MIN_SCORE",
    "DOCQA_INGEST_ROOT",
]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_defaults(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clean_env.chdir(tmp_path)
    s = Settings.from_env()
    assert s.model == "claude-opus-5-5"
    assert s.effort == "low"
    assert s.db_path == Path("./docqa.db")
    assert s.top_k == 5
    assert s.min_score == config.DEFAULT_MIN_SCORE
    assert s.ingest_root == tmp_path.resolve()


def test_overrides(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clean_env.setenv("DOCQA_MODEL", "claude-other")
    clean_env.setenv("DOCQA_EFFORT", "high")
    clean_env.setenv("DOCQA_DB", str(tmp_path / "x.db"))
    clean_env.setenv("DOCQA_TOP_K", "7")
    clean_env.setenv("DOCQA_MIN_SCORE", "2.5")
    clean_env.setenv("DOCQA_INGEST_ROOT", str(tmp_path))
    s = Settings.from_env()
    assert (s.model, s.effort, s.top_k, s.min_score) == ("claude-other", "high", 7, 2.5)
    assert s.db_path == tmp_path / "x.db"
    assert s.ingest_root == tmp_path.resolve()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DOCQA_TOP_K", "abc"),
        ("DOCQA_TOP_K", "0"),
        ("DOCQA_MIN_SCORE", "nope"),
        ("DOCQA_EFFORT", "turbo"),
    ],
)
def test_invalid_values_raise_clear_error(
    clean_env: pytest.MonkeyPatch, name: str, value: str
) -> None:
    clean_env.setenv(name, value)
    with pytest.raises(DocQAError, match=name):
        Settings.from_env()


def test_settings_never_hold_an_api_key(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-test-should-not-appear")
    s = Settings.from_env()
    field_names = {f.name for f in dataclasses.fields(s)}
    assert not any("key" in n.lower() for n in field_names)
    assert "sk-ant-test-should-not-appear" not in repr(s)


def test_dataclasses_are_frozen() -> None:
    chunk = Chunk(
        id=1, source="a.md", chunk_index=0, start_char=0, end_char=3, page=None, text="abc"
    )
    assert chunk.score == 0.0
    for obj in (
        chunk,
        Citation(source="a.md", quote="abc", chunk_id=1),
        Answer(text="t", citations=[], found=False),
        IngestReport(documents=0, chunks=0, skipped=[]),
        Settings.from_env(),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            obj.text = "x"  # type: ignore[union-attr]


def test_error_hierarchy() -> None:
    assert issubclass(IngestError, DocQAError)
    assert issubclass(AnswerError, DocQAError)
    for cls in (LLMAuthError, LLMRateLimitError, LLMUnavailableError, LLMRefusalError):
        assert issubclass(cls, AnswerError)
    assert LLMAuthError().code == "llm_auth"
    assert "ANTHROPIC_API_KEY" in str(LLMAuthError())
    assert LLMRateLimitError().code == "llm_rate_limited"
    assert LLMUnavailableError(status_code=503).status_code == 503
    assert "503" in str(LLMUnavailableError(status_code=503))
    assert LLMRefusalError(category="cyber").category == "cyber"
    assert LLMRefusalError().code == "llm_refusal"
