"""Vercel Deployment Protection bypass for server-to-Portal API calls.

Uses env `VERCEL_AUTOMATION_BYPASS_SECRET` → header `x-vercel-protection-bypass`.
Never log the secret value.
"""
from __future__ import annotations

import os


def is_staging_env() -> bool:
    erum = (os.environ.get("ERUM_ENV") or "").strip().lower()
    if erum == "staging":
        return True
    if (os.environ.get("STAGING") or "").strip() == "1":
        return True
    return False


def portal_bypass_headers() -> dict[str, str]:
    """Return bypass headers for Portal Preview calls.

    Staging/preview requires the secret. Production/custom domains typically
    do not need it; empty return is allowed outside staging.
    """
    secret = (os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET") or "").strip()
    if secret:
        return {"x-vercel-protection-bypass": secret}
    if is_staging_env():
        raise RuntimeError(
            "staging 거부: VERCEL_AUTOMATION_BYPASS_SECRET가 필요합니다 "
            "(Portal Preview SSO bypass)."
        )
    return {}


def merge_portal_headers(base: dict[str, str] | None = None) -> dict[str, str]:
    out = dict(base or {})
    out.update(portal_bypass_headers())
    return out
