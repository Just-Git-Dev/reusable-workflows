#!/usr/bin/env bash
# Roll the bundle forward to its previous content when the rotation failed before the roll.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
#
# Fires ONLY when an earlier step failed AND the Cloud Run roll did NOT
# succeed. In that window nothing consumes the new version yet, so it is
# safe to revert `latest` to the previously-in-use content.
#
# Revert by ROLL-FORWARD, not by disabling the new version: `latest` always
# points to the HIGHEST version number, so disabling it would leave `latest`
# on a DISABLED version and break both `access latest` and Cloud Run's
# `<secret>:latest` mount. Instead copy the prior content into a fresh
# ENABLED version, then disable the bad new one (now safe — no longer newest).
#
# Deliberately NOT failure()-blanket: if the failure lands on a post-deploy
# step (grace/cleanup/disable), the signer AND verifier are already on the
# new secret, and reverting SM here would BREAK signing.
set -eo pipefail

NEW_VERSION="${NEW_VERSION##*/}"
CUR_VERSION="${CUR_VERSION##*/}"
echo "::warning::Rotation failed before the signer moved over — restoring ${BUNDLE_SECRET} latest to version ${CUR_VERSION}."
gcloud secrets versions access "$CUR_VERSION" \
  --secret="$BUNDLE_SECRET" --project="$GCP_PROJECT" > /tmp/rollback.env
if [ ! -s /tmp/rollback.env ]; then
  echo "::error::Could not read previous version ${CUR_VERSION} — manual intervention needed."
  exit 1
fi
gcloud secrets versions add "$BUNDLE_SECRET" \
  --project="$GCP_PROJECT" --data-file=/tmp/rollback.env
rm -f /tmp/rollback.env
# A PARTIAL roll (service A rolled onto N+1, service B failed) leaves live revisions
# pinning N+1: disabling it would break their next cold start. Refuse to disable a
# version any revision with traffic > 0 still pins; leave it ENABLED and fail loudly
# so a human looks. A listing failure also leaves it enabled (fail closed).
PINNED=""
mark() { case " $PINNED " in *" $1 "*) ;; *) PINNED="${PINNED} $1" ;; esac; }
# shellcheck disable=SC2016
# (jq program: the $vars are jq's, not the shell's)
PINS_JQ='def pins($s): . as $r
          | [$r.spec.containers[]?.volumeMounts[]?.name] as $mounted
          | ( [$r.spec.volumes[]?
               | select(.secret.secretName == $s and (.name as $v | $mounted | index($v) != null))
               | .secret.items[]? | (.key // .version) | tostring | sub("^.*/"; "")]
            + [$r.spec.containers[]?.env[]?.valueFrom.secretKeyRef?
               | select(.name == $s) | .key | tostring | sub("^.*/"; "")] );'
# LIVE = a revision with traffic > 0 or a tag, the latest READY and latest CREATED
# revisions (the template's revision takes traffic as soon as it is ready), and the
# service TEMPLATE itself. Read from the newest-50 list AND by name: a traffic-holding
# revision can be older than the 50 newest.
IFS=',' read -ra SERVICES <<< "$SERVICES_CSV"
for svc in "${SERVICES[@]}"; do
  svc="${svc#"${svc%%[![:space:]]*}"}"   # ltrim
  svc="${svc%"${svc##*[![:space:]]}"}"   # rtrim
  [ -z "$svc" ] && continue
  if ! gcloud --project="$GCP_PROJECT" run services describe "$svc" \
        --region="$GCP_REGION" --format=json </dev/null > /tmp/service.json \
     || ! gcloud --project="$GCP_PROJECT" run revisions list --service="$svc" \
        --region="$GCP_REGION" --sort-by=~metadata.creationTimestamp --limit=50 \
        --format=json </dev/null > /tmp/revisions.json; then
    echo "::error::Could not read ${svc}'s revisions — leaving version ${NEW_VERSION} ENABLED (cannot prove nothing pins it). Manual intervention needed."
    exit 1
  fi
  [ -s /tmp/service.json ] || echo '{}' > /tmp/service.json
  [ -s /tmp/revisions.json ] || echo '[]' > /tmp/revisions.json
  if jq -e --arg s "$BUNDLE_SECRET" --arg n "$NEW_VERSION" --slurpfile svc /tmp/service.json \
       "$PINS_JQ"'
       ($svc[0].status.latestReadyRevisionName // "") as $ready
       | ([$svc[0].status.traffic[]? | select((.percent // 0) > 0 or ((.tag // "") != ""))
           | (.revisionName // $ready)]
          + [$ready, ($svc[0].status.latestCreatedRevisionName // "")]) as $live
       | ( [.[] | select(.metadata.name as $nm | $live | index($nm)) | pins($s)[]]
           + ($svc[0].spec.template // {} | pins($s)) )
       | index($n) != null' /tmp/revisions.json > /dev/null; then
    mark "$svc"
  fi
  jq -r '(.status.latestReadyRevisionName // "") as $ready | $ready,
         (.status.latestCreatedRevisionName // ""),
         (.status.traffic[]? | select((.percent // 0) > 0 or ((.tag // "") != ""))
          | (.revisionName // $ready))' /tmp/service.json | grep -v '^$' | sort -u > /tmp/live.txt || true
  while read -r rev; do
    [ -n "$rev" ] || continue
    if ! gcloud --project="$GCP_PROJECT" run revisions describe "$rev" \
          --region="$GCP_REGION" --format=json </dev/null > /tmp/rev.json; then
      echo "::error::Could not read revision ${rev} of ${svc} — leaving version ${NEW_VERSION} ENABLED (cannot prove nothing pins it). Manual intervention needed."
      exit 1
    fi
    [ -s /tmp/rev.json ] || echo '{}' > /tmp/rev.json
    if jq -e --arg s "$BUNDLE_SECRET" --arg n "$NEW_VERSION" "$PINS_JQ"'pins($s) | index($n) != null' \
         /tmp/rev.json > /dev/null; then
      mark "$svc"
    fi
  done < /tmp/live.txt
done
if [ -n "$PINNED" ]; then
  echo "::error::Partial roll: live revision(s) of${PINNED} still pin ${BUNDLE_SECRET}:${NEW_VERSION}. NOT disabling it (that would break their next cold start). 'latest' content is restored; re-run the rotation or roll those services back, then disable ${NEW_VERSION} by hand."
  exit 1
fi
gcloud secrets versions disable "$NEW_VERSION" \
  --secret="$BUNDLE_SECRET" --project="$GCP_PROJECT" \
  || echo "::warning::Could not disable failed version ${NEW_VERSION} (non-fatal — latest already restored)."
