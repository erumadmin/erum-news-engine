"""Shared HTML allowlist sanitizer for published article bodies (stored XSS)."""

from __future__ import annotations

import nh3

ALLOWED_TAGS = {"p", "strong", "em", "br", "h3", "h4", "a", "ul", "ol", "li", "img", "blockquote"}
ALLOWED_ATTRS = {
    "a": {"href", "title", "rel"},
    "img": {"src", "alt", "caption"},
}
ALLOWED_URL_SCHEMES = {"https", "http"}


def sanitize_article_html(html: str) -> str:
    if not html:
        return ""
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        link_rel=None,
        url_schemes=ALLOWED_URL_SCHEMES,
    )
