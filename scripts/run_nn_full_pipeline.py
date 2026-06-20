#!/usr/bin/env python3
"""
Thin CLI for the NN complete workflow (news-engine-test branch only).

Usage:
  FIXTURE_URL='<url>' .venv/bin/python scripts/run_nn_full_pipeline.py --mode dry-run
  FIXTURE_URL='<url>' .venv/bin/python scripts/run_nn_full_pipeline.py --mode review
  TARGET_URL_IDS='<url>' .venv/bin/python scripts/run_nn_full_pipeline.py --mode hidden-publish
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NN_ENVS = {
    "NN_PUBLISH_V4": "1",
    "NN_TARGET_ENGINE": "1",
    "NN_PACKET_PIPELINE": "1",
    "EDITORIAL_PIPELINE": "1",
    "EDITORIAL_FORCE_SITE": "NN",
    "IJ_TARGET_ENGINE": "0",
    "TIER_C_ENABLED": "1",
    "MIN_IMAGE_WIDTH": "720",
}


def _run(cmd, env):
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    sys.exit(proc.returncode)


def main():
    parser = argparse.ArgumentParser(description="NN full pipeline CLI (test branch)")
    parser.add_argument("--mode", required=True, choices=["dry-run", "review", "hidden-publish"])
    args = parser.parse_args()

    env = os.environ.copy()
    env.update(NN_ENVS)

    py = str(ROOT / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable

    if args.mode in ("dry-run", "review"):
        env["REVIEW_ONLY"] = "1"
        env["EDITORIAL_IMAGE_PROBE"] = "1"
        if args.mode == "review":
            env["EDITORIAL_IMAGE_PROBE_DOWNLOAD"] = "1"
            env.setdefault("NN_EDITORIAL_QUALITY_MAX_ATTEMPTS", "12")
        else:
            env.setdefault("NN_EDITORIAL_QUALITY_MAX_ATTEMPTS", "3")
        script = str(ROOT / "scripts" / "run_nn_editorial_quality_loop.py")
        _run([py, script], env)

    elif args.mode == "hidden-publish":
        env["REVIEW_ONLY"] = "0"
        env["HIDDEN_PUBLISH_TEST"] = "1"
        env["PUBLISH_STATUS"] = env.get("PUBLISH_STATUS", "draft")
        if not env.get("TARGET_URL_IDS"):
            print("ERROR: TARGET_URL_IDS must be set for hidden-publish mode", file=sys.stderr)
            sys.exit(2)
        engine_main = str(ROOT / "engine.py")
        _run([py, engine_main], env)


if __name__ == "__main__":
    main()
