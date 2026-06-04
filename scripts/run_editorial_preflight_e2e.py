#!/usr/bin/env python3
"""
Full IJ preflight: ingest → editorial → v4 text gate → image probe → publish manifest.

No API publish. REVIEW_ONLY=1 always. Optional download: EDITORIAL_IMAGE_PROBE_DOWNLOAD=1
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("REVIEW_ONLY", "1")
os.environ.setdefault("EDITORIAL_IMAGE_PROBE", "1")
os.environ.setdefault("EDITORIAL_IMAGE_PROBE_DOWNLOAD", "0")
os.environ.setdefault("EDITORIAL_PIPELINE", "1")
os.environ.setdefault("IJ_PACKET_PIPELINE", "1")
os.environ["IJ_TARGET_ENGINE"] = "1"
os.environ["IJ_PUBLISH_V4"] = "1"


def main() -> int:
    url = os.environ.get("FIXTURE_URL", "").strip()
    if not url:
        print("FIXTURE_URL required", file=sys.stderr)
        return 2
    py = ROOT / ".venv" / "bin" / "python"
    if not py.exists():
        py = Path(sys.executable)
    cmd = [str(py), str(ROOT / "scripts" / "run_editorial_quality_loop.py")]
    print("=== Editorial preflight E2E (no deploy) ===")
    print(f"  URL: {url}")
    print(f"  IMAGE_PROBE_DOWNLOAD: {os.environ.get('EDITORIAL_IMAGE_PROBE_DOWNLOAD', '0')}")
    proc = subprocess.run(cmd, cwd=ROOT, env=os.environ.copy())
    if proc.returncode not in (0, 3):
        return proc.returncode

    out_dir = ROOT / "review_outputs"
    qualities = sorted(out_dir.glob("editorial_quality_*.json"), key=lambda p: p.stat().st_mtime)
    if not qualities:
        print("No editorial_quality_*.json found", file=sys.stderr)
        return 1
    latest = json.loads(qualities[-1].read_text(encoding="utf-8"))
    preflight = latest.get("publish_preflight") or {}
    summary = {
        "url": latest.get("url"),
        "score_total": (latest.get("score") or {}).get("total"),
        "passes": (latest.get("score") or {}).get("passes"),
        "image_status": (latest.get("image_probe") or {}).get("status"),
        "layout_type": preflight.get("layout_type"),
        "text_publish_ready": preflight.get("text_publish_ready"),
        "would_publish_api": preflight.get("would_publish_api"),
        "blocked_reasons": preflight.get("blocked_reasons"),
    }
    summary_path = out_dir / "editorial_preflight_latest.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nPreflight summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("text_publish_ready") else 3


if __name__ == "__main__":
    raise SystemExit(main())
