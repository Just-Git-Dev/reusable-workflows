#!/usr/bin/env bash
# Refuse any boolean-typed input that is not exactly 'true' or 'false'.
#
# GitHub's `if: inputs.x != 'true'` compares case-insensitively; the scripts compare with bash
# `[ "$X" = "true" ]`, which is case-sensitive. So `dry_run: True` skipped the live-write guard in
# the `if:` while the scripts still read it as not-true, and `yes` or `1` did a LIVE write. One
# closed vocabulary makes the `if:` and the scripts agree.
#
# Env (never interpolated): FORCE, DRY_RUN, CONCURRENCY_DECLARED.
set -eo pipefail

BAD=0
for name in FORCE DRY_RUN CONCURRENCY_DECLARED; do
  value="${!name-}"
  case "$value" in
    true|false) ;;
    *)
      echo "::error::input $(printf '%s' "$name" | tr '[:upper:]' '[:lower:]') must be exactly 'true' or 'false' (got '${value}'). Refusing: 'yes', '1' or 'True' would be read differently by the workflow's if: and by the scripts."
      BAD=1 ;;
  esac
done
exit "$BAD"
