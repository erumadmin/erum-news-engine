#!/usr/bin/env python3
"""
Run REVIEW_ONLY pipeline in a test → score → save loop until target score or max attempts.

Exit 0 when score >= TARGET (default 9.5). Saves scored HTML + compare MD per attempt.
"""

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
os.environ.setdefault("EDITORIAL_IMAGE_PROBE", "1")
os.environ.setdefault("EDITORIAL_IMAGE_PROBE_DOWNLOAD", "0")
os.environ.setdefault("EDITORIAL_PIPELINE", "1")
os.environ.setdefault("IJ_PACKET_PIPELINE", "1")
os.environ["IJ_TARGET_ENGINE"] = "1"
os.environ["IJ_PUBLISH_V4"] = "1"
os.environ.setdefault("TIER_C_ENABLED", "1")
os.environ.setdefault("EDITORIAL_REQUIRE_FULL_SOURCE", "1")

from engine.pipeline.editorial_report import (  # noqa: E402
    normalize_ij_body_html,
    write_editorial_quality_bundle,
)
from engine.pipeline.editorial_scorecard import TARGET_SCORE, score_editorial_rewrite  # noqa: E402
from engine.pipeline.rewrite_validate import validate_ij_editorial_rewrite  # noqa: E402

FIXTURE_URL = os.environ.get(
    "FIXTURE_URL",
    "https://www.korea.kr/news/policyNewsView.do?newsId=148965108&call_from=rsslink",
)
MAX_ATTEMPTS = int(os.environ.get("EDITORIAL_QUALITY_MAX_ATTEMPTS", "12"))
KST = ZoneInfo("Asia/Seoul")


_OFFICIAL_FIXTURE_HOSTS = (
    "price.go.kr",
    "en-ter.co.kr",
    "kepco.co.kr",
    "ftc.go.kr",
    "fairtrade.go.kr",
    "motie.go.kr",
)


def _live_research_fetcher(live_fetcher):
    """korea.kr = live ingest; known action hubs = stable fixture excerpts for discovered_facts."""

    from engine.pipeline.fixture_fetcher import target_fixture_fetcher

    def _fetch(url: str):
        u = (url or "").lower()
        if "korea.kr" in u:
            return live_fetcher(url)
        if any(host in u for host in _OFFICIAL_FIXTURE_HOSTS):
            return target_fixture_fetcher(url)
        try:
            resp = live_fetcher(url)
            if getattr(resp, "status_code", 500) < 400 and len(getattr(resp, "text", "") or "") > 200:
                return resp
        except Exception:
            pass
        return target_fixture_fetcher(url)

    return _fetch


def _fixture_dual_fetcher(research_fetcher):
    """Keep fixture 원문 on korea.kr ingest; still fetch official URLs for research."""

    def _fetch(url: str):
        u = (url or "").lower()
        if "korea.kr" in u and ("policynews" in u or "newsid=" in u):
            return type("R", (), {"status_code": 500, "text": ""})()
        return research_fetcher(url)

    return _fetch


def _load_article_from_compare_md(path: Path) -> tuple[str, str]:
    """Parse title + body from editorial_compare_*.md 원문 section."""
    text = path.read_text(encoding="utf-8")
    if "## 원문 (전문)" not in text:
        raise ValueError(f"compare MD missing 원문 section: {path}")
    after = text.split("## 원문 (전문)", 1)[1]
    block_lines: list[str] = []
    for ln in after.splitlines():
        if ln.strip().startswith("## "):
            break
        block_lines.append(ln)
    lines = [ln for ln in block_lines if ln.strip()]
    title = "제목 미상"
    body_lines = lines
    if lines and lines[0].startswith("**제목:"):
        title = lines[0].replace("**제목:**", "").strip()
        body_lines = lines[1:]
    return title, "\n".join(body_lines)


def _load_engine():
    import importlib.util

    spec = importlib.util.spec_from_file_location("erum_news_engine_main", ROOT / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _print_loop_goals() -> None:
    from engine.pipeline.editorial_scorecard import (
        TARGET_COALITION_BRIEFING,
        TARGET_ORIGINALITY,
        TARGET_READER_VALUE,
        TARGET_RESEARCH_DEPTH,
        TARGET_SCORE,
    )

    print("=== IJ 품질 루프 목표 ===")
    print(f"  총점 ≥ {TARGET_SCORE}")
    print(f"  reader_value ≥ {TARGET_READER_VALUE}, originality ≥ {TARGET_ORIGINALITY}")
    print(f"  research_depth ≥ {TARGET_RESEARCH_DEPTH}, coalition_briefing ≥ {TARGET_COALITION_BRIEFING}")
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if is_publish_v4_enabled():
        print("  게이트 (v4): article_publish_ready, 본문 무URL, validate_publish, research_depth≥7")
    else:
        print("  게이트: briefing_ready, coalition_takeaways_in_body, discovered≥1, 4문단+다만")
    print("========================\n")


def main() -> int:
    _print_loop_goals()
    eng = _load_engine()
    from engine.pipeline.orchestrator import run_pre_publish_pipeline

    source_json = os.environ.get("FIXTURE_JSON", "").strip()
    source_md = os.environ.get("FIXTURE_SOURCE_MD", "").strip()
    if source_json:
        json_path = Path(source_json)
        if not json_path.is_absolute():
            json_path = ROOT / json_path
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        os.environ["EDITORIAL_REQUIRE_FULL_SOURCE"] = "0"
        os.environ.setdefault("MIN_SOURCE_BODY_CHARS", "120")
        article = {
            "url": raw.get("url") or FIXTURE_URL,
            "url_id": eng.extract_unique_id(raw.get("url") or FIXTURE_URL),
            "title": os.environ.get("FIXTURE_TITLE", raw.get("title", "")),
            "body": raw.get("body") or "",
            "raw_html": raw.get("raw_html") or "",
            "image": "",
            "source_type": "policy_briefing",
            "ingest_source": "fixture_json",
        }
        from engine.pipeline.fixture_fetcher import target_fixture_fetcher

        fetcher = _fixture_dual_fetcher(target_fixture_fetcher)
    elif source_md:
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
    editorial_ctx = run_pre_publish_pipeline(article, fetcher=fetcher, persist=False)
    if editorial_ctx is None:
        print("DROP: pre-publish pipeline returned None")
        return 2
    if getattr(editorial_ctx, "skip_rewrite", False):
        print(
            f"FAIL: Target gate — rewrite skipped "
            f"({getattr(editorial_ctx, 'skip_rewrite_reason', '')})"
        )
        gate = (editorial_ctx.packet or {}).get("research_gate") or {}
        print(f"  research_depth={gate.get('research_depth')} reasons={gate.get('research_gate_reasons')}")
        return 2

    ingest_reason = article.get("ingest_source", "unknown")
    upload_counts = {p: 0 for p in eng.MEDIA_PREFIXES}
    out_dir = Path(eng._review_output_dir())
    last_paths: dict[str, str] = {}
    last_score: dict | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        ts = datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S")
        print(f"\n=== 품질 루프 시도 {attempt}/{MAX_ATTEMPTS} ===")
        try:
            result = eng.process_article(
                article, upload_counts, review_mode=True, editorial_ctx=editorial_ctx
            )
        except Exception as exc:
            print(f"FAIL: {exc}")
            return 1

        variant = next((v for v in result.get("variants", []) if v.get("prefix") == "IJ_"), {})
        if not variant or variant.get("status") != "SUCCESS":
            print(f"FAIL: {variant}")
            article["editorial_score_gaps"] = [
                str(variant.get("failure") or variant.get("status") or "rewrite_failed")
            ]
            continue

        body_html = normalize_ij_body_html(variant.get("body", ""))
        from engine.pipeline.publish_validate import is_publish_v4_enabled, publish_sanitize_body

        if is_publish_v4_enabled():
            body_html, _ = publish_sanitize_body(body_html, editorial_ctx.packet, article)
            variant = {**variant, "body": body_html}
        ok_val, val_msg = validate_ij_editorial_rewrite(
            variant.get("title", ""),
            body_html,
            editorial_ctx.packet,
            article,
        )
        score = score_editorial_rewrite(
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
        score["validation_ok"] = ok_val
        score["validation_msg"] = val_msg
        if is_publish_v4_enabled():
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
            score["passes"] = bool(
                ok_val
                and publish_gate.get("article_publish_ready")
                and score.get("total", 0) >= TARGET_SCORE
            )
        else:
            score["passes"] = bool(score["passes"] and ok_val)

        from engine.pipeline.publish_preflight import build_publish_preflight

        image_probe = result.get("image_probe") if isinstance(result, dict) else None
        publish_preflight = build_publish_preflight(
            variant={**variant, "body": body_html, "status": "SUCCESS"},
            article=article,
            editorial_ctx=editorial_ctx,
            image_probe=image_probe,
            score=score,
            review_mode=True,
            image_required=(getattr(editorial_ctx, "assigned_site", None) == "IJ"),
        )
        last_paths = write_editorial_quality_bundle(
            out_dir,
            ts=ts,
            article=article,
            editorial_ctx=editorial_ctx,
            variant={**variant, "body": body_html},
            score=score,
            ingest_reason=ingest_reason,
            attempt=attempt,
            image_probe=image_probe,
            publish_preflight=publish_preflight,
        )
        if is_publish_v4_enabled() and last_paths.get("latest_score"):
            score = json.loads(Path(last_paths["latest_score"]).read_text(encoding="utf-8"))
        last_score = score

        print(f"URL: {FIXTURE_URL}")
        print(f"QA: {variant.get('qa_score')}")
        print(f"검증: {'OK' if ok_val else val_msg}")
        print(f"Score: {score['total']} / 10 (target {TARGET_SCORE})")
        dims = score["dimensions"]
        rv = dims.get("reader_value", 0)
        orig = dims.get("originality", 0)
        print(
            f"Dimensions: {dims} "
            f"(reader_value≥{score.get('target_reader_value', 9.0)}→{rv}, "
            f"originality≥{score.get('target_originality', 9.0)}→{orig})"
        )
        ru = (editorial_ctx.packet or {}).get("reader_utility") or {}
        print(
            f"reader_utility 슬롯: scenarios={len(ru.get('scenarios') or [])} "
            f"checklist={len(ru.get('checklist') or [])} "
            f"quotes={len(ru.get('evidence_quotes') or [])} "
            f"source_quotes={len(ru.get('source_confirmation_quotes') or [])}"
        )
        if score["gaps"]:
            print("Gaps:")
            for g in score["gaps"]:
                print(f"  - {g}")
        print(f"Artifacts: {last_paths}")

        if score["passes"]:
            print(f"\n통과 (시도 {attempt}).")
            return 0

        article["editorial_score_gaps"] = score.get("gaps") or []
        print(f"다음 시도 피드백: {article['editorial_score_gaps']}")
        best = float(score.get("total") or 0)
        prev_best = float(article.get("_editorial_best_score") or 0)
        if best >= prev_best:
            article["_editorial_best_score"] = best
            article["_editorial_best_body"] = body_html

    if article.get("_editorial_best_body"):
        print(
            f"\n최고 점수 {article['_editorial_best_score']} — "
            "목표 미달이지만 최선 본문을 article에 보존했습니다."
        )

    print(f"\n미통과: {MAX_ATTEMPTS}회 시도 후 목표 {TARGET_SCORE} 미달.")
    if last_score:
        print(f"마지막 점수: {last_score['total']}")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
