"""Weighted editorial quality score (0–10) aligned with human review rubric."""

from __future__ import annotations

import re
from typing import Any

from engine.pipeline.editorial_facts import fact_groups_from_source, key_fact_covered
from engine.pipeline.coalition_brief import assess_briefing_ready
from engine.pipeline.editorial_originality import score_originality_dimension
from engine.pipeline.reader_utility import score_reader_value_dimension
from engine.pipeline.publish_validate import (
    article_publish_ready,
    is_publish_v4_enabled,
    publish_sanitize_body,
    score_article_voice,
    score_lead_quality,
    score_prose_cleanliness,
)
from engine.pipeline.target_engine import is_target_engine_enabled
from engine.pipeline.rewrite_validate import (
    LIMITATION_MARKERS,
    REPEAT_POLICY_TERMS,
    REPEAT_WATCH_PHRASES,
    _is_thin_source,
    _paragraph_plain_blocks,
    _urls_required_from_packet,
    collect_source_fidelity_gaps,
    flatten_nested_paragraph_tags,
    temporal_hint_from_source,
)
from research_collector import strip_html_tags

TARGET_SCORE = 9.5
TARGET_READER_VALUE = 9.0
TARGET_ORIGINALITY = 9.0
TARGET_RESEARCH_DEPTH = 7.0
TARGET_COALITION_BRIEFING = 9.0
MIN_PARAGRAPH_CHARS = 55


def score_editorial_rewrite(
    title: str,
    excerpt: str,
    body: str,
    article: dict[str, Any],
    packet: dict[str, Any],
    *,
    qa_score: int | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_body = (article or {}).get("body") or ""
    raw_body = body or ""
    # Detect nested <p> on the rewrite input before v4 sanitize flattens it.
    had_nested_p = bool(re.search(r"<p[^>]*>\s*<p", raw_body, flags=re.IGNORECASE))
    if is_publish_v4_enabled():
        raw_body, _ = publish_sanitize_body(raw_body, packet, article)
        body_norm = flatten_nested_paragraph_tags(raw_body)
        plain_probe = re.sub(r"\s+", " ", strip_html_tags(body_norm)).strip()
        if "연대·보고" in plain_probe:
            raw_body, _ = publish_sanitize_body(raw_body, packet, article)
    body_norm = flatten_nested_paragraph_tags(raw_body)
    paras = _paragraph_plain_blocks(body_norm)
    p_count = len(paras)
    plain = re.sub(r"\s+", " ", strip_html_tags(body_norm)).strip()
    gaps: list[str] = []

    # --- structure (0–10) ---
    structure = 10.0
    if p_count < 4:
        structure -= 3.0
        gaps.append(f"문단 {p_count}개 (4개 필요)")
    if had_nested_p:
        structure -= 2.0
        gaps.append("중첩 p 태그")
    short = [i + 1 for i, p in enumerate(paras[:4]) if len(p) < MIN_PARAGRAPH_CHARS]
    if short:
        structure -= min(2.0, 0.5 * len(short))
        gaps.append(f"짧은 문단: {short}")
    if len(paras) >= 4:
        from engine.pipeline.ij_paragraph_roles import BG_PARA2_KEYS, MECH_STRUCTURE_KEYS

        mech_in_2 = any(k in paras[1] for k in MECH_STRUCTURE_KEYS)
        mech_in_3 = any(k in paras[2] for k in MECH_STRUCTURE_KEYS)
        para2_has_bg = any(k in paras[1] for k in BG_PARA2_KEYS)
        if not mech_in_2 and not para2_has_bg:
            structure -= 1.5
            gaps.append("2문단 배경·문제 약함")
        elif para2_has_bg and not mech_in_2 and _is_thin_source(article or {}, packet):
            allow_blob = " ".join(
                [
                    source_body,
                    " ".join(str(x) for x in (packet.get("key_facts") or [])),
                    str(packet.get("main_claim") or ""),
                ]
            )
            invented_bg = any(
                term in paras[1]
                for term in ("슈링크플레이션", "인플레이션", "물가 급등", "물가급등")
            ) and not any(
                term in allow_blob
                for term in ("슈링크플레이션", "인플레이션", "물가 급등", "물가급등")
            )
            if invented_bg:
                structure -= 1.5
                gaps.append("2문단 근거 없는 배경")
        if not (mech_in_2 or mech_in_3):
            structure -= 1.5
            gaps.append("해법 문단 작동 구조 약함")
        if not paras[3].strip().startswith("다만") and not any(
            m in paras[3] for m in LIMITATION_MARKERS
        ):
            structure -= 2.0
            gaps.append("4문단 한계·조건 약함")
        if paras[0] and "그동안" in paras[0]:
            structure -= 0.5
            gaps.append("1문단에 배경 혼입")
    structure = max(0.0, structure)

    # --- facts (0–10) ---
    facts = 10.0
    missing_labels: list[str] = []
    for label, alts in fact_groups_from_source(source_body):
        if not any(alt in plain for alt in alts):
            missing_labels.append(label)
    if missing_labels:
        facts -= min(5.0, 1.2 * len(missing_labels))
        gaps.append("원문 핵심 누락: " + ", ".join(missing_labels))
    kf = packet.get("key_facts") or []
    if kf:
        covered = sum(1 for f in kf[:4] if key_fact_covered(f, plain))
        if covered < min(3, len(kf)):
            facts -= 1.5
            gaps.append("key_facts 반영 부족")
    fidelity_gaps = collect_source_fidelity_gaps(
        title, body_norm, article, excerpt=excerpt or "", packet=packet
    )
    if fidelity_gaps:
        facts -= min(3.0, 1.0 * len(fidelity_gaps))
        gaps.extend(f"fidelity: {g}" for g in fidelity_gaps)
    facts = max(0.0, facts)

    # --- utility (0–10) ---
    utility = 10.0
    if not is_publish_v4_enabled():
        for host in _urls_required_from_packet(packet):
            if host not in plain.lower():
                utility -= 2.5
                gaps.append(f"URL 누락: {host}")
        if not re.search(r"https?://", plain):
            utility -= 1.0
    utility = max(0.0, utility)

    # --- editorial (0–10) ---
    editorial = 10.0
    hint = temporal_hint_from_source(source_body)
    if hint.startswith("다음 달") and re.search(r"이달부터", plain):
        editorial -= 2.0
        gaps.append("시점 혼용")
    for phrase in REPEAT_WATCH_PHRASES:
        if plain.count(phrase) > 2:
            editorial -= 1.0
            gaps.append(f"반복: {phrase}")
    for phrase in REPEAT_POLICY_TERMS:
        if plain.count(phrase) > 4:
            editorial -= 0.5
    if "official_evidence_missing" in (packet.get("risk_flags") or []):
        if not any(m in plain for m in LIMITATION_MARKERS):
            editorial -= 2.5
            gaps.append("한계 서술 없음")
    ev_ok = sum(1 for e in (evidence or []) if e.get("fetch_status") == "ok")
    if ev_ok < 1:
        editorial -= 0.5
    editorial = max(0.0, editorial)

    # --- reader_value (0–10) ---
    reader_value, reader_gaps = score_reader_value_dimension(packet, plain)
    gaps.extend(reader_gaps)

    # --- originality (0–10): 재구성·독자 관점 (환각 없는 범위) ---
    originality, originality_gaps = score_originality_dimension(packet, plain, source_body)
    gaps.extend(originality_gaps)

    # --- qa proxy (0–10) ---
    qa_dim = 8.0
    if qa_score is not None:
        qa_dim = min(10.0, max(0.0, qa_score / 13.0))

    research_dim = 10.0
    coalition_dim = 10.0
    article_voice = 10.0
    lead_quality = 10.0
    prose_cleanliness = 10.0
    if is_target_engine_enabled():
        gate = packet.get("research_gate") or {}
        depth = float(gate.get("research_depth") or (packet.get("research_meta") or {}).get("research_depth") or 0)
        research_dim = min(10.0, depth)
        if depth < TARGET_RESEARCH_DEPTH:
            gaps.append(f"research_depth {depth} < {TARGET_RESEARCH_DEPTH}")
        discovered = packet.get("discovered_facts") or []
        if is_publish_v4_enabled():
            article_voice, av_gaps = score_article_voice(plain, paras)
            gaps.extend(av_gaps)
            lead_quality, lq_gaps = score_lead_quality(paras, packet, article)
            gaps.extend(lq_gaps)
            prose_cleanliness, pc_gaps = score_prose_cleanliness(plain, paras)
            gaps.extend(pc_gaps)
            br = assess_briefing_ready(packet, discovered, body_plain=plain, paras=paras)
            checks = br.get("checks") or {}
            if not checks.get("discovered_min"):
                facts -= 1.0
            total = (
                article_voice * 0.22
                + lead_quality * 0.15
                + structure * 0.12
                + facts * 0.15
                + prose_cleanliness * 0.12
                + editorial * 0.08
                + utility * 0.08
                + originality * 0.08
                + research_dim * 0.05
                + qa_dim * 0.05
            )
        else:
            br = assess_briefing_ready(packet, discovered, body_plain=plain, paras=paras)
            checks = br.get("checks") or {}
            coalition_dim = 10.0 if br.get("briefing_ready") else 5.0
            if not br.get("briefing_ready"):
                coalition_dim = max(0.0, 10.0 - 2.5 * len(br.get("fail_reasons") or []))
                gaps.append("briefing_not_ready: " + ", ".join(br.get("fail_reasons") or []))
            if not checks.get("discovered_min"):
                facts -= 1.0
            total = (
                structure * 0.18
                + facts * 0.18
                + utility * 0.10
                + editorial * 0.10
                + reader_value * 0.08
                + originality * 0.08
                + coalition_dim * 0.10
                + research_dim * 0.10
                + qa_dim * 0.08
            )
    else:
        total = (
            structure * 0.22
            + facts * 0.22
            + utility * 0.14
            + editorial * 0.14
            + reader_value * 0.09
            + originality * 0.09
            + qa_dim * 0.10
        )
    total = round(min(10.0, total), 2)
    fidelity_ok = not fidelity_gaps
    form_score = total

    passes_score = (
        total >= TARGET_SCORE
        and reader_value >= TARGET_READER_VALUE
        and originality >= TARGET_ORIGINALITY
    )
    publish_gate: dict[str, Any] | None = None
    if is_target_engine_enabled():
        if is_publish_v4_enabled():
            publish_gate = article_publish_ready(
                title,
                excerpt,
                body_norm,
                packet,
                article,
                score_total=total,
            )
            passes_score = bool(publish_gate.get("article_publish_ready"))
        else:
            passes_score = (
                passes_score
                and research_dim >= TARGET_RESEARCH_DEPTH
                and coalition_dim >= TARGET_COALITION_BRIEFING
                and not (packet.get("research_gate") or {}).get("research_insufficient")
            )
    passes_score = bool(passes_score and fidelity_ok)

    dims = {
        "structure": round(structure, 2),
        "facts": round(facts, 2),
        "utility": round(utility, 2),
        "editorial": round(editorial, 2),
        "reader_value": round(reader_value, 2),
        "originality": round(originality, 2),
        "qa_proxy": round(qa_dim, 2),
    }
    if is_target_engine_enabled():
        dims["research_depth"] = round(research_dim, 2)
        if is_publish_v4_enabled():
            dims["article_voice"] = round(article_voice, 2)
            dims["lead_quality"] = round(lead_quality, 2)
            dims["prose_cleanliness"] = round(prose_cleanliness, 2)
        else:
            dims["coalition_briefing"] = round(coalition_dim, 2)

    result = {
        "publish_body": body_norm if is_publish_v4_enabled() else body,
        "total": total,
        "form_score": form_score,
        "fidelity_ok": fidelity_ok,
        "fidelity_gaps": list(fidelity_gaps),
        "target": TARGET_SCORE,
        "target_reader_value": TARGET_READER_VALUE,
        "target_originality": TARGET_ORIGINALITY,
        "target_research_depth": TARGET_RESEARCH_DEPTH if is_target_engine_enabled() else None,
        "target_coalition_briefing": TARGET_COALITION_BRIEFING if is_target_engine_enabled() else None,
        "passes": passes_score,
        "briefing_ready": (
            assess_briefing_ready(
                packet,
                packet.get("discovered_facts") or [],
                body_plain=plain,
                paras=paras,
            ).get("briefing_ready")
            if is_target_engine_enabled()
            else None
        ),
        "dimensions": dims,
        "gaps": gaps,
        "paragraph_count": p_count,
        "scored_body_normalized": True,
    }
    if publish_gate is not None:
        result["article_publish_ready"] = publish_gate.get("article_publish_ready")
        result["publish_validation"] = publish_gate.get("publish_validation")
        result["sources_footer"] = publish_gate.get("sources_footer")
    return result
