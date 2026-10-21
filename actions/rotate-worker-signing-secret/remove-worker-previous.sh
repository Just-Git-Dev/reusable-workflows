#!/usr/bin/env bash
# Remove the Worker PREVIOUS slot after the grace window.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

# Non-fatal: after grace the PREVIOUS slot is unused, so a failure here
# doesn't break signing — but still show the CF body rather than swallow it.
HTTP=$(curl -sS -o /tmp/cf_resp.json -w '%{http_code}' -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${CF_WORKER_SCRIPT}/secrets/${CF_PREVIOUS}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" || echo "000")
if [ "$HTTP" -lt 200 ] || [ "$HTTP" -ge 300 ]; then
  echo "::warning::Removing PREVIOUS slot returned HTTP $HTTP (non-fatal):"
  cat /tmp/cf_resp.json 2>/dev/null; echo
else
  echo "CF Worker PREVIOUS slot removed (HTTP $HTTP)."
fi
