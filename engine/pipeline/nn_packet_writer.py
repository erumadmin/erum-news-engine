"""Neighbor News hybrid rewrite input — source + packet + community brief."""

from __future__ import annotations

import json
import os
from typing import Any

from engine.pipeline.editorial_originality import build_originality_guidance
from engine.pipeline.nn_community_brief import build_community_brief, format_community_brief_block
from engine.pipeline.packet_writer import (
    MAX_EVIDENCE_ITEMS,
    MAX_EVIDENCE_EXCERPT_CHARS,
    MAX_ORIGINAL_CHARS,
    _format_action_items_block,
    _format_evidence_block,
    _format_required_facts_block,
    slim_packet_for_rewrite,
)
from engine.pipeline.reader_utility import format_reader_utility_block
from engine.pipeline.rewrite_validate import temporal_hint_from_source
from research_collector import strip_html_tags

NN_PUBLISH_V4_APPEND = """

[이웃뉴스 v4 — 본문 규칙]
- 본문에 URL·전화번호(☎)를 직접 쓰지 않는다 (확인 경로는 시스템 footer).
- 대화체 흉내("~하시죠?", "~해보세요") 금지. 친절하지만 기사 문장으로 쓴다.
- 「도모」「제고」「활성화」 등 행정 홍보 수사 금지. 원문에 있는 공식 제도명(예: 적극행정)만 그대로 쓸 수 있다.
- 4번째 <p>는 「다만」으로 시작하거나, 남은 제한·예외를 분명히 짚는다.
"""


NN_REWRITE_TEMPLATE = """당신은 **이웃뉴스** 기자다. 뉴스가 어렵게 느껴지는 독자에게, 이웃이 옆집에 설명하듯 **생활에 닿는 변화**를 풀어 쓴다.

- [수집 원문]이 1차 근거. [리서치 패킷]·[추가 근거]·[독자 4축]은 구조화 보조다.
- 세 곳 어디에도 없는 수치·일정·혜택·절차를 만들지 않는다.
- 원문 순서 복사 금지. **영향받는 사람 → 왜 → 조건·이용 → 남은 제한** 순으로 재배열한다.

[수집 원문]
제목: {source_title}
URL: {source_url}
발행시각(KST): {source_published_at}

본문:
{original_text}

[리서치 패킷]
{packet_json}

{community_brief_block}

[독자 가치 — reader_utility]
{reader_utility_block}

[독창성 — 원문·패킷 재구성만]
{originality_guidance_block}

[독자 확인 경로 — v4에서는 본문 URL 금지, 내용만 3문단에 반영]
{action_items_block}

[원문 핵심 사실]
{required_facts_block}

[추가 근거]
{evidence_block}

편집 힌트: publish_grade={publish_grade} | risk_flags={risk_flags}
시점: effective_date={effective_date} | why_now={why_now} | 통일 표기={temporal_hint}

작성 체크리스트 (이웃뉴스):
- 1문단: **영향받는 사람·이용자·환자 가족**이 주어. 「보건복지부가」「상급종합병원이」로 시작 금지.
- 1문단 첫 문장은 자연스러운 생활 문장. 「X는 병원 보상 체계가…」처럼 어색한 치환 금지.
- 2문단: 왜 바뀌는지·기존 문제 (원문만)
- 3문단: 조건·수치·등급·기간 + **해당 여부 한 줄**(예: 상급종합만, 종합병원은 이번엔 제외)
- 4문단: 「다만」+ 남은 제한 (템플릿 「세부 조건과 적용 범위는 발표 내용에 따른다」만으로 채우지 말 것)
- 독자 4축(누구/변화/조건/할 일) 중 **최소 3개** 본문에 드러낼 것

본문 650~1000자, HTML <p> 정확히 4개. JSON 금지.
제목:
리드문:
본문:
카테고리:
태그:
"""


def is_nn_publish_v4_enabled() -> bool:
    return os.environ.get("NN_PUBLISH_V4", "1").strip() not in ("0", "false", "False")


def is_nn_target_engine_enabled() -> bool:
    return os.environ.get("NN_TARGET_ENGINE", "0").strip() in ("1", "true", "True")


def build_rewrite_user_message_for_nn(
    article: dict[str, Any],
    packet: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    *,
    max_original_chars: int = MAX_ORIGINAL_CHARS,
) -> str:
    original_text = strip_html_tags(article.get("body", "") or "").strip()
    if len(original_text) > max_original_chars:
        original_text = original_text[:max_original_chars] + "\n…(이하 생략)"

    if is_nn_target_engine_enabled() and "community_brief" not in packet:
        packet = {**packet, "community_brief": build_community_brief(packet)}

    risk_flags = packet.get("risk_flags") or []
    source_for_hint = original_text or (article.get("body") or "")
    temporal_hint = temporal_hint_from_source(source_for_hint) or "(원문에서 추출 불가)"

    msg = NN_REWRITE_TEMPLATE.format(
        source_title=(article.get("title") or "").strip() or "미상",
        source_url=(article.get("url") or "").strip() or "미상",
        source_published_at=article.get("source_published_at") or "미상",
        original_text=original_text or "(본문 없음)",
        packet_json=json.dumps(slim_packet_for_rewrite(packet), ensure_ascii=False, indent=2),
        community_brief_block=format_community_brief_block(packet),
        reader_utility_block=format_reader_utility_block(packet),
        originality_guidance_block=build_originality_guidance(
            packet, article.get("body") or original_text
        ),
        action_items_block=_format_action_items_block(packet),
        required_facts_block=_format_required_facts_block(packet),
        evidence_block=_format_evidence_block(evidence),
        publish_grade=packet.get("publish_grade", "?"),
        risk_flags=", ".join(risk_flags) if risk_flags else "(없음)",
        effective_date=(packet.get("effective_date") or "").strip() or "(미상)",
        why_now=(packet.get("why_now") or "").strip() or "(미상)",
        temporal_hint=temporal_hint,
    )
    if is_nn_publish_v4_enabled():
        msg += NN_PUBLISH_V4_APPEND
    return msg


def build_nn_quality_retry_suffix(gaps: list[str] | None) -> str:
    if not gaps:
        return ""
    joined = "; ".join(gaps)
    return (
        "\n\n[이웃뉴스 품질 루프 수정 요청]\n"
        f"이전 gaps: {joined}\n"
        "- 1문단 주어 = 영향받는 사람·이용자 (기관명 리드 금지)\n"
        "- 독자 4축(누구/변화/조건/할 일) 3개 이상 반영\n"
        "- 3문단에 이용·신청·시행·예외 정보\n"
        "- 4문단 「다만」+ 한계·유예\n"
        "- 본문 URL 금지, 행정 홍보 수사 금지\n"
    )
