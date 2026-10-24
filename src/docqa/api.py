"""HTTP API (FastAPI). Run with: uvicorn docqa.api:app --port 8000"""

from __future__ import annotations

import base64
import hashlib
import re
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from docqa import __version__
from docqa.config import CHAT_CHARS_CAP, CHAT_MESSAGES_CAP, Settings
from docqa.errors import AnswerError, ChatHistoryError, IngestError, LLMRateLimitError
from docqa.models import Answer, ChatTurn
from docqa.service import DocQAService

# Largest accepted request body. A full widget request (20 messages of 2000 characters, even
# in 3-byte UTF-8) is about 120 KiB.
MAX_BODY_BYTES = 256 * 1024
_TOO_LARGE = {
    "code": "request_too_large",
    "message": f"The request body must be at most {MAX_BODY_BYTES} bytes.",
}


class BodySizeLimitMiddleware:
    """Reject request bodies over ``max_bytes`` with 413, before they are parsed (SEC M2).

    Checks Content-Length up front and also counts streamed (chunked) bodies as they arrive.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = Headers(scope=scope).get("content-length", "")
        if length.isdigit() and int(length) > self.max_bytes:
            response = JSONResponse({"detail": _TOO_LARGE}, status_code=413)
            await response(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # FastAPI re-raises HTTPException from body reading as is.
                    raise HTTPException(status_code=413, detail=_TOO_LARGE)
            return message

        await self.app(scope, limited_receive, send)


app = FastAPI(
    title="Kaikeel DocQA",
    version=__version__,
    description="Answers questions from your documents, with verifiable citations.",
)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)


def _inline_hash(html: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", html, re.DOTALL)
    if match is None:
        raise RuntimeError(f"widget has no inline <{tag}>")
    digest = hashlib.sha256(match.group(1).encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


# Read once at import; hashes are derived from the file, so editing it never breaks the CSP.
WIDGET_HTML = files("docqa").joinpath("static/index.html").read_text("utf-8")
WIDGET_HEADERS = {
    "Content-Security-Policy": (
        f"default-src 'none'; script-src {_inline_hash(WIDGET_HTML, 'script')}; "
        f"style-src {_inline_hash(WIDGET_HTML, 'style')}; connect-src 'self'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, description="Folder inside DOCQA_INGEST_ROOT.")


class IngestResponse(BaseModel):
    documents: int
    chunks: int
    skipped: list[str]
    unchanged: int


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    k: int | None = Field(default=None, ge=1, le=20)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    # Hard cap; the configurable DOCQA_CHAT_MAX_CHARS (<= this) is applied by the service.
    content: str = Field(max_length=CHAT_CHARS_CAP)


class ChatRequest(BaseModel):
    """Shape only; limits (DOCQA_CHAT_*) and role order are checked by chat.validate_history."""

    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(max_length=CHAT_MESSAGES_CAP)
    k: int | None = Field(default=None, ge=1, le=20)


class CitationOut(BaseModel):
    source: str
    quote: str


class AnswerResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    found: bool

    @classmethod
    def from_answer(cls, answer: Answer) -> AnswerResponse:
        return cls(
            answer=answer.text,
            citations=[CitationOut(source=c.source, quote=c.quote) for c in answer.citations],
            found=answer.found,
        )


@lru_cache(maxsize=1)
def get_service() -> DocQAService:
    """One service per process, configured from the environment (overridden in tests)."""
    return DocQAService.from_settings(Settings.from_env())


ServiceDep = Annotated[DocQAService, Depends(get_service)]


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _llm_error(exc: AnswerError) -> HTTPException:
    status = 429 if isinstance(exc, LLMRateLimitError) else 502
    return _error(status, exc.code, str(exc))


# HEAD too, so `curl -I /` can check the security headers.
@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
def widget() -> HTMLResponse:
    """Sample chat widget (ADR 0006): same origin as the API, data rendered via textContent."""
    return HTMLResponse(WIDGET_HTML, headers=WIDGET_HEADERS)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
def ingest(body: IngestRequest, service: ServiceDep) -> IngestResponse:
    root = service.settings.ingest_root.resolve()
    target = (root / body.path).resolve()  # absolute paths replace root; checked below
    if not target.is_relative_to(root):
        raise _error(400, "path_outside_root", "Path must be inside DOCQA_INGEST_ROOT.")
    try:
        report = service.ingest(Path(target))
    except IngestError:
        raise _error(400, "ingest_error", f"{body.path} is not a directory.") from None
    return IngestResponse(
        documents=report.documents,
        chunks=report.chunks,
        skipped=report.skipped,
        unchanged=report.unchanged,
    )


@app.post("/ask")
def ask(body: AskRequest, service: ServiceDep) -> AnswerResponse:
    try:
        answer = service.ask(body.question, body.k)
    except AnswerError as exc:
        raise _llm_error(exc) from None
    return AnswerResponse.from_answer(answer)


@app.post("/chat")
def chat(body: ChatRequest, service: ServiceDep) -> AnswerResponse:
    messages = [ChatTurn(role=m.role, content=m.content) for m in body.messages]
    try:
        answer = service.chat(messages, body.k)
    except ChatHistoryError as exc:
        raise _error(422, exc.code, str(exc)) from None
    except AnswerError as exc:
        raise _llm_error(exc) from None
    return AnswerResponse.from_answer(answer)
