"""Originality rubric: editorial added value without new facts (source + packet only)."""

from __future__ import annotations

import re
from typing import Any

from engine.pipeline.editorial_facts import key_fact_covered
from engine.pipeline.reader_utility import (
    _checklist_reflected,
    _scenario_reflected,
    _url_reflected_in_plain,
)

COMPARISON_CUES = ("비교", "각각", "표기", "고지서", "두 요금", "요금을")
PROCEDURE_CUES = (
    "공개",
    "알리",
    "고지",
    "협약",
    "시행",
    "의무",
    "축소",
    "변경",
    "지정",
    "수립",
    "도입",
    "고시",
    "확정",
)
SCENARIO_MARKERS = ("예를 들어", "반면", "반대로", "업종 특성", "업종은", "카페", "음식점")
SCENARIO_CONTRAST_MARKERS = ("예를 들어", "반면", "반대로", "유리", "다르", "집중")


def source_has_scenario_material(source_body: str) -> bool:
    return any(m in (source_body or "") for m in SCENARIO_MARKERS)


def comparison_cues_for_source(source_body: str) -> list[str]:
    body = source_body or ""
    cues = [c for c in COMPARISON_CUES if c in body]
    if cues:
        return cues
    return [c for c in PROCEDURE_CUES if c in body]


def build_originality_guidance(packet: dict[str, Any], source_body: str) -> str:
    """Rewrite prompt hints — only from packet / source."""
    ru = packet.get("reader_utility") or {}
    lines = [
        "아래는 독창성(원문 재구성·독자 관점) 힌트다. 원문·패킷에 없는 수치·표·FAQ는 쓰지 않는다.",
    ]
    scenarios = ru.get("scenarios") or []
    if scenarios:
        lines.append(f"- 시나리오 대비 1줄(3문단): {scenarios[0].get('body', '')[:120]}")
    elif source_has_scenario_material(source_body):
        lines.append("- 시나리오: 원문 예시·대비 문장을 3문단에 1줄로 풀기")
    else:
        lines.append("- 누가·무엇이 바뀌는지(1문단)와 확인 경로(3문단)를 분리해 서술")

    checklist = ru.get("checklist") or []
    n_check = min(3, max(2, len(checklist) or 2))
    if checklist:
        lines.append(f"- 체크리스트 {n_check}항(3문단, 번호 없이):")
        for c in checklist[:3]:
            lines.append(f"  · {c.get('step', '')[:100]}")
    else:
        lines.append("- 원문의 시점·고지·공개·선택 문장을 2~3개 행동으로 녹인다.")

    links = ru.get("primary_links") or []
    if links:
        lines.append("- 링크: 보도자료(또는 공식 보도) + 독자 확인 URL을 3문단에 명시")
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    as_of = ru.get("as_of_date") or ""
    if as_of and not is_publish_v4_enabled():
        lines.append(f"- 기준일: {as_of} (4문단에 '기준'과 날짜)")
    elif as_of and is_publish_v4_enabled():
        lines.append("- 기준일은 본문에 쓰지 않는다 (시스템 footer만)")

    cues = comparison_cues_for_source(source_body)
    if cues:
        lines.append(
            f"- 원문 절차·비교 서술: '{cues[0]}' 등 원문 표현만 (표/수치는 원문에 있을 때만)"
        )
    return "\n".join(lines)


def _checklist_required_count(packet: dict[str, Any], source_body: str) -> int:
    ru = packet.get("reader_utility") or {}
    checklist = ru.get("checklist") or []
    if len(source_body or "") < 500:
        return min(3, max(2, len(checklist)))
    return min(3, max(2, len(checklist) or 3))


def _scenario_score(plain: str, packet: dict[str, Any], source_body: str) -> tuple[float, str | None]:
    ru = packet.get("reader_utility") or {}
    scenarios = list(ru.get("scenarios") or [])
    if not scenarios and source_body:
        from engine.pipeline.reader_utility import extract_scenarios

        scenarios = extract_scenarios(source_body)
    if scenarios:
        if not any(_scenario_reflected(s, plain) for s in scenarios):
            return 0.0, "시나리오 미반영"
        return 2.0, None

    if source_has_scenario_material(source_body):
        if any(m in plain for m in SCENARIO_MARKERS) and (
            "유리" in plain or "반면" in plain or "다르" in plain
        ):
            return 2.0, None
        if any(m in plain for m in SCENARIO_MARKERS):
            return 1.0, "시나리오 대비 약함"
        return 0.0, "시나리오 대비 미흡"

    # 원문에 예시가 없는 짧은 보도: 변화·확인 경로 재구성
    kf = packet.get("key_facts") or []
    kf_hits = sum(1 for f in kf[:4] if key_fact_covered(f, plain))
    if kf_hits >= 2 and re.search(r"https?://", plain) and any(
        k in plain for k in ("시행", "대상", "적용", "공개", "알리")
    ):
        return 2.0, None
    if kf_hits >= 1:
        return 1.0, "독자 관점 재구성 약함"
    return 0.0, "독자 관점 재구성 미흡"


def _checklist_score(plain: str, packet: dict[str, Any], source_body: str) -> tuple[float, str | None]:
    required = _checklist_required_count(packet, source_body)
    ru = packet.get("reader_utility") or {}
    checklist = list(ru.get("checklist") or [])
    if len(checklist) < 2 and source_body:
        from engine.pipeline.reader_utility import extract_checklist

        checklist = extract_checklist(source_body)
    hits = sum(1 for c in checklist if _checklist_reflected(c, plain))
    if hits >= required:
        return 2.0, None
    temporal = [t for t in re.findall(r"\d{1,2}월|\d+개월", source_body) if t in source_body]
    if len(temporal) >= required and sum(1 for t in temporal if t in plain) >= required:
        return 2.0, None
    action_hits = sum(
        1
        for kw in ("고지", "선택", "확인", "신청", "표기", "공개", "알리")
        if kw in plain and kw in source_body
    )
    if hits >= required - 1 and action_hits >= required:
        return 1.0, "체크리스트 일부 미흡"
    return 0.0, "체크리스트 미흡"


def _confirmation_score(plain: str, packet: dict[str, Any]) -> tuple[float, str | None]:
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    ru = packet.get("reader_utility") or {}
    as_of = (ru.get("as_of_date") or "").strip()
    if is_publish_v4_enabled():
        footer = packet.get("sources_footer") or []
        footer_urls = {(f.get("url") or "").strip() for f in footer if (f.get("url") or "").strip()}
        links = ru.get("primary_links") or []
        required = [(link.get("url") or "").strip() for link in links if (link.get("url") or "").strip()]
        if required and all(url in footer_urls for url in required):
            return 2.0, None
        if footer_urls and any("korea.kr" in u for u in footer_urls):
            return 2.0, None
        if footer_urls:
            return 1.0, "기준일·링크 묶음 약함"
        return 0.0, "기준일·링크 묶음 미흡"

    has_as_of = bool(as_of and (as_of in plain or "기준" in plain))
    links = ru.get("primary_links") or []
    reflected = sum(1 for link in links if _url_reflected_in_plain(link.get("url") or "", plain))
    has_announcement = (
        "korea.kr" in plain.lower()
        or ("보도자료" in plain and "기준" in plain)
        or ("공식" in plain and "기준" in plain)
    )
    has_reader = reflected >= 1 or any(
        x in plain.lower()
        for x in ("kepco", "price.go.kr", "en-ter", "ftc.go.kr", "go.kr")
    )
    if has_as_of and has_announcement and reflected >= 2:
        return 2.0, None
    if has_as_of and has_reader and (has_announcement or reflected >= 1):
        return 2.0, None
    if has_as_of and has_reader:
        return 1.0, "기준일·링크 묶음 약함"
    return 0.0, "기준일·링크 묶음 미흡"


def _comparison_score(plain: str, source_body: str) -> tuple[float, str | None]:
    cues = comparison_cues_for_source(source_body)
    if not cues:
        if any(k in plain for k in ("협약", "시행", "공개")) and any(
            k in source_body for k in ("협약", "시행", "공개")
        ):
            return 2.0, None
        return 1.0, None
    hits = sum(1 for c in cues if c in plain)
    if hits >= 1:
        return 2.0, None
    return 0.0, "비교·절차 서술 미흡"


def _reframe_score(
    plain: str,
    source_body: str,
    *,
    para1: str | None = None,
    lead_line: str = "",
) -> tuple[float, str | None]:
    """Lead/opening not a verbatim copy of source first chunk."""
    check = (para1 if para1 is not None else plain) or ""
    lead_line = (lead_line or "").strip()
    if lead_line and check.startswith(lead_line[: min(28, len(lead_line))]):
        return 2.0, None
    src = re.sub(r"\s+", " ", (source_body or "").strip())
    if len(src) < 40:
        return 2.0, None
    head = src[:80]
    window = check[:220] if para1 is not None else plain[:200]
    if head not in check and src[:50] not in check:
        return 2.0, None
    business_reframe_markers = ("기업", "실무", "공급망", "협력사", "투자", "상장사", "기관")
    if src[:35] in window and any(marker in window for marker in business_reframe_markers):
        return 2.0, None
    if src[:35] not in window:
        return 1.0, "리드 재구성 약함"
    return 0.0, "원문 첫 문장 복사에 가까움"


def _hallucination_penalty(plain: str, source_body: str) -> float:
    penalty = 0.0
    src_billion = set(re.findall(r"\d+\s*억", source_body))
    body_billion = set(re.findall(r"\d+\s*억", plain))
    if body_billion - src_billion:
        penalty += 2.0
    src_months = set(re.findall(r"\d{1,2}월", source_body))
    extra_months = set(re.findall(r"\d{1,2}월", plain)) - src_months
    if len(extra_months) > 2:
        penalty += 1.0
    if (
        "표" in plain
        and "표" not in source_body
        and "표기" not in source_body
        and "비교표" not in plain
    ):
        penalty += 1.0
    for term in ("슈링크플레이션", "인플레이션", "물가급등", "물가 급등"):
        if term in plain and term not in (source_body or ""):
            # Compact-space variant for 물가 급등
            if term == "물가 급등" and "물가급등" in (source_body or ""):
                continue
            if term == "물가급등" and "물가 급등" in (source_body or ""):
                continue
            penalty += 2.0
            break
    return penalty


def score_originality_dimension(
    packet: dict[str, Any],
    plain: str,
    source_body: str,
) -> tuple[float, list[str]]:
    """
    0–10: 5 buckets × 0–2 (partial 1 allowed → 9.0 achievable).

    시나리오 대비 또는(원문 무예시 시) 독자 관점 재구성
    체크리스트 (원문 길이에 따라 2~3항)
    기준일 + 링크 묶음
    원문 비교·절차 서술
    리드 재구성(원문 첫 문장 복사 회피)
    """
    gaps: list[str] = []
    score = 0.0

    from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

    paras = _paragraph_plain_blocks(plain)
    if len(paras) <= 1 and len(plain) > 120:
        parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", plain.strip())
        p1 = " ".join(parts[:2]) if parts else plain[:220]
    else:
        p1 = paras[0] if paras else plain[:220]
    lead_line = ((packet.get("field_takeaways") or {}).get("lead_line") or "").strip()

    for points, gap in (
        _scenario_score(plain, packet, source_body),
        _checklist_score(plain, packet, source_body),
        _confirmation_score(plain, packet),
        _comparison_score(plain, source_body),
        _reframe_score(plain, source_body, para1=p1, lead_line=lead_line),
    ):
        score += points
        if gap:
            gaps.append(gap)

    penalty = _hallucination_penalty(plain, source_body)
    if penalty:
        score -= penalty
        gaps.append("원문 없는 수치·표현 의심")

    return max(0.0, min(10.0, score)), gaps


def reframe_para1_against_source(
    paras: list[str],
    packet: dict[str, Any],
    source_body: str,
) -> list[str]:
    """When para1 copies source opener, prepend coalition lead or drop duplicate sentence."""
    if not paras:
        return paras
    src = re.sub(r"\s+", " ", (source_body or "").strip())
    if len(src) < 40:
        return paras
    p0 = (paras[0] or "").strip()
    if src[:50] not in p0 and src[:35] not in p0[:200]:
        return paras
    ft = packet.get("field_takeaways") or {}
    lead = (ft.get("lead_line") or "").strip()
    main = (packet.get("main_claim") or "").strip()
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if lead:
        opener = lead
    elif main and is_publish_v4_enabled():
        opener = f"{main[:120].rstrip('.')}."
    elif main:
        opener = f"연대·보고 관점에서 {main[:120].rstrip('.')}."
    else:
        opener = ""
    if opener and not opener.startswith(src[:20]):
        from engine.pipeline.coalition_takeaways import sanitize_para1_coalition

        raw = packet.get("_raw_source") or {}
        trimmed = p0
        if src[:40] in trimmed:
            trimmed = trimmed.replace(src[: min(80, len(src))], "", 1).strip()
        paras[0] = sanitize_para1_coalition(
            f"{opener} {trimmed}".strip() if trimmed else opener,
            lead or opener,
            raw,
        )
    return paras


def inject_originality_anchors(
    body: str,
    packet: dict[str, Any],
    source_body: str,
) -> str:
    """Finalize: inject source-backed originality elements (all article types)."""
    from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

    paras = _paragraph_plain_blocks(body)
    if len(paras) < 4:
        return body
    paras = reframe_para1_against_source(paras, packet, source_body)
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    if is_publish_v4_enabled():
        return "".join(f"<p>{p}</p>" for p in paras[:4])

    plain = " ".join(paras)
    ru = packet.get("reader_utility") or {}

    checklist = ru.get("checklist") or []
    missing = [c for c in checklist if not _checklist_reflected(c, plain)]
    for step in missing[:3]:
        text = (step.get("step") or "").strip()
        if text and len(text) <= 120 and len(paras[2]) < 900:
            paras[2] = f"{paras[2].rstrip()} {text}".strip()
            plain = " ".join(paras)

    scenarios = ru.get("scenarios") or []
    if scenarios and not any(_scenario_reflected(s, plain) for s in scenarios):
        snippet = (scenarios[0].get("body") or "")[:90].strip()
        if snippet:
            if "반면" not in snippet and ("반면" in snippet or "주요국" in snippet):
                snippet = f"반면 {snippet}"
            idx = 1 if len(paras[1]) < 800 else 2
            if len(paras[idx]) + len(snippet) < 900:
                paras[idx] = f"{paras[idx].rstrip()} {snippet}".strip()
                plain = " ".join(paras)

    from engine.pipeline.discovered_facts import discovered_fact_reflected_in_plain

    discovered = packet.get("discovered_facts") or []
    has_discovered = any(
        discovered_fact_reflected_in_plain((d.get("fact") or ""), plain) for d in discovered
    )
    para3_room = 900 - len(paras[2])

    cues = comparison_cues_for_source(source_body)
    if (
        cues
        and sum(1 for c in cues if c in plain) < 2
        and len(paras[2]) < 650
        and not has_discovered
        and para3_room > 120
    ):
        for ln in (source_body or "").splitlines():
            ln = ln.strip()
            if len(ln) < 20 or not any(c in ln for c in cues):
                continue
            if ln[:50] in plain:
                continue
            paras[2] = f"{paras[2].rstrip()} {ln[:100]}".strip()
            plain = " ".join(paras)
            break

    links = ru.get("primary_links") or []
    missing_links = [
        link
        for link in links
        if (link.get("url") or "") and not _url_reflected_in_plain(link["url"], plain)
    ]
    if missing_links and para3_room > 80:
        link = missing_links[0]
        url = (link.get("url") or "").strip()
        label = (link.get("label") or "공식 안내").strip()
        if label.startswith("http") or label == url:
            label = "공식 안내"
        suffix = f"자세한 절차는 {label}({url})에서 확인할 수 있다."
        if len(suffix) <= para3_room:
            paras[2] = f"{paras[2].rstrip()} {suffix}".strip()

    return "".join(f"<p>{p}</p>" for p in paras[:4])
