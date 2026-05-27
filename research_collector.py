"""
Deterministic research collection for policy-briefing style sources.

No LLM calls — link extraction, domain classification, optional HTTP fetch.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# Official / high-trust domains for IJ policy stories (suffix match)
OFFICIAL_DOMAIN_SUFFIXES: tuple[tuple[str, str, int], ...] = (
    (".go.kr", "government", 90),
    ("korea.kr", "policy_briefing", 85),
    ("law.go.kr", "law", 95),
    ("epeople.go.kr", "public_petition", 80),
    ("nas.go.kr", "statistics", 85),
)

SKIP_HOST_FRAGMENTS = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "mailto:",
    "javascript:",
)

# korea.kr 페이지 공통 헤더/푸터 링크 — 기사 근거로 쓰지 않음
GLOBAL_NAV_HOSTS = frozenset(
    {
        "www.epeople.go.kr",
        "www.ehistory.go.kr",
        "www.ktv.go.kr",
        "www.laiis.go.kr",
        "www.president.go.kr",
        "www.opm.go.kr",
        "www.korea.kr",
    }
)

ARTICLE_ROOT_SELECTORS = (
    ".view_cont",
    "#articleBody",
    ".article-content",
    ".news_view",
    "article",
    ".content",
)

# 본문에 부처명만 있고 URL이 없을 때 시도할 공식 보도자료 허브 (검색/목록 페이지)
SKIP_FETCH_EVIDENCE_TYPES = frozenset({"ministry_press_hub"})

MINISTRY_PRESS_HUBS: tuple[tuple[str, str, str], ...] = (
    (r"공정거래위원회|공정위", "https://www.ftc.go.kr/www/bbs/bbsList.do?key=0000104030000", "ministry_press_hub"),
    (r"과학기술정보통신부|과기정통부", "https://www.msit.go.kr/bbs/list.do?sCode=user&mId=57&mPid=74", "ministry_press_hub"),
    (r"산업통상부|산업통상자원부|산업부", "https://www.motie.go.kr/motie/ne/presse/press2/bbs/bbsList.do?bbs_cd_n=81", "ministry_press_hub"),
    (r"보건복지부|복지부", "https://www.mohw.go.kr/board.es?mid=a10503000000&bid=0027", "ministry_press_hub"),
    (r"기획재정부|기재부", "https://www.moef.go.kr/nw/nes/nesList.do", "ministry_press_hub"),
    (r"국토교통부|국토부", "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp", "ministry_press_hub"),
)

URL_IN_TEXT_RE = re.compile(
    r"https?://[^\s\)\]\"'<>]+|(?:www\.)[a-zA-Z0-9][-a-zA-Z0-9.]+\.[a-zA-Z]{2,}[^\s\)\]\"'<>]*"
)

EFFECTIVE_DATE_RE = re.compile(
    r"(\d{4})[./년\s]*(\d{1,2})[./월\s]*(\d{1,2})"
)

CONTACT_LINE_RE = re.compile(r"^문의\s*[:：]", re.MULTILINE)

SUBSTANTIVE_EVIDENCE_EXCERPT_CHARS = 80
MIN_BODY_CHARS_FOR_GRADE_A = 500
MIN_BODY_CHARS_FOR_GRADE_B = 280
THIN_SOURCE_BODY_CHARS = 400


@dataclass
class LinkCandidate:
    url: str
    anchor_text: str
    source: str  # html | text
    domain: str
    evidence_type: str
    reliability_rank: int


@dataclass
class EvidenceItem:
    evidence_type: str
    url: str
    title: str
    body_excerpt: str
    published_at: Optional[str]
    reliability_rank: int
    collected_at: str
    fetch_status: str  # ok | skipped | error


@dataclass
class EvidencePlan:
    assigned_site: str
    raw_source_url: str
    link_candidates: list[LinkCandidate] = field(default_factory=list)
    fetch_targets: list[LinkCandidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ResearchPacket:
    site: str
    main_claim: str
    why_now: str
    who_is_affected: list[str]
    effective_date: str
    conditions: list[str]
    exceptions: list[str]
    action_items: list[str]
    key_facts: list[str]
    source_refs: list[dict[str, str]]
    risk_flags: list[str]
    image_asset_tier: str
    publish_grade: str
    placement_hint: str
    evidence_count: int
    official_evidence_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def strip_html_tags(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)


def normalize_url(url: str, base_url: str = "") -> Optional[str]:
    if not url or not str(url).strip():
        return None
    url = str(url).strip()
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        if url.startswith("www."):
            url = "https://" + url
        elif base_url:
            url = urljoin(base_url, url)
        else:
            return None
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    lowered = url.lower()
    for frag in SKIP_HOST_FRAGMENTS:
        if frag in lowered:
            return None
    return url.split("#")[0].rstrip("/")


def classify_domain(url: str) -> tuple[str, str, int]:
    host = (urlparse(url).netloc or "").lower()
    if not host:
        return "unknown", "unknown", 10
    for suffix, evidence_type, rank in OFFICIAL_DOMAIN_SUFFIXES:
        if suffix.startswith(".") and host.endswith(suffix):
            return host, evidence_type, rank
        if suffix in host:
            return host, evidence_type, rank
    if host.endswith(".or.kr"):
        return host, "organization", 60
    if host.endswith(".co.kr") or host.endswith(".com"):
        return host, "corporate", 40
    return host, "other", 20


def extract_urls_from_text(text: str) -> list[tuple[str, str]]:
    if not text:
        return []
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in URL_IN_TEXT_RE.finditer(text):
        raw = match.group(0).rstrip(".,;)")
        url = normalize_url(raw)
        if url and url not in seen:
            seen.add(url)
            found.append((url, "text"))
    return found


def _article_root_nodes(soup: BeautifulSoup) -> list[Any]:
    nodes = []
    for selector in ARTICLE_ROOT_SELECTORS:
        node = soup.select_one(selector)
        if node and node not in nodes:
            nodes.append(node)
    return nodes


def extract_links_from_html(html: str, base_url: str = "") -> list[tuple[str, str, str]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def collect_from(node, source_label: str) -> None:
        for anchor in node.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            if not href or href.startswith("#"):
                continue
            url = normalize_url(href, base_url)
            if not url or url in seen:
                continue
            host = (urlparse(url).netloc or "").lower()
            if host in GLOBAL_NAV_HOSTS:
                continue
            seen.add(url)
            text = anchor.get_text(" ", strip=True)[:120]
            results.append((url, text, source_label))

    article_nodes = _article_root_nodes(soup)
    if article_nodes:
        for node in article_nodes:
            collect_from(node, "html_article")
    else:
        collect_from(soup, "html")

    return results


def infer_ministry_hubs(body: str) -> list[LinkCandidate]:
    text = body or ""
    out: list[LinkCandidate] = []
    seen: set[str] = set()
    for pattern, hub_url, label in MINISTRY_PRESS_HUBS:
        if not re.search(pattern, text):
            continue
        url = normalize_url(hub_url)
        if not url or url in seen:
            continue
        seen.add(url)
        host, etype, rank = classify_domain(url)
        out.append(
            LinkCandidate(
                url=url,
                anchor_text=label,
                source="ministry_infer",
                domain=host,
                evidence_type="ministry_press_hub",
                reliability_rank=rank,
            )
        )
    return out


def discover_link_candidates(
    *,
    body: str = "",
    html: str = "",
    base_url: str = "",
) -> list[LinkCandidate]:
    merged: dict[str, LinkCandidate] = {}

    for url, source in extract_urls_from_text(body):
        host, etype, rank = classify_domain(url)
        merged[url] = LinkCandidate(
            url=url,
            anchor_text="",
            source=source,
            domain=host,
            evidence_type=etype,
            reliability_rank=rank,
        )

    for url, anchor, source in extract_links_from_html(html, base_url):
        host, etype, rank = classify_domain(url)
        prev = merged.get(url)
        anchor_text = anchor or (prev.anchor_text if prev else "")
        if prev and prev.reliability_rank >= rank and len(anchor_text) <= len(prev.anchor_text):
            continue
        merged[url] = LinkCandidate(
            url=url,
            anchor_text=anchor_text,
            source=source,
            domain=host,
            evidence_type=etype,
            reliability_rank=rank,
        )

    for hub in infer_ministry_hubs(body):
        if hub.url not in merged:
            merged[hub.url] = hub

    return sorted(merged.values(), key=lambda c: (-c.reliability_rank, c.url))


def build_evidence_plan(
    raw_source: dict[str, Any],
    *,
    assigned_site: str = "IJ",
    max_fetch: int = 3,
    min_official_rank: int = 80,
) -> EvidencePlan:
    url = (raw_source.get("url") or raw_source.get("source_url") or "").strip()
    html = raw_source.get("raw_html") or raw_source.get("rss_summary") or raw_source.get("html") or ""
    body = raw_source.get("body") or raw_source.get("source_body") or ""
    if not body.strip() and html:
        body = strip_html_tags(html)

    candidates = discover_link_candidates(body=body, html=html, base_url=url)
    notes: list[str] = []
    if not candidates:
        notes.append("본문/HTML에서 추출한 외부 링크 없음 — 부처 보도자료 URL 수동/검색 필요")

    # Prefer official domains; exclude self (same article)
    parsed_source = urlparse(url)
    source_key = (parsed_source.netloc + parsed_source.path).lower()

    inferred_hubs = [c for c in candidates if c.evidence_type == "ministry_press_hub"]
    if inferred_hubs and not any(c.evidence_type != "ministry_press_hub" for c in candidates):
        notes.append(
            f"부처 보도자료 허브 {len(inferred_hubs)}건 추론됨 — 목록 페이지 매칭(제목 검색)은 아직 미구현"
        )

    fetch_targets: list[LinkCandidate] = []
    for cand in candidates:
        if cand.evidence_type in SKIP_FETCH_EVIDENCE_TYPES:
            continue
        if min_official_rank and cand.reliability_rank < min_official_rank:
            continue
        host = (cand.domain or "").lower()
        if host in GLOBAL_NAV_HOSTS:
            continue
        cand_path = urlparse(cand.url)
        cand_key = (cand_path.netloc + cand_path.path).lower()
        if source_key and cand_key == source_key:
            continue
        if cand.url.rstrip("/") == url.rstrip("/"):
            continue
        fetch_targets.append(cand)
        if len(fetch_targets) >= max_fetch:
            break

    # law.go.kr 본문 링크·ftc 등 부처 도메인 우선
    def _fetch_priority(c: LinkCandidate) -> tuple[int, int, str]:
        host = (c.domain or "").lower()
        law_boost = 10 if "law.go.kr" in host and c.source == "html_article" else 0
        ftc_boost = 20 if host.endswith("ftc.go.kr") or host.endswith("mss.go.kr") else 0
        article_boost = 5 if c.source == "html_article" else 0
        return (-(c.reliability_rank + law_boost + ftc_boost + article_boost), len(c.url), c.url)

    fetch_targets.sort(key=_fetch_priority)
    fetch_targets = fetch_targets[:max_fetch]

    if candidates and not fetch_targets:
        notes.append("링크는 있으나 공식 도메인(신뢰도 80+) 후보 없음")

    return EvidencePlan(
        assigned_site=assigned_site,
        raw_source_url=url,
        link_candidates=candidates,
        fetch_targets=fetch_targets,
        notes=notes,
    )


def _extract_page_title_and_excerpt(html: str, max_chars: int = 800) -> tuple[str, str]:
    if not html:
        return "", ""
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    for selector in (".view_cont", "#articleBody", "article", ".article-body", ".content"):
        node = soup.select_one(selector)
        if node:
            text = node.get_text("\n", strip=True)
            if len(text) > 80:
                return title, text[:max_chars]
    text = soup.get_text("\n", strip=True)
    return title, text[:max_chars]


def fetch_evidence_page(
    url: str,
    fetcher: Callable[[str], Any],
    *,
    timeout_hint: str = "",
) -> EvidenceItem:
    collected_at = _now_iso()
    try:
        response = fetcher(url)
        status = getattr(response, "status_code", None)
        if response is None or (status is not None and status >= 400):
            code = status or "none"
            return EvidenceItem(
                evidence_type=classify_domain(url)[1],
                url=url,
                title="",
                body_excerpt="",
                published_at=None,
                reliability_rank=classify_domain(url)[2],
                collected_at=collected_at,
                fetch_status=f"error:http_{code}",
            )
        html = getattr(response, "text", "") or ""
        title, excerpt = _extract_page_title_and_excerpt(html)
        host, etype, rank = classify_domain(url)
        return EvidenceItem(
            evidence_type=etype,
            url=url,
            title=title,
            body_excerpt=excerpt,
            published_at=None,
            reliability_rank=rank,
            collected_at=collected_at,
            fetch_status="ok",
        )
    except Exception as exc:
        return EvidenceItem(
            evidence_type=classify_domain(url)[1],
            url=url,
            title="",
            body_excerpt="",
            published_at=None,
            reliability_rank=classify_domain(url)[2],
            collected_at=collected_at,
            fetch_status=f"error:{type(exc).__name__}",
        )


def collect_evidence(
    raw_source: dict[str, Any],
    fetcher: Callable[[str], Any],
    *,
    assigned_site: str = "IJ",
    max_fetch: int = 3,
) -> tuple[EvidencePlan, list[EvidenceItem]]:
    plan = build_evidence_plan(raw_source, assigned_site=assigned_site, max_fetch=max_fetch)
    items: list[EvidenceItem] = []
    for target in plan.fetch_targets:
        items.append(fetch_evidence_page(target.url, fetcher))
    return plan, items


def _first_sentence(text: str, max_len: int = 200) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?다요])\s+", text)
    head = parts[0] if parts else text
    return head[:max_len]


def _extract_effective_date(text: str) -> str:
    m = EFFECTIVE_DATE_RE.search(text or "")
    if not m:
        return ""
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _extract_who_affected(text: str) -> list[str]:
    patterns = [
        r"소비자",
        r"기업",
        r"중소(?:기업|벤처)",
        r"국민",
        r"가구",
        r"자영업자",
        r"협력사",
    ]
    found = []
    for p in patterns:
        m = re.search(p, text or "")
        if m:
            found.append(m.group(0))
    return list(dict.fromkeys(found))[:6]


def _extract_action_items(text: str) -> list[str]:
    """Reader-facing URLs and notice channels mentioned in source text."""
    items: list[str] = []
    for url, anchor in extract_urls_from_text(text or ""):
        label = (anchor or url).strip()
        if "price.go.kr" in url or "참가격" in label:
            items.append(f"참가격 확인: {url}")
        elif ".go.kr" in url:
            items.append(f"공식 안내: {url}")
    for m in re.finditer(
        r"(3개월|1개월|30일|60일|90일)[^\n]{0,40}(?:전|이내|이전)",
        text or "",
    ):
        items.append(m.group(0).strip()[:120])
    return list(dict.fromkeys(items))[:6]


def _bullet_conditions(text: str) -> list[str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    keys = ("해야 한다", "해야 한다", "이상", "미만", "금지", "의무", "알려야", "제공", "게시")
    out = []
    for ln in lines:
        if any(k in ln for k in keys) and len(ln) >= 12:
            out.append(ln[:240])
        if len(out) >= 5:
            break
    return out


def build_research_packet(
    raw_source: dict[str, Any],
    evidence_items: list[EvidenceItem],
    *,
    assigned_site: str = "IJ",
) -> ResearchPacket:
    title = (raw_source.get("title") or raw_source.get("source_title") or "").strip()
    body = (raw_source.get("body") or raw_source.get("source_body") or "").strip()
    source_url = (raw_source.get("url") or raw_source.get("source_url") or "").strip()

    main_claim = _first_sentence(body) or title
    why_now = ""
    if "추진" in body or "배경" in body or "상황" in body:
        for ln in body.splitlines():
            if any(k in ln for k in ("추진", "배경", "때문", "하여")):
                why_now = ln.strip()[:240]
                break
    if not why_now:
        why_now = _first_sentence(body[80:400] if len(body) > 80 else body, 180)

    source_refs: list[dict[str, str]] = [
        {"role": "lead", "url": source_url, "title": title},
    ]
    official_count = 0
    substantive_official_count = 0
    for item in evidence_items:
        if item.fetch_status != "ok":
            continue
        excerpt_len = len((item.body_excerpt or "").strip())
        source_refs.append(
            {
                "role": "evidence",
                "url": item.url,
                "title": item.title or item.url,
                "type": item.evidence_type,
            }
        )
        if item.reliability_rank >= 80:
            official_count += 1
            if excerpt_len >= SUBSTANTIVE_EVIDENCE_EXCERPT_CHARS:
                substantive_official_count += 1

    key_facts = []
    for ln in body.splitlines():
        ln = ln.strip()
        if len(ln) < 20 or CONTACT_LINE_RE.match(ln):
            continue
        if any(k in ln for k in ("협약", "의결", "발표", "시행", "공개", "의무", "%", "개월", "억")):
            key_facts.append(ln[:220])
        if len(key_facts) >= 6:
            break

    risk_flags: list[str] = []
    if substantive_official_count < 1:
        risk_flags.append("official_evidence_missing")
    if len(body) < THIN_SOURCE_BODY_CHARS:
        risk_flags.append("thin_source_body")
    if "협약" in body and "체결" in body and substantive_official_count < 1:
        risk_flags.append("announcement_only_risk")

    publish_grade = "D"
    if (
        len(body) >= MIN_BODY_CHARS_FOR_GRADE_A
        and substantive_official_count >= 2
        and len(key_facts) >= 3
    ):
        publish_grade = "A"
    elif (
        len(body) >= MIN_BODY_CHARS_FOR_GRADE_B
        and substantive_official_count >= 1
        and len(key_facts) >= 2
    ):
        publish_grade = "B"
    elif len(key_facts) >= 1 and len(body) >= 120:
        publish_grade = "C"

    if "announcement_only_risk" in risk_flags and publish_grade in ("A", "B"):
        publish_grade = "C"
    if "thin_source_body" in risk_flags and publish_grade in ("A", "B"):
        publish_grade = "C"

    placement_hint = "ledger"
    if publish_grade == "A":
        placement_hint = "secondary_lead"
    elif publish_grade == "B":
        placement_hint = "proof_row"

    return ResearchPacket(
        site=assigned_site,
        main_claim=main_claim,
        why_now=why_now,
        who_is_affected=_extract_who_affected(body),
        effective_date=_extract_effective_date(body),
        conditions=_bullet_conditions(body),
        exceptions=[],
        action_items=_extract_action_items(body),
        key_facts=key_facts,
        source_refs=source_refs,
        risk_flags=risk_flags,
        image_asset_tier="none",
        publish_grade=publish_grade,
        placement_hint=placement_hint,
        evidence_count=len([e for e in evidence_items if e.fetch_status == "ok"]),
        official_evidence_count=substantive_official_count,
    )


def assess_research_readiness(packet: ResearchPacket) -> dict[str, Any]:
    """Human-readable readiness report for probes and tests."""
    blockers = []
    if packet.publish_grade == "D":
        blockers.append("publish_grade_D")
    if "official_evidence_missing" in packet.risk_flags:
        blockers.append("need_more_official_sources")
    return {
        "ready_for_writing": packet.publish_grade in ("A", "B"),
        "publish_grade": packet.publish_grade,
        "placement_hint": packet.placement_hint,
        "official_evidence_count": packet.official_evidence_count,
        "risk_flags": packet.risk_flags,
        "blockers": blockers,
    }


def run_research_pipeline(
    raw_source: dict[str, Any],
    fetcher: Optional[Callable[[str], Any]] = None,
    *,
    assigned_site: str = "IJ",
    max_fetch: int = 3,
) -> dict[str, Any]:
    if fetcher is None:
        plan = build_evidence_plan(raw_source, assigned_site=assigned_site, max_fetch=max_fetch)
        evidence_items: list[EvidenceItem] = []
    else:
        plan, evidence_items = collect_evidence(
            raw_source, fetcher, assigned_site=assigned_site, max_fetch=max_fetch
        )
    packet = build_research_packet(raw_source, evidence_items, assigned_site=assigned_site)
    evidence_dicts = [asdict(e) for e in evidence_items]
    if fetcher is not None:
        from engine.pipeline.tier_c import collect_tier_c_evidence

        tier_c_rows = collect_tier_c_evidence(
            raw_source,
            evidence_dicts,
            packet.to_dict(),
            fetcher,
            max_fetch=int(__import__("os").environ.get("TIER_C_MAX_FETCH", "2")),
        )
        if tier_c_rows:
            for row in tier_c_rows:
                evidence_items.append(
                    EvidenceItem(
                        evidence_type=row.get("evidence_type", "tier_c"),
                        url=row.get("url", ""),
                        title=row.get("title", ""),
                        body_excerpt=row.get("body_excerpt", ""),
                        published_at=row.get("published_at"),
                        reliability_rank=int(row.get("reliability_rank") or 0),
                        collected_at=row.get("collected_at", _now_iso()),
                        fetch_status=row.get("fetch_status", "error"),
                    )
                )
            packet = build_research_packet(raw_source, evidence_items, assigned_site=assigned_site)
            evidence_dicts = [asdict(e) for e in evidence_items]
    return {
        "plan": {
            "assigned_site": plan.assigned_site,
            "raw_source_url": plan.raw_source_url,
            "link_candidates": [asdict(c) for c in plan.link_candidates],
            "fetch_targets": [asdict(c) for c in plan.fetch_targets],
            "notes": plan.notes,
        },
        "evidence": evidence_dicts,
        "packet": packet.to_dict(),
        "readiness": assess_research_readiness(packet),
    }
