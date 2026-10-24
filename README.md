# Kaikeel DocQA

Ask questions about your own documents and get answers that cite the exact passages they are based on.
When the documents do not contain the answer, DocQA says so instead of guessing.

DocQA indexes `.md`, `.txt` and `.pdf` files into a single SQLite file, finds relevant passages with BM25
(SQLite FTS5), and asks Claude to answer from those passages using the API's native citations. It ships as a
CLI, a small HTTP API with stateless multi-turn chat, and a sample chat widget.

## Quick start (uv)

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/) (tested with uv 0.6.3).

```bash
git clone <repository-url> docqa && cd docqa
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

The sample documents in `examples/docs/` describe a fictional studio ("Kaikeel Handbook Lite"). They were
written for this demo and may be shared freely.

## HTTP API and chat widget

```bash
uv run uvicorn docqa.api:app --port 8000
```

Open `http://localhost:8000/` for the sample chat widget, or call the API directly:

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
  document says "defect") miss the right file. English plurals and verb forms are handled by stemming. The `Retriever` interface allows a vector or hybrid retriever to be added later without changing
  the API.
- **Follow-up questions.** A follow-up is combined with the previous user question only when it contains a
  reference word ("it", "that", "other", "one", ...). A follow-up without one that still matches something on
  its own, such as "And the price?", is searched as a standalone question and may pick up the wrong item.
  Assistant answers are not used for retrieval. Reference words are English only.
- **The evidence gate is a heuristic.** It was tuned on the sample corpus; see `DOCQA_MIN_COVERAGE` above. A
  question that reuses the documents' words except for one rare word is the hardest case ("What is the price of
  the Enterprise plan?" is rejected, but only just).
- **Index maintenance.** Files deleted from a folder are not removed from the index in v0.1; delete the
  database file and ingest again.
- **PDFs.** Only PDFs with a text layer are supported; scanned PDFs are skipped (no OCR).
- **No authentication or rate limiting** on the API, and no CORS. Run it locally or behind your own gateway.

## Project layout

```
src/docqa/      cli.py, api.py, service.py, chat.py, retriever.py, llm.py, ingest.py, store.py, eval.py
src/docqa/static/index.html   sample chat widget
examples/       sample documents and eval set
docs/           SPEC.md and architecture decision records (docs/adr/)
tests/          pytest suite (offline)
```

## License

MIT, see `LICENSE.md`.

## Support

Built by Kaikeel.
