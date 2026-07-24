#!/usr/bin/env bash
# W8 / production Engine cron runner (Vultr).
#
# - NEVER git pull
# - NEVER rely on shell profile or implicit cwd .env
# - Load ONLY ENGINE_ENV_FILE (mode 600, owner=runner uid, exact W8 values)
# - flock wraps SHA check + env load + today-count + engine.py
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
# Holds through env validation, daily DRAFT count (inside engine.py), and execution.
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

# Load + validate ENGINE_ENV_FILE (mode 600, owner, exact 3/9/1 contract).
# Prints KEY=VALUE lines for eval; never reads ~/.profile or cwd .env.
EVAL_FILE="$(mktemp)"
cleanup() { rm -f "$EVAL_FILE"; }
trap cleanup EXIT

python3 - "$ENGINE_ENV_FILE" "$EVAL_FILE" <<'PY' || die "ENGINE_ENV_FILE validation failed (fail-closed)"
import sys
from pathlib import Path
from erum_pipeline.w8_runner_env import load_w8_env_file

env_path, out_path = sys.argv[1], sys.argv[2]
loaded = load_w8_env_file(env_path)
# Webhook gate must be explicit in the same file (or already exact-checked above).
if (loaded.get("REVALIDATE_FAILURE_WEBHOOK_CONFIGURED") or "").strip() != "1":
    raise SystemExit("REVALIDATE_FAILURE_WEBHOOK_CONFIGURED must be 1 in ENGINE_ENV_FILE → BLOCKED")
lines = [f"{k}={v}" for k, v in loaded.items()]
Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"loaded {len(loaded)} keys from {env_path}", flush=True)
PY

set -a
# shellcheck disable=SC1090
source "$EVAL_FILE"
set +a

log "ENV_FILE_OK path=$ENGINE_ENV_FILE PUBLISH_STATUS=$PUBLISH_STATUS PER_RUN_LIMIT=$PER_RUN_LIMIT DAILY_PUBLISH_LIMIT=$DAILY_PUBLISH_LIMIT PER_SITE_PER_RUN_LIMIT=$PER_SITE_PER_RUN_LIMIT"

python3 - <<'PY'
from erum_pipeline.staging_guards import assert_required_engine_env
print(assert_required_engine_env())
PY

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
