"""Desk Fit helpers — route/candidate gates aligned with prompts/desks."""

from __future__ import annotations

import re
from typing import Any

# Enterprise / compliance axes (CB Fit)
CB_ENTERPRISE_CUES = (
    "기업",
    "사업주",
    "사업자",
    "법인",
    "상장",
    "공시",
    "조달",
    "계약",
    "입찰",
    "공급망",
    "협력사",
    "과태료",
    "시정명령",
    "의무화",
    "준수",
    "신고",
    "인허가",
    "인증",
    "공장",
    "물류",
    "창고",
    "사업장",
    "근로",
    "고용",
    "임금",
    "배출",
    "환경규제",
    "컴플라이언스",
    "ESG공시",
)

# Strong hospital/welfare performance subsidy without general enterprise duty
CB_NONFIT_HEALTH_CUES = (
    "중환자실",
    "상급종합병원",
    "종합병원",
    "병상",
    "간호 등급",
    "성과보상",
    "성과지원",
    "부하지수",
    "환자 진료",
    "의료진",
    "건강보험 청구",
)

CB_NONFIT_POLITICS_CUES = (
    "국무회의",
    "대통령은",
    "대통령이",
    "발언을 하고",
    "강조했다",
)

NN_LIFE_CUES = (
    "신청",
    "이용",
    "가구",
    "주민",
    "할인",
    "요금",
    "수급",
    "돌봄",
    "학부모",
    "자영업",
    "승객",
    "환자",
    "가족",
    "생활",
    "체감",
)


def _text(raw: dict[str, Any]) -> str:
    return f"{raw.get('title') or ''} {raw.get('body') or raw.get('source_body') or ''}"


def cb_enterprise_hit_count(raw: dict[str, Any]) -> int:
    text = _text(raw)
    return sum(1 for c in CB_ENTERPRISE_CUES if c in text)


def cb_is_nonfit(raw: dict[str, Any]) -> tuple[bool, str]:
    """Return (nonfit, reason). Nonfit → CB must not write."""
    text = _text(raw)
    ent = cb_enterprise_hit_count(raw)
    health = sum(1 for c in CB_NONFIT_HEALTH_CUES if c in text)
    politics = sum(1 for c in CB_NONFIT_POLITICS_CUES if c in text)

    if health >= 2 and ent < 2:
        return True, "cb_nonfit_health_performance"
    if politics >= 2 and ent < 2 and not re.search(r"(시행|의무|과태료|공시|조달|계약)", text):
        return True, "cb_nonfit_political_speech"
    if ent < 1 and health < 1:
        # no enterprise cue and no clear market signal words
        if not re.search(r"(투자|수요|인력|인프라|업종)", text):
            return True, "cb_nonfit_no_enterprise_axis"
    return False, ""


def nn_life_hit_count(raw: dict[str, Any]) -> int:
    text = _text(raw)
    return sum(1 for c in NN_LIFE_CUES if c in text)
