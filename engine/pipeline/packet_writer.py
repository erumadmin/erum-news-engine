from __future__ import annotations

import json
from typing import Any

from research_collector import strip_html_tags

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

[독자 확인 경로 — 아래 항목이 있으면 본문 3·4문단 중 하나에 URL을 빠짐없이 포함]
{action_items_block}

[추가 근거]
{evidence_block}

편집 힌트: publish_grade={publish_grade} | risk_flags={risk_flags}
시점: effective_date={effective_date} | why_now={why_now}
시행·기간 표기(이달/다음 달/6월 등)는 위 시점과 모순되지 않게 하나로 통일한다.

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
- 동일 사실(기간·자동 적용·요금제 종류·대상 요금 등)은 기사 전체에서 각각 1회만 언급한다.

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


def _format_action_items_block(packet: dict[str, Any]) -> str:
    items = packet.get("action_items") or []
    if not items:
        return "(없음 — 원문에 공개 URL이 없으면 생략 가능)"
    return "\n".join(f"- {item}" for item in items)


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
    return EDITORIAL_REWRITE_TEMPLATE.format(
        source_title=(article.get("title") or "").strip() or "미상",
        source_url=(article.get("url") or "").strip() or "미상",
        source_published_at=article.get("source_published_at") or "미상",
        original_text=original_text or "(본문 없음)",
        packet_json=json.dumps(packet, ensure_ascii=False, indent=2),
        action_items_block=_format_action_items_block(packet),
        evidence_block=_format_evidence_block(evidence),
        publish_grade=packet.get("publish_grade", "?"),
        risk_flags=", ".join(risk_flags) if risk_flags else "(없음)",
        effective_date=(packet.get("effective_date") or "").strip() or "(미상)",
        why_now=(packet.get("why_now") or "").strip() or "(미상)",
    )


def build_rewrite_user_message_from_packet(
    article: dict[str, Any],
    packet: dict[str, Any],
) -> str:
    """하위 호환 — 패킷만 넘기던 경로. 신규 코드는 build_rewrite_user_message_from_editorial 사용."""
    return build_rewrite_user_message_from_editorial(article, packet, evidence=None)
