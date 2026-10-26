#!/usr/bin/env bash
# Write the non-secret state variable {current, pending, [phase,] rotated_at} in the project repo.
# STATE_ROTATED_AT is an epoch number, or 'now'. `phase` is written only when STATE_PHASE is set:
# put = the Worker PUT / environment write may not have happened, env = both are done.
#
# Env: GH_TOKEN, REPO, STATE_VARIABLE, STATE_CURRENT, STATE_PENDING, STATE_PHASE (optional),
# STATE_ROTATED_AT, DRY_RUN, NOW.
set -eo pipefail

[ "${DRY_RUN:-false}" != "true" ] || { echo "::error::refusing to write in dry_run"; exit 1; }
AT="$STATE_ROTATED_AT"
if [ "$AT" = "now" ]; then AT="${NOW:-$(date +%s)}"; fi
JSON=$(jq -nc --arg c "$STATE_CURRENT" --arg p "$STATE_PENDING" --arg ph "${STATE_PHASE:-}" --argjson at "$AT" \
  '{current: $c, pending: $p, rotated_at: $at} + (if $ph == "" then {} else {phase: $ph} end)')
gh variable set "$STATE_VARIABLE" --repo "$REPO" --body "$JSON"
echo "State ${STATE_VARIABLE}: ${JSON}"
