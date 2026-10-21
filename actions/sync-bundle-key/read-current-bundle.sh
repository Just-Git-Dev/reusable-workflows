#!/usr/bin/env bash
# Read the newest ENABLED bundle version into /tmp/bundle.env.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

if ! gcloud secrets describe "$BUNDLE_SECRET" --project="$GCP_PROJECT" >/dev/null 2>&1; then
  echo "::error::Secret $BUNDLE_SECRET does not exist in $GCP_PROJECT. Create it first."
  exit 1
fi
# `--limit=1` rather than `| head -1`: head closing the pipe can
# SIGPIPE gcloud, which under pipefail would fail the step.
CURRENT_VERSION=$(gcloud secrets versions list "$BUNDLE_SECRET" \
  --project="$GCP_PROJECT" --filter='state=ENABLED' \
  --sort-by=~createTime --limit=1 --format='value(name)')
if [ -n "$CURRENT_VERSION" ]; then
  gcloud secrets versions access "$CURRENT_VERSION" \
    --secret="$BUNDLE_SECRET" --project="$GCP_PROJECT" > /tmp/bundle.env
  echo "current_version=$CURRENT_VERSION" >> "$GITHUB_OUTPUT"
  echo "Current enabled version: $CURRENT_VERSION"
else
  : > /tmp/bundle.env
  echo "No enabled version yet — starting from an empty bundle."
fi
