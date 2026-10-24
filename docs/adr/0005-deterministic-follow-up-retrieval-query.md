# 5. Deterministic retrieval query for follow-up questions (no LLM rewriting)

Date: 2026-10-25 · Status: Accepted · Author: sol-architect

## Context
AC8: a follow-up such as "And what about the other one?" must retrieve the right document thanks to the
previous turn. BM25 on the follow-up alone finds nothing (all tokens are stopwords) or the wrong thing.
The test suite must run offline (AC5) and the not-found path must not call the model (AC2 rule).

Options considered:
1. **LLM query rewriting** (ask Claude to turn the follow-up into a standalone question). Best quality, but an
   extra paid call per turn, non-deterministic, impossible to test offline, and it would call the model even
   when the answer is "not found".
2. **Concatenate the whole history** into the query. Topic drift: old terms outrank the new question.
3. **Latest question + the previous user question, with a fixed rule.** Deterministic, pure, cheap.

## Decision
Option 3, implemented as the pure function `chat.retrieval_queries(messages) -> list[str]`:
- `latest` = last user message; `previous` = the user message immediately before it (assistant turns ignored).
- No `previous` → `[latest]`.
- `latest` contains a reference word (`REFERENCE_WORDS`: it, its, this, that, these, those, they, them, their,
  other, another, one, ones, same, else, former, latter) → `[latest + "\n" + previous]`.
- Otherwise → `[latest, latest + "\n" + previous]`: try the standalone question first, fall back to the
  combined query only if it returns nothing.
- The service tries the queries in order and stops at the first non-empty result. `REFERENCE_WORDS` are a
  subset of the retriever's stopwords, so they never match documents by themselves.

## Consequences
- Fully offline and unit-testable; AC8 is proven with the sample docs and the fake model.
- No extra model calls; the not-found path still never touches the API.
- Known limitation (documented in README): a follow-up without a reference word that still matches something
  on its own ("And the price?") is searched as a standalone question. Assistant answers are not used for
  retrieval. English reference words only, matching the English sample docs.
- The rule lives behind one function, so it can later be swapped for LLM rewriting without touching the API.
