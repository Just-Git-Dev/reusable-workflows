# bootstrap-alerts

Applies a Google Cloud Monitoring notification channel and a set of alert
policies from the **caller repo's** alerts directory, or from a rendered
`policies_artifact` (see [Rendered policies from an artifact](#rendered-policies-from-an-artifact-alertgen--service-alertsyml)
below). Idempotent: existing **unmanaged** channels and policies matched by
`displayName` are skipped unless `force_update: true`; **managed** policies
(see below) are updated only when their content actually changed.

The workflow checks out the *caller*, so each repo keeps its own policy files
under version control. Policy files may contain the literal token
`NOTIFICATION_CHANNEL_PLACEHOLDER`, which is replaced with the resolved channel
resource name before apply.

[`service-alerts.yml`](service-alerts.md) (an app-facing wrapper around a
spec-driven policy generator, "alertgen") renders policy files and hands them
to this workflow via `policies_artifact` instead of a checked-in `alerts_dir` —
see [Rendered policies from an artifact](#rendered-policies-from-an-artifact-alertgen--service-alertsyml)
below.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | yes | — | GCP project id |
| `wif_provider` | yes | — | WIF provider resource name |
| `service_account` | yes | — | SA email to impersonate |
| `alerts_dir` | no | `infra/alerts` | directory in the caller repo |
| `channel_file` | no | `email-channel.yaml` | relative to `alerts_dir` |
| `policy_glob` | no | `policy-*.yaml` | relative to `alerts_dir` |
| `force_update` | no | `false` | overwrite existing policies (destructive) |
| `policies_artifact` | no | `''` | name of an Actions artifact holding rendered policy files + the channel file; when set it replaces `alerts_dir` as the source (see below) |
| `dry_run` | no | `false` | plan only — print what would create/update/leave unchanged, make no create/update calls |

## Outputs

`channel_name`, `policies_created`, `policies_updated`, `policies_skipped`,
`policies_failed`, `policies_drifted` (managed policies whose live content was
hand-edited since the last apply — see below).

## Required IAM

On `service_account`: `roles/monitoring.alertPolicyEditor`,
`roles/monitoring.notificationChannelEditor`.

## Example caller

```yaml
name: Bootstrap Cloud Monitoring alerts
on:
  workflow_dispatch:
    inputs:
      force_update:
        type: boolean
        default: false

permissions:
  contents: read
  id-token: write

jobs:
  run:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-alerts.yml@v2.10.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_INFRA_SA }}
      force_update: ${{ inputs.force_update }}
```

## Policy file format — YAML or JSON

Both are accepted. Files are parsed with `yaml.safe_load`, and JSON is a subset
of YAML, so a policy set written as JSON (what `gcloud alpha monitoring policies
describe` emits) works without conversion. Point the globs at it:

```yaml
    with:
      channel_file: email-channel.json
      policy_glob: 'policy-*.json'
```

The same parser backs `validate-alerts.yml`, so the linter and the applier agree
on what a policy file is. They disagreed until the 2026-09-07 fix — see that
date's RCA in `DECISIONS.md`.

## Adopting this from a hand-rolled apply script

Two things a local `apply-alerts.sh` typically does differently, both of which
must change before the first run:

1. **Attach the channel in the file, not on the command line.** A script that
   passes `--notification-channels=<id>` leaves the policy JSON with no
   `notificationChannels` key. This workflow substitutes the literal
   `NOTIFICATION_CHANNEL_PLACEHOLDER` instead, and `validate-alerts.yml`
   *fails* a policy that lacks it — a policy that notifies nobody is the
   failure mode that gate exists to catch. Add to each policy file:

   ```json
   "notificationChannels": ["NOTIFICATION_CHANNEL_PLACEHOLDER"]
   ```

2. **Editing a policy file is a no-op by default.** Existing policies are
   matched by `displayName` and *skipped*; run with `force_update: true` to
   push an edit to a live policy. A local script with the same skip-if-exists
   behaviour has the same trap, silently.

## Failure modes it guards against

- A `channels create` that exits 0 but prints nothing no longer substitutes an
  **empty** channel name into every policy — the job fails instead.
- An unmatched `policy_glob` fails the job rather than silently applying nothing
  (the shell would otherwise pass the unexpanded glob through as a filename).

## Managed policies (`userLabels.managed_by: alertgen`)

A policy file whose `userLabels.managed_by` is exactly `alertgen` is **managed**,
and is identified and updated differently from a hand-written one:

- **Identity is `alertgen_owner` + `rule_id` labels, never `displayName`.** A
  managed file must also carry a non-empty `userLabels.spec_hash` — if any of
  the three is missing, that file fails (not a silent skip).
- The live policy is looked up by those two labels
  (`gcloud alpha monitoring policies list --filter='userLabels.alertgen_owner="…" AND userLabels.rule_id="…"'`).
  More than one match is an error (ambiguous, never guessed at).
- **Zero label matches, but a policy with that `displayName` already exists:**
  this is a hand-written policy sitting on a name alertgen owns. It is an
  **ERROR**, not a skip and not an overwrite — delete or rename the hand-written
  policy (after checking it against the rendered spec) and re-run.
- **Zero label matches, no `displayName` collision:** created normally.
- **One label match:** the live `userLabels.spec_hash` is compared with the
  file's. Different (or `force_update: true`) → updated. If the live
  `mutationRecord.mutatedBy` is not the applier's own service account, a
  `::warning::` names who last touched it before the update overwrites that
  edit. Equal → left unchanged, **and** the live policy's content is projected
  onto the rendered file's key paths (ignoring `userLabels` and
  `notificationChannels`) and compared; a difference means someone hand-edited
  the live policy without changing the spec, and is reported via
  `policies_drifted` and a `::warning::` rather than silently overwritten —
  set `force_update: true` to reset it to the rendered spec.
- `prune` (deleting a managed policy whose rule was removed from the spec) is
  **deferred**; nothing in this workflow deletes a policy today.

## `dry_run`

Set `dry_run: true` to plan without applying: the notification-channel and
policy create/update calls are skipped, and each line is prefixed `would
create:` / `would update:` instead of `created:` / `updated:` (`unchanged:` /
`skipped (exists):` are unaffected — those already made no call). If the
channel does not exist yet, `channel_name` comes back as the sentinel
`DRY_RUN_UNCREATED_CHANNEL` instead of a resolved resource name. The `created` /
`updated` / `skipped` / `drifted` counts reflect the plan either way, so a
dry run's job summary reads the same as the corresponding real run would.

## Rendered policies from an artifact (alertgen / `service-alerts.yml`)

Set `policies_artifact` to the name of an Actions artifact that contains both
the rendered policy files and the channel file (this is how `service-alerts.yml`
calls this workflow after `alertgen render`). When set, it replaces `alerts_dir`
entirely: the artifact is downloaded to `.alertgen-policies`, which becomes the
effective `alerts_dir` for the rest of the job — `channel_file` and
`policy_glob` are still read relative to it. A download failure (e.g. the
artifact expired or was never uploaded) fails the job; there is no silent
fallback to an empty policy set.
