#!/usr/bin/env bash
# Write the new value into the service repo's environment secret via the App token. The value goes
# to `gh secret set` on stdin only (from the 0600 file).
#
# Env: GH_TOKEN, OWNER, TARGET_REPO, TARGET_ENVIRONMENT, TARGET_SECRET_NAME, DRY_RUN.
set -eo pipefail

[ "${DRY_RUN:-false}" != "true" ] || { echo "::error::refusing to write in dry_run"; exit 1; }
gh secret set "$TARGET_SECRET_NAME" --env "$TARGET_ENVIRONMENT" --repo "${OWNER}/${TARGET_REPO}" < "${RUNNER_TEMP:?}/rotate-external/new-secret"
echo "Set ${TARGET_SECRET_NAME} in ${OWNER}/${TARGET_REPO} environment ${TARGET_ENVIRONMENT}."
