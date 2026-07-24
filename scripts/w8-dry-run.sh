#!/usr/bin/env bash
# Dry-run / review-only engine invocation (no DB success / no publish).
# Distinct from scripts/w8-cron-runner.sh operational DRAFT mode.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export REVIEW_ONLY=1
export PUBLISH_STATUS="${PUBLISH_STATUS:-DRAFT}"
export HIDDEN_PUBLISH_TEST="${HIDDEN_PUBLISH_TEST:-0}"
: "${PER_RUN_LIMIT:=3}"
: "${DAILY_PUBLISH_LIMIT:=9}"
: "${PER_SITE_PER_RUN_LIMIT:=1}"
export PER_RUN_LIMIT DAILY_PUBLISH_LIMIT PER_SITE_PER_RUN_LIMIT

echo "[dry-run] REVIEW_ONLY=1 — no publish, no DB success writes expected"
python3 - <<'PY'
from erum_pipeline.staging_guards import assert_required_engine_env
print(assert_required_engine_env())
PY
python3 engine.py
