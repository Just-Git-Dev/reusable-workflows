# bootstrap-alerts

Applies a Google Cloud Monitoring notification channel and a set of alert
policies from the **caller repo's** alerts directory. Idempotent: existing
channels and policies matched by `displayName` are skipped unless
`force_update: true`.

The workflow checks out the *caller*, so each repo keeps its own policy files
under version control. Policy files may contain the literal token
`NOTIFICATION_CHANNEL_PLACEHOLDER`, which is replaced with the resolved channel
resource name before apply.

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

## Outputs

`channel_name`, `policies_created`, `policies_updated`, `policies_skipped`.

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-alerts.yml@v1.1.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_INFRA_SA }}
      force_update: ${{ inputs.force_update }}
```

## Failure modes it guards against

- A `channels create` that exits 0 but prints nothing no longer substitutes an
  **empty** channel name into every policy — the job fails instead.
- An unmatched `policy_glob` fails the job rather than silently applying nothing
  (the shell would otherwise pass the unexpanded glob through as a filename).
