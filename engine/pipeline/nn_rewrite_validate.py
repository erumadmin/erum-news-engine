"""NN editorial finalize + validation."""

from __future__ import annotations

import re
from typing import Any

from engine.pipeline.nn_community_brief import (
    INSTITUTION_LEAD_MARKERS,
    build_community_brief,
    score_community_axes,
    validate_nn_forbidden_phrases,
    validate_nn_lead,
)
from engine.pipeline.nn_packet_writer import is_nn_publish_v4_enabled
from engine.pipeline.reader_utility import score_reader_value_dimension
from engine.pipeline.rewrite_validate import (
    IJ_REQUIRED_PARAGRAPH_COUNT,
    LIMITATION_MARKERS,
    MIN_PARAGRAPH_CHARS,
    _paragraph_plain_blocks,
    append_limitation_paragraph_if_needed,
    cap_watch_phrase_repetition,
    enforce_four_paragraph_structure,
    flatten_nested_paragraph_tags,
    inject_missing_source_anchors,
    inject_reader_utility_anchors,
    missing_fact_labels,
    normalize_temporal_in_body,
    pad_paragraph_min_length,
    sanitize_editorial_body,
    temporal_hint_from_source,
)
from research_collector import strip_html_tags

NN_PARA2_KEYS = ("배경", "문제", "이유", "때문", "기존", "지금까지", "그동안", "한편")
NN_PARA3_KEYS = (
    "신청",
    "이용",
    "조건",
    "대상",
    "시행",
    "절차",
    "제외",
    "확대",
    "인상",
    "할인",
    "지원",
    "운영",
    "부터",
    "까지",
    "월",
    "년",
)
NN_FORBIDDEN_REPLACEMENTS = {
    "적극행정": "__NN_ALLOWLIST_ACTIVE_ADMIN__",
    "도모": "추진",
    "제고": "높이기",
    "기여": "도움",
    "적극": "우선",
    "활성화": "확대",
    "혁신적": "새로운",
    "선도적": "앞선",
    "부상": "주목",
    "공고히": "탄탄히",
}


def _strip_institution_opener(text: str) -> str:
    t = (text or "").strip()
    for marker in INSTITUTION_LEAD_MARKERS:
        if t.startswith(marker):
            t = t[len(marker) :].strip()
            break
    return t


def normalize_nn_forbidden_phrases(body: str) -> str:
    out = body or ""
    for src, dst in NN_FORBIDDEN_REPLACEMENTS.items():
        out = re.sub(src, dst, out)
    out = out.replace("__NN_ALLOWLIST_ACTIVE_ADMIN__", "적극행정")
    return out


def fix_nn_para1_lead_opener(
    paras: list[str],
    packet: dict[str, Any],
    source_body: str,
) -> list[str]:
    """Reader-first lead; strip institution opener / source copy."""
    if not paras:
        return paras
    brief = packet.get("community_brief") or build_community_brief(
        {**packet, "_raw_source": {"body": source_body}}
    )
    p0 = (paras[0] or "").strip()
    src = re.sub(r"\s+", " ", (source_body or "").strip())
    institution_lead = any(p0.startswith(m) for m in INSTITUTION_LEAD_MARKERS)
    copies_source = len(src) >= 40 and (src[:50] in p0 or src[:35] in p0[:220])
    ok_lead, _ = validate_nn_lead([p0])
    if ok_lead and not copies_source:
        return paras

    who = brief.get("who_affected") or []
    who_label = who[0] if who else ""
    if not who_label:
        for marker in ("6급 공무원", "9급", "저연차·현장 공무원", "저연차", "현장 공무원", "공무원"):
            if marker in (source_body or ""):
                who_label = marker
                break

    change = (brief.get("life_change") or packet.get("main_claim") or "").strip()
    change = re.sub(r"^(인사혁신처|인사처|정부|관계부처)(는|가)\s*", "", change).strip()
    if who_label and change:
        opener = f"{who_label}에게 {change[:100].rstrip('.')}."
    elif change:
        opener = change[:120].rstrip(".") + "."
    else:
        opener = ""

    trimmed = _strip_institution_opener(p0)
    if src[:50] in trimmed:
        trimmed = trimmed.replace(src[: min(80, len(src))], "", 1).strip(" .,")
    if opener:
        paras[0] = f"{opener} {trimmed}".strip() if trimmed else opener
    else:
        paras[0] = trimmed

    ok_lead, _ = validate_nn_lead([paras[0]])
    if not ok_lead and opener:
        paras[0] = opener
    if len((paras[0] or "").strip()) < MIN_PARAGRAPH_CHARS:
        supplements = list(brief.get("conditions") or []) + list(packet.get("key_facts") or [])
        for item in supplements:
            text = str(item).strip().rstrip(".")
            if not text or text[:30] in paras[0]:
                continue
            candidate = f"{paras[0].rstrip()} {text}."
            paras[0] = candidate
            if len(paras[0]) >= MIN_PARAGRAPH_CHARS:
                break
    return paras


def inject_nn_v4_originality_anchors(
    body: str,
    packet: dict[str, Any],
    source_body: str,
) -> str:
    from engine.pipeline.editorial_originality import comparison_cues_for_source
    from engine.pipeline.reader_utility import _checklist_reflected, _scenario_reflected

    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body
    plain = " ".join(paras)
    ru = packet.get("reader_utility") or {}

    scenarios = ru.get("scenarios") or []
    if scenarios and not any(_scenario_reflected(s, plain) for s in scenarios):
        snippet = (scenarios[0].get("body") if isinstance(scenarios[0], dict) else str(scenarios[0]))[
            :90
        ].strip()
        if snippet and len(paras[1]) + len(snippet) < 900:
            paras[1] = f"{paras[1].rstrip()} {snippet}".strip()
            plain = " ".join(paras)

    checklist = ru.get("checklist") or []
    for step in checklist[:3]:
        text = (step.get("step") if isinstance(step, dict) else str(step))[:100].strip()
        if text and not _checklist_reflected(step if isinstance(step, dict) else {"step": text}, plain):
            if len(paras[2]) + len(text) < 900:
                paras[2] = f"{paras[2].rstrip()} {text[:90]}".strip()
                plain = " ".join(paras)
                break

    cues = comparison_cues_for_source(source_body)
    if cues and not any(c in plain for c in cues):
        for ln in (source_body or "").splitlines():
            ln = ln.strip()
            if len(ln) < 20 or not any(c in ln for c in cues):
                continue
            if ln[:50] in plain:
                continue
            if len(paras[2]) + len(ln) < 920:
                paras[2] = f"{paras[2].rstrip()} {ln[:100]}".strip()
                break

    return "".join(f"<p>{p}</p>" for p in paras[:4])


def ensure_nn_limitation_paragraph(body: str, packet: dict[str, Any]) -> str:
    from engine.pipeline.rewrite_validate import validate_limitation_paragraph

    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body
    ok, _ = validate_limitation_paragraph(paras[3], paras[2])
    if ok:
        return body

    brief = packet.get("community_brief") or build_community_brief(packet)
    candidates: list[str] = []
    for c in (brief.get("conditions") or packet.get("conditions") or packet.get("exceptions") or []):
        text = str(c).strip()
        if text and any(k in text for k in ("아직", "예정", "목표", "단계", "제외", "한정", "추후", "달라")):
            candidates.append(text[:120].rstrip("."))
    if "official_evidence_missing" in (packet.get("risk_flags") or []):
        candidates.append("세부 시행 일정은 추가 공지에 따른다")

    for trial_core in candidates:
        trial = f"다만 {trial_core}."
        if validate_limitation_paragraph(trial, paras[2])[0]:
            paras[3] = trial
            return "".join(f"<p>{p}</p>" for p in paras[:4])

    paras[3] = (
        "다만 세부 적용 범위와 시행 일정, 예외 조건은 추가 공지에 따라 달라질 수 있다."
    )
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def validate_nn_paragraph_roles(paras: list[str]) -> tuple[bool, str]:
    if len(paras) < 4:
        return False, f"문단 수 부족({len(paras)}개)"
    for i, p in enumerate(paras[:4], start=1):
        if len(p) < MIN_PARAGRAPH_CHARS:
            return False, f"{i}문단 너무 짧음({len(p)}자)"
    if not any(k in paras[1] for k in NN_PARA2_KEYS):
        return False, "2문단 배경·이유 부족"
    if not any(k in paras[2] for k in NN_PARA3_KEYS):
        return False, "3문단 조건·이용·절차 부족"
    if not (
        paras[3].startswith("다만")
        or any(m in paras[3] for m in LIMITATION_MARKERS)
        or any(k in paras[3] for k in ("제한", "예외", "유예", "아직", "남"))
    ):
        return False, "4문단 한계·생활 영향 부족"
    return True, "OK"


def finalize_nn_editorial_body(
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> str:
    source_text = (article or {}).get("body") or ""
    body = flatten_nested_paragraph_tags(body)
    body = normalize_nn_forbidden_phrases(body)
    body = normalize_temporal_in_body(body, source_text)
    body = enforce_four_paragraph_structure(body)
    body = inject_missing_source_anchors(body, source_text)
    body = append_limitation_paragraph_if_needed(body, packet)
    body = inject_reader_utility_anchors(body, packet)
    if is_nn_publish_v4_enabled():
        body = inject_nn_v4_originality_anchors(body, packet, source_text)
    else:
        from engine.pipeline.editorial_originality import inject_originality_anchors

        body = inject_originality_anchors(body, packet, source_text)
    body = ensure_nn_limitation_paragraph(body, packet)
    paras = _paragraph_plain_blocks(body)
    if paras:
        paras = fix_nn_para1_lead_opener(paras, packet, source_text)
        body = "".join(f"<p>{p}</p>" for p in paras[:4])
    body = sanitize_editorial_body(body, packet)
    body = pad_paragraph_min_length(body)
    body = cap_watch_phrase_repetition(body)
    if is_nn_publish_v4_enabled():
        from engine.pipeline.publish_validate import publish_sanitize_body

        body, _footer = publish_sanitize_body(body, packet, article)
        body = ensure_nn_limitation_paragraph(body, packet)
    return body


def validate_nn_editorial_rewrite(
    title: str,
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if not body or not body.strip():
        return False, "본문 누락"
    if not title or len(title.strip()) < 5:
        return False, "제목 누락 또는 너무 짧음"

    body = flatten_nested_paragraph_tags(body)
    source_text = (article or {}).get("body") or ""
    body = normalize_temporal_in_body(body, source_text)
    plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()
    paras = _paragraph_plain_blocks(body)

    if len(paras) < IJ_REQUIRED_PARAGRAPH_COUNT:
        return False, f"문단 수 부족({len(paras)}개, 4문단 필요)"

    hint = temporal_hint_from_source(source_text) or temporal_hint_from_source(plain)
    if hint.startswith("다음 달") and re.search(r"이달부터|이번 달부터", plain):
        return False, "시점 표기 불일치(이달/다음 달 혼용)"

    ok_lead, lead_msg = validate_nn_lead(paras)
    if not ok_lead:
        return False, lead_msg

    ok_phrase, phrase_msg = validate_nn_forbidden_phrases(plain)
    if not ok_phrase:
        return False, phrase_msg

    ok_roles, role_msg = validate_nn_paragraph_roles(paras)
    if not ok_roles:
        return False, role_msg

    missing = missing_fact_labels(plain, source_text)
    if missing:
        return False, "원문 핵심 누락: " + ", ".join(missing)

    axes_score, axes_gaps = score_community_axes(packet, plain)
    if axes_score < 7.0 and axes_gaps:
        return False, "community_axes: " + ", ".join(axes_gaps)

    if is_nn_publish_v4_enabled():
        from engine.pipeline.publish_validate import publish_sanitize_body

        body, _ = publish_sanitize_body(body, packet, article)
        paras = _paragraph_plain_blocks(body)
        plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()
        if re.search(r"https?://|www\.", plain, re.I):
            return False, "본문 URL 노출(v4)"

    return True, "OK"


def build_nn_rewrite_correction_suffix(error_message: str) -> str:
    return (
        f"\n\n[수정 요청 — 이웃뉴스] {error_message}\n"
        "반드시 수정: (1) <p> 4개 "
        "(2) 1문단 = 영향받는 사람·이용자 주어 "
        "(3) 3문단 = 조건·이용·시행 "
        "(4) 4문단 = 「다만」+ 한계 "
        "(5) 본문 URL·행정 홍보 수사 금지."
    )
