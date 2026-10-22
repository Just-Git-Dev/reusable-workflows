#!/usr/bin/env bash
# A composite action only WARNS on an unknown or stale `with:` key, so a v4 caller still passing
# `mode` / `confirm_removed` would get a green run that silently keeps the keys it meant to remove.
# Both inputs are tombstones since v5.0.0: refuse any non-empty value.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
set -eo pipefail

if [ -n "$MODE" ] || [ -n "$CONFIRM_REMOVED" ]; then
  echo "::error::'mode' and 'confirm_removed' were removed in v5.0.0: the sync is merge-only and keeps every key it is not given. Drop 'mode', and name the keys to remove in 'remove_keys' (CSV) instead of 'confirm_removed'. See docs/sync-bundle-key.md, Migrating from v4."
  exit 1
fi
