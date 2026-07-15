# promote-image

Retag an **already-built** image from one tag to another **without rebuilding**,
then roll the target service onto it. Keyless WIF, with a key-based fallback for
callers not yet federated.

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
| `gcp_region` | (req) | GAR host region (used to derive the host when `image_registry` is empty) + Cloud Run region default |
| `image_registry` | `''` | full GAR host (e.g. `us-central1-docker.pkg.dev`); empty ⇒ `<gcp_region>-docker.pkg.dev`. Set to match the exact host stage pushed to |
| `gar_project` / `gar_repo` / `image_name` | (req) | image path; `image_name` may contain slashes |
| `source_tag` | (req) | existing tag to promote FROM (usually the stage commit SHA) |
| `target_tag` | `''` | tag to promote TO; empty ⇒ the triggering ref name (e.g. the pushed git tag) |
| `require_semver` | `true` | reject a `target_tag` that is not `vX.Y.Z` |
| `also_tag_latest` | `false` | also move `:latest` onto the promoted image |
| `wif_provider` / `service_account` | `''` | keyless WIF; empty `wif_provider` ⇒ **key-based** auth via the credential secrets below |
| `deploy_target` | `none` | `none` \| `gke` \| `cloud-run` — what to roll after retagging |
| `cluster_project` / `cluster_name` / `cluster_location` | — | GKE target (`deploy_target=gke`) |
| `namespace` / `svc_name` | — | GKE workload + container name |
| `workload_type` / `deploy_method` | `deployment` / `kubectl` | `deployment`\|`cron`; `kubectl`\|`helm` |
| `helm_chart` / `helm_release` / `helm_values_path` / `helm_extra_args` | — | helm only |
| `app_version` | `''` | kubectl/deployment: `set env APP_VERSION=…` after the roll |
| `run_project` / `run_region` / `run_service` | `gar_project` / `gcp_region` / — | Cloud Run target (`deploy_target=cloud-run`) |
| `commit_sha` | `''` | source commit of the promoted image; stamped as the live commit. Empty ⇒ `github.sha` (the released commit on a tag-triggered promote) |
| `environment` | `''` | when set, also record a GitHub Deployment marking this env's live commit |
| `record_github_deployment` | `true` | record the Deployment (needs `environment` + `deployments: write`) |
| `enforce_forward_only` | `false` | reject an out-of-order (older) release — see below. Requires `environment` |
| `dry_run` | `false` | print the retag + roll commands without executing |

## Auth — WIF (preferred) or key-based

Set `wif_provider` + `service_account` for keyless WIF (no secrets needed;
`id-token: write` is set by the reusable). **Leave `wif_provider` empty** to use
a stored GCP SA-key JSON instead — the interim path for a caller not yet
federated (this is what quizzing-pro prod uses):

| Secret | Format | When required |
|---|---|---|
| `registry_credentials` | GCP SA-key JSON | key-based: authenticates the server-side `add-tag` retag |
| `cluster_credentials` | GCP SA-key JSON | key-based **and** `deploy_target != none`: authenticates the GKE/Cloud Run roll (may equal `registry_credentials`) |

The retag authenticates with `registry_credentials`; the roll re-auths with
`cluster_credentials`, so the two may point at different projects. On the WIF
path both secrets are ignored.

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

## Example — key-based GKE promote (not yet federated)

Prod retags `image:<sha>` → `image:<tag>` and rolls GKE using a stored deploy
key. Mirrors `zopsmart/workflows` prod-deploy 1:1 for a caller without WIF:

```yaml
name: Promote to prod
on:
  push:
    tags: ['v*']

permissions:
  contents: read

jobs:
  promote:
    strategy:
      matrix:
        include:
          - { svc: api,             type: deployment }
          - { svc: payment-enquiry, type: cron }
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/promote-image.yml@v1.7.0
    with:
      gcp_region: ${{ vars.CLUSTER_REGION }}
      image_registry: ${{ vars.IMAGE_REGISTRY }}   # exact host stage pushed to
      gar_project: ${{ vars.REGISTRY_PROJECT }}
      gar_repo: ${{ vars.REGISTRY_REPO }}
      image_name: ${{ matrix.svc }}
      source_tag: ${{ github.sha }}       # the stage build tagged with this SHA
      # target_tag omitted ⇒ the pushed tag (vX.Y.Z)
      # wif_provider omitted ⇒ key-based auth
      deploy_target: gke
      cluster_project: ${{ vars.CLUSTER_PROJECT }}
      cluster_name: ${{ vars.CLUSTER_NAME }}
      cluster_location: ${{ vars.CLUSTER_REGION }}
      namespace: ${{ vars.PROD_NAMESPACE }}
      svc_name: ${{ matrix.svc }}
      workload_type: ${{ matrix.type }}
      app_version: ${{ github.ref_name }}
    secrets:
      registry_credentials: ${{ secrets.PROD_DEPLOY_KEY }}
      cluster_credentials: ${{ secrets.PROD_DEPLOY_KEY }}
```

## Dry run

`dry_run: true` prints the exact `gcloud container images add-tag` and roll
commands without executing them — the retag is a mutation, so it honours the
repo convention that every mutating workflow has a safe plan mode.

## Live-commit stamping

On the roll, the promoted commit (`commit_sha`, else `github.sha`) is stamped onto
the target — Cloud Run label `jgd_commit=<sha>` / GKE annotation
`jgd.dev/commit=<sha>` — and, when `environment` is set, recorded as a GitHub
Deployment. This keeps the [forward-only](release-process.md) baseline accurate:
prod's live commit advances with each promote. Skipped for `deploy_target: none`
(nothing is rolled).

## Forward-only (opt-in)

Set `enforce_forward_only: true` (with `environment`) to **reject an out-of-order
release** — a tag cut from a commit older than what's already live. The guard, run
before any retag/roll:

1. reads the live commit = the sha of the latest **successful GitHub Deployment**
   for `environment` (recorded by prior promotes/deploys — so those must run with
   `environment` set too, to build the baseline);
2. compares `live...candidate` via the GitHub compare API;
3. **blocks only when the candidate is `behind`** (an ancestor of live). `ahead`,
   `identical`, and `diverged` pass — "block iff behind" gives strict latest-only on
   linear `main` while permitting a stage lineage switch.

No baseline yet (first release) ⇒ allowed. It **fails closed**: a compare API error
or unknown commit blocks the promote rather than waving it through — re-run, or set
`enforce_forward_only: false` to override. The guard reads via `github.token`
(`contents: read` + `deployments: read`, both already granted); it needs no cloud
auth.

## Concurrency

Keyed on `<gar_project>-<image_name>-<environment>` when `environment` is set — the
**same scheme as [`rollback-service`](rollback-service.md)**, so a promote and a
rollback for one environment are mutually exclusive. Falls back to the legacy
`<gar_project>-<image_name>-<target_tag>` key when `environment` is empty (unchanged
for existing callers). `cancel-in-progress: false`.
