#!/usr/bin/env bash
# Write the run summary.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

{
  if [ "$DRY_RUN" = "true" ]; then
    echo "## [dry run] Would rotate ${BUNDLE_KEY} in ${BUNDLE_SECRET} (${GCP_PROJECT})"
    echo ""
    echo "- Current bundle version: ${CUR_VERSION} (would be disabled after grace)"
    echo "- Would roll: \`${SERVICES_CSV}\`"
    echo "- Would set Worker \`${CF_WORKER_SCRIPT}\` slots: ${CF_PRIMARY} (+ ${CF_PREVIOUS} during grace)"
  else
    echo "## Rotated ${BUNDLE_KEY} in ${BUNDLE_SECRET} (${GCP_PROJECT})"
    echo ""
    echo "- Empty/bootstrap: ${CUR_EMPTY}"
    echo "- Old version: ${CUR_VERSION} (disabled)"
    echo "- New version: ${NEW_VERSION}"
    echo "- Cloud Run rolled: \`${SERVICES_CSV}\`"
    echo "- Worker: ${CF_WORKER_SCRIPT} (PRIMARY set; PREVIOUS held ${GRACE_SECONDS}s then removed)"
  fi
} >> "$GITHUB_STEP_SUMMARY"
