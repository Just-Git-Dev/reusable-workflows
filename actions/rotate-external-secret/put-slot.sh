#!/usr/bin/env bash
# PUT the new value into the EMPTY Worker slot. The other slot (the old value) is untouched.
# The JSON is built by jq from the secret FILE and sent on stdin, so the value is on no command line.
#
# Env: CF_ACCOUNT_ID, WORKER_SCRIPT, CF_API_TOKEN, NEW_SLOT, DRY_RUN.
set -eo pipefail

[ "${DRY_RUN:-false}" != "true" ] || { echo "::error::refusing to write in dry_run"; exit 1; }
DIR="${RUNNER_TEMP:?}/rotate-external"
HTTP=$(jq -n --arg name "$NEW_SLOT" --rawfile text "$DIR/new-secret" '{name: $name, text: $text, type: "secret_text"}' \
  | curl -sS -o "$DIR/cf_resp.json" -w '%{http_code}' -X PUT \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${WORKER_SCRIPT}/secrets" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    --data @-) || HTTP="000"
if [ "$HTTP" -lt 200 ] || [ "$HTTP" -ge 300 ]; then
  echo "::error::CF Worker PUT (slot ${NEW_SLOT}) returned HTTP $HTTP; the old slot is untouched."
  jq -c '.errors // empty' "$DIR/cf_resp.json" 2>/dev/null || true
  exit 1
fi
echo "CF Worker slot ${NEW_SLOT} set (HTTP $HTTP)."
