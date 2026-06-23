"""Persist editorial quality-loop artifacts (score + compare + scored body)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from engine.pipeline.rewrite_validate import flatten_nested_paragraph_tags, _paragraph_plain_blocks
from research_collector import strip_html_tags

KST = ZoneInfo("Asia/Seoul")


def normalize_ij_body_html(body: str) -> str:
    """Body used for scoring, validation, and reports."""
    flat = flatten_nested_paragraph_tags(body or "")
    paras = _paragraph_plain_blocks(flat)
    if len(paras) >= 4:
        return "".join(f"<p>{p}</p>" for p in paras[:4])
    return flat


def write_editorial_quality_bundle(
    output_dir: Path,
    *,
    ts: str,
    article: dict[str, Any],
    editorial_ctx: Any,
    variant: dict[str, Any],
    score: dict[str, Any],
    ingest_reason: str = "",
    attempt: int = 1,
    image_probe: dict[str, Any] | None = None,
    publish_preflight: dict[str, Any] | None = None,
    site_code: str = "IJ",
    report_label: str = "IJ",
    body_prefix: str = "editorial_ij_body",
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    body_html = normalize_ij_body_html(variant.get("body", ""))
    from engine.pipeline.publish_validate import is_publish_v4_enabled, publish_sanitize_body

    packet = getattr(editorial_ctx, "packet", None) or {} if editorial_ctx is not None else {}
    if is_publish_v4_enabled() and editorial_ctx is not None:
        body_html, _ = publish_sanitize_body(body_html, packet, article)
        from engine.pipeline.publish_validate import article_publish_ready

        publish_gate = article_publish_ready(
            variant.get("title", ""),
            variant.get("excerpt", ""),
            body_html,
            packet,
            article,
            score_total=score.get("total"),
        )
        score["article_publish_ready"] = publish_gate.get("article_publish_ready")
        score["publish_validation"] = publish_gate.get("publish_validation")
        score["sources_footer"] = publish_gate.get("sources_footer")
        if score.get("validation_ok", True) and score.get("total", 0) >= score.get("target", 9.5):
            score["passes"] = bool(publish_gate.get("article_publish_ready"))
    paras = _paragraph_plain_blocks(body_html)

    payload = {
        "generated_kst": datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S"),
        "attempt": attempt,
        "url": article.get("url"),
        "ingest_reason": ingest_reason,
        "title": variant.get("title"),
        "excerpt": variant.get("excerpt"),
        "body_html": body_html,
        "qa_score": variant.get("qa_score"),
        "score": score,
        "image_probe": image_probe,
        "publish_preflight": publish_preflight,
    }
    json_path = output_dir / f"editorial_quality_{ts}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_path = output_dir / "editorial_quality_score.json"
    latest_path.write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")

    compare_path = output_dir / f"editorial_compare_{ts}.md"
    compare_path.write_text(
        _build_compare_markdown(
            article,
            editorial_ctx,
            variant,
            body_html,
            paras,
            score,
            report_label=report_label,
            ingest_reason=ingest_reason,
            attempt=attempt,
            image_probe=image_probe,
            publish_preflight=publish_preflight,
        ),
        encoding="utf-8",
    )

    body_path = output_dir / f"{body_prefix}_{ts}.html"
    body_path.write_text(body_html, encoding="utf-8")

    return {
        "json": str(json_path),
        "compare": str(compare_path),
        "body_html": str(body_path),
        "latest_score": str(latest_path),
    }


def _build_compare_markdown(
    article: dict[str, Any],
    editorial_ctx: Any,
    variant: dict[str, Any],
    body_html: str,
    paras: list[str],
    score: dict[str, Any],
    *,
    report_label: str,
    ingest_reason: str,
    attempt: int,
    image_probe: dict[str, Any] | None = None,
    publish_preflight: dict[str, Any] | None = None,
) -> str:
    packet = editorial_ctx.packet if editorial_ctx else {}
    evidence = editorial_ctx.evidence if editorial_ctx else []
    lines = [
        f"# 원문 vs 패킷 기반 {report_label} 기사 비교 (채점 산출물)",
        "",
        f"- 생성(KST): {datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 시도: {attempt}",
        f"- URL: {article.get('url')}",
        f"- 원문수집: {ingest_reason} | ingest_source: {article.get('ingest_source', '?')}",
        f"- 본문 길이: {len(article.get('body') or '')}자",
        f"- **채점: {score.get('total')} / 10** (목표 {score.get('target')}, "
        f"reader_value≥{score.get('target_reader_value', 9.0)}, "
        f"originality≥{score.get('target_originality', 9.0)}, "
        f"{'통과' if score.get('passes') else '미통과'})",
    ]
    if score.get("briefing_ready") is not None:
        lines.append(f"- **briefing_ready:** {score.get('briefing_ready')}")
    gate = packet.get("research_gate") or {}
    if gate:
        lines.extend(
            [
                f"- **research_depth:** {gate.get('research_depth', '?')} "
                f"(min {gate.get('research_depth_min', '?')})",
                f"- **research_insufficient:** {gate.get('research_insufficient', False)}",
            ]
        )
    lines.append(f"- QA: {variant.get('qa_score')}")
    lines.append(f"- 문단(논리): {len(paras)}")
    if score.get("gaps"):
        lines.append(f"- gaps: {', '.join(score['gaps'])}")
    if image_probe:
        lines.extend(
            [
                f"- **image_probe:** {image_probe.get('status')} "
                f"({len(image_probe.get('candidates') or [])} candidates)",
            ]
        )
        if image_probe.get("selected_url"):
            lines.append(f"- **featured (probe):** {image_probe.get('selected_url')}")
    if publish_preflight:
        lines.extend(
            [
                f"- **layout_type:** {publish_preflight.get('layout_type')}",
                f"- **text_publish_ready:** {publish_preflight.get('text_publish_ready')}",
                f"- **would_publish_api:** {publish_preflight.get('would_publish_api')}",
            ]
        )
        br = publish_preflight.get("blocked_reasons") or []
        if br:
            lines.append(f"- **publish blocked:** {', '.join(br)}")
    discovered = packet.get("discovered_facts") or []
    lines.extend(["", "## 조사에서 확인 (원문에 없음)", ""])
    if discovered:
        for d in discovered[:8]:
            lines.append(f"- [{d.get('role', '?')}] {d.get('fact', '')}")
            lines.append(f"  - 출처: {d.get('source_url', '')}")
    else:
        lines.append("- (없음)")
    jb = packet.get("journalist_brief") or {}
    lines.extend(["", "## 연대 브리프", ""])
    if jb:
        lines.append(f"- lead_question: {jb.get('lead_question', '')}")
        for t in jb.get("reader_tasks") or []:
            lines.append(f"- reader_task: {t}")
        for g in jb.get("coalition_gaps") or []:
            lines.append(f"- coalition_gap: {g}")
    else:
        lines.append("- (없음)")
    ft = packet.get("field_takeaways") or {}
    lines.extend(["", "## NGO·SE 현장 시사점 (패킷)", ""])
    if ft:
        if ft.get("lead_implication"):
            lines.append(f"- lead_implication: {ft['lead_implication']}")
        if ft.get("who_line"):
            lines.append(f"- who: {ft['who_line']}")
        for a in ft.get("action_lines") or []:
            lines.append(f"- action: {a}")
        if ft.get("caution_line"):
            lines.append(f"- caution: {ft['caution_line']}")
    else:
        lines.append("- (없음)")
    if image_probe or publish_preflight:
        lines.extend(["", "## 이미지·발행 프리플라이트 (API 호출 없음)", ""])
        if image_probe:
            lines.append(f"- status: {image_probe.get('status')}")
            lines.append(f"- code: {image_probe.get('code', '')}")
            lines.append(f"- selected: {image_probe.get('selected_url', '')}")
            lines.append(f"- download_ok: {image_probe.get('download_ok')}")
            for c in (image_probe.get("candidates") or [])[:5]:
                lines.append(f"- candidate [{c.get('score')}]: {c.get('url', '')[:120]}")
        if publish_preflight:
            lines.append(f"- layout_type: {publish_preflight.get('layout_type')}")
            lines.append(f"- placement_slot: {publish_preflight.get('placement_slot')}")
            lines.append(f"- text_publish_ready: {publish_preflight.get('text_publish_ready')}")
            lines.append(f"- would_publish_api: {publish_preflight.get('would_publish_api')}")
            lines.append(f"- r2_required_for_erum: {publish_preflight.get('r2_required_for_erum')}")
    lines.extend(["", "## 수집된 증거 (fetch ok, 발췌)", ""])
    ok_ev = [e for e in evidence if e.get("fetch_status") == "ok"]
    for e in ok_ev[:8]:
        ex = (e.get("body_excerpt") or "")[:200]
        lines.append(f"- [{e.get('evidence_type')}] {e.get('title') or e.get('url')}")
        lines.append(f"  - 발췌({len(ex)}자): {ex or '(없음)'}")
    if not ok_ev:
        lines.append("- (없음)")

    lines.extend(
        [
            "",
            "## 원문 (전문)",
            "",
            f"**제목:** {article.get('title')}",
            "",
            (article.get("body") or "")[:6000],
            "",
            "## 리서치 패킷",
            "",
            f"- main_claim: {packet.get('main_claim', '')}",
            f"- key_facts: {packet.get('key_facts', [])}",
            f"- risk_flags: {packet.get('risk_flags', [])}",
            f"- packet_version: {(packet.get('research_meta') or {}).get('packet_version', 1)}",
            "",
            "## reader_utility (패킷 v2)",
            "",
        ]
    )
    ru = packet.get("reader_utility") or {}
    if ru:
        lines.append(f"- as_of_date: {ru.get('as_of_date', '')}")
        for s in (ru.get("scenarios") or [])[:3]:
            lines.append(f"- scenario: {s.get('label', '')}")
        for c in (ru.get("checklist") or [])[:4]:
            lines.append(f"- checklist: {c.get('step', '')}")
        for link in (ru.get("primary_links") or [])[:6]:
            lines.append(f"- link: {link.get('label', '')} → {link.get('url', '')}")
    else:
        lines.append("- (없음)")
    lines.extend(
        [
            "",
            f"## {report_label} 재작성 (채점·검증에 사용한 HTML)",
            "",
            f"**제목:** {variant.get('title', '(없음)')}",
            "",
            f"**리드문:** {variant.get('excerpt', '')}",
            "",
            body_html,
            "",
            f"## {report_label} 본문 (평문 4문단)",
            "",
        ]
    )
    for i, p in enumerate(paras[:4], start=1):
        lines.append(f"{i}. {p}")
    lines.append("")
    return "\n".join(lines)
