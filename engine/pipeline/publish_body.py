"""Assemble IJ publish body: sanitize prose, append sources footer, delegate gate."""

from __future__ import annotations

import html as _html
from typing import Any

from engine.pipeline.publish_validate import article_publish_ready, publish_sanitize_body


def render_sources_footer_html(footer: list[dict]) -> str:
    """Render sources_footer entries as an HTML block; empty list → no section."""
    if not footer:
        return ""
    items = []
    for entry in footer:
        url = (entry.get("url") or "").strip()
        if not url:
            continue
        label = (entry.get("label") or url).strip()
        items.append(
            f'<li><a href="{_html.escape(url)}">{_html.escape(label)}</a></li>'
        )
    if not items:
        return ""
    return (
        '<section class="ij-sources-footer">'
        "<h3>관련 링크</h3>"
        f"<ul>{''.join(items)}</ul>"
        "</section>"
    )


def prepare_ij_publish_body(
    title: str,
    excerpt: str,
    body_html: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sanitize body, run publish gate, append sources footer HTML."""
    body, footer = publish_sanitize_body(body_html, packet, article)
    gate = article_publish_ready(title, excerpt, body_html, packet, article)
    body += render_sources_footer_html(footer)
    return {
        "body_html": body,
        "publish_ready": gate["article_publish_ready"],
        "gate": gate,
        "sources_footer": footer,
    }
