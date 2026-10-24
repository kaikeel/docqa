"""The sample corpus and eval set ship with the repo and must stay consistent."""

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "examples" / "docs"
EVAL = ROOT / "examples" / "eval.jsonl"
HOLDOUT = ROOT / "examples" / "eval_holdout.jsonl"


def test_sample_docs_cover_all_formats() -> None:
    suffixes = {p.suffix for p in DOCS.iterdir()}
    assert {".md", ".txt", ".pdf"} <= suffixes
    assert 6 <= len(list(DOCS.iterdir())) <= 10


def _cases(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def test_holdout_is_separate_from_dev_and_large_enough() -> None:
    dev = {str(c["question"]).lower() for c in _cases(EVAL)}
    holdout = _cases(HOLDOUT)
    assert len(holdout) >= 20
    assert sum(not c["answerable"] for c in holdout) >= 5
    assert not dev & {str(c["question"]).lower() for c in holdout}


@pytest.mark.parametrize("path", [EVAL, HOLDOUT], ids=["dev", "holdout"])
def test_eval_file_is_valid_jsonl_with_existing_sources(path: Path) -> None:
    cases: list[Any] = _cases(path)
    assert len(cases) >= 15
    answerable = [c for c in cases if c["answerable"]]
    unanswerable = [c for c in cases if not c["answerable"]]
    assert len(answerable) >= 10
    assert len(unanswerable) >= 3
    for case in cases:
        assert set(case) == {"question", "expected_sources", "answerable"}
        assert isinstance(case["question"], str) and case["question"].strip()
    for case in answerable:
        assert case["expected_sources"]
        for source in case["expected_sources"]:
            assert (DOCS / source).is_file(), source
    for case in unanswerable:
        assert case["expected_sources"] == []
