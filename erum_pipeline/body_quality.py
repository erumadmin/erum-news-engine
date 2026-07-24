"""Reader-body quality gates for DRAFT creation.

Internal editorial packets may use structural labels; reader-facing content must not.
Hard-fail publish_ready when banned meta labels / bad repetition / packet leaks appear.
Naive string-strip is not a rewrite — gate fails so fixer/pipeline must rewrite.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Bracket / review meta labels that must never reach article body.
BANNED_META_LABEL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"【\s*사실\s*】",
        r"【\s*사실[·・\-].*?】",
        r"【\s*매체\s*해석.*?】",
        r"【\s*매체.*?】",
        r"【\s*해석.*?】",
        r"【\s*내부.*?】",
        r"【\s*팩트.*?】",
        r"【\s*QA.*?】",
        r"【\s*리뷰.*?】",
        r"\[\s*사실\s*\]",
        r"\[\s*매체\s*해석.*?\]",
    )
)

BANNED_META_PHRASES: tuple[str, ...] = (
    "사실·정부 발표",
    "매체 해석·IJ",
    "매체 해석·NN",
    "매체 해석·CB",
    "매체 해석·ij",
    "매체 해석·nn",
    "매체 해석·cb",
    "journalist_brief",
    "field_takeaways",
    "key_facts",
    "discovered_facts",
    "risk_flags",
    "community_brief",
    "compliance_brief",
    "scorecard",
)

# Known bad prose regressions from advanced-branch experiments.
BANNED_PROSE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"다만\s*다만",
        r"그러나\s*그러나",
        r"또한\s*또한",
        r"그리고\s*그리고",
    )
)

MEDIA_CODE_IN_BODY = re.compile(r"(?<![A-Za-z])(IJ|NN|CB)(?![A-Za-z])")


def find_banned_meta_labels(text: str) -> list[str]:
    hits: list[str] = []
    body = text or ""
    for pat in BANNED_META_LABEL_PATTERNS:
        for m in pat.finditer(body):
            hits.append(m.group(0))
    for phrase in BANNED_META_PHRASES:
        if phrase in body:
            hits.append(phrase)
    return hits


def find_banned_prose(text: str) -> list[str]:
    hits: list[str] = []
    body = text or ""
    for pat in BANNED_PROSE_PATTERNS:
        for m in pat.finditer(body):
            hits.append(m.group(0))
    return hits


def find_media_codes_mid_article(text: str) -> list[str]:
    """Flag bare IJ/NN/CB codes in reader body (not URLs)."""
    return [m.group(0) for m in MEDIA_CODE_IN_BODY.finditer(text or "")]


def _plain_text(html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def title_lead_body_overlap(title: str, excerpt: str, body: str) -> list[str]:
    """Detect near-duplicate title/lead/body openings."""
    issues: list[str] = []
    t = _plain_text(title)
    e = _plain_text(excerpt)
    b = _plain_text(body)
    if t and e and t == e:
        issues.append("title_equals_excerpt")
    if t and b.startswith(t) and len(t) >= 12:
        issues.append("body_starts_with_title")
    if e and b.startswith(e) and len(e) >= 20:
        issues.append("body_starts_with_excerpt")
    # repeated consecutive sentence
    sentences = [s.strip() for s in re.split(r"(?<=다\.)\s+", b) if s.strip()]
    for i in range(len(sentences) - 1):
        if sentences[i] == sentences[i + 1] and len(sentences[i]) >= 20:
            issues.append("consecutive_duplicate_sentence")
            break
    return issues


def source_fidelity_ok(body: str, source_text: str) -> tuple[bool, str]:
    """
    Lightweight fidelity check: body should not invent long numeric runs
    absent from source. Soft numbers (1–2 digits) ignored.
    """
    if not source_text:
        return True, "no_source"
    src = source_text
    body_nums = set(re.findall(r"\d{3,}", body or ""))
    missing = [n for n in body_nums if n not in src]
    # Allow year-like 20xx if present nearby in source as year pattern
    bad = []
    for n in missing:
        if re.fullmatch(r"20\d{2}", n) and n in src:
            continue
        if n not in src:
            bad.append(n)
    if len(bad) >= 3:
        return False, f"invented_numbers:{','.join(bad[:5])}"
    return True, "ok"


def evaluate_reader_body(
    *,
    title: str,
    excerpt: str,
    body: str,
    source_text: str = "",
    soft_score: Optional[float] = None,
) -> dict[str, Any]:
    """
    Hard gate for reader-facing content.

    soft_score is ignored when hard fails — high auto-score cannot override.
    """
    meta = find_banned_meta_labels(body) + find_banned_meta_labels(title) + find_banned_meta_labels(excerpt)
    prose = find_banned_prose(body)
    codes = find_media_codes_mid_article(body)
    dedupe = title_lead_body_overlap(title, excerpt, body)
    fidelity_ok, fidelity_msg = source_fidelity_ok(body, source_text)

    hard_fails: list[str] = []
    if meta:
        hard_fails.append(f"meta_labels:{'|'.join(meta[:8])}")
    if prose:
        hard_fails.append(f"bad_prose:{'|'.join(prose[:5])}")
    if codes:
        hard_fails.append(f"media_codes:{'|'.join(sorted(set(codes)))}")
    if "consecutive_duplicate_sentence" in dedupe:
        hard_fails.append("repetition")
    if not fidelity_ok:
        hard_fails.append(fidelity_msg)

    publish_ready = len(hard_fails) == 0
    return {
        "publish_ready": publish_ready,
        "hard_fails": hard_fails,
        "soft_score": soft_score,
        "meta_labels": meta,
        "bad_prose": prose,
        "media_codes": codes,
        "dedupe_issues": dedupe,
        "fidelity": fidelity_msg,
        # Explicit: soft score never rescues hard fail
        "soft_score_overridden": bool(soft_score is not None and soft_score >= 0.9 and not publish_ready),
    }


def append_sources_footer_html(body: str, source_url: Optional[str], *, section_class: str = "sources-footer") -> str:
    """Append a simple sources footer when a source URL exists and is not already present."""
    url = (source_url or "").strip()
    if not url:
        return body
    if url in (body or ""):
        return body
    import html as _html

    footer = (
        f'<section class="{_html.escape(section_class, quote=True)}">'
        "<h3>관련 링크</h3>"
        f'<ul><li><a href="{_html.escape(url)}">보도자료 원문</a></li></ul>'
        "</section>"
    )
    return (body or "") + footer
