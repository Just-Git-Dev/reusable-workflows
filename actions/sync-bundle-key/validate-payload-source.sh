#!/usr/bin/env bash
# Refuse an unknown payload_source (a typo must not silently read a different secret).
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

case "$PAYLOAD_SOURCE" in
  caller|environment) ;;
  *) echo "::error::payload_source must be 'caller' or 'environment' (got '${PAYLOAD_SOURCE}')." >&2; exit 1 ;;
esac
