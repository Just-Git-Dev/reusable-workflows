#!/usr/bin/env bash
# Read the non-secret state variable ({current, pending, rotated_at}) of the project repo. A missing
# variable is the empty state (bootstrap); any other API error fails the step.
#
# Env: GH_TOKEN, REPO (owner/name of the project repo), STATE_VARIABLE.
set -eo pipefail

#
# Only stdout is state. stderr goes to a file and is read only to classify a failure, so a warning
# gh prints on a successful read (update notice, deprecation) never lands in the stored state.
ERRF=$(mktemp)
trap 'rm -f "$ERRF"' EXIT
if OUT=$(gh variable get "$STATE_VARIABLE" --repo "$REPO" 2>"$ERRF"); then
  STATE=$(printf '%s' "$OUT" | tr -d '\n')
  [ ! -s "$ERRF" ] || echo "::notice::gh printed on stderr while reading ${STATE_VARIABLE} (not stored): $(head -c 300 "$ERRF")"
elif OUT=$(cat "$ERRF"); printf '%s' "$OUT" | grep -Eqi '404|not found'; then
  STATE=""
  echo "No state variable ${STATE_VARIABLE} yet (bootstrap)."
else
  echo "::error::cannot read variable ${STATE_VARIABLE} in ${REPO}: ${OUT}. Check the App has Variables: write on the project repo."
  exit 1
fi
echo "state_json=${STATE}" >> "$GITHUB_OUTPUT"
