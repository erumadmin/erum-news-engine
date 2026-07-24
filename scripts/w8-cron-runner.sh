#!/usr/bin/env bash
# W8 / production Engine cron runner (Vultr).
#
# - NEVER git pull
# - Run only from a fixed checkout whose HEAD matches APPROVED_ENGINE_SHA
# - flock against duplicate runs
# - Fail closed on missing env / wrong SHA
#
# This script does NOT install or modify crontab. Ops installs one crontab line
# that calls this script after backup + approval.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOCK_FILE="${ENGINE_CRON_LOCK_FILE:-/var/lock/erum-news-engine.w8.lock}"
LOG_FILE="${ENGINE_CRON_LOG_FILE:-$ROOT/cron.w8.log}"
APPROVED_SHA="${APPROVED_ENGINE_SHA:-}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

log() {
  echo "[$(ts)] $*" | tee -a "$LOG_FILE"
}

die() {
  log "ERROR: $*"
  exit 1
}

# --- flock (non-blocking): exit 0 if another run holds the lock ---
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "SKIP: another engine run holds $LOCK_FILE"
  exit 0
fi

log "START root=$ROOT"

# --- SHA pin ---
[[ -n "$APPROVED_SHA" ]] || die "APPROVED_ENGINE_SHA is required"
HEAD="$(git rev-parse HEAD)"
# Accept full SHA equality or approved short SHA as unique prefix of HEAD.
if [[ "$HEAD" != "$APPROVED_SHA" && "$HEAD" != "$APPROVED_SHA"* ]]; then
  die "HEAD $HEAD != APPROVED_ENGINE_SHA $APPROVED_SHA (refusing to run; no git pull)"
fi
log "SHA_OK head=$HEAD approved=$APPROVED_SHA"

# --- Required env (fail closed) ---
require_env() {
  local k="$1"
  [[ -n "${!k:-}" ]] || die "missing required env: $k"
}

require_env PUBLISH_STATUS
require_env PER_RUN_LIMIT
require_env DAILY_PUBLISH_LIMIT
require_env PER_SITE_PER_RUN_LIMIT
require_env ERUM_API_BASE
require_env ONE_SOURCE_ONE_SITE

[[ "${PUBLISH_STATUS}" == "DRAFT" ]] || die "PUBLISH_STATUS must be DRAFT for W8 cron (got ${PUBLISH_STATUS})"
[[ "${ONE_SOURCE_ONE_SITE}" == "1" ]] || die "ONE_SOURCE_ONE_SITE must be 1 (customer 3-media fanout forbidden)"
[[ "${REVIEW_ONLY:-0}" == "0" ]] || die "REVIEW_ONLY must be 0 for operational DRAFT cron (use separate dry-run)"
[[ "${HIDDEN_PUBLISH_TEST:-0}" == "0" ]] || die "HIDDEN_PUBLISH_TEST must be 0 for operational DRAFT cron"

# Portal-side gate mirrored as ops flag: cron must not start without webhook configured.
[[ "${REVALIDATE_FAILURE_WEBHOOK_CONFIGURED:-}" == "1" ]] \
  || die "REVALIDATE_FAILURE_WEBHOOK_CONFIGURED!=1 (set Portal REVALIDATE_FAILURE_WEBHOOK_URL first) → BLOCKED"

# Staging/prod API guard (Python also enforces)
python3 - <<'PY'
from erum_pipeline.staging_guards import assert_required_engine_env
print(assert_required_engine_env())
PY

log "ENV_OK PUBLISH_STATUS=$PUBLISH_STATUS PER_RUN_LIMIT=$PER_RUN_LIMIT DAILY_PUBLISH_LIMIT=$DAILY_PUBLISH_LIMIT PER_SITE_PER_RUN_LIMIT=$PER_SITE_PER_RUN_LIMIT"

set +e
python3 engine.py >>"$LOG_FILE" 2>&1
rc=$?
set -e

if [[ $rc -ne 0 ]]; then
  log "FAIL engine.py exit=$rc"
  exit "$rc"
fi

log "OK engine.py exit=0"
exit 0
