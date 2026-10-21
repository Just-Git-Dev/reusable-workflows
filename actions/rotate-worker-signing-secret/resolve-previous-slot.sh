#!/usr/bin/env bash
# Work out the Worker PREVIOUS slot name (blank input = <primary>_PREVIOUS).
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

# A step output, not $GITHUB_ENV: a step's own env: wins over $GITHUB_ENV, so later steps read this output.
if [ -z "$CF_PREVIOUS" ]; then
  CF_PREVIOUS="${CF_PRIMARY}_PREVIOUS"
fi
echo "cf_previous=$CF_PREVIOUS" >> "$GITHUB_OUTPUT"
