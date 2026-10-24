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

## Calibration (BUILD T11, 2026-10-25, eng-developer)

**Threshold semantics.** `DOCQA_MIN_SCORE` is applied as an *evidence gate on the best match*: if the
top-ranked chunk scores below it, retrieval returns nothing (not found, no LLM call); otherwise the whole
top-k is returned, including weaker chunks. A per-chunk filter (the wording in the original SPEC) cannot
satisfy AC4 and AC8 at the same time on the sample set: the follow-up "And what about the other one?" needs
the Pro plan chunk (score 2.49) next to the Starter chunk (6.93), while the strongest unanswerable question
("How many vacation days do employees get per year?") scores 2.67. With the gate, weaker chunks only add
context; `found` still requires a citation from Claude.

**Value: `DOCQA_MIN_SCORE = 3.0`** (default in `config.py`). Method: ingest `examples/docs`, run every
`examples/eval.jsonl` question with no threshold, record the top score per question
(`docqa eval ... --retrieval-only --k 3` with `DOCQA_MIN_SCORE` overridden), then sweep:

| `DOCQA_MIN_SCORE` | hit@3 (18 answerable) | unanswerable rejected (4) |
|---|---|---|
| 2.5 | 1.000 | 3/4 |
| 2.7 | 1.000 | 4/4 |
| 3.0 (chosen) | 0.944 | 4/4 |
| 3.5 / 4.0 / 4.5 | 0.944 | 4/4 |

2.7 is the only value with 18/18, but it sits 0.03 above the strongest unanswerable question, so it
overfits the sample. Every value in (2.81, 4.52] gives the same result; 3.0 is near the low end so short
but valid questions still pass. The one miss is "Which licences are allowed for dependencies?": the sample
says "licence", and FTS5 does not stem plurals, so the right file scores only 1.97 (a documented BM25
limitation). Scores depend on corpus size and vocabulary; users should re-run this sweep on their own
documents.
