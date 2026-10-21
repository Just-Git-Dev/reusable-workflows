#!/usr/bin/env bash
# Write the run summary.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

{
  if [ "$DRY_RUN" = "true" ]; then
    echo "## [dry run] Would sync ${TITLE} into ${BUNDLE_SECRET} (${GCP_PROJECT})"
    echo ""
    echo "- Current bundle version: ${OLD_VERSION:-<none>} (would be disabled)"
    echo "- Services that would roll: \`${SERVICES_CSV}\`"
  else
    echo "## Synced ${TITLE} into ${BUNDLE_SECRET} (${GCP_PROJECT})"
    echo ""
    echo "- Old bundle version: ${OLD_VERSION:-<none>}"
    echo "- New bundle version: ${NEW_VERSION:-<not created>}"
    echo "- Cloud Run services rolled: ${ROLLED:-0} of \`${SERVICES_CSV}\`"
  fi
  echo "- Mount path: ${MOUNT_PATH}"
} >> "$GITHUB_STEP_SUMMARY"
