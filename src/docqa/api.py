"""HTTP API (FastAPI). Run with: uvicorn docqa.api:app --port 8000"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from docqa import __version__
from docqa.config import Settings
from docqa.errors import AnswerError, IngestError, LLMRateLimitError
from docqa.models import Answer
from docqa.service import DocQAService

app = FastAPI(
    title="Kaikeel DocQA",
    version=__version__,
    description="Answers questions from your documents, with verifiable citations.",
)


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
