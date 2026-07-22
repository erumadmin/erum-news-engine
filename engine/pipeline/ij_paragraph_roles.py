"""Shared IJ four-paragraph role cues (electric, hygiene, 유턴, etc.)."""

from __future__ import annotations

BG_PARA2_KEYS = (
    "기존",
    "그동안",
    "우려",
    "문제",
    "부담",
    "혼란",
    "불안",
    "지적",
    "논란",
    "인상",
    "축소",
    "사례",
    "상황",
    "제도",
    "유턴",
    "복귀",
    "해외",
    "지방",
    "문턱",
    "진출",
    "어려움",
    "제약",
    "보호무역",
    "한계가",
    "초기",
    "반면",
    "접수",
    "선정",
    "과제",
    "부처",
    "확보",
    "심사",
)

MECH_PARA3_KEYS = (
    "고지",
    "표기",
    "선택",
    "단일",
    "한전",
    "요금",
    "공개",
    "협약",
    "참가격",
    "포장",
    "지원",
    "투자",
    "절차",
    "신청",
    "유턴",
    "복귀",
    "상담",
    "협상",
    "보조",
    "면제",
    "인정",
    "확인할 수",
    "누리집",
    "http",
)

# Desk North Star / Hard-Fail H1 — 해법 작동 구조 단서 (2문단 우선, 3문단도 허용)
MECH_STRUCTURE_KEYS = MECH_PARA3_KEYS + (
    "기준",
    "산식",
    "지수",
    "보상",
    "차등",
    "도입",
    "연계",
    "산정",
    "지표",
    "등급",
    "산출",
    "배분",
    "가중",
    "반영",
    "운영",
    "체계",
    "방식",
    "단계",
    "요건",
    "조건",
)


def para_scores_background(para: str) -> int:
    return sum(1 for k in BG_PARA2_KEYS if k in para)


def para_scores_mechanism(para: str) -> int:
    return sum(1 for k in MECH_STRUCTURE_KEYS if k in para)


def paragraphs_roles_swapped(paras: list[str]) -> bool:
    if len(paras) < 3:
        return False
    p2, p3 = paras[1], paras[2]
    bg2, mech2 = para_scores_background(p2), para_scores_mechanism(p2)
    bg3, mech3 = para_scores_background(p3), para_scores_mechanism(p3)
    return mech2 > bg2 and bg3 > mech3 and mech2 >= 2 and bg3 >= 2


def reorder_paragraph_roles_paras(paras: list[str]) -> list[str]:
    """Legacy helper: previously swapped 2↔3 when mech sat in para2.

    Desk North Star (v10) puts 해법 작동 in para2, so swapping that shape is harmful.
    Keep identity; do not reorder.
    """
    return paras
