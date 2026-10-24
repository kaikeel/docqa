# Kaikeel Handbook Lite: Coding Standards

*Fictional sample document for the DocQA demo.*

## Principles

- **Smallest solution first.** Build the simplest thing that meets the acceptance criteria.
  Avoid speculative abstractions.
- **Readable over clever.** Names explain intent; comments explain why, not what.

## Formatting and linting

Python code is formatted and linted with ruff. TypeScript code uses eslint and prettier.
Formatting is never discussed in code review: the formatter decides.

## Type checking

Python projects use type hints everywhere and run mypy in strict mode on the source
package. TypeScript projects enable the strict compiler option.

## Testing

- Every piece of business logic has a unit test.
- Each main user flow has at least one integration or end-to-end test.
- Line coverage of the logic must be at least 80 percent; the CI pipeline fails below that
  threshold.
- Tests must not call paid external APIs. Use a fake implementation behind an interface.

## Dependencies

Only use popular, maintained libraries with a permissive licence (MIT, Apache 2.0 or BSD).
Pin exact versions and commit the lock file. Every new dependency needs a one-line
justification in the pull request.

## Configuration

All configuration comes from environment variables, documented in a `.env.example` file.
Secrets and environment-specific URLs are never hard-coded.

## Error handling

Errors shown to end users must be clear and actionable. Logs include enough context to
debug the problem but never contain secrets or personal data.
