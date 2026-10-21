#!/usr/bin/env bash
# Wait grace_seconds so every URL signed with the old secret expires.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

sleep "$GRACE_SECONDS"
