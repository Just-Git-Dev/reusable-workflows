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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v4.1.0
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
| `provenance` | input | `mode=min` | `docker/build-push-action` `provenance:` value — reproduces buildx's own default (unsigned attestation manifest alongside the image), stated here so it survives an action bump instead of drifting silently |
| `sbom` | input | `false` | `docker/build-push-action` `sbom:` value — reproduces buildx's own default (no SBOM emitted) |
| `deploy_mode` | input | `update-image` | see table above |
| `deploy_flags` | input | `''` | flags for `deploy_mode=deploy`, **one per line** — spaces within a line are preserved (safe for values containing spaces or commas). Prefer this |
| `extra_deploy_flags` | input | `''` | legacy: flags as one space-separated string — word-split, so a space inside any value breaks argv. Prefer `deploy_flags` |
| `image` | input | `''` | deploy a **prebuilt** image instead of building: digest reference only (`…@sha256:<64 hex>`), a tag is refused. See [Deploy a prebuilt image](#deploy-a-prebuilt-image-image-v410) |
| `build_only` | input | `false` | build **and push**, then stop — no Cloud Run mutation, no Deployment record. See below |
| `dry_run` | input | `false` | build only — **no push**, no Cloud Run mutation |
| `env_file`, `generated_env`, `env_secret`, `env_mount_path`, `pin_env`, `manifest_retention_days` | input | see [Runtime config (v4)](#runtime-config-v4) | env file, bundle pin, labels and manifest |

No secrets: WIF is keyless. `id-token: write` is set by the reusable.

## Outputs

`image` — the fully-qualified image reference built (the input digest reference when the `image` input is set). Set for `build_only` runs too — it is the whole point of them.
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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v4.1.0
    with:
      gcp_project: <consumer-C-project-id>
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      gar_repo: backend
      image_name: gateway      # image path differs from the service name
      service: gateway-prod
      image_tag: ${{ github.event.inputs.tag }}   # empty on tag-push ⇒ ref name
```

## Example — full deploy with inline config

Use `deploy_flags` (one flag per line). Spaces within a line are preserved, so a
value with a space or comma is safe:

```yaml
    with:
      gcp_project: <consumer-B-project-id>
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      gar_repo: backend
      image_name: image-service
      service: <service>-image-service
      deploy_mode: deploy
      deploy_flags: |
        --allow-unauthenticated
        --ingress=all
        --set-env-vars=JWT_ISSUER=<issuer>,JWT_AUDIENCE=<service>-api
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
      gcp_project: <consumer-B-project-id>
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      gar_repo: backend
      image_name: image-service
      service: <service>-image-service
      image_tag: '0.1.8'                    # image gets :0.1.8
      checkout_ref: ${{ github.ref_name }}  # but build this git ref (e.g. v0.1.8)
      require_semver: false                 # 0.1.8 is not vX.Y.Z
```

## Deploy a prebuilt image (`image`, v4.1.0)

`image: <region>-docker.pkg.dev/<project>/<repo>/<name>@sha256:<64 hex>` deploys an image that
something else already built and pushed (for example the one a caller's gate just tested), and keeps
the **full** deploy path: checkout, env render, bundle pin, `jgd_commit` / env labels, the Deployment
record, the config manifest and the summary all run as for a built image. Only the build is skipped.
Default `''` is the build-and-push flow above, unchanged. The reference needs all three path
segments (`<project>/<repo>/<name>`, the name may contain more `/`); `name:tag@sha256:...` is
refused, since only a bare digest is a reference that cannot move.

**Digest only.** A tag reference (`…:v1.2.3`) is refused with an error naming `image`. A tag can be
moved between the moment a gate tests an image and the moment this deploy runs; a digest cannot, so
the bytes deployed are provably the bytes tested.

What the run does when `image` is set:

- `Resolve tag + image ref` validates the digest shape, then outputs `image` = the input. The tag
  (`image_tag` or the triggering ref) is still resolved: it drives the checkout, the Deployment
  record and `require_semver`.
- `Configure docker`, `setup-buildx` and `Build & push image` are skipped.
- `Verify prebuilt image` runs `gcloud artifacts docker images describe` on the reference and fails
  the run if that digest is not in Artifact Registry (the releaser SA already reads GAR). The digest
  it reports goes into the config manifest's `image_digest`.
- `image` + `build_only: true` is refused (nothing to build, nothing to stop after).
- Build-only inputs are ignored (nothing is built or pushed). A `::notice::` lists which of
  `also_tag_latest`, `docker_target` and `build_args` were set; `context`, `dockerfile` and
  `platforms` have defaults, so they are ignored silently.

**The checkout is not compared with the image.** The workflow does not check that the image's OCI
revision label equals the checked-out commit (images from other build systems may carry no label).
The caller passes the same tag as `image_tag` and as the one the image was built from, so the commit
stamped on the service is the commit the image came from.

### `deploy-cloud-run` vs `promote-image` — which to use

| | `deploy-cloud-run` with `image` | `promote-image` |
|---|---|---|
| Deploys a digest | yes (digest only) | yes |
| Env file render, bundle pin | yes | no |
| `jgd_commit` / env labels, forward-only guard | yes | no |
| Config manifest artifact | yes | no |
| Retags the image | no | yes (server-side) |
| Pick it when | the service has runtime config (v4) or you need the manifest / live-commit marker | you only need to retag and flip the image |

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

## Runtime config (v4)

From v4 the deploy carries the service's non-secret configuration and keeps the bundle secret
pinned. Four things are involved: a committed env file (plain config), the bundle secret
`<d>-env` (secret values, mounted as a file), the revision labels, and a manifest. See
[runtime-config](runtime-config.md) for the model and [MIGRATION-v4](MIGRATION-v4.md) for what a
v3 caller must change.

| Input | Default | Notes |
|---|---|---|
| `env_file` | `''` | path, in the checkout, of the YAML env file (e.g. `deploy/env.stage.yaml`). Empty = v3 behaviour, no env file |
| `generated_env` | `''` | newline `KEY=VALUE` pairs the workflow produces (e.g. `APP_VERSION`), merged into the file |
| `env_secret` | `''` | the bundle secret name, `<d>-env` |
| `env_mount_path` | — | path where the service mounts the bundle |
| `pin_env` | `true` | see [Pinning the bundle](#pinning-the-bundle) |
| `manifest_retention_days` | `400` | retention of the `config-manifest.json` artifact |

### Render

A pure step merges `env_file` and `generated_env` into `$RUNNER_TEMP/env.rendered.yaml`. It
**refuses**: a key present in both inputs, and any key whose name matches `PASSWORD`, `SECRET`,
`TOKEN` or ends in `_URL` (secrets belong in the bundle, never in the plain file; this repeats the
[deploy-env-lint](deploy-env-lint.md) rule as defence in depth). `jgd_env_sha` is the first 8
hex characters of the sha256 of the rendered file.

### Deploy step

The deploy keeps the existing `gcloud run` step and passes the rendered file with
`--env-vars-file=<rendered>`. Both `deploy_mode`s accept it. There is no converter and the deploy
does not move to another action (owner ruling: the env file is deployed with `--env-vars-file`).
The file is the complete set of plain environment variables for the new revision; a variable not
in the file is not set by this deploy.

### Pinning the bundle

The bundle is mounted at a **version number**, not `latest`, so a revision always starts with the
secret version it was deployed with. The pin step reads the service's currently mounted
`env_secret` version:

- `latest` (a v3 service): resolve the newest ENABLED version number `N` and pass
  `--update-secrets=<mount>=<env_secret>:<N>`;
- a number: **keep it**. A deploy never moves the pin; only the bundle writers
  ([sync-bundle-key](sync-bundle-key.md) and the two rotators) do.

The same pin step runs when `env_secret` is empty and then only refuses: the deploy fails when the
live template mounts a `*-env` secret at `:latest` (as a volume item or an env `secretKeyRef`), or
when `deploy_flags` / `extra_deploy_flags` mount one at `:latest` in a `--set/--update/--add-secrets`
list, unless `pin_env: false`. Only the secret ref of a secrets flag counts; `-env:latest` inside
some other flag's value does not. A service that does not exist yet passes; any other `describe`
error refuses.

**Ruling (owner, 2026-10-21): `pin_env: false` ships.** `pin_env` defaults to `true`; setting it
to `false` is an opt-out for a service with no `*-env` bundle yet, and every run that uses it
prints a warning in its summary. It exists so a caller can adopt v4 service by service.

### Labels

Each revision gets `jgd_commit` (already stamped today, see below), `jgd_env_version` (the pinned
`N`), `jgd_env_sha` (the rendered file's hash) and `jgd_run` (the workflow run). From a revision
you can therefore read back the commit, the bundle version and the env file it started with.

### Manifest

The deploy writes `config-manifest.json`: the commit, the image digest, the revision, the
`env_secret` version `N`, and the keys with their source (file, generated or bundle) and, for
non-secret keys, their value. It is shown as a table in the run summary and uploaded as an
artifact for `manifest_retention_days`. Secret values never appear. The repository's own maximum
artifact retention must be at least that many days, or the upload is capped by it; raising it is a
repository setting.

### Forward-only fallback

The [forward-only](#live-commit-stamping) guard reads "what is live" from the environment's latest
successful GitHub Deployment. When the environment has **no** successful Deployment (for example
after renaming `production` to `prod`, a new environment name), v3 allowed any deploy. v4 instead
reads the service's `jgd_commit` label as the baseline and compares against it. If neither exists
(the first deploy ever) the deploy is allowed, with a notice. A failed `describe` of the service
(403, a transient error) is not "no label": the guard fails closed and refuses; only a successful
describe with no label, or a service that does not exist yet, means "no baseline".

### Why the deploy job has no `environment:`

Deploy jobs deliberately declare no job-level `environment:`. They need no environment secrets
(WIF is keyless; the bundle is pinned in Secret Manager), and an environment restricted to
`main` is expected to reject a tag-triggered job (unverified at the time of writing). The
`environment` **input** keeps its meaning: the name of the GitHub Deployment record and the
forward-only lineage.

## Concurrency

Keyed on `<project>-<service>` with `cancel-in-progress: false` — a deploy is
never cancelled mid-flight by a newer run.

## Dry run

`dry_run: true` builds the image (validating the Dockerfile) but does **not**
push it or touch Cloud Run; the deploy step prints the exact `gcloud` command it
would run. Use it to preview before applying, per the repo convention that every
mutating workflow has a safe plan mode.
