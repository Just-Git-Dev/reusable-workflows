# deploy-gke-service

Build a container, push it to Artifact Registry (gha-cached), and roll a GKE
workload onto it — via `kubectl set image` or `helm upgrade`. **This is the
Just-Git-Dev replacement for `zopsmart/workflows` stage/prod-deploy on GKE.**

Two fixes over the external system:

- **Keyless WIF** (`wif_provider` + `service_account`), no stored SA JSON key.
  (Callers still on an SA-JSON key can bridge via
  [`deploy-cluster-keyed`](deploy-cluster-keyed.md) until the deployer SA is
  federated.)
- **SHA-pinned and versioned here**, instead of floating on an external
  `zopsmart/workflows@main` that mints cluster creds.

## What stays in the caller

- **Monorepo change-detection** — keep it in `on.paths` (e.g. `backend/worker/**`).
  This workflow deploys one service; the caller decides *when* to run it.
- **Pre-deploy tests / preflight gates** — separate caller jobs gating via `needs:`.

## Inputs (no secrets — WIF is keyless)

| Name | Default | Notes |
|---|---|---|
| `gcp_region` | (req) | Artifact Registry host region |
| `gar_project` | `cluster_project` | project owning the GAR repo |
| `gar_repo` / `image_name` | (req) | `image_name` may contain slashes (e.g. `staging/api`) |
| `image_tag` | `''` | empty ⇒ commit SHA |
| `wif_provider` / `service_account` | (req) | keyless WIF |
| `cluster_project` / `cluster_name` / `cluster_location` | (req) | GKE target |
| `namespace` | (req) | k8s namespace |
| `svc_name` | (req) | workload **and** container name (`kubectl set image svc=image`) |
| `workload_type` | `deployment` | `deployment` \| `cron` |
| `deploy_method` | `kubectl` | `kubectl` \| `helm` |
| `context` / `dockerfile` / `platforms` / `build_args` | `.` / `Dockerfile` / `linux/amd64` / `''` | build |
| `helm_chart` / `helm_release` / `helm_values_path` / `helm_extra_args` | — / `svc_name` / — / — | helm only |
| `app_version` | `''` | kubectl/deployment: `set env APP_VERSION=…` after the roll |
| `dry_run` | `false` | build only, no push, `--dry-run` on kubectl/helm |

## Example — kubectl (single-service GKE deploy)

```yaml
name: Deploy api
on:
  push:
    branches: [development]

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-gke-service.yml@v1.3.0
    with:
      gcp_region: asia-south1
      gar_project: zs-products
      gar_repo: zop-dev
      image_name: customs-staging/api
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GKE_DEPLOYER_SA }}
      cluster_project: zs-products
      cluster_name: internal-products
      cluster_location: asia-south1
      namespace: customs-staging
      svc_name: api
      build_args: |
        JAR_FILE=build/libs/app.jar
```

## Example — monorepo service (path-filtered in the caller)

```yaml
on:
  push:
    branches: [main, development]
    paths:
      - "backend/worker/**"
      - ".github/workflows/deploy-worker.yaml"

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-gke-service.yml@v1.3.0
    with:
      gcp_region: asia-southeast1
      gar_repo: backend
      image_name: worker
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GKE_DEPLOYER_SA }}
      cluster_project: revvup
      cluster_name: geo-engine
      cluster_location: asia-southeast1
      namespace: staging
      svc_name: worker
      context: backend/worker
```

## Migration note

The external `zopsmart/workflows` system also does a few things this workflow
does not. Verified against its live callers (`zopsmart/*`, `quizzing-pro/*`),
here is where each lands in the JGD model:

| zopsmart capability | JGD home |
|---|---|
| Stage→prod **retag/promote** (no rebuild) | [`promote-image`](promote-image.md) |
| **Multi-registry** (ecr/acr/ghcr/…) + **multi-cloud** key-based deploy | [`deploy-cluster-keyed`](deploy-cluster-keyed.md) |
| Language auto-detect | dropped — use explicit `ci-go`/`ci-node` |
| Env-file → **ConfigMap** (change-routed, applied with `kubectl apply --force` — *not* a semantic diff) + config-only updates | Secret-Manager bundles (`sync-bundle-key`); see the GKE config note below |

Confirm each service's config source before cutting over, and migrate to WIF
(grant the deployer SA on the cluster) as part of the same PR.

**GKE config on Secret-Manager bundles.** Unlike Cloud Run (`--set-secrets`),
GKE has no native secret-mount, so a bundle needs a mechanism in-cluster
(External Secrets Operator, or an initContainer that pulls the secret). Plan
that per service; it does not need a new reusable.

## Live-commit stamping

The kubectl path stamps the built commit onto the workload as an annotation
`jgd.dev/commit=<sha>`, so the [forward-only](release-process.md) check can read
back "what is live". Set `environment` (e.g. `staging`) to also record a **GitHub
Deployment** on that commit (best-effort; needs `deployments: write`, opt out with
`record_github_deployment: false`). Helm-managed workloads get the Deployment record
but not the annotation (bake a `jgd.dev/commit` label into the chart if you need it
on the resource). Callers that set no `environment` are unaffected.

Set `enforce_forward_only: true` (with `environment`) to **reject an out-of-order
deploy** — a commit older than what's already live. The guard runs *before the
build*, reads the live commit from the env's latest successful GitHub Deployment, and
blocks only when the candidate is `behind` (`ahead`/`identical`/`diverged` pass, so a
stage lineage switch is allowed); it fails closed on a compare-API error. Same guard
as [`promote-image`](promote-image.md#forward-only-opt-in).

## Concurrency

Keyed on `<cluster>-<namespace>-<svc>` with `cancel-in-progress: false`.
