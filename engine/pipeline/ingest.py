"""Raw source page enrichment — RSS summary is not enough for editorial pipeline."""

from __future__ import annotations

from typing import Any, Callable, Optional, Tuple

from bs4 import BeautifulSoup

from research_collector import strip_html_tags

# 설계: 정책브리핑 RSS만으로는 부족, 전문 본문 최소 길이
MIN_SOURCE_BODY_CHARS = int(__import__("os").environ.get("MIN_SOURCE_BODY_CHARS", "400"))

KOREA_KR_BODY_SELECTORS = (
    ".view_cont",
    "#articleBody",
    ".article-content",
    ".news_view",
    "article",
    ".content",
)

NEWSWIRE_BODY_SELECTORS = (
    ".release-body2",
    ".news-read-column",
    "section.article_column",
    ".news-release2",
)


def parse_article_page(html: str, *, page_url: str = "") -> tuple[str, str, str]:
    """HTML -> (title, plain body, raw_html snippet for link discovery)."""
    soup = BeautifulSoup(html or "", "html.parser")
    title = ""
    h1 = soup.select_one("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"}) or soup.find(
            "meta", attrs={"name": "og:title"}
        )
        if og and og.get("content"):
            title = str(og.get("content", "")).strip()

    body_node = None
    selectors = KOREA_KR_BODY_SELECTORS
    if "newswire.co.kr" in (page_url or ""):
        selectors = NEWSWIRE_BODY_SELECTORS + KOREA_KR_BODY_SELECTORS
    for sel in selectors:
        body_node = soup.select_one(sel)
        if body_node:
            break
    body = body_node.get_text(separator="\n", strip=True) if body_node else strip_html_tags(html)
    max_body = int(__import__("os").environ.get("INGEST_MAX_BODY_CHARS", "500000"))
    max_html = int(__import__("os").environ.get("INGEST_MAX_HTML_CHARS", "500000"))
    return title[:1000], body[:max_body], html[:max_html]


def _min_body_chars(override: int) -> int:
    return int(__import__("os").environ.get("MIN_SOURCE_BODY_CHARS", str(override)))


def enrich_article_from_page(
    article: dict[str, Any],
    fetcher: Optional[Callable[[str], Any]],
    *,
    min_body_chars: int = MIN_SOURCE_BODY_CHARS,
    require_fetch: bool = False,
) -> Tuple[bool, dict[str, Any], str]:
    min_body_chars = _min_body_chars(min_body_chars)
    """
    Fetch source URL and replace title/body/raw_html when successful.

    Returns (ok, article, reason).
    require_fetch=True → fetch 실패 또는 본문 부족 시 ok=False (조용히 RSS 유지 금지).
    """
    url = (article.get("url") or "").strip()
    if not url:
        return False, article, "missing_url"
    if fetcher is None:
        out = dict(article)
        body = (out.get("body") or "").strip()
        html = out.get("raw_html") or ""
        if len(body) < min_body_chars and html:
            expanded = strip_html_tags(html)
            if len(expanded) > len(body):
                body = expanded
                out["body"] = body
                out["ingest_source"] = "raw_html_fallback"
        body_len = len(body)
        if require_fetch:
            return False, out, "fetcher_required"
        if body_len < min_body_chars:
            return False, out, f"thin_body_no_fetch:{body_len}"
        return True, out, f"rss_only:{body_len}"

    resp = fetcher(url)
    status = getattr(resp, "status_code", None)
    if resp is None or (status is not None and status >= 400):
        code = status or "none"
        if require_fetch:
            return False, article, f"fetch_failed:http_{code}"
        body_len = len((article.get("body") or "").strip())
        return (
            (body_len >= min_body_chars),
            article,
            f"fetch_failed_fallback_rss:{body_len}",
        )

    html = getattr(resp, "text", "") or ""
    if hasattr(resp, "encoding"):
        resp.encoding = "utf-8"
    live_title, live_body, _ = parse_article_page(html, page_url=url)
    if not live_body.strip():
        if require_fetch:
            return False, article, "empty_body_after_parse"
        return False, article, "empty_body_after_parse"

    out = dict(article)
    if live_title:
        out["title"] = live_title
    out["body"] = live_body
    out["raw_html"] = html
    out["ingest_source"] = "full_page"

    if len(live_body) < min_body_chars:
        return False, out, f"thin_body:{len(live_body)}"

    return True, out, f"full_page:{len(live_body)}"


def enrich_articles_batch(
    articles: list[dict[str, Any]],
    fetcher: Callable[[str], Any],
    *,
    min_body_chars: int = MIN_SOURCE_BODY_CHARS,
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for article in articles:
        ok, enriched, reason = enrich_article_from_page(
            article,
            fetcher,
            min_body_chars=min_body_chars,
            require_fetch=False,
        )
        title_preview = (enriched.get("title") or "")[:40]
        if ok:
            print(f"      ✅ [원문보강] {title_preview}… ({reason})")
            kept.append(enriched)
        else:
            print(f"      ⏭️ [원문보강] 스킵 {title_preview}… ({reason})")
    return kept
