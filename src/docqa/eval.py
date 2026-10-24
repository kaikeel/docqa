"""Evaluation on a JSONL question set: retrieval hit@k (no API key) and full answer checks."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docqa.errors import DocQAError
from docqa.retriever import Retriever
from docqa.service import DocQAService


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_sources: tuple[str, ...]
    answerable: bool


@dataclass(frozen=True)
class EvalReport:
    k: int
    answerable: int
    hits: int  # answerable cases with an expected source in the top-k
    unanswerable: int
    unanswerable_rejected: int  # unanswerable cases where retrieval found nothing
    citation_rate: float | None = None  # full mode: answerable cases answered with a citation
    not_found_accuracy: float | None = None  # full mode: unanswerable cases with found=False

    @property
    def hit_rate(self) -> float:
        return self.hits / self.answerable if self.answerable else 0.0


def load_cases(path: Path) -> list[EvalCase]:
    """Parse ``{"question", "expected_sources", "answerable"}`` lines; errors name the line."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DocQAError(f"cannot read {path}: {type(exc).__name__}") from None
    cases = [_parse(line, number) for number, line in enumerate(lines, start=1) if line.strip()]
    if not cases:
        raise DocQAError(f"{path} contains no cases")
    return cases


def _parse(line: str, number: int) -> EvalCase:
    try:
        data: Any = json.loads(line)
    except json.JSONDecodeError:
        raise DocQAError(f"line {number}: not valid JSON") from None
    if not isinstance(data, dict):
        raise DocQAError(f"line {number}: expected a JSON object")
    question = data.get("question")
    sources = data.get("expected_sources")
    answerable = data.get("answerable")
    if not isinstance(question, str) or not question.strip():
        raise DocQAError(f"line {number}: 'question' must be a non-empty string")
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        raise DocQAError(f"line {number}: 'expected_sources' must be a list of strings")
    if not isinstance(answerable, bool):
        raise DocQAError(f"line {number}: 'answerable' must be true or false")
    if answerable and not sources:
        raise DocQAError(f"line {number}: answerable cases need at least one expected source")
    return EvalCase(question=question, expected_sources=tuple(sources), answerable=answerable)


def run_retrieval_eval(retriever: Retriever, cases: Sequence[EvalCase], k: int) -> EvalReport:
    hits = rejected = 0
    for case in cases:
        results = retriever.search(case.question, k)
        if case.answerable:
            hits += any(chunk.source in case.expected_sources for chunk in results)
        else:
            rejected += not results
    answerable = sum(case.answerable for case in cases)
    return EvalReport(
        k=k,
        answerable=answerable,
        hits=hits,
        unanswerable=len(cases) - answerable,
        unanswerable_rejected=rejected,
    )


def run_full_eval(service: DocQAService, cases: Sequence[EvalCase], k: int) -> EvalReport:
    """Retrieval metrics plus real answers (needs ANTHROPIC_API_KEY unless a fake model is used)."""
    retrieval = run_retrieval_eval(service.retriever, cases, k)
    cited = not_found = 0
    for case in cases:
        answer = service.ask(case.question, k)
        if case.answerable:
            cited += bool(answer.citations)
        else:
            not_found += not answer.found
    return EvalReport(
        k=retrieval.k,
        answerable=retrieval.answerable,
        hits=retrieval.hits,
        unanswerable=retrieval.unanswerable,
        unanswerable_rejected=retrieval.unanswerable_rejected,
        citation_rate=cited / retrieval.answerable if retrieval.answerable else None,
        not_found_accuracy=not_found / retrieval.unanswerable if retrieval.unanswerable else None,
    )
