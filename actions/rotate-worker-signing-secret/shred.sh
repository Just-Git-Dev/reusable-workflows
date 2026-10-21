#!/usr/bin/env bash
# Remove every local copy of the bundle and the Worker payload.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
set -eo pipefail

rm -f /tmp/bundle.env /tmp/bundle.env.new /tmp/rollback.env /tmp/cf_secret.json /tmp/enabled.txt /tmp/to-disable.txt
