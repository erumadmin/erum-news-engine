"""IJ publish-first v4: sanitize publish body and validate article_publish_ready."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from research_collector import strip_html_tags

from engine.pipeline.rewrite_validate import (
    IJ_REQUIRED_PARAGRAPH_COUNT,
    MIN_PARAGRAPH_CHARS,
    _paragraph_plain_blocks,
    flatten_nested_paragraph_tags,
    is_publish_boilerplate_para4,
    strip_publish_boilerplate_para4,
    validate_limitation_paragraph,
    validate_para1_lead,
)

URL_PATTERN = re.compile(r"https?://[^\s\)\]\"'<>]+|www\.[^\s\)\]\"'<>]+", re.IGNORECASE)
COALITION_OPENER_RE = re.compile(r"^연대·보고\s*관점에서\s*")
NUMBERED_PARA_RE = re.compile(r"^(\d+)\.\s+")
BRIEFING_PHRASES = (
    "연대·보고 관점에서",
    "연대·보고 현장에서는",
    "연대·보고 전",
    "연대·대외 안내 시",
    "연대·대외",
    "파트너·수혜자",
    "NGO·SE",
    "공식 조사에서 확인한 내용",
    "체크리스트",
    "보도자료 원문:",
)
COALITION_CLAUSE_RE = re.compile(
    r"(?:연대·(?:보고|대외)[^。]{0,120}|파트너·수혜자[^。]{0,80})[.!?。]?\s*"
)
PRESS_RELEASE_PASTE = re.compile(r"보도자료\s*원문\s*[:：]", re.IGNORECASE)
PUBLISH_AS_OF_INLINE_RE = re.compile(
    r"\s*기준\s*[:：]?\s*\d{4}-\d{2}-\d{2}\s*\.?\s*",
    re.IGNORECASE,
)
MAINTENANCE_SNIPPET_RE = re.compile(
    r"[^.!?。]*(?:시스템\s*점검|홈페이지\s*담당)[^.!?。]*[.!?。]?\s*"
)
PROCEDURAL_CTA_RE = re.compile(
    r"자세한\s*절차는[^.!?。]{0,80}확인(?:할\s*수\s*있)?(?:다|해야\s*한다)[.!?。]?\s*",
    re.IGNORECASE,
)
OFFICIAL_QUOTE_PASTE_RE = re.compile(
    r'공식\s*보도에\s*따르면\s*,?\s*"[^"]{10,}[.!?。…]?"\s*',
    re.IGNORECASE,
)
SOURCE_REF_IN_BODY_RE = re.compile(
    r"보도자료\s*원문[^.!?。]{0,40}확인[^.!?。]*[.!?。]?\s*",
    re.IGNORECASE,
)

HOST_LABELS: dict[str, str] = {
    "korea.kr": "보도자료 원문 (대한민국 정책브리핑)",
    "kepco.co.kr": "한전 요금 안내",
    "online.kepco.co.kr": "한전ON",
    "en-ter.co.kr": "에너지마켓플레이스",
    "price.go.kr": "참가격",
}


def is_publish_v4_enabled() -> bool:
    for key in ("IJ_PUBLISH_V4", "NN_PUBLISH_V4", "CB_PUBLISH_V4"):
        val = os.environ.get(key, "").strip().lower()
        if val in ("1", "true", "yes"):
            return True
        if val in ("0", "false", "no"):
            continue
    return os.environ.get("IJ_PUBLISH_V4", "1").strip() not in ("0", "false", "False")


def body_has_exposed_urls(text: str) -> bool:
    return bool(URL_PATTERN.search(text or ""))


def _label_for_url(url: str, fallback: str = "") -> str:
    host = (urlparse(url).netloc or "").lower().replace("www.", "")
    for key, label in HOST_LABELS.items():
        if key in host:
            return label
    return (fallback or "공식 안내").strip() or "관련 링크"


def _collect_packet_links(packet: dict[str, Any]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: str, label: str = "") -> None:
        url = (url or "").strip()
        if not url or url in seen:
            return
        seen.add(url)
        links.append({"url": url, "label": _label_for_url(url, label)})

    ru = packet.get("reader_utility") or {}
    for item in ru.get("primary_links") or []:
        add(item.get("url") or "", item.get("label") or "")
    for item in packet.get("action_items") or []:
        for url in re.findall(r"https?://[^\s\)\]\"']+", str(item)):
            add(url)
    raw = packet.get("_raw_source") or {}
    if raw.get("url"):
        add(raw["url"], "보도자료 원문")
    return links


def _inline_url_replacement(_url: str) -> str:
    """Body must not carry footer-style source labels (avoids false P2 on '브리핑' etc.)."""
    return ""


def strip_publish_metadata_leaks(text: str) -> str:
    """Remove as-of dates and maintenance-page junk from publish body text."""
    t = (text or "").strip()
    t = PUBLISH_AS_OF_INLINE_RE.sub("", t)
    t = MAINTENANCE_SNIPPET_RE.sub("", t)
    t = PROCEDURAL_CTA_RE.sub("", t)
    t = OFFICIAL_QUOTE_PASTE_RE.sub("", t)
    t = SOURCE_REF_IN_BODY_RE.sub("", t)
    t = re.sub(r"\s*☎\s*[\d\-]+\s*", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def paragraph_is_complete(p: str) -> bool:
    """True when a publish paragraph ends on a finished sentence."""
    p = (p or "").strip()
    if len(p) < MIN_PARAGRAPH_CHARS:
        return False
    if re.search(r'[.!?。]["\']?\s*$', p):
        return True
    if re.search(
        r"(습니다|합니다|한다|된다|했다|였다|이다|있다|없다|예정이다|됐다|였다)\.\s*$",
        p,
    ):
        return True
    return False


def repair_incomplete_paragraph(p: str) -> str:
    """Drop a trailing clause fragment cut mid-sentence."""
    p = (p or "").strip()
    if paragraph_is_complete(p):
        return p
    parts = re.split(r"(?<=[.!?。])\s+", p)
    if len(parts) >= 2 and parts[-1] and not re.search(r"[.!?。]\s*$", parts[-1]):
        repaired = " ".join(parts[:-1]).strip()
        if paragraph_is_complete(repaired):
            return repaired
    return p


def strip_briefing_phrases(text: str) -> str:
    """Remove coalition/briefing markers from a single text chunk (e.g. lead_line)."""
    t = (text or "").strip()
    t = COALITION_OPENER_RE.sub("", t)
    t = COALITION_CLAUSE_RE.sub("", t)
    for phrase in BRIEFING_PHRASES:
        t = t.replace(phrase, "")
    t = PRESS_RELEASE_PASTE.sub("", t)
    t = strip_publish_metadata_leaks(t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _publish_safe_packet_for_lead(packet: dict[str, Any]) -> dict[str, Any]:
    """Packet copy safe for v4 lead fix (no coalition lead_line re-injection)."""
    ft = dict(packet.get("field_takeaways") or {})
    lead = strip_briefing_phrases((ft.get("lead_line") or "").strip())
    if not lead or len(lead) < 20:
        lead = strip_briefing_phrases((packet.get("main_claim") or "").strip())
    if lead:
        ft["lead_line"] = lead[:200]
    else:
        ft.pop("lead_line", None)
    return {**packet, "field_takeaways": ft}


def _strip_urls_from_text(text: str) -> tuple[str, list[dict[str, str]]]:
    found: list[dict[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,;)")
        found.append({"url": url, "label": _label_for_url(url)})
        return _inline_url_replacement(url)

    cleaned = URL_PATTERN.sub(repl, text or "")
    cleaned = re.sub(r"(?:확인\s*[:：]\s*)+", "", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned, found


def _strip_coalition_openers(paras: list[str]) -> list[str]:
    out: list[str] = []
    for p in paras:
        t = COALITION_OPENER_RE.sub("", (p or "").strip()).strip()
        if t and t != p:
            pass
        out.append(t or p)
    return out


def _strip_numbered_prefixes(paras: list[str]) -> list[str]:
    out: list[str] = []
    for p in paras:
        t = NUMBERED_PARA_RE.sub("", (p or "").strip()).strip()
        out.append(t)
    return out


def publish_sanitize_body(
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """Remove exposed URLs and briefing patterns; return body + sources_footer entries."""
    body = flatten_nested_paragraph_tags(body or "")
    paras = _paragraph_plain_blocks(body)
    footer_map: dict[str, dict[str, str]] = {}

    def add_footer(url: str, label: str) -> None:
        url = url.strip()
        if url:
            footer_map[url] = {"url": url, "label": label or _label_for_url(url)}

    for link in _collect_packet_links(packet):
        add_footer(link["url"], link["label"])

    cleaned_paras: list[str] = []
    for p in paras:
        p2, urls = _strip_urls_from_text(p)
        for u in urls:
            add_footer(u["url"], u["label"])
        cleaned_paras.append(strip_briefing_phrases(p2))

    cleaned_paras = _strip_numbered_prefixes(cleaned_paras)

    if len(cleaned_paras) >= 4:
        from engine.pipeline.rewrite_validate import fix_para1_lead_opener

        lead_packet = _publish_safe_packet_for_lead(packet) if is_publish_v4_enabled() else packet
        force_site = os.environ.get("EDITORIAL_FORCE_SITE", "").strip().upper()
        if force_site == "NN":
            from engine.pipeline.nn_rewrite_validate import fix_nn_para1_lead_opener

            source_body = (article or {}).get("body") or ""
            cleaned_paras = fix_nn_para1_lead_opener(cleaned_paras, lead_packet, source_body)
        else:
            cleaned_paras = fix_para1_lead_opener(cleaned_paras, lead_packet)
        if is_publish_v4_enabled():
            cleaned_paras = [strip_briefing_phrases(p) for p in cleaned_paras]
            cleaned_paras = [repair_incomplete_paragraph(p) for p in cleaned_paras[:4]]
            cleaned_paras[3] = strip_publish_boilerplate_para4(cleaned_paras[3])
            cleaned_paras[3] = strip_publish_metadata_leaks(cleaned_paras[3])

    body_out = "".join(f"<p>{p}</p>" for p in cleaned_paras[:4]) if cleaned_paras else body
    from engine.pipeline.html_sanitize import sanitize_article_html

    body_out = sanitize_article_html(body_out)
    footer = list(footer_map.values())
    packet["sources_footer"] = footer
    return body_out, footer


def validate_publish_article(
    title: str,
    excerpt: str,
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """P1–P6 publish criteria from ij-news-engine-target-design-v4.md §1.1."""
    if not is_publish_v4_enabled():
        return True, "v4_disabled"

    body, _ = publish_sanitize_body(body or "", packet, article)
    body = flatten_nested_paragraph_tags(body or "")
    paras = _paragraph_plain_blocks(body)
    plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()

    if not title or len(title.strip()) < 5:
        return False, "제목 누락 또는 너무 짧음 (P1)"

    if len(paras) < IJ_REQUIRED_PARAGRAPH_COUNT:
        return False, f"문단 수 부족({len(paras)}개, P1)"

    short = [i + 1 for i, p in enumerate(paras[:4]) if len(p) < MIN_PARAGRAPH_CHARS]
    if short:
        return False, f"짧은 문단: {short} (P1)"

    incomplete = [
        i + 1
        for i, p in enumerate(paras[:4])
        if len(p) >= MIN_PARAGRAPH_CHARS and not paragraph_is_complete(p)
    ]
    if incomplete:
        return False, f"미완성 문단(문장 미종결): {incomplete} (P1)"

    if "보도자료 원문" in plain or "자세한 절차는" in plain:
        return False, "절차 안내·원문 확인 문구 (P2)"
    if "공식 보도에 따르면" in plain and '"' in plain:
        return False, "보도 인용 붙여넣기 (P2)"

    if COALITION_CLAUSE_RE.search(plain) or "연대·보고" in plain:
        return False, "브리핑체 표현: 연대·보고 (P2)"
    for phrase in BRIEFING_PHRASES:
        if phrase in plain:
            return False, f"브리핑체 표현: {phrase} (P2)"
    if PUBLISH_AS_OF_INLINE_RE.search(plain):
        return False, "본문 기준일 메타데이터 (P2)"
    if "시스템 점검" in plain and ("☎" in plain or "044-" in plain):
        return False, "점검·문의 페이지 잔여 (P2)"

    if body_has_exposed_urls(plain):
        return False, "본문 URL 노출 (P3)"

    if NUMBERED_PARA_RE.search(paras[0] if paras else "") or any(
        NUMBERED_PARA_RE.search(p) for p in paras[1:3]
    ):
        return False, "번호 문단 잔여 (P3)"

    ok_lead, lead_msg = validate_para1_lead(paras, packet, article)
    if not ok_lead:
        return False, f"리드 부족 (P5): {lead_msg}"

    if paras and ("NGO 업무" in paras[0] or "업무 메모" in paras[0]):
        return False, "NGO 메모형 리드 (P5)"

    if len(paras) >= 4:
        if is_publish_boilerplate_para4(paras[3]):
            return False, "템플릿 한계·출처 문구 (P6)"
        ok_lim, lim_msg = validate_limitation_paragraph(
            paras[3], paras[2] if len(paras) >= 3 else None
        )
        if not ok_lim:
            return False, f"다만 문단 부족 (P6): {lim_msg}"

    footer = packet.get("sources_footer") or []
    ru = packet.get("reader_utility") or {}
    required_urls = [
        (link.get("url") or "").strip()
        for link in (ru.get("primary_links") or [])
        if (link.get("url") or "").strip()
    ]
    footer_urls = {(f.get("url") or "").strip() for f in footer}
    for url in required_urls:
        if url and url not in footer_urls:
            return False, f"출처 footer 누락: {url} (P4)"

    return True, "OK"


def score_article_voice(plain: str, paras: list[str]) -> tuple[float, list[str]]:
    """0–10: news tone, no briefing openers (v4 article_voice)."""
    score = 10.0
    gaps: list[str] = []
    for phrase in BRIEFING_PHRASES:
        if phrase in plain:
            score -= 3.0
            gaps.append(f"브리핑체: {phrase}")
    if PRESS_RELEASE_PASTE.search(plain):
        score -= 2.0
        gaps.append("보도자료 원문 표기")
    if plain.count("연대·보고") > 1:
        score -= 2.0
        gaps.append("연대 오프너 반복")
    return max(0.0, score), gaps


def score_prose_cleanliness(plain: str, paras: list[str]) -> tuple[float, list[str]]:
    """0–10: no URLs in body, no numbered para junk (v4 prose_cleanliness)."""
    score = 10.0
    gaps: list[str] = []
    if body_has_exposed_urls(plain):
        score -= 5.0
        gaps.append("본문 URL 노출")
    for p in paras[:4]:
        if NUMBERED_PARA_RE.search(p):
            score -= 2.0
            gaps.append("번호 문단 잔여")
            break
    return max(0.0, score), gaps


def score_lead_quality(
    paras: list[str],
    packet: dict[str, Any],
    article: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    ok, msg = validate_para1_lead(paras, packet, article)
    if ok:
        return 10.0, []
    return 5.0, [msg]


def article_publish_ready(
    title: str,
    excerpt: str,
    body: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None,
    *,
    score_total: float | None = None,
    target_score: float = 9.5,
) -> dict[str, Any]:
    """Combined v4 publish gate (validate + score threshold)."""
    if is_publish_v4_enabled():
        body, _ = publish_sanitize_body(body, packet, article)
    pub_ok, pub_msg = validate_publish_article(title, excerpt, body, packet, article)
    from engine.pipeline.target_engine import is_target_engine_enabled

    research_ok = True
    force_site = os.environ.get("EDITORIAL_FORCE_SITE", "").strip().upper()
    if is_target_engine_enabled() and force_site != "NN":
        gate = packet.get("research_gate") or {}
        if gate:
            if gate.get("research_insufficient"):
                research_ok = False
            depth = float(gate.get("research_depth") or 0)
            if depth < 7.0:
                research_ok = False

    score_ok = score_total is None or score_total >= target_score
    ready = pub_ok and research_ok and score_ok
    return {
        "article_publish_ready": ready,
        "publish_validation": {"ok": pub_ok, "message": pub_msg},
        "research_ok": research_ok,
        "score_ok": score_ok,
        "score_total": score_total,
        "sources_footer": packet.get("sources_footer") or [],
    }
