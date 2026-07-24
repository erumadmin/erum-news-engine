#!/usr/bin/env python3
"""W8 cron entry: load ENGINE_ENV_FILE in-process and exec engine.py (no shell source)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)

    env_file = (os.environ.get("ENGINE_ENV_FILE") or "").strip()
    if not env_file:
        print("ERROR: ENGINE_ENV_FILE is required", file=sys.stderr)
        return 1

    # Import after chdir so package resolution is stable.
    from erum_pipeline.w8_runner_env import build_explicit_child_env, load_w8_env_file

    try:
        parsed = load_w8_env_file(env_file)
        child_env = build_explicit_child_env(parsed)
    except Exception as exc:
        # Message must not include secret values (loaders already redact).
        print(f"ERROR: ENGINE_ENV_FILE validation failed: {exc}", file=sys.stderr)
        return 1

    print(
        "ENV_OK "
        f"file={env_file} "
        f"ERUM_ENV={child_env.get('ERUM_ENV')} "
        f"PER_RUN_LIMIT={child_env.get('PER_RUN_LIMIT')} "
        f"DAILY_PUBLISH_LIMIT={child_env.get('DAILY_PUBLISH_LIMIT')} "
        f"PER_SITE_PER_RUN_LIMIT={child_env.get('PER_SITE_PER_RUN_LIMIT')} "
        f"ERUM_EXPLICIT_ENV_ONLY={child_env.get('ERUM_EXPLICIT_ENV_ONLY')}",
        flush=True,
    )

    # Safe subprocess: env mapping only — no shell, no sourced temp files.
    proc = subprocess.run(
        [sys.executable, str(root / "engine.py")],
        cwd=str(root),
        env=child_env,
        check=False,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
