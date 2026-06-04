"""Layout / hero decision from image probe (image failure ≠ text failure)."""

from __future__ import annotations

from typing import Any, Literal

LayoutType = Literal["hero", "card", "list", "brief"]


def decide_layout_type(
    image_probe: dict[str, Any] | None,
    *,
    placement_slot: str = "ledger",
    publish_grade: str = "C",
) -> LayoutType:
    """
    Map image availability + editorial placement to front layout slot.

    Policy (research-pipeline): missing image → list/brief, not abort publish.
    """
    probe = image_probe or {}
    status = probe.get("status", "")
    has_safe_image = status == "download_ok" or (
        status == "candidates_ok" and bool(probe.get("selected_url"))
    )

    if has_safe_image and placement_slot == "hero" and publish_grade in ("A", "B"):
        return "hero"
    if has_safe_image and placement_slot in ("hero", "secondary_lead"):
        return "card"
    if has_safe_image:
        return "list"
    if placement_slot in ("hero", "secondary_lead"):
        return "brief"
    return "list"
