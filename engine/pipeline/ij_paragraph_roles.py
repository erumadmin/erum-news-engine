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


def para_scores_background(para: str) -> int:
    return sum(1 for k in BG_PARA2_KEYS if k in para)


def para_scores_mechanism(para: str) -> int:
    return sum(1 for k in MECH_PARA3_KEYS if k in para)


def paragraphs_roles_swapped(paras: list[str]) -> bool:
    if len(paras) < 3:
        return False
    p2, p3 = paras[1], paras[2]
    bg2, mech2 = para_scores_background(p2), para_scores_mechanism(p2)
    bg3, mech3 = para_scores_background(p3), para_scores_mechanism(p3)
    return mech2 > bg2 and bg3 > mech3 and mech2 >= 2 and bg3 >= 2


def reorder_paragraph_roles_paras(paras: list[str]) -> list[str]:
    """Swap para 2↔3 when background/mechanism roles are inverted."""
    if len(paras) < 4 or not paragraphs_roles_swapped(paras):
        return paras
    out = list(paras[:4])
    out[1], out[2] = out[2], out[1]
    return out
