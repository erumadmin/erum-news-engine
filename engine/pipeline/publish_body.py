"""Assemble IJ publish body: sanitize prose, append sources footer, delegate gate."""

from __future__ import annotations

import html as _html
from typing import Any

from engine.pipeline.publish_validate import article_publish_ready, publish_sanitize_body


def render_sources_footer_html(footer: list[dict], *, section_class: str = "ij-sources-footer") -> str:
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
        f'<section class="{_html.escape(section_class, quote=True)}">'
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
    return _prepare_site_publish_body(title, excerpt, body_html, packet, article)


def prepare_nn_publish_body(
    title: str,
    excerpt: str,
    body_html: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
    *,
    score_total: float | None = None,
) -> dict[str, Any]:
    """Neighbor News publish body — same v4 gate as IJ, NN footer class."""
    return _prepare_site_publish_body(
        title,
        excerpt,
        body_html,
        packet,
        article,
        footer_class="nn-sources-footer",
        score_total=score_total,
    )


def prepare_cb_publish_body(
    title: str,
    excerpt: str,
    body_html: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
    *,
    score_total: float | None = None,
) -> dict[str, Any]:
    """CSR Briefing publish body - same v4 gate as IJ, CB footer class."""
    return _prepare_site_publish_body(
        title,
        excerpt,
        body_html,
        packet,
        article,
        footer_class="cb-sources-footer",
        score_total=score_total,
    )


def _prepare_site_publish_body(
    title: str,
    excerpt: str,
    body_html: str,
    packet: dict[str, Any],
    article: dict[str, Any] | None = None,
    *,
    footer_class: str = "ij-sources-footer",
    score_total: float | None = None,
) -> dict[str, Any]:
    body, footer = publish_sanitize_body(body_html, packet, article)
    gate = article_publish_ready(
        title, excerpt, body, packet, article, score_total=score_total
    )
    body += render_sources_footer_html(footer, section_class=footer_class)
    return {
        "body_html": body,
        "publish_ready": gate["article_publish_ready"],
        "gate": gate,
        "sources_footer": footer,
    }
