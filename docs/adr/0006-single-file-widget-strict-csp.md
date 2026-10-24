# 6. Sample widget: one self-contained HTML file, `textContent` only, hash-based CSP

Date: 2026-10-25 · Status: Accepted · Author: sol-architect

## Context
Scope adds a sample chat widget at `GET /` that calls `POST /chat` and shows citations under each answer, to
illustrate embedding on a customer site. AC8 requires API data to be rendered with `textContent` (never
`innerHTML`). Out of scope: a full web UI, frameworks, server-side sessions. Answers and quotes come from
user-supplied documents and model output, so they must be treated as untrusted (XSS).

## Decision
- One file `src/docqa/static/index.html` with a single inline `<style>` and a single inline `<script>`; no
  framework, no CDN, no external fonts/images, no inline `on*=` handlers. Conversation state is a JS array in
  page memory (max 20 messages, same as the server default).
- All dynamic content is written via `createElement` + `textContent`. `innerHTML`, `outerHTML`,
  `insertAdjacentHTML`, `document.write`, `eval` and `new Function` are banned and checked by a test.
- FastAPI serves the file (read once via `importlib.resources`) with
  `Content-Security-Policy: default-src 'none'; script-src 'sha256-…'; style-src 'sha256-…'; connect-src 'self';
  img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'`, plus `X-Content-Type-Options:
  nosniff` and `Referrer-Policy: no-referrer`. The hashes are computed from the file at startup, so editing the
  widget never requires editing the policy, and there is no `'unsafe-inline'`.
- No CORS; the widget is same-origin with the API. README explains what to change to embed cross-origin.

## Consequences
- Zero new dependencies; works offline and inside the Docker image.
- Even if a DOM bug slipped in, the CSP blocks injected scripts and outbound requests to other origins.
- Browser behaviour is not exercised in CI (no Playwright, kept out to stay within appetite); the automated
  tests are static checks + TestClient, and a real-browser check is on the CEO's G3 checklist.
- Cross-origin embedding needs CORS and a looser `frame-ancestors`: deliberately not done in v0.1.
