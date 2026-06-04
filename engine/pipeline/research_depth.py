"""Research depth score (0–10) for Target engine gate."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def research_depth_config() -> dict[str, float | int]:
    return {
        "min_ok_evidence": _env_int("RESEARCH_MIN_OK_EVIDENCE", 1),
        "min_discovered": _env_int("RESEARCH_MIN_DISCOVERED_FACTS", 1),
        "depth_min": _env_float("RESEARCH_DEPTH_MIN", 7.0),
    }


def compute_research_depth(
    evidence: list[dict[str, Any]],
    discovered_facts: list[dict[str, Any]],
    packet: dict[str, Any],
) -> float:
    cfg = research_depth_config()
    score = 0.0
    ok = [e for e in evidence if e.get("fetch_status") == "ok"]
    ok_substantive = [
        e
        for e in ok
        if len((e.get("body_excerpt") or "").strip()) >= 80
    ]
    if len(ok_substantive) >= cfg["min_ok_evidence"]:
        score += 2.0
    if len(discovered_facts) >= cfg["min_discovered"]:
        score += 2.0

    hosts: set[str] = set()
    for e in ok:
        host = (urlparse(e.get("url") or "").netloc or "").lower()
        if host:
            hosts.add(host)
    if len(hosts) >= 2:
        score += 2.0

    ru = packet.get("reader_utility") or {}
    links = ru.get("primary_links") or []
    action = packet.get("action_items") or []
    reader_hosts = set()
    for url in list(links) + list(action):
        h = (urlparse(str(url)).netloc or "").lower()
        if h:
            reader_hosts.add(h)
    for e in ok:
        h = (urlparse(e.get("url") or "").netloc or "").lower()
        if h in reader_hosts:
            score += 2.0
            break

    if ok_substantive and discovered_facts:
        score += 2.0

    briefing = packet.get("briefing_ready")
    if isinstance(briefing, dict) and briefing.get("briefing_ready"):
        score += 1.0
    elif len(discovered_facts) >= 2:
        score += 1.0

    return min(10.0, score)


def assess_research_gate(
    evidence: list[dict[str, Any]],
    discovered_facts: list[dict[str, Any]],
    packet: dict[str, Any],
) -> dict[str, Any]:
    cfg = research_depth_config()
    depth = compute_research_depth(evidence, discovered_facts, packet)
    ok = [e for e in evidence if e.get("fetch_status") == "ok"]
    ok_sub = [e for e in ok if len((e.get("body_excerpt") or "").strip()) >= 80]
    reasons: list[str] = []
    if len(ok_sub) < cfg["min_ok_evidence"]:
        reasons.append("ok_evidence_below_min")
    if len(discovered_facts) < cfg["min_discovered"]:
        reasons.append("discovered_below_min")
    if depth < cfg["depth_min"]:
        reasons.append("research_depth_below_min")
    # REVIEW_ONLY + fixture 원문: live evidence fetch may fail; packet slots still gate quality.
    if os.environ.get("REVIEW_ONLY", "0") == "1":
        raw_body = ((packet.get("_raw_source") or {}).get("body") or "").strip()
        if len(raw_body) >= 400 and (packet.get("key_facts") or []):
            depth = max(depth, float(cfg["depth_min"]))
            reasons = [
                r
                for r in reasons
                if r
                not in (
                    "research_depth_below_min",
                    "discovered_below_min",
                    "ok_evidence_below_min",
                )
            ]
    insufficient = bool(reasons)
    return {
        "research_depth": round(depth, 2),
        "research_insufficient": insufficient,
        "research_gate_reasons": reasons,
        "research_depth_min": cfg["depth_min"],
    }
