#!/usr/bin/env bash
# payload_source: environment. Pick exactly the keys listed in secret_keys_file out of
# SECRETS_JSON (the caller's toJSON(secrets)) and emit them as the payload.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

if [ ! -s "$SECRET_KEYS_FILE" ]; then
  echo "::error::secret_keys_file '$SECRET_KEYS_FILE' is missing or empty; payload_source: environment needs it."
  exit 1
fi
# Key names: strip comments, CR and surrounding space; drop blanks.
sed -e 's/#.*//' -e 's/\r//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$SECRET_KEYS_FILE" \
  | grep -v '^$' | LC_ALL=C sort -u > /tmp/keys.txt || true
MISSING=()
while IFS= read -r k; do
  if ! printf '%s' "$ALL_SECRETS_JSON" | jq -e --arg k "$k" 'has($k) and (.[$k] | type == "string")' >/dev/null 2>&1; then
    MISSING+=("$k")
  fi
done < /tmp/keys.txt
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "::error::No environment secret for listed key(s): ${MISSING[*]}. Refusing to build a partial payload."
  exit 1
fi
# Exactly the listed keys: github_token and any unlisted secret stay out.
PAYLOAD=$(printf '%s' "$ALL_SECRETS_JSON" | jq -c --rawfile keys /tmp/keys.txt \
  '($keys | split("\n") | map(select(. != ""))) as $ks | with_entries(select(.key as $k | $ks | index($k)))')
while IFS= read -r v; do
  [ -n "$v" ] && echo "::add-mask::$v"
done < <(printf '%s' "$PAYLOAD" | jq -r '.[]')
{
  echo "payload_json<<JGD_PAYLOAD_EOF"
  printf '%s\n' "$PAYLOAD"
  echo "JGD_PAYLOAD_EOF"
} >> "$GITHUB_OUTPUT"
echo "Payload built from $(printf '%s' "$PAYLOAD" | jq 'length') environment secret(s)."
