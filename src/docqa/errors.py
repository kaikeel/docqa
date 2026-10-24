"""Domain errors with messages that are safe to show to end users (never include secrets)."""

from __future__ import annotations


class DocQAError(Exception):
    """Base class for all DocQA errors."""

    code = "docqa_error"


class IngestError(DocQAError):
    """A directory or file could not be ingested."""

    code = "ingest_error"


class AnswerError(DocQAError):
    """The answer model failed."""

    code = "answer_error"


class LLMAuthError(AnswerError):
    code = "llm_auth"

    def __init__(self, message: str = "ANTHROPIC_API_KEY is missing or invalid.") -> None:
        super().__init__(message)


class LLMRateLimitError(AnswerError):
    code = "llm_rate_limited"

    def __init__(
        self, message: str = "The Claude API rate limit was reached. Retry later."
    ) -> None:
        super().__init__(message)


class LLMUnavailableError(AnswerError):
    code = "llm_unavailable"

    def __init__(self, status_code: int | None = None) -> None:
        self.status_code = status_code
        detail = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"The Claude API is unavailable{detail}. Retry later.")


class LLMRefusalError(AnswerError):
    code = "llm_refusal"

    def __init__(self, category: str | None = None) -> None:
        self.category = category
        detail = f" (category: {category})" if category else ""
        super().__init__(f"The model declined to answer this question{detail}.")
