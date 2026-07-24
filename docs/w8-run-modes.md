# Engine W8 run modes — exact commands & side effects

**Scope:** documentation + local scripts. Do not run operational DRAFT against production until W8 is approved.

## A. Dry-run / review (no writes)

```bash
cd /path/to/erum-news-engine   # approved checkout
export ERUM_ENV=staging          # or production only after W8 approval + read-only intent
export PUBLISH_STATUS=DRAFT
export REVIEW_ONLY=1
export HIDDEN_PUBLISH_TEST=0
export PER_RUN_LIMIT=3
export DAILY_PUBLISH_LIMIT=9
export PER_SITE_PER_RUN_LIMIT=1
export ONE_SOURCE_ONE_SITE=1
# plus ERUM_API_BASE / DB_* / LLM keys as required by staging_guards
./scripts/w8-dry-run.sh
# equivalent: REVIEW_ONLY=1 python3 engine.py
```

**Expected changes**

| System | Change |
|--------|--------|
| Portal DB articles | **none** (no create/publish) |
| Engine MariaDB success tables | **none** |
| R2 | **none** (image download/upload skipped in review mode) |
| Local disk | may write a review report file under the engine tree |

## B. Operational DRAFT candidate generation

```bash
cd /path/to/erum-news-engine   # HEAD must equal APPROVED_ENGINE_SHA
export ERUM_ENV=production       # only after W8 approval
export PUBLISH_STATUS=DRAFT
export REVIEW_ONLY=0
export HIDDEN_PUBLISH_TEST=0
export PER_RUN_LIMIT=3
export DAILY_PUBLISH_LIMIT=9
export PER_SITE_PER_RUN_LIMIT=1
export ONE_SOURCE_ONE_SITE=1
export APPROVED_ENGINE_SHA=<full-or-short-approved-sha>
export REVALIDATE_FAILURE_WEBHOOK_CONFIGURED=1  # only after Portal webhook is live
./scripts/w8-cron-runner.sh
```

**Expected changes (first cycle cap)**

| System | Change |
|--------|--------|
| Portal DB | up to **3 DRAFT** articles total; **≤1 per site** (IJ/NN/CB); status stays DRAFT; no auto-approve/publish |
| Engine MariaDB | attempt/state rows may update; success finalize only when statuses are PUBLISHED (so DRAFT-only runs typically skip success finalize) |
| R2 | image objects for created drafts (if image pipeline succeeds) |
| GSC | **none** |
| Customer 3-media fanout | **none** (`ONE_SOURCE_ONE_SITE=1`) |

Human Preview review + separate `/approve` + `/publish` required. Automation must assert `revalidation.ok=true` **and** `x-revalidation-status: ok` (admin retry failure = HTTP **502**).
