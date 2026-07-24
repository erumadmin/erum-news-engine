from erum_pipeline.vercel_bypass import is_staging_env, merge_portal_headers, portal_bypass_headers
import os
import pytest


def test_staging_requires_bypass(monkeypatch):
    monkeypatch.setenv("ERUM_ENV", "staging")
    monkeypatch.delenv("VERCEL_AUTOMATION_BYPASS_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="VERCEL_AUTOMATION_BYPASS_SECRET"):
        portal_bypass_headers()


def test_bypass_header_present(monkeypatch):
    monkeypatch.setenv("ERUM_ENV", "staging")
    monkeypatch.setenv("VERCEL_AUTOMATION_BYPASS_SECRET", "test-secret")
    headers = merge_portal_headers({"x-api-key": "k"})
    assert headers["x-vercel-protection-bypass"] == "test-secret"
    assert headers["x-api-key"] == "k"


def test_non_staging_without_secret_ok(monkeypatch):
    monkeypatch.setenv("ERUM_ENV", "production")
    monkeypatch.delenv("VERCEL_AUTOMATION_BYPASS_SECRET", raising=False)
    assert portal_bypass_headers() == {}
    assert is_staging_env() is False
