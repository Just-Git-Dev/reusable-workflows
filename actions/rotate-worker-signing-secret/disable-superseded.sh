#!/usr/bin/env bash
# Disable the superseded bundle versions (keep-set), never destroy.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved from the v4.0.0 reusable workflow; docs/rotate-worker-signing-secret-action.md.
#
# Reached only when every service rolled: a failed roll fails the step
# above, and `if: success()` is the implicit default for later steps.
#
# KEEP-SET (v4). ENABLED versions kept = the union of
#   - the new version N+1,
#   - the version pinned by each of the two newest PREVIOUS revisions of every
#     rolled service (read only from volumes a volumeMount actually uses; an
#     orphan declared volume pins nothing), so the previous revision stays a
#     valid rollback target, and
#   - the `keep_enabled_count` newest ENABLED versions (a floor, minimum 1).
# Everything else is disabled. A pre-existing ENABLED tail (a hand-added
# version, or one from manage-config-secrets) is therefore mopped up too.
#
# DISABLE ONLY, never destroy. Destruction needs a quarantine clock (GSM
# stores no disabled-at timestamp, so it comes from Admin Activity audit
# logs) and the Cloud Run consumer scan; both live in
# cleanup-secret-versions, and this workflow deliberately holds neither
# roles/logging.viewer nor roles/run.viewer. See DECISIONS.md 2026-08-17.
set -eo pipefail

case "$KEEP_ENABLED_COUNT" in
  ''|*[!0-9]*)
    echo "::error::keep_enabled_count must be a non-negative integer (got '$KEEP_ENABLED_COUNT')."
    exit 1 ;;
esac
if [ "$KEEP_ENABLED_COUNT" -lt 1 ]; then
  echo "::error::keep_enabled_count must be >= 1: 0 disables every version and leaves 'latest' unresolvable."
  exit 1
fi
NEW_VERSION="${NEW_VERSION##*/}"
# `latest` resolves SERVER-SIDE to the newest ENABLED version, so keeping
# at least one guarantees this step can never silently repoint it.
# Written to a file rather than piped: a heredoc consumer downstream of a
# pipe claims stdin and kills the producer (shellcheck SC2259).
gcloud secrets versions list "$BUNDLE_SECRET" \
  --project="$GCP_PROJECT" --filter='state=ENABLED' \
  --sort-by=~createTime --format='value(name)' > /tmp/enabled.raw
sed 's|.*/||' /tmp/enabled.raw | grep -v '^$' > /tmp/enabled.txt || true
TOTAL=$(wc -l < /tmp/enabled.txt | tr -d ' ')
# Keep-set, one version per line.
: > /tmp/keep.txt
[ -z "$NEW_VERSION" ] || echo "$NEW_VERSION" >> /tmp/keep.txt
head -n "$KEEP_ENABLED_COUNT" /tmp/enabled.txt >> /tmp/keep.txt
# Keep-set = every pin a LIVE or recent revision holds, across EVERY consumer of the
# bundle secret in the project, in EVERY region (not only services_csv / GCP_REGION):
#   (a) each revision with traffic > 0, or a tag (served at its tag URL), on a Service
#       (after a `rollback to_revision` traffic stays pinned to an old revision until
#       `--to-latest`). Read BY NAME as well as out of the newest-50 list: a pin can
#       sit on a revision older than the 50 newest for as long as traffic is held there,
#   (b) the two newest revisions before the one just rolled, per Service,
#   (c) every Cloud Run Job's pin (a Job has no traffic; its pin is live).
# A pin is a secret volume item (`volumes[].secret.items[].key`) a volumeMount uses OR an
# env var `valueFrom.secretKeyRef{name,key}`.
# A listing/describe failure fails the step BEFORE anything is disabled.
# shellcheck disable=SC2016
# (jq program: the $vars are jq's, not the shell's)
PINS_JQ='def pins($s): . as $r
          | [$r.spec.containers[]?.volumeMounts[]?.name] as $mounted
          | ( [$r.spec.volumes[]?
               | select(.secret.secretName == $s and (.name as $v | $mounted | index($v) != null))
               | .secret.items[]? | (.key // .version) | tostring | sub("^.*/"; "")]
            + [$r.spec.containers[]?.env[]?.valueFrom.secretKeyRef?
               | select(.name == $s) | .key | tostring | sub("^.*/"; "")] );'
# No --region: list every region the project uses; the label carries each one's region.
LOC='metadata.labels."cloud.googleapis.com/location"'
gcloud --project="$GCP_PROJECT" run services list \
  --format="value(metadata.name,${LOC})" </dev/null > /tmp/consumers.raw 2> /tmp/consumers.err
# An all-region list that skipped a region ("did not respond ... may be incomplete") would
# hide that region's consumers from the keep-set: refuse, disable nothing.
cat /tmp/consumers.err >&2
if grep -qiE 'did not respond|may be incomplete' /tmp/consumers.err; then
  echo "::error::the all-region services list did not cover every region (refusing; nothing disabled): $(head -c 300 /tmp/consumers.err)" >&2
  exit 1
fi
IFS=',' read -ra LISTED <<< "$SERVICES_CSV"
for svc in "${LISTED[@]}"; do
  svc="${svc#"${svc%%[![:space:]]*}"}"   # ltrim
  svc="${svc%"${svc##*[![:space:]]}"}"   # rtrim
  [ -z "$svc" ] || printf '%s\t%s\n' "$svc" "$GCP_REGION" >> /tmp/consumers.raw
done
# name<TAB>region, an empty region meaning GCP_REGION.
awk -F'\t' -v r="$GCP_REGION" 'NF && $1 != "" { print $1 "\t" ($2 == "" ? r : $2) }' \
  /tmp/consumers.raw | sort -u > /tmp/consumers.txt
while IFS=$'\t' read -r svc reg; do
  [ -n "$svc" ] || continue
  gcloud --project="$GCP_PROJECT" run services describe "$svc" \
    --region="$reg" --format=json </dev/null > /tmp/service.json
  [ -s /tmp/service.json ] || echo '{}' > /tmp/service.json
  gcloud --project="$GCP_PROJECT" run revisions list --service="$svc" \
    --region="$reg" \
    --sort-by=~metadata.creationTimestamp --limit=50 --format=json \
    </dev/null > /tmp/revisions.json
  [ -s /tmp/revisions.json ] || echo '[]' > /tmp/revisions.json
  jq -r --arg s "$BUNDLE_SECRET" --arg n "$NEW_VERSION" --slurpfile svc /tmp/service.json "
    $PINS_JQ
    (\$svc[0].status.latestReadyRevisionName // \"\") as \$latest
    | ([\$svc[0].status.traffic[]? | select((.percent // 0) > 0 or ((.tag // \"\") != \"\"))
        | (.revisionName // \$latest)]) as \$live
    | ( [.[] | select(.metadata.name as \$nm | \$live | index(\$nm)) | pins(\$s)[]]
      + [.[0:3] | map({pins: pins(\$s)}) | map(select((.pins | index(\$n)) == null))
         | .[0:2][].pins[]] )
    | .[] | select(test(\"^[0-9]+\$\"))" /tmp/revisions.json >> /tmp/keep.txt
  # (a) by name: every traffic-holding (or tagged) revision, listed or not.
  jq -r '(.status.latestReadyRevisionName // "") as $latest | .status.traffic[]?
         | select((.percent // 0) > 0 or ((.tag // "") != "")) | (.revisionName // $latest)
         | select(. != "")' /tmp/service.json | sort -u > /tmp/live.txt
  while read -r rev; do
    [ -n "$rev" ] || continue
    gcloud --project="$GCP_PROJECT" run revisions describe "$rev" \
      --region="$reg" --format=json </dev/null > /tmp/rev.json
    [ -s /tmp/rev.json ] || echo '{}' > /tmp/rev.json
    jq -r --arg s "$BUNDLE_SECRET" "
      $PINS_JQ
      pins(\$s)[] | select(test(\"^[0-9]+\$\"))" /tmp/rev.json >> /tmp/keep.txt
  done < /tmp/live.txt
done < /tmp/consumers.txt
gcloud --project="$GCP_PROJECT" run jobs list \
  --format="value(metadata.name,${LOC})" </dev/null > /tmp/jobs.raw 2> /tmp/jobs.err
cat /tmp/jobs.err >&2
if grep -qiE 'did not respond|may be incomplete' /tmp/jobs.err; then
  echo "::error::the all-region jobs list did not cover every region (refusing; nothing disabled): $(head -c 300 /tmp/jobs.err)" >&2
  exit 1
fi
awk -F'\t' -v r="$GCP_REGION" 'NF && $1 != "" { print $1 "\t" ($2 == "" ? r : $2) }' \
  /tmp/jobs.raw | sort -u > /tmp/jobs.txt
while IFS=$'\t' read -r job reg; do
  [ -n "$job" ] || continue
  gcloud --project="$GCP_PROJECT" run jobs describe "$job" \
    --region="$reg" --format=json </dev/null > /tmp/job.json
  [ -s /tmp/job.json ] || echo '{}' > /tmp/job.json
  jq -r --arg s "$BUNDLE_SECRET" "
    $PINS_JQ
    (.spec.template.spec.template // {}) | pins(\$s)[] | select(test(\"^[0-9]+\$\"))" \
    /tmp/job.json >> /tmp/keep.txt
done < /tmp/jobs.txt
grep -vxFf /tmp/keep.txt /tmp/enabled.txt > /tmp/to-disable.txt || true
COUNT=$(wc -l < /tmp/to-disable.txt | tr -d ' ')
echo "ENABLED versions: $TOTAL; keeping $(sort -u /tmp/keep.txt | wc -l | tr -d ' ') in the keep-set; disabling $COUNT."
if [ "$COUNT" -gt 1 ]; then
  echo "::warning::Disabling $COUNT versions, more than the one this run superseded — a pre-existing ENABLED tail was present. Every one is reversible with 'gcloud secrets versions enable'."
fi
while read -r v; do
  [ -n "$v" ] || continue
  echo "Disabling version $v"
  gcloud secrets versions disable "$v" \
    --secret="$BUNDLE_SECRET" \
    --project="$GCP_PROJECT" </dev/null
done < /tmp/to-disable.txt
