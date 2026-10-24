# 7. Evidence gate on IDF-weighted query coverage, with porter stemming

Date: 2026-10-25 · Status: Accepted · Author: eng-developer (QA fix round 1) · Supersedes: the
"Calibration" section of ADR 0002 (threshold on the raw BM25 score)

## Context
ADR 0002 gated retrieval on the raw BM25 score of the best chunk (`DOCQA_MIN_SCORE = 3.0`). QA (report of
2026-10-25, bug #1) showed this rejects most short, natural questions even when the right file ranks first:
BM25 grows with the number of matching words, so a question with one or two content words almost never
reaches 3.0 ("What is the warranty?" 1.45, "What support plans do you have?" 2.65, "What is a change request?"
2.95). The value had also been tuned on the same 22 questions it was reported on, all long and specific, so
the reported hit@3 of 0.944 was in-sample. ADR 0002 claimed "short but valid questions still pass", which was
false.

A raw BM25 threshold cannot separate "short question, good match" from "long question, weak match": both have
low scores. What separates answerable from unanswerable questions on the sample corpus is whether the best
passage contains the *distinctive* words of the question. Unanswerable questions contain a topic word the
corpus does not have ("vacation", "trial", "cloud", "Kubernetes"); answerable ones mostly do not.

## Decision
1. **Gate on coverage, not on score.** For the best-ranked chunk, compute
   `coverage = Σ idf(t) for content words t present in the chunk / Σ idf(t) over all content words`,
   with `idf(t) = ln(1 + (N − df(t) + 0.5) / (df(t) + 0.5))` (the BM25 IDF; `N` = chunks, `df` = chunks
   containing `t`). A word that is not in the corpus at all has the highest weight. If
   `coverage < DOCQA_MIN_COVERAGE` (default **0.5**), retrieval returns nothing: "not found", no LLM call.
   Otherwise the whole top-k is returned, as before (weaker chunks are context; `found` still requires a
   citation). Presence is checked with FTS5 `MATCH` restricted to the chunk, so it uses exactly the same
   tokenizer as the search.
2. **Porter stemming.** The FTS5 tokenizer becomes `porter unicode61 remove_diacritics 2`, so "plans" matches
   "plan", "licences" matches "licence", "included" matches "includes". Without it, coverage would punish
   ordinary word forms. Existing index files are refused with a clear message ("delete the file and ingest
   again"), tracked with `PRAGMA user_version`.
3. **Question fillers are stopwords**: `long often many quickly soon get got need want know happen happens`
   ("How long…", "How often…", "What happens…").
4. `DOCQA_MIN_SCORE` is removed; `DOCQA_MIN_COVERAGE` must be a finite number in [0, 1] (QA #13: `nan` is now
   rejected at start-up).

Alternatives considered:
- *BM25 score divided by the number of content words.* On the dev set the ranges overlap (answerable as low as
  0.70, unanswerable as high as 1.31), because a single common word ("warranty", in 7 of 23 chunks) has a low
  IDF and therefore a low score even when it is the whole question.
- *Unweighted share of words present.* "What is the price of a domain name?" has 1 of 3 words present, the
  same as several answerable questions with one filler word; without IDF weights "domain" counts no more than
  "price".
- *Coverage over the union of the top-k chunks.* Raises unanswerable questions too (filler words are found
  somewhere); the top-1 chunk is stricter and easier to explain.

## Calibration (dev only) and holdout check
Method: the original `examples/eval.jsonl` (22 questions) became the **dev** set and gained 17 questions: the
13 short questions QA listed in its report (they motivated the change, so they are "seen" data) and 4 new
unanswerable ones. `examples/eval_holdout.jsonl` (35 questions: 24 answerable, 11 unanswerable, written as a
first-time visitor would ask: "Do you have meetings?", "pricing", "What is the warranty on hardware?") was
**written before any coverage number was computed, and evaluated once, after the design and value were
fixed**. It was not edited afterwards.

Coverage of the best chunk on dev (porter + fillers): unanswerable questions top out at 0.42 ("How do I apply
for a job?"), answerable ones start at 0.43 ("What is the release process?": the release checklist never says
"process"), then 0.59. Every value in (0.43, 0.59] gives the same dev result; 0.5 is in the middle. Values in
(0.42, 0.43] would give 31/31 but sit on a single question.

| Set | Cases | hit@3 | Unanswerable rejected |
|---|---|---|---|
| dev (`eval.jsonl`, calibration) | 39 | 0.968 (30/31) | 8/8 |
| original 22 questions (subset of dev) | 22 | 1.000 (18/18) | 4/4 |
| holdout (`eval_holdout.jsonl`, untouched) | 35 | 0.833 (20/24) | 11/11 |
| *old gate, `DOCQA_MIN_SCORE=3.0`, for comparison: original 22* | 22 | 0.944 (17/18) | 4/4 |

Holdout misses, all lexical: "Where do secrets go?" (coverage 0.25) and "What linter do you use?" (0.28; the
document says "linted") are rejected by the gate; "How do I report a bug?" (the document says "defect") and
"What are your business hours?" pass the gate but rank other files first. The closest unanswerable holdout
question is "What is the price of the Enterprise plan?" at 0.45, below 0.5 but not by much: a question that
reuses the corpus vocabulary except for one rare word is the hardest case for any lexical gate.

## Consequences
- Short questions whose words appear in the documents now reach Claude ("What is the warranty?" → coverage
  1.0). Claude may still answer "not found" and `found` stays `false` without a citation, so the gate only has
  to be good enough to avoid wasting API calls and to say "not found" quickly; it is not the last line.
- The gate is less corpus-specific than a raw BM25 score (it is a ratio between 0 and 1), but it is still a
  heuristic tuned on one small corpus. Users should run `docqa eval` on their own questions and adjust
  `DOCQA_MIN_COVERAGE`. Synonyms and paraphrases remain out of reach for BM25 (README "Known limitations").
- Cost: one small FTS5 query per content word of the question to compute `df` and presence; a 2000-character
  query takes about 10 ms on the sample index.
- Porter stemming is English. Vietnamese without diacritics still matches (both sides are stemmed the same
  way); Chinese is still not segmented (known limitation).
