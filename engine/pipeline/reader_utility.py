"""Build reader_utility block for ResearchPacket v2 (source + evidence only)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from research_collector import EvidenceItem, extract_urls_from_text

KST = ZoneInfo("Asia/Seoul")
SCENARIO_MARKERS = (
    "예를 들어",
    "반면",
    "경우",
    "업종",
    "카페",
    "음식점",
    "낮 시간",
    "특히",
    "우선",
    "도입",
    "지정",
    "예정",
    "반영",
)
CHECKLIST_VERBS = (
    "확인",
    "신청",
    "선택",
    "시행",
    "공개",
    "알리",
    "알려",
    "표기",
    "적용",
    "문의",
    "안내",
    "제공",
    "게시",
    "선정",
    "접수",
    "배분",
    "지원",
    "심사",
    "의결",
    "지정",
    "수립",
    "도입",
    "고시",
    "확정",
    "개발",
    "추진",
)
DATE_FRAGMENT = re.compile(
    r"(\d{1,2}월|\d+일|\d{4}년|다음\s*달|6개월|12월|11월|3개월|1개월|5년|분기|년부터|년까지)"
)


def _line_in_source(line: str, body: str) -> bool:
    line = (line or "").strip()
    if len(line) < 12:
        return False
    if line in body:
        return True
    snippet = line[: min(50, len(line))]
    return len(snippet) >= 12 and snippet in body


def _iter_body_lines(body: str):
    """Line-split; fall back to sentence split for single-block fixture bodies."""
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    if len(lines) >= 3:
        yield from lines
        return
    for chunk in re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", (body or "").strip()):
        chunk = chunk.strip()
        if len(chunk) >= 20:
            yield chunk


def extract_scenarios(body: str, *, max_items: int = 3) -> list[dict[str, str]]:
    candidates: list[tuple[int, str]] = []
    for ln in _iter_body_lines(body):
        ln = ln.strip()
        if len(ln) < 25 or len(ln) > 220:
            continue
        if not any(m in ln for m in SCENARIO_MARKERS):
            continue
        if not _line_in_source(ln, body):
            continue
        rank = 0 if "예를 들어" in ln else 1 if "반면" in ln or "반대" in ln else 2
        candidates.append((rank, ln))
    candidates.sort(key=lambda x: (x[0], len(x[1])))
    scenarios: list[dict[str, str]] = []
    for _, ln in candidates:
        label = ln[:60].rstrip(".,")
        scenarios.append({"label": label, "body": ln[:280], "source": "raw_body"})
        if len(scenarios) >= max_items:
            break
    return scenarios


def extract_checklist(body: str, *, max_items: int = 4) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    skip_prefixes = ("정부가", "기후", "또한 일부", "지난 3월")
    action_hints = ("고지서", "선택", "확인", "표기", "신청", "문의", "공개", "알려", "게시", "제공")
    body_stripped = (body or "").strip()
    short_body = len(body_stripped) < 500
    policy_body = len(body_stripped) >= 600
    max_line = 200 if short_body else 130
    min_items = 3 if short_body else 2
    for ln in _iter_body_lines(body):
        if len(ln) < 18 or len(ln) > max_line:
            continue
        if any(ln.startswith(p) for p in skip_prefixes):
            continue
        if not any(v in ln for v in CHECKLIST_VERBS):
            continue
        if not policy_body and not DATE_FRAGMENT.search(ln) and "부터" not in ln and "까지" not in ln:
            continue
        if not policy_body and not any(h in ln for h in action_hints) and not (
            short_body and ("개월" in ln or "공개" in ln or "알리" in ln or "알려" in ln)
        ):
            continue
        if not _line_in_source(ln, body):
            continue
        steps.append({"step": ln[:240], "source": "raw_body"})
        if len(steps) >= max_items:
            break
    if short_body and len(steps) < min_items:
        for ln in _iter_body_lines(body):
            ln = ln.strip()
            if len(ln) < 15 or ln in [s["step"] for s in steps]:
                continue
            if any(v in ln for v in CHECKLIST_VERBS) or "개월" in ln:
                steps.append({"step": ln[:240], "source": "raw_body"})
            if len(steps) >= max_items:
                break
    if len(steps) < 2 and len((body or "").strip()) >= 1200:
        for ln in (body or "").splitlines():
            ln = ln.strip()
            if len(ln) < 20 or len(ln) > 200 or ln in [s["step"] for s in steps]:
                continue
            if not any(v in ln for v in CHECKLIST_VERBS):
                continue
            if not any(
                h in ln
                for h in (
                    "확인",
                    "신청",
                    "지원",
                    "운영",
                    "추진",
                    "개편",
                    "면제",
                    "접수",
                    "선정",
                    "배분",
                    "지정",
                    "도입",
                    "고시",
                )
            ):
                continue
            if not _line_in_source(ln, body):
                continue
            steps.append({"step": ln[:240], "source": "raw_body"})
            if len(steps) >= max_items:
                break
    return steps


def build_primary_links(
    source_url: str,
    source_title: str,
    action_items: list[str],
    evidence_items: list[EvidenceItem],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    if source_url:
        links.append(
            {
                "label": "보도자료 원문",
                "url": source_url,
                "role": "announcement",
                "fetch_status": "n/a",
            }
        )
    seen: set[str] = set()
    for item in action_items or []:
        for url, _ in extract_urls_from_text(item):
            if url in seen:
                continue
            seen.add(url)
            host = (urlparse(url).netloc or "").lower()
            role = "official_reader" if ".go.kr" in host or "kepco" in host else "reader"
            links.append(
                {
                    "label": item.split(":")[0] if ":" in item else "독자 확인",
                    "url": url,
                    "role": role,
                    "fetch_status": "n/a",
                }
            )
    for ev in evidence_items:
        if ev.fetch_status != "ok" or not ev.url:
            continue
        if ev.url in seen:
            continue
        seen.add(ev.url)
        host = (urlparse(ev.url).netloc or "").lower()
        label = (ev.title or "").strip()[:80]
        if not label or label.startswith("http"):
            if "motie" in host:
                label = "산업통상부 공식 안내"
            elif "price.go" in host:
                label = "참가격 확인"
            elif "kepco" in host:
                label = "한전 공식 안내"
            else:
                label = "공식 안내"
        links.append(
            {
                "label": label,
                "url": ev.url,
                "role": "evidence",
                "fetch_status": ev.fetch_status,
            }
        )
    return links[:12]


CONTACT_LINE_RE = re.compile(r"^문의\s*[:：]")


def build_source_confirmation_quotes(
    body: str,
    source_url: str,
    *,
    max_items: int = 2,
) -> list[dict[str, str]]:
    """Verbatim lines from raw body when HTTP evidence fetch is unavailable."""
    min_len = 40 if len((body or "").strip()) < 500 else 80
    quotes: list[dict[str, str]] = []
    for ln in (body or "").splitlines():
        ln = ln.strip()
        if len(ln) < min_len or CONTACT_LINE_RE.match(ln):
            continue
        quotes.append(
            {
                "url": source_url or "raw_body",
                "quote": ln[:400],
                "used_for": "source_confirmation",
            }
        )
        if len(quotes) >= max_items:
            break
    return quotes


IRRELEVANT_EVIDENCE_MARKERS = (
    "시스템 점검",
    "점검이 진행",
    "서비스 문의",
    "홈페이지 담당",
    "☎",
    "장애 복구",
    "접속 불가",
    "일시 중단",
)


def is_irrelevant_evidence_snippet(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 20:
        return False
    hits = sum(1 for m in IRRELEVANT_EVIDENCE_MARKERS if m in t)
    return hits >= 2 or ("시스템 점검" in t and "문의" in t)


def build_evidence_quotes(
    evidence_items: list[EvidenceItem],
    *,
    min_excerpt: int = 80,
    max_items: int = 3,
) -> list[dict[str, str]]:
    quotes: list[dict[str, str]] = []
    for ev in evidence_items:
        if ev.fetch_status != "ok":
            continue
        excerpt = (ev.body_excerpt or "").strip()
        if len(excerpt) < min_excerpt or is_irrelevant_evidence_snippet(excerpt):
            continue
        quotes.append(
            {
                "url": ev.url,
                "quote": excerpt[:400],
                "used_for": "reader_confirmation",
            }
        )
        if len(quotes) >= max_items:
            break
    return quotes


def build_reader_utility(
    raw_source: dict[str, Any],
    evidence_items: list[EvidenceItem],
    *,
    ingest_source: str = "",
) -> dict[str, Any]:
    body = (raw_source.get("body") or raw_source.get("source_body") or "").strip()
    source_url = (raw_source.get("url") or raw_source.get("source_url") or "").strip()
    title = (raw_source.get("title") or raw_source.get("source_title") or "").strip()
    action_items = raw_source.get("action_items")
    if action_items is None:
        from research_collector import _extract_action_items

        action_items = _extract_action_items(body)

    fetched = build_evidence_quotes(evidence_items)
    confirmation = build_source_confirmation_quotes(body, source_url)
    return {
        "scenarios": extract_scenarios(body),
        "checklist": extract_checklist(body),
        "primary_links": build_primary_links(
            source_url, title, list(action_items or []), evidence_items
        ),
        "as_of_date": datetime.now(tz=KST).strftime("%Y-%m-%d"),
        "evidence_quotes": fetched if fetched else confirmation,
        "source_confirmation_quotes": confirmation,
    }


def format_reader_utility_block(packet: dict[str, Any]) -> str:
    """Prompt block for rewrite (packet v2)."""
    ru = packet.get("reader_utility") or {}
    if not ru:
        return "(reader_utility 없음 — 원문·action_items·증거만 사용)"
    lines = [f"기준일(as_of): {ru.get('as_of_date', '(미상)')}"]
    scenarios = ru.get("scenarios") or []
    if scenarios:
        lines.append("시나리오 (원문 예시만):")
        for s in scenarios:
            lines.append(f"- {s.get('label', '')}: {s.get('body', '')}")
    checklist = ru.get("checklist") or []
    if checklist:
        lines.append("체크리스트 (원문·증거 행동만):")
        for c in checklist:
            lines.append(f"- {c.get('step', '')}")
    links = ru.get("primary_links") or []
    if links:
        lines.append("공식·독자 링크:")
        for link in links:
            lines.append(f"- {link.get('label', '')}: {link.get('url', '')}")
    quotes = ru.get("evidence_quotes") or []
    if quotes:
        lines.append("증거 발췌 (인용만):")
        for q in quotes:
            lines.append(f"- {q.get('url', '')}: {q.get('quote', '')[:200]}")
    lines.append(
        "위 블록에 있는 내용만 독자 가치로 추가한다. 없는 수치·표·FAQ는 쓰지 않는다."
    )
    return "\n".join(lines)


def _scenario_reflected(scenario: dict[str, str], plain: str) -> bool:
    body = (scenario.get("body") or "").strip()
    if len(body) >= 15 and body[:40] in plain:
        return True
    if len(body) >= 20 and body[4:44] in plain:
        return True
    tokens = [w for w in re.findall(r"[\w가-힣]+", body) if len(w) >= 2]
    return sum(1 for t in tokens[:8] if t in plain) >= 2


def _url_reflected_in_plain(url: str, plain: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    plain_l = plain.lower()
    if not host:
        return (url or "").lower() in plain_l
    return host in plain_l or host.replace("www.", "") in plain_l


def _checklist_reflected(step: dict[str, str], plain: str) -> bool:
    text = (step.get("step") or "").strip()
    if len(text) >= 12 and text[:35] in plain:
        return True
    tokens = [w for w in re.findall(r"[\w가-힣]+", text) if len(w) >= 2]
    return sum(1 for t in tokens[:5] if t in plain) >= 2


def score_reader_value_dimension(packet: dict[str, Any], plain: str) -> tuple[float, list[str]]:
    """0–10 rubric aligned with ij-editorial-workflow-v2-design §7.2."""
    from engine.pipeline.publish_validate import is_publish_v4_enabled

    ru = packet.get("reader_utility") or {}
    gaps: list[str] = []
    score = 0.0

    raw_body = ((packet.get("_raw_source") or {}).get("body") or "").strip()
    scenarios = list(ru.get("scenarios") or [])
    if len(scenarios) < 1 and raw_body:
        scenarios = extract_scenarios(raw_body)
    checklist = list(ru.get("checklist") or [])
    if len(checklist) < 2 and raw_body:
        checklist = extract_checklist(raw_body)
    if scenarios:
        reflected = sum(1 for s in scenarios if _scenario_reflected(s, plain))
        need = 1 if len(scenarios) >= 2 else 1
        if reflected >= need:
            score += 2.0
        else:
            gaps.append("scenario 미반영")

    if len(checklist) >= 2:
        hits = sum(1 for c in checklist if _checklist_reflected(c, plain))
        need_hits = 2 if len(checklist) < 4 else 1
        if hits >= need_hits:
            score += 2.0
        else:
            gaps.append("checklist 반영 부족")
    elif checklist and _checklist_reflected(checklist[0], plain):
        score += 2.0
    elif checklist:
        gaps.append("checklist 미반영")

    as_of = (ru.get("as_of_date") or "").strip()
    if is_publish_v4_enabled():
        if as_of:
            score += 2.0
    elif as_of and (as_of in plain or "기준" in plain):
        score += 2.0
    elif as_of:
        gaps.append("as_of/기준 미반영")

    quotes = (ru.get("evidence_quotes") or []) + (ru.get("source_confirmation_quotes") or [])
    seen_q: set[str] = set()
    unique_quotes = []
    for q in quotes:
        key = (q.get("quote") or "")[:60]
        if key and key not in seen_q:
            seen_q.add(key)
            unique_quotes.append(q)
    if unique_quotes:
        if any((q.get("quote") or "")[:40] in plain for q in unique_quotes):
            score += 2.0
        else:
            gaps.append("확인 인용 미반영")

    if is_publish_v4_enabled():
        footer = packet.get("sources_footer") or []
        anchor_ok = any(
            token in plain
            for token in ("한전", "정책브리핑", "공식", "누리집", "보도자료", "안내")
        )
        if footer:
            score += 2.0
        elif anchor_ok:
            score += 2.0
        elif (ru.get("primary_links") or []) or ((packet.get("_raw_source") or {}).get("url")):
            gaps.append("출처 앵커·footer 미흡")
        else:
            score += 2.0
    else:
        if not unique_quotes:
            links_early = ru.get("primary_links") or []
            src_url = ((packet.get("_raw_source") or {}).get("url") or "").strip()
            if any(_url_reflected_in_plain(link.get("url") or "", plain) for link in links_early):
                score += 2.0
            elif src_url and _url_reflected_in_plain(src_url, plain):
                score += 2.0
        links = ru.get("primary_links") or []
        url_hits = sum(1 for link in links if _url_reflected_in_plain(link.get("url") or "", plain))
        if url_hits >= 2 or (url_hits >= 1 and len(links) <= 1):
            score += 2.0
        elif url_hits >= 1:
            score += 1.0
        else:
            gaps.append("primary_links URL 부족")

    return min(10.0, score), gaps
