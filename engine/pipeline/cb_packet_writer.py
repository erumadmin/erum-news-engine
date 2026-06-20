"""CSR Briefing hybrid rewrite input - source + packet + compliance brief."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from engine.pipeline.editorial_originality import build_originality_guidance
from engine.pipeline.packet_writer import (
    MAX_ORIGINAL_CHARS,
    _format_action_items_block,
    _format_evidence_block,
    _format_required_facts_block,
)
from engine.pipeline.reader_utility import format_reader_utility_block
from engine.pipeline.rewrite_validate import temporal_hint_from_source
from research_collector import strip_html_tags

CB_PUBLISH_V4_APPEND = """

[CSR 브리핑 v4 - 본문 규칙]
- 본문에 URL·전화번호(☎)를 직접 쓰지 않는다.
- 1문단은 기업·기관 실무 영향으로 시작한다.
- 3문단에는 확인 절차·적용 범위·일정·예외 중 최소 하나를 넣는다.
- 4번째 <p>는 반드시 「다만」으로 시작하고 유예·한계·예외만 쓴다.
"""

CB_REWRITE_TEMPLATE = """당신은 **CSR 브리핑** 기자다. 기업 ESG, 공시, 대외협력, 공급망 실무자가 바로 읽고 판단할 수 있는 기사만 쓴다.

- [수집 원문]이 1차 근거다. [리서치 패킷]과 [compliance_brief]는 구조화 보조다.
- 세 곳 어디에도 없는 일정, 의무, 비용, 예외를 만들지 않는다.
- 원문 순서 복사 금지. **기업 영향 → 배경 → 확인할 실무 항목 → 남은 제한** 순으로 재배열한다.

[수집 원문]
제목: {source_title}
URL: {source_url}
발행시각(KST): {source_published_at}

본문:
{original_text}

[리서치 패킷]
{packet_json}

[기업 실무 브리프 - compliance_brief]
{compliance_brief_block}

[독자 가치 - reader_utility]
{reader_utility_block}

[독창성 - 원문·패킷 재구성만]
{originality_guidance_block}

[실무 확인 경로 - v4에서는 본문 URL 금지]
{action_items_block}

[원문 핵심 사실]
{required_facts_block}

[추가 근거]
{evidence_block}

편집 힌트: publish_grade={publish_grade} | risk_flags={risk_flags}
시점: effective_date={effective_date} | why_now={why_now} | 통일 표기={temporal_hint}

작성 체크리스트 (CSR 브리핑):
- 1문단: 기업·기관 실무자에게 무엇이 바뀌는지
- 2문단: 규제·배경·왜 중요한지
- 3문단: 일정, 적용 범위, 제출·점검·확인 항목
- 4문단: 「다만」+ 유예, 예외, 미확정 요소
- 공급망, 공시, 규제, 예외, 제출, 점검 중 최소 3개 축이 본문에 드러날 것

본문 650~1000자, HTML <p> 정확히 4개. JSON 금지.
제목:
리드문:
본문:
카테고리:
태그:
"""


def is_cb_publish_v4_enabled() -> bool:
    return os.environ.get("CB_PUBLISH_V4", "1").strip() not in ("0", "false", "False")


def is_cb_target_engine_enabled() -> bool:
    return os.environ.get("CB_TARGET_ENGINE", "0").strip() in ("1", "true", "True")


PHOTO_CAPTION_MARKERS = (
    "사진은 기사와 관련 없음",
    "ⓒ뉴스1",
    "무단 전재-재배포 금지",
    "제공)",
    "주재하고 있다",
)
GENERIC_WHO = {"기업", "기관", "중소벤처", "사업자"}
BUSINESS_CHANGE_KEYS = ("완화", "지원", "보조금", "투자", "유턴", "복귀", "인정", "요건", "시행")
BUSINESS_CHANGE_STRONG_KEYS = ("완화", "개편", "인정기준", "보조금", "지원체계", "투자")
CHECK_ITEM_KEYS = ("확인", "점검", "적용", "요건", "보조금", "법령", "시행", "일정", "범위", "지원")
LIMIT_KEYS = ("예정", "내년", "올해", "한도", "조건", "범위", "유예", "예외", "현행")
ANNOUNCE_LEAD_RE = re.compile(r"^(정부|산업통상부|중기부|환경부|고용부|국토부|금융위|공정위|관계부처).{0,40}(발표|밝혔|회의)")


def _is_noisy_business_line(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 12:
        return True
    return any(marker in t for marker in PHOTO_CAPTION_MARKERS)


def _candidate_business_lines(packet: dict[str, Any]) -> list[str]:
    raw = (packet.get("_raw_source") or {}).get("body") or ""
    lines: list[str] = []
    for item in (packet.get("action_items") or []) + (packet.get("conditions") or []) + (packet.get("key_facts") or []):
        text = str(item).strip()
        if text:
            lines.append(text)
    for sent in re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", raw):
        text = sent.strip()
        if text:
            lines.append(text)
    unique: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line in seen or _is_noisy_business_line(line):
            continue
        seen.add(line)
        unique.append(line)
    return unique


def _pick_who_affected(packet: dict[str, Any]) -> list[str]:
    who = [str(item).strip() for item in packet.get("who_is_affected") or [] if str(item).strip()]
    refined = [item for item in who if item not in GENERIC_WHO]
    if refined:
        return refined[:3]
    title = ((packet.get("_raw_source") or {}).get("title") or "").strip()
    title_match = re.search(r"([가-힣A-Za-z0-9·\-\s]{2,20}(?:기업|사업자|상장사|기관))", title)
    if title_match:
        return [title_match.group(1).strip()]
    if who:
        return who[:1]
    return []


def _pick_business_change(packet: dict[str, Any], candidates: list[str]) -> str:
    main_claim = (packet.get("main_claim") or "").strip()
    for text in candidates:
        if ANNOUNCE_LEAD_RE.search(text):
            continue
        if any(key in text for key in BUSINESS_CHANGE_STRONG_KEYS):
            return text
    for text in candidates:
        if ANNOUNCE_LEAD_RE.search(text):
            continue
        if any(key in text for key in BUSINESS_CHANGE_KEYS):
            return text
    if main_claim and not ANNOUNCE_LEAD_RE.search(main_claim):
        return main_claim
    return next((text for text in candidates if len(text) >= 20), main_claim)


def _pick_check_items(candidates: list[str]) -> list[str]:
    picked = [text for text in candidates if any(key in text for key in CHECK_ITEM_KEYS)]
    return picked[:3]


def _pick_remaining_limits(candidates: list[str]) -> list[str]:
    picked = [text for text in candidates if any(key in text for key in LIMIT_KEYS)]
    return picked[:3]


def build_compliance_brief(packet: dict[str, Any]) -> dict[str, Any]:
    candidates = _candidate_business_lines(packet)
    who = _pick_who_affected(packet)
    actions = _pick_check_items(candidates)
    limits = _pick_remaining_limits(candidates)
    main_claim = _pick_business_change(packet, candidates)
    return {
        "who_affected": who,
        "business_change": main_claim,
        "check_items": actions or candidates[:2],
        "remaining_limits": limits or candidates[-2:],
    }


def format_compliance_brief_block(packet: dict[str, Any]) -> str:
    brief = packet.get("compliance_brief") or {}
    if not brief:
        return "(compliance_brief 없음)"
    lines = []
    for item in brief.get("who_affected") or []:
        lines.append(f"- who_affected: {item}")
    if brief.get("business_change"):
        lines.append(f"- business_change: {brief['business_change']}")
    for item in brief.get("check_items") or []:
        lines.append(f"- check_item: {item}")
    for item in brief.get("remaining_limits") or []:
        lines.append(f"- remaining_limit: {item}")
    return "\n".join(lines) or "(compliance_brief 없음)"


def build_rewrite_user_message_for_cb(
    article: dict[str, Any],
    packet: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    *,
    max_original_chars: int = MAX_ORIGINAL_CHARS,
) -> str:
    original_text = strip_html_tags(article.get("body", "") or "").strip()
    if len(original_text) > max_original_chars:
        original_text = original_text[:max_original_chars] + "\n...(이하 생략)"

    if is_cb_target_engine_enabled() and "compliance_brief" not in packet:
        packet = {**packet, "compliance_brief": build_compliance_brief(packet)}

    risk_flags = packet.get("risk_flags") or []
    source_for_hint = original_text or (article.get("body") or "")
    temporal_hint = temporal_hint_from_source(source_for_hint) or "(원문에서 추출 불가)"

    msg = CB_REWRITE_TEMPLATE.format(
        source_title=(article.get("title") or "").strip() or "미상",
        source_url=(article.get("url") or "").strip() or "미상",
        source_published_at=article.get("source_published_at") or "미상",
        original_text=original_text or "(본문 없음)",
        packet_json=json.dumps(packet, ensure_ascii=False, indent=2),
        compliance_brief_block=format_compliance_brief_block(packet),
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
    if is_cb_publish_v4_enabled():
        msg += CB_PUBLISH_V4_APPEND
    return msg
