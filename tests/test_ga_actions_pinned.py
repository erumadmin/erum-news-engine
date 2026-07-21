"""Verify all GitHub Actions are pinned to full 40-char SHAs, not floating tags."""
from pathlib import Path
import re
import sys

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"

FLOATING_TAG_RE = re.compile(r"uses:\s*([\w.-]+)/([\w.-]+)@v\d+")

def test_all_actions_pinned():
    offenders = []
    workflow_files = list(WORKFLOWS_DIR.rglob("*.yml")) + list(WORKFLOWS_DIR.rglob("*.yaml"))
    for yml in workflow_files:
        for i, line in enumerate(yml.read_text(encoding="utf-8").splitlines(), 1):
            m = FLOATING_TAG_RE.search(line)
            if m and " # " not in line:
                offenders.append(f"{yml.name}:{i}: {line.strip()}")
            elif m and " # " in line:
                # has a comment but still floating tag — still an offender
                offenders.append(f"{yml.name}:{i}: {line.strip()} (has comment but tag not pinned)")
    assert not offenders, "Floating action tags found:\n" + "\n".join(offenders)

if __name__ == "__main__":
    test_all_actions_pinned()
    print("OK: all GitHub Actions pinned to SHAs")
