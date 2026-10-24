"""Pure chat logic: history validation and deterministic retrieval queries (ADR 0004, 0005)."""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence

from docqa.errors import ChatHistoryError
from docqa.models import ChatTurn

# Words that point back to an earlier turn. All of them are retriever stopwords, so they never
# match documents themselves (tested).
REFERENCE_WORDS = frozenset(
    """
    it its this that these those they them their
    other another one ones same else former latter
    """.split()  # noqa: SIM905
)
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def prepare_history(messages: Sequence[ChatTurn], max_chars: int) -> list[ChatTurn]:
    """Normalise a history into exactly what will be validated and sent to the model.

    Every message is stripped, so length checks measure the text that is actually sent
    (whitespace padding cannot slip past the limit). Earlier assistant answers are cut to
    ``max_chars``: they were produced by the server (up to the model's max_tokens), and they
    are context only (ADR 0004), so a long answer must never make the next request invalid.
    """
    prepared: list[ChatTurn] = []
    for turn in messages:
        content = turn.content.strip()
        if turn.role == "assistant":
            content = content[:max_chars].rstrip()
        prepared.append(ChatTurn(role=turn.role, content=content))
    return prepared


def validate_history(messages: Sequence[ChatTurn], max_messages: int, max_chars: int) -> None:
    """Raise ChatHistoryError naming the first rule the history breaks."""
    if len(messages) < 1:
        raise ChatHistoryError("messages must contain at least 1 message")
    if len(messages) > max_messages:
        raise ChatHistoryError(f"messages must contain at most {max_messages} messages")
    for number, turn in enumerate(messages, start=1):
        # Length is measured on the content as given (prepare_history has already stripped
        # it), i.e. on exactly what is sent to the model.
        if not turn.content.strip():
            raise ChatHistoryError(f"message {number} is empty")
        if len(turn.content) > max_chars:
            raise ChatHistoryError(f"message {number} is longer than {max_chars} characters")
    if messages[0].role != "user":
        raise ChatHistoryError("messages must start with a user message")
    if messages[-1].role != "user":
        raise ChatHistoryError("messages must end with a user message (the new question)")
    for previous, current in itertools.pairwise(messages):
        if previous.role == current.role:
            raise ChatHistoryError("message roles must alternate between user and assistant")


def retrieval_queries(messages: Sequence[ChatTurn]) -> list[str]:
    """Queries to try in order for the latest user question (ADR 0005)."""
    user_turns = [turn.content for turn in messages if turn.role == "user"]
    latest = user_turns[-1]
    if len(user_turns) < 2:
        return [latest]
    combined = f"{latest}\n{user_turns[-2]}"
    if REFERENCE_WORDS.intersection(w.lower() for w in _WORD_RE.findall(latest)):
        return [combined]
    return [latest, combined]
