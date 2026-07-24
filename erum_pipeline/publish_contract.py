"""Article API payload helpers for vNext."""
from __future__ import annotations

from typing import Any, Optional


def build_article_payload(
    *,
    site_code: str,
    title: str,
    body: str,
    cat_id: int,
    status: str,
    img_url: Optional[str] = None,
    excerpt: str = "",
    author: Optional[str] = None,
    author_slug: Optional[str] = None,
    image_caption: Optional[str] = None,
    image_credit: Optional[str] = None,
    image_source: Optional[str] = None,
    image_rights_basis: Optional[str] = None,
    image_is_fallback: Optional[bool] = None,
    source_url: Optional[str] = None,
    published_at: Optional[str] = None,
    source_published_at: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    engine_commit: Optional[str] = None,
    prompt_version: Optional[str] = None,
    normalized_source_id: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "site": site_code,
        "title": title,
        "content": body,
        "excerpt": excerpt or "",
        "status": status,
        "categoryId": cat_id,
        "featuredImageUrl": img_url,
        "publishedAt": published_at,
        "provenanceChannel": "AUTO_NEWS",
    }
    optional = {
        "author": author,
        "authorSlug": author_slug,
        "imageCaption": image_caption,
        "imageCredit": image_credit,
        "imageSource": image_source,
        "imageRightsBasis": image_rights_basis,
        "imageIsFallback": image_is_fallback,
        "sourceUrl": source_url,
        "sourcePublishedAt": source_published_at,
        "idempotencyKey": idempotency_key,
        "engineCommit": engine_commit,
        "promptVersion": prompt_version,
        "normalizedSourceId": normalized_source_id,
    }
    for k, v in optional.items():
        if v is not None:
            payload[k] = v
    if payload.get("sourcePublishedAt") is None:
        payload.pop("sourcePublishedAt", None)
    return payload


def should_record_published_success(status: str) -> bool:
    return status == "PUBLISHED"
