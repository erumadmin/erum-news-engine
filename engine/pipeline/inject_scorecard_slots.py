"""Finalize: inject packet slots until reader_value / originality rubrics are satisfied."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from engine.pipeline.discovered_facts import discovered_fact_reflected_in_plain
from engine.pipeline.inject_discovered import _truncate_discovered_snippet
from engine.pipeline.editorial_originality import (
    comparison_cues_for_source,
    inject_originality_anchors,
)
from engine.pipeline.reader_utility import (
    _checklist_reflected,
    _scenario_reflected,
    _url_reflected_in_plain,
)
from engine.pipeline.rewrite_validate import (
    _paragraph_plain_blocks,
    ensure_valid_limitation_paragraph,
    strip_para4_expansion_sentences,
)

MAX_P3 = 920
MAX_P2 = 880
MAX_P4 = 480


def _room(para: str, cap: int) -> int:
    return max(0, cap - len(para))


def _append_para(paras: list[str], idx: int, suffix: str, cap: int) -> bool:
    suffix = (suffix or "").strip()
    if not suffix or idx >= len(paras):
        return False
    if _room(paras[idx], cap) < len(suffix) + 1:
        return False
    paras[idx] = f"{paras[idx].rstrip()} {suffix}".strip()
    return True


def ensure_scorecard_slots(
    body: str,
    packet: dict[str, Any],
    source_body: str,
) -> str:
    """Source-backed injections aligned with score_reader_value / score_originality."""
    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body
    from engine.pipeline.editorial_originality import reframe_para1_against_source

    paras = reframe_para1_against_source(paras, packet, source_body)
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if is_publish_v4_enabled():
        return "".join(f"<p>{p}</p>" for p in paras[:4])

    plain = " ".join(paras)
    ru = packet.get("reader_utility") or {}
    source_body = source_body or ""

    scenarios = ru.get("scenarios") or []
    if scenarios and not any(_scenario_reflected(s, plain) for s in scenarios):
        snippet = (scenarios[0].get("body") or "")[:85].strip()
        if snippet and "반면" not in snippet[:6]:
            snippet = f"반면 {snippet}" if any(m in snippet for m in ("주요국", "미·", "일 등")) else snippet
        if snippet:
            _append_para(paras, 1, snippet, MAX_P2)
            plain = " ".join(paras)

    checklist = list(ru.get("checklist") or [])
    if len(checklist) < 2 and source_body:
        from engine.pipeline.reader_utility import extract_checklist

        for step in extract_checklist(source_body):
            if step not in checklist:
                checklist.append(step)
    missing = [c for c in checklist if not _checklist_reflected(c, plain)]
    for step in missing[:2]:
        text = (step.get("step") or "").strip()[:100]
        if text and _append_para(paras, 2, text, MAX_P3):
            plain = " ".join(paras)

    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if not is_publish_v4_enabled():
        links = ru.get("primary_links") or []
        for link in links[:2]:
            url = (link.get("url") or "").strip()
            label = (link.get("label") or "공식 안내").strip()
            if not url or _url_reflected_in_plain(url, plain):
                continue
            host = (urlparse(url).netloc or "").lower()
            short = label if len(label) < 20 else ("보도자료 원문" if "korea.kr" in host else "공식 안내")
            suffix = f"{short}: {url}"
            if _append_para(paras, 2, suffix, MAX_P3) or _append_para(paras, 1, suffix, MAX_P2):
                plain = " ".join(paras)

    from engine.pipeline.reader_utility import is_irrelevant_evidence_snippet

    quotes = (ru.get("evidence_quotes") or []) + (ru.get("source_confirmation_quotes") or [])
    quotes = [q for q in quotes if not is_irrelevant_evidence_snippet((q.get("quote") or ""))]
    if quotes and not any((q.get("quote") or "")[:40] in plain for q in quotes):
        snippet = (quotes[0].get("quote") or "").strip()
        if len(snippet) >= 30:
            use = snippet[:70].rstrip("., ") + ("…" if len(snippet) > 70 else "")
            quote_suffix = f'공식 보도에 따르면, "{use}"'
            if _append_para(paras, 2, quote_suffix, MAX_P3) or _append_para(paras, 1, quote_suffix, MAX_P2):
                plain = " ".join(paras)

    cues = comparison_cues_for_source(source_body)
    if cues and sum(1 for c in cues if c in plain) < 2:
        for ln in source_body.splitlines():
            ln = ln.strip()
            if len(ln) < 25 or not any(c in ln for c in cues):
                continue
            if ln[:45] in plain:
                continue
            if _append_para(paras, 2, ln[:95], MAX_P3) or _append_para(paras, 1, ln[:95], MAX_P2):
                plain = " ".join(paras)
                break

    discovered = packet.get("discovered_facts") or []
    for item in discovered:
        fact = (item.get("fact") or "").strip()
        if len(fact) < 20 or discovered_fact_reflected_in_plain(fact, plain):
            continue
        snippet = _truncate_discovered_snippet(fact, 110)
        if _append_para(paras, 2, snippet, MAX_P3) or _append_para(paras, 1, snippet, MAX_P2):
            plain = " ".join(paras)
            break

    body = "".join(f"<p>{p}</p>" for p in paras[:4])
    body = inject_originality_anchors(body, packet, source_body)
    paras = _paragraph_plain_blocks(body)
    if len(paras) >= 4:
        paras[3] = strip_para4_expansion_sentences(paras[3], packet)
        body = "".join(f"<p>{p}</p>" for p in paras[:4])
        body = ensure_valid_limitation_paragraph(body, packet)
        paras = _paragraph_plain_blocks(body)
        if not is_publish_v4_enabled():
            as_of = (ru.get("as_of_date") or "").strip()
            plain = " ".join(paras)
            if as_of and as_of not in plain and len(paras) >= 4:
                from engine.pipeline.rewrite_validate import validate_limitation_paragraph

                suffix = f"보도·안내 내용은 {as_of} 기준 공식 보도자료를 참고한다."
                trial = f"{paras[3].rstrip()} {suffix}".strip()
                p3 = paras[2] if len(paras) >= 3 else None
                if validate_limitation_paragraph(trial, p3)[0] and len(trial) <= MAX_P4:
                    paras[3] = trial
        body = "".join(f"<p>{p}</p>" for p in paras[:4])
    return body
