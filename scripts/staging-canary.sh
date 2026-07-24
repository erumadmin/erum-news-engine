#!/usr/bin/env bash
# One-shot staging canary. Never installs cron. Never targets Vultr production host.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ERUM_STAGING_ENV_FILE:-$HOME/.env.erum_staging}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE (see configs/staging.env.example)" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
export ERUM_ENV=staging
export PUBLISH_STATUS="${PUBLISH_STATUS:-DRAFT}"
export HIDDEN_PUBLISH_TEST="${HIDDEN_PUBLISH_TEST:-1}"
unset GSC_SERVICE_ACCOUNT_JSON || true
exec "$ROOT/scripts/canary-runner.sh" "$@"
