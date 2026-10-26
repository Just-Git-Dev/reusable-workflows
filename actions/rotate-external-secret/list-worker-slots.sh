#!/usr/bin/env bash
# List the Worker secret NAMES (never values) and emit which of the two slots exist, as
# `present` (comma list, slot_a first). Any non-2xx fails the step.
#
# Env: CF_ACCOUNT_ID, WORKER_SCRIPT, CF_API_TOKEN, SLOT_A, SLOT_B.
set -eo pipefail

RESP="${RUNNER_TEMP:?}/cf_list.json"
HTTP=$(curl -sS -o "$RESP" -w '%{http_code}' -X GET \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${WORKER_SCRIPT}/secrets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}") || HTTP="000"
if [ "$HTTP" -lt 200 ] || [ "$HTTP" -ge 300 ]; then
  echo "::error::listing Worker secrets returned HTTP $HTTP. Check cf_account_id, worker_script and that the token has Workers Scripts:Edit."
  exit 1
fi
PRESENT=$(jq -r --arg a "$SLOT_A" --arg b "$SLOT_B" \
  '[.result[].name] as $n | [$a, $b] | map(select(. as $s | $n | index($s))) | join(",")' "$RESP")
rm -f "$RESP"
echo "Worker secrets present among the slots: ${PRESENT:-none}"
echo "present=${PRESENT}" >> "$GITHUB_OUTPUT"
