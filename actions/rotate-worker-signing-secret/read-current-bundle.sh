#!/usr/bin/env bash
# Read the current bundle (or start empty) and the OLD signing secret.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

if ! gcloud secrets describe "$BUNDLE_SECRET" --project="$GCP_PROJECT" >/dev/null 2>&1; then
  if [ "$BOOTSTRAP" = "true" ]; then
    echo "::warning::Bundle $BUNDLE_SECRET absent — bootstrap run, starting empty."
    : > /tmp/bundle.env
    echo "empty=true" >> "$GITHUB_OUTPUT"
    exit 0
  fi
  echo "::error::Secret $BUNDLE_SECRET does not exist in $GCP_PROJECT. Create it first, or set bootstrap: true."
  exit 1
fi
# --limit=1 (not | head -1): closing the pipe can SIGPIPE gcloud, which
# under pipefail would fail the step.
CURRENT_VERSION=$(gcloud secrets versions list "$BUNDLE_SECRET" \
  --project="$GCP_PROJECT" --filter='state=ENABLED' \
  --sort-by=~createTime --limit=1 --format='value(name)')
if [ -z "$CURRENT_VERSION" ]; then
  : > /tmp/bundle.env
  echo "empty=true" >> "$GITHUB_OUTPUT"
  echo "No enabled version yet — starting from an empty bundle."
  exit 0
fi
gcloud secrets versions access "$CURRENT_VERSION" \
  --secret="$BUNDLE_SECRET" --project="$GCP_PROJECT" > /tmp/bundle.env
echo "current_version=$CURRENT_VERSION" >> "$GITHUB_OUTPUT"
echo "empty=false" >> "$GITHUB_OUTPUT"
echo "Current enabled version: $CURRENT_VERSION"
# The OLD signing secret becomes the Worker PREVIOUS slot during grace.
OLD=$(grep "^${BUNDLE_KEY}=" /tmp/bundle.env | sed "s/^${BUNDLE_KEY}=//" || true)
if [ -n "$OLD" ]; then
  echo "::add-mask::$OLD"
  {
    echo "old_secret<<JGD_SECRET_EOF"
    printf '%s\n' "$OLD"
    echo "JGD_SECRET_EOF"
  } >> "$GITHUB_OUTPUT"
fi
