#!/usr/bin/env bash
# Remove the generated value and every scratch file, whatever happened before.
set -eo pipefail

DIR="${RUNNER_TEMP:?}/rotate-external"
if [ -f "$DIR/new-secret" ] && command -v shred >/dev/null 2>&1; then
  shred -u "$DIR/new-secret" 2>/dev/null || true
fi
rm -rf "$DIR"
rm -f "${RUNNER_TEMP}/cf_list.json" "${RUNNER_TEMP}/cf_resp.json"
