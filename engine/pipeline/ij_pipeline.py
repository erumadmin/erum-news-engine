"""IJ-aware editorial pipeline: image gate before research for IJ articles."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from engine.pipeline.exceptions import PipelineFailure
from engine.pipeline.article_images import require_article_image
from engine.pipeline.ingest import enrich_article_from_page
from engine.pipeline.orchestrator import enrich_raw_source, should_use_ij_editorial_rewrite
from engine.pipeline.placement import score_placement
from engine.profiles import get_profile, route_primary
from engine.types import EditorialContext, SiteCode

import research_collector as rc


def _research_and_build_context(
    raw: dict[str, Any],
    assigned: SiteCode,
    route_reason: str,
    route_score: float,
    profile: Any,
    fetcher: Optional[Callable[[str], Any]],
    *,
    persist: bool = False,
    db_hooks: Optional[dict[str, Callable[..., Any]]] = None,
) -> Optional[EditorialContext]:
    max_fetch = profile.collect_evidence_plan(raw).get("max_fetch", 3)
    research = rc.run_research_pipeline(
        raw,
        fetcher=fetcher,
        assigned_site=assigned,
        max_fetch=max_fetch,
    )

    packet = research["packet"]
    publish_grade = packet.get("publish_grade", "D")
    if publish_grade == "D":
        print(f"   🚫 [2차결정] publish_grade D — 발행 스킵")
        return None

    placement = score_placement(
        packet,
        publish_grade=publish_grade,
        thresholds=profile.placement_config(),
    )
    print(
        f"   📐 [배치] slot={placement.slot} score={placement.total} "
        f"grade={publish_grade} hints={packet.get('placement_hint')}"
    )

    use_packet = should_use_ij_editorial_rewrite(assigned)
    skip_rewrite = False
    skip_rewrite_reason = ""
    if assigned == "IJ" and use_packet:
        from engine.pipeline.target_engine import should_skip_rewrite

        if should_skip_rewrite(packet):
            skip_rewrite = True
            skip_rewrite_reason = "research_insufficient"
            print("   ⏭️ [Target] 조사 부족 — IJ 재작성 스킵 (research_insufficient)")

    raw_id: Optional[int] = None
    packet_id: Optional[int] = None
    if persist and db_hooks:
        raw_id = db_hooks.get("save_raw_source", lambda *_a, **_k: None)(raw, research)
        packet_id = db_hooks.get("save_research_packet", lambda *_a, **_k: None)(
            raw_id, assigned, packet, publish_grade, placement
        )

    return EditorialContext(
        assigned_site=assigned,
        routing_reason=route_reason,
        publish_grade=publish_grade,
        placement=placement,
        packet=packet,
        evidence=research.get("evidence", []),
        use_packet_writing=use_packet,
        raw_source_id=raw_id,
        research_packet_id=packet_id,
        skip_rewrite=skip_rewrite,
        skip_rewrite_reason=skip_rewrite_reason,
    )


def run_ij_editorial_stages(
    article: dict[str, Any],
    fetcher: Optional[Callable[[str], Any]] = None,
    *,
    persist: bool = False,
    db_hooks: Optional[dict[str, Callable[..., Any]]] = None,
) -> Optional[EditorialContext]:
    """
    Ingest -> route/filter -> (IJ only) image gate -> research -> placement.
    Returns None when the article should be dropped.
    """
    require_fetch = os.environ.get("EDITORIAL_REQUIRE_FULL_SOURCE", "0") == "1"
    ok, enriched, ingest_reason = enrich_article_from_page(
        article,
        fetcher,
        require_fetch=require_fetch,
    )
    print(f"   📥 [원문수집] {ingest_reason}")
    if not ok:
        print(f"   🚫 [원문수집] 실패 — 파이프라인 중단 ({ingest_reason})")
        return None
    enriched_copy = dict(enriched)
    article.clear()
    article.update(enriched_copy)

    raw = enrich_raw_source(article)
    route = route_primary(raw)
    if route.site == "DROP":
        print(f"   🚫 [라우팅] DROP ({route.reason}, score={route.score:.1f})")
        return None

    assigned: SiteCode = route.site
    profile = get_profile(assigned)
    cand = profile.candidate_filter(raw)
    print(
        f"   🔎 [후보필터] {assigned} "
        f"{'ACCEPT' if cand.accept else 'DROP'} ({cand.reason})"
    )
    if not cand.accept:
        return None
    print(f"   🧭 [라우팅] {assigned} ({route.reason}, score={route.score:.1f})")

    if assigned == "IJ":
        try:
            img_result = require_article_image(article, download=True)
            article["_ij_img_result"] = img_result
        except PipelineFailure as e:
            print(f"   🖼️ [이미지] {e.code} — 기사 스킵")
            article["_skip_reason"] = e.code
            article["_skip_image_status"] = e.code
            return None

    return _research_and_build_context(
        raw,
        assigned,
        route.reason,
        route.score,
        profile,
        fetcher,
        persist=persist,
        db_hooks=db_hooks,
    )
