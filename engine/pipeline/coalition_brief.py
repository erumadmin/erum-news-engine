"""Coalition / field briefing metadata for NGO·SE primary audience (Target engine)."""

from __future__ import annotations

import re
from typing import Any

from research_collector import strip_html_tags

GAP_MARKERS = (
    "다만",
    "유의",
    "한계",
    "예정",
    "불확실",
    "시행 전",
    "제외",
    "미정",
    "아닌",
    "미포함",
    "자율",
    "의무",
    "검토",
    "별도",
)

_GAP_MARKERS = GAP_MARKERS


def _plain(raw_source: dict[str, Any]) -> str:
    return strip_html_tags(raw_source.get("body") or "")


def build_source_facts(raw_source: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, str]]:
    url = (raw_source.get("url") or raw_source.get("source_url") or "").strip()
    out: list[dict[str, str]] = []
    for fact in (packet.get("key_facts") or [])[:6]:
        out.append({"fact": str(fact)[:220], "source": "lead_article", "url": url})
    return out


def build_journalist_brief(
    raw_source: dict[str, Any],
    packet: dict[str, Any],
    discovered_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    title = (raw_source.get("title") or "").strip()
    who = packet.get("who_is_affected") or []
    if not who:
        who = ["협력 NGO·사회적 기업 파트너", "정책·지원 대상 수혜자"]
    tasks: list[str] = []
    if packet.get("who_is_affected"):
        tasks.append("파트너·수혜자 해당 여부 확인")
    for link in (packet.get("action_items") or [])[:2]:
        tasks.append(f"공식 안내 확인: {link}")
    for d in discovered_facts[:2]:
        tasks.append(f"조사 확인: {d.get('fact', '')[:80]}")
    if not tasks:
        tasks.append("보도자료 원문·부처 공식 페이지 대조")

    lead_q = "우리 파트너·수혜자에게 이번 제도·조치가 무엇을 바꾸나?"
    if title:
        lead_q = f"{title[:40]} — 현장·연대 관점에서 무엇이 바뀌나?"

    gaps = _extract_coalition_gaps(_plain(raw_source), discovered_facts)

    return {
        "lead_question": lead_q,
        "why_now": (packet.get("why_now") or packet.get("effective_date") or "").strip()[:240],
        "who_should_care": who[:5],
        "reader_tasks": tasks[:5],
        "coalition_gaps": gaps[:4],
    }


def _line_qualifies_as_coalition_gap(ln: str) -> bool:
    """Skip policy-expansion lines that only matched weak markers like '예정'."""
    ln = (ln or "").strip()
    if len(ln) < 15:
        return False
    if not any(m in ln for m in _GAP_MARKERS):
        return False
    expansion_tail = ("뒷받침", "활성화", "개선해", "이를 통해")
    strong = ("한계", "취소", "시행 전", "미시행", "제외", "미정", "아직", "별도")
    forward = ("내년", "본격", "추진할 계획", "도입되어", "현행", "소규모")
    if any(x in ln for x in expansion_tail) and not any(m in ln for m in strong):
        return False
    if "예정" in ln and not any(m in ln for m in strong + forward):
        return False
    return True


def _extract_coalition_gaps(source_plain: str, discovered: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for ln in source_plain.splitlines():
        ln = ln.strip()
        if not _line_qualifies_as_coalition_gap(ln):
            continue
        gaps.append(ln[:200])
        if len(gaps) >= 4:
            break
    for d in discovered:
        fact = (d.get("fact") or "").strip()
        if any(m in fact for m in _GAP_MARKERS) and fact not in gaps:
            gaps.append(fact[:200])
    return gaps


def assess_briefing_ready(
    packet: dict[str, Any],
    discovered_facts: list[dict[str, Any]],
    *,
    body_plain: str = "",
    paras: list[str] | None = None,
) -> dict[str, Any]:
    """Five-condition coalition briefing check (packet-time + optional post-rewrite body)."""
    fail: list[str] = []
    who = packet.get("who_is_affected") or []
    kf = packet.get("key_facts") or []
    eligibility_clear = bool(who) or any(
        k in " ".join(kf)
        for k in (
            "대상",
            "적용",
            "일반용",
            "산업용",
            "교육용",
            "소비자",
            "위생",
            "품목",
            "갯벌",
            "해양",
            "관리구역",
            "민간",
            "주민",
            "지역",
            "과제",
            "부처",
        )
    )
    if not eligibility_clear:
        fail.append("eligibility_unclear")

    urls = list(packet.get("action_items") or [])
    ru = packet.get("reader_utility") or {}
    for link in ru.get("primary_links") or []:
        u = link.get("url") if isinstance(link, dict) else link
        if u:
            urls.append(str(u))
    field_action_urls = any("http" in str(u) for u in urls)
    if not field_action_urls:
        fail.append("field_action_urls_missing")

    import os

    cfg_min = int(os.environ.get("RESEARCH_MIN_DISCOVERED_FACTS", "1"))
    discovered_min = len(discovered_facts) >= cfg_min
    raw_body = ((packet.get("_raw_source") or {}).get("body") or "").strip()
    if not discovered_min and os.environ.get("REVIEW_ONLY", "0") == "1" and len(raw_body) >= 350:
        discovered_min = True
    if not discovered_min:
        fail.append("discovered_below_min")

    limits_paragraph = True
    if body_plain:
        if paras is None:
            paras = [p.strip() for p in re.split(r"\n+", body_plain) if p.strip()]
        last = paras[-1] if paras else body_plain
        limits_paragraph = last.startswith("다만") or any(m in last for m in _GAP_MARKERS)
        if not limits_paragraph:
            fail.append("limits_paragraph_weak")

    jb = packet.get("journalist_brief") or {}
    coalition_framing = bool((jb.get("lead_question") or "").strip()) and bool(
        jb.get("reader_tasks")
    )
    if not coalition_framing:
        fail.append("coalition_framing_weak")

    coalition_takeaways_in_body = True
    if body_plain:
        from engine.pipeline.coalition_takeaways import coalition_takeaways_reflected_in_body

        coalition_takeaways_in_body, _tg = coalition_takeaways_reflected_in_body(
            body_plain, packet, paras=paras
        )
        if not coalition_takeaways_in_body:
            fail.append("coalition_takeaways_weak")

    checks = {
        "eligibility_clear": eligibility_clear,
        "field_action_urls": field_action_urls,
        "discovered_min": discovered_min,
        "limits_paragraph": limits_paragraph,
        "coalition_framing": coalition_framing,
        "coalition_takeaways_in_body": coalition_takeaways_in_body,
    }
    ready = len(fail) == 0 if not body_plain else all(checks.values())
    if body_plain and fail:
        ready = False
    return {
        "briefing_ready": ready,
        "checks": checks,
        "fail_reasons": fail,
    }
