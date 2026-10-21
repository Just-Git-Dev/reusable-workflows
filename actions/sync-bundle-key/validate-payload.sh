#!/usr/bin/env bash
# Refuse a payload that would corrupt the bundle or distribute a placeholder.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

if ! printf '%s' "$PAYLOAD_JSON" | jq -e 'type == "object" and length > 0' >/dev/null 2>&1; then
  echo "::error::payload_json must be a non-empty JSON object of {DEST_KEY: value}."
  exit 1
fi
if ! printf '%s' "$PAYLOAD_JSON" | jq -e 'all(.[]; type == "string")' >/dev/null 2>&1; then
  echo "::error::every payload_json value must be a string."
  exit 1
fi
# Value-safety guards (the merge below writes `KEY=value` lines into an env
# file). Every refusal names the KEY only, never the value.
#
# ALWAYS: a newline, CR or NUL in a key or value is written as raw bytes and
# splits or truncates the line, corrupting the bundle. (Byte test via explode:
# no regex or string-escape quirks across jq versions.) TRAILING newlines of a
# value are not refused: the merge reads it with `val=$(...)`, which strips
# them, exactly as v3.7.0 did, so they never reach the file.
BADBYTES=$(printf '%s' "$PAYLOAD_JSON" | jq -r '
  def bad: explode | any(. == 0 or . == 10 or . == 13);
  [to_entries[] | select((.key | bad) or (.value | sub("\n+\\z"; "") | bad)) | .key | @json] | join(", ")')
if [ -n "$BADBYTES" ]; then
  echo "::error::payload_json key or value contains a newline, carriage return or NUL: $BADBYTES. A bundle line is KEY=value on one line; refusing to write what would corrupt the .env."
  exit 1
fi
# strict_values (default false, so v3.7.0 payloads keep working): the checks
# below only refuse what v3.7.0 wrote without corrupting anything.
if [ "$STRICT_VALUES" = "true" ]; then
  # Keys must be env-var names. Printed JSON-quoted (@json) because a bad key
  # may hold `::` that would forge a workflow command.
  BADKEYS=$(printf '%s' "$PAYLOAD_JSON" \
    | jq -r '[keys[] | select(test("\\A[A-Za-z_][A-Za-z0-9_]*\\z") | not) | @json] | join(", ")')
  if [ -n "$BADKEYS" ]; then
    echo "::error::payload_json key(s) are not valid env names (^[A-Za-z_][A-Za-z0-9_]*\$): $BADKEYS"
    exit 1
  fi
  # Empty / whitespace-only values, and values that are a whole placeholder
  # (-, changeme, todo, xxx..., <...>, ${...}). Compared after trimming and
  # lowercasing; a real credential merely CONTAINING one of these passes.
  # Not subject to min_value_length: 0, which only relaxes the length floor.
  PLACEHOLDER=$(printf '%s' "$PAYLOAD_JSON" | jq -r '
    [to_entries[]
     | select((.value | gsub("\\A\\s+|\\s+\\z"; "") | ascii_downcase)
              | (. == "" or . == "-" or test("\\A(change[-_]?me|placeholder|todo|tbd|dummy|example|x{3,})\\z")
                 or test("\\A<.*>\\z") or test("\\A\\$\\{.*\\}\\z")))
     | .key] | join(", ")')
  if [ -n "$PLACEHOLDER" ]; then
    echo "::error::payload_json value(s) are empty, whitespace-only or a placeholder: $PLACEHOLDER. Refusing to distribute a value that cannot be a credential. Source the real value from a GitHub secret."
    exit 1
  fi
fi
# Mask every value so nothing leaks in later logs.
while IFS= read -r v; do
  [ -n "$v" ] && echo "::add-mask::$v"
done < <(printf '%s' "$PAYLOAD_JSON" | jq -r '.[]')
# Reject values too short to be a real credential. A rotation workflow
# "succeeded" in May 2026 while distributing the literal string "-":
# it is a non-empty string, so the two checks above both passed, and
# the placeholder sat in the bundle for two months. Report the KEY
# only — never the value, which may be a real secret.
if [ "${MIN_VALUE_LEN:-0}" -gt 0 ]; then
  SHORT=$(printf '%s' "$PAYLOAD_JSON" \
    | jq -r --argjson n "$MIN_VALUE_LEN" '[to_entries[] | select((.value|length) < $n) | .key] | join(", ")')
  if [ -n "$SHORT" ]; then
    echo "::error::payload_json value(s) shorter than $MIN_VALUE_LEN chars: $SHORT. Refusing to distribute a value that cannot be a credential. Pass min_value_length: 0 to override."
    exit 1
  fi
fi
COUNT=$(printf '%s' "$PAYLOAD_JSON" | jq 'length')
echo "Payload carries $COUNT key(s)."
printf '%s' "$PAYLOAD_JSON" | jq -r 'keys[] | "  will upsert: \(.)"'
