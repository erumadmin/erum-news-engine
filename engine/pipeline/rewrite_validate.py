"""Deterministic checks for IJ editorial hybrid rewrites (post-LLM)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from research_collector import strip_html_tags

IJ_REQUIRED_PARAGRAPH_COUNT = 4
LIMITATION_MARKERS = ("다만", "한계", "조건", "유의", "아직", "남은")
REPEAT_WATCH_PHRASES = ("자동 적용", "유리한 요금", "자동으로", "비교 분석", "비교분석")
REPEAT_MAX_TOTAL = 4
REPEAT_POLICY_TERMS = ("6개월",)


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


def _paragraph_plain_blocks(body: str) -> list[str]:
    blocks = re.findall(r"<p[^>]*>(.*?)</p>", body or "", flags=re.IGNORECASE | re.DOTALL)
    if blocks:
        return [strip_html_tags(b).strip() for b in blocks if strip_html_tags(b).strip()]
    plain = strip_html_tags(body or "")
    return [p.strip() for p in re.split(r"\n{2,}", plain) if p.strip()]


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

    paragraph_count = len(re.findall(r"<p\b", body, flags=re.IGNORECASE))
    if not paragraph_count:
        paragraph_count = len(_paragraph_plain_blocks(body))
    if paragraph_count < IJ_REQUIRED_PARAGRAPH_COUNT:
        return False, f"문단 수 부족({paragraph_count}개, IJ 4문단 필요)"

    source_text = (article or {}).get("body") or ""
    body = normalize_temporal_in_body(body, source_text)
    plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()
    hint = temporal_hint_from_source(source_text) or temporal_hint_from_source(plain)

    if hint.startswith("다음 달") and re.search(r"이달부터|이번 달부터", plain):
        return False, "시점 표기 불일치(이달/다음 달 혼용)"

    for host in _urls_required_from_packet(packet):
        if host not in plain.lower() and host.replace("www.", "") not in plain.lower():
            return False, f"독자 확인 URL 누락({host})"

    for phrase in REPEAT_WATCH_PHRASES:
        if plain.count(phrase) > 2:
            return False, f"반복 과다({phrase})"
    for phrase in REPEAT_POLICY_TERMS:
        if plain.count(phrase) > REPEAT_MAX_TOTAL:
            return False, f"반복 과다({phrase})"

    risk_flags = packet.get("risk_flags") or []
    if "official_evidence_missing" in risk_flags:
        paras = _paragraph_plain_blocks(body)
        if paras:
            last = paras[-1]
            if not any(m in last for m in LIMITATION_MARKERS):
                return False, "4문단 한계·조건 서술 부족"

    if not title or len(title.strip()) < 5:
        return False, "제목 누락 또는 너무 짧음"

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


def build_rewrite_correction_suffix(error_message: str) -> str:
    return (
        f"\n\n[수정 요청] 이전 출력이 규칙을 어겼습니다: {error_message}\n"
        "반드시 수정: (1) 본문은 <p> 태그 정확히 4개 "
        "(2) 마지막 <p>에 다만/조건/한계 "
        "(3) action_items URL 전부 포함 "
        "(4) 시점 표기 하나로 통일 "
        "(5) 같은 기간·절차 표현은 2회 이하."
    )
