#!/usr/bin/env bash
# Retire the old Worker slot after the grace period. Failure fails the run (the next run retries);
# a 404 means it is already gone and is only noted.
#
# Env: CF_ACCOUNT_ID, WORKER_SCRIPT, CF_API_TOKEN, RETIRE_SLOT, DRY_RUN.
set -eo pipefail

[ "${DRY_RUN:-false}" != "true" ] || { echo "::error::refusing to delete in dry_run"; exit 1; }
HTTP=$(curl -sS -o "${RUNNER_TEMP:?}/cf_resp.json" -w '%{http_code}' -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${WORKER_SCRIPT}/secrets/${RETIRE_SLOT}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}") || HTTP="000"
if [ "$HTTP" = "404" ]; then
  echo "::notice::slot ${RETIRE_SLOT} was already gone (HTTP 404)."
elif [ "$HTTP" -lt 200 ] || [ "$HTTP" -ge 300 ]; then
  echo "::error::CF Worker DELETE (slot ${RETIRE_SLOT}) returned HTTP $HTTP; the next run retries."
  jq -c '.errors // empty' "${RUNNER_TEMP}/cf_resp.json" 2>/dev/null || true
  exit 1
else
  echo "CF Worker slot ${RETIRE_SLOT} retired (HTTP $HTTP)."
fi
