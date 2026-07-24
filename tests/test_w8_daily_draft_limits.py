from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from erum_pipeline.draft_lifecycle import (
    count_unique_drafts_created_on_date,
    count_unique_drafts_in_kst_day,
    ensure_draft_tracking_table,
    list_tracked_draft_url_ids,
    record_draft_mapping,
)
from erum_pipeline.kst_time import KST, kst_naive_day_window, now_kst
from erum_pipeline.publish_limits import compute_run_remaining
from erum_pipeline.w8_runner_env import (
    W8_EXACT_ENV,
    assert_env_file_secure,
    assert_w8_exact_values,
    build_explicit_child_env,
    load_w8_env_file,
    parse_env_value,
)


def _valid_w8_body(**overrides: str) -> str:
    data = {
        **W8_EXACT_ENV,
        "DB_HOST": "db.prod.erum.example",
        "DB_PORT": "3306",
        "DB_USER": "erum",
        "DB_PASSWORD": "plain-secret",
        "DB_NAME": "erum_news",
        "ERUM_API_KEY": "portal-api-key",
        "R2_ACCOUNT_ID": "acct123",
        "R2_ACCESS_KEY_ID": "AKIAEXAMPLE",
        "R2_SECRET_ACCESS_KEY": "r2secret",
        "R2_BUCKET_NAME": "erum-media",
        "R2_PUBLIC_URL": "https://cdn.erum.example",
        "LLM_PROVIDER": "upstage",
        "UPSTAGE_API_KEY": "upstage-key",
    }
    data.update(overrides)
    return "\n".join(f"{k}={v}" for k, v in data.items()) + "\n"


def _write_w8_env(tmp_path: Path, **overrides: str) -> Path:
    path = tmp_path / ".env.w8"
    path.write_text(_valid_w8_body(**overrides), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_compute_run_remaining_daily_and_per_run():
    assert compute_run_remaining(9, 9, 3) == 0
    assert compute_run_remaining(8, 9, 3) == 1
    assert compute_run_remaining(0, 9, 3) == 3
    assert compute_run_remaining(7, 9, 3) == 2


def test_w8_exact_values_reject_wrong_limits():
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
    path = _write_w8_env(tmp_path)
    loaded = load_w8_env_file(path)
    assert loaded["PER_RUN_LIMIT"] == "3"
    assert loaded["DAILY_PUBLISH_LIMIT"] == "9"
    assert loaded["PER_SITE_PER_RUN_LIMIT"] == "1"
    assert loaded["ERUM_ENV"] == "production"
    assert loaded["ERUM_API_BASE"] == "https://erum-one.com"


def test_reject_staging_api_and_db(tmp_path):
    path = _write_w8_env(tmp_path, ERUM_API_BASE="https://erum-staging.vercel.app")
    with pytest.raises(RuntimeError, match="ERUM_API_BASE"):
        load_w8_env_file(path)

    path2 = tmp_path / ".env.w8.stagingdb"
    path2.write_text(_valid_w8_body(DB_NAME="erum_staging"), encoding="utf-8")
    path2.chmod(0o600)
    with pytest.raises(RuntimeError, match="DB_NAME"):
        load_w8_env_file(path2)


def test_reject_empty_secret_without_logging_value(tmp_path):
    path = _write_w8_env(tmp_path, DB_PASSWORD="")
    with pytest.raises(RuntimeError, match="DB_PASSWORD") as ei:
        load_w8_env_file(path)
    assert "empty" in str(ei.value)
    # must not echo a secret payload
    assert "plain-secret" not in str(ei.value)


def test_parse_env_value_preserves_special_chars():
    assert parse_env_value('p$ass #word "q"t`x\\z') == 'p$ass #word "q"t`x\\z'
    assert parse_env_value("'keep $HOME #x'") == "keep $HOME #x"
    assert parse_env_value('"a\'b`c\\\\d"') == "a'b`c\\\\d"


def test_special_chars_reach_engine_child_process(tmp_path):
    """$, space, #, quotes, backtick, backslash must reach the child env unchanged."""
    password = 'p$ass #word "q"t`x\\z'
    api_key = "k$1 #2 '3`4\\5"
    path = _write_w8_env(tmp_path, DB_PASSWORD=password, ERUM_API_KEY=api_key)
    # Ensure raw file lines are unquoted (parser must not shell-expand).
    raw = path.read_text(encoding="utf-8")
    assert f"DB_PASSWORD={password}" in raw
    assert f"ERUM_API_KEY={api_key}" in raw

    parsed = load_w8_env_file(path)
    assert parsed["DB_PASSWORD"] == password
    assert parsed["ERUM_API_KEY"] == api_key

    child = build_explicit_child_env(parsed)
    assert child["ERUM_EXPLICIT_ENV_ONLY"] == "1"
    assert child["DB_PASSWORD"] == password
    assert child["ERUM_API_KEY"] == api_key
    # Parent shell secrets must not fill missing keys — child only inherits PATH/etc.
    assert "ADMIN_API_KEY" not in child or "ADMIN_API_KEY" in parsed

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,os; print(json.dumps({"
            "'DB_PASSWORD': os.environ.get('DB_PASSWORD'),"
            "'ERUM_API_KEY': os.environ.get('ERUM_API_KEY'),"
            "'ERUM_EXPLICIT_ENV_ONLY': os.environ.get('ERUM_EXPLICIT_ENV_ONLY'),"
            "}))",
        ],
        env=child,
        capture_output=True,
        text=True,
        check=True,
    )
    got = json.loads(probe.stdout)
    assert got["DB_PASSWORD"] == password
    assert got["ERUM_API_KEY"] == api_key
    assert got["ERUM_EXPLICIT_ENV_ONLY"] == "1"


def test_explicit_child_env_does_not_inherit_parent_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PASSWORD", "from-parent-should-not-win")
    monkeypatch.setenv("UPSTAGE_API_KEY", "parent-upstage")
    path = _write_w8_env(tmp_path, DB_PASSWORD="from-file", UPSTAGE_API_KEY="from-file-llm")
    parsed = load_w8_env_file(path)
    child = build_explicit_child_env(parsed)
    assert child["DB_PASSWORD"] == "from-file"
    assert child["UPSTAGE_API_KEY"] == "from-file-llm"


def test_kst_day_window_half_open():
    late = datetime(2026, 7, 24, 23, 59, tzinfo=KST)
    early = datetime(2026, 7, 25, 0, 1, tzinfo=KST)
    s1, e1 = kst_naive_day_window(late)
    s2, e2 = kst_naive_day_window(early)
    assert s1 == datetime(2026, 7, 24, 0, 0, 0)
    assert e1 == datetime(2026, 7, 25, 0, 0, 0)
    assert s2 == datetime(2026, 7, 25, 0, 0, 0)
    assert e2 == datetime(2026, 7, 26, 0, 0, 0)


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
    today = now_kst().date()
    yesterday = today - timedelta(days=1)
    with mysql_conn.cursor() as cur:
        ensure_draft_tracking_table(cur)
        cur.execute("DELETE FROM auto_news_drafts")
        _insert_draft(cur, "src-yesterday", datetime.combine(yesterday, datetime.min.time()))
        assert count_unique_drafts_created_on_date(cur, today) == 0

        for i in range(8):
            _insert_draft(cur, f"src-today-{i}", datetime.combine(today, datetime.min.time()))
        _insert_draft(
            cur,
            "src-today-pub",
            datetime.combine(today, datetime.min.time()),
            status="PUBLISHED",
        )
        assert count_unique_drafts_created_on_date(cur, today) == 9
        assert compute_run_remaining(9, 9, 3) == 0

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
    today = now_kst().date()
    created = 0
    with mysql_conn.cursor() as cur:
        ensure_draft_tracking_table(cur)
        cur.execute("DELETE FROM auto_news_drafts")

        def one_run():
            nonlocal created
            today_count = count_unique_drafts_created_on_date(cur, today)
            remaining = compute_run_remaining(today_count, 9, 3)
            for _i in range(remaining):
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


def test_mysql_kst_boundary_and_utc_session(mysql_conn):
    """KST 23:59 counts for that day; 00:01 next day resets. Independent of DB session TZ."""
    with mysql_conn.cursor() as cur:
        ensure_draft_tracking_table(cur)
        cur.execute("DELETE FROM auto_news_drafts")
        cur.execute("SET time_zone = '+00:00'")

        late_now = datetime(2026, 7, 24, 23, 59, tzinfo=KST)
        early_now = datetime(2026, 7, 25, 0, 1, tzinfo=KST)

        _insert_draft(cur, "kst-2359", datetime(2026, 7, 24, 23, 59, 0))
        assert count_unique_drafts_in_kst_day(cur, late_now) == 1
        assert count_unique_drafts_in_kst_day(cur, early_now) == 0

        _insert_draft(cur, "kst-0001", datetime(2026, 7, 25, 0, 1, 0))
        assert count_unique_drafts_in_kst_day(cur, early_now) == 1
        assert count_unique_drafts_in_kst_day(cur, late_now) == 1

        # record_draft_mapping uses explicit KST-naive created_at; ON DUPLICATE keeps it.
        record_draft_mapping(
            cur,
            url_id="map-1",
            site="IJ",
            article_id=42,
            created_at=datetime(2026, 7, 24, 23, 58, 0),
        )
        record_draft_mapping(
            cur,
            url_id="map-1",
            site="IJ",
            article_id=42,
            created_at=datetime(2026, 7, 25, 12, 0, 0),  # must NOT overwrite created_at
        )
        cur.execute("SELECT created_at FROM auto_news_drafts WHERE url_id='map-1'")
        row = cur.fetchone()
        created = row["created_at"] if isinstance(row, dict) else row[0]
        assert created == datetime(2026, 7, 24, 23, 58, 0)
        assert count_unique_drafts_in_kst_day(cur, late_now) == 2  # kst-2359 + map-1
