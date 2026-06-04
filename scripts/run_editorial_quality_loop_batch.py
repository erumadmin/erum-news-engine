#!/usr/bin/env python3
"""
Run editorial quality loop for each article in a manifest (subprocess per article).

Exit 0 only when every article reaches target score within max attempts.
Writes review_outputs/editorial_batch_summary_<ts>.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "scripts" / "run_editorial_quality_loop.py"
DEFAULT_MANIFEST = ROOT / "scripts" / "fixtures" / "editorial_batch_manifest.json"
KST = ZoneInfo("Asia/Seoul")


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_one(article: dict, *, max_attempts: int, python: str) -> dict:
    env = os.environ.copy()
    env.setdefault("REVIEW_ONLY", "1")
    env.setdefault("EDITORIAL_IMAGE_PROBE", "1")
    env.setdefault("EDITORIAL_IMAGE_PROBE_DOWNLOAD", "0")
    env.setdefault("EDITORIAL_PIPELINE", "1")
    env.setdefault("IJ_PACKET_PIPELINE", "1")
    env.setdefault("IJ_TARGET_ENGINE", "1")
    env["IJ_PUBLISH_V4"] = "1"
    env.setdefault("TIER_C_ENABLED", "1")
    env.setdefault("EDITORIAL_REQUIRE_FULL_SOURCE", "0")
    env.setdefault("MIN_SOURCE_BODY_CHARS", "120")
    env["EDITORIAL_QUALITY_MAX_ATTEMPTS"] = str(max_attempts)
    env["FIXTURE_URL"] = article["url"]
    if article.get("fixture_source_md"):
        env["FIXTURE_SOURCE_MD"] = article["fixture_source_md"]
    else:
        env.pop("FIXTURE_SOURCE_MD", None)
        env["EDITORIAL_REQUIRE_FULL_SOURCE"] = "1"
    if article.get("title"):
        env["FIXTURE_TITLE"] = article["title"]
    else:
        env.pop("FIXTURE_TITLE", None)

    proc = subprocess.run(
        [python, str(LOOP)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    score_snapshot: dict | None = None
    latest = ROOT / "review_outputs" / "editorial_quality_score.json"
    if proc.returncode == 0 and latest.is_file():
        try:
            score_snapshot = json.loads(latest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            score_snapshot = None
    return {
        "id": article.get("id"),
        "label": article.get("label"),
        "url": article["url"],
        "fixture_source_md": article.get("fixture_source_md"),
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "passed": proc.returncode == 0,
        "gate": "article_publish_ready_v4",
        "total": (score_snapshot or {}).get("total"),
        "article_publish_ready": (score_snapshot or {}).get("article_publish_ready"),
        "publish_validation": (score_snapshot or {}).get("publish_validation"),
    }


def main() -> int:
    manifest_path = Path(os.environ.get("EDITORIAL_BATCH_MANIFEST", str(DEFAULT_MANIFEST)))
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest = _load_manifest(manifest_path)
    max_attempts = int(
        os.environ.get(
            "EDITORIAL_QUALITY_MAX_ATTEMPTS",
            manifest.get("max_attempts_per_article", 12),
        )
    )
    python = os.environ.get("PYTHON", sys.executable)
    articles = manifest.get("articles") or []
    if not articles:
        print("manifest has no articles")
        return 2

    print(f"=== 배치 품질 루프 ({len(articles)}건) ===")
    print(f"manifest: {manifest_path}")
    print(f"max_attempts/article: {max_attempts}")
    print(f"target_score: {manifest.get('target_score', 9.5)}")
    print("gate: article_publish_ready (IJ_PUBLISH_V4=1)\n")

    max_rounds = int(os.environ.get("EDITORIAL_BATCH_MAX_ROUNDS", "4"))
    results: list[dict | None] = [None] * len(articles)
    for round_n in range(1, max_rounds + 1):
        pending = [
            (i, art)
            for i, art in enumerate(articles)
            if results[i] is None or not results[i]["passed"]
        ]
        if not pending:
            break
        if round_n > 1:
            print(f"\n=== 재시도 라운드 {round_n}/{max_rounds} ({len(pending)}건) ===")
        for i, art in pending:
            label = art.get("label") or art.get("id") or art["url"]
            print(f"\n[{i + 1}/{len(articles)}] {label}" + (f" (r{round_n})" if round_n > 1 else ""))
            print(f"  URL: {art['url']}")
            if art.get("fixture_source_md"):
                print(f"  원문: {art['fixture_source_md']}")
            else:
                print("  원문: live fetch (korea.kr)")
            row = _run_one(art, max_attempts=max_attempts, python=python)
            results[i] = row
            ready = row.get("article_publish_ready")
            status = "PASS" if row["passed"] else f"FAIL(exit {row['exit_code']})"
            print(f"  → {status} (total={row.get('total')}, publish_ready={ready})")
    results = [r for r in results if r is not None]

    ts = datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S")
    summary_path = ROOT / "review_outputs" / f"editorial_batch_summary_{ts}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_kst": ts,
        "manifest": str(manifest_path),
        "target_score": manifest.get("target_score", 9.5),
        "gate": "article_publish_ready_v4",
        "ij_publish_v4": True,
        "max_attempts_per_article": max_attempts,
        "all_passed": all(r["passed"] for r in results),
        "all_publish_ready": all(r.get("article_publish_ready") for r in results),
        "results": results,
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n요약: {summary_path}")
    print(f"전체 통과: {payload['all_passed']}")
    return 0 if payload["all_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
