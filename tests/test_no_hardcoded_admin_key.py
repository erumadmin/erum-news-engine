"""Ensure no hardcoded Admin API key fallback remains in source files."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HARDCODED_KEY = "eRuM@AdminKey2026!"

TARGET_FILES = [
    REPO_ROOT / "engine.py",
    REPO_ROOT / "scripts" / "backfill_r2_images.py",
    REPO_ROOT / "scripts" / "backfill_author.py",
]


def test_no_hardcoded_admin_key_literal():
    for path in TARGET_FILES:
        content = path.read_text(encoding="utf-8")
        assert HARDCODED_KEY not in content, f"{path.name} still contains hardcoded admin key"


def test_runtime_error_guard_present():
    for path in TARGET_FILES:
        content = path.read_text(encoding="utf-8")
        assert "RuntimeError" in content, f"{path.name} missing RuntimeError guard for missing API key"


if __name__ == "__main__":
    test_no_hardcoded_admin_key_literal()
    test_runtime_error_guard_present()
    print("OK: no hardcoded admin key; RuntimeError guards present")
