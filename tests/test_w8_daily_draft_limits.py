from datetime import date, datetime, timedelta

import pytest

from erum_pipeline.draft_lifecycle import (
    count_unique_drafts_created_on_date,
    ensure_draft_tracking_table,
    list_tracked_draft_url_ids,
    record_draft_mapping,
)
from erum_pipeline.publish_limits import compute_run_remaining
from erum_pipeline.w8_runner_env import (
    W8_EXACT_ENV,
    assert_env_file_secure,
    assert_w8_exact_values,
    load_w8_env_file,
    parse_env_file,
)


def test_compute_run_remaining_daily_and_per_run():
    assert compute_run_remaining(9, 9, 3) == 0
    assert compute_run_remaining(8, 9, 3) == 1
    assert compute_run_remaining(0, 9, 3) == 3
    assert compute_run_remaining(7, 9, 3) == 2


def test_w8_exact_values_reject_wrong_limits(tmp_path):
    env = dict(W8_EXACT_ENV)
    env["PER_RUN_LIMIT"] = "15"
    with pytest.raises(RuntimeError, match="PER_RUN_LIMIT"):
        assert_w8_exact_values(env)


def test_env_file_missing_and_mode(tmp_path):
    missing = tmp_path / "nope.env"
    with pytest.raises(RuntimeError, match="missing"):
        assert_env_file_secure(missing)

    bad_mode = tmp_path / "bad.env"
    bad_mode.write_text("PUBLISH_STATUS=DRAFT\n", encoding="utf-8")
    bad_mode.chmod(0o644)
    with pytest.raises(RuntimeError, match="mode must be 600"):
        assert_env_file_secure(bad_mode)


def test_load_w8_env_file_ok(tmp_path):
    path = tmp_path / ".env.w8"
    body = "\n".join(f"{k}={v}" for k, v in W8_EXACT_ENV.items())
    body += "\nREVALIDATE_FAILURE_WEBHOOK_CONFIGURED=1\nERUM_API_BASE=https://example.test\n"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    loaded = load_w8_env_file(path)
    assert loaded["PER_RUN_LIMIT"] == "3"
    assert loaded["DAILY_PUBLISH_LIMIT"] == "9"
    assert loaded["PER_SITE_PER_RUN_LIMIT"] == "1"
    parsed = parse_env_file(path)
    assert parsed["ERUM_API_BASE"] == "https://example.test"


@pytest.fixture(scope="module")
def mysql_conn():
    """Isolated local MySQL DB — skip if unavailable."""
    pymysql = pytest.importorskip("pymysql")
    try:
        root = pymysql.connect(
            host="127.0.0.1",
            user="root",
            password="",
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"local MySQL unavailable: {exc}")

    db_name = "erum_w8_limit_test"
    with root.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        cur.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4")
    root.select_db(db_name)
    yield root
    with root.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
    root.close()


def _insert_draft(cur, url_id: str, created_at: datetime, status: str = "DRAFT"):
    ensure_draft_tracking_table(cur)
    cur.execute(
        """
        INSERT INTO auto_news_drafts
          (url_id, site, article_id, status, created_at, updated_at)
        VALUES (%s, 'IJ', %s, %s, %s, %s)
        """,
        (url_id, abs(hash(url_id)) % 1_000_000 + 1, status, created_at, created_at),
    )


def test_mysql_daily_limit_and_exclusion(mysql_conn):
    today = date.today()
    yesterday = today - timedelta(days=1)
    with mysql_conn.cursor() as cur:
        ensure_draft_tracking_table(cur)
        # yesterday should not count toward today
        _insert_draft(cur, "src-yesterday", datetime.combine(yesterday, datetime.min.time()))
        assert count_unique_drafts_created_on_date(cur, today) == 0

        for i in range(8):
            _insert_draft(cur, f"src-today-{i}", datetime.combine(today, datetime.min.time()))
        # one of today's later published — still counts
        _insert_draft(
            cur,
            "src-today-pub",
            datetime.combine(today, datetime.min.time()),
            status="PUBLISHED",
        )
        assert count_unique_drafts_created_on_date(cur, today) == 9
        assert compute_run_remaining(9, 9, 3) == 0

        # reset day for 8-count case
        cur.execute("DELETE FROM auto_news_drafts WHERE url_id LIKE 'src-today%'")
        for i in range(8):
            _insert_draft(cur, f"src-today-{i}", datetime.combine(today, datetime.min.time()))
        assert count_unique_drafts_created_on_date(cur, today) == 8
        assert compute_run_remaining(8, 9, 3) == 1

        tracked = list_tracked_draft_url_ids(cur)
        assert "src-yesterday" in tracked
        assert "src-today-0" in tracked


def test_mysql_consecutive_runs_cap_at_nine(mysql_conn):
    """Simulate flock-serialized runs: 3+3+3 then block 10th creation."""
    today = date.today()
    created = 0
    with mysql_conn.cursor() as cur:
        cur.execute("DELETE FROM auto_news_drafts")
        ensure_draft_tracking_table(cur)

        def one_run():
            nonlocal created
            today_count = count_unique_drafts_created_on_date(cur, today)
            remaining = compute_run_remaining(today_count, 9, 3)
            for i in range(remaining):
                created += 1
                _insert_draft(
                    cur,
                    f"run-src-{created}",
                    datetime.combine(today, datetime.min.time()) + timedelta(seconds=created),
                )
            return remaining

        assert one_run() == 3
        assert one_run() == 3
        assert one_run() == 3
        assert one_run() == 0
        assert count_unique_drafts_created_on_date(cur, today) == 9
        assert created == 9
