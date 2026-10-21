#!/usr/bin/env bash
# Read the Cloudflare API token out of SECRETS_JSON (the caller's toJSON(secrets)) and emit it as
# the step output `cf_api_token`, masked. Only that one key leaves this step; every other secret in
# SECRETS_JSON stays here. A missing token fails the step: the Worker slots cannot be set without it.
#
# Env (never interpolated): SECRETS_JSON.
set -eo pipefail

TOKEN=$(printf '%s' "$SECRETS_JSON" | jq -r 'to_entries | map(select(.key | ascii_downcase == "cloudflare_api_token")) | .[0].value // empty')
if [ -z "$TOKEN" ]; then
  echo "::error::secrets_json carries no cloudflare_api_token (the Worker slots cannot be set without it)."
  exit 1
fi
echo "::add-mask::$TOKEN"
{
  echo "cf_api_token<<JGD_TOKEN_EOF"
  printf '%s\n' "$TOKEN"
  echo "JGD_TOKEN_EOF"
} >> "$GITHUB_OUTPUT"
