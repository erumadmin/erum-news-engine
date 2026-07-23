import os
from erum_pipeline.staging_guards import assert_required_engine_env, resolve_r2_key

KEYS = [
    "ERUM_ENV", "ERUM_API_BASE", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME",
    "R2_BUCKET_NAME", "R2_PUBLIC_URL", "R2_KEY_PREFIX",
]


def _with_env(values, fn):
    prev = {k: os.environ.get(k) for k in KEYS}
    try:
        for k in KEYS:
            if k in values:
                if values[k] is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = values[k]
        return fn()
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_staging_rejects_production_api_and_db():
    def run():
        try:
            assert_required_engine_env()
            raise AssertionError("expected failure")
        except RuntimeError as exc:
            assert "staging 거부" in str(exc) or "production" in str(exc).lower()

    _with_env(
        {
            "ERUM_ENV": "staging",
            "ERUM_API_BASE": "https://erum-one.com",
            "DB_HOST": "64.176.227.225",
            "DB_USER": "u",
            "DB_PASSWORD": "p",
            "DB_NAME": "erum_company",
            "R2_BUCKET_NAME": None,
            "R2_PUBLIC_URL": None,
            "R2_KEY_PREFIX": None,
        },
        run,
    )


def test_staging_accepts_non_production():
    def run():
        cfg = assert_required_engine_env()
        assert "staging" in cfg["ERUM_API_BASE"] or "vercel.app" in cfg["ERUM_API_BASE"]
        assert resolve_r2_key("a.webp", "2026/07") == "news/2026/07/a.webp"

    _with_env(
        {
            "ERUM_ENV": "staging",
            "ERUM_API_BASE": "https://erum-company-website-git-staging.vercel.app",
            "DB_HOST": "staging-db.example.com",
            "DB_USER": "erum_staging",
            "DB_PASSWORD": "p",
            "DB_NAME": "erum_company_staging",
            "R2_BUCKET_NAME": "erum-news-images-staging",
            "R2_PUBLIC_URL": "https://staging-images.example.com",
            "R2_KEY_PREFIX": None,
        },
        run,
    )


def test_staging_shared_bucket_requires_prefix():
    def run():
        try:
            assert_required_engine_env()
            raise AssertionError("expected failure")
        except RuntimeError as exc:
            assert "R2_KEY_PREFIX" in str(exc) or "prefix" in str(exc).lower()

    _with_env(
        {
            "ERUM_ENV": "staging",
            "ERUM_API_BASE": "https://portal-staging.example.com",
            "DB_HOST": "staging-db.example.com",
            "DB_USER": "erum_staging",
            "DB_PASSWORD": "p",
            "DB_NAME": "erum_company_staging",
            "R2_BUCKET_NAME": "erum-news-images",
            "R2_PUBLIC_URL": "https://pub-dd677a54d7cf4d8cabd2c3238f4558c9.r2.dev",
            "R2_KEY_PREFIX": None,
        },
        run,
    )
