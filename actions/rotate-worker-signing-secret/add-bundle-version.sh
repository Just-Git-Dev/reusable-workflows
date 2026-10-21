#!/usr/bin/env bash
# Add the patched bundle as a new Secret Manager version.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

gcloud secrets versions add "$BUNDLE_SECRET" \
  --project="$GCP_PROJECT" --data-file=/tmp/bundle.env
NEW_VERSION=$(gcloud secrets versions list "$BUNDLE_SECRET" \
  --project="$GCP_PROJECT" --filter='state=ENABLED' \
  --sort-by=~createTime --limit=1 --format='value(name)')
if [ -z "$NEW_VERSION" ]; then
  echo "::error::Could not resolve the newly added version of $BUNDLE_SECRET."
  exit 1
fi
echo "new_version=$NEW_VERSION" >> "$GITHUB_OUTPUT"
