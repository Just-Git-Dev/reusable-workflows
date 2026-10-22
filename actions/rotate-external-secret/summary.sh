#!/usr/bin/env bash
# Step summary: the branch taken and the names involved. Names only, never a value.
#
# Env: ACTION, MESSAGE, DRY_RUN, WORKER_SCRIPT, SLOT_A, SLOT_B, TARGET_REPO, TARGET_ENVIRONMENT,
# TARGET_SECRET_NAME, SYNC_WORKFLOW, STATE_VARIABLE, CURRENT, NEW_SLOT, RETIRE_SLOT.
set -eo pipefail

{
  echo "### rotate-external-secret"
  echo "- worker: \`${WORKER_SCRIPT}\` slots \`${SLOT_A}\` / \`${SLOT_B}\`; current: \`${CURRENT:-none}\`"
  echo "- branch: \`${ACTION:-not decided}\` (dry_run=${DRY_RUN})"
  echo "- ${MESSAGE:-no decision was reached (see the failed step)}"
  if [ "$DRY_RUN" = "true" ]; then
    case "$ACTION" in
      rotate) echo "- would PUT \`${NEW_SLOT}\`, set \`${TARGET_SECRET_NAME}\` in \`${TARGET_REPO}\` / \`${TARGET_ENVIRONMENT}\`, set pending in \`${STATE_VARIABLE}\`, dispatch \`${SYNC_WORKFLOW}\`, wait, promote" ;;
      pending-sync) echo "- would dispatch \`${SYNC_WORKFLOW}\`, wait, then promote \`${NEW_SLOT}\` in \`${STATE_VARIABLE}\`" ;;
      retire) echo "- would DELETE slot \`${RETIRE_SLOT}\`" ;;
      adopt) echo "- would set \`${STATE_VARIABLE}\` to current \`${CURRENT}\`" ;;
      *) echo "- would make no write call" ;;
    esac
  fi
} >> "$GITHUB_STEP_SUMMARY"
