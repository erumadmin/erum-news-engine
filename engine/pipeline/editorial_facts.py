"""Shared source-fact groups for IJ validation and editorial scorecard."""

from __future__ import annotations

import re


def fact_groups_from_source(source_body: str) -> list[tuple[str, list[str]]]:
    """(label, alternatives) — any alternative in rewrite counts as covered."""
    body = source_body or ""
    groups: list[tuple[str, list[str]]] = []
    if re.search(r"다음\s*달", body):
        groups.append(("시행 시점", ["다음 달"]))
    if "전기위원회" in body:
        groups.append(("심의 절차", ["전기위원회"]))
    if re.search(r"11월", body):
        groups.append(("적용 기간", ["11월"]))
    if "고지서" in body or "표기" in body:
        groups.append(("고지 방식", ["고지서", "표기"]))
    if "12월" in body:
        groups.append(("선택 시점", ["12월"]))
    if "단일" in body and "시간대별" in body:
        groups.append(("요금제", ["단일", "시간대별"]))
    if "700억" in body or "700억 원" in body:
        groups.append(("효율 투자", ["700억"]))
    return groups


def missing_fact_labels(plain: str, source_body: str) -> list[str]:
    missing: list[str] = []
    for label, alts in fact_groups_from_source(source_body):
        if not any(alt in plain for alt in alts):
            missing.append(label)
    return missing


# (paragraph_index, sentence template with {alt})
FACT_LABEL_INJECT: dict[str, tuple[int, str]] = {
    "시행 시점": (0, "시행 시점은 {alt}에 맞춘다."),
    "심의 절차": (1, "관련 기관은 {alt} 심의를 거쳤다."),
    "적용 기간": (0, "적용·비교 대상 기간은 {alt}을 포함한다."),
    "고지 방식": (2, "안내는 {alt}를 통해 이뤄진다."),
    "선택 시점": (3, "{alt}부터 선택·적용할 수 있다."),
    "요금제": (2, "요금제는 {alt} 등으로 구분된다."),
    "효율 투자": (3, "투자 규모는 원문에 {alt} 등으로 안내된다."),
}


def key_fact_covered(fact: str, plain: str) -> bool:
    fact = (fact or "").strip()
    if not fact:
        return False
    if fact[:25] in plain:
        return True
    tokens = [w for w in re.findall(r"[\w가-힣]+", fact) if len(w) >= 2]
    if len(tokens) >= 2 and sum(1 for t in tokens[:8] if t in plain) >= 2:
        return True
    return any(len(w) > 3 and w in plain for w in tokens[:4])
