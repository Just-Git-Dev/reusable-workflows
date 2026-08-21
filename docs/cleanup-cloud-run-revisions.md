# cleanup-cloud-run-revisions

Prunes **inactive** Cloud Run revisions per service, keeping the traffic-serving revision(s)
plus the `keep_last` most-recent.

Idle revisions cost no compute, so the reason to delete them is not the revision — it is the
**image digest each one pins**. A retained revision holds a reference into Artifact Registry
that stops [`cleanup-gar-images`](cleanup-gar-images.md) from reclaiming that storage. Pair
the two, and **schedule this one first**, so digests freed here are reclaimable on the same
cycle.

A revision holding **any** traffic — a percent split, a tagged target, or `latestReady` — is
never a delete candidate. Deletion is best-effort: a revision that turns out to still be in
use is skipped, not fatal.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | yes | — | project owning the Cloud Run services |
| `gcp_region` | no | `asia-southeast1` | region of the services |
| `wif_provider` | yes | — | WIF provider resource name |
| `service_account` | yes | — | SA email to impersonate |
| `keep_last` | no | `10` | per service, retain this many of the most-recent inactive revisions |
| `services` | no | `''` (all in region) | comma/space-separated list to limit to |
| `dry_run` | no | **`true`** | print the plan only, delete nothing |

`dry_run` defaults to `true`. A caller that wants deletions has to say so.

## Outputs

`candidates` (revisions the plan selected), `deleted` (0 on a dry run), `skipped` (in use or
already gone).

## Required IAM

On `service_account`: `roles/run.developer`.

`roles/run.viewer` is read-only and cannot delete; `run.developer` is the minimum that both
enumerates and deletes. A custom role with `run.services.get`/`list` +
`run.revisions.list`/`delete` also works.

## Example caller

```yaml
name: Cleanup Cloud Run revisions
on:
  schedule:
    - cron: '0 3 * * 0'        # weekly, BEFORE the GAR sweep
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: true

permissions:
  contents: read
  id-token: write

jobs:
  run:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/cleanup-cloud-run-revisions.yml@v2.3.1
    with:
      gcp_project: my-gcp-project
      gcp_region: asia-southeast1
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_DEPLOY_SA }}
      keep_last: '10'
      dry_run: ${{ inputs.dry_run || false }}
```

## Notes

- Run with `dry_run: true` first and read the plan in the job summary. The caller owns both
  the schedule and the dry-run decision.
- Concurrency group is `cleanup-run-revisions-<project>-<region>` with
  `cancel-in-progress: false`: two prunes of the same project/region must never race on a
  delete-set that was computed before the other run started.
