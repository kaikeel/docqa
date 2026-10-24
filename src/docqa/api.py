"""HTTP API (FastAPI). Run with: uvicorn docqa.api:app --port 8000"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from docqa import __version__
from docqa.config import CHAT_CHARS_CAP, CHAT_MESSAGES_CAP, Settings
from docqa.errors import AnswerError, ChatHistoryError, DocQAError, IngestError, LLMRateLimitError
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


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the service at start-up so bad settings or an unusable index stop the server
    with a clear message, instead of a healthy-looking server that answers 500 (QA #2, #7)."""
    build = app.dependency_overrides.get(get_service, get_service)
    try:
        build()
    except DocQAError as exc:
        logger.error("DocQA cannot start: %s", exc)
        raise RuntimeError(f"DocQA cannot start: {exc}") from None
    yield


app = FastAPI(
    title="Kaikeel DocQA",
    version=__version__,
    description="Answers questions from your documents, with verifiable citations.",
    lifespan=lifespan,
)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)

# Every error response has the shape {"detail": {"code", "message"}} (QA #8).
_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail: object = exc.detail
    if not isinstance(detail, dict):  # Starlette's own errors carry a plain string
        detail = {"code": _HTTP_CODES.get(exc.status_code, "http_error"), "message": str(detail)}
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Location, message and type only: the user's input is not echoed back.
    errors = [
        {"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    message = "; ".join(
        f"{'.'.join(str(part) for part in e['loc'][1:]) or 'body'}: {e['msg']}" for e in errors
    )
    detail = {"code": "invalid_request", "message": message, "errors": errors}
    return JSONResponse({"detail": detail}, status_code=422)


@app.exception_handler(Exception)
async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Logged with its traceback by the server; the client gets no internals.
    detail = {"code": "internal_error", "message": "Internal server error."}
    return JSONResponse({"detail": detail}, status_code=500)


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


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon() -> Response:
    """No icon: 204 keeps the browser console free of 404 noise (QA #16)."""
    return Response(status_code=204)


@app.get("/health")
def health(service: ServiceDep) -> dict[str, str]:
    """200 only if the index can be written; 503 ``index_unavailable`` otherwise."""
    try:
        service.store.check_writable()
    except DocQAError as exc:
        logger.error("Health check failed: %s", exc)
        raise _error(503, "index_unavailable", "The index cannot be written.") from None
    return {"status": "ok"}


@app.post("/ingest")
def ingest(body: IngestRequest, service: ServiceDep) -> IngestResponse:
    root = service.settings.ingest_root.resolve()
    try:
        target = (root / body.path).resolve()  # absolute paths replace root; checked below
    except (ValueError, OSError):  # e.g. an embedded NUL character
        raise _error(400, "invalid_path", "The path is not valid.") from None
    if not target.is_relative_to(root):
        raise _error(400, "path_outside_root", "Path must be inside DOCQA_INGEST_ROOT.")
    try:
        # Symlinked files may point anywhere inside the ingest root, never outside it.
        report = service.ingest(Path(target), allowed_root=root)
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
