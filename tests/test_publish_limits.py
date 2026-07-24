import pytest

from erum_pipeline.publish_limits import (
    all_enabled_sites_at_capacity,
    apply_per_site_run_limit,
    require_positive_int_env,
)


def test_require_positive_int_env_fail_closed_missing():
    with pytest.raises(RuntimeError, match="필요합니다"):
        require_positive_int_env("PER_RUN_LIMIT", env={})


def test_require_positive_int_env_rejects_zero_and_non_int():
    with pytest.raises(RuntimeError, match="1 이상"):
        require_positive_int_env("PER_RUN_LIMIT", env={"PER_RUN_LIMIT": "0"})
    with pytest.raises(RuntimeError, match="양의 정수"):
        require_positive_int_env("DAILY_PUBLISH_LIMIT", env={"DAILY_PUBLISH_LIMIT": "x"})


def test_require_positive_int_env_ok():
    assert require_positive_int_env("PER_RUN_LIMIT", env={"PER_RUN_LIMIT": "3"}) == 3
    assert require_positive_int_env("DAILY_PUBLISH_LIMIT", env={"DAILY_PUBLISH_LIMIT": "9"}) == 9


def test_apply_per_site_run_limit_disables_saturated_prefix():
    plan = {
        "IJ_": {"enabled": True, "mode": "primary", "reason": "one-source-one-site"},
        "NN_": {"enabled": True, "mode": "primary", "reason": "one-source-one-site"},
        "CB_": {"enabled": False, "mode": "skip", "reason": "not-assigned"},
    }
    apply_per_site_run_limit(plan, {"IJ_": 1, "NN_": 0, "CB_": 0}, per_site_limit=1)
    assert plan["IJ_"]["enabled"] is False
    assert plan["IJ_"]["reason"] == "per-site-run-limit"
    assert plan["NN_"]["enabled"] is True


def test_all_enabled_sites_at_capacity():
    flags = {"IJ": True, "NN": True, "CB": True}
    assert (
        all_enabled_sites_at_capacity(
            {"IJ_": 1, "NN_": 1, "CB_": 1},
            flags,
            1,
        )
        is True
    )
    assert (
        all_enabled_sites_at_capacity(
            {"IJ_": 1, "NN_": 0, "CB_": 1},
            flags,
            1,
        )
        is False
    )
