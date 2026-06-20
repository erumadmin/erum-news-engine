#!/usr/bin/env python3
"""NN (이웃뉴스) editorial quality loop — image → research → rewrite → publish preflight."""

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
os.environ.setdefault("NN_PACKET_PIPELINE", "1")
os.environ.setdefault("NN_TARGET_ENGINE", "1")
os.environ.setdefault("NN_PUBLISH_V4", "1")
os.environ.setdefault("EDITORIAL_FORCE_SITE", "NN")
os.environ["IJ_TARGET_ENGINE"] = "0"
os.environ.setdefault("TIER_C_ENABLED", "1")
os.environ.setdefault("EDITORIAL_REQUIRE_FULL_SOURCE", "1")
os.environ.setdefault("MIN_IMAGE_WIDTH", "720")

from engine.pipeline.editorial_report import (  # noqa: E402
    normalize_ij_body_html,
    write_editorial_quality_bundle,
)
from engine.pipeline.nn_scorecard import TARGET_SCORE, score_nn_editorial_rewrite  # noqa: E402
from engine.pipeline.nn_rewrite_validate import validate_nn_editorial_rewrite  # noqa: E402
from engine.pipeline.publish_body import prepare_nn_publish_body  # noqa: E402
from engine.pipeline.publish_preflight import build_publish_preflight  # noqa: E402

FIXTURE_URL = os.environ.get(
    "FIXTURE_URL",
    "https://www.korea.kr/news/policyNewsView.do?newsId=148965573&call_from=rsslink",
)
MAX_ATTEMPTS = int(os.environ.get("NN_EDITORIAL_QUALITY_MAX_ATTEMPTS", "12"))
KST = ZoneInfo("Asia/Seoul")


def _load_engine():
    import importlib.util

    spec = importlib.util.spec_from_file_location("erum_news_engine_main", ROOT / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _print_goals() -> None:
    from engine.pipeline.nn_scorecard import (
        TARGET_COMMUNITY_AXES,
        TARGET_ORIGINALITY,
        TARGET_READER_VALUE,
    )

    print("=== NN (이웃뉴스) 품질 루프 ===")
    print(f"  총점 ≥ {TARGET_SCORE}")
    print(f"  community_axes ≥ {TARGET_COMMUNITY_AXES}, reader_value ≥ {TARGET_READER_VALUE}")
    print(f"  originality ≥ {TARGET_ORIGINALITY}, article_publish_ready (v4)")
    print(f"  이미지: editorial_stages gate (download) + probe in review\n")


def _inject_cached_image(article: dict, image_path: Path) -> None:
    img_bytes = image_path.read_bytes()
    url = article.get("url") or "fixture://cached-image"
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
    os.environ["IJ_TARGET_ENGINE"] = "0"
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
    if editorial_ctx.assigned_site != "NN":
        print(f"WARN: assigned_site={editorial_ctx.assigned_site} (expected NN)")

    upload_counts = {p: 0 for p in eng.MEDIA_PREFIXES}
    out_dir = Path(eng._review_output_dir())

    for attempt in range(1, MAX_ATTEMPTS + 1):
        ts = datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S")
        print(f"\n=== NN 시도 {attempt}/{MAX_ATTEMPTS} ===")
        try:
            result = eng.process_article(
                article, upload_counts, review_mode=True, editorial_ctx=editorial_ctx
            )
        except Exception as exc:
            print(f"FAIL: {exc}")
            return 1

        variant = next((v for v in result.get("variants", []) if v.get("prefix") == "NN_"), {})
        if not variant or variant.get("status") != "SUCCESS":
            print(f"FAIL: {variant}")
            fail_msg = str(variant.get("failure") or variant.get("status") or "rewrite_failed")
            article["editorial_score_gaps"] = variant.get("qa_fails") or [fail_msg]
            print(f"다음 시도 피드백: {article['editorial_score_gaps']}")
            continue

        body_html = normalize_ij_body_html(variant.get("body", ""))

        ok_val, val_msg = validate_nn_editorial_rewrite(
            variant.get("title", ""),
            body_html,
            editorial_ctx.packet,
            article,
        )
        score = score_nn_editorial_rewrite(
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

        from engine.pipeline.publish_validate import article_publish_ready

        publish_gate = article_publish_ready(
            variant.get("title", ""),
            variant.get("excerpt", ""),
            body_html,
            editorial_ctx.packet,
            article,
            score_total=score.get("total"),
        )
        score["article_publish_ready"] = publish_gate.get("article_publish_ready")
        score["publish_validation"] = publish_gate.get("publish_validation")
        score["sources_footer"] = publish_gate.get("sources_footer")
        score["validation_ok"] = ok_val
        score["validation_msg"] = val_msg
        score["passes"] = bool(
            ok_val
            and publish_gate.get("article_publish_ready")
            and score.get("total", 0) >= TARGET_SCORE
        )

        pub = prepare_nn_publish_body(
            variant.get("title", ""),
            variant.get("excerpt", ""),
            body_html,
            editorial_ctx.packet,
            article,
            score_total=score.get("total"),
        )
        body_html = pub["body_html"]
        variant = {**variant, "body": body_html}

        image_probe = result.get("image_probe")
        publish_preflight = build_publish_preflight(
            variant={**variant, "body": body_html, "status": "SUCCESS"},
            article=article,
            editorial_ctx=editorial_ctx,
            image_probe=image_probe,
            score=score,
            review_mode=True,
            image_required=True,
        )
        score["publish_preflight"] = publish_preflight

        last_paths = write_editorial_quality_bundle(
            out_dir,
            ts=ts,
            article=article,
            editorial_ctx=editorial_ctx,
            variant={**variant, "body": body_html, "prefix": "NN_"},
            score=score,
            ingest_reason=article.get("ingest_source", "live"),
            attempt=attempt,
            image_probe=image_probe,
            publish_preflight=publish_preflight,
        )

        print(f"URL: {article.get('url', FIXTURE_URL)}")
        print(f"QA: {variant.get('qa_score')}")
        print(f"검증: {'OK' if ok_val else val_msg}")
        print(f"publish_ready: {score.get('article_publish_ready')}")
        print(f"Score: {score['total']} / 10 (target {TARGET_SCORE})")
        print(f"Dimensions: {score['dimensions']}")
        if image_probe:
            print(f"Image: {image_probe.get('status')} download_ok={image_probe.get('download_ok')}")
        print(f"Preflight: would_publish_api={publish_preflight.get('would_publish_api')}")
        if score["gaps"]:
            for g in score["gaps"]:
                print(f"  gap: {g}")
        print(f"Artifacts: {last_paths}")

        if score["passes"]:
            print(f"\nNN 통과 (시도 {attempt}).")
            return 0
        article["editorial_score_gaps"] = score.get("gaps") or [val_msg]
        print(f"다음 시도 피드백: {article['editorial_score_gaps']}")

    print(f"\nNN 미통과 (최대 {MAX_ATTEMPTS}회).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
