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
