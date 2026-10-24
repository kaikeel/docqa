# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Project scaffold: uv-managed Python 3.12 package `docqa`, ruff, mypy (strict), pytest with an
  80% coverage gate, and a test guard that blocks real API clients and network access (T1).
- Domain models, error hierarchy and `Settings.from_env` with documented defaults (T2).
- Loaders for `.md`, `.txt` and `.pdf` (per page) and an overlapping, word-boundary-aware chunker (T3).
- SQLite store with an FTS5 index and idempotent, hash-based directory ingest (T4).
- Fictional, publishable sample corpus "Kaikeel Handbook Lite" (10 files including a PDF and two support plans for follow-up chat scenarios) and a 22-question eval set (T5).
- BM25 retriever on SQLite FTS5 behind a `Retriever` protocol, with operator-safe query sanitising and a score threshold (T6).
- `ClaudeAnswerModel` using Claude's native citations through the official SDK (server-side fallback beta, explicit effort), and a `FakeAnswerModel` for offline tests (T7).
- Chat history support in the answer model: earlier turns as plain text, documents only in the latest turn (T15).
- `DocQAService`: ingest and ask, with a not-found path that never creates the model or calls the API (T8).
- Stateless chat core: history validation, deterministic follow-up retrieval queries and `DocQAService.chat` (T16).
- CLI commands `docqa ingest` and `docqa ask` (`--k`, `--db`, `--json`) with documented exit codes (T9).
- HTTP API: `GET /health`, `POST /ingest` (restricted to `DOCQA_INGEST_ROOT`) and `POST /ask` with 429/502 error mapping (T10).
- Stateless `POST /chat` endpoint with the same response schema as `/ask` and 422 `chat_history_invalid` for invalid histories (T17).
- Sample chat widget at `GET /` (single HTML file, `textContent` only) served with a hash-based Content-Security-Policy (T18).
- `docqa eval` with retrieval-only hit@k and full-mode citation rate; `DOCQA_MIN_SCORE` calibrated to 3.0 on the sample set and applied as an evidence gate on the best match (T11).
- Dockerfile (non-root, uv-locked), `.env.example` and README with uv and Docker quick starts, API/chat/widget usage, evaluation and known limitations (T12).
