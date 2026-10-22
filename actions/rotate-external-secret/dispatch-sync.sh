#!/usr/bin/env bash
# Dispatch the service's own bundle sync with a unique correlation_id the sync echoes into its run
# name (its run-name is "sync <correlation_id>"), so wait-sync.sh can find exactly that run.
#
# Env: GH_TOKEN, OWNER, TARGET_REPO, SYNC_WORKFLOW, SYNC_REF, SYNC_INPUTS_JSON, CORRELATION_ID, DRY_RUN.
set -eo pipefail

[ "${DRY_RUN:-false}" != "true" ] || { echo "::error::refusing to dispatch in dry_run"; exit 1; }
ARGS=()
while IFS= read -r kv; do
  ARGS+=(-f "$kv")
done < <(printf '%s' "$SYNC_INPUTS_JSON" | jq -r 'to_entries[] | "\(.key)=\(.value)"')
gh workflow run "$SYNC_WORKFLOW" --repo "${OWNER}/${TARGET_REPO}" --ref "$SYNC_REF" "${ARGS[@]}" -f "correlation_id=${CORRELATION_ID}"
echo "Dispatched ${SYNC_WORKFLOW} on ${OWNER}/${TARGET_REPO}@${SYNC_REF} (correlation_id ${CORRELATION_ID})."
