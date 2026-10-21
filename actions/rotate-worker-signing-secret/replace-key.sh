#!/usr/bin/env bash
# Put the new secret into the local bundle copy.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

if grep -q "^${BUNDLE_KEY}=" /tmp/bundle.env; then
  awk -v k="$BUNDLE_KEY" -v v="$NEW_SECRET" \
    'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' /tmp/bundle.env > /tmp/bundle.env.new
  mv /tmp/bundle.env.new /tmp/bundle.env
else
  echo "${BUNDLE_KEY}=${NEW_SECRET}" >> /tmp/bundle.env
fi
