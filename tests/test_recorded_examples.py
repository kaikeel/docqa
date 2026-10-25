"""examples/recorded/ must stay honest: real API shapes, verbatim quotes, reproducible retrieval."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from docqa.api import AnswerResponse, AskRequest, ChatRequest
from docqa.chat import retrieval_queries
from docqa.models import ChatTurn, Chunk
from docqa.retriever import content_tokens
from tests.helpers import make_service

RECORDED = Path(__file__).resolve().parent.parent / "examples" / "recorded"
FILES = sorted(RECORDED.glob("*.json"))
EXPECTED = {"ask-warranty.json", "ask-gold-plan-not-found.json", "chat-support-plans.json"}


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return data


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_expected_recordings_exist() -> None:
    assert {p.name for p in FILES} == EXPECTED


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_recording_states_where_it_comes_from(path: Path) -> None:
    provenance = _load(path)["provenance"]
    assert "Claude Code" in provenance
    assert "NOT output of DocQA's Anthropic API path" in provenance
    assert "native citations" in provenance


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_requests_and_responses_have_the_api_shape(path: Path) -> None:
    for exchange in _load(path)["exchanges"]:
        request_model = AskRequest if exchange["endpoint"] == "POST /ask" else ChatRequest
        assert exchange["endpoint"] in {"POST /ask", "POST /chat"}
        request_model.model_validate(exchange["request"])
        response = AnswerResponse.model_validate(exchange["response"])
        assert set(exchange["response"]) == {"answer", "citations", "found"}
        assert response.found is bool(response.citations)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_retrieval_and_quotes_match_the_sample_docs(path: Path, tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    for exchange in _load(path)["exchanges"]:
        request = exchange["request"]
        if "question" in request:
            queries = [request["question"]]
        else:
            queries = retrieval_queries([ChatTurn(**m) for m in request["messages"]])
        chunks: list[Chunk] = []
        for query in queries:
            chunks = service.retriever.search(query, 5)
            if chunks:
                break
        recorded = exchange["retrieval"]
        assert recorded["query"] == query
        assert recorded["passages_sent_to_model"] == [c.source for c in chunks]
        coverage = service.retriever.coverage(content_tokens(query), chunks[0].id)
        assert recorded["best_passage_coverage"] == round(coverage, 2)
        for citation in exchange["response"]["citations"]:
            sources = {c.source for c in chunks if _norm(citation["quote"]) in _norm(c.text)}
            assert citation["source"] in sources, citation
    assert factory.calls == 0  # checking a recording never calls a model
