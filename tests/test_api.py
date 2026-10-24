import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docqa import api
from docqa.errors import (
    AnswerError,
    LLMAuthError,
    LLMIncompleteError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMUnavailableError,
)
from docqa.models import Answer, ChatTurn, Chunk
from docqa.service import DocQAService
from tests.helpers import CountingFactory, make_service

WARRANTY_Q = "How long is the warranty on a fixed-price project?"


@pytest.fixture
def service(tmp_path: Path) -> DocQAService:
    return make_service(tmp_path)[0]


@pytest.fixture
def client(service: DocQAService) -> Iterator[TestClient]:
    api.app.dependency_overrides[api.get_service] = lambda: service
    with TestClient(api.app) as test_client:
        yield test_client
    api.app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_found_schema(client: TestClient) -> None:
    response = client.post("/ask", json={"question": WARRANTY_Q})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"answer", "citations", "found"}
    assert data["found"] is True
    assert data["citations"][0]["source"] == "warranty-policy.md"
    assert set(data["citations"][0]) == {"source", "quote"}


def test_ask_not_found_schema(client: TestClient, service: DocQAService) -> None:
    response = client.post("/ask", json={"question": "zeppelin airships", "k": 3})
    assert response.status_code == 200
    assert response.json() == {
        "answer": "Not found in the provided documents.",
        "citations": [],
        "found": False,
    }
    assert isinstance(service.model_factory, CountingFactory)
    assert service.model_factory.calls == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": "x" * 2001},
        {"question": "ok", "k": 0},
        {"question": "ok", "k": 21},
        {"question": "ok", "extra": 1},
    ],
)
def test_ask_validation(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/ask", json=body).status_code == 422


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (LLMRateLimitError(), 429, "llm_rate_limited"),
        (LLMAuthError(), 502, "llm_auth"),
        (LLMUnavailableError(503), 502, "llm_unavailable"),
        (LLMRefusalError("cyber"), 502, "llm_refusal"),
        (LLMIncompleteError(), 502, "llm_incomplete"),
    ],
)
def test_llm_errors_map_to_status(
    client: TestClient, service: DocQAService, error: AnswerError, status: int, code: str
) -> None:
    class Failing:
        def answer(
            self, question: str, chunks: list[Chunk], history: tuple[ChatTurn, ...] = ()
        ) -> Answer:
            raise error

    service.model_factory = Failing
    response = client.post("/ask", json={"question": WARRANTY_Q})
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code, "message": str(error)}}


def test_ingest_inside_root(client: TestClient, service: DocQAService) -> None:
    response = client.post("/ingest", json={"path": "examples/docs"})
    assert response.status_code == 200
    assert response.json() == {"documents": 0, "chunks": 0, "skipped": [], "unchanged": 10}


@pytest.mark.parametrize("path", ["..", "/etc", "examples/../..", "does-not-exist"])
def test_ingest_outside_root_or_missing_is_400(client: TestClient, path: str) -> None:
    response = client.post("/ingest", json={"path": path})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] in {"path_outside_root", "ingest_error"}


def test_ingest_symlink_escape_is_400(
    client: TestClient, service: DocQAService, tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "escape").symlink_to(tmp_path)
    service.settings = service.settings.__class__(
        **{**service.settings.__dict__, "ingest_root": root}
    )
    response = client.post("/ingest", json={"path": "escape"})
    assert response.status_code == 400


def _with_root(service: DocQAService, root: Path) -> None:
    from dataclasses import replace

    service.settings = replace(service.settings, ingest_root=root)


def test_ingest_file_symlink_escape_is_skipped(
    client: TestClient, service: DocQAService, tmp_path: Path
) -> None:
    (tmp_path / "secret.md").write_text("TOPSECRET outside root password hunter2", "utf-8")
    root = tmp_path / "root"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "link.md").symlink_to(tmp_path / "secret.md")
    _with_root(service, root)
    response = client.post("/ingest", json={"path": "docs"})
    assert response.status_code == 200
    assert response.json()["documents"] == 0
    assert response.json()["skipped"] == ["link.md: symlink outside root"]
    assert client.post("/ask", json={"question": "TOPSECRET hunter2"}).json()["found"] is False


def test_ingest_symlink_inside_ingest_root_is_allowed(
    client: TestClient, service: DocQAService, tmp_path: Path
) -> None:
    root = tmp_path / "root"
    (root / "shared").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "shared" / "faq.md").write_text("zebra crossing rules", "utf-8")
    (root / "docs" / "faq.md").symlink_to(root / "shared" / "faq.md")
    _with_root(service, root)
    response = client.post("/ingest", json={"path": "docs"})
    assert (response.json()["documents"], response.json()["skipped"]) == (1, [])


@pytest.mark.parametrize("path", ["exam\x00ples", "\x00"])
def test_ingest_path_with_nul_is_400(client: TestClient, path: str) -> None:
    response = client.post("/ingest", json={"path": path})  # sent as JSON "\u0000"
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_path"


def test_get_service_builds_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCQA_DB", str(tmp_path / "env.db"))
    api.get_service.cache_clear()
    try:
        service = api.get_service()
        assert service.settings.db_path == tmp_path / "env.db"
        assert api.get_service() is service
    finally:
        api.get_service.cache_clear()


# --- start-up and health (QA #2, #7) ------------------------------------------------


def test_bad_environment_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCQA_EFFORT", "turbo")
    with (
        pytest.raises(RuntimeError, match="DocQA cannot start: DOCQA_EFFORT must be one of"),
        TestClient(api.app),
    ):
        pass


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_unwritable_database_fails_at_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)  # like /app in the image, owned by root
    monkeypatch.setenv("DOCQA_DB", str(locked / "docqa.db"))
    try:
        with (
            pytest.raises(RuntimeError, match=r"cannot open the index .*locked/docqa\.db"),
            TestClient(api.app),
        ):
            pass
    finally:
        locked.chmod(0o700)


def test_startup_builds_the_service_once(tmp_path: Path) -> None:
    with TestClient(api.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    assert api.get_service.cache_info().currsize == 1


def test_health_reports_an_unwritable_index(client: TestClient, service: DocQAService) -> None:
    service.store.conn.execute("PRAGMA query_only = ON")  # every write now fails
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "index_unavailable"
    service.store.conn.execute("PRAGMA query_only = OFF")
    assert client.get("/health").status_code == 200


# --- POST /chat (AC8) -----------------------------------------------------------------

Q1 = {"role": "user", "content": "What does the Starter plan include?"}
A1 = {"role": "assistant", "content": "Up to 4 hours of maintenance per month."}


def test_chat_found_schema_and_history(client: TestClient, service: DocQAService) -> None:
    body = {"messages": [Q1, A1, {"role": "user", "content": "How much does it cost?"}]}
    response = client.post("/chat", json=body)
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"answer", "citations", "found"}
    assert data["found"] is True
    assert data["citations"][0]["source"] == "support-plan-starter.md"
    assert isinstance(service.model_factory, CountingFactory)
    _question, _chunks, history = service.model_factory.model.calls[0]
    assert history == (ChatTurn(**Q1), ChatTurn(**A1))  # type: ignore[arg-type]


def test_chat_not_found_schema(client: TestClient, service: DocQAService) -> None:
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "zeppelins"}]})
    assert response.status_code == 200
    assert response.json() == {
        "answer": "Not found in the provided documents.",
        "citations": [],
        "found": False,
    }
    assert isinstance(service.model_factory, CountingFactory)
    assert service.model_factory.calls == 0


def _with_limits(service: DocQAService, messages: int = 20, chars: int = 2000) -> None:
    from dataclasses import replace

    service.settings = replace(service.settings, chat_max_messages=messages, chat_max_chars=chars)


@pytest.mark.parametrize(
    ("body", "limits"),
    [
        ({"messages": [Q1, A1, Q1]}, {"messages": 2}),
        ({"messages": [{"role": "user", "content": "x" * 51}]}, {"chars": 50}),
        ({"messages": [Q1, A1]}, {}),
        ({"messages": [Q1, Q1]}, {}),
        ({"messages": []}, {}),
        ({"messages": [{"role": "user", "content": "   "}]}, {}),
    ],
)
def test_chat_history_rules_are_422(
    client: TestClient, service: DocQAService, body: dict[str, object], limits: dict[str, int]
) -> None:
    _with_limits(service, **limits)
    response = client.post("/chat", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "chat_history_invalid"
    assert response.json()["detail"]["message"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"messages": [{"role": "system", "content": "hi"}]},
        {"messages": [{"role": "user"}]},
        {"messages": [{"role": "user", "content": "hi", "citations": []}]},
        {"messages": [Q1], "extra": True},
        {"messages": [Q1], "k": 0},
    ],
)
def test_chat_shape_errors_are_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/chat", json=body).status_code == 422


@pytest.mark.parametrize(("error", "status"), [(LLMRateLimitError(), 429), (LLMAuthError(), 502)])
def test_chat_llm_errors(
    client: TestClient, service: DocQAService, error: AnswerError, status: int
) -> None:
    class Failing:
        def answer(
            self, question: str, chunks: list[Chunk], history: tuple[ChatTurn, ...] = ()
        ) -> Answer:
            raise error

    service.model_factory = Failing
    response = client.post("/chat", json={"messages": [Q1]})
    assert response.status_code == status
    assert response.json()["detail"]["code"] == error.code


# --- request limits (QA #3, #4 / SEC M2) ------------------------------------------


def test_widget_flow_survives_an_answer_longer_than_the_chat_limit(
    client: TestClient, service: DocQAService
) -> None:
    """The widget sends the server's own answer back; a long one must not block the chat."""

    class Verbose:
        def answer(
            self, question: str, chunks: list[Chunk], history: tuple[ChatTurn, ...] = ()
        ) -> Answer:
            return Answer(text="L" * 2500, citations=[], found=False)

    service.model_factory = Verbose
    messages: list[dict[str, str]] = [{"role": "user", "content": WARRANTY_Q}]
    first = client.post("/chat", json={"messages": messages})
    assert first.status_code == 200
    messages += [
        {"role": "assistant", "content": first.json()["answer"]},
        {"role": "user", "content": "And how quickly are critical defects fixed?"},
    ]
    second = client.post("/chat", json={"messages": messages})
    assert second.status_code == 200, second.text


@pytest.mark.parametrize(
    "body",
    [
        {"messages": [{"role": "user", "content": "x" * 32_001}]},
        {
            "messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
            * 50
            + [{"role": "user", "content": "q"}]
        },
    ],
    ids=["content-over-hard-cap", "over-100-messages"],
)
def test_chat_schema_hard_caps_are_422(
    client: TestClient, service: DocQAService, body: dict[str, object]
) -> None:
    _with_limits(service, messages=1000, chars=100_000)  # only the schema caps apply
    response = client.post("/chat", json=body)
    assert response.status_code == 422
    assert "chat_history_invalid" not in response.text  # rejected by the schema itself


def test_whitespace_padding_is_rejected_before_parsing(client: TestClient) -> None:
    content = WARRANTY_Q + " " * 1_000_000
    response = client.post("/chat", json={"messages": [{"role": "user", "content": content}]})
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"


def test_body_limit_applies_without_content_length(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"question": "'
        for _ in range(300):
            yield b"a" * 1024
        yield b'"}'

    response = client.post("/ask", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"


def test_body_under_the_limit_is_accepted(client: TestClient) -> None:
    content = "x" * 30_000
    response = client.post("/chat", json={"messages": [{"role": "user", "content": content}]})
    assert response.status_code == 422  # too long for DOCQA_CHAT_MAX_CHARS, but not 413
    assert response.json()["detail"]["code"] == "chat_history_invalid"


# --- one error format everywhere (QA #6, #7, #8), favicon (QA #16) ----------------------


def test_validation_errors_use_the_common_format(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "", "k": 0})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_request"
    assert "question" in detail["message"]
    assert [e["loc"] for e in detail["errors"]] == [["body", "question"], ["body", "k"]]
    assert all("input" not in e for e in detail["errors"])  # user input is not echoed


def test_malformed_json_uses_the_common_format(client: TestClient) -> None:
    response = client.post("/ask", content="{nope", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [("get", "/nope", 404, "not_found"), ("get", "/ask", 405, "method_not_allowed")],
)
def test_http_errors_use_the_common_format(
    client: TestClient, method: str, path: str, status: int, code: str
) -> None:
    response = client.request(method.upper(), path)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["message"]


def test_unexpected_errors_are_json_without_internals(service: DocQAService) -> None:
    class Broken:
        def answer(
            self, question: str, chunks: list[Chunk], history: tuple[ChatTurn, ...] = ()
        ) -> Answer:
            raise RuntimeError("/Users/secret/path sk-ant-api03-FAKE")

    service.model_factory = Broken
    api.app.dependency_overrides[api.get_service] = lambda: service
    try:
        with TestClient(api.app, raise_server_exceptions=False) as client:
            response = client.post("/ask", json={"question": WARRANTY_Q})
    finally:
        api.app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json() == {
        "detail": {"code": "internal_error", "message": "Internal server error."}
    }
    assert "secret" not in response.text


def test_favicon_is_empty_not_404(client: TestClient) -> None:
    assert client.get("/favicon.ico").status_code == 204
    assert client.head("/favicon.ico").status_code == 204
