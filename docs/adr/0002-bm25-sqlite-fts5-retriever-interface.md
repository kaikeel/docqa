# 2. BM25 with SQLite FTS5 behind a `Retriever` interface (no vector DB in v0.1)

Date: 2026-10-25 · Status: Accepted · Author: sol-architect

## Context
DocQA v0.1 is an internal portfolio project with an appetite of at most one AI work-day. AC4 requires a
retrieval eval that runs without any API key (hit@3 ≥ 0.8 on the sample set), AC5 requires all tests to run
offline, and AC6 requires a stranger to reach a first answer in ≤ 10 minutes. Vector search would need either
an embeddings API (key + network in eval/tests) or a local embedding model (large download, slow Docker build),
plus a vector store (pgvector/Qdrant/Chroma = extra service or dependency). `PROJECT.md` explicitly lists vector
DB / embeddings as out of scope.

AC2 also needs a deterministic "no evidence" signal so we can answer "not found" without calling the LLM.

## Decision
- Store chunks in a single SQLite file with an external-content FTS5 table (`unicode61 remove_diacritics 2`).
- Rank with FTS5 `bm25()`; expose `score = -bm25()` (higher is better).
- Sanitize user queries into quoted tokens joined by `OR` (stopwords removed) so FTS5 operators in user input
  cannot cause syntax errors or change query semantics.
- Apply a configurable score threshold (`DOCQA_MIN_SCORE`, calibrated on `examples/eval.jsonl`). Nothing above
  the threshold → `found=false`, LLM is not called.
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
