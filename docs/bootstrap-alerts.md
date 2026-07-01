# bootstrap-alerts

Applies a GCP Monitoring notification channel + alert policies from the **caller
repo's** `infra/alerts/` (`email-channel.yaml` + `policy-*.yaml`). Idempotent:
existing channels/policies matched by `displayName` are skipped unless
`force_update: true`.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | yes | — | e.g. `auto-mahn`, `traide-in` |
| `wif_provider` | yes | — | pass `${{ vars.GCP_WIF_PROVIDER }}` |
| `service_account` | yes | — | pass the org's infra SA var |
| `alerts_dir` | no | `infra/alerts` | dir in caller repo |
| `force_update` | no | `false` | overwrite existing policies (destructive) |

Required IAM on the SA: `roles/monitoring.alertPolicyEditor`,
`roles/monitoring.notificationChannelEditor`.

## Example caller — AutoMahn/project `.github/workflows/bootstrap-alerts.yml`

```yaml
name: Bootstrap Cloud Monitoring alerts
on:
  workflow_dispatch:
    inputs:
      force_update: { type: boolean, default: false }
jobs:
  run:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-alerts.yml@v1
    with:
      gcp_project: auto-mahn
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_ROTATOR_SA }}
      force_update: ${{ inputs.force_update }}
```

## Example caller — Traide-Co/project

Same, with `gcp_project: traide-in` and `service_account: ${{ vars.GCP_INFRA_SA }}`.
