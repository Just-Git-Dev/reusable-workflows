# deploy-cloud-run

Build a container, push it to Artifact Registry (with `type=gha` layer caching),
and roll a Cloud Run service onto it. WIF auth; the WIF provider and releaser SA
are inputs.

## Two modes

| `deploy_mode` | gcloud call | When |
|---|---|---|
| `update-image` (default) | `gcloud run services update --image` | Strict image flip. Env/secrets/scale/SA/probes are owned by a **separate provision workflow**; this only changes which image is live. Safest. |
| `deploy` | `gcloud run deploy … <deploy_flags>` | Create/configure the service inline. Pass `--allow-unauthenticated`, `--set-env-vars=…`, `--ingress=…` via `deploy_flags` (one per line). |

App-specific pre-deploy gates (unit tests, `pyproject`/`go.mod` version
cross-checks, migration smokes) stay as their own caller jobs and gate this with
`needs:`.

## `build_only` — build-once, promote-to-prod

`build_only: true` builds and pushes the image, then **stops**: no
`gcloud run` call, no GitHub Deployment record, no forward-only guard (there is
no environment lineage to protect). It mirrors `promote-image.yml`'s
`deploy_target: none`, so the two reusables are symmetric halves of one flow.

The problem it solves: with a single tag-triggered `deploy.yml`, the artifact
that ships to production is **built at release time, from source, and has never
run anywhere**. Re-running the release, or re-cutting the tag, produces different
bytes than whatever was reviewed — base-image drift, dependency resolution,
`GOPROXY=direct` fallbacks. Build-once moves the build earlier:

```
push → main        deploy-cloud-run  build_only: true   → pushes image:<commit-sha>
                   caller's own jobs validate THAT image (migrations, smoke)
push → tag vX.Y.Z  promote-image     source_tag: <sha>  → server-side retag to :vX.Y.Z
                                     deploy_target: cloud-run → rolls prod
```

Production then runs bytes that were built and validated *before* the release was
cut. Nothing is rebuilt at release time.

```yaml
on:
  push:
    branches: [main]

jobs:
  build:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v2.3.0
    with:
      build_only: true
      image_tag: ${{ github.sha }}   # the promotion source
      require_semver: false          # a commit sha is not vX.Y.Z
      also_tag_latest: false         # :latest should track releases, not main
      gcp_project: my-project
      gar_repo: backend
      image_name: api
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
```

Two things this depends on, both worth confirming per repo before converting:

- **Config must be runtime-resolved**, not baked at build time (`APP_ENV=prod` as
  a `--set-env-vars`, not a build arg). That is what makes one image legitimately
  serve two environments.
- **GAR retention must not delete `:<sha>` before the release retags it.**
  `cleanup-gar-images` protects these via its
  [sha retention window](cleanup-gar-images.md#sha-retention-build-once-promote-to-prod),
  on by default. If you sweep GAR some other way, teach it the same rule first —
  otherwise a slow release cycle silently destroys the promotion source.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `gcp_project` | input (req) | — | project owning GAR + Cloud Run |
| `gcp_region` | input | `asia-southeast1` | GAR + Cloud Run region |
| `wif_provider` | input (req) | — | WIF provider resource name (not a secret) |
| `service_account` | input (req) | — | releaser SA email (not a secret) |
| `gar_repo` | input (req) | — | Artifact Registry repo (e.g. `backend`) |
| `image_name` | input (req) | — | image name in the repo (may differ from service) |
| `service` | input | `''` | Cloud Run service name. **Required unless `build_only: true`** |
| `image_tag` | input | `''` | tag to build/deploy; empty ⇒ triggering ref name |
| `checkout_ref` | input | `''` | git ref to build from; empty ⇒ the resolved image tag. Set it when the image tag isn't a git ref (e.g. app-version `0.1.8` vs git tag `v0.1.8`) |
| `require_semver` | input | `true` | reject a non-`vX.Y.Z` tag |
| `also_tag_latest` | input | `true` | also push `:latest` |
| `context` / `dockerfile` | input | `.` / `Dockerfile` | build context + Dockerfile |
| `docker_target` | input | `''` | multi-stage build stage (`docker build --target`); empty ⇒ last stage. For a Dockerfile with several leaves — e.g. a hermetic self-compiling stage for local work plus a slimmer CI stage |
| `platforms` | input | `linux/amd64` | build platform(s) |
| `build_args` | input | `''` | newline-separated docker build args |
| `deploy_mode` | input | `update-image` | see table above |
| `deploy_flags` | input | `''` | flags for `deploy_mode=deploy`, **one per line** — spaces within a line are preserved (safe for values containing spaces or commas). Prefer this |
| `extra_deploy_flags` | input | `''` | legacy: flags as one space-separated string — word-split, so a space inside any value breaks argv. Prefer `deploy_flags` |
| `build_only` | input | `false` | build **and push**, then stop — no Cloud Run mutation, no Deployment record. See below |
| `dry_run` | input | `false` | build only — **no push**, no Cloud Run mutation |

No secrets: WIF is keyless. `id-token: write` is set by the reusable.

## Outputs

`image` — the fully-qualified image reference built. Set for `build_only` runs too — it is the whole point of them.
`service_url` — the Cloud Run URL after the deploy. Empty for `build_only` / `dry_run`.

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v2.3.0
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

Use `deploy_flags` (one flag per line). Spaces within a line are preserved, so a
value with a space or comma is safe:

```yaml
    with:
      gcp_project: auto-mahn
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      gar_repo: backend
      image_name: image-service
      service: automahn-image-service
      deploy_mode: deploy
      deploy_flags: |
        --allow-unauthenticated
        --ingress=all
        --set-env-vars=JWT_ISSUER=automahn,JWT_AUDIENCE=automahn-api
        --set-env-vars=^@^CORS_ORIGINS=https://a.example, https://b.example
```

> The old `extra_deploy_flags` (single space-separated string) still works but
> word-splits — a space inside any value breaks argv. Migrate to `deploy_flags`.

## Example — decoupled image tag (app version ≠ git tag)

When the image should carry an app version (`0.1.8`) that differs from the pushed
git tag (`v0.1.8`), set `checkout_ref` so the build checks out the git ref while
the image is tagged independently:

```yaml
    with:
      gcp_project: auto-mahn
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      gar_repo: backend
      image_name: image-service
      service: automahn-image-service
      image_tag: '0.1.8'                    # image gets :0.1.8
      checkout_ref: ${{ github.ref_name }}  # but build this git ref (e.g. v0.1.8)
      require_semver: false                 # 0.1.8 is not vX.Y.Z
```

## Live-commit stamping

Every deploy stamps the built commit onto the service as a Cloud Run resource label
`jgd_commit=<sha>`, so the [forward-only](release-process.md) check can read back
"what is live" for this environment. Additionally, set `environment` (e.g.
`staging`) to also record a **GitHub Deployment** on that commit — the git-native
half of the record (best-effort; needs `deployments: write`, opt out with
`record_github_deployment: false`). Existing callers that set no `environment` are
unaffected — only the label is added.

Set `enforce_forward_only: true` (with `environment`) to **reject an out-of-order
deploy** — a commit older than what's already live in this environment. The guard
runs *before the build* (so a blocked deploy wastes no build), reads the live commit
from the env's latest successful GitHub Deployment, and blocks only when the
candidate is `behind` (`ahead`/`identical`/`diverged` pass, so a stage lineage switch
is allowed). It fails closed on a compare-API error. Same guard as
[`promote-image`](promote-image.md#forward-only-opt-in).

## Concurrency

Keyed on `<project>-<service>` with `cancel-in-progress: false` — a deploy is
never cancelled mid-flight by a newer run.

## Dry run

`dry_run: true` builds the image (validating the Dockerfile) but does **not**
push it or touch Cloud Run; the deploy step prints the exact `gcloud` command it
would run. Use it to preview before applying, per the repo convention that every
mutating workflow has a safe plan mode.
