#!/usr/bin/env bash
# Roll every service onto the new bundle version.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

# `value(name)` may return a full resource path; the mount wants the number.
NEW_VERSION="${NEW_VERSION##*/}"
if [ "$PIN_VERSIONS" = "true" ]; then
  if [ -z "$NEW_VERSION" ]; then
    echo "::error::pin_versions needs the new bundle version, which is empty."
    exit 1
  fi
  SECRET_REF="${BUNDLE_SECRET}:${NEW_VERSION}"
  LABELS="jgd_env_version=${NEW_VERSION},jgd_run=${GITHUB_RUN_ID}"
else
  SECRET_REF="${BUNDLE_SECRET}:latest"
  LABELS=""
fi
IFS=',' read -ra SERVICES <<< "$SERVICES_CSV"
ROLLED=0
FAILED=()
for svc in "${SERVICES[@]}"; do
  svc="${svc#"${svc%%[![:space:]]*}"}"   # ltrim
  svc="${svc%"${svc##*[![:space:]]}"}"   # rtrim
  [ -z "$svc" ] && continue
  if gcloud run services update "$svc" \
       --region="$GCP_REGION" \
       --project="$GCP_PROJECT" \
       --update-secrets="${MOUNT_PATH}=${SECRET_REF}" \
       ${LABELS:+--update-labels="$LABELS"}; then
    echo "rolled: $svc"
    ROLLED=$((ROLLED + 1))
  elif [ "${BOOTSTRAP:-false}" = "true" ]; then
    echo "::warning::Failed to update $svc during bootstrap (may not exist yet) — continuing."
  else
    echo "::error::Failed to roll $svc onto ${SECRET_REF}"
    FAILED+=("$svc")
  fi
done
echo "rolled=$ROLLED" >> "$GITHUB_OUTPUT"

# Fail loud and leave the old version ENABLED. Disabling it now would
# strand any service still reading it.
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "::error::${#FAILED[@]} service(s) failed to roll: ${FAILED[*]}"
  echo "::error::The previous bundle version is still enabled. Fix and re-run."
  exit 1
fi
if [ "$ROLLED" -eq 0 ]; then
  if [ "${BOOTSTRAP:-false}" = "true" ]; then
    echo "::warning::No service rolled during bootstrap — continuing."
  else
    echo "::error::services_csv resolved to zero service names."
    exit 1
  fi
fi
