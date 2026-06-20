"""Community brief for Neighbor News — who / change / conditions / what to do."""

from __future__ import annotations

import re
from typing import Any

from engine.pipeline.reader_utility import extract_checklist, extract_scenarios

INSTITUTION_LEAD_MARKERS = (
    "정부가",
    "정부는",
    "관계부처",
    "당국은",
    "당국이",
    "기관은",
    "부처는",
    "위원회는",
    "협회는",
    "인사혁신처",
    "인사처",
    "발표했다",
    "밝혔다",
    "공개했다",
)

NN_FORBIDDEN_PHRASES = (
    "도모",
    "제고",
    "기여",
    "활성화",
    "혁신적",
    "선도적",
    "부상",
    "공고히",
)

NN_PHRASE_ALLOWLIST = (
    "적극행정위원회",
    "적극행정",
    "활력 제고",
    "역량 제고",
)


def _scrub_allowlisted_phrases(plain: str) -> str:
    scrubbed = plain
    for term in NN_PHRASE_ALLOWLIST:
        scrubbed = scrubbed.replace(term, " ")
    return scrubbed


def build_community_brief(packet: dict[str, Any]) -> dict[str, Any]:
    """Extract NN editorial axes from research packet (source-bound only)."""
    raw = packet.get("_raw_source") or {}
    body = (raw.get("body") or raw.get("source_body") or "").strip()

    who = list(packet.get("who_is_affected") or [])
    if not who:
        jb = packet.get("journalist_brief") or {}
        who = list(jb.get("who_should_care") or [])

    if not who and body:
        for marker in (
            "9급",
            "6급",
            "7~9급",
            "저연차",
            "현장 공무원",
            "재난·안전",
            "경찰·소방",
            "청년",
            "소상공인",
        ):
            if marker in body and marker not in who:
                who.append(marker)

    life_change = (packet.get("main_claim") or "").strip()
    if not life_change:
        facts = packet.get("key_facts") or []
        life_change = facts[0] if facts else ""

    conditions = list(packet.get("conditions") or []) + list(packet.get("exceptions") or [])
    ru = packet.get("reader_utility") or {}
    checklist = list(ru.get("checklist") or [])
    if len(checklist) < 2 and body:
        checklist = [{"step": c.get("step", "")} for c in extract_checklist(body)]

    what_to_do: list[str] = []
    for item in packet.get("action_items") or []:
        text = str(item).strip()
        if text:
            what_to_do.append(text[:240])
    for step in checklist[:4]:
        s = (step.get("step") if isinstance(step, dict) else str(step)).strip()
        if s and s not in what_to_do:
            what_to_do.append(s[:240])

    scenarios = list(ru.get("scenarios") or [])
    if len(scenarios) < 1 and body:
        scenarios = extract_scenarios(body)

    return {
        "who_affected": who[:6],
        "life_change": life_change[:400],
        "conditions": conditions[:6],
        "what_to_do": what_to_do[:6],
        "scenarios": scenarios[:3],
        "checklist": checklist[:4],
        "effective_date": (packet.get("effective_date") or "").strip(),
        "why_now": (packet.get("why_now") or "").strip(),
    }


def format_community_brief_block(packet: dict[str, Any]) -> str:
    brief = packet.get("community_brief") or build_community_brief(packet)
    lines = ["[이웃뉴스 — 독자 4축 (패킷·원문만)]"]
    if brief.get("who_affected"):
        lines.append("누구 해당:")
        for w in brief["who_affected"]:
            lines.append(f"- {w}")
    if brief.get("life_change"):
        lines.append(f"무엇이 바뀌는가: {brief['life_change']}")
    if brief.get("conditions"):
        lines.append("조건·예외·시점:")
        for c in brief["conditions"]:
            lines.append(f"- {c}")
    if brief.get("what_to_do"):
        lines.append("독자가 확인·신청·이용할 것:")
        for w in brief["what_to_do"]:
            lines.append(f"- {w}")
    if brief.get("scenarios"):
        lines.append("원문 시나리오 (있을 때만):")
        for s in brief["scenarios"]:
            label = s.get("label", "") if isinstance(s, dict) else str(s)
            body = s.get("body", "") if isinstance(s, dict) else ""
            lines.append(f"- {label}: {body[:180]}")
    lines.append(
        "위 내용만 사용. 없는 일상 비유·가계 부담·체감 사례를 만들지 않는다."
    )
    return "\n".join(lines)


def _axis_reflected(text: str, plain: str) -> bool:
    text = (text or "").strip()
    if len(text) < 8:
        return False
    if text[:30] in plain:
        return True
    tokens = [w for w in re.findall(r"[\w가-힣]+", text) if len(w) >= 2]
    return sum(1 for t in tokens[:6] if t in plain) >= 2


def score_community_axes(packet: dict[str, Any], plain: str) -> tuple[float, list[str]]:
    """0–10: how many of 4 axes (who, change, conditions, action) appear in body."""
    brief = packet.get("community_brief") or build_community_brief(packet)
    gaps: list[str] = []
    hits = 0

    who_list = brief.get("who_affected") or []
    if who_list and any(_axis_reflected(w, plain) for w in who_list):
        hits += 1
    elif who_list:
        gaps.append("누구 해당 미반영")

    if brief.get("life_change") and _axis_reflected(brief["life_change"], plain):
        hits += 1
    else:
        gaps.append("변화 요약 미반영")

    cond = brief.get("conditions") or []
    checklist = brief.get("checklist") or []
    cond_texts = [str(c) for c in cond] + [
        (c.get("step") or "") if isinstance(c, dict) else str(c) for c in checklist
    ]
    if cond_texts and any(_axis_reflected(c, plain) for c in cond_texts if c):
        hits += 1
    elif cond_texts:
        gaps.append("조건·절차 미반영")

    actions = brief.get("what_to_do") or []
    if actions and any(_axis_reflected(a, plain) for a in actions):
        hits += 1
    elif actions:
        gaps.append("할 일·이용 정보 미반영")

    # Need 3 of 4 axes when data exists; if minimal packet, relax
    available = sum(
        1
        for block in (who_list, [brief.get("life_change")], cond_texts, actions)
        if block and any(str(x).strip() for x in block)
    )
    need = min(3, max(2, available))

    score = 10.0 if hits >= need else max(0.0, 10.0 * hits / max(need, 1))
    if hits < need:
        gaps.append(f"생활 4축 {hits}/{need}")
    return score, gaps


def validate_nn_lead(paras: list[str]) -> tuple[bool, str]:
    if not paras:
        return False, "1문단 없음"
    lead = paras[0].strip()
    if len(lead) < 20:
        return False, "1문단 너무 짧음"
    for marker in INSTITUTION_LEAD_MARKERS:
        if lead.startswith(marker):
            return False, f"기관명 리드 ({marker})"
    return True, "OK"


def validate_nn_forbidden_phrases(plain: str) -> tuple[bool, str]:
    scrubbed = _scrub_allowlisted_phrases(plain)
    found = [p for p in NN_FORBIDDEN_PHRASES if p in scrubbed]
    if "적극" in scrubbed:
        found.append("적극")
    if found:
        return False, f"금지 수사: {', '.join(list(dict.fromkeys(found))[:3])}"
    return True, "OK"
