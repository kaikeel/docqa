import logging
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage

from docqa.errors import (
    LLMAuthError,
    LLMIncompleteError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMUnavailableError,
)
from docqa.llm import (
    BETA_FALLBACK,
    MAX_TOKENS,
    SYSTEM_PROMPT,
    AnswerModel,
    ClaudeAnswerModel,
    FakeAnswerModel,
)
from docqa.models import Chunk, Citation

CHUNKS = [
    Chunk(11, "warranty-policy.md", 0, 0, 40, None, "Every project includes a 7-day warranty."),
    Chunk(12, "release-checklist.pdf", 0, 0, 30, 2, "A rollback drill is quarterly."),
]
FORBIDDEN_KEYS = {
    "temperature",
    "top_p",
    "top_k",
    "thinking",
    "budget_tokens",
    "tools",
    "tool_choice",
    "stop_sequences",
}


def message(content: list[dict[str, Any]], **extra: Any) -> BetaMessage:
    data: dict[str, Any] = {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "stop_reason": "end_turn",
        "stop_details": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "content": content,
    }
    data.update(extra)
    return BetaMessage.model_validate(data)


def cite(text: str, index: int, title: str = "t") -> dict[str, Any]:
    return {
        "type": "char_location",
        "cited_text": text,
        "document_index": index,
        "document_title": title,
        "start_char_index": 0,
        "end_char_index": len(text),
    }


class FakeMessages:
    def __init__(self, result: BetaMessage | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> BetaMessage:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeClient:
    def __init__(self, result: BetaMessage | Exception) -> None:
        self.messages = FakeMessages(result)
        self.beta = self


def model_with(result: BetaMessage | Exception) -> tuple[ClaudeAnswerModel, FakeMessages]:
    client = FakeClient(result)
    model = ClaudeAnswerModel(client_factory=lambda: client, model="claude-opus-5-5", effort="low")  # type: ignore[arg-type,return-value]
    return model, client.messages


CITED = message(
    [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {
            "type": "fallback",
            "from": {"model": "claude-opus-5-5"},
            "to": {"model": "claude-opus-5-5"},
            "trigger": {"type": "refusal"},
        },
        {"type": "text", "text": "The warranty lasts "},
        {
            "type": "text",
            "text": "7 days.",
            "citations": [
                cite("7-day warranty", 0),
                cite("7-day warranty", 0),  # duplicate is dropped
                cite("ghost", 5),  # out of range is dropped
            ],
        },
        {"type": "text", "text": " Drills are quarterly.", "citations": [cite("quarterly", 1)]},
    ]
)


def test_request_matches_spec_exactly() -> None:
    model, calls = model_with(CITED)
    model.answer("How long is the warranty?", CHUNKS)
    (kwargs,) = calls.calls
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["max_tokens"] == MAX_TOKENS == 8192
    assert kwargs["betas"] == [BETA_FALLBACK] == ["server-side-fallback-2026-07-01"]
    assert kwargs["fallbacks"] == "default"
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["system"] == SYSTEM_PROMPT
    assert set(kwargs) == {
        "model",
        "max_tokens",
        "betas",
        "fallbacks",
        "output_config",
        "system",
        "messages",
    }
    assert not FORBIDDEN_KEYS & set(kwargs)
    assert "format" not in kwargs["output_config"]
    (turn,) = kwargs["messages"]
    assert turn["role"] == "user"  # no assistant prefill
    *docs, question = turn["content"]
    assert question == {"type": "text", "text": "How long is the warranty?"}
    assert docs == [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": c.text},
            "title": f"{c.source}#{c.id}",
            "citations": {"enabled": True},
        }
        for c in CHUNKS
    ]


def test_effort_and_model_are_configurable() -> None:
    client = FakeClient(CITED)
    ClaudeAnswerModel(lambda: client, model="claude-other", effort="high").answer("q", CHUNKS)
    kwargs = client.messages.calls[0]
    assert (kwargs["model"], kwargs["output_config"]) == ("claude-other", {"effort": "high"})


def test_response_text_and_citations_are_mapped(caplog: pytest.LogCaptureFixture) -> None:
    model, _ = model_with(CITED)
    with caplog.at_level(logging.WARNING):
        answer = model.answer("q", CHUNKS)
    assert answer.text == "The warranty lasts 7 days. Drills are quarterly."
    assert answer.citations == [
        Citation(source="warranty-policy.md", quote="7-day warranty", chunk_id=11),
        Citation(source="release-checklist.pdf", quote="quarterly", chunk_id=12),
    ]
    assert answer.found is True
    assert "out of range" in caplog.text


def test_answer_without_citations_is_not_found() -> None:
    model, _ = model_with(message([{"type": "text", "text": "Not in the documents."}]))
    answer = model.answer("q", CHUNKS)
    assert (answer.text, answer.citations, answer.found) == ("Not in the documents.", [], False)


def test_fallback_model_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    model, _ = model_with(message([{"type": "text", "text": "x"}], model="claude-fallback"))
    with caplog.at_level(logging.INFO):
        model.answer("q", CHUNKS)
    assert "claude-fallback" in caplog.text


@pytest.mark.parametrize(
    ("details", "category"),
    [(None, None), ({"type": "refusal", "category": "cyber"}, "cyber")],
)
def test_refusal_raises(details: dict[str, Any] | None, category: str | None) -> None:
    resp = message(
        [{"type": "text", "text": "partial"}], stop_reason="refusal", stop_details=details
    )
    model, _ = model_with(resp)
    with pytest.raises(LLMRefusalError) as info:
        model.answer("q", CHUNKS)
    assert info.value.category == category


def test_max_tokens_with_text_is_used(caplog: pytest.LogCaptureFixture) -> None:
    resp = message([{"type": "text", "text": "cut short"}], stop_reason="max_tokens")
    model, _ = model_with(resp)
    with caplog.at_level(logging.WARNING):
        assert model.answer("q", CHUNKS).text == "cut short"
    assert "max_tokens" in caplog.text


def test_max_tokens_without_text_raises() -> None:
    resp = message(
        [{"type": "thinking", "thinking": "", "signature": "s"}], stop_reason="max_tokens"
    )
    model, _ = model_with(resp)
    with pytest.raises(LLMIncompleteError):
        model.answer("q", CHUNKS)


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls: type[anthropic.APIStatusError], code: int) -> anthropic.APIStatusError:
    response = httpx2.Response(code, request=REQUEST, headers={"request-id": "req_123"})
    return cls("boom sk-ant-secret", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (status_error(anthropic.AuthenticationError, 401), LLMAuthError),
        (status_error(anthropic.PermissionDeniedError, 403), LLMAuthError),
        (status_error(anthropic.RateLimitError, 429), LLMRateLimitError),
        (status_error(anthropic.InternalServerError, 500), LLMUnavailableError),
        (status_error(anthropic.BadRequestError, 400), LLMUnavailableError),
        (anthropic.APIConnectionError(request=REQUEST), LLMUnavailableError),
        (anthropic.APITimeoutError(request=REQUEST), LLMUnavailableError),
    ],
)
def test_sdk_errors_become_domain_errors(
    error: Exception, expected: type[Exception], caplog: pytest.LogCaptureFixture
) -> None:
    model, _ = model_with(error)
    with caplog.at_level(logging.DEBUG), pytest.raises(expected) as info:
        model.answer("q", CHUNKS)
    assert "sk-ant-secret" not in str(info.value)
    assert "sk-ant-secret" not in caplog.text


def test_status_code_is_kept() -> None:
    model, _ = model_with(status_error(anthropic.InternalServerError, 503))
    with pytest.raises(LLMUnavailableError) as info:
        model.answer("q", CHUNKS)
    assert info.value.status_code == 503


def test_client_is_created_lazily_and_once() -> None:
    created: list[FakeClient] = []

    def factory() -> FakeClient:
        created.append(FakeClient(CITED))
        return created[-1]

    model = ClaudeAnswerModel(client_factory=factory, model="m", effort="low")
    assert created == []
    model.answer("q", CHUNKS)
    model.answer("q", CHUNKS)
    assert len(created) == 1


def test_default_factory_uses_official_sdk_without_key_argument() -> None:
    from tests.conftest import NetworkBlockedError

    model = ClaudeAnswerModel(model="m", effort="low")
    with pytest.raises(NetworkBlockedError):
        model.answer("q", CHUNKS)


def test_fake_model_records_calls_and_cites_first_chunk() -> None:
    fake = FakeAnswerModel()
    answer = fake.answer("q", CHUNKS)
    assert fake.calls == [("q", CHUNKS)]
    assert answer.found is True
    assert answer.citations == [Citation("warranty-policy.md", CHUNKS[0].text[:60], 11)]
    assert isinstance(fake, AnswerModel)
    assert isinstance(ClaudeAnswerModel(model="m", effort="low"), AnswerModel)


def test_fake_model_without_chunks_is_not_found() -> None:
    assert FakeAnswerModel().answer("q", []).found is False


def test_non_char_location_citations_are_ignored() -> None:
    page_cite = {
        "type": "page_location",
        "cited_text": "x",
        "document_index": 0,
        "document_title": "t",
        "start_page_number": 1,
        "end_page_number": 2,
    }
    model, _ = model_with(message([{"type": "text", "text": "a", "citations": [page_cite]}]))
    assert model.answer("q", CHUNKS).citations == []
