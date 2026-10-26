#!/usr/bin/env bash
# Generate the new value, mask it at once, and keep it ONLY in a 0600 file under RUNNER_TEMP that
# the shred step removes. It is never a step output, an env var or a summary line.
#
# Env: SECRET_BYTES, DRY_RUN.
set -eo pipefail

[ "${DRY_RUN:-false}" != "true" ] || { echo "::error::refusing to generate a value in dry_run"; exit 1; }
DIR="${RUNNER_TEMP:?}/rotate-external"
mkdir -p "$DIR"
chmod 700 "$DIR"
umask 077
# hex so it is safe in a dotenv value and a JSON string alike.
NEW_SECRET=$(openssl rand -hex "$SECRET_BYTES")
echo "::add-mask::$NEW_SECRET"
printf '%s' "$NEW_SECRET" > "$DIR/new-secret"
