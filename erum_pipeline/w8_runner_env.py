"""W8 operational env-file loader (fail-closed, exact values)."""
from __future__ import annotations

import os
import pwd
import stat
from pathlib import Path
from typing import Mapping

# Exact W8 initial operating contract — runner rejects any other values.
W8_EXACT_ENV: dict[str, str] = {
    "PUBLISH_STATUS": "DRAFT",
    "REVIEW_ONLY": "0",
    "HIDDEN_PUBLISH_TEST": "0",
    "PER_RUN_LIMIT": "3",
    "DAILY_PUBLISH_LIMIT": "9",
    "PER_SITE_PER_RUN_LIMIT": "1",
    "ONE_SOURCE_ONE_SITE": "1",
}


def parse_env_file(path: str | Path) -> dict[str, str]:
    raw = Path(path).read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for line_no, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"{path}:{line_no}: invalid line (expected KEY=VALUE)")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            raise RuntimeError(f"{path}:{line_no}: empty key")
        out[key] = value
    return out


def assert_env_file_secure(path: str | Path, *, expected_uid: int | None = None) -> Path:
    p = Path(path)
    if not p.is_file():
        raise RuntimeError(f"ENGINE_ENV_FILE missing or not a file: {p}")
    st = p.stat()
    mode = stat.S_IMODE(st.st_mode)
    if mode != 0o600:
        raise RuntimeError(f"ENGINE_ENV_FILE mode must be 600 (got {oct(mode)}): {p}")
    uid = expected_uid if expected_uid is not None else os.getuid()
    if st.st_uid != uid:
        try:
            owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError:
            owner = str(st.st_uid)
        raise RuntimeError(f"ENGINE_ENV_FILE owner mismatch (got uid={st.st_uid}/{owner}, expected uid={uid}): {p}")
    return p


def assert_w8_exact_values(env: Mapping[str, str]) -> None:
    for key, expected in W8_EXACT_ENV.items():
        actual = (env.get(key) or "").strip()
        if actual != expected:
            raise RuntimeError(f"W8 env mismatch: {key} must be {expected!r} (got {actual!r})")


def load_w8_env_file(path: str | Path, *, expected_uid: int | None = None) -> dict[str, str]:
    """Validate secure file + exact W8 values; return parsed env mapping."""
    secure = assert_env_file_secure(path, expected_uid=expected_uid)
    parsed = parse_env_file(secure)
    assert_w8_exact_values(parsed)
    return parsed


def apply_env_to_os(env: Mapping[str, str]) -> None:
    for key, value in env.items():
        os.environ[key] = value
