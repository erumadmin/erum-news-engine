"""Dry-run publish checklist: what would happen without calling publish APIs."""

from __future__ import annotations

from typing import Any

from engine.pipeline.layout_decision import decide_layout_type


def build_publish_preflight(
    *,
    variant: dict[str, Any],
    article: dict[str, Any],
    editorial_ctx: Any,
    image_probe: dict[str, Any] | None,
    score: dict[str, Any],
    review_mode: bool = True,
) -> dict[str, Any]:
    placement = getattr(editorial_ctx, "placement", None) if editorial_ctx else None
    slot = getattr(placement, "slot", "ledger") if placement else "ledger"
    grade = getattr(editorial_ctx, "publish_grade", "C") if editorial_ctx else "C"
    layout = decide_layout_type(image_probe, placement_slot=slot, publish_grade=grade)

    text_ready = bool(
        variant.get("status") == "SUCCESS"
        and score.get("passes")
        and score.get("article_publish_ready", score.get("passes"))
    )
    img_status = (image_probe or {}).get("status", "not_probed")
    img_ok_for_hero = img_status == "download_ok" or (
        img_status == "candidates_ok" and bool((image_probe or {}).get("selected_url"))
    )

    blocked: list[str] = []
    if not text_ready:
        blocked.append("TEXT_GATE")
    if layout == "hero" and not img_ok_for_hero:
        blocked.append("HERO_IMAGE_MISSING")
    if img_status in ("error", "no_candidates", "download_failed") and layout in ("hero", "card"):
        blocked.append("IMAGE_WEAK_FOR_SLOT")

    live_blocked = list(blocked)
    if review_mode:
        blocked.append("REVIEW_ONLY")

    return {
        "text_publish_ready": text_ready,
        "would_publish_api": text_ready and not live_blocked,
        "would_publish": text_ready and not live_blocked,
        "review_mode": review_mode,
        "layout_type": layout,
        "placement_slot": slot,
        "publish_grade": grade,
        "image_status": img_status,
        "featured_image_url": (image_probe or {}).get("selected_url", ""),
        "image_download_ok": bool((image_probe or {}).get("download_ok")),
        "r2_required_for_erum": True,
        "blocked_reasons": blocked,
        "assigned_site": getattr(editorial_ctx, "assigned_site", None) if editorial_ctx else None,
    }
