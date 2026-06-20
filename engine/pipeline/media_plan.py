"""Media prefix plan for editorial 1-source-1-site routing."""

from __future__ import annotations

import os
from typing import Any

MEDIA_PREFIXES = ("IJ_", "NN_", "CB_")
SITE_PREFIX_BY_CODE = {"IJ": "IJ_", "NN": "NN_", "CB": "CB_"}


def build_media_plan_for_editorial(
    editorial_ctx: Any,
    *,
    assess_cb_article_fit: Any | None = None,
    article: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    When editorial_ctx is set, enable only the routed site prefix (and CB reassess).
    """
    media_plan: dict[str, dict[str, Any]] = {
        prefix: {"enabled": False, "mode": "skip", "reason": "not_routed"}
        for prefix in MEDIA_PREFIXES
    }
    target_prefix = SITE_PREFIX_BY_CODE.get(editorial_ctx.assigned_site, "IJ_")
    media_plan[target_prefix] = {
        "enabled": True,
        "mode": "default",
        "reason": editorial_ctx.routing_reason,
    }
    if target_prefix == "CB_" and assess_cb_article_fit is not None and article is not None:
        force_site = os.environ.get("EDITORIAL_FORCE_SITE", "").strip().upper()
        if force_site == "CB":
            media_plan["CB_"] = {
                "enabled": True,
                "mode": "forced",
                "reason": "forced_site_cb",
            }
            return media_plan
        cb_mode, cb_reason = assess_cb_article_fit(article)
        media_plan["CB_"] = {
            "enabled": cb_mode != "skip",
            "mode": cb_mode,
            "reason": cb_reason or editorial_ctx.routing_reason,
        }
    return media_plan
