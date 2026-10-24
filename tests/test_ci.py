"""The CI workflow pins third-party actions to full commit SHAs (SEC M3)."""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def test_every_action_is_pinned_to_a_commit_sha_with_its_tag() -> None:
    uses = [
        line.strip()
        for path in WORKFLOWS.glob("*.yml")
        for line in path.read_text("utf-8").splitlines()
        if re.match(r"\s*(-\s*)?uses:", line)
    ]
    assert uses
    for line in uses:
        assert re.search(r"uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line), line
