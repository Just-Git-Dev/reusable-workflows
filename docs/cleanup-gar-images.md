# cleanup-gar-images

Age-sweeps every image in a Google Artifact Registry Docker repo.

The keep-set is built from digests that are live on **all** Cloud Run Services
*and* Jobs in-region (cron and migration containers commonly live on Jobs, not
Services), plus the most-recent N semver tags per image, plus any tag listed in
`keep_tags` or matching a prefix in `keep_tag_prefixes`. Everything else is
deleted once it exceeds the untagged/tagged age limits.

If **zero** live digests resolve, the workflow aborts rather than treating the
whole repo as garbage.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | yes | — | |
| `gar_repo` | yes | — | Artifact Registry repository name |
| `wif_provider` / `service_account` | yes | — | |
| `gcp_region` | no | `asia-southeast1` | region of both the GAR repo and Cloud Run |
| `keep_semver_count` | no | `5` | most-recent `vX.Y.Z` digests kept per image |
| `untagged_max_age_days` | no | `15` | |
| `tagged_max_age_days` | no | `30` | |
| `keep_tags` | no | `latest,buildcache` | exact tags never deleted |
| `keep_tag_prefixes` | no | `hotfix-,rc-,debug-` | tag prefixes never deleted |
| `dry_run` | no | `true` | `true` prints the plan and deletes nothing |

The repo path is derived as `<gcp_region>-docker.pkg.dev/<gcp_project>/<gar_repo>`.

## Outputs

`candidates`, `deleted`, `skipped`.

## Required IAM

On `service_account`: `roles/artifactregistry.repoAdmin` (on the target repo)
and `roles/run.viewer` (to enumerate live Services and Jobs).

## `buildcache` and registry build caches

If you use a BuildKit **registry** cache (`cache-to:
type=registry,ref=...:buildcache`), that cache is an ordinary tagged image in
the same repo. It is in the default `keep_tags` for exactly this reason — with
it removed, a repo that goes `tagged_max_age_days` without a release would have
its build cache age-deleted and the next build would be a cold rebuild.

## Always dry-run first

`dry_run: true` prints the full plan to the step summary. Read it before you let
a first real sweep run against a repo — the keep-set is the only thing standing
between the sweep and an image you still need.

## Example caller

Real deletions daily, with a dry-run preview on the 1st of the month.

```yaml
name: Cleanup GAR images
on:
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: true
  schedule:
    - cron: '0 4 * * *'

permissions:
  contents: read
  id-token: write

jobs:
  resolve:
    runs-on: ubuntu-latest
    outputs:
      dry: ${{ steps.d.outputs.dry }}
    steps:
      - id: d
        env:
          EVENT: ${{ github.event_name }}
          REQUESTED: ${{ inputs.dry_run }}
        run: |
          if [ "$EVENT" = "workflow_dispatch" ]; then D="$REQUESTED"
          elif [ "$(date -u +%d)" -eq 1 ]; then D=true
          else D=false
          fi
          echo "dry=$D" >> "$GITHUB_OUTPUT"

  cleanup:
    needs: resolve
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/cleanup-gar-images.yml@v1.1.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_CLEANER_SA }}
      gar_repo: backend
      dry_run: ${{ needs.resolve.outputs.dry == 'true' }}
```

## Concurrency

Deletions run with `xargs -P 8`. The workflow holds a concurrency group keyed on
`<gcp_project>-<gar_repo>` so a manual dispatch cannot race the scheduled sweep
and act on a delete-set computed before the other run started.
