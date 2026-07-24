"""Fail-closed publish/run limit helpers for the news engine."""
from __future__ import annotations

import os
from typing import Mapping


def require_positive_int_env(
    name: str,
    env: Mapping[str, str] | None = None,
) -> int:
    """Read a required positive integer env var (no silent defaults)."""
    source = env if env is not None else os.environ
    raw = (source.get(name) or "").strip()
    if not raw:
        raise RuntimeError(f"{name} 환경변수가 필요합니다 (fail-closed).")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name}는 양의 정수여야 합니다 (got {raw!r}).") from exc
    if value < 1:
        raise RuntimeError(f"{name}는 1 이상이어야 합니다 (got {value}).")
    return value


def apply_per_site_run_limit(
    media_plan: dict,
    upload_counts: Mapping[str, int],
    per_site_limit: int,
) -> dict:
    """
    Disable any media prefix that already reached the per-site per-run cap.
    Mutates and returns media_plan.
    """
    for prefix, plan in list(media_plan.items()):
        if not plan.get("enabled", True):
            continue
        if int(upload_counts.get(prefix, 0)) >= per_site_limit:
            media_plan[prefix] = {
                "enabled": False,
                "mode": "skip",
                "reason": "per-site-run-limit",
            }
    return media_plan


def all_enabled_sites_at_capacity(
    upload_counts: Mapping[str, int],
    enable_flags: Mapping[str, bool],
    per_site_limit: int,
) -> bool:
    """True when every enabled site has already hit its per-run cap."""
    enabled_prefixes = []
    for site, flag in (("IJ", "IJ_"), ("NN", "NN_"), ("CB", "CB_")):
        if enable_flags.get(site, True):
            enabled_prefixes.append(flag)
    if not enabled_prefixes:
        return True
    return all(int(upload_counts.get(prefix, 0)) >= per_site_limit for prefix in enabled_prefixes)
