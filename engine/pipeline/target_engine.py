"""IJ Target engine: enrich packet with discovered facts, research gate, coalition brief."""

from __future__ import annotations

import os
from typing import Any

from engine.pipeline.coalition_brief import (
    assess_briefing_ready,
    build_journalist_brief,
    build_source_facts,
)
from engine.pipeline.coalition_takeaways import build_field_takeaways
from engine.pipeline.discovered_facts import extract_discovered_facts
from engine.pipeline.research_depth import assess_research_gate


def is_target_engine_enabled() -> bool:
    return os.environ.get("IJ_TARGET_ENGINE", "0").strip() not in ("0", "false", "False")


def enrich_packet_target(
    raw_source: dict[str, Any],
    packet: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Mutate packet dict in place with Target v3 fields; return packet."""
    discovered = extract_discovered_facts(raw_source, evidence)
    source_facts = build_source_facts(raw_source, packet)
    journalist_brief = build_journalist_brief(raw_source, packet, discovered)
    packet["journalist_brief"] = journalist_brief
    packet["_raw_source"] = {
        "title": (raw_source.get("title") or "").strip(),
        "body": raw_source.get("body") or "",
        "url": (raw_source.get("url") or raw_source.get("source_url") or "").strip(),
    }
    packet["field_takeaways"] = build_field_takeaways(raw_source, packet, discovered)
    briefing = assess_briefing_ready(packet, discovered)
    packet["briefing_ready"] = briefing
    gate = assess_research_gate(evidence, discovered, packet)

    meta = dict(packet.get("research_meta") or {})
    meta["packet_version"] = 3
    meta["research_depth"] = gate["research_depth"]
    meta["target_engine"] = True

    risk = list(packet.get("risk_flags") or [])
    if gate["research_insufficient"]:
        if "research_insufficient" not in risk:
            risk.append("research_insufficient")
        grade = packet.get("publish_grade", "C")
        if grade in ("A", "B"):
            packet["publish_grade"] = "C"
    packet["risk_flags"] = risk

    packet["research_meta"] = meta
    packet["discovered_facts"] = discovered
    packet["source_facts"] = source_facts
    packet["journalist_brief"] = journalist_brief
    packet["briefing_ready"] = briefing
    packet["research_gate"] = gate
    return packet


def should_skip_rewrite(packet: dict[str, Any]) -> bool:
    if not is_target_engine_enabled():
        return False
    if os.environ.get("RESEARCH_INSUFFICIENT_SKIP_REWRITE", "1").strip() in ("0", "false"):
        return False
    gate = packet.get("research_gate") or {}
    return bool(gate.get("research_insufficient"))
