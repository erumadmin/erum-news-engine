"""Non-blocking image discovery for REVIEW_ONLY / preflight (no publish)."""

from __future__ import annotations

from typing import Any

from engine.pipeline.article_images import require_article_image


def probe_article_images(article: dict[str, Any], *, download: bool = False) -> dict[str, Any]:
    """Non-blocking wrapper around require_article_image for preflight/review."""
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
        result = require_article_image(article, download=download)
        out["status"] = result["image_status"]
        out["selected_url"] = result["selected_url"] or ""
        out["caption"] = result.get("caption")
        out["download_ok"] = result["image_status"] == "download_ok"
        if result.get("img_bytes"):
            out["bytes_kb"] = len(result["img_bytes"]) // 1024
    except Exception as exc:
        code = getattr(exc, "code", "IMAGE_PROBE_EXCEPTION")
        message = getattr(exc, "message", str(exc))[:300]
        out["status"] = "error" if "FETCH" in code or "EXCEPTION" in code else "download_failed"
        out["code"] = code
        out["message"] = message
    return out
