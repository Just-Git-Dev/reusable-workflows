#!/usr/bin/env bash
# Find the sync run this job dispatched (its run name carries CORRELATION_ID as a whole word), refuse
# an ambiguous match, and wait for it to complete. Anything but success, or running past the
# deadline, fails the step: the state keeps `pending` and nothing is retired.
#
# Env: GH_TOKEN, OWNER, TARGET_REPO, SYNC_WORKFLOW, CORRELATION_ID, WAIT_MINUTES, POLL_SECONDS.
set -eo pipefail

REPO="${OWNER}/${TARGET_REPO}"
DEADLINE=$(( $(date +%s) + WAIT_MINUTES * 60 ))
RUN_ID=""
while [ -z "$RUN_ID" ]; do
  LIST=$(gh run list --repo "$REPO" --workflow "$SYNC_WORKFLOW" --event workflow_dispatch --limit 30 \
    --json databaseId,displayTitle,status,conclusion)
  IDS=$(printf '%s' "$LIST" | jq -r --arg c "$CORRELATION_ID" '[.[] | select(.displayTitle | split(" ") | index($c))] | map(.databaseId) | join(" ")')
  N=$(printf '%s' "$IDS" | wc -w | tr -d ' ')
  if [ "$N" -gt 1 ]; then
    echo "::error::ambiguous: ${N} sync runs match correlation id ${CORRELATION_ID} (${IDS}). Refusing to guess which one to trust."
    exit 1
  fi
  if [ "$N" = 1 ]; then RUN_ID="$IDS"; break; fi
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    echo "::error::timed out after ${WAIT_MINUTES} min: no ${SYNC_WORKFLOW} run named for ${CORRELATION_ID} appeared. Does the sync accept correlation_id and set run-name?"
    exit 1
  fi
  sleep "${POLL_SECONDS:-15}"
done
echo "Sync run ${RUN_ID} found."
while true; do
  VIEW=$(gh run view "$RUN_ID" --repo "$REPO" --json status,conclusion)
  STATUS=$(printf '%s' "$VIEW" | jq -r .status)
  if [ "$STATUS" = "completed" ]; then
    CONCLUSION=$(printf '%s' "$VIEW" | jq -r .conclusion)
    if [ "$CONCLUSION" = "success" ]; then echo "Sync run ${RUN_ID} succeeded."; exit 0; fi
    echo "::error::sync run ${RUN_ID} concluded ${CONCLUSION}. State keeps pending; both Worker slots stay valid; nothing is retired."
    exit 1
  fi
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    echo "::error::timed out after ${WAIT_MINUTES} min waiting for sync run ${RUN_ID} (status ${STATUS}). State keeps pending; nothing is retired."
    exit 1
  fi
  sleep "${POLL_SECONDS:-15}"
done
