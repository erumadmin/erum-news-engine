from __future__ import annotations

from typing import Any

from engine.types import PlacementScore, PlacementSlot, PublishGrade

SITE_PREFIX = {"IJ": "IJ_", "NN": "NN_", "CB": "CB_"}


def score_placement(
    packet: dict[str, Any],
    *,
    title: str = "",
    excerpt: str = "",
    publish_grade: PublishGrade = "C",
    thresholds: dict[str, int] | None = None,
) -> PlacementScore:
    """Article QA is separate; this scores homepage slot eligibility."""
    thresholds = thresholds or {"hero": 85, "secondary_lead": 70, "proof_row": 50}

    official = int(packet.get("official_evidence_count") or 0)
    key_facts = len(packet.get("key_facts") or [])
    risk_flags = list(packet.get("risk_flags") or [])
    image_tier = packet.get("image_asset_tier") or "none"

    social_clarity = min(30, 10 + official * 6 + (8 if key_facts >= 2 else 0))
    headline_strength = min(20, len((title or packet.get("main_claim") or "")) // 4)
    summary_strength = min(15, len(excerpt or packet.get("why_now") or "") // 6)
    image_trust = {"owned": 15, "official": 12, "none": 4, "forbidden": 0}.get(image_tier, 4)
    fact_density = min(10, key_facts * 2)
    timeliness = {"A": 10, "B": 8, "C": 5, "D": 2}.get(publish_grade, 5)

    total = social_clarity + headline_strength + summary_strength + image_trust + fact_density + timeliness
    hard_failures: list[str] = []
    if official < 2 and publish_grade == "A":
        hard_failures.append("hero_requires_two_official_sources")
    if "official_evidence_missing" in risk_flags and total >= thresholds["secondary_lead"]:
        hard_failures.append("official_evidence_missing")
    if image_tier == "forbidden":
        hard_failures.append("forbidden_image_tier")
    if "announcement_only_risk" in risk_flags:
        hard_failures.append("announcement_only_risk")

    slot: PlacementSlot = "ledger"
    if not hard_failures:
        if total >= thresholds["hero"]:
            slot = "hero"
        elif total >= thresholds["secondary_lead"]:
            slot = "secondary_lead"
        elif total >= thresholds["proof_row"]:
            slot = "proof_row"

    # Grade D never gets hero
    if publish_grade == "D":
        slot = "ledger"
        hard_failures.append("publish_grade_D")

    return PlacementScore(
        total=total,
        social_clarity=social_clarity,
        headline_strength=headline_strength,
        summary_strength=summary_strength,
        image_trust=image_trust,
        fact_density=fact_density,
        timeliness=timeliness,
        slot=slot,
        hard_failures=hard_failures,
    )
