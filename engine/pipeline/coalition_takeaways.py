"""NGO·SE field takeaways: implications for coalition audience in body (Target workflow)."""

from __future__ import annotations

import re
from typing import Any

from engine.pipeline.coalition_brief import GAP_MARKERS
from engine.pipeline.rewrite_validate import (
    LIMITATION_SENTENCE_GAP_MARKERS,
    _paragraph_plain_blocks,
    caution_unsafe_for_inject,
    coalition_gap_qualifies_for_caution,
    is_policy_expansion_text,
)
from engine.pipeline.publish_validate import is_publish_v4_enabled
from research_collector import strip_html_tags

WHO_PRIORITY_MARKERS = ("해외", "유턴", "진출", "NGO")
POLICY_EXPANSION_MARKERS = ("뒷받침", "활성화", "개선해")
GENERIC_WHO_LABELS = frozenset({"기업", "소비자", "국민", "대상"})
MSME_WHO_MARKERS = ("중소벤처", "중소기업", "벤처기업")
UTURN_WHO_PATTERN = re.compile(r"유턴|해외|진출|복귀")
LEAD_LINE_MAX = 200
GENERIC_WHO_LINE_RE = re.compile(
    r"연대·보고 현장에서는\s+[^.]{2,40}\s+등\s+해당·영향\s+여부를\s+점검한다\.?"
)

WHO_MARKERS = (
    "NGO",
    "사회적 기업",
    "사회공헌",
    "파트너",
    "수혜자",
    "연대",
    "회원사",
    "협력",
    "현장",
)
ACTION_MARKERS = ("확인", "열람", "신청", "문의", "안내", "대조", "점검", "공유")
CAUTION_MARKERS = ("다만", "유의", "한계", "예정", "자율", "과장", "불확실", "모니터링")


def _topic_is_uturn(raw_source: dict[str, Any], packet: dict[str, Any]) -> bool:
    title = (raw_source.get("title") or "")
    main = (packet.get("main_claim") or "")
    return "유턴" in title or "유턴" in main


def _lead_answer_is_headline(answer: str, raw_source: dict[str, Any]) -> bool:
    answer = (answer or "").strip()
    title = (raw_source.get("title") or "").strip()
    if not answer or not title:
        return False
    a, t = answer[:80], title[:80]
    return a in t or t in a or answer == title


def _build_lead_line(
    packet: dict[str, Any],
    jb: dict[str, Any],
    raw_source: dict[str, Any] | None = None,
) -> str:
    """One-sentence lead answer from lead_question (North Star P1)."""
    raw_source = raw_source or {}
    lead_q = (jb.get("lead_question") or "").strip()
    main = (packet.get("main_claim") or "").strip()
    answer = lead_q
    if "—" in answer:
        answer = answer.split("—", 1)[0].strip()
    elif re.search(r"\s[-–]\s", answer):
        parts = re.split(r"\s[-–]\s", answer, maxsplit=1)
        if len(parts) == 2 and any(m in parts[1] for m in ("현장", "연대", "무엇")):
            answer = parts[0].strip()
    if answer.endswith("?") or "?" in answer[-30:]:
        answer = answer.rstrip("?").strip()
    if _lead_answer_is_headline(answer, raw_source) and main:
        if is_publish_v4_enabled():
            answer = f"{main[:150].rstrip('.')}."
        elif _topic_is_uturn(raw_source, packet):
            answer = (
                "해외 진출·국내 복귀(유턴)를 검토하는 NGO·연대 현장에는 "
                f"{main[:130].rstrip('.')}."
            )
        else:
            answer = f"연대·보고 관점에서 {main[:150].rstrip('.')}."
    elif len(answer) > 120 or len(answer) > LEAD_LINE_MAX:
        answer = main or answer[:LEAD_LINE_MAX]
    elif len(answer) < 28 and main:
        answer = main
    if not answer and main:
        answer = main
    return answer[:LEAD_LINE_MAX].strip()


FORWARD_LIMITATION_MARKERS = (
    "시행",
    "내년",
    "본격",
    "취소",
    "미시행",
    "아직",
    "현행",
    "소규모",
    "일반 업종",
    "추진할",
    "정비",
)


def _gap_overlaps_para3(p3: str, gap: str, *, min_chunk: int = 36) -> bool:
    p3 = (p3 or "").strip()
    gap = (gap or "").strip()
    if not p3 or not gap:
        return False
    chunk = gap[: min(min_chunk, len(gap))]
    if chunk and chunk in p3:
        return True
    tokens = [w for w in re.findall(r"[가-힣]{5,}", gap) if len(w) >= 5][:6]
    if len(tokens) >= 2:
        hits = sum(1 for t in tokens if t in p3)
        if hits >= max(2, len(tokens) - 1):
            return True
    return False


def _limitation_gap_score(gap: str, p3: str) -> tuple[int, int]:
    """Lower is better: (overlap_penalty, length)."""
    gap = (gap or "").strip()
    overlap = 1000 if _gap_overlaps_para3(p3, gap) else 0
    forward = 0 if any(m in gap for m in FORWARD_LIMITATION_MARKERS) else 50
    past_only = 10 if re.search(r"(있었|왔|하였|됐)다\.?\s*$", gap) else 0
    weak_only = 30 if "일률" in gap and "한계" in gap and not any(
        m in gap for m in FORWARD_LIMITATION_MARKERS
    ) else 0
    return (overlap + forward + past_only + weak_only, len(gap))


def _build_limitation_sentence(gaps: list[str], p3_plain: str = "") -> str:
    qualifying = [
        (g or "").strip()
        for g in gaps
        if len((g or "").strip()) >= 12
        and any(m in g for m in LIMITATION_SENTENCE_GAP_MARKERS)
        and not is_policy_expansion_text((g or "").strip())
    ]
    if not qualifying:
        return ""
    best = min(qualifying, key=lambda g: _limitation_gap_score(g, p3_plain))
    if _gap_overlaps_para3(p3_plain, best):
        alt = [g for g in qualifying if not _gap_overlaps_para3(p3_plain, g)]
        if alt:
            best = min(alt, key=lambda g: _limitation_gap_score(g, p3_plain))
    gap = best[:160].rstrip(".")
    return f"다만 {gap}." if not gap.endswith(".") else f"다만 {gap}"


def refine_limitation_sentence_for_body(
    packet: dict[str, Any],
    p3_plain: str,
) -> str:
    """Re-pick para4 limitation using body para3 to avoid duplicate past-tense gap."""
    jb = packet.get("journalist_brief") or {}
    gaps = list(jb.get("coalition_gaps") or [])
    from engine.pipeline.rewrite_validate import validate_limitation_paragraph as _val_lim

    lim = _build_limitation_sentence(gaps, p3_plain)
    if lim and _val_lim(lim, p3_plain)[0]:
        return lim
    for fact in packet.get("key_facts") or []:
        fact = (fact or "").strip()
        if len(fact) < 20:
            continue
        if not any(m in fact for m in FORWARD_LIMITATION_MARKERS):
            continue
        if is_policy_expansion_text(fact) or _gap_overlaps_para3(p3_plain, fact):
            continue
        trial = f"다만 {fact[:150].rstrip('.')}."
        if _val_lim(trial, p3_plain)[0]:
            return trial
    return (packet.get("field_takeaways") or {}).get("limitation_sentence") or ""


def _build_who_line(
    who_label: str,
    raw_source: dict[str, Any],
    packet: dict[str, Any],
) -> str:
    uturn = _topic_is_uturn(raw_source, packet)
    if uturn:
        if not who_label or who_label in GENERIC_WHO_LABELS or any(
            m in who_label for m in MSME_WHO_MARKERS
        ):
            return (
                "해외 진출·국내 복귀(유턴)을 다루는 NGO·사회적 기업·연대 현장에서는 "
                "파트너·수혜자의 영향·해당 여부를 우선 점검한다."
            )[:240]
        if UTURN_WHO_PATTERN.search(who_label):
            return (
                f"해외 진출·국내 복귀(유턴)을 다루는 NGO·사회적 기업·연대 현장에서는 "
                f"{who_label} 등 영향·해당 여부를 우선 점검한다."
            )[:240]
    if not who_label:
        return ""
    if who_label in GENERIC_WHO_LABELS and uturn:
        return ""
    if is_publish_v4_enabled():
        return f"현장에서는 {who_label} 등 해당·영향 여부를 점검한다."[:240]
    return f"연대·보고 현장에서는 {who_label} 등 해당·영향 여부를 점검한다."[:240]


def build_field_takeaways(
    raw_source: dict[str, Any],
    packet: dict[str, Any],
    discovered_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive NGO·SE 시사점 from journalist_brief + packet (no invented facts)."""
    jb = packet.get("journalist_brief") or {}
    who = list(jb.get("who_should_care") or [])
    if not who:
        who = list(packet.get("who_is_affected") or [])[:3]

    def _pick_who_label(candidates: list[str]) -> str:
        cleaned = [w.strip() for w in candidates if w and len(w.strip()) >= 3]
        if not cleaned:
            return ""
        uturn = _topic_is_uturn(raw_source, packet)
        for marker in WHO_PRIORITY_MARKERS:
            for w in cleaned:
                if marker in w:
                    return w
        generic = set(GENERIC_WHO_LABELS)
        if uturn:
            non_msme = [
                w
                for w in cleaned
                if w not in generic and not any(m in w for m in MSME_WHO_MARKERS)
            ]
            if non_msme:
                return max(non_msme, key=len)
        specific = [w for w in cleaned if w not in generic]
        pool = specific or cleaned
        return max(pool, key=len)

    who_label = _pick_who_label(who)
    tasks = list(jb.get("reader_tasks") or [])
    gaps = list(jb.get("coalition_gaps") or [])

    who_line = _build_who_line(who_label, raw_source, packet)

    action_lines: list[str] = []
    for t in tasks[:3]:
        t = (t or "").strip()
        if not t:
            continue
        if t.startswith("조사 확인:"):
            fact_part = t.replace("조사 확인:", "").strip()[:100]
            if is_publish_v4_enabled():
                action_lines.append(
                    f"공식 조사에서 확인한 내용({fact_part})을 안내에 반영할 수 있다."
                )
            else:
                action_lines.append(
                    f"연대·보고 전 공식 조사에서 확인한 내용({fact_part})을 파트너 안내에 반영할 수 있다."
                )
        elif "해당 여부" in t:
            action_lines.append(f"현장에서는 {t}")
        else:
            action_lines.append(f"실무에서는 {t[:120]}")

    if not action_lines:
        src_url = (raw_source.get("url") or raw_source.get("source_url") or "").strip()
        if src_url:
            action_lines.append(
                f"현장에서는 공식 보도자료 원문을 확인해 적용 대상·일정·문의처를 점검한다. ({src_url})"
            )
        for link in (packet.get("reader_utility") or {}).get("primary_links") or []:
            label = (link.get("label") or "공식 안내").strip()
            url = (link.get("url") or "").strip()
            if url and len(action_lines) < 2:
                action_lines.append(
                    f"현장에서는 {label} 링크를 통해 세부 고시·안내를 확인한다. ({url})"
                )

    caution_line = ""
    limitation_gaps = [
        (g or "").strip()
        for g in gaps
        if coalition_gap_qualifies_for_caution((g or "").strip())
    ]
    if limitation_gaps:
        priority = [g for g in limitation_gaps if "한계" in g or "취소" in g]
        best = min(priority or limitation_gaps, key=len)
        caution_line = f"연대·대외 안내 시 {best[:160]}"
    else:
        for gap in gaps:
            gap = (gap or "").strip()
            if len(gap) < 12 or is_policy_expansion_text(gap):
                continue
            if not any(m in gap for m in GAP_MARKERS):
                continue
            caution_line = f"연대·대외 안내 시 {gap[:160]}"
            break

    lead_line = _build_lead_line(packet, jb, raw_source)
    limitation_sentence = _build_limitation_sentence(gaps)

    return {
        "lead_implication": (jb.get("lead_question") or "").strip()[:240],
        "lead_line": lead_line,
        "limitation_sentence": limitation_sentence,
        "who_line": who_line,
        "action_lines": action_lines[:3],
        "caution_line": caution_line,
        "who_should_care": who[:5],
        "who_label": who_label,
    }


def format_field_takeaways_block(packet: dict[str, Any]) -> str:
    ft = packet.get("field_takeaways") or {}
    if not ft:
        return "(시사점 없음 — 연대 브리프 기준으로 본문에 반영)"
    lead = ft.get("lead_line") or ft.get("lead_implication", "")
    lines = [f"- 시사점(리드): {lead}"]
    if ft.get("who_line"):
        lines.append(f"- 누구(1문단): {ft['who_line']}")
    for i, a in enumerate(ft.get("action_lines") or [], start=1):
        lines.append(f"- 할 일(3문단 {i}): {a}")
    if ft.get("limitation_sentence"):
        lines.append(f"- 유의(4문단 다만): {ft['limitation_sentence']}")
    elif ft.get("caution_line"):
        lines.append(f"- 유의(4문단 다만): {ft['caution_line']}")
    return "\n".join(lines)


def _line_reflected(line: str, plain: str, *, min_chunk: int = 18) -> bool:
    line = (line or "").strip()
    if not line:
        return True
    if line[: min(min_chunk, len(line))] in plain:
        return True
    tokens = [w for w in re.findall(r"[가-힣]{4,}", line) if len(w) >= 4]
    if len(tokens) >= 2:
        hits = sum(1 for t in tokens[:5] if t in plain)
        if hits >= max(2, len(tokens[:5]) - 1):
            return True
    return False


def coalition_takeaways_reflected_in_body(
    plain: str,
    packet: dict[str, Any],
    paras: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """NGO·SE 시사점이 본문 문단에 드러났는지 (패킷 field_takeaways 기준)."""
    if paras is None:
        paras = _paragraph_plain_blocks(f"<p>{'</p><p>'.join(plain.split(chr(10)))}</p>") if "\n" in plain else []
    if not paras and plain:
        paras = [plain]
    ft = packet.get("field_takeaways") or {}
    gaps: list[str] = []

    who_ok = any(m in plain for m in WHO_MARKERS)
    if ft.get("who_line"):
        who_ok = who_ok or _line_reflected(ft["who_line"], plain)
    if not who_ok and len(paras) >= 1:
        who_ok = any(m in paras[0] for m in WHO_MARKERS)
    if not who_ok:
        gaps.append("NGO·SE 대상(누구) 시사점 부족")

    actions = ft.get("action_lines") or []
    action_ok = False
    if len(paras) >= 3:
        p3 = paras[2]
        action_ok = any(m in p3 for m in ACTION_MARKERS)
        action_ok = action_ok or any(_line_reflected(a, p3, min_chunk=14) for a in actions)
    if not action_ok:
        gaps.append("현장 행동(확인·안내) 시사점 부족")

    caution_ok = False
    if len(paras) >= 4:
        p4 = paras[3]
        caution_ok = p4.strip().startswith("다만") or any(m in p4 for m in CAUTION_MARKERS)
        if ft.get("limitation_sentence"):
            caution_ok = caution_ok or _line_reflected(ft["limitation_sentence"], p4, min_chunk=14)
        elif ft.get("caution_line"):
            caution_ok = caution_ok or _line_reflected(ft["caution_line"], p4, min_chunk=14)
    if not caution_ok:
        gaps.append("4문단 연대 유의(다만) 시사점 부족")

    return (not gaps), gaps


def _caution_reads_as_limitation(caution: str) -> bool:
    caution = (caution or "").strip()
    if not caution or caution_unsafe_for_inject(caution):
        return False
    head = caution[:40]
    if any(m in head for m in GAP_MARKERS):
        return True
    if any(m in caution for m in ("한계", "유의", "불확실", "예정", "제외", "미정", "시행 전")):
        return True
    if any(m in head for m in POLICY_EXPANSION_MARKERS):
        return False
    if any(m in caution for m in POLICY_EXPANSION_MARKERS):
        return False
    return bool(caution)


def normalize_para1_lead_order(p0: str, lead_line: str) -> str:
    """Ensure lead_line opens para1; drop duplicate headline prefix when present."""
    p0 = (p0 or "").strip()
    lead_line = (lead_line or "").strip()
    if not lead_line:
        return p0
    head = lead_line[: min(36, len(lead_line))]
    if p0.startswith(head):
        return p0
    if _line_reflected(lead_line, p0[: min(220, len(p0))]):
        m = re.search(r"(?:^|\s)(?:\d+\.\s*)?산업통상", p0)
        if m and m.start() > 20:
            return f"{lead_line} {p0[m.start():].lstrip()}".strip()
    return f"{lead_line} {p0}".strip()


def sanitize_para1_coalition(
    p0: str,
    lead_line: str,
    raw_source: dict[str, Any] | None = None,
) -> str:
    """Remove headline duplicate, numbered debris, and policy-expansion opener tails."""
    p0 = (p0 or "").strip()
    raw_source = raw_source or {}
    title = (raw_source.get("title") or "").strip()
    if title and p0.startswith(title[: min(50, len(title))]):
        p0 = p0[len(title) :].lstrip(" .")
    p0 = re.sub(r"^\d+\.\s*", "", p0)
    kept: list[str] = []
    seen_heads: set[str] = set()
    for sent in re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", p0):
        s = sent.strip()
        if not s:
            continue
        if s.startswith("이를 위해"):
            continue
        if title and len(title) >= 20 and s[:40] in title:
            continue
        head = s[:50]
        if head in seen_heads:
            continue
        seen_heads.add(head)
        kept.append(s)
    p0 = " ".join(kept).strip()
    if lead_line:
        p0 = normalize_para1_lead_order(p0, lead_line)
    return p0


def _para4_needs_limitation_inject(p4: str, fill: str) -> bool:
    p4 = (p4 or "").strip()
    fill = (fill or "").strip()
    if not fill:
        return False
    snippet = fill[: min(80, len(fill))]
    if snippet and snippet in p4:
        return False
    if _line_reflected(fill, p4, min_chunk=24):
        return False
    return True


def inject_coalition_field_takeaways(body: str, packet: dict[str, Any]) -> str:
    """Append missing NGO·SE takeaway lines (excerpt-only, no new facts)."""
    ft = packet.get("field_takeaways") or {}
    if not ft:
        return body
    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body

    lead_line = (ft.get("lead_line") or "").strip()
    raw = packet.get("_raw_source") or {}
    if lead_line:
        paras[0] = sanitize_para1_coalition(paras[0], lead_line, raw)

    who_line = (ft.get("who_line") or "").strip()
    who_label = (ft.get("who_label") or "").strip()
    if who_line:
        paras[0] = GENERIC_WHO_LINE_RE.sub("", paras[0]).strip()
        has_who_markers = any(m in paras[0] for m in WHO_MARKERS)
        has_label = bool(who_label and who_label in paras[0])
        if not (has_who_markers and has_label) and not _line_reflected(who_line, paras[0]):
            if len(paras[0]) < 380:
                paras[0] = f"{paras[0].rstrip()} {who_line}".strip()

    actions = sorted(
        (a or "").strip() for a in (ft.get("action_lines") or []) if (a or "").strip()
    )
    for action in actions:
        if _line_reflected(action, paras[2]):
            continue
        if len(paras[2]) > 750 and len(action) > 80:
            continue
        if len(paras[2]) + len(action) + 1 < 900:
            paras[2] = f"{paras[2].rstrip()} {action}".strip()
        break

    if len(paras) >= 3 and not any(m in paras[2] for m in ACTION_MARKERS):
        fallback = "현장에서는 공식 보도·안내 문서에서 적용 대상과 시행 시점을 확인한다."
        if len(paras[2]) + len(fallback) + 1 < 920:
            paras[2] = f"{paras[2].rstrip()} {fallback}".strip()

    if len(paras) >= 3:
        refined = refine_limitation_sentence_for_body(packet, paras[2])
        if refined:
            ft = dict(ft)
            ft["limitation_sentence"] = refined
            packet["field_takeaways"] = ft

    limitation = (ft.get("limitation_sentence") or "").strip()
    caution = (ft.get("caution_line") or "").strip()
    if len(paras) >= 4:
        p4 = paras[3]
        if limitation and _gap_overlaps_para3(paras[2], limitation):
            limitation = refine_limitation_sentence_for_body(packet, paras[2])
        if (
            limitation
            and not caution_unsafe_for_inject(limitation)
            and _para4_needs_limitation_inject(p4, limitation)
        ):
            paras[3] = limitation[:480]
        elif (
            caution
            and not caution_unsafe_for_inject(caution)
            and _caution_reads_as_limitation(caution)
            and _para4_needs_limitation_inject(p4, caution)
        ):
            if not p4.startswith("다만"):
                paras[3] = f"다만 {caution}".strip()[:480]
            elif len(p4) < 320 and len(p4) + len(caution) + 2 < 480:
                paras[3] = f"{p4.rstrip()} {caution}".strip()[:480]

    return "".join(f"<p>{p}</p>" for p in paras[:4])
