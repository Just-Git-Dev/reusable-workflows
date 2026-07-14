# promote-image

Retag an **already-built** image from one tag to another **without rebuilding**,
then roll the target service onto it. Keyless WIF.

This is the Just-Git-Dev equivalent of `zopsmart/workflows` **prod-deploy**: a
stage pipeline builds and pushes `image:<sha>`; this workflow retags that exact
image `:<sha>` → `:<release>` in Artifact Registry and rolls prod. The retag is
server-side (`gcloud container images add-tag` — no pull/push of layers), so it
is fast and, crucially, **prod runs the identical bytes stage tested** — no
rebuild that could drift.

## When to use it

- **Stage → prod promotion.** Stage deploys `:<sha>`; on a release tag, promote
  that `:<sha>` to `:vX.Y.Z` and roll prod. No second build.
- **Re-point a service** at an image that already exists in GAR.

For the build-and-deploy step itself, use `deploy-cloud-run` / `deploy-gke-service`.

## Inputs

| Name | Default | Notes |
|---|---|---|
| `gcp_region` | (req) | Artifact Registry host region |
| `gar_project` / `gar_repo` / `image_name` | (req) | image path; `image_name` may contain slashes |
| `source_tag` | (req) | existing tag to promote FROM (usually the stage commit SHA) |
| `target_tag` | `''` | tag to promote TO; empty ⇒ the triggering ref name (e.g. the pushed git tag) |
| `require_semver` | `true` | reject a `target_tag` that is not `vX.Y.Z` |
| `also_tag_latest` | `false` | also move `:latest` onto the promoted image |
| `wif_provider` / `service_account` | (req) | keyless WIF |
| `deploy_target` | `none` | `none` \| `gke` \| `cloud-run` — what to roll after retagging |
| `cluster_project` / `cluster_name` / `cluster_location` | — | GKE target (`deploy_target=gke`) |
| `namespace` / `svc_name` | — | GKE workload + container name |
| `workload_type` / `deploy_method` | `deployment` / `kubectl` | `deployment`\|`cron`; `kubectl`\|`helm` |
| `helm_chart` / `helm_release` / `helm_values_path` / `helm_extra_args` | — | helm only |
| `app_version` | `''` | kubectl/deployment: `set env APP_VERSION=…` after the roll |
| `run_project` / `run_region` / `run_service` | `gar_project` / `gcp_region` / — | Cloud Run target (`deploy_target=cloud-run`) |
| `dry_run` | `false` | print the retag + roll commands without executing |

No secrets — WIF is keyless. `id-token: write` is set by the reusable.

## Example — promote stage `:sha` to a release tag and roll GKE prod

```yaml
name: Promote to prod
on:
  push:
    tags: ['v*.*.*']

permissions:
  contents: read
  id-token: write

jobs:
  promote:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/promote-image.yml@v1.4.0
    with:
      gcp_region: asia-south1
      gar_project: zs-products
      gar_repo: zop-dev
      image_name: customs/api
      source_tag: ${{ github.sha }}   # the stage build tagged with this SHA
      # target_tag omitted ⇒ the pushed tag (vX.Y.Z)
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GKE_DEPLOYER_SA }}
      deploy_target: gke
      cluster_project: zs-products
      cluster_name: internal-products
      cluster_location: asia-south1
      namespace: customs
      svc_name: api
```

## Example — promote and flip a Cloud Run service

```yaml
    with:
      gcp_region: asia-southeast1
      gar_project: realm-id
      gar_repo: backend
      image_name: bff-api
      source_tag: ${{ github.event.inputs.stage_sha }}
      target_tag: ${{ github.event.inputs.release }}
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      deploy_target: cloud-run
      run_service: api
```

## Dry run

`dry_run: true` prints the exact `gcloud container images add-tag` and roll
commands without executing them — the retag is a mutation, so it honours the
repo convention that every mutating workflow has a safe plan mode.

## Concurrency

Keyed on `<gar_project>-<image_name>-<target_tag>` with `cancel-in-progress: false`.
