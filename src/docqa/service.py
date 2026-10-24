"""Application service: wires ingest, retrieval and the answer model together."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from docqa.chat import retrieval_queries, validate_history
from docqa.config import Settings
from docqa.ingest import ingest_dir
from docqa.llm import AnswerModel, ClaudeAnswerModel
from docqa.models import Answer, ChatTurn, Chunk, IngestReport
from docqa.retriever import FTS5Retriever, Retriever
from docqa.store import Store

NOT_FOUND_TEXT = "Not found in the provided documents."

ModelFactory = Callable[[], AnswerModel]


class DocQAService:
    """``ask`` never creates the model (or calls the API) when retrieval finds no evidence."""

    def __init__(
        self,
        store: Store,
        retriever: Retriever,
        model_factory: ModelFactory,
        settings: Settings,
    ) -> None:
        self.store = store
        self.retriever = retriever
        self.model_factory = model_factory
        self.settings = settings
        self._model: AnswerModel | None = None

    @classmethod
    def from_settings(
        cls, settings: Settings, model_factory: ModelFactory | None = None
    ) -> DocQAService:
        store = Store(settings.db_path)
        retriever = FTS5Retriever(store, min_score=settings.min_score)

        def claude() -> AnswerModel:
            return ClaudeAnswerModel(model=settings.model, effort=settings.effort)

        return cls(store, retriever, model_factory or claude, settings)

    def ingest(self, root: Path) -> IngestReport:
        return ingest_dir(self.store, root)

    def ask(self, question: str, k: int | None = None) -> Answer:
        chunks = self.retriever.search(question, k or self.settings.top_k)
        if not chunks:
            return Answer(text=NOT_FOUND_TEXT, citations=[], found=False)
        return self._answer(question, chunks, ())

    def chat(self, messages: Sequence[ChatTurn], k: int | None = None) -> Answer:
        """Answer the last user message of a client-held history (ADR 0004, 0005)."""
        validate_history(messages, self.settings.chat_max_messages, self.settings.chat_max_chars)
        limit = k or self.settings.top_k
        chunks: list[Chunk] = []
        for query in retrieval_queries(messages):
            chunks = self.retriever.search(query, limit)
            if chunks:
                break
        if not chunks:
            return Answer(text=NOT_FOUND_TEXT, citations=[], found=False)
        return self._answer(messages[-1].content, chunks, tuple(messages[:-1]))

    def _answer(self, question: str, chunks: list[Chunk], history: tuple[ChatTurn, ...]) -> Answer:
        if self._model is None:
            self._model = self.model_factory()
        result = self._model.answer(question, chunks, history)
        # found means "backed by at least one citation", whatever the model claims.
        return Answer(text=result.text, citations=result.citations, found=bool(result.citations))
