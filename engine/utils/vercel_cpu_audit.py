from __future__ import annotations

import json
from typing import Any


def extract_team_softblock(payload: dict[str, Any], slug: str) -> dict[str, Any]:
    for team in payload.get("teams", []):
        if team.get("slug") != slug:
            continue
        soft_block = team.get("softBlock") or {}
        billing = team.get("billing") or {}
        return {
            "slug": slug,
            "status": "found",
            "billing_status": billing.get("status"),
            "soft_block_reason": soft_block.get("reason"),
            "soft_block_overage_type": soft_block.get("blockedDueToOverageType"),
            "soft_block": soft_block or None,
        }
    return {"slug": slug, "status": "missing"}


def classify_http_probe(url: str, status_code: int, headers: dict[str, str], body_text: str) -> dict[str, Any]:
    vercel_error = headers.get("x-vercel-error") or headers.get("X-Vercel-Error")
    if status_code == 402 and vercel_error == "DEPLOYMENT_DISABLED":
        return {
            "url": url,
            "status": "blocked",
            "reason": "DEPLOYMENT_DISABLED",
            "status_code": status_code,
        }
    if status_code >= 400:
        return {
            "url": url,
            "status": "error",
            "reason": vercel_error or body_text[:120],
            "status_code": status_code,
        }
    return {
        "url": url,
        "status": "ok",
        "status_code": status_code,
    }


def summarize_article_api_result(url: str, status_code: int, headers: dict[str, str], body_text: str) -> dict[str, Any]:
    classified = classify_http_probe(url, status_code, headers, body_text)
    if classified["status"] != "ok":
        return {**classified, "json_ok": False}

    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError:
        return {
            **classified,
            "status": "error",
            "reason": "invalid_json",
            "json_ok": False,
        }

    return {
        **classified,
        "json_ok": isinstance(payload, dict) and "articles" in payload,
        "article_count": len(payload.get("articles", [])) if isinstance(payload, dict) else None,
    }
