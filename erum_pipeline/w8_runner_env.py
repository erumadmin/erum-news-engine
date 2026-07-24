"""W8 operational env-file loader (fail-closed, exact values, no shell source)."""
from __future__ import annotations

import os
import pwd
import re
import stat
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

# Exact W8 initial operating contract — runner rejects any other values.
W8_EXACT_ENV: dict[str, str] = {
    "PUBLISH_STATUS": "DRAFT",
    "REVIEW_ONLY": "0",
    "HIDDEN_PUBLISH_TEST": "0",
    "PER_RUN_LIMIT": "3",
    "DAILY_PUBLISH_LIMIT": "9",
    "PER_SITE_PER_RUN_LIMIT": "1",
    "ONE_SOURCE_ONE_SITE": "1",
    "ERUM_ENV": "production",
    "ERUM_API_BASE": "https://erum-one.com",
    "REVALIDATE_FAILURE_WEBHOOK_CONFIGURED": "1",
}

# Keys that must appear in ENGINE_ENV_FILE itself (not inherited from the parent shell).
W8_REQUIRED_FILE_KEYS: tuple[str, ...] = (
    *W8_EXACT_ENV.keys(),
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
    "R2_PUBLIC_URL",
)

_STAGING_API_MARKERS = ("staging", "vercel.app", "localhost", "127.0.0.1")
_STAGING_DB_NAME_MARKERS = ("staging", "_stg", "test")
_SECRET_KEY_HINTS = ("PASSWORD", "SECRET", "API_KEY", "ACCESS_KEY", "TOKEN")

# Preserve for Python/runtime when spawning engine.py (never used to fill missing W8 secrets).
_CHILD_INHERIT_KEYS = {
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "SYSTEMROOT",
    "WINDIR",
}


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(h in upper for h in _SECRET_KEY_HINTS)


def _safe_err(key: str, detail: str) -> RuntimeError:
    """Never include secret values in error messages."""
    if _is_secret_key(key):
        return RuntimeError(f"ENGINE_ENV_FILE invalid: {key} ({detail})")
    return RuntimeError(f"ENGINE_ENV_FILE invalid: {key}={detail}")


def parse_env_value(raw: str) -> str:
    """
    Parse a single env value without shell expansion.
    Matching quotes are stripped once; contents ($, spaces, #, quotes, backticks, \\) kept verbatim.
    """
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


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
        if not key:
            raise RuntimeError(f"{path}:{line_no}: empty key")
        out[key] = parse_env_value(value)
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
        raise RuntimeError(
            f"ENGINE_ENV_FILE owner mismatch (got uid={st.st_uid}/{owner}, expected uid={uid}): {p}"
        )
    return p


def assert_w8_exact_values(env: Mapping[str, str]) -> None:
    for key, expected in W8_EXACT_ENV.items():
        actual = env.get(key)
        if actual is None:
            raise RuntimeError(f"W8 env missing required key: {key}")
        if actual != expected:
            # exact values are non-secret constants — safe to show expected/got
            raise RuntimeError(f"W8 env mismatch: {key} must be {expected!r} (got {actual!r})")


def _require_nonempty_from_file(env: Mapping[str, str], key: str) -> str:
    if key not in env:
        raise RuntimeError(f"ENGINE_ENV_FILE missing required key: {key}")
    value = env[key]
    if value is None or str(value).strip() == "":
        raise _safe_err(key, "empty")
    return value


def _assert_production_endpoints(env: Mapping[str, str]) -> None:
    api_base = env["ERUM_API_BASE"].rstrip("/")
    if api_base != "https://erum-one.com":
        raise RuntimeError(
            f"ERUM_API_BASE must be exactly https://erum-one.com (got non-matching production URL)"
        )
    host = (urlparse(api_base).hostname or "").lower()
    lowered = api_base.lower()
    if any(m in lowered for m in _STAGING_API_MARKERS) or host.endswith(".vercel.app"):
        raise RuntimeError("staging/preview API host forbidden in W8 production ENGINE_ENV_FILE")

    db_host = env["DB_HOST"].strip().lower()
    db_name = env["DB_NAME"].strip().lower()
    if any(m in db_host for m in ("staging", "localhost", "127.0.0.1")):
        raise RuntimeError("staging/local DB_HOST forbidden in W8 production ENGINE_ENV_FILE")
    if any(m in db_name for m in _STAGING_DB_NAME_MARKERS):
        raise RuntimeError("staging/test DB_NAME forbidden in W8 production ENGINE_ENV_FILE")

    if not re.fullmatch(r"\d+", env["DB_PORT"].strip()):
        raise RuntimeError("DB_PORT must be numeric")


def _assert_llm_keys(env: Mapping[str, str]) -> None:
    provider = (env.get("LLM_PROVIDER") or env.get("REWRITE_PROVIDER") or "upstage").strip().lower() or "upstage"
    rewrite = (env.get("REWRITE_PROVIDER") or provider).strip().lower()
    qa = (env.get("QA_PROVIDER") or provider).strip().lower()
    needed: set[str] = set()
    for p in {provider, rewrite, qa}:
        if p == "upstage":
            needed.add("UPSTAGE_API_KEY")
        elif p == "gemini":
            needed.add("GEMINI_API_KEY")
        elif p == "openrouter":
            needed.add("OPENROUTER_API_KEY")
        else:
            raise RuntimeError(f"unsupported LLM provider in ENGINE_ENV_FILE: {p}")
    for key in sorted(needed):
        _require_nonempty_from_file(env, key)


def assert_w8_production_file_complete(env: Mapping[str, str]) -> None:
    """Fail-closed validation of .env.w8 contents (no secret values in errors)."""
    assert_w8_exact_values(env)
    for key in W8_REQUIRED_FILE_KEYS:
        _require_nonempty_from_file(env, key)

    has_api = bool((env.get("ERUM_API_KEY") or "").strip()) or bool((env.get("ADMIN_API_KEY") or "").strip())
    if not has_api:
        raise RuntimeError("ENGINE_ENV_FILE missing required key: ERUM_API_KEY or ADMIN_API_KEY")

    _assert_production_endpoints(env)
    _assert_llm_keys(env)


def load_w8_env_file(path: str | Path, *, expected_uid: int | None = None) -> dict[str, str]:
    """Validate secure file + full W8 production contract; return parsed mapping."""
    secure = assert_env_file_secure(path, expected_uid=expected_uid)
    parsed = parse_env_file(secure)
    assert_w8_production_file_complete(parsed)
    return parsed


def build_explicit_child_env(parsed: Mapping[str, str]) -> dict[str, str]:
    """
    Build env for engine.py subprocess: system PATH/etc only + file values.
    Does not inherit parent secrets or load other dotenv files.
    """
    child = {k: v for k, v in os.environ.items() if k in _CHILD_INHERIT_KEYS}
    child.update(dict(parsed))
    child["ERUM_EXPLICIT_ENV_ONLY"] = "1"
    return child


def apply_env_to_os(env: Mapping[str, str]) -> None:
    for key, value in env.items():
        os.environ[key] = value
