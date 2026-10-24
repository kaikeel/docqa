# 3. Use Claude's native citations (document blocks) instead of parsing citations ourselves

Date: 2026-10-25 · Status: Accepted · Author: sol-architect

## Context
The core promise of DocQA (AC1) is that every answer carries verifiable citations: source file and a verbatim
quote. Common approaches are (a) asking the model to emit markers like `[1]` or a JSON list of quotes and then
parsing/validating them, or (b) using the Claude API's built-in citations feature, where each retrieved passage
is passed as a `document` content block with `citations.enabled = true` and the API returns text blocks with a
structured `citations` array (`type: "char_location"`, `cited_text`, `document_index`, `document_title`).

Approach (a) is fragile: markers can be malformed, quotes can be paraphrased or invented, and we would need
our own fuzzy matching to verify them. Structured outputs (`output_config.format`) cannot be combined with
citations on this API, so we cannot have both.

## Decision
- Pass each retrieved chunk as a plain-text `document` block (`source.type = "text"`,
  `media_type = "text/plain"`), titled `<file>#<chunk_id>`, with citations enabled on **all** documents, placed
  before the question text block.
- Call the official Anthropic Python SDK (`client.beta.messages.create` with server-side fallback beta,
  `output_config={"effort": ...}`), no raw HTTP and no OpenAI-compatible shim. Do not send sampling parameters,
  `thinking`, or an assistant prefill.
- Read only `type == "text"` blocks; map each citation's `document_index` back to the chunk list to obtain the
  `source`; use `cited_text` as the quote. Check `stop_reason` first (`"refusal"` → explicit error).
- Do not use structured outputs. `found` is true only if at least one citation was returned.

## Consequences
- Quotes are extracted by the API from the documents we supplied, so they are verbatim and traceable to a
  file without custom parsing or fuzzy matching.
- The LLM layer is tied to Claude's response shape; this is isolated behind the `AnswerModel` protocol, with a
  `FakeAnswerModel` for offline tests. Swapping providers would need a new implementation, not service changes.
- The answer is free text (no JSON schema). The API/CLI build their own JSON envelope
  (`{answer, citations[{source, quote}], found}`) from parsed blocks.
- We depend on a beta flag (`server-side-fallback-2026-07-01`); if it changes, only `ClaudeAnswerModel` is affected.
