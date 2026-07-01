# cleanup-gar-images

Age-sweeps every image in a GAR repo. Builds the keep-set from digests live on
**all** Cloud Run Services *and* Jobs in-region (so cron/migrate Jobs are
protected), plus the most-recent N semver tags per image and `latest`/safe-prefix
tags. The caller owns the `schedule` and the `dry_run` decision.

## Key inputs

`gcp_project`, `wif_provider`, `service_account`, `gar_repo` (req);
`gcp_region` (`asia-southeast1`), `keep_semver_count` (`5`),
`untagged_max_age_days` (`15`), `tagged_max_age_days` (`30`), `dry_run` (`true`).

`REPO_PATH` is derived as `<region>-docker.pkg.dev/<project>/<gar_repo>`.

## Example caller — AutoMahn/project (daily, monthly dry-run preview)

```yaml
name: Cleanup GAR images
on:
  workflow_dispatch:
    inputs:
      dry_run: { type: boolean, default: true }
  schedule:
    - cron: '0 4 * * *'
jobs:
  # Real deletions daily, except a dry-run preview on the 1st of the month.
  resolve:
    runs-on: ubuntu-latest
    outputs: { dry: ${{ steps.d.outputs.dry }} }
    steps:
      - id: d
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then D="${{ inputs.dry_run }}";
          elif [ "$(date -u +%d)" -eq 1 ]; then D=true; else D=false; fi
          echo "dry=$D" >> "$GITHUB_OUTPUT"
  cleanup:
    needs: resolve
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/cleanup-gar-images.yml@v1
    with:
      gcp_project: auto-mahn
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_CLEANER_SA }}
      gar_repo: backend
      dry_run: ${{ needs.resolve.outputs.dry == 'true' }}
```

Realm-ID/project: same, `gcp_project: realm-id`, its own cleaner SA. **First run
`dry_run: true` and review the plan** — Realm-ID gains Job/Service digest
protection it did not have before, so the keep-set changes.
