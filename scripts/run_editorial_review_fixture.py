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


def build_article_from_fixture_url() -> dict:
    raw = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    return {
        "url": raw["url"],
        "url_id": eng.extract_unique_id(raw["url"]),
        "title": raw["title"],
        "body": raw.get("body", ""),
        "raw_html": "",
        "image": "",
        "source_published_at": datetime.now(tz=KST),
        "source_type": "policy_briefing",
    }


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", eng.strip_html_tags(html or "")).strip()


def write_comparison_report(
    article: dict,
    editorial_ctx,
    result: dict,
    *,
    ingest_reason: str,
    output_dir: Path,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"editorial_compare_{ts}.md"

    variant = next((v for v in result.get("variants", []) if v.get("prefix") == "IJ_"), {})
    packet = editorial_ctx.packet if editorial_ctx else {}
    evidence = editorial_ctx.evidence if editorial_ctx else []

    lines = [
        "# 원문 vs 패킷 기반 IJ 기사 비교",
        "",
        f"- 생성(KST): {datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S')}",
        f"- URL: {article.get('url')}",
        f"- 원문수집: {ingest_reason} | ingest_source: {article.get('ingest_source', '?')}",
        f"- 본문 길이: {len(article.get('body') or '')}자",
        f"- 라우팅: {getattr(editorial_ctx, 'assigned_site', '?')} | "
        f"publish_grade: {getattr(editorial_ctx, 'publish_grade', '?')} | "
        f"배치: {editorial_ctx.placement.slot if editorial_ctx else '?'} "
        f"({editorial_ctx.placement.total if editorial_ctx else 0}점)",
        f"- 공식 증거(발췌 80자+): {packet.get('official_evidence_count', 0)}건",
        "",
        "## 수집된 증거 (fetch ok, 발췌)",
        "",
    ]
    ok_ev = [e for e in evidence if e.get("fetch_status") == "ok"]
    for e in ok_ev[:8]:
        ex = (e.get("body_excerpt") or "")[:200]
        lines.append(f"- [{e.get('evidence_type')}] {e.get('title') or e.get('url')}")
        lines.append(f"  - 발췌({len(ex)}자): {ex or '(없음)'}")
    if not ok_ev:
        lines.append("- (없음)")

    lines.extend(
        [
            "",
            "## 원문 (전문)",
            "",
            f"**제목:** {article.get('title')}",
            "",
            (article.get("body") or "")[:6000],
            "",
            "## 리서치 패킷",
            "",
            f"- main_claim: {packet.get('main_claim', '')}",
            f"- key_facts: {packet.get('key_facts', [])}",
            f"- risk_flags: {packet.get('risk_flags', [])}",
            "",
            "## IJ 재작성",
            "",
            f"**제목:** {variant.get('title', '(없음)')}",
            "",
            f"**리드문:** {variant.get('excerpt', '')}",
            "",
            _plain(variant.get("body", ""))[:3500] or "(없음)",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--purpose",
        action="store_true",
        help="live 원문 fetch 필수, 합성 HTML 미사용",
    )
    args = parser.parse_args()

    if args.purpose:
        os.environ["EDITORIAL_REQUIRE_FULL_SOURCE"] = "1"

    if not eng.UPSTAGE_API_KEY and not eng.GEMINI_API_KEY:
        print("UPSTAGE_API_KEY 또는 GEMINI_API_KEY 필요 (~/.env.erum_infra)")
        return 1

    article = build_article_from_fixture_url()
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
