# Kaikeel DocQA

Ask questions about your own documents and get answers that cite the exact passages they are based on.
When the documents do not contain the answer, DocQA says so instead of guessing.

DocQA indexes `.md`, `.txt` and `.pdf` files into a single SQLite file, finds relevant passages with BM25
(SQLite FTS5), and asks Claude to answer from those passages using the API's native citations. It ships as a
CLI, a small HTTP API with stateless multi-turn chat, and a sample chat widget.

![The DocQA sample widget in Chrome. The user asks "What support plans do you have?" and gets a short answer
describing the Starter and Pro plans, followed by two numbered citations from support-plan-starter.md and
support-plan-pro.txt. The user then asks "And what about the other one?" and gets a longer answer about the Pro
plan, followed by citations that quote individual lines of support-plan-pro.txt.](docs/images/widget-chat.jpg)

*The sample widget on the sample documents. The answers in this screenshot were produced by the local-only
Claude Code backend described in [See it without an API key](#see-it-without-an-api-key), not by the Anthropic
API path that DocQA ships; retrieval, the follow-up handling and the widget are DocQA's own.*

[See it without an API key](#see-it-without-an-api-key) ·
[Measured results](#measured-results) ·
[Why DocQA](#why-docqa) ·
[Adapt it to your documents](#adapt-it-to-your-documents) ·
[Quick start](#quick-start-uv) ·
[Quality process](docs/QUALITY.md)

## See it without an API key

**Recorded answers.** `examples/recorded/` holds three request/response pairs in the exact JSON shape of
`POST /ask` and `POST /chat`, plus the passages that retrieval sent to the model:

| File | What it shows |
|---|---|
| [`ask-warranty.json`](examples/recorded/ask-warranty.json) | "What is the warranty?" is answered from `warranty-policy.md` with two verbatim quotes (7-day warranty, what it covers). |
| [`ask-gold-plan-not-found.json`](examples/recorded/ask-gold-plan-not-found.json) | "What does the Gold support plan cost?" There is no Gold plan. This question passes the evidence gate (coverage 0.55, threshold 0.5), so the model is called; it answers "Not found in the provided documents." with no citations and `found: false`. |
| [`chat-support-plans.json`](examples/recorded/chat-support-plans.json) | Two `/chat` turns, as in the screenshot: "What support plans do you have?" (Starter and Pro, one quote each), then "And what about the other one?" (the Pro plan, eight quotes from `support-plan-pro.txt`). |

Where these come from, stated plainly: they were recorded with **Claude Opus 4.8 through the Claude Code CLI**
(`claude -p`), using a **local-only experimental backend that is not part of this repository**. They are not
output of DocQA's Anthropic API path. On that backend the model is asked to return its quotes as JSON, and a
quote is kept only if it appears verbatim in the passage it names. DocQA itself (`docqa.llm.ClaudeAnswerModel`)
uses the Anthropic API's native citations instead, so wording and citation choice can differ. Ingest,
retrieval, the evidence gate, the follow-up handling, request validation and the response shape are DocQA's
own code. Each file repeats this note and lists the model IDs the CLI reported.

**Reproduce the retrieval part yourself** (no key, no network after `uv sync`):

```bash
uv run docqa ingest examples/docs && uv run docqa eval examples/eval_holdout.jsonl --retrieval-only
```

Output on a fresh clone:

```
Ingested 10 documents, 23 chunks; skipped: none
cases: 35
hit@3: 0.833 (20/24 answerable)
unanswerable rejected: 11/11 (retrieval found nothing)
```

A "not found" answer is also produced without a key, because the model is never called for it:
`uv run docqa ask "What is the airspeed of an unladen swallow?"` prints `Not found in the provided documents.`

## Measured results

Retrieval and evidence-gate results on the sample documents (10 files, 23 passages), top 3 passages:

| Question set | Questions (answerable / not) | hit@3 | Unanswerable stopped by the gate |
|---|---|---|---|
| Dev, `examples/eval.jsonl` (used to calibrate the gate) | 39 (31 / 8) | 0.968 (30/31) | 8/8 |
| Holdout, `examples/eval_holdout.jsonl` (written before calibration, not used for tuning) | 35 (24 / 11) | 0.833 (20/24) | 11/11 |
| Independent QA set (written by the QA reviewer after the threshold was set; not in this repository) | 47 (30 / 17) | 0.867 (26/30) | 13/17 (76%) |

The first two rows are re-run with `uv run docqa eval <file> --retrieval-only` and need no key. The third row
was measured during QA of v0.1.0. `hit@3` is the share of answerable questions with a passage from an expected
file in the top 3. "Stopped by the gate" means retrieval returned nothing, so the answer was "not found" without
a model call; the four that passed on the QA set (for example "What does the Gold support plan cost?") reach
Claude, as in the recorded example above.

Read these numbers for what they are: one small, purpose-written corpus, and an evidence gate that is a
heuristic (see [How it works](#how-it-works)). They measure retrieval, not the quality of Claude's answers, and
they say nothing about your documents until you run the same evaluation on them. Cost and latency have not been
measured.

## Why DocQA

The main design choice: **"not found" is decided in code, before the model is called, not by asking the model
in a prompt to admit it does not know.** If the best passage does not cover enough of the question, DocQA
answers "Not found in the provided documents." and makes no API call at all. Questions that pass the gate are
still answered only with citations, and `found` is `true` only if the answer carries at least one.

| Often in RAG tutorials | In DocQA | Check it in |
|---|---|---|
| The prompt asks the model to say "I don't know" | An evidence gate in code returns "not found" before any model call | `src/docqa/retriever.py`, `tests/test_service.py::test_not_found_does_not_call_model`, `docs/adr/0007-evidence-gate-query-coverage.md` |
| The model writes its sources into the answer text | Quotes come from the API's native citations (`cited_text`), mapped back to the file; no citation means `found: false` | `src/docqa/llm.py`, `tests/test_llm.py::test_answer_without_citations_is_not_found`, `tests/test_service.py::test_found_requires_citations` |
| No evaluation, or tuned on the questions it is tested on | Retrieval eval that runs without a key, with a dev set and a separate holdout set | `examples/eval.jsonl`, `examples/eval_holdout.jsonl`, `src/docqa/eval.py` |
| The chat UI inserts model output with `innerHTML` | One-file widget that uses `textContent` only, a hash-based Content-Security-Policy and no external requests | `src/docqa/static/index.html`, `tests/test_widget.py` |
| Inputs and ingest paths are not limited | Per-message length limits (after stripping whitespace), a 256 KiB body limit, ingest restricted to one root, symlinks out of it skipped | `tests/test_chat.py`, `tests/test_api.py`, `tests/test_store_ingest.py` |
| Container runs as root, CI uses movable tags, tests call the real API | Non-root Docker image, GitHub Actions pinned to commit SHAs, tests remove the key and block network access | `Dockerfile`, `tests/test_ci.py`, `tests/conftest.py` |

How v0.1.0 was reviewed (two QA rounds and two security reviews by AI agents separate from development, with human sign-off, and what was found and fixed) is in
[`docs/QUALITY.md`](docs/QUALITY.md).

## Adapt it to your documents

1. **Index your files.** `uv run docqa ingest /path/to/your/docs` reads `.md`, `.txt` and PDFs with a text layer.
   Re-running it skips unchanged files. Deleted files stay in the index until you delete the database file and
   ingest again.
2. **Write a small eval set and tune the gate on it.** Put 30 or more of your users' real questions in a JSONL
   file (`{"question": "...", "expected_sources": ["file.md"], "answerable": true}`), including questions your
   documents do not answer. Keep some aside as a holdout you do not tune on. Then compare thresholds:
   ```bash
   DOCQA_MIN_COVERAGE=0.4 uv run docqa eval my_eval.jsonl --retrieval-only
   DOCQA_MIN_COVERAGE=0.6 uv run docqa eval my_eval.jsonl --retrieval-only
   ```
   Lower values answer more questions and let more unanswerable ones reach Claude; higher values do the
   opposite. Check the chosen value on the holdout set before using it.
3. **Embed the widget** on the same origin as the API, or put DocQA behind your domain with a reverse proxy
   (see [Embedding the widget](#embedding-the-widget)). Cross-origin embedding is not supported in v0.1.
4. **Know the retrieval limits.** BM25 matches words, not meaning, so synonyms are missed (see
   [Known limitations](#known-limitations)). To go further, implement the `Retriever` protocol in
   `src/docqa/retriever.py` (`search(query, k) -> list[Chunk]`) with a vector or hybrid search. The evidence
   gate lives inside `FTS5Retriever`, so a new retriever needs its own evidence check and its own evaluation.
5. **Deploy behind authentication.** The API has no authentication or rate limiting, and anyone who can reach it
   can spend your API key and ingest folders under `DOCQA_INGEST_ROOT`. Put it behind a reverse proxy that
   authenticates users, do not expose `POST /ingest` or the OpenAPI pages (`/docs`, `/redoc`, `/openapi.json`)
   publicly, and point `DOCQA_INGEST_ROOT` at your documents only.

## Quick start (uv)

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/) (tested with uv 0.6.3).

```bash
git clone https://github.com/kaikeel/docqa.git docqa && cd docqa
uv sync --locked                       # creates .venv with pinned dependencies
uv run docqa ingest examples/docs      # indexes the sample documents into ./docqa.db
```

Indexing, retrieval and the evaluation run without an API key. A "not found" answer also works without a key:

```bash
uv run docqa ask "What is the airspeed of an unladen swallow?"
# Not found in the provided documents.
```

To get real answers, provide your Anthropic API key in the environment (it is never read from a file by
DocQA and never logged):

```bash
export ANTHROPIC_API_KEY=...           # your own key
uv run docqa ask "How long is the warranty on a fixed-price project?"
uv run docqa ask --json "How long is the warranty on a fixed-price project?"
```

The plain output prints the answer followed by numbered citations, `[1] warranty-policy.md — "..."`.
`--json` prints the same structure as `POST /ask`: `{"answer", "citations": [{"source", "quote"}], "found"}`.

The sample documents in `examples/docs/` describe a fictional studio ("Kaikeel Handbook Lite"): warranty,
support plans (Starter and Pro), delivery and release process, incident response, estimates and change
requests, coding standards, security checklist and client communication. They were written for this demo and
may be shared freely. Questions to try:

- "What is the warranty?" or "How quickly are critical defects fixed?"
- "What support plans do you have?", then "And what about the other one?" (chat)
- "How do you handle incidents?", "What is a change request?", "How often is a rollback drill rehearsed?"

Questions about things the documents do not cover ("What is the warranty on hardware?") get "Not found".

## HTTP API and chat widget

```bash
uv run uvicorn docqa.api:app --port 8000
```

Open `http://localhost:8000/` for the sample chat widget (it shows three example questions you can click), or
call the API directly:

| Endpoint | Request | Response |
|---|---|---|
| `GET /health` | — | `{"status": "ok"}`, or `503` if the index cannot be written |
| `GET /` | — | Sample chat widget (HTML) |
| `POST /ingest` | `{"path": "examples/docs"}` (inside `DOCQA_INGEST_ROOT`) | `{"documents", "chunks", "skipped", "unchanged"}` |
| `POST /ask` | `{"question": "...", "k": 5}` (`k` optional, 1–20) | `{"answer", "citations": [{"source", "quote"}], "found"}` |
| `POST /chat` | `{"messages": [{"role": "user" \| "assistant", "content": "..."}], "k": 5}` | same as `/ask` |

```bash
curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "How long is the warranty on a fixed-price project?"}'

curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' -d '{"messages": [
  {"role": "user", "content": "What does the Starter plan include?"},
  {"role": "assistant", "content": "Up to 4 hours of maintenance work per month, ..."},
  {"role": "user", "content": "And what about the other one?"}
]}'
```

Errors always have the shape `{"detail": {"code": "...", "message": "..."}}`:

| Status | `code` | When |
|---|---|---|
| `400` | `path_outside_root`, `ingest_error`, `invalid_path` | `/ingest` path outside `DOCQA_INGEST_ROOT`, not a folder, or not a valid path |
| `404` / `405` | `not_found` / `method_not_allowed` | Unknown path or wrong HTTP method |
| `413` | `request_too_large` | Request body over 256 KiB |
| `422` | `invalid_request` | Body does not match the schema (also lists `errors: [{"loc", "msg", "type"}]`) |
| `422` | `chat_history_invalid` | `/chat` history breaks a rule (see below) |
| `429` | `llm_rate_limited` | The Claude API rate limit was reached |
| `500` | `internal_error` | Unexpected server error (details only in the server log) |
| `502` | `llm_auth`, `llm_unavailable`, `llm_refusal`, `llm_incomplete` | Missing or invalid key, API unavailable, refusal, or no answer within `max_tokens` |
| `503` | `index_unavailable` | `GET /health` only: the index cannot be written |

### Chat

`POST /chat` is stateless: the client sends the whole conversation each time and the server stores nothing.
Rules: at most `DOCQA_CHAT_MAX_MESSAGES` messages, roles alternate, and the first and last messages come from
the user. Messages are stripped of surrounding whitespace; each user message may then be at most
`DOCQA_CHAT_MAX_CHARS` characters. Assistant messages are sent back as plain text, and earlier answers longer
than `DOCQA_CHAT_MAX_CHARS` are shortened to that length rather than rejected (they are context only). Request
bodies larger than 256 KiB get `413`.

Two scenarios on the sample documents (both covered by tests with a fake model):

1. "What does the Starter plan include?" then "How much does it cost?": the follow-up is searched together with
   the previous question, so the answer cites `support-plan-starter.md`.
2. "What does the Starter plan include?" then "And what about the other one?": the follow-up alone matches
   nothing; with the previous question, both `support-plan-starter.md` and `support-plan-pro.txt` are passed to
   Claude, which picks "the other one".

### Embedding the widget

The widget is one self-contained file, `src/docqa/static/index.html` (no framework, no external requests). It
must be served from the same origin as the API, as `GET /` does, because it calls `fetch("/chat")` and the
Content-Security-Policy only allows `connect-src 'self'`. To place it on another site, put DocQA behind the same
domain with a reverse proxy, or copy the file and serve it next to the API. Embedding from a different origin
would need CORS and a looser `frame-ancestors` policy; v0.1 does not do this.

## Docker

```bash
docker build -t docqa .
docker run --rm -p 127.0.0.1:8000:8000 -e ANTHROPIC_API_KEY docqa
```

Or keep the settings in a file (the key stays out of your shell history):

```bash
cp .env.example .env            # then put your key after ANTHROPIC_API_KEY=
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env docqa
```

In another terminal:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/ingest -H 'Content-Type: application/json' -d '{"path": "examples/docs"}'
curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "How long is the warranty on a fixed-price project?"}'
```

The image runs as a non-root user, contains the sample documents under `/app/examples`, and stores the index
in `/data/docqa.db` (`/data` is the only writable folder; do not set `DOCQA_DB` to a path elsewhere). Add
`-v docqa-data:/data` to keep the index between runs. The key is passed at run time and is never part of the
image. `127.0.0.1:` publishes the port on this machine only: the API has no authentication, and anyone who can
reach it can spend your API key.

If the settings are invalid or the index cannot be opened, the container stops at start-up with a message such
as `DocQA cannot start: cannot open the index ...`. `GET /health` returns `503` with code `index_unavailable` if
the index stops accepting writes.

## Configuration

All settings are environment variables (see `.env.example`). DocQA does not load `.env` files itself; use
`export`, `set -a; . ./.env; set +a`, or Docker's `--env-file`.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Needed only for answers with evidence and the full eval. Read by the Anthropic SDK. |
| `DOCQA_MODEL` | `claude-opus-5-5` | Claude model. |
| `DOCQA_EFFORT` | `low` | Effort level sent to the API: `low`, `medium`, `high`, `xhigh` or `max`. |
| `DOCQA_DB` | `./docqa.db` (Docker: `/data/docqa.db`) | SQLite index file; its folder must be writable. |
| `DOCQA_TOP_K` | `5` | Passages sent to Claude per question. |
| `DOCQA_MIN_COVERAGE` | `0.5` | Share of the question (0 to 1, rare words weigh more) that the best passage must contain to count as evidence (see below). |
| `DOCQA_INGEST_ROOT` | current directory (Docker: `/app`) | `POST /ingest` only accepts folders inside this directory. |
| `DOCQA_CHAT_MAX_MESSAGES` | `20` | Maximum messages per `/chat` request (at most 100). |
| `DOCQA_CHAT_MAX_CHARS` | `2000` | Maximum characters per `/chat` user message; longer earlier answers are shortened to this length (at most 32000). |

## How it works

1. **Ingest.** Files are split into overlapping passages of up to 800 characters (150 overlap, cut at
   whitespace; PDFs page by page) and stored in SQLite with an FTS5 full-text index. Re-ingesting skips files
   whose content hash has not changed and replaces the passages of files that have. Hidden files and folders
   are skipped, symlinked folders are not followed, and a symlinked file is read only if it points inside the
   folder being ingested (for `POST /ingest`: inside `DOCQA_INGEST_ROOT`).
2. **Retrieve.** The question is reduced to its content words (stopwords and FTS5 operators removed, English
   word forms stemmed so "plans" matches "plan") and ranked with BM25. Then an evidence gate checks how much of
   the question the best passage covers: the share of the question's words found in it, each weighted by how
   rare it is in your documents (a word that appears nowhere weighs the most). Below `DOCQA_MIN_COVERAGE` the
   answer is "Not found in the provided documents." and Claude is not called at all.
3. **Answer.** Each passage is sent to Claude as a document block with citations enabled. The API returns the
   answer with the exact quoted text and the document it came from; DocQA maps that back to the file name. It
   does not ask the model to write citations itself, so quotes are verbatim.
4. **Found.** An answer counts as found only if it carries at least one citation. If Claude says the documents
   do not cover the question and cites nothing, `found` is `false`.

`DOCQA_MIN_COVERAGE = 0.5` was calibrated on the dev set `examples/eval.jsonl` only, and checked on a separate
holdout set, `examples/eval_holdout.jsonl`, that was written before calibration and not used to tune anything.
Short questions such as "What is the warranty?" pass (the warranty passage covers the whole question), while
"What is the warranty on hardware?" does not ("hardware" is nowhere in the documents). The method, the
alternatives and the misses are in `docs/adr/0007-evidence-gate-query-coverage.md`. The gate is a heuristic
tuned on one small corpus: run the evaluation on your own questions and adjust the value.

## Evaluation

```bash
uv run docqa ingest examples/docs
uv run docqa eval examples/eval.jsonl --retrieval-only --k 3           # dev set, no API key needed
uv run docqa eval examples/eval_holdout.jsonl --retrieval-only --k 3   # holdout set
```

Output on the sample documents:

```
cases: 39
hit@3: 0.968 (30/31 answerable)
unanswerable rejected: 8/8 (retrieval found nothing)
cases: 35
hit@3: 0.833 (20/24 answerable)
unanswerable rejected: 11/11 (retrieval found nothing)
```

`hit@k` is the share of answerable questions with at least one passage from an expected file in the top k.
Without `--retrieval-only` the command also asks Claude every question (needs a key, makes one API call per
answerable question) and reports `citation_rate` and `not_found_accuracy`. Each line of the eval file is
`{"question": "...", "expected_sources": ["file.md"], "answerable": true}`.

## Running tests

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest --cov=docqa --cov-fail-under=80
```

The tests never call the Anthropic API: they use a fake answer model or a fake SDK client, and a fixture
removes `ANTHROPIC_API_KEY` and blocks network connections for the whole run.

## Known limitations

- **Lexical search.** BM25 matches words, not meaning. Synonyms and different word forms are missed: the sample
  questions "What linter do you use?" (the document says "linted with ruff") and "How do I report a bug?" (the
  document says "defect") miss the right file. English plurals and verb forms are handled by stemming. The `Retriever` interface allows a
  vector or hybrid retriever to be added later without changing the API.
- **Follow-up questions.** A follow-up is combined with the previous user question only when it contains a
  reference word ("it", "that", "other", "one", ...). A follow-up without one that still matches something on
  its own, such as "And the price?", is searched as a standalone question and may pick up the wrong item.
  Assistant answers are not used for retrieval. Reference words are English only.
- **The evidence gate is a heuristic.** It was tuned on the sample corpus; see `DOCQA_MIN_COVERAGE` above. A
  question that reuses the documents' words except for one rare word is the hardest case ("What is the price of
  the Enterprise plan?" is rejected, but only just). On questions written after tuning, about one in four
  "looks answerable but is not" questions (asking about a plan or price that does not exist) still pass the gate.
  They then reach Claude, which is instructed to answer only from the cited passages and to say when the
  documents do not contain the answer, so treat the gate as a cost saver, not as the only guard.
- **Index maintenance.** Files deleted from a folder are not removed from the index in v0.1; delete the
  database file and ingest again.
- **Languages.** Stopwords, stemming and follow-up reference words are English. Vietnamese works with or
  without diacritics. Chinese, Japanese and Korean are not segmented into words, so a search for part of a
  sentence (for example `保修` inside `保修政策…`) finds nothing.
- **PDFs.** Only PDFs with a text layer are supported; scanned PDFs are skipped (no OCR). pypdf may print
  warnings for damaged PDFs on stderr in addition to the `skipped` line.
- **Duplicate names.** Files are tracked by their absolute path, so two folders can both contain
  `warranty-policy.md`; citations show the path relative to the ingested folder, so both are cited under the
  same name.
- **Symlinks.** Symlinked folders are not followed, and symlinked files are only read if they point inside the
  ingested folder (`DOCQA_INGEST_ROOT` for the API); others are listed as "symlink outside root".
- **One shared index.** `POST /ingest` accepts any folder inside `DOCQA_INGEST_ROOT`, and everything ingested
  goes into the same index; there is no way to remove a folder except deleting the database file. The
  `skipped` list names every skipped file and can be long. Point `DOCQA_INGEST_ROOT` at your documents, not at
  a folder that also contains code or virtual environments.
- **No authentication or rate limiting** on the API, and no CORS. Anyone who can reach it can ingest folders
  and spend your API key: run it locally (`-p 127.0.0.1:...` with Docker) or behind your own gateway. The
  OpenAPI pages (`/docs`, `/redoc`, `/openapi.json`) are enabled.
- **Untrusted documents.** Text in an ingested document can try to steer the answer (prompt injection).
  Citations are always verbatim quotes returned by the API, but only ingest documents you trust.
- **Base image.** `python:3.12-slim` currently has known Debian CVEs without a fix available; rebuild the image
  when Debian publishes fixes.

## Project layout

```
src/docqa/      cli.py, api.py, service.py, chat.py, retriever.py, llm.py, ingest.py, store.py, eval.py
src/docqa/static/index.html   sample chat widget
examples/       sample documents and eval set
docs/adr/       architecture decision records
tests/          pytest suite (offline)
```

## License

MIT, see `LICENSE.md`.

## Support

Built by Kaikeel. How this release was tested and reviewed: [`docs/QUALITY.md`](docs/QUALITY.md).
