# deploy-cloud-run

Build a container, push it to Artifact Registry (with `type=gha` layer caching),
and roll a Cloud Run service onto it. WIF auth; the WIF provider and releaser SA
are inputs.

## Two modes

| `deploy_mode` | gcloud call | When |
|---|---|---|
| `update-image` (default) | `gcloud run services update --image` | Strict image flip. Env/secrets/scale/SA/probes are owned by a **separate provision workflow**; this only changes which image is live. Safest. |
| `deploy` | `gcloud run deploy … <extra_deploy_flags>` | Create/configure the service inline. Pass `--allow-unauthenticated`, `--set-env-vars=…`, `--ingress=…` via `extra_deploy_flags`. |

App-specific pre-deploy gates (unit tests, `pyproject`/`go.mod` version
cross-checks, migration smokes) stay as their own caller jobs and gate this with
`needs:`.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `gcp_project` | input (req) | — | project owning GAR + Cloud Run |
| `gcp_region` | input | `asia-southeast1` | GAR + Cloud Run region |
| `wif_provider` | input (req) | — | WIF provider resource name (not a secret) |
| `service_account` | input (req) | — | releaser SA email (not a secret) |
| `gar_repo` | input (req) | — | Artifact Registry repo (e.g. `backend`) |
| `image_name` | input (req) | — | image name in the repo (may differ from service) |
| `service` | input (req) | — | Cloud Run service name |
| `image_tag` | input | `''` | tag to build/deploy; empty ⇒ triggering ref name |
| `require_semver` | input | `true` | reject a non-`vX.Y.Z` tag |
| `also_tag_latest` | input | `true` | also push `:latest` |
| `context` / `dockerfile` | input | `.` / `Dockerfile` | build context + Dockerfile |
| `platforms` | input | `linux/amd64` | build platform(s) |
| `build_args` | input | `''` | newline-separated docker build args |
| `deploy_mode` | input | `update-image` | see table above |
| `extra_deploy_flags` | input | `''` | flags for `deploy_mode=deploy` |
| `dry_run` | input | `false` | build only — no push, no Cloud Run mutation |

No secrets: WIF is keyless. `id-token: write` is set by the reusable.

## Outputs

`image` — the fully-qualified image reference built.
`service_url` — the Cloud Run URL after the deploy.

## Example — strict image flip (config owned by a provision workflow)

```yaml
name: Deploy
on:
  push:
    tags: ['v*.*.*']
  workflow_dispatch:
    inputs:
      tag: { description: 'Existing tag to re-deploy', required: true }

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v1.3.0
    with:
      gcp_project: realm-id
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      gar_repo: backend
      image_name: bff-api      # image path differs from the service name
      service: api
      image_tag: ${{ github.event.inputs.tag }}   # empty on tag-push ⇒ ref name
```

## Example — full deploy with inline config

```yaml
    with:
      gcp_project: auto-mahn
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      gar_repo: backend
      image_name: image-service
      service: automahn-image-service
      deploy_mode: deploy
      extra_deploy_flags: >-
        --allow-unauthenticated --ingress=all
        --set-env-vars=JWT_ISSUER=automahn,JWT_AUDIENCE=automahn-api
```

## Concurrency

Keyed on `<project>-<service>` with `cancel-in-progress: false` — a deploy is
never cancelled mid-flight by a newer run.

## Dry run

`dry_run: true` builds the image (validating the Dockerfile) but does **not**
push it or touch Cloud Run; the deploy step prints the exact `gcloud` command it
would run. Use it to preview before applying, per the repo convention that every
mutating workflow has a safe plan mode.
