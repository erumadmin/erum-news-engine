"""Desk Fit helpers — media-fit hard gates (ported selectively from 5e3146f).

IJ: public-interest impact OK when source has policy/society axis.
NN: require citizen/household practical cues; DROP if weak.
CB: require enterprise/ESG/regulation axis; DROP lifestyle/citizen-only.
"""
from __future__ import annotations

import re
from typing import Any

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
    "ESG",
    "규제",
)

CB_NONFIT_LIFESTYLE_CUES = (
    "육아휴직급여 수급자",
    "맞벌이 가구",
    "학부모",
    "주민 체감",
    "생활 팁",
    "여행",
    "맛집",
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
    "지역",
    "소상공인",
)

IJ_PUBLIC_INTEREST_CUES = (
    "정책",
    "제도",
    "공익",
    "불평등",
    "취약",
    "사회",
    "공공",
    "복지",
    "노동",
    "기후",
    "규제",
    "권리",
    "법률",
    "개정",
    "국회",
    "시행령",
    "조례",
    "고용보험",
)


def _text(raw: dict[str, Any]) -> str:
    return f"{raw.get('title') or ''} {raw.get('body') or raw.get('source_body') or ''}"


def cb_enterprise_hit_count(raw: dict[str, Any]) -> int:
    text = _text(raw)
    return sum(1 for c in CB_ENTERPRISE_CUES if c in text)


def nn_life_hit_count(raw: dict[str, Any]) -> int:
    text = _text(raw)
    return sum(1 for c in NN_LIFE_CUES if c in text)


def ij_public_interest_hit_count(raw: dict[str, Any]) -> int:
    text = _text(raw)
    return sum(1 for c in IJ_PUBLIC_INTEREST_CUES if c in text)


def media_fit_gate(site: str, raw: dict[str, Any]) -> tuple[bool, str]:
    """
    Hard media-fit gate. Returns (ok, reason).
    ok=False means DROP / do not assign this site.
    """
    site_key = (site or "").strip().upper()
    text = _text(raw)

    if site_key == "NN":
        if nn_life_hit_count(raw) < 1:
            return False, "nn_drop_weak_citizen_relevance"
        return True, "nn_fit"

    if site_key == "CB":
        lifestyle = sum(1 for c in CB_NONFIT_LIFESTYLE_CUES if c in text)
        ent = cb_enterprise_hit_count(raw)
        if lifestyle >= 1 and ent < 1:
            return False, "cb_drop_lifestyle_citizen_only"
        if ent < 1 and not re.search(r"(ESG|공시|과태료|규제|준법|공급망)", text):
            return False, "cb_drop_no_enterprise_esg_regulation"
        return True, "cb_fit"

    if site_key == "IJ":
        if ij_public_interest_hit_count(raw) < 1 and not re.search(
            r"(정책|제도|사회|노동|복지|법률|개정|국회|시행령)", text
        ):
            return False, "ij_drop_no_public_interest_axis"
        return True, "ij_fit"

    return False, "unknown_site"
