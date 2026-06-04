from __future__ import annotations

import json
from typing import Any

from engine.pipeline.editorial_originality import build_originality_guidance
from engine.pipeline.reader_utility import format_reader_utility_block
from engine.pipeline.rewrite_validate import temporal_hint_from_source
from engine.pipeline.coalition_takeaways import format_field_takeaways_block
from engine.pipeline.publish_validate import is_publish_v4_enabled
from engine.pipeline.publish_validate import is_publish_v4_enabled
from engine.pipeline.target_engine import is_target_engine_enabled
from research_collector import strip_html_tags

PUBLISH_V4_RULES_APPEND = """

[v4 발행 — 신문체, 연대 브리핑 금지]
- 「연대·보고」「연대·대외」「파트너·수혜자」「NGO·SE」 등 연대·현장 브리핑 표현을 쓰지 않는다.
- 4문단에 「기준: YYYY-MM-DD」「기준 YYYY-MM-DD」「보도·안내 내용은 … 기준」을 넣지 않는다 (출처·기준일은 시스템 footer만).
- 본문에 URL·전화번호를 직접 쓰지 않는다.
- 시스템 점검·홈페이지 담당·콜센터 안내 문구는 본문에 넣지 않는다.
"""

PUBLISH_V4_RULES_APPEND = """

[v4 발행 — 신문체, 연대 브리핑 금지]
- 「연대·보고」「연대·대외」「파트너·수혜자」「NGO·SE」 등 연대·현장 브리핑 표현을 쓰지 않는다.
- 4문단에 「기준: YYYY-MM-DD」「기준 YYYY-MM-DD」「보도·안내 내용은 … 기준」을 넣지 않는다 (출처·기준일은 시스템 footer만).
- 본문에 URL·전화번호(☎)를 직접 쓰지 않는다.
- 4번째 <p>는 반드시 「다만」으로 시작하고, 시행 범위·적용 조건·유의점만 쓴다.
"""

TARGET_EDITORIAL_REWRITE_TEMPLATE = """당신은 사회공헌·비영리 현장을 돕는 정책 데스크 기자다.
1차 독자는 NGO, 사회적 기업, 사회공헌 업계 실무자다. 파트너·수혜자에게 설명·연대 공지·보고에 쓸 **현장·연대 브리핑**을 쓴다.

- [수집 원문]으로 이슈를 파악했고, [조사에서 확인한 사실]은 공식 페이지 fetch 발췌다.
- **원문과 조사 발췌에 있는 사실만** 사용한다. 없는 수치·일정·절차·FAQ를 만들지 않는다.
- 보도자료 문장 순서 복사 금지. [연대 브리프]의 질문·할 일에 답하는 구조로 재구성한다.
- [조사에서 확인한 사실]은 최소 1건 본문(3문단 권장)에 반영한다.

[연대 브리프]
{coalition_brief_block}

[NGO·SE 현장 시사점 — 본문에 반드시 반영, 원문·조사 범위만]
{field_takeaways_block}

[조사에서 확인한 사실]
{discovered_block}

[수집 원문]
제목: {source_title}
URL: {source_url}
발행시각(KST): {source_published_at}

본문:
{original_text}

[리서치 패킷]
{packet_json}

[독자 가치 — reader_utility만 사용]
{reader_utility_block}

[독창성 가치 — 원문·패킷·조사 재구성만]
{originality_guidance_block}

[독자 확인 경로]
{action_items_block}

[원문 핵심 사실]
{required_facts_block}

[추가 근거]
{evidence_block}

편집 힌트: publish_grade={publish_grade} | risk_flags={risk_flags} | research_depth={research_depth}
시점: effective_date={effective_date} | why_now={why_now} | 통일 표기={temporal_hint}

작성 체크리스트 (연대 브리핑):
- 1문단: 무엇이 바뀌는지 + NGO·SE·파트너·수혜자 시사점(누구 해당)
- 2문단: 배경·문제 (원문·조사만)
- 3문단: 작동 방식 + 조사 fact + 현장 할 일(확인·안내·공유) + action_items URL 전부
- 4문단: 반드시 "다만"으로 시작 — 연대·대외 안내 시 유의점(coalition_gaps)
- [NGO·SE 현장 시사점] 블록의 who/할 일/유의를 각각 1·3·4문단에 녹일 것 (라벨 출력 금지)

본문 700~1100자, HTML <p> 정확히 4개. JSON 금지.
제목:
리드문:
본문:
카테고리:
태그:
"""

# news_editor_common.md 와 동일한 라벨 출력 (JSON 아님 — parse_llm_response 호환)
EDITORIAL_REWRITE_TEMPLATE = """아래 [수집 원문], [리서치 패킷], [추가 근거]에 있는 사실만 사용해 기사를 작성하세요.

- 수집 원문이 1차 근거다. 리서치 패킷은 구조화 요약이고, 추가 근거는 교차 확인·보강용이다.
- 세 곳 어디에도 없는 수치·일정·품목·시행 여부·기대효과를 만들지 마세요.
- 원문 문장을 순서대로 복사·축약하지 말고, 독자가 구조를 이해할 수 있게 재구성한다.

[수집 원문]
제목: {source_title}
URL: {source_url}
발행시각(KST): {source_published_at}

본문:
{original_text}

[리서치 패킷]
{packet_json}

[독자 가치 — reader_utility만 사용, 없으면 생략]
{reader_utility_block}

[독창성 가치 — 원문·패킷 재구성만, 환각 금지]
{originality_guidance_block}

[독자 확인 경로 — 아래 항목이 있으면 본문 3·4문단 중 하나에 URL을 빠짐없이 포함]
{action_items_block}

[원문 핵심 사실 — 반드시 본문에 반영 (없는 내용 추가 금지)]
{required_facts_block}

[추가 근거]
{evidence_block}

편집 힌트: publish_grade={publish_grade} | risk_flags={risk_flags}
시점: effective_date={effective_date} | why_now={why_now} | 통일 표기={temporal_hint}
시행·기간은 통일 표기와 effective_date에 맞춘다. "다음 달"이면 "이달부터"를 쓰지 않는다.

작성 체크리스트:
- 무엇이 바뀌었는지: main_claim, key_facts, 원문 첫머리
- 왜 지금: why_now
- 누가 영향: who_is_affected
- 작동 방식: conditions, key_facts, 원문의 고지·제출·공개 채널
- 독자 확인 경로: [독자 확인 경로] 블록의 URL — 있으면 본문에 반드시 포함
- 조건·한계: exceptions, risk_flags 반영

risk_flags에 official_evidence_missing 이 있으면 단정적 해석·임팩트 과장을 하지 말고 조치·고지·자율 협약 여부를 구분해 쓴다.
announcement_only_risk가 있으면 제목·리드에 법적 의무화·시행 완료를 단정하지 않는다.

본문은 700~1100자 안팎으로 완결한다.
- HTML: 정확히 4개의 <p>...</p> 블록만 사용한다. 소제목·번호·"1." 라벨 금지.
- 1번째 <p>: 변화·수혜자 / 2번째 <p>: 배경·문제 / 3번째 <p>: 작동 방식 / 4번째 <p>: 임팩트·남은 조건
- 4번째 <p> 첫머리는 반드시 "다만"으로 시작하고, 시행 범위·기간·남은 조건을 2문장 이상 쓴다.
- official_evidence_missing이면 법적 의무·효과를 단정하지 말고 조치·고지·자율 여부를 구분한다.
- 동일 사실(기간·자동 적용·요금제 종류·대상 요금 등)은 기사 전체에서 각각 최대 2회.

반드시 아래 형식만 출력하세요 (JSON 금지):
제목:
리드문:
본문:
카테고리:
태그:
"""

MAX_ORIGINAL_CHARS = int(__import__("os").environ.get("REWRITE_SOURCE_MAX_CHARS", "4000"))
MAX_EVIDENCE_ITEMS = 5
MAX_EVIDENCE_EXCERPT_CHARS = 600


def _format_required_facts_block(packet: dict[str, Any]) -> str:
    facts = packet.get("key_facts") or []
    if not facts:
        return "(패킷 key_facts 없음)"
    return "\n".join(f"- {f}" for f in facts[:6])


def _format_action_items_block(packet: dict[str, Any]) -> str:
    items = packet.get("action_items") or []
    if not items:
        return "(없음 — 원문에 공개 URL이 없으면 생략 가능)"
    return "\n".join(f"- {item}" for item in items)


def _format_coalition_brief_block(packet: dict[str, Any]) -> str:
    jb = packet.get("journalist_brief") or {}
    if not jb:
        return "(연대 브리프 없음)"
    lines = [
        f"- lead_question: {jb.get('lead_question', '')}",
        f"- why_now: {jb.get('why_now', '')}",
    ]
    for w in jb.get("who_should_care") or []:
        lines.append(f"- who_should_care: {w}")
    for t in jb.get("reader_tasks") or []:
        lines.append(f"- reader_task: {t}")
    for g in jb.get("coalition_gaps") or []:
        lines.append(f"- coalition_gap: {g}")
    return "\n".join(lines)


def _format_discovered_block(packet: dict[str, Any]) -> str:
    items = packet.get("discovered_facts") or []
    if not items:
        return "(조사 확인 사실 없음 — 본문에 조사 fact 추가 금지)"
    lines = []
    for d in items[:6]:
        lines.append(f"- [{d.get('role', '?')}] {d.get('fact', '')}")
        lines.append(f"  출처: {d.get('source_url', '')}")
        ex = (d.get("excerpt") or "")[:200]
        if ex:
            lines.append(f"  발췌: {ex}")
    return "\n".join(lines)


def _format_evidence_block(evidence: list[dict[str, Any]] | None) -> str:
    if not evidence:
        return "(추가 근거 없음 — 수집 원문과 패킷만 사용)"
    lines: list[str] = []
    for item in evidence:
        if item.get("fetch_status") != "ok":
            continue
        if len(lines) >= MAX_EVIDENCE_ITEMS:
            break
        etype = item.get("evidence_type") or "unknown"
        title = (item.get("title") or item.get("url") or "").strip()
        url = (item.get("url") or "").strip()
        excerpt = (item.get("body_excerpt") or "").strip()[:MAX_EVIDENCE_EXCERPT_CHARS]
        lines.append(f"- [{etype}] {title}")
        lines.append(f"  URL: {url}")
        lines.append(f"  발췌: {excerpt or '(없음)'}")
    return "\n".join(lines) if lines else "(fetch ok 추가 근거 없음)"


def build_rewrite_user_message_from_editorial(
    article: dict[str, Any],
    packet: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    *,
    max_original_chars: int = MAX_ORIGINAL_CHARS,
) -> str:
    """수집 원문 전문 + 리서치 패킷 + 추가 근거를 합쳐 IJ 재작성 입력을 만든다."""
    original_text = strip_html_tags(article.get("body", "") or "").strip()
    if len(original_text) > max_original_chars:
        original_text = original_text[:max_original_chars] + "\n…(이하 생략)"

    risk_flags = packet.get("risk_flags") or []
    source_for_hint = original_text or (article.get("body") or "")
    temporal_hint = temporal_hint_from_source(source_for_hint) or "(원문에서 추출 불가 — 리드와 본문 동일 표기)"
    originality_block = build_originality_guidance(
        packet, article.get("body") or original_text
    )
    common = dict(
        source_title=(article.get("title") or "").strip() or "미상",
        source_url=(article.get("url") or "").strip() or "미상",
        source_published_at=article.get("source_published_at") or "미상",
        original_text=original_text or "(본문 없음)",
        packet_json=json.dumps(packet, ensure_ascii=False, indent=2),
        reader_utility_block=format_reader_utility_block(packet),
        originality_guidance_block=originality_block,
        action_items_block=_format_action_items_block(packet),
        required_facts_block=_format_required_facts_block(packet),
        evidence_block=_format_evidence_block(evidence),
        publish_grade=packet.get("publish_grade", "?"),
        risk_flags=", ".join(risk_flags) if risk_flags else "(없음)",
        effective_date=(packet.get("effective_date") or "").strip() or "(미상)",
        why_now=(packet.get("why_now") or "").strip() or "(미상)",
        temporal_hint=temporal_hint,
    )
    if is_target_engine_enabled() and not is_publish_v4_enabled():
        meta = packet.get("research_meta") or {}
        return TARGET_EDITORIAL_REWRITE_TEMPLATE.format(
            **common,
            coalition_brief_block=_format_coalition_brief_block(packet),
            field_takeaways_block=format_field_takeaways_block(packet),
            discovered_block=_format_discovered_block(packet),
            research_depth=meta.get("research_depth", "?"),
        )
    base = EDITORIAL_REWRITE_TEMPLATE.format(**common)
    if is_publish_v4_enabled():
        if is_target_engine_enabled():
            disc = _format_discovered_block(packet)
            if "(조사 확인 사실 없음" not in disc:
                base += f"\n\n[조사에서 확인한 사실 — 원문에 없을 때만 3문단에 반영]\n{disc}\n"
        base += PUBLISH_V4_RULES_APPEND
    return base


def build_editorial_quality_retry_suffix(gaps: list[str] | None) -> str:
    if not gaps:
        return ""
    joined = "; ".join(gaps)
    if is_publish_v4_enabled():
        return (
            "\n\n[품질 루프 수정 요청 — v4 발행]\n"
            f"이전 시도 채점 gaps: {joined}\n"
            "- 신문체 4문단. 연대·보고·파트너·수혜자·NGO 표현 금지\n"
            "- 4문단에 기준일·「보도·안내 내용은 … 기준」 금지 (footer만)\n"
            "- checklist·scenario·action_items는 패킷·원문 범위만 3문단에 반영 (URL 본문 금지)\n"
            "- 4문단은 「다만」+ 시행·대상·한계 2문장 이상 (템플릿 한계 문장 금지)\n"
        )
    return (
        "\n\n[품질 루프 수정 요청]\n"
        f"이전 시도 채점 gaps: {joined}\n"
        "- reader_utility의 as_of_date는 4문단에 '기준'과 날짜로 반드시 포함\n"
        "- checklist·scenario는 패킷 문장을 본문 3문단에 짧게 반영\n"
        "- action_items URL은 3문단에 빠짐없이 포함\n"
        "- originality: 시나리오 대비 1줄, 체크리스트 3단계, 원문 비교·표기(원문에 있을 때만)\n"
        "- NGO·SE 시사점: 1문단 누구, 3문단 현장 할 일, 4문단 다만 유의 — 패킷 field_takeaways 반영\n"
    )


def build_rewrite_user_message_from_packet(
    article: dict[str, Any],
    packet: dict[str, Any],
) -> str:
    """하위 호환 — 패킷만 넘기던 경로. 신규 코드는 build_rewrite_user_message_from_editorial 사용."""
    return build_rewrite_user_message_from_editorial(article, packet, evidence=None)
