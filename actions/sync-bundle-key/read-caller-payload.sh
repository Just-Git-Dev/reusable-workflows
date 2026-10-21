#!/usr/bin/env bash
# payload_source: caller. Read the `payload_json` secret out of SECRETS_JSON (the caller's
# toJSON(secrets)) and emit it as the step output `payload_json`. Only that one key leaves this
# step; every other secret in SECRETS_JSON stays here. A missing secret emits nothing, and the
# Validate step then refuses the empty payload.
#
# Env (never interpolated): SECRETS_JSON.
set -eo pipefail

PAYLOAD=$(printf '%s' "$SECRETS_JSON" | jq -r 'to_entries | map(select(.key | ascii_downcase == "payload_json")) | .[0].value // empty')
[ -n "$PAYLOAD" ] || exit 0
# The secret is already masked as a whole; its parsed values are derived data, so mask them too.
while IFS= read -r v; do
  [ -n "$v" ] && echo "::add-mask::$v"
done < <(printf '%s' "$PAYLOAD" | jq -r 'if type == "object" then .[] | strings else empty end' 2>/dev/null || true)
{
  echo "payload_json<<JGD_PAYLOAD_EOF"
  printf '%s\n' "$PAYLOAD"
  echo "JGD_PAYLOAD_EOF"
} >> "$GITHUB_OUTPUT"
