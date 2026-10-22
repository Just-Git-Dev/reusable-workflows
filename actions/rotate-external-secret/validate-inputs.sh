#!/usr/bin/env bash
# Refuse malformed inputs before anything is read or written, and emit `token_repos`: the two repos
# (target, this one) the App token is scoped to.
#
# Env (never interpolated): CF_ACCOUNT_ID WORKER_SCRIPT SLOT_A SLOT_B TARGET_REPO TARGET_ENVIRONMENT
# TARGET_SECRET_NAME SYNC_WORKFLOW SYNC_REF SYNC_INPUTS_JSON STATE_VARIABLE ROTATE_EVERY_DAYS
# GRACE_HOURS WAIT_MINUTES SECRET_BYTES APP_ID GITHUB_REPOSITORY.
set -eo pipefail

BAD=0
bad() { echo "::error::$1"; BAD=1; }
match() { # name value regex
  printf '%s' "$2" | grep -Eq "$3" || bad "input $1 ('$2') is malformed; expected $3"
}
int_between() { # name value min max
  if printf '%s' "$2" | grep -Eq '^[0-9]+$' && [ "$2" -ge "$3" ] && [ "$2" -le "$4" ]; then return 0; fi
  bad "input $1 ('$2') must be a whole number from $3 to $4"
}

match cf_account_id "$CF_ACCOUNT_ID" '^[A-Za-z0-9]+$'
match worker_script "$WORKER_SCRIPT" '^[A-Za-z0-9_-]+$'
match slot_a "$SLOT_A" '^[A-Za-z_][A-Za-z0-9_]*$'
match slot_b "$SLOT_B" '^[A-Za-z_][A-Za-z0-9_]*$'
[ "$SLOT_A" != "$SLOT_B" ] || bad "slot_a and slot_b must differ (the two slots alternate)"
match target_repo "$TARGET_REPO" '^[A-Za-z0-9._-]+$'
match target_environment "$TARGET_ENVIRONMENT" '^[A-Za-z0-9._-]+$'
match target_secret_name "$TARGET_SECRET_NAME" '^[A-Za-z_][A-Za-z0-9_]*$'
match sync_workflow "$SYNC_WORKFLOW" '^[A-Za-z0-9_-][A-Za-z0-9._-]*\.ya?ml$'
match sync_ref "$SYNC_REF" '^[A-Za-z0-9._/-]+$'
match state_variable "$STATE_VARIABLE" '^[A-Za-z_][A-Za-z0-9_]*$'
case "$STATE_VARIABLE" in GITHUB_*) bad "state_variable must not start with GITHUB_" ;; esac
match app_id "$APP_ID" '^[0-9]+$'
int_between rotate_every_days "$ROTATE_EVERY_DAYS" 1 3650
int_between grace_hours "$GRACE_HOURS" 0 8760
int_between wait_minutes "$WAIT_MINUTES" 1 30
int_between secret_bytes "$SECRET_BYTES" 16 128
if ! printf '%s' "$SYNC_INPUTS_JSON" | jq -e 'type == "object" and (has("correlation_id") | not) and all(.[]; type == "string" or type == "number" or type == "boolean")' >/dev/null 2>&1; then
  bad "sync_inputs_json must be a JSON object of scalar values and must not set correlation_id (the rotation adds it)"
fi
[ "$BAD" = 0 ] || exit 1

PROJECT="${GITHUB_REPOSITORY#*/}"
if [ "$PROJECT" = "$TARGET_REPO" ]; then REPOS="$TARGET_REPO"; else REPOS="${TARGET_REPO},${PROJECT}"; fi
echo "token_repos=${REPOS}" >> "$GITHUB_OUTPUT"
