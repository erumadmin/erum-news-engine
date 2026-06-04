"""Deterministic checks for IJ editorial hybrid rewrites (post-LLM)."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from engine.pipeline.editorial_facts import missing_fact_labels
from research_collector import strip_html_tags

IJ_REQUIRED_PARAGRAPH_COUNT = 4
MIN_PARAGRAPH_CHARS = 55
LIMITATION_MARKERS = (
    "다만",
    "한계",
    "조건",
    "유의",
    "아직",
    "남은",
    "취소",
    "미시행",
    "예정",
    "제외",
    "범위",
)
LEAD_HEAD_CHARS = 120
LEAD_CHUNK_MIN = 20
POLICY_EXPANSION_PHRASES = ("뒷받침", "활성화", "개선해")
LIMITATION_SAFE_MARKERS = ("한계", "유의", "예정", "제외", "불확실")
STRONG_LIMITATION_MARKERS = ("한계", "유의", "불확실", "제외", "취소")
CAUTION_GAP_KEYWORDS = ("한계", "취소", "예정", "지정 취소", "일률")
LIMITATION_SENTENCE_GAP_MARKERS = ("한계", "취소", "지정 취소", "일률")
DEFAULT_LIMITATION_SENTENCE = (
    "다만 이번 조치는 시행 범위·적용 조건에 따라 효과가 달라질 수 있어, "
    "유의할 한계와 남은 조건은 공식 안내를 함께 확인해야 한다."
)
AS_OF_BOILERPLATE_RE = re.compile(
    r"\s*보도·안내\s*내용은\s+[^.!?。]{0,48}기준\s+공식\s+보도자료[^.!?。]*[.!?。]?\s*",
    re.IGNORECASE,
)
REPEAT_WATCH_PHRASES = ("자동 적용", "유리한 요금", "자동으로", "비교 분석", "비교분석")
REPEAT_MAX_TOTAL = 4
REPEAT_POLICY_TERMS = ("6개월",)
PHRASE_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "유리한 요금": ("낮은 요금", "요금이 적은 쪽", "저렴한 요금안"),
    "자동 적용": ("자동 반영", "자동 선택"),
    "자동으로": ("별도 신청 없이", "스스로"),
    "비교 분석": ("요금 비교", "요금안 비교"),
    "비교분석": ("요금 비교", "요금안 비교"),
}


def _lead_anchor_texts(packet: dict[str, Any], article: dict[str, Any] | None = None) -> list[str]:
    texts: list[str] = []
    main = (packet.get("main_claim") or "").strip()
    if main:
        texts.append(main)
    jb = packet.get("journalist_brief") or {}
    lead_q = (jb.get("lead_question") or "").strip()
    if lead_q:
        texts.append(lead_q)
    for fact in packet.get("key_facts") or []:
        fact = (fact or "").strip()
        if fact:
            texts.append(fact)
            break
    ft = packet.get("field_takeaways") or {}
    lead_line = (ft.get("lead_line") or "").strip()
    if lead_line:
        texts.append(lead_line)
    return texts


def _anchor_chunk_present(head: str, anchor: str, min_len: int = LEAD_CHUNK_MIN) -> bool:
    anchor = (anchor or "").strip()
    head = head or ""
    if len(anchor) < min_len:
        return False
    if anchor in head:
        return True
    for i in range(0, len(anchor) - min_len + 1):
        if anchor[i : i + min_len] in head:
            return True
    return False


def validate_para1_lead(
    paras: list[str],
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if not paras or not (paras[0] or "").strip():
        return False, "1문단 리드 부족"
    p0 = (paras[0] or "").strip()
    ft = packet.get("field_takeaways") or {}
    lead_line = (ft.get("lead_line") or "").strip()
    main = (packet.get("main_claim") or "").strip()
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if lead_line and is_publish_v4_enabled():
        head = p0[:LEAD_HEAD_CHARS]
        if "이를 위해" in p0[:200]:
            return False, "1문단 리드 부족"
        if re.match(r"^[^.]{8,60}\s+1\.\s*산업통상", p0):
            return False, "1문단 리드 부족"
        if p0.startswith("연대·보고"):
            return False, "1문단 리드 부족"
        for anchor in (lead_line, main, *_lead_anchor_texts(packet, article)):
            if not anchor:
                continue
            chunk = min(LEAD_CHUNK_MIN, max(12, len(anchor.strip())))
            if _anchor_chunk_present(head, anchor, min_len=chunk):
                return True, "OK"
        return False, "1문단 리드 부족"
    if lead_line:
        if not p0.startswith(lead_line[: min(28, len(lead_line))]):
            return False, "1문단 리드 부족"
        if "이를 위해" in p0[:200]:
            return False, "1문단 리드 부족"
        head = p0[:80]
        if re.match(r"^[^.]{8,60}\s+1\.\s*산업통상", p0):
            return False, "1문단 리드 부족"
        if head.startswith("산업통상") and "연대" not in head[:60] and "NGO" not in head[:60]:
            return False, "1문단 리드 부족"
        return True, "OK"
    head = p0[:LEAD_HEAD_CHARS]
    for anchor in _lead_anchor_texts(packet, article):
        if _anchor_chunk_present(head, anchor):
            return True, "OK"
    return False, "1문단 리드 부족"


def caution_unsafe_for_inject(caution: str) -> bool:
    """Block injecting caution_line that reads as policy expansion."""
    c = (caution or "").strip()
    if not c:
        return True
    if any(x in c for x in POLICY_EXPANSION_PHRASES):
        return True
    head = c[:60]
    if "이를 통해" in head and not any(m in head for m in LIMITATION_SAFE_MARKERS):
        return True
    return False


def is_policy_expansion_text(text: str, *, head_len: int = 60) -> bool:
    """True when text reads as policy expansion, not a limitation/caution."""
    t = (text or "").strip()
    if not t:
        return False
    if any(x in t for x in POLICY_EXPANSION_PHRASES) and not any(
        m in t for m in STRONG_LIMITATION_MARKERS
    ):
        return True
    head = t[:head_len]
    if "이를 통해" in head and not any(m in head for m in LIMITATION_SAFE_MARKERS):
        return True
    return False


def coalition_gap_qualifies_for_caution(gap: str) -> bool:
    """Coalition gap suitable for para4 caution inject (real limitation, not expansion)."""
    gap = (gap or "").strip()
    if len(gap) < 12 or not any(k in gap for k in CAUTION_GAP_KEYWORDS):
        return False
    return not is_policy_expansion_text(gap)


def sentence_is_para4_expansion(sent: str) -> bool:
    """Strip-worthy expansion sentence in para 4."""
    s = (sent or "").strip()
    if not s:
        return False
    if "이를 통해" in s and "뒷받침" in s:
        return True
    return is_policy_expansion_text(s)


def _split_korean_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", t)
    return [p.strip() for p in parts if p.strip()]


def strip_para4_expansion_sentences(para: str, packet: dict[str, Any] | None = None) -> str:
    """Remove expansion-only tails from para 4 (post-inject cleanup)."""
    para = (para or "").strip()
    if not para:
        return para
    jb = (packet or {}).get("journalist_brief") or {}
    expansion_gaps = [
        (g or "").strip()
        for g in (jb.get("coalition_gaps") or [])
        if (g or "").strip() and is_policy_expansion_text(g)
    ]
    kept: list[str] = []
    for sent in _split_korean_sentences(para):
        drop = sentence_is_para4_expansion(sent)
        if not drop and expansion_gaps:
            for gap in expansion_gaps:
                chunk = gap[: min(40, len(gap))]
                if len(chunk) >= 20 and chunk in sent:
                    drop = True
                    break
        if not drop:
            kept.append(sent)
    if not kept:
        return ""
    out = " ".join(kept).strip()
    if out and not out.startswith("다만") and para.startswith("다만"):
        out = f"다만 {out.lstrip('다만').strip()}"
    return out


def validate_limitation_paragraph(
    para4: str,
    para3: str | None = None,
) -> tuple[bool, str]:
    p = (para4 or "").strip()
    if not p.startswith("다만"):
        return False, "4문단 한계·유의 부족"
    substantive = [m for m in LIMITATION_MARKERS if m != "다만"]
    has_substance = any(m in p for m in substantive)
    expansion_only = any(x in p for x in POLICY_EXPANSION_PHRASES) and not has_substance
    if expansion_only or not has_substance:
        return False, "4문단 한계·유의 부족"
    if para3:
        from engine.pipeline.coalition_takeaways import _gap_overlaps_para3

        core = p.lstrip("다만").strip()
        if _gap_overlaps_para3(para3, core):
            return False, "4문단 한계·유의 부족"
    return True, "OK"


def _para4_is_generic_limitation(p4: str) -> bool:
    p4 = (p4 or "").strip()
    if not p4:
        return True
    if p4.strip() == DEFAULT_LIMITATION_SENTENCE.strip():
        return True
    return "시행 범위·적용 조건" in p4 and "공식 안내를 함께 확인" in p4


def strip_publish_boilerplate_para4(p4: str) -> str:
    """Remove v3 template limitation and as-of footer from publish para 4."""
    p = (p4 or "").strip()
    p = AS_OF_BOILERPLATE_RE.sub("", p).strip()
    if _para4_is_generic_limitation(p):
        if p.strip() == DEFAULT_LIMITATION_SENTENCE.strip():
            return ""
        gen = DEFAULT_LIMITATION_SENTENCE.strip()
        if gen in p:
            p = p.replace(gen, "").strip(" .")
    return p.strip()


def is_publish_boilerplate_para4(p4: str) -> bool:
    p = (p4 or "").strip()
    if not p:
        return False
    if _para4_is_generic_limitation(p):
        return True
    return bool(AS_OF_BOILERPLATE_RE.search(p))


V4_EVIDENCE_CAUTION = (
    "다만 세부 적용 대상·시행 일정·예외 조건은 "
    "관계 부처 공식 안내와 보도자료 원문을 통해 확인해야 한다."
)


def _strip_coalition_caution_prefix(caution: str) -> str:
    c = (caution or "").strip()
    if c.startswith("연대·대외 안내 시 "):
        return c[len("연대·대외 안내 시 ") :].strip()
    if c.startswith("연대·보고 현장에서는 "):
        return c[len("연대·보고 현장에서는 ") :].strip()
    return c


def build_v4_limitation_from_packet(
    packet: dict[str, Any],
    p3_plain: str,
) -> str:
    """Article-specific para4 for v4 (no DEFAULT_LIMITATION / as-of boilerplate)."""
    from engine.pipeline.coalition_takeaways import refine_limitation_sentence_for_body

    p3 = (p3_plain or "").strip()
    lim = refine_limitation_sentence_for_body(packet, p3)
    if lim and validate_limitation_paragraph(lim, p3)[0] and not is_publish_boilerplate_para4(lim):
        return lim[:480]

    ft = packet.get("field_takeaways") or {}
    caution = _strip_coalition_caution_prefix((ft.get("caution_line") or "").strip())
    if caution:
        trial = caution if caution.startswith("다만") else f"다만 {caution}"
        if (
            validate_limitation_paragraph(trial, p3)[0]
            and not is_publish_boilerplate_para4(trial)
            and not is_policy_expansion_text(trial)
        ):
            return trial[:480]

    for fact in packet.get("key_facts") or []:
        fact = (fact or "").strip()
        if len(fact) < 18:
            continue
        if is_policy_expansion_text(fact):
            continue
        if not any(
            m in fact
            for m in (
                "한계",
                "유의",
                "예정",
                "제외",
                "아직",
                "미시행",
                "조건",
                "범위",
                "확정",
                "시행",
            )
        ):
            continue
        trial = f"다만 {fact[:150].rstrip('.')}."
        if validate_limitation_paragraph(trial, p3)[0] and not is_publish_boilerplate_para4(trial):
            return trial[:480]

    for item in packet.get("discovered_facts") or []:
        fact = (item.get("fact") or "").strip()
        if len(fact) < 20 or is_policy_expansion_text(fact):
            continue
        trial = f"다만 {fact[:140].rstrip('.')}."
        if validate_limitation_paragraph(trial, p3)[0] and not is_publish_boilerplate_para4(trial):
            return trial[:480]

    if "official_evidence_missing" in (packet.get("risk_flags") or []):
        return V4_EVIDENCE_CAUTION

    return ""


def fix_ij_llm_body_markup(body: str) -> str:
    """Normalize common LLM markup issues before validate_content_quality."""
    out = flatten_nested_paragraph_tags(body or "")
    out = out.replace("…", "다.").replace("...", "")
    for pat, repl in (
        (r"습니다\.", "다."),
        (r"습니다\b", "다"),
        (r"입니다\.", "다."),
        (r"입니다\b", "다"),
        (r"드립니다\.", "한다."),
        (r"겠습니다\.", " 것이다."),
    ):
        out = re.sub(pat, repl, out)
    plain = strip_html_tags(out).strip()
    if plain and plain[-1] in "0123456789":
        out = re.sub(r"(\d)(\s*</p>\s*)$", r"\1.</p>", out.rstrip(), count=1) + "\n"
    return out


def fix_para1_lead_opener(paras: list[str], packet: dict[str, Any]) -> list[str]:
    if not paras:
        return paras
    p0 = (paras[0] or "").strip()
    ft = packet.get("field_takeaways") or {}
    lead_line = (ft.get("lead_line") or "").strip()
    if lead_line:
        from engine.pipeline.coalition_takeaways import sanitize_para1_coalition

        raw = packet.get("_raw_source") or {}
        paras[0] = sanitize_para1_coalition(p0, lead_line, raw)
        p0 = paras[0]
    if p0.startswith("이를 위해"):
        main = (packet.get("main_claim") or "").strip()
        if main and not lead_line:
            sent = main[:100].rstrip(".") + "."
            paras[0] = f"{sent} {p0}".strip()
    ok, _ = validate_para1_lead(paras, packet, None)
    if ok:
        return paras
    if lead_line:
        return paras
    for fact in packet.get("key_facts") or []:
        fact = (fact or "").strip()
        if len(fact) < LEAD_CHUNK_MIN:
            continue
        if _anchor_chunk_present(paras[0][:LEAD_HEAD_CHARS], fact):
            break
        sent = fact[:100].rstrip(".") + "."
        paras[0] = f"{sent} {paras[0]}".strip()
        break
    return paras


def ensure_valid_limitation_paragraph(body: str, packet: dict[str, Any]) -> str:
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    paras = _paragraph_plain_blocks(body, preserve_empty=True)
    if len(paras) < 4:
        return body
    while len(paras) < 4:
        paras.append("")
    ft = packet.get("field_takeaways") or {}
    p3 = paras[2] if len(paras) >= 3 else ""
    v4 = is_publish_v4_enabled()
    if v4:
        paras[3] = strip_publish_boilerplate_para4(paras[3])
    from engine.pipeline.coalition_takeaways import refine_limitation_sentence_for_body

    limitation = refine_limitation_sentence_for_body(packet, p3) or (
        ft.get("limitation_sentence") or ""
    ).strip()
    if limitation and validate_limitation_paragraph(limitation, p3)[0]:
        p4 = paras[3]
        lim_head = limitation[: min(40, len(limitation))]
        if _para4_is_generic_limitation(p4) or (lim_head and lim_head not in p4):
            paras[3] = limitation[:480]
            return "".join(f"<p>{p}</p>" for p in paras[:4])
    ok, _ = validate_limitation_paragraph(paras[3], p3)
    if ok and not is_publish_boilerplate_para4(paras[3]):
        return "".join(f"<p>{p}</p>" for p in paras[:4])
    if limitation and validate_limitation_paragraph(limitation, p3)[0]:
        paras[3] = limitation[:480]
        return "".join(f"<p>{p}</p>" for p in paras[:4])
    caution = (ft.get("caution_line") or "").strip()
    if not v4:
        if caution.startswith("연대·대외 안내 시 "):
            trial = f"다만 {caution[len('연대·대외 안내 시 ') :].strip()}"
        elif caution and not caution.startswith("다만"):
            trial = f"다만 {caution}"
        else:
            trial = caution
        if trial and validate_limitation_paragraph(trial, p3)[0]:
            paras[3] = trial[:480]
            return "".join(f"<p>{p}</p>" for p in paras[:4])
        paras[3] = DEFAULT_LIMITATION_SENTENCE
        return "".join(f"<p>{p}</p>" for p in paras[:4])
    v4_lim = build_v4_limitation_from_packet(packet, p3)
    if v4_lim:
        paras[3] = v4_lim
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def split_limitation_paragraph(body: str, packet: dict[str, Any]) -> str:
    """Move URL/action tail from para 4 to para 3 when para 4 is overloaded."""
    max_p4 = 400
    max_p3 = 880
    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body
    p4 = paras[3]
    if len(p4) <= max_p4 or "다만" not in p4:
        return body
    url_m = re.search(r"https?://\S+", p4)
    if not url_m:
        return body
    idx = url_m.start()
    head = p4[:idx].rstrip(" ,;")
    tail = p4[idx:].strip()
    if not head.startswith("다만"):
        head = f"다만 {head.lstrip('다만').strip()}"
    if tail and len(paras[2]) + len(tail) + 2 <= max_p3:
        paras[2] = f"{paras[2].rstrip()} {tail}".strip()
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    ru = packet.get("reader_utility") or {}
    as_of = (ru.get("as_of_date") or "").strip()
    parts = [head]
    if not is_publish_v4_enabled() and as_of and as_of not in head:
        parts.append(f"보도·안내 내용은 {as_of} 기준 공식 보도자료를 참고한다.")
    ft = packet.get("field_takeaways") or {}
    caution = (ft.get("caution_line") or "").strip()
    if caution and len(caution) <= 140:
        caution_head = caution[:40]
        if not any(x in caution_head for x in POLICY_EXPANSION_PHRASES):
            if any(m in caution for m in LIMITATION_MARKERS[1:]) or any(
                m in caution for m in ("예정", "제외", "불확실", "시행 전", "미정")
            ):
                if caution not in head:
                    parts.append(caution[:120])
    paras[3] = " ".join(parts).strip()[:max_p4]
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def flatten_nested_paragraph_tags(body: str) -> str:
    """Fix <p><p>...</p></p> duplicates from the rewrite model."""
    out = body or ""
    for _ in range(4):
        updated = re.sub(r"(<p[^>]*>)\s*<p[^>]*>", r"\1", out, flags=re.IGNORECASE)
        updated = re.sub(r"</p>\s*</p>", "</p>", updated, flags=re.IGNORECASE)
        if updated == out:
            break
        out = updated
    return out


def normalize_temporal_in_body(body: str, source_text: str) -> str:
    """Replace common mismatch when source says next month."""
    hint = temporal_hint_from_source(source_text)
    if not hint.startswith("다음 달"):
        return body
    return re.sub(r"이달부터", "다음 달 1일부터", body)


def temporal_hint_from_source(text: str) -> str:
    """Primary timing phrase from policy briefing body (for consistent copy)."""
    if not text:
        return ""
    if re.search(r"다음\s*달\s*1\s*일", text):
        return "다음 달 1일부터"
    if re.search(r"다음\s*달", text):
        return "다음 달부터"
    m = re.search(r"(\d{1,2})월\s*1\s*일부터", text)
    if m:
        return f"{m.group(1)}월 1일부터"
    m = re.search(r"(\d{1,2})월부터", text)
    if m:
        return f"{m.group(1)}월부터"
    return ""


def _paragraph_plain_blocks(body: str, *, preserve_empty: bool = False) -> list[str]:
    blocks = re.findall(r"<p[^>]*>(.*?)</p>", body or "", flags=re.IGNORECASE | re.DOTALL)
    if blocks:
        plain = [strip_html_tags(b).strip() for b in blocks]
        if preserve_empty:
            return plain
        return [p for p in plain if p]
    plain = strip_html_tags(body or "")
    parts = [p.strip() for p in re.split(r"\n{2,}", plain)]
    if preserve_empty:
        return parts
    return [p for p in parts if p]


def _urls_required_from_packet(packet: dict[str, Any]) -> list[str]:
    hosts: list[str] = []
    for item in packet.get("action_items") or []:
        for url in re.findall(r"https?://[^\s\)\]\"']+", str(item)):
            host = (urlparse(url).netloc or "").lower()
            if host:
                hosts.append(host)
    return list(dict.fromkeys(hosts))


def validate_ij_editorial_rewrite(
    title: str,
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if not body or not body.strip():
        return False, "본문 누락"

    body = flatten_nested_paragraph_tags(body)
    paras = _paragraph_plain_blocks(body)
    paragraph_count = len(paras)
    if paragraph_count < IJ_REQUIRED_PARAGRAPH_COUNT:
        return False, f"문단 수 부족({paragraph_count}개, IJ 4문단 필요)"

    source_text = (article or {}).get("body") or ""
    body = normalize_temporal_in_body(body, source_text)
    plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()
    paras = _paragraph_plain_blocks(body)
    hint = temporal_hint_from_source(source_text) or temporal_hint_from_source(plain)

    if hint.startswith("다음 달") and re.search(r"이달부터|이번 달부터", plain):
        return False, "시점 표기 불일치(이달/다음 달 혼용)"

    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if not is_publish_v4_enabled():
        for host in _urls_required_from_packet(packet):
            if host not in plain.lower() and host.replace("www.", "") not in plain.lower():
                return False, f"독자 확인 URL 누락({host})"

    for phrase in REPEAT_WATCH_PHRASES:
        if plain.count(phrase) > 2:
            return False, f"반복 과다({phrase})"
    for phrase in REPEAT_POLICY_TERMS:
        if plain.count(phrase) > REPEAT_MAX_TOTAL:
            return False, f"반복 과다({phrase})"

    ok_roles, role_msg = validate_paragraph_roles(paras)
    if not ok_roles:
        return False, role_msg

    missing = missing_fact_labels(plain, source_text)
    if missing:
        return False, "원문 핵심 누락: " + ", ".join(missing)

    risk_flags = packet.get("risk_flags") or []

    if not title or len(title.strip()) < 5:
        return False, "제목 누락 또는 너무 짧음"

    from engine.pipeline.target_engine import is_target_engine_enabled

    if is_target_engine_enabled():
        gate = packet.get("research_gate") or {}
        if gate.get("research_insufficient"):
            return False, "research_insufficient"
        from engine.pipeline.discovered_facts import discovered_fact_reflected_in_plain

        discovered = packet.get("discovered_facts") or []
        source_text = (article or {}).get("body") or ""
        skip_discovered_gate = is_publish_v4_enabled() and os.environ.get("REVIEW_ONLY", "0") == "1"
        if not skip_discovered_gate:
            for d in discovered[:3]:
                fact = (d.get("fact") or "").strip()
                if len(fact) < 20:
                    continue
                from engine.pipeline.discovered_facts import _in_source

                if _in_source(fact, source_text):
                    continue
                if not discovered_fact_reflected_in_plain(fact, plain):
                    return False, "discovered_fact 본문 미반영"
        from engine.pipeline.coalition_brief import assess_briefing_ready

        if not is_publish_v4_enabled():
            from engine.pipeline.coalition_takeaways import coalition_takeaways_reflected_in_body

            ok_take, take_gaps = coalition_takeaways_reflected_in_body(plain, packet, paras=paras)
            if not ok_take:
                return False, "coalition_takeaways_weak: " + ", ".join(take_gaps)

            br = assess_briefing_ready(packet, discovered, body_plain=plain, paras=paras)
            if not br.get("briefing_ready"):
                reasons = list(br.get("fail_reasons") or [])
                if os.environ.get("REVIEW_ONLY", "0") == "1":
                    reasons = [r for r in reasons if r != "discovered_below_min"]
                if reasons:
                    return False, "briefing_not_ready: " + ", ".join(reasons)

        if is_publish_v4_enabled():
            from engine.pipeline.publish_validate import publish_sanitize_body

            body, _ = publish_sanitize_body(body, packet, article)
            paras = _paragraph_plain_blocks(body)

        ok_lead, lead_msg = validate_para1_lead(paras, packet, article)
        if not ok_lead:
            return False, lead_msg

        ok_lim, lim_msg = validate_limitation_paragraph(
            paras[3], paras[2] if len(paras) >= 3 else None
        )
        if not ok_lim:
            return False, lim_msg

    return True, "OK"


def append_limitation_paragraph_if_needed(body: str, packet: dict[str, Any]) -> str:
    if "official_evidence_missing" not in (packet.get("risk_flags") or []):
        return body
    paras = _paragraph_plain_blocks(body)
    if paras and any(m in paras[-1] for m in LIMITATION_MARKERS):
        return body
    fallback = (
        "다만 이번 조치는 보도자료·시행 범위에 따라 적용 대상과 효과가 달라질 수 있어, "
        "시행 시점과 남은 조건은 공식 안내를 함께 확인해야 한다."
    )
    matches = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", body or "", flags=re.IGNORECASE | re.DOTALL))
    if matches:
        last = matches[-1]
        inner = strip_html_tags(last.group(2)).strip()
        if not inner.startswith("다만"):
            inner = f"다만 {inner}"
        return (
            body[: last.start()]
            + f"{last.group(1)}{inner}{last.group(3)}"
            + body[last.end() :]
        )
    return body.rstrip() + f"<p>{fallback}</p>"


def _split_sentences(plain: str) -> list[str]:
    parts = re.split(r"(?<=[다.!?])\s+", plain or "")
    return [p.strip() for p in parts if p.strip() and len(p.strip()) >= 8]


def enforce_four_paragraph_structure(body: str) -> str:
    """Rebuild exactly four <p> blocks with IJ role separation."""
    from engine.pipeline.ij_paragraph_roles import (
        BG_PARA2_KEYS,
        MECH_PARA3_KEYS,
        reorder_paragraph_roles_paras,
    )

    body = flatten_nested_paragraph_tags(body or "")
    paras = _paragraph_plain_blocks(body)
    if len(paras) == 4:
        paras = reorder_paragraph_roles_paras(paras)
    if len(paras) == 4 and all(len(p) >= MIN_PARAGRAPH_CHARS for p in paras):
        roles_ok = (
            any(k in paras[1] for k in BG_PARA2_KEYS)
            and any(k in paras[2] for k in MECH_PARA3_KEYS)
            and (paras[3].startswith("다만") or any(m in paras[3] for m in LIMITATION_MARKERS))
        )
        if roles_ok:
            return "".join(f"<p>{p}</p>" for p in paras)

    plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()
    sentences = _split_sentences(plain)
    buckets: list[list[str]] = [[], [], [], []]
    for sent in sentences:
        if sent.startswith("다만") or ("법적 의무" in sent and "다만" in plain):
            buckets[3].append(sent)
        elif any(k in sent for k in ("http://", "https://", "한전ON", "에너지마켓")):
            buckets[2].append(sent)
        elif any(k in sent for k in ("그동안", "우려", "문제가", "부담이")):
            buckets[1].append(sent)
        elif any(k in sent for k in ("고지서", "표기", "단일 요금", "시간대별", "자동 적용", "비교분석")):
            buckets[2].append(sent)
        elif not buckets[0]:
            buckets[0].append(sent)
        elif len(buckets[1]) < len(buckets[2]):
            buckets[1].append(sent)
        else:
            buckets[2].append(sent)

    for sent in list(buckets[2]):
        if "다만" in sent or "700억" in sent or "LED" in sent:
            buckets[2].remove(sent)
            buckets[3].append(sent)

    fallback_limitation = (
        "다만 이번 조치는 시행 범위와 적용 대상에 따라 효과가 달라질 수 있어 "
        "공식 안내를 함께 확인해야 한다."
    )
    merged: list[str] = []
    for i, bucket in enumerate(buckets):
        text = " ".join(bucket).strip()
        if not text:
            text = fallback_limitation if i == 3 else ""
        if i == 3 and text and not text.startswith("다만"):
            text = f"다만 {text}"
        merged.append(text)

    while len(merged) < 4:
        merged.append(fallback_limitation if len(merged) == 3 else "")
    merged = merged[:4]
    for i in range(4):
        if not merged[i].strip():
            merged[i] = (
                "관련 내용은 공식 보도자료와 안내 페이지에서 확인할 수 있다."
                if i == 2
                else "제도 개편 배경과 적용 대상은 원문 보도를 참고한다."
            )

    from engine.pipeline.ij_paragraph_roles import reorder_paragraph_roles_paras

    merged = reorder_paragraph_roles_paras(merged)
    return "".join(f"<p>{p}</p>" for p in merged)


def inject_missing_source_anchors(body: str, source_text: str) -> str:
    """Append source-anchored sentences when the model omitted named procedures."""
    from engine.pipeline.editorial_facts import (
        FACT_LABEL_INJECT,
        fact_groups_from_source,
        missing_fact_labels,
    )

    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body
    plain = " ".join(paras)
    groups = {label: alts for label, alts in fact_groups_from_source(source_text)}
    for label in missing_fact_labels(plain, source_text):
        spec = FACT_LABEL_INJECT.get(label)
        if not spec:
            continue
        idx, tmpl = spec
        alt = groups[label][0]
        sentence = tmpl.format(alt=alt)
        if idx < len(paras) and sentence not in paras[idx]:
            paras[idx] = f"{paras[idx].rstrip()} {sentence}".strip()
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def _dedupe_urls_in_text(text: str) -> str:
    """Keep first URL per host; drop 'url: url' label noise."""
    text = re.sub(r"\s+(https?://\S+)\s*:\s*\1\b", r" \1", text)
    text = re.sub(r"(보도자료 원문\s*[:：]\s*){2,}", "보도자료 원문: ", text)
    urls = list(re.finditer(r"https?://\S+", text))
    if len(urls) <= 1:
        return text.strip()
    seen_hosts: set[str] = set()
    to_remove: list[tuple[int, int]] = []
    for m in urls:
        host = (urlparse(m.group(0)).netloc or "").lower().replace("www.", "")
        if not host:
            continue
        if host in seen_hosts:
            to_remove.append((m.start(), m.end()))
        else:
            seen_hosts.add(host)
    out = text
    for start, end in reversed(to_remove):
        out = out[:start] + out[end:]
    return re.sub(r"\s{2,}", " ", out).strip()


def sanitize_editorial_action_paragraph(para: str, packet: dict[str, Any]) -> str:
    """Trim para-3 tail clutter after anchor injection (duplicate URLs / discovered)."""
    from engine.pipeline.discovered_facts import discovered_fact_reflected_in_plain

    para = _dedupe_urls_in_text(para)
    plain_before = para

    for item in packet.get("discovered_facts") or []:
        fact = (item.get("fact") or "").strip()
        if len(fact) < 30:
            continue
        first = para.find(fact)
        last = para.rfind(fact)
        if first >= 0 and last > first:
            para = (para[:last] + para[last + len(fact) :]).strip()
        if not discovered_fact_reflected_in_plain(fact, para):
            continue
        tokens = sorted(
            [w for w in re.findall(r"[가-힣]{4,}", fact) if len(w) >= 4],
            key=len,
            reverse=True,
        )
        for tok in tokens[:3]:
            if para.count(tok) < 2:
                continue
            before = para
            last = para.rfind(tok)
            if last > 0:
                para = para[:last].rstrip(" ,.;")
                for end in ("다.", "다 ", "한다.", "된다."):
                    pos = para.rfind(end)
                    if pos > len(para) * 0.35:
                        para = para[: pos + len(end.rstrip()) + (1 if end.endswith(".") else 0)].strip()
                        break
            if not discovered_fact_reflected_in_plain(fact, para):
                para = before
            break

    if len(para) > 920:
        cut = para.rfind("다.", 0, 920)
        if cut > 400:
            para = para[: cut + 2].strip()

    para = re.sub(r"\s+이를 위해 올해 중[^.]{0,120}\.", "", para).strip()

    if para and para[-1] not in ".!?":
        para = re.sub(r"\s+[^\s.!?·]{1,24}$", "", para).strip()
        if para and para[-1] not in ".!?":
            cut = para.rfind("다.", 0, max(0, len(para) - 1))
            if cut > len(para) * 0.4:
                para = para[: cut + 2].strip()

    return para if para else plain_before


def sanitize_editorial_limitation_paragraph(para: str) -> str:
    """Drop duplicated caution tails and policy-expansion sentences in para 4."""
    para = _dedupe_urls_in_text(para)
    if not para.strip().startswith("다만"):
        return para
    chunk = 48
    for start in range(0, max(0, len(para) - chunk * 2), 12):
        snippet = para[start : start + chunk].strip()
        if len(snippet) < 28:
            continue
        second = para.find(snippet, start + len(snippet) - 8)
        if second > start + 20:
            para = para[:second].rstrip(" ,;")
            break
    filtered: list[str] = []
    for sent in _split_korean_sentences(para):
        if sentence_is_para4_expansion(sent):
            continue
        if any(x in sent for x in POLICY_EXPANSION_PHRASES) and not any(
            m in sent for m in STRONG_LIMITATION_MARKERS
        ):
            continue
        filtered.append(sent)
    if filtered:
        para = " ".join(filtered).strip()
    else:
        para = ""
    if para and not para.startswith("다만"):
        para = f"다만 {para.lstrip('다만').strip()}"
    return para.strip()


def sanitize_editorial_body(body: str, packet: dict[str, Any]) -> str:
    from engine.pipeline.ij_paragraph_roles import reorder_paragraph_roles_paras

    paras = _paragraph_plain_blocks(body)
    if len(paras) < 3:
        return body
    paras = reorder_paragraph_roles_paras(paras)
    paras[2] = sanitize_editorial_action_paragraph(paras[2], packet)
    if len(paras) >= 4:
        paras[3] = sanitize_editorial_limitation_paragraph(paras[3])
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def cap_watch_phrase_repetition(body: str, max_count: int = 2) -> str:
    """Keep watch phrases at most *max_count* times (validation + scorecard)."""
    paras = _paragraph_plain_blocks(body)
    if not paras:
        return body
    for phrase in REPEAT_WATCH_PHRASES:
        total = sum(p.count(phrase) for p in paras)
        if total <= max_count:
            continue
        alts = PHRASE_ALTERNATIVES.get(phrase, ("해당 표현",))
        alt_idx = 0
        seen = 0
        for i, p in enumerate(paras):
            parts: list[str] = []
            start = 0
            while True:
                idx = p.find(phrase, start)
                if idx == -1:
                    parts.append(p[start:])
                    break
                parts.append(p[start:idx])
                seen += 1
                if seen <= max_count:
                    parts.append(phrase)
                else:
                    parts.append(alts[alt_idx % len(alts)])
                    alt_idx += 1
                start = idx + len(phrase)
            paras[i] = "".join(parts)
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def inject_reader_utility_anchors(body: str, packet: dict[str, Any]) -> str:
    """Ensure packet reader_utility slots appear in body (finalize, no hallucination)."""
    from engine.pipeline.reader_utility import _checklist_reflected, _scenario_reflected

    ru = packet.get("reader_utility") or {}
    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body
    plain = " ".join(paras)

    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if is_publish_v4_enabled():
        return "".join(f"<p>{p}</p>" for p in paras[:4])

    as_of = (ru.get("as_of_date") or "").strip()
    if as_of and as_of not in plain and "기준" not in plain:
        paras[3] = (
            f"{paras[3].rstrip()} 보도·안내 내용은 {as_of} 기준 공식 보도자료를 참고한다."
        ).strip()

    scenarios = ru.get("scenarios") or []
    if scenarios and not any(_scenario_reflected(s, plain) for s in scenarios):
        snippet = (scenarios[0].get("body") or "")[:90].strip()
        if snippet:
            if "반면" not in snippet and any(m in snippet for m in ("반면", "주요국", "대외")):
                snippet = f"반면 {snippet}"
            target_idx = 1 if len(paras) > 1 and len(paras[1]) < 850 else 2
            if len(paras[target_idx]) + len(snippet) < 900:
                paras[target_idx] = f"{paras[target_idx].rstrip()} {snippet}".strip()
                plain = " ".join(paras)

    checklist = ru.get("checklist") or []
    missing = [c for c in checklist if not _checklist_reflected(c, plain)]
    for step in missing[:2]:
        text = (step.get("step") or "").strip()
        if text and len(text) <= 100:
            paras[2] = f"{paras[2].rstrip()} {text}".strip()
            plain = " ".join(paras)

    from engine.pipeline.reader_utility import _url_reflected_in_plain, is_irrelevant_evidence_snippet

    links = ru.get("primary_links") or []
    missing_links = [
        link
        for link in links
        if (link.get("url") or "") and not _url_reflected_in_plain(link["url"], plain)
    ]
    if missing_links and len(paras) >= 3:
        tail = " ".join(
            f"{link.get('label', '확인')}: {link.get('url', '')}" for link in missing_links[:2]
        )
        paras[2] = f"{paras[2].rstrip()} {tail}".strip()
        plain = " ".join(paras)

    quotes = (ru.get("evidence_quotes") or []) + (ru.get("source_confirmation_quotes") or [])
    for q in quotes:
        snippet = (q.get("quote") or "").strip()
        if len(snippet) < 30 or is_irrelevant_evidence_snippet(snippet):
            continue
        if snippet[:40] in plain:
            continue
        use = snippet[:72].rstrip("., ") + ("…" if len(snippet) > 72 else "")
        if len(paras[2]) + len(use) > 950:
            use = snippet[:60]
        paras[2] = f'{paras[2].rstrip()} 공식 보도에 따르면, "{use}"'.strip()
        break

    return "".join(f"<p>{p}</p>" for p in paras[:4])


def pad_paragraph_min_length(body: str) -> str:
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if is_publish_v4_enabled():
        return body
    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body
    pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
    for i in range(len(paras)):
        while len(paras[i]) < MIN_PARAGRAPH_CHARS:
            paras[i] = f"{paras[i].rstrip()} {pad}".strip()
    return "".join(f"<p>{p}</p>" for p in paras[:4])


def finalize_ij_editorial_body(
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> str:
    source_text = (article or {}).get("body") or ""
    body = flatten_nested_paragraph_tags(body)
    body = normalize_temporal_in_body(body, source_text)
    body = enforce_four_paragraph_structure(body)
    paras = _paragraph_plain_blocks(body)
    if len(paras) >= 1:
        paras = fix_para1_lead_opener(paras, packet)
        body = "".join(f"<p>{p}</p>" for p in paras[:4])
    body = inject_missing_source_anchors(body, source_text)
    body = append_limitation_paragraph_if_needed(body, packet)
    paras = _paragraph_plain_blocks(body)
    if len(paras) != 4:
        body = enforce_four_paragraph_structure(body)
    body = inject_missing_source_anchors(body, source_text)
    body = inject_reader_utility_anchors(body, packet)
    from engine.pipeline.editorial_originality import inject_originality_anchors

    body = inject_originality_anchors(body, packet, source_text)
    body = sanitize_editorial_body(body, packet)
    from engine.pipeline.target_engine import is_target_engine_enabled

    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if is_target_engine_enabled() and not is_publish_v4_enabled():
        from engine.pipeline.coalition_takeaways import inject_coalition_field_takeaways

        body = inject_coalition_field_takeaways(body, packet)
        body = sanitize_editorial_body(body, packet)
    from engine.pipeline.inject_scorecard_slots import ensure_scorecard_slots

    body = ensure_scorecard_slots(body, packet, source_text)
    body = split_limitation_paragraph(body, packet)
    body = ensure_valid_limitation_paragraph(body, packet)
    paras = _paragraph_plain_blocks(body)
    if len(paras) >= 1:
        paras = fix_para1_lead_opener(paras, packet)
        body = "".join(f"<p>{p}</p>" for p in paras[:4])
    body = pad_paragraph_min_length(body)
    body = cap_watch_phrase_repetition(body)
    from engine.pipeline.inject_discovered import inject_discovered_fact_anchors

    body = inject_missing_source_anchors(body, source_text)
    body = inject_discovered_fact_anchors(body, packet)
    if is_publish_v4_enabled():
        from engine.pipeline.publish_validate import publish_sanitize_body

        body, _footer = publish_sanitize_body(body, packet, article)
    return body


def validate_paragraph_roles(paras: list[str]) -> tuple[bool, str]:
    from engine.pipeline.ij_paragraph_roles import BG_PARA2_KEYS, MECH_PARA3_KEYS

    if len(paras) < 4:
        return False, f"문단 수 부족({len(paras)}개)"
    for i, p in enumerate(paras[:4], start=1):
        if len(p) < MIN_PARAGRAPH_CHARS:
            return False, f"{i}문단 너무 짧음({len(p)}자)"
    if not any(k in paras[1] for k in BG_PARA2_KEYS):
        return False, "2문단 배경·문제 부족"
    if not any(k in paras[2] for k in MECH_PARA3_KEYS):
        return False, "3문단 작동 방식 부족"
    if not (paras[3].startswith("다만") or any(m in paras[3] for m in LIMITATION_MARKERS)):
        return False, "4문단 한계·조건 서술 부족"
    return True, "OK"


def build_rewrite_correction_suffix(error_message: str) -> str:
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    base = (
        f"\n\n[수정 요청] 이전 출력이 규칙을 어겼습니다: {error_message}\n"
        "반드시 수정: (1) 본문은 <p> 태그 정확히 4개 "
        "(2) 마지막 <p>는 「다만」으로 시작하고, 시행 일정·적용 범위·예외·유의 등 "
        "기사별 구체 한계 1~2문장 (템플릿·「보도·안내 내용은 … 기준」 금지) "
    )
    if is_publish_v4_enabled():
        return (
            base
            + "(3) 본문에 URL·「보도자료 원문에서 확인」·「자세한 절차는 … 확인」 금지 "
            "(4) 각 문단은 완결된 문장(。.!?。)으로 끝낼 것 — 중간에 끊기지 않게 "
            "(5) 시점 표기 하나로 통일, 「연대·보고 관점에서」 금지."
        )
    return (
        base
        + "(3) action_items URL 전부 포함 "
        "(4) 시점 표기 하나로 통일 "
        "(5) 같은 기간·절차 표현은 2회 이하."
    )
