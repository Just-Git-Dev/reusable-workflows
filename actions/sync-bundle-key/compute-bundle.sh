#!/usr/bin/env bash
# Overlay the payload on the current bundle (mode replace|merge) and print the diff by key name.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

case "$MODE" in
  replace|merge) ;;
  *) echo "::error::mode must be 'replace' or 'merge' (got '$MODE')."; exit 1 ;;
esac
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
# Key names only, from here on: current keys, payload keys, listed keys.
# Blank lines and comments in the current bundle are not keys.
awk 'BEGIN{FS="="} NF && $0 !~ /^[[:space:]]*#/ {print $1}' /tmp/bundle.env \
  | LC_ALL=C sort -u > /tmp/keys.cur
printf '%s' "$PAYLOAD_JSON" | jq -r 'keys[]' | LC_ALL=C sort -u > /tmp/keys.payload
if [ "$MODE" = "replace" ]; then
  if [ ! -s "$SECRET_KEYS_FILE" ]; then
    echo "::error::mode: replace needs secret_keys_file; '$SECRET_KEYS_FILE' is missing or empty."
    exit 1
  fi
  sed -e 's/#.*//' -e 's/\r//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$SECRET_KEYS_FILE" \
    | grep -v '^$' | LC_ALL=C sort -u > /tmp/keys.listed || true
  if [ ! -s /tmp/keys.listed ]; then
    echo "::error::secret_keys_file '$SECRET_KEYS_FILE' lists no keys; refusing to replace the bundle with nothing."
    exit 1
  fi
  # A listed key that is in neither the payload nor the bundle cannot be written.
  LC_ALL=C sort -u /tmp/keys.cur /tmp/keys.payload > /tmp/keys.have
  MISSING=$(LC_ALL=C comm -23 /tmp/keys.listed /tmp/keys.have | paste -sd, -)
  if [ -n "$MISSING" ]; then
    echo "::error::Listed in $SECRET_KEYS_FILE but in neither the payload nor the current bundle: $MISSING. Nothing written."
    exit 1
  fi
  LC_ALL=C comm -23 /tmp/keys.cur /tmp/keys.listed > /tmp/keys.dropped
  UNLISTED=$(LC_ALL=C comm -13 /tmp/keys.listed /tmp/keys.payload | paste -sd, -)
  if [ -n "$UNLISTED" ]; then
    echo "::warning::Payload key(s) not listed in $SECRET_KEYS_FILE: $UNLISTED. They are written now and dropped by the next replace run."
  fi
  DROPPED=$(paste -sd, - < /tmp/keys.dropped)
  if [ -n "$DROPPED" ] && [ "$DRY_RUN" != "true" ]; then
    CONFIRMED=$(printf '%s' "$CONFIRM_REMOVED" | tr ',' '\n' \
      | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v '^$' | LC_ALL=C sort -u | paste -sd, - || true)
    if [ "$CONFIRMED" != "$DROPPED" ]; then
      echo "::error::This run would drop key(s) from the bundle: $DROPPED. Set confirm_removed to exactly that list to proceed (got '${CONFIRMED}')."
      exit 1
    fi
  fi
  # Keep only the listed keys' current lines (order preserved).
  awk -F= 'NR==FNR{k[$0]=1; next} ($1"" in k)' /tmp/keys.listed /tmp/bundle.env > /tmp/bundle.env.new
  mv /tmp/bundle.env.new /tmp/bundle.env
else
  : > /tmp/keys.dropped
fi
# Overlay the payload (base64 per value so newlines/special chars survive the shell).
while IFS=$'\t' read -r key b64; do
  val=$(printf '%s' "$b64" | base64 -d)
  upsert "$key" "$val"
done < <(printf '%s' "$PAYLOAD_JSON" | jq -r 'to_entries[] | [.key, (.value | @base64)] | @tsv')
# The diff, by NAME only: +added -removed =kept.
LC_ALL=C comm -13 /tmp/keys.cur /tmp/keys.payload > /tmp/keys.added
LC_ALL=C comm -23 /tmp/keys.cur /tmp/keys.dropped > /tmp/keys.kept
{
  echo "### Bundle diff by key name (${MODE})"
  echo '```'
  sed 's/^/+ /' /tmp/keys.added
  sed 's/^/- /' /tmp/keys.dropped
  sed 's/^/= /' /tmp/keys.kept
  echo '```'
} | tee -a "$GITHUB_STEP_SUMMARY"
