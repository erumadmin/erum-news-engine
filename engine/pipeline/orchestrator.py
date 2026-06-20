from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable, Optional

from engine.pipeline.ingest import enrich_article_from_page
from engine.pipeline.placement import score_placement
from engine.profiles import get_profile, route_primary
from engine.types import EditorialContext, SiteCode

import research_collector as rc


def should_use_ij_editorial_rewrite(assigned_site: str) -> bool:
    """
  IJ + IJ_PACKET_PIPELINE=1: 하이브리드 유저 메시지(원문 전문 + 패킷 + 근거).
  System prompt는 GitHub prompts/news_editor_common + news_editor_ij 그대로.
  """
    return assigned_site == "IJ" and os.environ.get("IJ_PACKET_PIPELINE", "1") != "0"


def should_use_nn_editorial_rewrite(assigned_site: str) -> bool:
    """NN + NN_PACKET_PIPELINE=1: 원문 + 패킷 + community_brief 하이브리드 재작성."""
    return assigned_site == "NN" and os.environ.get("NN_PACKET_PIPELINE", "0") == "1"


def should_use_cb_editorial_rewrite(assigned_site: str) -> bool:
    """CB + CB_PACKET_PIPELINE=1: 원문 + 패킷 + compliance_brief 하이브리드 재작성."""
    return assigned_site == "CB" and os.environ.get("CB_PACKET_PIPELINE", "0") == "1"


def should_use_packet_editorial_rewrite(assigned_site: str) -> bool:
    return (
        should_use_ij_editorial_rewrite(assigned_site)
        or should_use_nn_editorial_rewrite(assigned_site)
        or should_use_cb_editorial_rewrite(assigned_site)
    )


def source_hash(raw_source: dict[str, Any]) -> str:
    url = (raw_source.get("url") or raw_source.get("source_url") or "").strip()
    title = (raw_source.get("title") or raw_source.get("source_title") or "").strip()
    payload = f"{url}|{title}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def enrich_raw_source(article: dict[str, Any]) -> dict[str, Any]:
    """Normalize engine collect_articles() shape to research pipeline shape."""
    body = article.get("body") or ""
    return {
        "url": article.get("url", ""),
        "url_id": article.get("url_id", ""),
        "title": article.get("title", ""),
        "body": body,
        "raw_html": article.get("raw_html") or body,
        "source_type": article.get("source_type")
        or ("newswire" if "newswire" in (article.get("url") or "") else "policy_briefing"),
        "source_published_at": article.get("source_published_at"),
        "image": article.get("image", ""),
        "source_hash": source_hash(article),
    }


def run_pre_publish_pipeline(
    article: dict[str, Any],
    fetcher: Optional[Callable[[str], Any]] = None,
    *,
    persist: bool = False,
    db_hooks: Optional[dict[str, Callable[..., Any]]] = None,
) -> Optional[EditorialContext]:
    """
    Ingest (full page) -> candidate filter -> route -> research -> packet -> placement.
    Returns None when article should be dropped.
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

    force_site = os.environ.get("EDITORIAL_FORCE_SITE", "").strip().upper()
    assigned: SiteCode = force_site if force_site in ("IJ", "NN", "CB") else route.site
    if force_site in ("IJ", "NN", "CB") and force_site != route.site:
        print(f"   🧭 [라우팅] FORCE {assigned} (auto={route.site})")
    profile = get_profile(assigned)
    cand = profile.candidate_filter(raw)
    print(
        f"   🔎 [후보필터] {assigned} "
        f"{'ACCEPT' if cand.accept else 'DROP'} ({cand.reason})"
    )
    if not cand.accept:
        return None
    print(f"   🧭 [라우팅] {assigned} ({route.reason}, score={route.score:.1f})")

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

    if assigned == "NN" and os.environ.get("NN_TARGET_ENGINE", "0") == "1":
        from engine.pipeline.nn_community_brief import build_community_brief

        packet = {**packet, "community_brief": build_community_brief({**packet, "_raw_source": raw})}
    if assigned == "CB" and os.environ.get("CB_TARGET_ENGINE", "0") == "1":
        from engine.pipeline.cb_packet_writer import build_compliance_brief

        packet = {**packet, "compliance_brief": build_compliance_brief(packet)}

    use_packet = should_use_packet_editorial_rewrite(assigned)
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
        routing_reason=route.reason,
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
