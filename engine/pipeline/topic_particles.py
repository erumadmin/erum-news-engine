"""Korean topic-particle helpers for desk lead openers."""

from __future__ import annotations

import re


def source_is_icu_load_index(text: str) -> bool:
    """True only for the ICU 부하지수/성과보상 story — not bare 30% or 종합병원."""
    t = text or ""
    return bool(re.search(r"중환자실", t) and re.search(r"부하지수|성과보상|800\s*억", t))


def topic_particle_eun_neun(noun: str) -> str:
    """Attach 은/는 by batchim (받침)."""
    word = (noun or "").strip()
    if not word:
        return "는"
    last = word[-1]
    if "가" <= last <= "힣":
        return "은" if ((ord(last) - 0xAC00) % 28) else "는"
    return "는"


def with_topic_particle(noun: str) -> str:
    word = (noun or "").strip()
    if not word:
        return word
    if word.endswith(("은", "는", "이", "가")):
        return word
    return f"{word}{topic_particle_eun_neun(word)}"
