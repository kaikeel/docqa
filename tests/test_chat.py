"""Chat core (ADR 0004, 0005) and the AC8 follow-up scenarios on examples/docs.

Scenarios (also in README):
  (a) "What does the Starter plan include?" -> follow-up "How much does it cost?"
      -> evidence from support-plan-starter.md (file A).
  (b) "What does the Starter plan include?" -> follow-up "And what about the other one?"
      -> chunks sent to the model include support-plan-starter.md (A) and
      support-plan-pro.txt (B); choosing "the other one" is Claude's job (CEO G3 check).
"""

from dataclasses import replace
from pathlib import Path

import pytest

from docqa.chat import REFERENCE_WORDS, prepare_history, retrieval_queries, validate_history
from docqa.config import Settings
from docqa.errors import ChatHistoryError, DocQAError
from docqa.models import ChatTurn
from docqa.retriever import STOPWORDS
from docqa.service import NOT_FOUND_TEXT
from tests.helpers import make_service

Q1 = "What does the Starter plan include?"
A1 = "It includes up to 4 hours of maintenance work per month."


def u(text: str) -> ChatTurn:
    return ChatTurn(role="user", content=text)


def a(text: str) -> ChatTurn:
    return ChatTurn(role="assistant", content=text)


# --- retrieval_queries -------------------------------------------------------------


def test_single_turn_uses_latest_only() -> None:
    assert retrieval_queries([u("pricing?")]) == ["pricing?"]


def test_reference_word_combines_with_previous_user_question() -> None:
    msgs = [u(Q1), a(A1), u("How much does it cost?")]
    assert retrieval_queries(msgs) == ["How much does it cost?\n" + Q1]


def test_standalone_question_is_tried_first() -> None:
    msgs = [u(Q1), a(A1), u("Explain the rollback drill")]
    assert retrieval_queries(msgs) == [
        "Explain the rollback drill",
        "Explain the rollback drill\n" + Q1,
    ]


def test_only_the_previous_user_turn_is_used_and_assistant_ignored() -> None:
    msgs = [u("first topic"), a("pro plan answer"), u("second topic"), a("x"), u("And that?")]
    assert retrieval_queries(msgs) == ["And that?\nsecond topic"]


def test_reference_words_are_stopwords() -> None:
    assert REFERENCE_WORDS <= STOPWORDS


# --- validate_history ----------------------------------------------------------------


def test_valid_history_passes() -> None:
    validate_history([u(Q1), a(A1), u("And the other one?")], max_messages=20, max_chars=2000)


@pytest.mark.parametrize(
    ("messages", "fragment"),
    [
        ([], "at least 1"),
        ([u("q"), a("a"), u("q")], "at most 2"),
        ([u("   ")], "empty"),
        ([u("x" * 11)], "longer than 10"),
        ([a("hi"), u("q")], "start with a user"),
        ([u("q"), a("a")], "end with a user"),
        ([u("q"), u("q2")], "alternate"),
    ],
)
def test_invalid_histories_name_the_rule(messages: list[ChatTurn], fragment: str) -> None:
    max_messages = 2 if len(messages) == 3 else 20
    with pytest.raises(ChatHistoryError, match=fragment):
        validate_history(messages, max_messages=max_messages, max_chars=10)


def test_prepare_history_strips_and_shortens_answers() -> None:
    # What is measured is exactly what is sent: whitespace is stripped first, and earlier
    # answers (which the server itself produced, up to max_tokens) are cut to max_chars
    # instead of being rejected (QA #3, #4 / SEC M2).
    prepared = prepare_history([u("  q  "), a("  " + "y" * 30), u("\n n \t")], max_chars=10)
    assert prepared == [u("q"), a("y" * 10), u("n")]


def test_padding_does_not_hide_a_long_user_message() -> None:
    prepared = prepare_history([u("x" * 11 + " " * 1000)], max_chars=10)
    with pytest.raises(ChatHistoryError, match="longer than 10"):
        validate_history(prepared, max_messages=20, max_chars=10)


def test_chat_history_error_code() -> None:
    assert ChatHistoryError("x").code == "chat_history_invalid"


# --- settings ---------------------------------------------------------------------


def test_chat_limits_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings.from_env()
    assert (s.chat_max_messages, s.chat_max_chars) == (20, 2000)
    monkeypatch.setenv("DOCQA_CHAT_MAX_MESSAGES", "4")
    monkeypatch.setenv("DOCQA_CHAT_MAX_CHARS", "100")
    s = Settings.from_env()
    assert (s.chat_max_messages, s.chat_max_chars) == (4, 100)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DOCQA_CHAT_MAX_MESSAGES", "zero"),
        ("DOCQA_CHAT_MAX_CHARS", "zero"),
        ("DOCQA_CHAT_MAX_MESSAGES", "101"),  # above the hard cap of the API schema
        ("DOCQA_CHAT_MAX_CHARS", "32001"),
    ],
)
def test_invalid_chat_limits(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(DocQAError, match=name):
        Settings.from_env()


# --- service.chat on examples/docs (AC8) ------------------------------------------


def test_chat_followup_same_item(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    answer = service.chat([u(Q1), a(A1), u("How much does it cost?")])
    assert answer.found is True
    assert answer.citations[0].source == "support-plan-starter.md"
    question, _chunks, history = factory.model.calls[0]
    assert question == "How much does it cost?"
    assert history == (u(Q1), a(A1))


def test_chat_followup_other_item(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    followup = "And what about the other one?"
    assert service.retriever.search(followup, 5) == []
    service.chat([u(Q1), a(A1), u(followup)])
    sources = {c.source for c in factory.model.calls[0][1]}
    assert {"support-plan-starter.md", "support-plan-pro.txt"} <= sources


def test_chat_not_found_does_not_call_model(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    answer = service.chat([u("Tell me about zeppelins"), a("?"), u("And their airships?")])
    assert (answer.text, answer.found) == (NOT_FOUND_TEXT, False)
    assert factory.calls == 0 and factory.model.calls == []


def test_chat_validates_with_settings_limits(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    service.settings = replace(service.settings, chat_max_messages=1)
    with pytest.raises(ChatHistoryError):
        service.chat([u(Q1), a(A1), u("And the other one?")])
    assert factory.calls == 0


def test_chat_single_turn_behaves_like_ask(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    answer = service.chat([u("How long is the warranty on a fixed-price project?")], k=3)
    assert answer.citations[0].source == "warranty-policy.md"
    assert len(factory.model.calls[0][1]) <= 3


def test_chat_sends_the_stripped_question(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    service.chat([u("How long is the warranty on a fixed-price project?" + " " * 100_000)])
    question, _chunks, _history = factory.model.calls[0]
    assert question == "How long is the warranty on a fixed-price project?"


def test_long_earlier_answer_is_shortened_not_rejected(tmp_path: Path) -> None:
    service, factory = make_service(tmp_path)
    long_answer = "L" * 2500  # longer than DOCQA_CHAT_MAX_CHARS (2000)
    answer = service.chat([u(Q1), a(long_answer), u("How much does it cost?")])
    assert answer.found is True
    _question, _chunks, history = factory.model.calls[0]
    assert history == (u(Q1), a("L" * 2000))
