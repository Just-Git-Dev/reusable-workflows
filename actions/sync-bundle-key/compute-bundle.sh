#!/usr/bin/env bash
# Overlay the payload on the current bundle and print the diff by key name. Merge-only: every key
# the payload does not carry is kept byte-for-byte; a key leaves only when named in REMOVE_KEYS.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# docs/sync-bundle-key.md "Merge and explicit removal".
set -eo pipefail

# Value of KEY in the current bundle (empty if absent), bytes exact, key via ENVIRON not a regex.
cur_value() {
  KEY="$1" awk 'BEGIN{FS=OFS="="} $1""==ENVIRON["KEY"]""{sub(/^[^=]*=/, ""); print; exit}' /tmp/bundle.env
}
upsert() {
  local key="$1" val="$2"
  # Key and value reach awk through ENVIRON, never `-v` (which processes
  # backslash escapes and corrupts a value holding one) and never as a
  # regex (`A.B` must not match `AxB`). Bytes are written exactly.
  if KEY="$key" awk 'BEGIN{FS="="} $1""==ENVIRON["KEY"]""{f=1} END{exit !f}' /tmp/bundle.env; then
    KEY="$key" VAL="$val" awk 'BEGIN{FS=OFS="="} $1""==ENVIRON["KEY"]""{print ENVIRON["KEY"] "=" ENVIRON["VAL"]; next} {print}' /tmp/bundle.env > /tmp/bundle.env.new
    mv /tmp/bundle.env.new /tmp/bundle.env
  else
    # A last line with no trailing newline would swallow the appended key.
    if [ -s /tmp/bundle.env ] && [ -n "$(tail -c1 /tmp/bundle.env)" ]; then
      echo >> /tmp/bundle.env
    fi
    echo "${key}=${val}" >> /tmp/bundle.env
  fi
}
# Key names only, from here on: current keys, payload keys, keys to remove.
# Blank lines and comments in the current bundle are not keys.
awk 'BEGIN{FS="="} NF && $0 !~ /^[[:space:]]*#/ {print $1}' /tmp/bundle.env \
  | LC_ALL=C sort -u > /tmp/keys.cur
printf '%s' "$PAYLOAD_JSON" | jq -r 'keys[]' | LC_ALL=C sort -u > /tmp/keys.payload
# remove_keys (comma or newline separated): trimmed, empties ignored, case-sensitive, env-name pattern.
printf '%s' "$REMOVE_KEYS" | tr ',' '\n' \
  | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v '^$' | LC_ALL=C sort -u > /tmp/keys.remove || true
BADREMOVE=$(grep -v -E '^[A-Za-z_][A-Za-z0-9_]*$' /tmp/keys.remove | jq -R . | paste -sd, - || true)
if [ -n "$BADREMOVE" ]; then
  echo "::error::remove_keys name(s) are not valid env names (^[A-Za-z_][A-Za-z0-9_]*\$): $BADREMOVE. Nothing written."
  exit 1
fi
# A key cannot be written and removed in one run.
CONFLICT=$(LC_ALL=C comm -12 /tmp/keys.remove /tmp/keys.payload | paste -sd, - || true)
if [ -n "$CONFLICT" ]; then
  echo "::error::remove_keys names key(s) that are also in the payload: $CONFLICT. A run cannot both write and remove a key. Nothing written."
  exit 1
fi
LC_ALL=C comm -12 /tmp/keys.remove /tmp/keys.cur > /tmp/keys.dropped
# Matching is by line prefix `KEY=` only; an indented or `export KEY=` line is not matched.
ABSENT=$(LC_ALL=C comm -23 /tmp/keys.remove /tmp/keys.cur | paste -sd, - || true)
if [ -n "$ABSENT" ]; then
  echo "::warning::remove_keys names key(s) have no line starting KEY= in the current bundle (nothing removed): $ABSENT."
fi
# Remove first (only the named keys' lines; order of the rest preserved).
if [ -s /tmp/keys.dropped ]; then
  awk -F= 'NR==FNR{k[$0]=1; next} !($1"" in k)' /tmp/keys.dropped /tmp/bundle.env > /tmp/bundle.env.new
  mv /tmp/bundle.env.new /tmp/bundle.env
fi
# Overlay the payload (base64 per value so newlines/special chars survive the shell).
: > /tmp/keys.updated
while IFS=$'\t' read -r key b64; do
  val=$(printf '%s' "$b64" | base64 -d)
  if LC_ALL=C grep -qx -F -- "$key" /tmp/keys.cur && [ "$(cur_value "$key")" != "$val" ]; then
    echo "$key" >> /tmp/keys.updated
  fi
  upsert "$key" "$val"
done < <(printf '%s' "$PAYLOAD_JSON" | jq -r 'to_entries[] | [.key, (.value | @base64)] | @tsv')
# The diff, by NAME only: +added ~updated -removed, and a count of the rest.
LC_ALL=C comm -13 /tmp/keys.cur /tmp/keys.payload > /tmp/keys.added
LC_ALL=C sort -u -o /tmp/keys.updated /tmp/keys.updated
UNCHANGED=$(LC_ALL=C comm -23 /tmp/keys.cur /tmp/keys.dropped | LC_ALL=C comm -23 - /tmp/keys.updated | wc -l | tr -d ' ')
{
  echo "### Bundle diff by key name"
  echo '```'
  sed 's/^/+ /' /tmp/keys.added
  sed 's/^/~ /' /tmp/keys.updated
  sed 's/^/- /' /tmp/keys.dropped
  echo "= ${UNCHANGED} kept unchanged"
  echo '```'
} | tee -a "$GITHUB_STEP_SUMMARY"
