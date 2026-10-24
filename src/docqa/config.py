"""Runtime settings, read from environment variables in one place.

The Anthropic API key is deliberately not part of Settings: the official SDK reads
ANTHROPIC_API_KEY from the environment itself, so the key never passes through DocQA code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

from docqa.errors import DocQAError

Effort = Literal["low", "medium", "high", "xhigh", "max"]
EFFORTS: tuple[str, ...] = get_args(Effort)

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT: Effort = "low"
DEFAULT_DB = "./docqa.db"
DEFAULT_TOP_K = 5
DEFAULT_CHAT_MAX_MESSAGES = 20
DEFAULT_CHAT_MAX_CHARS = 2000
# Calibrated on examples/ (T11, see README and docs/adr/0002): the highest-scoring
# unanswerable sample question scores 2.67, the weakest answerable hit 4.52.
DEFAULT_MIN_SCORE = 3.0


@dataclass(frozen=True)
class Settings:
    model: str
    effort: Effort
    db_path: Path
    top_k: int
    min_score: float
    ingest_root: Path
    chat_max_messages: int = DEFAULT_CHAT_MAX_MESSAGES
    chat_max_chars: int = DEFAULT_CHAT_MAX_CHARS

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            model=os.environ.get("DOCQA_MODEL") or DEFAULT_MODEL,
            effort=_effort(),
            db_path=Path(os.environ.get("DOCQA_DB") or DEFAULT_DB),
            top_k=_positive_int("DOCQA_TOP_K", DEFAULT_TOP_K),
            min_score=_float("DOCQA_MIN_SCORE", DEFAULT_MIN_SCORE),
            ingest_root=Path(os.environ.get("DOCQA_INGEST_ROOT") or os.getcwd()).resolve(),
            chat_max_messages=_positive_int("DOCQA_CHAT_MAX_MESSAGES", DEFAULT_CHAT_MAX_MESSAGES),
            chat_max_chars=_positive_int("DOCQA_CHAT_MAX_CHARS", DEFAULT_CHAT_MAX_CHARS),
        )


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise DocQAError(f"{name} must be an integer, got {raw!r}") from None
    if value < 1:
        raise DocQAError(f"{name} must be >= 1, got {value}")
    return value


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise DocQAError(f"{name} must be a number, got {raw!r}") from None


def _effort() -> Effort:
    raw = os.environ.get("DOCQA_EFFORT") or DEFAULT_EFFORT
    if raw not in EFFORTS:
        raise DocQAError(f"DOCQA_EFFORT must be one of {', '.join(EFFORTS)}, got {raw!r}")
    return cast(Effort, raw)
