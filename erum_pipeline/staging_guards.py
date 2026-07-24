"""Staging / production endpoint guards for the news engine."""
from __future__ import annotations

import os
from urllib.parse import urlparse

PRODUCTION_API_HOSTS = {"erum-one.com", "www.erum-one.com"}
PRODUCTION_DB_HOSTS = {"64.176.227.225"}
PRODUCTION_DB_NAMES = {"erum_company"}
PRODUCTION_R2_BUCKETS = {"erum-news-images"}
PRODUCTION_R2_PUBLIC_HOSTS = {"pub-dd677a54d7cf4d8cabd2c3238f4558c9.r2.dev"}


def resolve_erum_env() -> str:
    raw = (os.environ.get("ERUM_ENV") or "").strip().lower()
    if raw in {"staging", "production", "local", "test"}:
        return raw
    if (os.environ.get("STAGING") or "").strip() == "1":
        return "staging"
    if (os.environ.get("HIDDEN_PUBLISH_TEST") or "").strip() == "1":
        return "staging"
    return "production"


def is_staging_env(erum_env: str | None = None) -> bool:
    return (erum_env or resolve_erum_env()) == "staging"


def _host(url_or_host: str) -> str:
    value = (url_or_host or "").strip()
    if not value:
        return ""
    if "://" not in value:
        return value.lower().split(":")[0]
    return (urlparse(value).hostname or "").lower()


def assert_required_engine_env() -> dict[str, str]:
    missing = [k for k in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME", "ERUM_API_BASE") if not (os.environ.get(k) or "").strip()]
    if missing:
        raise RuntimeError(f"필수 환경변수 누락: {', '.join(missing)}")

    api_base = os.environ["ERUM_API_BASE"].strip().rstrip("/")
    db_host = os.environ["DB_HOST"].strip()
    db_name = os.environ["DB_NAME"].strip()
    erum_env = resolve_erum_env()

    if is_staging_env(erum_env):
        api_host = _host(api_base)
        if api_host in PRODUCTION_API_HOSTS or "erum-one.com" in api_base.lower():
            raise RuntimeError("staging 거부: ERUM_API_BASE가 production(erum-one.com)을 가리킵니다.")
        if db_host in PRODUCTION_DB_HOSTS:
            raise RuntimeError("staging 거부: DB_HOST가 production Vultr(64.176.227.225)입니다.")
        if db_name in PRODUCTION_DB_NAMES:
            raise RuntimeError("staging 거부: DB_NAME이 production(erum_company)입니다.")

        bucket = (os.environ.get("R2_BUCKET_NAME") or "").strip()
        prefix = (os.environ.get("R2_KEY_PREFIX") or "").strip().strip("/")
        public_url = (os.environ.get("R2_PUBLIC_URL") or "").strip()
        if bucket:
            if bucket in PRODUCTION_R2_BUCKETS and not prefix.startswith("staging"):
                raise RuntimeError(
                    "staging 거부: production R2 bucket(erum-news-images)을 쓰려면 R2_KEY_PREFIX=staging/... 가 필요합니다."
                )
        if public_url and _host(public_url) in PRODUCTION_R2_PUBLIC_HOSTS and not prefix.startswith("staging"):
            raise RuntimeError(
                "staging 거부: production R2 public URL 사용 시 R2_KEY_PREFIX=staging/... 가 필요합니다."
            )

    return {
        "ERUM_ENV": erum_env,
        "ERUM_API_BASE": api_base,
        "DB_HOST": db_host,
        "DB_NAME": db_name,
    }


def resolve_r2_key(filename: str, yyyymm: str) -> str:
    prefix = (os.environ.get("R2_KEY_PREFIX") or "").strip().strip("/")
    bucket = (os.environ.get("R2_BUCKET_NAME") or "").strip()
    base = f"news/{yyyymm}/{filename}"
    if prefix:
        return f"{prefix}/{base}"
    if is_staging_env():
        if not bucket:
            raise RuntimeError("staging에서는 R2_BUCKET_NAME이 필요합니다.")
        if bucket in PRODUCTION_R2_BUCKETS:
            raise RuntimeError(
                "staging에서 production R2 bucket을 쓰려면 R2_KEY_PREFIX=staging/... 가 필요합니다."
            )
    return base
