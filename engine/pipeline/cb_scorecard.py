"""CSR Briefing editorial quality scorecard."""

from __future__ import annotations

import re
from typing import Any

from engine.pipeline.cb_packet_writer import is_cb_publish_v4_enabled
from engine.pipeline.cb_rewrite_validate import validate_cb_paragraph_roles
from engine.pipeline.editorial_facts import fact_groups_from_source, key_fact_covered
from engine.pipeline.editorial_originality import score_originality_dimension
from engine.pipeline.reader_utility import score_reader_value_dimension
from engine.pipeline.rewrite_validate import _paragraph_plain_blocks, flatten_nested_paragraph_tags
from research_collector import strip_html_tags

TARGET_SCORE = 9.5
TARGET_BUSINESS_AXES = 7.0
TARGET_READER_VALUE = 8.0
TARGET_ORIGINALITY = 8.0
MIN_PARAGRAPH_CHARS = 55


def _brief_reflected(needle: str, plain: str, *, min_chars: int = 12) -> bool:
    text = (needle or "").strip()
    if not text:
        return False
    if text in plain:
        return True
    # Soft match: significant token overlap (avoid exact long-line requirement)
    tokens = [t for t in re.split(r"[\s,·./]+", text) if len(t) >= 2][:8]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in plain)
    return hits >= max(2, min(4, len(tokens) // 2)) and len(text) >= min_chars


def score_business_axes(packet: dict[str, Any], plain: str) -> tuple[float, list[str]]:
    brief = packet.get("compliance_brief") or {}
    gaps: list[str] = []
    score = 10.0

    who_ok = any(
        item and (item in plain or any(tok in plain for tok in re.split(r"[\s·]+", item) if len(tok) >= 2))
        for item in brief.get("who_affected") or []
    ) or any(k in plain for k in ("사업주", "기업", "사업자", "상장사"))
    checks = {
        "who_affected": who_ok,
        "business_change": _brief_reflected(str(brief.get("business_change") or ""), plain),
        "check_items": any(_brief_reflected(str(item), plain) for item in brief.get("check_items") or [])
        or any(k in plain for k in ("점검", "확인", "적용", "고시", "과태료")),
        "remaining_limits": any(_brief_reflected(str(item), plain) for item in brief.get("remaining_limits") or [])
        or any(k in plain for k in ("유예", "예외", "미정", "고시", "미만")),
    }
    labels = {
        "who_affected": "영향받는 기업/실무자",
        "business_change": "실무 변화",
        "check_items": "확인 절차",
        "remaining_limits": "남은 제한",
    }
    for key, ok in checks.items():
        if not ok:
            score -= 1.5
            gaps.append(labels[key])
    return max(0.0, score), gaps


def score_cb_editorial_rewrite(
    title: str,
    excerpt: str,
    body: str,
    article: dict[str, Any],
    packet: dict[str, Any],
    *,
    qa_score: int | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_body = body or ""
    publish_body = raw_body
    sources_footer: list[dict[str, str]] = []

    if is_cb_publish_v4_enabled():
        from engine.pipeline.publish_validate import publish_sanitize_body

        publish_body, sources_footer = publish_sanitize_body(raw_body, packet, article)
        if sources_footer:
            packet = {**packet, "sources_footer": sources_footer}

    body_norm = flatten_nested_paragraph_tags(publish_body)
    paras = _paragraph_plain_blocks(body_norm)
    plain = re.sub(r"\s+", " ", strip_html_tags(body_norm)).strip()
    gaps: list[str] = []

    structure = 10.0
    if len(paras) < 4:
        structure -= 3.0
        gaps.append(f"문단 {len(paras)}개")
    short = [i + 1 for i, p in enumerate(paras[:4]) if len(p) < MIN_PARAGRAPH_CHARS]
    if short:
        structure -= min(2.0, 0.5 * len(short))
        gaps.append(f"짧은 문단: {short}")
    ok_roles, role_msg = validate_cb_paragraph_roles(paras)
    if not ok_roles:
        structure -= 2.0
        gaps.append(role_msg)

    business_score, business_gaps = score_business_axes(packet, plain)
    if business_gaps:
        gaps.extend(business_gaps)

    reader_score, rv_gaps = score_reader_value_dimension(packet, plain)
    if rv_gaps:
        gaps.extend(rv_gaps)

    orig_score, orig_gaps = score_originality_dimension(packet, plain, article.get("body") or "")
    if orig_gaps:
        gaps.extend(orig_gaps)

    fact_score = 10.0
    groups = fact_groups_from_source(article.get("body") or "")
    uncovered = [
        label
        for label, alts in groups
        if not any(key_fact_covered(alt, plain) for alt in alts)
    ]
    if uncovered:
        fact_score -= min(4.0, len(uncovered) * 1.5)
        gaps.append(f"fact 미반영: {', '.join(uncovered[:3])}")

    voice = 10.0
    if re.search(r"https?://|www\.", plain, re.I):
        voice -= 2.0
        gaps.append("본문 URL 노출")
    if not paras or not any(
        key in paras[0]
        for key in ("기업", "상장사", "협력사", "실무자", "공급망", "ESG", "사업주", "사업자", "물류", "공장")
    ):
        voice -= 2.0
        gaps.append("기업 실무 리드 부족")

    weights = {
        "structure": 0.15,
        "business_axes": 0.25,
        "reader_value": 0.15,
        "originality": 0.15,
        "fact_coverage": 0.15,
        "voice": 0.15,
    }
    dimensions = {
        "structure": round(max(0.0, structure), 2),
        "business_axes": round(business_score, 2),
        "reader_value": round(reader_score, 2),
        "originality": round(orig_score, 2),
        "fact_coverage": round(max(0.0, fact_score), 2),
        "voice": round(max(0.0, voice), 2),
    }
    total = sum(dimensions[k] * weights[k] for k in weights)

    passes = (
        total >= TARGET_SCORE
        and business_score >= TARGET_BUSINESS_AXES
        and reader_score >= TARGET_READER_VALUE
        and orig_score >= TARGET_ORIGINALITY
        and len(paras) >= 4
    )

    article_publish_ready_flag = passes
    publish_validation: dict[str, Any] = {}
    if is_cb_publish_v4_enabled():
        from engine.pipeline.publish_validate import article_publish_ready

        gate = article_publish_ready(
            title,
            excerpt,
            publish_body,
            packet,
            article,
            score_total=round(total, 2),
        )
        article_publish_ready_flag = bool(gate.get("article_publish_ready"))
        publish_validation = gate.get("publish_validation") or {}
        if not article_publish_ready_flag:
            msg = publish_validation.get("message") or "publish_v4_gate"
            gaps.append(str(msg))
        passes = bool(passes and article_publish_ready_flag)

    return {
        "total": round(total, 2),
        "dimensions": dimensions,
        "gaps": list(dict.fromkeys(gaps)),
        "passes": passes,
        "publish_body": publish_body,
        "sources_footer": sources_footer,
        "article_publish_ready": article_publish_ready_flag,
        "publish_validation": publish_validation,
        "target_business_axes": TARGET_BUSINESS_AXES,
        "target_reader_value": TARGET_READER_VALUE,
        "target_originality": TARGET_ORIGINALITY,
        "qa_score": qa_score,
    }
