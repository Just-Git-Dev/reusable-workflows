#!/usr/bin/env bash
# Generate the new signing secret.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

# hex so it is safe in a dotenv value and a JSON string alike.
NEW_SECRET=$(openssl rand -hex "$SECRET_BYTES")
echo "::add-mask::$NEW_SECRET"
{
  echo "new_secret<<JGD_SECRET_EOF"
  printf '%s\n' "$NEW_SECRET"
  echo "JGD_SECRET_EOF"
} >> "$GITHUB_OUTPUT"
