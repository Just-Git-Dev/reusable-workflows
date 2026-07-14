# deploy-gke-service

Build a container, push it to Artifact Registry (gha-cached), and roll a GKE
workload onto it — via `kubectl set image` or `helm upgrade`. **This is the
Just-Git-Dev replacement for `zopsmart/workflows` stage/prod-deploy on GKE.**

Two fixes over the external system:

- **Keyless WIF** (`wif_provider` + `service_account`), no stored SA JSON key
  (retires zop-mannai's `credentials_json` and the geo-engine SA-key secrets).
- **SHA-pinned and versioned here**, instead of floating on an external
  `zopsmart/workflows@main` that mints cluster creds.

## What stays in the caller

- **Monorepo change-detection** — keep it in `on.paths` (e.g. `backend/worker/**`),
  exactly as the geo-engine callers already do. This workflow deploys one
  service; the caller decides *when* to run it.
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

## Example — kubectl (replaces zop-mannai's inline SA-JSON deploy)

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

## Example — monorepo service (replaces a geo-engine stage-deploy-*)

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

The external `zopsmart/workflows` system also did multi-registry resolution,
language auto-detection, host-side builds and a ConfigMap-diff apply. Those are
either handled elsewhere in the JGD model (`ci-go`/`ci-node` for build/test,
Secret-Manager bundles for config) or intentionally dropped. Confirm each
service's config source before cutting over, and migrate to WIF (grant the
deployer SA on the cluster) as part of the same PR.

## Concurrency

Keyed on `<cluster>-<namespace>-<svc>` with `cancel-in-progress: false`.
