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
    ensure_danman_prefix,
    enforce_four_paragraph_structure,
    flatten_nested_paragraph_tags,
    inject_missing_source_anchors,
    inject_reader_utility_anchors,
    missing_fact_labels,
    normalize_danman_opener,
    normalize_temporal_in_body,
    pad_paragraph_min_length,
    sanitize_editorial_body,
    temporal_hint_from_source,
    validate_limitation_paragraph,
)
from research_collector import strip_html_tags

CB_LEAD_KEYS = (
    "기업",
    "상장사",
    "기관",
    "협력사",
    "공급망",
    "실무자",
    "법무",
    "ESG",
    "CSR",
    "사업주",
    "사업자",
    "물류",
    "공장",
)
CB_PARA3_KEYS = ("제출", "적용", "범위", "일정", "확인", "점검", "공시", "신고", "기준", "예외", "유예", "과태료", "고시")
CB_AGENCY_KEYS = ("공정거래위원회", "정부", "부처", "위원회", "당국", "국토교통부", "국토부")
CB_REGULATORY_MARKERS = (
    "과태료",
    "의무",
    "규제",
    "고시",
    "시행",
    "공시",
    "신고",
    "시정",
    "제재",
    "벌칙",
    "소방",
    "스프링클러",
)
# Align with publish_validate CB agency gate (+ 위원회·등 N개 부처)
CB_AGENCY_LEAD_RE = re.compile(
    r"^(?:정부|국토교통부|국토부|산업통상부|산업통상자원부|중기부|환경부|고용부|"
    r"금융위|금융위원회|공정위|공정거래위원회|관계부처|보건복지부|복지부|"
    r"재정경제부|기획재정부)"
    r"(?:\s*등\s*[0-9]+\s*개\s*부처)?"
    r"(는|가|이|은)\s*"
)
CB_AGENCY_LEAD_LOOSE_RE = re.compile(
    r"^[가-힣A-Za-z]{2,16}(?:위원회|부|처|청)\s*등.{0,20}부처(는|가|이|은)\s*"
)


def is_cb_agency_lead(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(CB_AGENCY_LEAD_RE.match(t) or CB_AGENCY_LEAD_LOOSE_RE.match(t))


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
    # inject_cb_business_anchors bug: full clause + 「을 먼저 확인」
    text = re.sub(
        r"기업은\s+(.{20,220}?다)\s*을 먼저 확인해야 한다\.?",
        r"\1",
        text or "",
    )
    text = re.sub(r"(있다|된다|한다|된다)\s*을\b", r"\1", text)
    text = text.replace("협력사은", "협력사는").replace("사업주은", "사업주는")
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
    seen_chunks: list[str] = []
    for idx, para in enumerate(paras):
        text = re.sub(r"\s+", " ", (para or "")).strip()
        if idx == 0:
            text = _dedupe_repeated_opening_sentence(text)
            text = _ensure_cb_lead_min_length(text)
        text = _strip_inline_number_marker(text)
        text = _repair_invalid_business_anchor(text)
        # Drop near-duplicate paragraph bodies (40+ char overlap)
        norm = re.sub(r"\s+", "", text)
        if len(norm) >= 40 and any(norm[:50] in prev or prev[:50] in norm for prev in seen_chunks):
            if idx == 3:
                text = "다만 세부 기준·유예 범위는 하위 고시와 후속 안내에 따라 달라질 수 있다. 예외 적용 여부를 계속 확인해야 한다."
            elif idx == 2:
                text = "적용 범위·시행 일정·과태료·조달·계약 반영 여부를 점검해야 한다. 규모 미만 사업장 유예도 함께 본다."
            elif idx == 0:
                text = _ensure_cb_lead_min_length(
                    "관련 기업은 바뀌는 의무·기준을 확인하고 적용 일정을 점검해야 한다."
                )
            else:
                text = (
                    "규제 환경이 바뀌며 의무·비용·일정을 다시 봐야 한다. "
                    "기업은 적용 범위와 시행 시점을 우선 확인한다."
                )
        seen_chunks.append(norm)
        polished.append(text)
    while len(polished) < 4:
        polished.append(
            "다만 세부 기준과 유예 범위는 하위 고시에 따라 달라질 수 있다. 예외 여부를 확인해야 한다."
        )
    return polished[:4]


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
    limit = "세부 적용 범위와 유예는 하위 고시·후속 안내에 따라 달라질 수 있다"
    for item in limits:
        text = str(item).strip().rstrip(".")
        if text and len(text) <= 70 and any(k in text for k in ("유예", "고시", "미만", "예외")):
            limit = text
            break
    paras[3] = f"다만 {limit}. 예외 범위와 후속 공지 여부를 함께 확인해야 한다."
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def repair_cb_lead(paras: list[str], packet: dict[str, Any], source_text: str = "") -> list[str]:
    if not paras:
        return paras
    brief = packet.get("compliance_brief") or build_compliance_brief(packet)
    p0 = (paras[0] or "").strip()
    agency = is_cb_agency_lead(p0)
    who = next((str(item).strip() for item in brief.get("who_affected") or [] if str(item).strip()), "")
    src = source_text or ""
    if not who:
        if "사업주" in src or "물류" in src:
            who = "대형 물류창고·공장 사업주"
        elif "기업" in src:
            who = "관련 기업"
    from engine.pipeline.topic_particles import with_topic_particle

    who_topic = with_topic_particle(who) if who else ""
    if who and ("소방" in src or "스프링클러" in src):
        opener = (
            f"{who_topic} 스프링클러·경보설비 등 소방설비 기준을 맞춰야 하며, "
            f"미이행 시 시정명령과 과태료 부과 대상이 된다. "
            f"과태료는 위반 횟수에 따라 차등 부과하는 방안이 검토된다."
        )
    elif who:
        change = (brief.get("business_change") or "").strip().rstrip(".")
        change = re.sub(
            r"^(정부|국토교통부|국토부|보건복지부|복지부|재정경제부|기획재정부|"
            r"금융위|금융위원회|산업통상부|산업통상자원부)(는|가)\s*",
            "",
            change,
        )
        if change and len(change) < 120:
            opener = f"{who_topic} {change}."
        else:
            opener = f"{who_topic} 바뀌는 의무·기준을 확인하고 적용 일정을 점검해야 한다."
    else:
        opener = ""

    needs_repair = (
        agency
        or _cb_has_broken_korean(p0)
        or not any(key in p0 for key in CB_LEAD_KEYS)
    )
    if needs_repair and opener:
        paras[0] = opener
    return paras


def _cb_has_broken_korean(text: str) -> bool:
    t = text or ""
    if re.search(r"협력사은|사업주은|상장사은|다을|을을|은은|는는|있다을|된다을|반영될 수 있다을", t):
        return True
    # Batchim nouns wrongly taking 는 (e.g. 중소기업는 / 관련 기업는)
    if re.search(r"(?:중소기업|관련\s*기업|(?<![가-힣])기업)는", t):
        return True
    return False


def _cb_repeated_chunk(paras: list[str]) -> bool:
    blobs = [re.sub(r"\s+", "", p) for p in paras if p]
    for i, a in enumerate(blobs):
        if len(a) < 40:
            continue
        for j, b in enumerate(blobs):
            if i >= j:
                continue
            if a[:50] in b or b[:50] in a:
                return True
    return False


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


def inject_cb_business_anchors(
    paras: list[str],
    packet: dict[str, Any],
    source_text: str = "",
) -> list[str]:
    if len(paras) < 4:
        return paras
    brief = packet.get("compliance_brief") or build_compliance_brief(packet)
    para3 = (paras[2] or "").strip()
    for item in brief.get("check_items") or []:
        text = str(item).strip().rstrip(".")
        if not text or len(text) > 48 or re.search(r"[.!?]", text):
            continue
        if text not in para3:
            paras[2] = f"{para3} {text}도 함께 점검해야 한다.".strip()
            para3 = paras[2]
            break
    if not any(key in paras[2] for key in CB_PARA3_KEYS):
        blob = " ".join(
            [
                source_text or "",
                " ".join(str(x) for x in (brief.get("check_items") or [])),
                " ".join(str(x) for x in (brief.get("remaining_limits") or [])),
                str(brief.get("business_change") or ""),
                " ".join(paras),
            ]
        )
        if any(m in blob for m in CB_REGULATORY_MARKERS):
            paras[2] = (
                f"{paras[2].rstrip()} 적용 범위·시행 일정·과태료·조달·계약 반영 여부를 점검해야 한다."
            ).strip()
        else:
            paras[2] = (
                f"{paras[2].rstrip()} 적용 대상·일정·제출 요건을 점검해야 한다."
            ).strip()

    para4 = (paras[3] or "").strip()
    if not para4.startswith("다만"):
        paras[3] = ensure_danman_prefix(para4) if para4 else "다만 세부 기준은 하위 고시에 따라 달라질 수 있다."
    else:
        paras[3] = normalize_danman_opener(para4)
    for item in brief.get("remaining_limits") or []:
        text = str(item).strip().rstrip(".")
        if not text or len(text) > 80:
            continue
        if not any(k in text for k in ("유예", "고시", "예정", "미만", "예외", "공지")):
            continue
        short = text.split("다.")[0]
        if len(short) <= 70 and short not in paras[3]:
            paras[3] = ensure_danman_prefix(
                f"{short}. 예외 범위와 후속 공지 여부를 계속 확인해야 한다."
            )
            break
    if len(paras[3]) < MIN_PARAGRAPH_CHARS:
        paras[3] = (
            f"{paras[3].rstrip('.')} "
            "적용 범위와 유예 조건은 후속 고시에 따라 달라질 수 있다."
        ).strip()
    return paras


def _cb_strip_invented_norm(text: str, source_text: str = "") -> str:
    """Drop invented 의무화 only when the source does not use that wording."""
    t = text or ""
    src = source_text or ""
    if "의무화" not in src:
        t = t.replace("의무화", "강화")
    if "의무적으로" not in src:
        t = t.replace("의무적으로", "")
    t = re.sub(r"기준을\s*기준으로", "기준을", t)
    t = re.sub(r"기준으로\s*갖춰야", "맞춰야", t)
    t = re.sub(r"기준\s*기준", "기준", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def finalize_cb_title(title: str, article: dict[str, Any] | None = None) -> str:
    source = f"{(article or {}).get('title') or ''} {(article or {}).get('body') or ''}"
    t = (title or "").strip()
    if "의무화" in t and "의무화" not in source:
        t = t.replace("의무화", "강화")
    t = re.sub(r"기준\s*기준", "기준", t)
    t = re.sub(r"강화\s*강화", "강화", t)
    return t


def finalize_cb_editorial_body(
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> str:
    source_text = (article or {}).get("body") or ""
    body = flatten_nested_paragraph_tags(body)
    body = _cb_strip_invented_norm(body, source_text)
    body = normalize_temporal_in_body(body, source_text)
    body = enforce_four_paragraph_structure(body)
    body = inject_missing_source_anchors(body, source_text)
    body = append_limitation_paragraph_if_needed(body, packet)
    body = inject_reader_utility_anchors(body, packet)
    body = ensure_cb_limitation_paragraph(body, packet)
    paras = _paragraph_plain_blocks(body)
    if paras:
        paras = repair_cb_lead(paras, packet, source_text)
        paras = inject_cb_business_anchors(paras, packet, source_text)
        paras = inject_cb_confirmation_quote(paras, packet)
        # Soften agency-toned para2 opener for CB desk
        if len(paras) >= 2 and re.match(
            r"^(국토교통부|국토부|정부|보건복지부|복지부)(는|가)\s*",
            paras[1] or "",
        ):
            paras[1] = re.sub(
                r"^(국토교통부|국토부|정부|보건복지부|복지부)(는|가)\s*",
                "이번 조치는 ",
                paras[1],
                count=1,
            )
            paras[1] = paras[1].replace("전환한다는 방침이다", "전환한다")
            paras[1] = paras[1].replace("전환하는 취지다", "전환한다")
            paras[1] = re.sub(r"취지다\.", "다.", paras[1])
            paras[1] = paras[1].replace("전환한다", "전환한다")
        paras = _polish_cb_paragraphs(paras)
        body = "".join(f"<p>{p}</p>" for p in paras[:4])
    body = sanitize_editorial_body(body, packet)
    body = pad_paragraph_min_length(body)
    body = cap_watch_phrase_repetition(body)
    if is_cb_publish_v4_enabled():
        from engine.pipeline.publish_validate import publish_sanitize_body

        body, _footer = publish_sanitize_body(body, packet, article)
        paras = _paragraph_plain_blocks(body)
        paras = repair_cb_lead(paras, packet, source_text)
        paras = _polish_cb_paragraphs(paras)
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

    source_text = (article or {}).get("body") or ""
    body = flatten_nested_paragraph_tags(body)
    body = _cb_strip_invented_norm(body, source_text)
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

    if _cb_has_broken_korean(plain):
        return False, "CB 비문·조사 오류"
    if _cb_repeated_chunk(paras):
        return False, "CB 문장 반복"
    if is_cb_agency_lead(paras[0] or ""):
        return False, "1문단 기관명 리드"

    missing = missing_fact_labels(plain, source_text)
    if missing:
        return False, "원문 핵심 누락: " + ", ".join(missing)

    if is_cb_publish_v4_enabled():
        from engine.pipeline.publish_validate import publish_sanitize_body

        body, _ = publish_sanitize_body(body, packet, article)
        plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()
        if re.search(r"https?://|www\.", plain, re.I):
            return False, "본문 URL 노출(v4)"

    from engine.pipeline.rewrite_validate import validate_source_fidelity

    title = _cb_strip_invented_norm(title)
    title = finalize_cb_title(title, article)
    body = _cb_strip_invented_norm(body)
    ok_fid, fid_msg = validate_source_fidelity(title, body, article, packet=packet)
    if not ok_fid:
        return False, fid_msg

    return True, "OK"
