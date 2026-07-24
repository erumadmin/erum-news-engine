#!/usr/bin/env bash
# W8 / production Engine cron runner (Vultr).
#
# - NEVER git pull
# - NEVER source ENGINE_ENV_FILE / temp shell files / shell profiles / cwd .env
# - Python validates ENGINE_ENV_FILE and runs engine.py with an explicit env mapping
# - flock wraps SHA check → Python env load → engine.py (today-count + create)
# - Fail closed on missing/bad env file or wrong SHA
#
# This script does NOT install or modify crontab.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOCK_FILE="${ENGINE_CRON_LOCK_FILE:-/var/lock/erum-news-engine.w8.lock}"
LOG_FILE="${ENGINE_CRON_LOG_FILE:-$ROOT/cron.w8.log}"
APPROVED_SHA="${APPROVED_ENGINE_SHA:-}"
ENGINE_ENV_FILE="${ENGINE_ENV_FILE:-}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

log() {
  echo "[$(ts)] $*" | tee -a "$LOG_FILE"
}

die() {
  log "ERROR: $*"
  exit 1
}

# --- flock (non-blocking): exit 0 if another run holds the lock ---
# Holds through SHA pin, Python env validation, daily DRAFT count, and engine.py.
mkdir -p "$(dirname "$LOCK_FILE")" 2>/dev/null || true
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "SKIP: another engine run holds $LOCK_FILE"
  exit 0
fi

log "START root=$ROOT"

[[ -n "$APPROVED_SHA" ]] || die "APPROVED_ENGINE_SHA is required"
[[ -n "$ENGINE_ENV_FILE" ]] || die "ENGINE_ENV_FILE is required (explicit path; no implicit .env)"

HEAD="$(git rev-parse HEAD)"
if [[ "$HEAD" != "$APPROVED_SHA" && "$HEAD" != "$APPROVED_SHA"* ]]; then
  die "HEAD $HEAD != APPROVED_ENGINE_SHA $APPROVED_SHA (refusing to run; no git pull)"
fi
log "SHA_OK head=$HEAD approved=$APPROVED_SHA"

# Python-only env load + engine.py (no shell source of secrets).
export ENGINE_ENV_FILE
set +e
python3 scripts/w8_run_engine.py >>"$LOG_FILE" 2>&1
rc=$?
set -e

if [[ $rc -ne 0 ]]; then
  log "FAIL w8_run_engine/engine.py exit=$rc"
  exit "$rc"
fi

log "OK w8_run_engine/engine.py exit=0"
exit 0
