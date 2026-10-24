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


def test_get_service_builds_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCQA_DB", str(tmp_path / "env.db"))
    api.get_service.cache_clear()
    try:
        service = api.get_service()
        assert service.settings.db_path == tmp_path / "env.db"
        assert api.get_service() is service
    finally:
        api.get_service.cache_clear()
