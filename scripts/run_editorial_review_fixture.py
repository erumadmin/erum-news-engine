#!/usr/bin/env python3
"""
설계 목적 리뷰: live 원문 fetch 필수 → 증거 → 패킷 → IJ 작성 → 비교 리포트

  python3 scripts/run_editorial_review_fixture.py --purpose
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("REVIEW_ONLY", "1")
os.environ.setdefault("EDITORIAL_PIPELINE", "1")
# IJ: 수집 원문 + 리서치 패킷·근거 합산 재작성
os.environ.setdefault("IJ_PACKET_PIPELINE", "1")
os.environ.setdefault("EDITORIAL_REQUIRE_FULL_SOURCE", "1")
os.environ.setdefault("PUBLISH_STATUS", "DRAFT")


def _load_main_engine():
    import importlib.util

    path = ROOT / "engine.py"
    spec = importlib.util.spec_from_file_location("erum_news_engine_main", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


eng = _load_main_engine()
from engine.pipeline.orchestrator import run_pre_publish_pipeline  # noqa: E402

FIXTURE_JSON = ROOT / "tests/fixtures/research/cached_source.json"
KST = ZoneInfo("Asia/Seoul")


def build_article_from_fixture_url(*, url: str | None = None, title: str | None = None) -> dict:
    raw = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    use_url = (url or raw["url"]).strip()
    return {
        "url": use_url,
        "url_id": eng.extract_unique_id(use_url),
        "title": (title or raw.get("title") or "").strip() or "제목 미상",
        "body": raw.get("body", "") if not url else "",
        "raw_html": "",
        "image": "",
        "source_published_at": datetime.now(tz=KST),
        "source_type": "policy_briefing",
    }


def write_comparison_report(
    article: dict,
    editorial_ctx,
    result: dict,
    *,
    ingest_reason: str,
    output_dir: Path,
) -> str:
    from engine.pipeline.editorial_report import (
        normalize_ij_body_html,
        write_editorial_quality_bundle,
    )
    from engine.pipeline.editorial_scorecard import score_editorial_rewrite
    from engine.pipeline.rewrite_validate import validate_ij_editorial_rewrite

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S")
    variant = next((v for v in result.get("variants", []) if v.get("prefix") == "IJ_"), {})
    if not variant or variant.get("status") != "SUCCESS":
        path = output_dir / f"editorial_compare_{ts}.md"
        path.write_text(
            f"# 비교 리포트 (IJ 미생성)\n\n- URL: {article.get('url')}\n",
            encoding="utf-8",
        )
        return str(path)

    body_html = normalize_ij_body_html(variant.get("body", ""))
    ok_val, val_msg = validate_ij_editorial_rewrite(
        variant.get("title", ""),
        body_html,
        editorial_ctx.packet if editorial_ctx else {},
        article,
    )
    score = score_editorial_rewrite(
        variant.get("title", ""),
        variant.get("excerpt", ""),
        body_html,
        article,
        editorial_ctx.packet if editorial_ctx else {},
        qa_score=variant.get("qa_score"),
        evidence=editorial_ctx.evidence if editorial_ctx else None,
    )
    score["validation_ok"] = ok_val
    score["validation_msg"] = val_msg
    score["passes"] = bool(score["passes"] and ok_val)

    paths = write_editorial_quality_bundle(
        output_dir,
        ts=ts,
        article=article,
        editorial_ctx=editorial_ctx,
        variant={**variant, "body": body_html},
        score=score,
        ingest_reason=ingest_reason,
        attempt=1,
    )
    return paths["compare"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--purpose",
        action="store_true",
        help="live 원문 fetch 필수, 합성 HTML 미사용",
    )
    parser.add_argument(
        "--url",
        metavar="URL",
        help="기본 cached_source.json 대신 이 URL로 live fetch (제목은 페이지에서 추출)",
    )
    parser.add_argument("--title", metavar="TITLE", help="--url 사용 시 RSS 제목 힌트(선택)")
    args = parser.parse_args()

    if args.purpose:
        os.environ["EDITORIAL_REQUIRE_FULL_SOURCE"] = "1"

    if not eng.UPSTAGE_API_KEY and not eng.GEMINI_API_KEY:
        print("UPSTAGE_API_KEY 또는 GEMINI_API_KEY 필요 (~/.env.erum_infra)")
        return 1

    article = build_article_from_fixture_url(url=args.url, title=args.title)
    print(f"📰 대상: {article['title'][:70]}")
    print(f"   URL: {article['url']}")

    fetcher = eng.fetch_with_retry
    editorial_ctx = run_pre_publish_pipeline(article, fetcher=fetcher, persist=False)
    ingest_reason = article.get("ingest_source", "unknown")

    if editorial_ctx is None:
        print("🚫 파이프라인 DROP — 비교 리포트만 저장")
        path = write_comparison_report(
            article,
            None,
            {"variants": []},
            ingest_reason=ingest_reason,
            output_dir=Path(eng._review_output_dir()),
        )
        print(f"📊 {path}")
        return 2

    grade_order = {"A": 4, "B": 3, "C": 2, "D": 1}
    if grade_order.get(editorial_ctx.publish_grade, 0) < 2:
        print(f"⏭️ publish_grade {editorial_ctx.publish_grade} — 작성 스킵 (C 이상만)")
        compare = write_comparison_report(
            article,
            editorial_ctx,
            {"variants": []},
            ingest_reason=ingest_reason,
            output_dir=Path(eng._review_output_dir()),
        )
        print(f"📊 {compare}")
        return 3

    upload_counts = {p: 0 for p in eng.MEDIA_PREFIXES}
    result = eng.process_article(article, upload_counts, review_mode=True, editorial_ctx=editorial_ctx)
    review_path = eng.write_review_report([result])
    compare_path = write_comparison_report(
        article,
        editorial_ctx,
        result,
        ingest_reason=ingest_reason,
        output_dir=Path(eng._review_output_dir()),
    )
    print(f"\n📝 리뷰: {review_path}")
    print(f"📊 비교: {compare_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
