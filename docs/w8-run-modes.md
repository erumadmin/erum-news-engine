# Engine W8 run modes — exact commands & side effects

**Scope:** documentation + local scripts. Do not run operational DRAFT against production until W8 is approved.

## Daily limit semantics (blocking fix)

`DAILY_PUBLISH_LIMIT` counts **unique `auto_news_drafts.url_id`** whose `created_at` falls in the KST half-open window **`[today 00:00, tomorrow 00:00)`**. Query uses `created_at >= start AND created_at < end` — **not** `DATE(created_at)` and **not** the DB session timezone. Rows later marked `PUBLISHED` still count.

`record_draft_mapping` writes an explicit **KST-naive** `created_at` (same policy). `ON DUPLICATE KEY UPDATE` does **not** rewrite `created_at`.

Any `url_id` present in `auto_news_drafts` (DRAFT or PUBLISHED) is excluded from the next collection set to prevent reprocessing / duplicate R2 uploads.

`scripts/w8-cron-runner.sh` holds `flock` for the entire SHA check → Python env load → `engine.py` (today-count then creates drafts). **No shell `source` of `.env.w8`.**

## Env loading (ops stability)

1. Bash runner only checks `APPROVED_ENGINE_SHA` + flock, then runs `python3 scripts/w8_run_engine.py`.
2. Python parses `ENGINE_ENV_FILE` (mode 600, owner check, exact 3/9/1 + production hosts), builds an env mapping, sets `ERUM_EXPLICIT_ENV_ONLY=1`, and runs `engine.py` via `subprocess` **without shell**.
3. With `ERUM_EXPLICIT_ENV_ONLY=1`, `engine.py` **never** reads cwd `.env`, `~/.env.erum_infra`, or other supplemental files. Missing keys are **not** filled from elsewhere — fail-closed.
4. Staging/preview/empty production values in `.env.w8` → abort. Secret values are never logged.

## A. Dry-run / review (no writes)

```bash
cd /path/to/erum-news-engine
export REVIEW_ONLY=1 PUBLISH_STATUS=DRAFT HIDDEN_PUBLISH_TEST=0
export PER_RUN_LIMIT=3 DAILY_PUBLISH_LIMIT=9 PER_SITE_PER_RUN_LIMIT=1 ONE_SOURCE_ONE_SITE=1
./scripts/w8-dry-run.sh
```

| System | Change |
|--------|--------|
| Portal DB / R2 / engine success | none |
| Local | optional review report |

## B. Operational DRAFT (W8 runner)

Requires explicit env file (never implicit cwd `.env` / shell profile):

```bash
# host prep (once)
install -m 600 -o root -g root /path/to/configs/w8.env.example /root/erum-news-engine-w8/.env.w8
# edit secrets; keep mode 600

cd /root/erum-news-engine-w8
export APPROVED_ENGINE_SHA=<approved-full-sha>
export ENGINE_ENV_FILE=/root/erum-news-engine-w8/.env.w8
./scripts/w8-cron-runner.sh
```

Exact keys required in `.env.w8` (see `configs/w8.env.example` / `erum_pipeline/w8_runner_env.py`):

```
PUBLISH_STATUS=DRAFT
REVIEW_ONLY=0
HIDDEN_PUBLISH_TEST=0
PER_RUN_LIMIT=3
DAILY_PUBLISH_LIMIT=9
PER_SITE_PER_RUN_LIMIT=1
ONE_SOURCE_ONE_SITE=1
ERUM_ENV=production
ERUM_API_BASE=https://erum-one.com
REVALIDATE_FAILURE_WEBHOOK_CONFIGURED=1
```

Plus non-empty: `ERUM_API_KEY` or `ADMIN_API_KEY`, `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`, R2 set, and LLM key for the chosen provider.

| System | Change |
|--------|--------|
| Portal | ≤3 new DRAFTs/run, ≤9 unique drafts/day, ≤1/site/run; no auto PUBLISHED |
| R2 | image upload possible for new drafts only |
| GSC | none |

## Cron one-liner (no implicit env)

```cron
0 * * * * cd /root/erum-news-engine-w8 && APPROVED_ENGINE_SHA=<SHA> ENGINE_ENV_FILE=/root/erum-news-engine-w8/.env.w8 ./scripts/w8-cron-runner.sh >>/root/erum-news-engine-w8/cron.w8.log 2>&1
```
