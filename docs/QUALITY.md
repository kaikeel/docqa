# How v0.1.0 was checked

This page summarises the quality and security process behind DocQA v0.1.0: what was checked, what failed the
first time, how it was fixed, which tools were run, and which risks remain. It is a summary of the internal
QA and security reports for this release, limited to technical content.

## Process

1. **QA round 1: fail.** A QA review, run separately from development, went through the acceptance criteria on
   a clean clone (uv and Docker), the API and CLI edge cases, and the widget in headless Chrome. Result: 5 major
   and 11 minor defects.
2. **Security gate round 1: fail.** A separate security review found 3 medium findings (M1 to M3 below) and
   several low ones.
3. **Fix round.** Each defect was fixed or, where it was accepted as a limitation, documented in the README.
   The evidence gate was redesigned (ADR 0007).
4. **QA round 2: pass.** All 16 round-1 defects were re-checked with their original reproduction steps and
   closed. Three new minor issues were found (see below).
5. **Security gate round 2: pass.** No critical, high or medium findings left in the code, dependencies, image
   or git history.

Neither QA nor the security review called the Anthropic API. The answer path was tested with a fake answer
model and a fake SDK client, and the test suite blocks network access. The checks that need a real API key
are not part of these results.

## Main defects from round 1 and how they were fixed

| Area | Problem found | Fix |
|---|---|---|
| Evidence gate | The gate was a raw BM25 score threshold. It rejected short natural questions such as "What is the warranty?", and it had been tuned on the same questions it was measured on. | Replaced by IDF-weighted query coverage of the best passage (`DOCQA_MIN_COVERAGE`), porter stemming in FTS5, calibration on a dev set and a check on a separate holdout set written before calibration (ADR 0007). |
| Ingest (security M1) | A symlinked file inside the ingest root that pointed outside it was read and could be quoted in answers. | Symlinked files are read only if they resolve inside the ingested folder (`DOCQA_INGEST_ROOT` for the API); others are skipped as "symlink outside root". Symlinked folders are not followed. |
| Input limits (security M2) | The `/chat` length limit was measured after stripping whitespace but the unstripped text was sent on, so padding bypassed it; request bodies had no size limit. | The stripped text is validated and sent; bodies over 256 KiB get `413`, including chunked bodies without `Content-Length`. |
| Docker | `docker run --env-file .env` with the example file failed with a `500`, because the example pointed the index at the read-only `/app`. | The example no longer sets that path; invalid settings or an unusable index stop the API at start-up with a clear message, and `GET /health` returns `503` if the index cannot be written. |
| Widget | After an answer longer than the chat limit, every following message failed, so the widget was stuck. | Earlier answers are shortened to `DOCQA_CHAT_MAX_CHARS` instead of rejected, on both the server and the widget. |
| CI (security M3) | GitHub Actions were referenced by movable tags. | Pinned to full commit SHAs (tag in a comment), checked by a test, and updated by Dependabot. |

Other round-1 fixes include: an invalid ingest path with an embedded NUL returns `400 invalid_path` instead of
`500`; every API error is JSON with a code and validation errors no longer echo the input; files with the same
relative name in two ingested folders no longer overwrite each other; the Docker image no longer contains uv or
its cache.

## Round 2 results

| Check | Result |
|---|---|
| Tests | 243 passed, 99.81% line and branch coverage, with no network access |
| Lint and types | `ruff check`, `ruff format --check` and `mypy` (strict) clean |
| Retrieval eval, dev set | hit@3 0.968 (30/31), unanswerable questions stopped by the gate 8/8 |
| Retrieval eval, holdout set | hit@3 0.833 (20/24), stopped 11/11 |
| New QA question set (47 questions written after the threshold was set) | hit@3 0.867 (26/30), stopped 13/17 (76%) |
| Clean clone, uv | Clone, `uv sync --locked`, ingest and a first "not found" answer in about 12 seconds with an empty uv cache |
| Widget in headless Chrome | Suggested questions, a 2,654-character answer followed by 13 more turns without an error, a follow-up that reaches both plan files, injected HTML not executed, no console or CSP errors |

New minor issues from round 2:

- **The gate lets some "looks answerable but is not" questions through**, such as "What does the Gold support
  plan cost?" (4 of 17 on the new set), and blocks a few rephrased answerable ones (3 of 30). A threshold sweep
  from 0.35 to 0.70 found no value that separates the two groups on that set, so the threshold was kept and the
  README describes the limitation. Those questions reach Claude, which has to answer "not found" itself.
- **Long unbroken strings overflowed the widget's message bubbles.** Fixed before release.
- **A start-up failure logs a short traceback** after the clear error message. Cosmetic; still open.

## Tools run by the security gate

| Tool | Version | Scope | Result |
|---|---|---|---|
| gitleaks | 8.30.1 | Full git history (all refs, merge diffs, dangling commits) and the working tree | No leaks found |
| pip-audit | 2.10.1 | Locked dependencies with hashes, PyPI and OSV advisory sources | No known vulnerabilities |
| bandit | 1.9.4 | `src`, `scripts` | No high or medium findings; one low finding, a false positive (an SQL string in a variable named `_TOKEN_SQL`) |
| semgrep | 1.182.1 | Python, OWASP Top 10, security-audit, secrets, Dockerfile, GitHub Actions and JavaScript rulesets on `src`, `Dockerfile`, `.github` | No findings in `src` or the widget; one finding on the Dependabot config (no `cooldown`). `--config auto` was not run because it requires sending metrics. |
| trivy | 0.76.1 | Docker image (vulnerabilities, secrets, misconfiguration) and Dockerfile | 8 high Debian CVEs in the base image, all without a fix available; 0 with `--ignore-unfixed`; no critical. Secret hits were false positives in SDK docstrings. Misconfiguration: 0 high or critical |

The security gate also re-ran the round-1 proof-of-concept inputs and variants against the API, the CLI and a
local container: symlink chains, absolute and nested symlinks, `..` and Unicode path tricks, multi-megabyte
whitespace padding, chunked bodies, malformed JSON, and error responses carrying marker strings. It confirmed
that the image runs as a non-root user (uid 10001), cannot write to `/app`, and contains no `.env` file,
database or uv binary.

## Accepted risks

These were accepted for v0.1.0 and are listed in the README under Known limitations where they affect users.

- **Base image CVEs.** `python:3.12-slim` has known Debian CVEs with no fix available yet. No code path in DocQA
  uses the affected packages directly. The base image is not pinned by digest; rebuild when Debian ships fixes.
- **No authentication or rate limiting.** Anyone who can reach the API can ingest folders inside
  `DOCQA_INGEST_ROOT` and spend the API key. The README publishes the Docker port on `127.0.0.1` only and
  recommends an authenticating reverse proxy. The OpenAPI pages are enabled.
- **Prompt injection from documents.** Text in an ingested document can try to steer the answer. Quotes are
  verbatim citations returned by the API, the model has no tools, and the widget renders text only, but only
  ingest documents you trust.
- **Hardlinks and links inside the root.** A hardlink to a file outside the ingest root cannot be told apart
  from a normal file and is indexed. A symlink to a hidden file inside the root is followed. Exploiting either
  requires write access to the document folder.
- **Other low findings still open:** a few malformed ingest paths (a path that is too long, a symlink loop)
  return a generic `500` JSON error instead of `400`, without leaking details; the Dependabot configuration has
  no cooldown period.
