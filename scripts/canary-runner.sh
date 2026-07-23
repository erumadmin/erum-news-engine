#!/usr/bin/env bash
# Erum vNext canary / staging engine runner.
# IMPORTANT: This script must NEVER install or modify crontab.
# Do not run on Vultr production host /root/erum-news-engine.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${1:-}" == "--install-cron" ]]; then
  echo "Refused: canary runner must not install cron." >&2
  exit 2
fi

: "${ERUM_ENV:=staging}"
: "${PUBLISH_STATUS:=DRAFT}"
: "${HIDDEN_PUBLISH_TEST:=1}"
: "${REVIEW_ONLY:=0}"
export ERUM_ENV PUBLISH_STATUS HIDDEN_PUBLISH_TEST REVIEW_ONLY

# Fail closed if production endpoints are configured (Python guards also enforce).
python3 - <<'PY'
from erum_pipeline.staging_guards import assert_required_engine_env
print(assert_required_engine_env())
PY

echo "Starting one-shot canary run (no cron)..."
python3 engine.py
