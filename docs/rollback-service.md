# rollback-service

Roll a running service **back** onto an **already-built, previously-shipped** image
(by tag or digest) — **no rebuild, no retag**. The out-of-band "stop the bleeding"
bridge from [release-process.md](release-process.md).

It is deliberately **separate from `promote-image`**. The promote flow is
forward-only and immutable-tag driven; a fast rollback is a temporary *backward*
artifact move, so mixing the two would corrupt that invariant. This workflow only
buys time — **the permanent fix is always `git revert` + a new linear tag through
`promote-image`.**

## When to use it

- **Incident response.** Prod (or stage) is serving a bad release; get a prior
  prod-proven image live in seconds while you prepare the real fix.
- Roll a service to any image already in Artifact Registry, by `vX.Y.Z` tag or by
  immutable `sha256:` digest (digest is the safest target).

For the forward promotion path, use [`promote-image`](promote-image.md).

## No pin / freeze — by design

This stack is **push-based**: Cloud Run and GKE hold the image they were rolled onto
— no reconciler (Argo/Flux) re-derives "latest tag", so nothing autonomously undoes
a rollback. The only re-clobber risk is a human *manually re-promoting the bad tag*
mid-incident; if that ever needs guarding, quarantine the specific bad artifact in
`promote-image` (see `TODO.md`) rather than freezing all promotion. So this workflow
sets **no pin**, and there is no unpin lifecycle to manage.

## Caller owns the trigger

Like every reusable here, this declares only `workflow_call`. Wire it to a manual
`workflow_dispatch` (the usual choice — a human decides to roll back):

```yaml
name: Rollback prod
on:
  workflow_dispatch:
    inputs:
      rollback_tag:    { description: 'prior vX.Y.Z to roll to', required: false }
      rollback_digest: { description: 'or a sha256: digest',      required: false }
      commit_sha:      { description: 'source commit of that image', required: false }
      reason:          { description: 'incident ref',              required: false }
```

## Inputs

| Name | Default | Notes |
|---|---|---|
| `gcp_region` | (req) | GAR host region + Cloud Run region default |
| `image_registry` | `''` | full GAR host; empty ⇒ `<gcp_region>-docker.pkg.dev` |
| `gar_project` / `gar_repo` / `image_name` | (req) | image path; `image_name` may contain slashes |
| `rollback_tag` | `''` | tag to roll back TO — **exactly one** of tag/digest |
| `rollback_digest` | `''` | `sha256:…` to roll back TO (immutable, safest) — **exactly one** of tag/digest |
| `commit_sha` | `''` | source commit of the rolled-to image; stamped + recorded so forward-only stays accurate. Strongly recommended; empty ⇒ no stamp/record |
| `reason` | `''` | incident ref, shown in summary + Deployment |
| `environment` | `production` | GitHub Deployment environment name |
| `record_github_deployment` | `true` | record a Deployment (+success) as the env's live-commit marker; needs `deployments: write` + a `commit_sha` |
| `deploy_target` | (req) | `gke` \| `cloud-run` — no `none`, a rollback must roll |
| `wif_provider` / `service_account` | `''` | keyless WIF; empty `wif_provider` ⇒ key-based auth |
| `cluster_project` / `cluster_name` / `cluster_location` | — | GKE target |
| `namespace` / `svc_name` | — | GKE workload + container name |
| `workload_type` / `deploy_method` | `deployment` / `kubectl` | `deployment`\|`cron`; `kubectl`\|`helm` |
| `helm_chart` / `helm_release` / `helm_values_path` / `helm_extra_args` | — | helm only |
| `app_version` | `''` | kubectl/deployment: `set env APP_VERSION=…` after the roll |
| `run_project` / `run_region` / `run_service` | `gar_project` / `gcp_region` / — | Cloud Run target |
| `dry_run` | `false` | print the roll commands without executing |

## Auth

Identical to `promote-image`: set `wif_provider` + `service_account` for keyless WIF,
or leave `wif_provider` empty for key-based auth.

| Secret | Format | When required |
|---|---|---|
| `registry_credentials` | GCP SA-key JSON | key-based: authenticates `container images describe` (the image-exists check) |
| `cluster_credentials` | GCP SA-key JSON | key-based: authenticates the GKE/Cloud Run roll (may equal `registry_credentials`) |

## Live-commit stamping

On the roll, when `commit_sha` is set, the source commit is stamped onto the service
so forward-only (in `promote-image`) can read back "what is live" after the rollback:

- **Cloud Run** — a resource label `jgd_commit=<sha>` (label keys are slash-free).
- **GKE** — an annotation `jgd.dev/commit=<sha>` on the workload.
- **GitHub Deployment** — a `success` deployment on `<commit_sha>` for `environment`
  (the second, git-native record; disable with `record_github_deployment: false`).

Without `commit_sha` the roll still happens, but nothing is stamped/recorded — so the
next forward-only check has no accurate "live" baseline. Pass it whenever you can.

## Example — roll a Cloud Run prod service back to a prior digest

```yaml
name: Rollback prod
on:
  workflow_dispatch:
    inputs:
      rollback_digest: { required: true }
      commit_sha:      { required: true }
      reason:          { required: false }

permissions:
  contents: read
  id-token: write
  deployments: write

jobs:
  rollback:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rollback-service.yml@v1.8.0
    with:
      gcp_region: asia-southeast1
      gar_project: realm-id
      gar_repo: backend
      image_name: bff-api
      rollback_digest: ${{ github.event.inputs.rollback_digest }}
      commit_sha: ${{ github.event.inputs.commit_sha }}
      reason: ${{ github.event.inputs.reason }}
      environment: production
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      deploy_target: cloud-run
      run_service: api
```

## Example — key-based GKE rollback to a prior tag

```yaml
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rollback-service.yml@v1.8.0
    with:
      gcp_region: ${{ vars.CLUSTER_REGION }}
      image_registry: ${{ vars.IMAGE_REGISTRY }}
      gar_project: ${{ vars.REGISTRY_PROJECT }}
      gar_repo: ${{ vars.REGISTRY_REPO }}
      image_name: api
      rollback_tag: v1.2.1
      commit_sha: ${{ github.event.inputs.commit_sha }}
      deploy_target: gke
      cluster_project: ${{ vars.CLUSTER_PROJECT }}
      cluster_name: ${{ vars.CLUSTER_NAME }}
      cluster_location: ${{ vars.CLUSTER_REGION }}
      namespace: ${{ vars.PROD_NAMESPACE }}
      svc_name: api
      app_version: v1.2.1
    secrets:
      registry_credentials: ${{ secrets.PROD_DEPLOY_KEY }}
      cluster_credentials: ${{ secrets.PROD_DEPLOY_KEY }}
```

## Dry run

`dry_run: true` prints the exact roll command without executing it and skips the
Deployment record — the roll is a mutation, honouring the repo convention that every
mutating workflow has a safe plan mode.

## Concurrency

Keyed on `deploy-<gar_project>-<image_name>-<environment>` with
`cancel-in-progress: false` — serialized against other rollbacks (and, once it
adopts the same key, normal promotion) for the same target so the last write wins.
