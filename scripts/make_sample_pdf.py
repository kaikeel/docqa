"""Regenerate examples/docs/release-checklist.pdf (fictional sample content, no extra deps).

Usage: uv run python -m scripts.make_sample_pdf
"""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.make_pdf import build_pdf

PAGE_1 = [
    "Kaikeel Handbook Lite: Release Checklist",
    "(Fictional sample document for the DocQA demo.)",
    "",
    "VERSIONING",
    "Every release gets a semantic version number: MAJOR.MINOR.PATCH.",
    "Increase PATCH for bug fixes, MINOR for backwards-compatible features,",
    "and MAJOR for breaking changes. The first client release is 0.1.0.",
    "",
    "CHANGELOG",
    "Move the entries under Unreleased into a new section named after the version,",
    "with the release date. Group entries as Added, Changed, Fixed and Removed.",
    "",
    "TAGGING",
    "Create an annotated git tag such as v0.1.0 on the merge commit in main.",
    "The handover zip archive is always built from the tag, never from a branch.",
]

PAGE_2 = [
    "GATES BEFORE TAGGING",
    "The quality report and the security report must both say PASS.",
    "CI must be green on the exact commit that will be tagged.",
    "",
    "ROLLBACK PLAN",
    "Every release note states how to roll back: which previous tag to redeploy",
    "and whether any database migration must be reverted first.",
    "A rollback drill is rehearsed once per quarter on a staging copy.",
    "",
    "ANNOUNCEMENT",
    "After tagging, the delivery lead posts a short release note to the client",
    "thread listing the version, the highlights and any action the client must take.",
]

TARGET = Path(__file__).resolve().parent.parent / "examples" / "docs" / "release-checklist.pdf"


def main() -> None:
    TARGET.write_bytes(build_pdf([PAGE_1, PAGE_2]))


if __name__ == "__main__":
    main()
