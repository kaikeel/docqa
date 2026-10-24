"""The sample corpus and eval set ship with the repo and must stay consistent."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "examples" / "docs"
EVAL = ROOT / "examples" / "eval.jsonl"


def test_sample_docs_cover_all_formats() -> None:
    suffixes = {p.suffix for p in DOCS.iterdir()}
    assert {".md", ".txt", ".pdf"} <= suffixes
    assert 6 <= len(list(DOCS.iterdir())) <= 10


def test_eval_file_is_valid_jsonl_with_existing_sources() -> None:
    cases = [json.loads(line) for line in EVAL.read_text("utf-8").splitlines() if line.strip()]
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
