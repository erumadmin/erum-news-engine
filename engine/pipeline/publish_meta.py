from __future__ import annotations

from typing import Any


def build_publish_extras(editorial_ctx: Any) -> dict[str, Any]:
    if editorial_ctx is None:
        return {}
    return {
        "publish_grade": getattr(editorial_ctx, "publish_grade", None),
        "placement_slot": editorial_ctx.placement.slot,
        "editorial_score": editorial_ctx.placement.total,
    }
