"""Answer generation with Claude's native citations (ADR 0003), plus a fake for offline tests."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol, runtime_checkable

import anthropic
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaRequestDocumentBlockParam,
)

from docqa.config import Effort
from docqa.errors import (
    LLMAuthError,
    LLMIncompleteError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMUnavailableError,
)
from docqa.models import Answer, Chunk, Citation

logger = logging.getLogger(__name__)

MAX_TOKENS = 8192  # thinking counts towards max_tokens on Opus 5.5, so leave headroom
BETA_FALLBACK = "server-side-fallback-2026-07-01"  # pairs with fallbacks="default"
FAKE_QUOTE_CHARS = 60

SYSTEM_PROMPT = (
    "You answer questions using only the documents provided in the latest user message. "
    "If the documents do not contain the information needed, say clearly that it was not "
    "found in the provided documents. Be concise."
)


@runtime_checkable
class AnswerModel(Protocol):
    def answer(self, question: str, chunks: list[Chunk]) -> Answer:
        """Answer ``question`` from ``chunks`` only, with citations into those chunks."""
        ...


class FakeAnswerModel:
    """Deterministic model for tests: records calls and cites the first chunk."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Chunk]]] = []

    def answer(self, question: str, chunks: list[Chunk]) -> Answer:
        self.calls.append((question, list(chunks)))
        if not chunks:
            return Answer(text="Not found in the provided documents.", citations=[], found=False)
        first = chunks[0]
        quote = first.text[:FAKE_QUOTE_CHARS]
        citation = Citation(source=first.source, quote=quote, chunk_id=first.id)
        return Answer(
            text=f"According to {first.source}: {quote}", citations=[citation], found=True
        )


def _default_client() -> anthropic.Anthropic:
    # Looked up at call time; the SDK reads ANTHROPIC_API_KEY from the environment itself.
    return anthropic.Anthropic()


class ClaudeAnswerModel:
    """Calls Claude through the official SDK; the client is created on first use."""

    def __init__(
        self,
        client_factory: Callable[[], anthropic.Anthropic] = _default_client,
        *,
        model: str,
        effort: Effort,
    ) -> None:
        self._client_factory = client_factory
        self._client: anthropic.Anthropic | None = None
        self.model = model
        self.effort = effort

    def answer(self, question: str, chunks: list[Chunk]) -> Answer:
        response = self._create(self._messages(question, chunks))
        return self._parse(response, chunks)

    def _messages(self, question: str, chunks: list[Chunk]) -> list[BetaMessageParam]:
        documents: list[BetaContentBlockParam] = [_document_block(c) for c in chunks]
        content: list[BetaContentBlockParam] = [*documents, {"type": "text", "text": question}]
        return [{"role": "user", "content": content}]

    def _create(self, messages: list[BetaMessageParam]) -> BetaMessage:
        if self._client is None:
            self._client = self._client_factory()
        try:
            # Typed against the installed SDK: mypy checks betas/fallbacks/output_config here.
            response: BetaMessage = self._client.beta.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                betas=[BETA_FALLBACK],
                fallbacks="default",
                output_config={"effort": self.effort},
                system=SYSTEM_PROMPT,
                messages=messages,
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise LLMAuthError() from None
        except anthropic.RateLimitError:
            raise LLMRateLimitError() from None
        except anthropic.APIStatusError as exc:
            logger.warning(
                "Claude API error: status=%s request_id=%s", exc.status_code, exc.request_id
            )
            raise LLMUnavailableError(status_code=exc.status_code) from None
        except anthropic.APIConnectionError as exc:
            logger.warning("Claude API connection error: %s", type(exc).__name__)
            raise LLMUnavailableError() from None
        return response

    def _parse(self, response: BetaMessage, chunks: list[Chunk]) -> Answer:
        if response.stop_reason == "refusal":
            details = response.stop_details
            raise LLMRefusalError(category=details.category if details else None)
        if response.model != self.model:
            logger.info("Answer served by fallback model %s", response.model)

        parts: list[str] = []
        citations: list[Citation] = []
        seen: set[tuple[int, str]] = set()
        for block in response.content:
            if block.type != "text":
                continue  # thinking, fallback and any other block types carry no answer text
            parts.append(block.text)
            for cited in block.citations or []:
                if cited.type != "char_location":
                    continue
                index = cited.document_index
                if not 0 <= index < len(chunks):
                    logger.warning("Ignoring citation with document_index %d out of range", index)
                    continue
                chunk = chunks[index]
                key = (chunk.id, cited.cited_text)
                if key not in seen:
                    seen.add(key)
                    citations.append(
                        Citation(source=chunk.source, quote=cited.cited_text, chunk_id=chunk.id)
                    )
        text = "".join(parts)
        if response.stop_reason == "max_tokens":
            if not text:
                raise LLMIncompleteError()
            logger.warning("Answer truncated at max_tokens=%d", MAX_TOKENS)
        return Answer(text=text, citations=citations, found=bool(citations))


def _document_block(chunk: Chunk) -> BetaRequestDocumentBlockParam:
    return {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": chunk.text},
        "title": f"{chunk.source}#{chunk.id}",
        "citations": {"enabled": True},
    }
