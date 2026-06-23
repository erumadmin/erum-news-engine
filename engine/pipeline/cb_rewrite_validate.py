"""CB editorial finalize + validation."""

from __future__ import annotations

import re
from typing import Any

from engine.pipeline.cb_packet_writer import build_compliance_brief, is_cb_publish_v4_enabled
from engine.pipeline.rewrite_validate import (
    IJ_REQUIRED_PARAGRAPH_COUNT,
    LIMITATION_MARKERS,
    MIN_PARAGRAPH_CHARS,
    _paragraph_plain_blocks,
    append_limitation_paragraph_if_needed,
    build_v4_limitation_from_packet,
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
    validate_limitation_paragraph,
)
from research_collector import strip_html_tags

CB_LEAD_KEYS = ("기업", "상장사", "기관", "협력사", "공급망", "실무자", "법무", "ESG", "CSR")
CB_PARA3_KEYS = ("제출", "적용", "범위", "일정", "확인", "점검", "공시", "신고", "기준", "예외")
CB_AGENCY_KEYS = ("공정거래위원회", "정부", "부처", "위원회", "당국")


def _dedupe_repeated_opening_sentence(text: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text or "") if part.strip()]
    if len(parts) >= 2:
        first = re.sub(r"\s+", " ", parts[0]).strip()
        second = re.sub(r"\s+", " ", parts[1]).strip()
        first = re.sub(r"^(기업|상장사|기관|협력사|실무자)(은|는)\s+", "", first)
        second = re.sub(r"^(기업|상장사|기관|협력사|실무자)(은|는)\s+", "", second)
        if first == second:
            parts.pop(1)
            return " ".join(parts).strip()
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    duplicated_tail = re.match(
        r"^(?P<tail>.+?다)\s+(?P<subject>(?:(?:기업|상장사|기관|협력사|실무자)(?:은|는)\s+)?)"
        r"(?P=tail)(?:\s+(?P<rest>.*))?$",
        collapsed,
    )
    if duplicated_tail:
        subject = duplicated_tail.group("subject").strip()
        lead = f"{subject} {duplicated_tail.group('tail').strip()}".strip() if subject else duplicated_tail.group("tail").strip()
        rest = (duplicated_tail.group("rest") or "").strip()
        return f"{lead}. {rest}".strip() if rest else f"{lead}."
    tail_repeat = re.match(
        r"^(?P<tail>.+?다)\s+(?P<subject>(?:기업|상장사|기관|협력사|실무자)(?:은|는))\s+(?P=tail)\.?$",
        collapsed,
    )
    if tail_repeat:
        return f"{tail_repeat.group('subject')} {tail_repeat.group('tail').strip()}."
    single_line_repeat = re.match(
        r"^(?P<a>(?:(?:기업|상장사|기관|협력사|실무자)(?:은|는)\s+)?.+?다)\s+"
        r"(?P<b>(?:(?:기업|상장사|기관|협력사|실무자)(?:은|는)\s+)?.+?다)\.?$",
        collapsed,
    )
    if single_line_repeat:
        first = re.sub(r"^(기업|상장사|기관|협력사|실무자)(은|는)\s+", "", single_line_repeat.group("a")).strip()
        second = re.sub(r"^(기업|상장사|기관|협력사|실무자)(은|는)\s+", "", single_line_repeat.group("b")).strip()
        if first == second:
            return f"{single_line_repeat.group('b').strip()}."
    return collapsed


def _strip_inline_number_marker(text: str) -> str:
    cleaned = re.sub(r"(^|\s)\d+\.\s+(?=[가-힣A-Za-z])", r"\1", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _repair_invalid_business_anchor(text: str) -> str:
    malformed = re.compile(
        r"기업은\s+[^.]{0,140}?(?:"
        + "|".join(map(re.escape, CB_AGENCY_KEYS))
        + r")[^.]{0,140}?(?:밝혔|발표했|안내했|설명했|전했)[^.]{0,100}?을 먼저 확인해야 한다\.?",
    )
    if malformed.search(text or ""):
        text = malformed.sub("기업은 관련 공지와 적용 범위를 먼저 확인해야 한다.", text)
    return re.sub(r"\s+", " ", text or "").strip()


def _ensure_cb_lead_min_length(text: str) -> str:
    if len(text or "") >= MIN_PARAGRAPH_CHARS:
        return text
    extra = "적용 범위와 고지 시점을 함께 점검해야 한다."
    if extra not in (text or ""):
        return f"{(text or '').rstrip('.')} {extra}".strip()
    return (text or "").strip()


def _polish_cb_paragraphs(paras: list[str]) -> list[str]:
    polished: list[str] = []
    for idx, para in enumerate(paras):
        text = re.sub(r"\s+", " ", (para or "")).strip()
        if idx == 0:
            text = _dedupe_repeated_opening_sentence(text)
            text = _ensure_cb_lead_min_length(text)
        text = _strip_inline_number_marker(text)
        text = _repair_invalid_business_anchor(text)
        polished.append(text)
    return polished


def validate_cb_paragraph_roles(paras: list[str]) -> tuple[bool, str]:
    if len(paras) < 4:
        return False, f"문단 수 부족({len(paras)}개)"
    for i, p in enumerate(paras[:4], start=1):
        if len(p) < MIN_PARAGRAPH_CHARS:
            return False, f"{i}문단 너무 짧음({len(p)}자)"
    if not any(k in paras[0] for k in CB_LEAD_KEYS):
        return False, "1문단 기업 실무 영향 부족"
    if not any(k in paras[2] for k in CB_PARA3_KEYS):
        return False, "3문단 확인 절차·범위 부족"
    if not (
        paras[3].startswith("다만")
        and any(k in paras[3] for k in ("예외", "유예", "한계", "미정", "예정", "범위"))
    ):
        return False, "4문단 제한·예외 부족"
    return True, "OK"


def ensure_cb_limitation_paragraph(body: str, packet: dict[str, Any]) -> str:
    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body

    p3 = (paras[2] or "").strip()
    p4 = (paras[3] or "").strip()
    ok_lim, _ = validate_limitation_paragraph(p4, p3)
    if ok_lim and len(p4) >= MIN_PARAGRAPH_CHARS:
        return body

    v4_lim = build_v4_limitation_from_packet(packet, p3)
    if v4_lim:
        paras[3] = v4_lim
        return "".join(f"<p>{p}</p>" for p in paras[:4])

    brief = packet.get("compliance_brief") or build_compliance_brief(packet)
    limits = list(brief.get("remaining_limits") or [])
    limit = str(limits[0]).rstrip(".") if limits else "세부 적용 범위와 예외는 추가 공지에 따라 달라질 수 있다"
    paras[3] = f"다만 {limit}. 예외 범위와 후속 공지 여부를 함께 확인해야 한다."
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def repair_cb_lead(paras: list[str], packet: dict[str, Any], source_text: str = "") -> list[str]:
    if not paras:
        return paras
    brief = packet.get("compliance_brief") or build_compliance_brief(packet)
    p0 = (paras[0] or "").strip()
    normalized_source = re.sub(r"\s+", " ", (source_text or "").strip())
    source_copy_like = False
    if len(normalized_source) >= 35:
        lead_window = p0[:220]
        if normalized_source[:50] in lead_window or normalized_source[:35] in lead_window:
            source_copy_like = True
    if re.match(r"^(정부|산업통상부|중기부|환경부|고용부|국토부|금융위|공정위|관계부처)", p0):
        source_copy_like = True
    if any(key in p0 for key in CB_LEAD_KEYS) and len(p0) >= MIN_PARAGRAPH_CHARS and not source_copy_like:
        return paras

    who = next((str(item).strip() for item in brief.get("who_affected") or [] if str(item).strip()), "")
    change = (brief.get("business_change") or packet.get("main_claim") or "").strip().rstrip(".")
    opener_parts = [part for part in (who, change) if part]
    if opener_parts:
        if who and change and not change.startswith(who):
            opener = f"{who}은 {change}".strip()
        else:
            opener = " ".join(opener_parts).strip()
        if not opener.endswith("."):
            opener += "."
        tail = p0
        if source_copy_like or re.match(r"^(정부|산업통상부|중기부|환경부|고용부|국토부|금융위|공정위|관계부처)", tail):
            tail = ""
        paras[0] = f"{opener} {tail}".strip() if tail else opener
    return paras


def inject_cb_confirmation_quote(paras: list[str], packet: dict[str, Any]) -> list[str]:
    if len(paras) < 3:
        return paras
    if is_cb_publish_v4_enabled():
        return paras
    from engine.pipeline.reader_utility import is_irrelevant_evidence_snippet

    plain = " ".join(paras)
    quotes = (packet.get("reader_utility") or {}).get("evidence_quotes") or []
    quotes += (packet.get("reader_utility") or {}).get("source_confirmation_quotes") or []
    for q in quotes:
        snippet = (q.get("quote") or "").strip()
        if len(snippet) < 30 or is_irrelevant_evidence_snippet(snippet):
            continue
        if snippet[:40] in plain:
            return paras
        for width in (68, 52, 40):
            use = snippet[:width].rstrip("., ") + ("…" if len(snippet) > width else "")
            suffix = f'공식 보도에 따르면, "{use}"'
            if len(paras[2]) + len(suffix) + 1 <= 920:
                paras[2] = f"{paras[2].rstrip()} {suffix}".strip()
                return paras
            if len(paras[1]) + len(suffix) + 1 <= 880:
                paras[1] = f"{paras[1].rstrip()} {suffix}".strip()
                return paras
        return paras
    return paras


def inject_cb_business_anchors(paras: list[str], packet: dict[str, Any]) -> list[str]:
    if len(paras) < 4:
        return paras
    brief = packet.get("compliance_brief") or build_compliance_brief(packet)
    para3 = (paras[2] or "").strip()
    for item in brief.get("check_items") or []:
        text = str(item).strip().rstrip(".")
        if not text:
            continue
        if text not in para3:
            paras[2] = f"{para3} 기업은 {text}을 먼저 확인해야 한다.".strip()
            para3 = paras[2]
            break
    if not any(key in paras[2] for key in CB_PARA3_KEYS):
        paras[2] = f"{paras[2].rstrip()} 적용 범위와 제출 일정을 점검해야 한다.".strip()

    para4 = (paras[3] or "").strip()
    for item in brief.get("remaining_limits") or []:
        text = str(item).strip().rstrip(".")
        if not text:
            continue
        if text not in para4:
            paras[3] = f"다만 {text}. 예외 범위와 추가 공지 여부를 계속 확인해야 한다."
            break
    if len(paras[3]) < MIN_PARAGRAPH_CHARS:
        paras[3] = (
            f"{paras[3].rstrip('.')} "
            "적용 범위와 유예 조건은 후속 고시에 따라 달라질 수 있다."
        ).strip()
    return paras


def finalize_cb_editorial_body(
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> str:
    source_text = (article or {}).get("body") or ""
    body = flatten_nested_paragraph_tags(body)
    body = normalize_temporal_in_body(body, source_text)
    body = enforce_four_paragraph_structure(body)
    body = inject_missing_source_anchors(body, source_text)
    body = append_limitation_paragraph_if_needed(body, packet)
    body = inject_reader_utility_anchors(body, packet)
    body = ensure_cb_limitation_paragraph(body, packet)
    paras = _paragraph_plain_blocks(body)
    if paras:
        paras = repair_cb_lead(paras, packet, source_text)
        paras = inject_cb_business_anchors(paras, packet)
        paras = inject_cb_confirmation_quote(paras, packet)
        paras = _polish_cb_paragraphs(paras)
        body = "".join(f"<p>{p}</p>" for p in paras[:4])
    body = sanitize_editorial_body(body, packet)
    body = pad_paragraph_min_length(body)
    body = cap_watch_phrase_repetition(body)
    if is_cb_publish_v4_enabled():
        from engine.pipeline.publish_validate import publish_sanitize_body

        body, _footer = publish_sanitize_body(body, packet, article)
        paras = _polish_cb_paragraphs(_paragraph_plain_blocks(body))
        body = "".join(f"<p>{p}</p>" for p in paras[:4])
        body = pad_paragraph_min_length(body)
        body = ensure_cb_limitation_paragraph(body, packet)
    return body


def validate_cb_editorial_rewrite(
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

    ok_roles, role_msg = validate_cb_paragraph_roles(paras)
    if not ok_roles:
        return False, role_msg

    missing = missing_fact_labels(plain, source_text)
    if missing:
        return False, "원문 핵심 누락: " + ", ".join(missing)

    if is_cb_publish_v4_enabled():
        from engine.pipeline.publish_validate import publish_sanitize_body

        body, _ = publish_sanitize_body(body, packet, article)
        plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()
        if re.search(r"https?://|www\.", plain, re.I):
            return False, "본문 URL 노출(v4)"

    return True, "OK"
