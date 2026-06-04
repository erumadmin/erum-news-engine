"""Extract discovered_facts: facts in official fetch excerpts not present in source body."""

from __future__ import annotations

import re
from typing import Any

from research_collector import strip_html_tags

MIN_EXCERPT_CHARS = 80
MIN_FACT_CHARS = 25
MAX_FACT_CHARS = 220

_ROLE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("procedure", ("신청", "절차", "방법", "확인", "고지", "표기", "선택")),
    ("deadline", ("월", "일", "부터", "까지", "기간", "12월", "6월")),
    ("faq", ("FAQ", "자주", "안내", "문의")),
    ("eligibility", ("대상", "해당", "적용", "제외", "업종")),
    ("contact", ("문의", "전화", "고객센터", "콜센터")),
    ("statistics", ("%", "억", "만", "건", "명")),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _source_plain(raw_source: dict[str, Any]) -> str:
    body = raw_source.get("body") or raw_source.get("source_body") or ""
    return _normalize(strip_html_tags(body))


def _in_source(sentence: str, source_plain: str) -> bool:
    s = _normalize(sentence)
    if len(s) < 12:
        return True
    if s in source_plain:
        return True
  # partial overlap: 70% of shorter in longer
    short, long = (s, source_plain) if len(s) <= len(source_plain) else (source_plain, s)
    if len(short) >= 20 and short[: max(15, len(short) * 2 // 3)] in long:
        return True
    return False


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    out: list[str] = []
    for p in parts:
        p = _normalize(p)
        if len(p) >= MIN_FACT_CHARS:
            out.append(p[:MAX_FACT_CHARS])
    return out


def _low_quality_fact(sentence: str) -> bool:
    s = _normalize(sentence)
    if "공식 안내" in s and s.count("공식 안내") >= 3:
        return True
    words = s.split()
    if len(words) >= 8 and len(set(words)) / len(words) < 0.35:
        return True
    try:
        from engine.pipeline.reader_utility import is_irrelevant_evidence_snippet

        if is_irrelevant_evidence_snippet(s):
            return True
    except ImportError:
        pass
    if "시스템 점검" in s and ("문의" in s or "☎" in s):
        return True
    return False


def _skip_evidence_url(url: str) -> bool:
    u = (url or "").lower()
    if "msit.go.kr" in u and "/bbs/list" in u:
        return True
    return False


REFLECT_MIN_CHUNK = 22


def _plain_for_fact_match(plain: str) -> str:
    """Strip URLs and soften trailing verb endings for overlap checks."""
    text = re.sub(r"\(https?://[^)]+\)", "", plain)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(제공|안내|공개|확인)(한다|하며|함|합니다|됩니다)", r"\1", text)
    return text


def discovered_fact_reflected_in_plain(fact: str, plain: str) -> bool:
    """True when the body already contains the fact (full, clause, or distinctive phrase)."""
    fact_n = _normalize(fact)
    plain_n = _normalize(_plain_for_fact_match(plain))
    if not fact_n or len(fact_n) < 20:
        return True
    fact_cmp = _plain_for_fact_match(fact_n)
    for n in (40, 30, 24):
        if len(fact_cmp) >= n and fact_cmp[:n] in plain_n:
            return True
    for chunk in re.split(r"[.。!?]", fact_cmp):
        chunk = chunk.strip()
        if len(chunk) >= REFLECT_MIN_CHUNK and chunk in plain_n:
            return True
    words = fact_cmp.split()
    if len(words) >= 5:
        if " ".join(words[:5]) in plain_n or " ".join(words[-5:]) in plain_n:
            return True
    tokens = [w for w in re.findall(r"[가-힣]{4,}", fact_cmp) if len(w) >= 4]
    if len(tokens) >= 3:
        hits = sum(1 for t in tokens[:6] if t in plain_n)
        if hits >= max(2, len(tokens[:6]) - 1):
            return True
    return False


def dedupe_discovered_facts(discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop overlapping facts from the same excerpt (keep the longer sentence)."""
    out: list[dict[str, Any]] = []
    for item in discovered:
        fact = _normalize(item.get("fact") or "")
        if len(fact) < MIN_FACT_CHARS:
            continue
        dominated = False
        for i, kept in enumerate(out):
            other = _normalize(kept.get("fact") or "")
            if fact in other or other in fact:
                if len(fact) > len(other):
                    out[i] = item
                dominated = True
                break
            if discovered_fact_reflected_in_plain(fact, other) or discovered_fact_reflected_in_plain(
                other, fact
            ):
                if len(fact) >= len(other):
                    out[i] = item
                dominated = True
                break
        if not dominated:
            out.append(item)
    return out


def _role_for(sentence: str) -> str:
    for role, keys in _ROLE_KEYWORDS:
        if any(k in sentence for k in keys):
            return role
    return "procedure"


def extract_discovered_facts(
    raw_source: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    min_excerpt_chars: int = MIN_EXCERPT_CHARS,
) -> list[dict[str, Any]]:
    """Return facts found in fetch-ok excerpts that are not substring of source body."""
    source_plain = _source_plain(raw_source)
    seen: set[str] = set()
    discovered: list[dict[str, Any]] = []

    for item in evidence:
        if item.get("fetch_status") != "ok":
            continue
        url = (item.get("url") or "").strip()
        if _skip_evidence_url(url):
            continue
        excerpt = (item.get("body_excerpt") or "").strip()
        if len(excerpt) < min_excerpt_chars:
            continue
        for sent in _split_sentences(excerpt):
            key = sent[:80]
            if key in seen:
                continue
            if _in_source(sent, source_plain):
                continue
            if _low_quality_fact(sent):
                continue
            seen.add(key)
            discovered.append(
                {
                    "fact": sent,
                    "source_url": url,
                    "excerpt": excerpt[:600],
                    "role": _role_for(sent),
                    "audience_tag": "field_partner",
                }
            )
    return dedupe_discovered_facts(discovered)
