"""Inject missing discovered_facts into IJ body (excerpt substrings only)."""

from __future__ import annotations

from typing import Any

from engine.pipeline.discovered_facts import discovered_fact_reflected_in_plain
from engine.pipeline.rewrite_validate import _paragraph_plain_blocks
from research_collector import strip_html_tags

MAX_DISCOVERED_INJECT_CHARS = 120
MAX_PARAGRAPH3_CHARS = 900


def _truncate_discovered_snippet(fact: str, max_chars: int = MAX_DISCOVERED_INJECT_CHARS) -> str:
    """Trim at last complete sentence; never cut inside parentheses."""
    fact = (fact or "").strip()
    if len(fact) <= max_chars:
        return fact
    window = fact[:max_chars]
    cut = window.rfind("다.")
    if cut >= 20:
        window = window[: cut + 2]
    else:
        window = window.rstrip()
        if len(window) < 20:
            return ""
    while window.count("(") > window.count(")"):
        window = window.rsplit("(", 1)[0].rstrip()
    while window.count("（") > window.count("）"):
        window = window.rsplit("（", 1)[0].rstrip()
    return window.rstrip(" ,;·")


def inject_discovered_fact_anchors(body: str, packet: dict[str, Any]) -> str:
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if is_publish_v4_enabled():
        return body
    discovered = packet.get("discovered_facts") or []
    if not discovered:
        return body
    paras = _paragraph_plain_blocks(body)
    if len(paras) < 3:
        return body
    plain = strip_html_tags(body)
    for item in discovered:
        fact = (item.get("fact") or "").strip()
        if len(fact) < 20:
            continue
        if discovered_fact_reflected_in_plain(fact, plain):
            continue
        snippet = _truncate_discovered_snippet(fact)
        if len(paras[2]) + len(snippet) + 1 > MAX_PARAGRAPH3_CHARS:
            continue
        paras[2] = f"{paras[2].rstrip()} {snippet}".strip()
        return "".join(f"<p>{p}</p>" for p in paras[:4])
    return body
