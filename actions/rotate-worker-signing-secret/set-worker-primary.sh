#!/usr/bin/env bash
# Set the Worker PRIMARY slot to the new secret.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

# jq builds the JSON, so the value stays data whatever characters it holds.
jq -n --arg name "$CF_PRIMARY" --arg text "$NEW_SECRET" \
  '{name: $name, text: $text, type: "secret_text"}' > /tmp/cf_secret.json
HTTP=$(curl -sS -o /tmp/cf_resp.json -w '%{http_code}' -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${CF_WORKER_SCRIPT}/secrets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data @/tmp/cf_secret.json)
rm -f /tmp/cf_secret.json
if [ "$HTTP" -lt 200 ] || [ "$HTTP" -ge 300 ]; then
  echo "::error::CF Worker PUT (PRIMARY slot) returned HTTP $HTTP"
  cat /tmp/cf_resp.json 2>/dev/null; echo
  exit 1
fi
echo "CF Worker PRIMARY slot set (HTTP $HTTP)."
