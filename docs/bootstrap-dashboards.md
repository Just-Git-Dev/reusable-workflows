# bootstrap-dashboards

Applies Google Cloud Monitoring **dashboards** from the **caller repo's** dashboards
directory, mirroring [`bootstrap-alerts`](bootstrap-alerts.md). The workflow checks out the
caller, so each project keeps its own dashboard JSON under version control.

Identity is `displayName`, the same convention the alerts workflow uses. Existing dashboards
are left untouched unless `force_update: true`, in which case they are updated **in place**
via their resource name — not delete-and-recreate, which would mint a new dashboard id and
break every bookmark and console link pointing at it.

Dashboards are declared as JSON rather than YAML because JSON is what the console's "JSON
editor" round-trips: a dashboard tuned by hand in the UI can be pasted straight back into the
repo.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | yes | — | GCP project id the dashboards belong to |
| `wif_provider` | yes | — | WIF provider resource name |
| `service_account` | yes | — | SA email to impersonate |
| `dashboards_dir` | no | `infra/dashboards` | directory in the caller repo |
| `dashboard_glob` | no | `dashboard-*.json` | relative to `dashboards_dir` |
| `force_update` | no | `false` | update existing dashboards in place instead of skipping |

## Outputs

`created`, `updated`, `skipped`, `failed`.

`failed` is a count, and a non-zero value also fails the run — it is there so a caller can
report the number, not so it can be ignored.

## Required IAM

On `service_account`: `roles/monitoring.dashboardEditor` (or `roles/monitoring.editor`,
which subsumes it).

## Example caller

```yaml
name: Bootstrap Cloud Monitoring dashboards
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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-dashboards.yml@v2.6.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_INFRA_SA }}
      force_update: ${{ inputs.force_update }}
```

## Notes

- Runs under a `bootstrap-dashboards-<gcp_project>` concurrency group with
  `cancel-in-progress: false` — two applies to one project never interleave, and neither is
  cancelled halfway through.
- `force_update` is the only path that mutates an existing dashboard. Default behaviour is
  additive, so re-running after adding one file applies only that file.
