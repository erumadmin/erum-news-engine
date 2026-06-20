#!/usr/bin/env python3
"""CB (CSR 브리핑) editorial quality loop - image -> research -> rewrite -> publish preflight."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("REVIEW_ONLY", "1")
os.environ.setdefault("EDITORIAL_PIPELINE", "1")
os.environ.setdefault("CB_PACKET_PIPELINE", "1")
os.environ.setdefault("CB_TARGET_ENGINE", "1")
os.environ.setdefault("CB_PUBLISH_V4", "1")
os.environ.setdefault("EDITORIAL_FORCE_SITE", "CB")
os.environ["IJ_TARGET_ENGINE"] = "0"
os.environ.setdefault("TIER_C_ENABLED", "1")
os.environ.setdefault("EDITORIAL_REQUIRE_FULL_SOURCE", "1")
os.environ.setdefault("MIN_IMAGE_WIDTH", "720")

from engine.pipeline.cb_rewrite_validate import validate_cb_editorial_rewrite  # noqa: E402
from engine.pipeline.cb_scorecard import TARGET_SCORE, score_cb_editorial_rewrite  # noqa: E402
from engine.pipeline.editorial_report import normalize_ij_body_html  # noqa: E402

FIXTURE_URL = os.environ.get(
    "FIXTURE_URL",
    "https://www.korea.kr/news/policyNewsView.do?newsId=148965573&call_from=rsslink",
)
MAX_ATTEMPTS = int(os.environ.get("CB_EDITORIAL_QUALITY_MAX_ATTEMPTS", "12"))
KST = ZoneInfo("Asia/Seoul")


def _load_engine():
    import importlib.util

    spec = importlib.util.spec_from_file_location("erum_news_engine_main", ROOT / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _print_goals() -> None:
    from engine.pipeline.cb_scorecard import (
        TARGET_BUSINESS_AXES,
        TARGET_ORIGINALITY,
        TARGET_READER_VALUE,
    )

    print("=== CB (CSR 브리핑) 품질 루프 ===")
    print(f"  총점 >= {TARGET_SCORE}")
    print(f"  business_axes >= {TARGET_BUSINESS_AXES}, reader_value >= {TARGET_READER_VALUE}")
    print(f"  originality >= {TARGET_ORIGINALITY}, article_publish_ready (v4)")
    print("  이미지: editorial_stages gate (download) + probe in review\n")


def _inject_cached_image(article: dict, image_path: Path) -> None:
    img_bytes = image_path.read_bytes()
    article["_article_img_result"] = {
        "img_bytes": img_bytes,
        "content_type": "image/jpeg",
        "filename": image_path.name,
        "caption": "",
        "selected_url": os.environ.get(
            "FIXTURE_IMAGE_URL",
            "https://www.korea.kr/newsWeb/resources/attaches/2026.06/01/58d4abf7a1c3965361733de2354a71af.jpg",
        ),
        "image_status": "download_ok",
    }
    article["_ij_img_result"] = article["_article_img_result"]


def main() -> int:
    _print_goals()
    eng = _load_engine()
    from engine.pipeline.editorial_stages import run_editorial_stages
    from scripts.run_editorial_quality_loop import _fixture_dual_fetcher, _live_research_fetcher

    fixture_json = os.environ.get("FIXTURE_JSON", "").strip()
    source_md = os.environ.get("FIXTURE_SOURCE_MD", "").strip()
    if fixture_json:
        path = Path(fixture_json)
        if not path.is_absolute():
            path = ROOT / path
        raw = json.loads(path.read_text(encoding="utf-8"))
        os.environ["EDITORIAL_REQUIRE_FULL_SOURCE"] = "0"
        article = {
            "url": raw.get("url") or FIXTURE_URL,
            "url_id": eng.extract_unique_id(raw.get("url") or FIXTURE_URL),
            "title": os.environ.get("FIXTURE_TITLE", raw.get("title", "")),
            "body": raw.get("body") or "",
            "raw_html": raw.get("raw_html") or "",
            "image": raw.get("image") or "",
            "source_type": "policy_briefing",
            "ingest_source": "fixture_json",
        }
        cached_img = os.environ.get(
            "FIXTURE_CACHED_IMAGE",
            str(ROOT / "review_outputs" / "featured_20260605_091959.jpg"),
        )
        if Path(cached_img).is_file():
            _inject_cached_image(article, Path(cached_img))
        from engine.pipeline.fixture_fetcher import target_fixture_fetcher

        fetcher = _fixture_dual_fetcher(target_fixture_fetcher)
    elif source_md:
        from scripts.run_editorial_quality_loop import _load_article_from_compare_md

        md_path = Path(source_md)
        if not md_path.is_absolute():
            md_path = ROOT / md_path
        title, body = _load_article_from_compare_md(md_path)
        os.environ["EDITORIAL_REQUIRE_FULL_SOURCE"] = "0"
        article = {
            "url": FIXTURE_URL,
            "url_id": eng.extract_unique_id(FIXTURE_URL),
            "title": os.environ.get("FIXTURE_TITLE", title),
            "body": body,
            "raw_html": "",
            "image": "",
            "source_type": "policy_briefing",
            "ingest_source": "fixture_source_md",
        }
        cached_img = os.environ.get(
            "FIXTURE_CACHED_IMAGE",
            str(ROOT / "review_outputs" / "featured_20260605_091959.jpg"),
        )
        if Path(cached_img).is_file():
            _inject_cached_image(article, Path(cached_img))
        from engine.pipeline.fixture_fetcher import target_fixture_fetcher

        fetcher = _fixture_dual_fetcher(target_fixture_fetcher)
    else:
        article = {
            "url": FIXTURE_URL,
            "url_id": eng.extract_unique_id(FIXTURE_URL),
            "title": os.environ.get("FIXTURE_TITLE", ""),
            "body": "",
            "raw_html": "",
            "image": "",
            "source_type": "policy_briefing",
        }
        fetcher = _live_research_fetcher(eng.fetch_with_retry)

    editorial_ctx = run_editorial_stages(article, fetcher=fetcher, persist=False)
    if editorial_ctx is None:
        code = article.get("_skip_image_status") or "pipeline_drop"
        print(f"DROP: editorial_stages returned None ({code})")
        return 2
    if editorial_ctx.assigned_site != "CB":
        print(f"WARN: assigned_site={editorial_ctx.assigned_site} (expected CB)")

    upload_counts = {p: 0 for p in eng.MEDIA_PREFIXES}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        ts = datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S")
        print(f"\n=== CB 시도 {attempt}/{MAX_ATTEMPTS} ===")
        try:
            result = eng.process_article(
                article, upload_counts, review_mode=True, editorial_ctx=editorial_ctx
            )
        except Exception as exc:
            print(f"FAIL: {exc}")
            return 1

        variant = next((v for v in result.get("variants", []) if v.get("prefix") == "CB_"), {})
        if not variant or variant.get("status") != "SUCCESS":
            print(f"FAIL: {variant}")
            fail_msg = str(variant.get("failure") or variant.get("status") or "rewrite_failed")
            article["editorial_score_gaps"] = variant.get("qa_fails") or [fail_msg]
            print(f"다음 시도 피드백: {article['editorial_score_gaps']}")
            continue

        body_html = normalize_ij_body_html(variant.get("body", ""))
        ok_val, val_msg = validate_cb_editorial_rewrite(
            variant.get("title", ""),
            body_html,
            editorial_ctx.packet,
            article,
        )
        score = score_cb_editorial_rewrite(
            variant.get("title", ""),
            variant.get("excerpt", ""),
            body_html,
            article,
            editorial_ctx.packet,
            qa_score=variant.get("qa_score"),
            evidence=editorial_ctx.evidence,
        )
        if score.get("publish_body"):
            body_html = score["publish_body"]
            variant = {**variant, "body": body_html}

        print(
            f"score={score['total']} pass={score['passes']} "
            f"publish_ready={score.get('article_publish_ready')} "
            f"gaps={score.get('gaps')}"
        )
        if ok_val and score.get("passes"):
            print(f"PASS: CB editorial review bundle ready ({ts})")
            return 0

        article["editorial_score_gaps"] = score.get("gaps") or [val_msg]
        print(f"다음 시도 피드백: {article['editorial_score_gaps']}")

    print("FAIL: max attempts reached")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

