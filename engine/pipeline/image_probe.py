"""Non-blocking image discovery for REVIEW_ONLY / preflight (no publish)."""

from __future__ import annotations

from typing import Any

from engine.pipeline.article_images import (
    PipelineFailure,
    download_best_image,
    find_best_image,
)


def probe_article_images(article: dict[str, Any], *, download: bool = False) -> dict[str, Any]:
    """Non-blocking image probe for preflight/review. Uses article_images functions."""
    out: dict[str, Any] = {
        "status": "pending",
        "candidates": [],
        "selected_url": "",
        "selected_source": "",
        "caption": None,
        "download_ok": False,
        "bytes_kb": 0,
        "code": "",
        "message": "",
    }
    try:
        candidates = find_best_image(article)
    except PipelineFailure as failure:
        out["status"] = "error"
        out["code"] = failure.code
        out["message"] = failure.message
        return out
    except Exception as exc:
        out["status"] = "error"
        out["code"] = "IMAGE_PROBE_EXCEPTION"
        out["message"] = str(exc)[:300]
        return out

    if not candidates:
        out["status"] = "no_candidates"
        out["code"] = "NO_USABLE_IMAGE"
        out["message"] = "이미지 후보 없음"
        return out

    out["candidates"] = [
        {"url": c.url, "source": c.source, "score": c.score, "caption": c.caption}
        for c in candidates[:8]
    ]
    best = candidates[0]
    out["selected_url"] = best.url
    out["selected_source"] = best.source
    out["caption"] = best.caption
    out["status"] = "candidates_ok"

    if not download:
        return out

    try:
        img_bytes, _ct, _fn, cap, url = download_best_image(candidates)
        out["download_ok"] = True
        out["bytes_kb"] = len(img_bytes) // 1024
        out["selected_url"] = url or best.url
        out["caption"] = cap or best.caption
        out["status"] = "download_ok"
    except PipelineFailure as failure:
        out["status"] = "download_failed"
        out["code"] = failure.code
        out["message"] = failure.message
    except Exception as exc:
        out["status"] = "download_failed"
        out["code"] = "IMAGE_DOWNLOAD_EXCEPTION"
        out["message"] = str(exc)[:300]
    return out
