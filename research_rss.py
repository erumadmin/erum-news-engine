"""
RSS ingestion for research probes — mirrors engine.py collect_articles() input shape.

Production path: RSS summary -> raw source -> research -> (optional page enrich).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import feedparser

from research_collector import strip_html_tags

KST = ZoneInfo("Asia/Seoul")

# engine.RSS_FEEDS와 동일 (프로브 기본값)
DEFAULT_RSS_FEEDS: list[tuple[str, str, str]] = [
    ("https://www.korea.kr/rss/policy.xml", "정책브리핑-policy", "policy_briefing"),
    ("https://www.korea.kr/rss/dept_moef.xml", "정책브리핑-moef", "policy_briefing"),
    ("https://www.korea.kr/rss/dept_msit.xml", "정책브리핑-msit", "policy_briefing"),
    ("https://www.korea.kr/rss/dept_motir.xml", "정책브리핑-motir", "policy_briefing"),
    ("https://www.korea.kr/rss/dept_mw.xml", "정책브리핑-mw", "policy_briefing"),
    ("https://api.newswire.co.kr/rss/all", "뉴스와이어", "newswire"),
]


def extract_unique_id(url: str) -> str:
    """engine.extract_unique_id와 동일 규칙."""
    if not url:
        return ""
    cleaned = url.strip().split("#", 1)[0]
    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
    return cleaned[:500]


def feed_time_to_kst(dt: Optional[Any]) -> Optional[datetime]:
    if not dt:
        return None
    try:
        return datetime(*dt[:6], tzinfo=KST)
    except Exception:
        return None


def _entry_field(entry: Any, key: str, default: Any = "") -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def rss_entry_to_raw_source(
    entry: Any,
    *,
    feed_url: str,
    feed_name: str,
    source_type: str,
) -> dict[str, Any]:
    """feedparser entry -> research raw_source (engine collect_articles 필드 호환)."""
    link = (_entry_field(entry, "link") or "").strip()
    title = (_entry_field(entry, "title") or "")[:1000]
    rss_summary = _entry_field(entry, "summary") or _entry_field(entry, "description") or ""
    if isinstance(rss_summary, bytes):
        rss_summary = rss_summary.decode("utf-8", errors="replace")
    rss_summary = str(rss_summary)[:30000]

    body = strip_html_tags(rss_summary)[:30000]
    dt = _entry_field(entry, "published_parsed") or _entry_field(entry, "updated_parsed")
    source_published_at = feed_time_to_kst(dt)

    img_link = ""
    media = _entry_field(entry, "media_content") or []
    for mc in media:
        if isinstance(mc, dict) and "image" in mc.get("type", ""):
            img_link = mc.get("url", "") or ""
            break

    return {
        "url": link,
        "url_id": extract_unique_id(link),
        "title": title,
        "body": body,
        "rss_summary": rss_summary,
        "raw_html": rss_summary,
        "image": img_link,
        "source_type": source_type,
        "feed_url": feed_url,
        "feed_name": feed_name,
        "source_published_at": source_published_at.isoformat() if source_published_at else None,
    }


def ingest_rss_feed(
    feed_url: str,
    *,
    feed_name: str = "",
    source_type: str = "policy_briefing",
    limit: int = 5,
    fetcher: Callable[[str], Any],
    title_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    name = feed_name or feed_url.rsplit("/", 1)[-1]
    resp = fetcher(feed_url)
    status = getattr(resp, "status_code", None)
    if resp is None or (status is not None and status >= 400):
        raise RuntimeError(f"RSS fetch failed: {feed_url} (HTTP {status})")

    text = getattr(resp, "text", "") or ""
    if hasattr(resp, "encoding"):
        resp.encoding = "utf-8"
    parsed = feedparser.parse(text)

    out: list[dict[str, Any]] = []
    for entry in parsed.entries:
        if len(out) >= limit:
            break
        if not _entry_field(entry, "link"):
            continue
        raw = rss_entry_to_raw_source(
            entry,
            feed_url=feed_url,
            feed_name=name,
            source_type=source_type,
        )
        if title_filter and title_filter not in raw.get("title", ""):
            continue
        if not re.search(r"[가-힣]", raw.get("title", "")):
            continue
        out.append(raw)
    return out


def ingest_rss_feeds(
    feeds: list[tuple[str, str, str]],
    *,
    limit_total: int = 10,
    fetcher: Callable[[str], Any],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    per_feed = max(1, limit_total // max(len(feeds), 1))
    for feed_url, feed_name, source_type in feeds:
        if len(collected) >= limit_total:
            break
        try:
            batch = ingest_rss_feed(
                feed_url,
                feed_name=feed_name,
                source_type=source_type,
                limit=per_feed,
                fetcher=fetcher,
            )
            collected.extend(batch)
        except Exception:
            continue
    return collected[:limit_total]
