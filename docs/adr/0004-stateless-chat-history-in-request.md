# 4. Stateless multi-turn chat: history travels in each request, documents only in the latest turn

Date: 2026-10-25 · Status: Accepted · Author: sol-architect

## Context
The scope was extended (acceptance criterion AC8) with `POST /chat`: multi-turn chat for a website support widget,
**without server-side sessions**. We have to decide what the client sends, how it is validated, and how the
conversation is passed to Claude together with the cited `document` blocks (ADR 0003).

Constraints from the current API and SDK (`anthropic==2.3.0`, which sends `anthropic-version: 2026-10-21` by default):
- The Messages API is stateless; the first message must be `user`.
- On API version 2026-10-21 a `document` block in an `assistant` message and a `text` block with non-empty
  `citations` in a `user` message both return 400.
- On Claude Opus 5.5, thinking blocks are bound to the model and the exact prefix that produced them
  ("preserved thinking"); replaying them after editing history is an error on newer accounts.
- Prefill (ending with an assistant turn) is not supported on Opus 5.5.

## Decision
- Request: `{"messages": [{"role": "user"|"assistant", "content": str}], "k"?: int}`; response is the same
  `{answer, citations[{source, quote}], found}` envelope as `/ask`.
- Validation in a pure function (`chat.validate_history`), limits from env: at most `DOCQA_CHAT_MAX_MESSAGES`
  (default 20) messages, each 1..`DOCQA_CHAT_MAX_CHARS` (default 2000) characters after stripping, roles strictly
  alternating, first **and** last message `user`. Any violation → 422 with code `chat_history_invalid`.
- The request to Claude is: earlier turns as plain-string messages (`{"role", "content": str}`), then the latest
  user turn as `[*document_blocks, {"type": "text", "text": latest}]`. Documents are retrieved fresh for the
  latest turn only; earlier turns' documents are not re-sent. The client sends assistant answers back as plain
  text (no citations), so no thinking blocks or citations are ever replayed.
- If retrieval finds nothing, return not-found without creating the model (same rule as AC2).

## Consequences
- No session store, no cleanup, horizontally trivial; refresh = new conversation.
- The request shape satisfies the 2026-10-21 rules and the Opus 5.5 preserved-thinking rules by construction.
- The client controls history, including assistant turns, so a user can put words in the "assistant's mouth".
  Acceptable: the user only affects their own answer, and the system prompt tells the model that earlier turns
  are context, not a source of truth; citations still come only from the documents of the latest turn.
- Cost per turn grows with history; bounded by the two limits. Prompt caching is not used in v0.1.

## Amendment (QA fix round 1, 2026-10-25, eng-developer)
QA found two flaws in the validation rule above (QA #3, #4; SEC M2):
- Lengths were measured after `strip()` but the unstripped text was sent to the model, so whitespace padding
  bypassed the limit, and the request body itself had no size limit.
- Assistant turns were held to `DOCQA_CHAT_MAX_CHARS` although the server itself produces answers up to
  `max_tokens` (8192 tokens), so the widget, which sends answers back, was stuck after one long answer.

New rules: every message is stripped first and the stripped text is both measured and sent
(`chat.prepare_history`). User messages must be 1..`DOCQA_CHAT_MAX_CHARS` characters (422 otherwise). Earlier
assistant answers are **cut** to `DOCQA_CHAT_MAX_CHARS` characters instead of being rejected: they are context
only, and the server must never reject its own output. The widget does the same cut before keeping an answer.
Hard caps before any parsing work: request body ≤ 256 KiB (413 `request_too_large`), at most 100 messages and
32,000 characters per message in the schema (422); `DOCQA_CHAT_MAX_MESSAGES` ≤ 100 and
`DOCQA_CHAT_MAX_CHARS` ≤ 32,000 are enforced at start-up.
