# 2. BM25 with SQLite FTS5 behind a `Retriever` interface (no vector DB in v0.1)

Date: 2026-10-25 · Status: Accepted (threshold and calibration superseded by ADR 0007) · Author: sol-architect

## Context
DocQA v0.1 is an internal portfolio project with an appetite of at most one AI work-day. AC4 requires a
retrieval eval that runs without any API key (hit@3 ≥ 0.8 on the sample set), AC5 requires all tests to run
offline, and AC6 requires a stranger to reach a first answer in ≤ 10 minutes. Vector search would need either
an embeddings API (key + network in eval/tests) or a local embedding model (large download, slow Docker build),
plus a vector store (pgvector/Qdrant/Chroma = extra service or dependency). `PROJECT.md` explicitly lists vector
DB / embeddings as out of scope.

AC2 also needs a deterministic "no evidence" signal so we can answer "not found" without calling the LLM.

## Decision
- Store chunks in a single SQLite file with an external-content FTS5 table (`unicode61 remove_diacritics 2`;
  `porter` stemming added by ADR 0007).
- Rank with FTS5 `bm25()`; expose `score = -bm25()` (higher is better).
- Sanitize user queries into quoted tokens joined by `OR` (stopwords removed) so FTS5 operators in user input
  cannot cause syntax errors or change query semantics.
- Apply a configurable evidence threshold. Nothing above the threshold → `found=false`, LLM is not called.
  (Originally a raw BM25 score, `DOCQA_MIN_SCORE`; replaced by query coverage, `DOCQA_MIN_COVERAGE`, in ADR 0007.)
- Define `Retriever` as a `typing.Protocol` with `search(query: str, k: int) -> list[Chunk]`. `DocQAService`
  depends only on the protocol; `FTS5Retriever` is the only implementation in v0.1.

## Consequences
- Zero extra services or model downloads; SQLite and FTS5 ship with CPython/`python:3.12-slim`. Tests and the
  retrieval eval are fully offline and fast.
- Lexical matching misses paraphrases/synonyms; this is documented in the README and measured by the eval.
- Absolute BM25 scores depend on corpus size and term statistics, so the threshold is corpus-specific. The
  default is tuned on the sample set; users with their own corpus may need to adjust `DOCQA_MIN_SCORE`.
- A future `VectorRetriever` or hybrid retriever (e.g. pgvector, on the Adopt ring) can be added without changing
  the service, API or CLI — only the wiring in the factory.

## Calibration (BUILD T11, 2026-10-25, eng-developer) — superseded by ADR 0007

Kept for history. The gate became an *evidence gate on the best match* (top-1 below the threshold → nothing;
otherwise the whole top-k), which ADR 0007 keeps. The threshold itself was `DOCQA_MIN_SCORE = 3.0` on the raw
BM25 score, tuned on the 22 questions of `examples/eval.jsonl` (hit@3 0.944, 4/4 unanswerable rejected).

**Correction (QA fix round 1):** this section originally said "3.0 is near the low end so short but valid
questions still pass". That was wrong: QA showed most short natural questions score below 3.0 even when the
right file ranks first ("What is the warranty?" 1.45, "What is a change request?" 2.95), and the numbers were
measured on the same questions used for tuning. ADR 0007 replaces the raw score with IDF-weighted query
coverage, calibrated on a dev set and checked on a separate holdout set.
