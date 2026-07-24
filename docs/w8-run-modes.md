# Engine W8 run modes — exact commands & side effects

**Scope:** documentation + local scripts. Do not run operational DRAFT against production until W8 is approved.

## Daily limit semantics (blocking fix)

`DAILY_PUBLISH_LIMIT` counts **unique `auto_news_drafts.url_id` created today** (`DATE(created_at)` in KST day), including rows later marked `PUBLISHED`. It does **not** count live Portal PUBLISHED volume.

Any `url_id` present in `auto_news_drafts` (DRAFT or PUBLISHED) is excluded from the next collection set to prevent reprocessing / duplicate R2 uploads.

`scripts/w8-cron-runner.sh` holds `flock` for the entire SHA check → env load → `engine.py` (which reads today-count then creates drafts).

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

Exact keys required in `.env.w8` (any other value → abort):

```
PUBLISH_STATUS=DRAFT
REVIEW_ONLY=0
HIDDEN_PUBLISH_TEST=0
PER_RUN_LIMIT=3
DAILY_PUBLISH_LIMIT=9
PER_SITE_PER_RUN_LIMIT=1
ONE_SOURCE_ONE_SITE=1
REVALIDATE_FAILURE_WEBHOOK_CONFIGURED=1
```

| System | Change |
|--------|--------|
| Portal | ≤3 new DRAFTs/run, ≤9 unique drafts/day, ≤1/site/run; no auto PUBLISHED |
| R2 | image upload possible for new drafts only |
| GSC | none |

## Cron one-liner (no implicit env)

```cron
0 * * * * cd /root/erum-news-engine-w8 && APPROVED_ENGINE_SHA=<SHA> ENGINE_ENV_FILE=/root/erum-news-engine-w8/.env.w8 ./scripts/w8-cron-runner.sh >>/root/erum-news-engine-w8/cron.w8.log 2>&1
```
