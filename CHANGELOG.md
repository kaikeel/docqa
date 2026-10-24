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
- Verified the README on a clean clone without an API key: uv path, retrieval eval, tests and Docker image (T13).

### Changed
- The evidence gate now uses IDF-weighted query coverage of the best passage (`DOCQA_MIN_COVERAGE`, default
  0.5) instead of a raw BM25 score (`DOCQA_MIN_SCORE` removed), so short natural questions such as "What is the
  warranty?" are answered; FTS5 uses porter stemming. Calibrated on the dev set `examples/eval.jsonl` and
  checked on the new holdout set `examples/eval_holdout.jsonl` (ADR 0007). Index files from earlier builds are
  refused with a "delete and ingest again" message (T19).

### Fixed
- `DOCQA_MIN_COVERAGE` values outside [0, 1], `nan` and `inf` are rejected at start-up (T19).
- `/chat` validates the stripped text it actually sends (whitespace padding no longer bypasses the limit),
  shortens earlier answers longer than `DOCQA_CHAT_MAX_CHARS` instead of rejecting them (the widget no longer
  gets stuck after a long answer), and request bodies over 256 KiB get `413` (T20).

