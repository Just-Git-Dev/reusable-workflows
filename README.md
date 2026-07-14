# reusable-workflows

Shared **`workflow_call`** GitHub Actions for teams shipping apps on **Google
Cloud (Cloud Run + GKE) + Postgres + Cloudflare** — the CI, build/deploy, and ops
workflows every such repo would otherwise copy-paste. Host them once and a fix
lands everywhere.

- **Keyless by default.** GCP access uses [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation);
  the provider and service account are plain inputs, not stored keys.
- **No project values baked in.** Every project-specific value — GCP project,
  region, cluster, service and secret names, Cloudflare account and zone — is a
  `workflow_call` input.
- **Safe to run in production.** Third-party actions are SHA-pinned, every `run:`
  is `shell: bash` (pipefail), and destructive workflows have a `dry_run` plan mode.

## Workflows

### CI

| Workflow | Purpose |
|---|---|
| [`ci-go.yml`](docs/ci-go.md) | Go core: build · vet · test · golangci-lint, module/build caching; optional coverage gate + postgres/mysql/redis service containers |
| [`ci-node.yml`](docs/ci-node.md) | Node/React core: install · lint · test · build, setup-node caching; optional service containers |

### Build & deploy

| Workflow | Purpose |
|---|---|
| [`deploy-cloud-run.yml`](docs/deploy-cloud-run.md) | Build → push (GAR, gha-cached) → roll a **Cloud Run** service (image-flip or full deploy), keyless WIF |
| [`deploy-gke-service.yml`](docs/deploy-gke-service.md) | Build → push (GAR, gha-cached) → roll a **GKE** workload via kubectl/helm, keyless WIF |
| [`promote-image.yml`](docs/promote-image.md) | Retag an existing image (**no rebuild**) → roll GKE or Cloud Run — stage→prod promotion, keyless WIF |
| [`deploy-cluster-keyed.yml`](docs/deploy-cluster-keyed.md) | **Key-based** deploy: **multi-cloud** (GKE/EKS/AKS/kubeconfig) + **multi-registry** (GAR/ECR/ACR/GHCR/DockerHub/…) build → push → roll |

### Secrets & rotation

| Workflow | Purpose |
|---|---|
| [`sync-bundle-key.yml`](docs/sync-bundle-key.md) | Upsert key(s) into a Secret Manager bundle → roll Cloud Run → disable the old version |
| [`rotate-signing-keypair.yml`](docs/rotate-signing-keypair.md) | Rotate an RS256 (JWT) signing keypair in a bundle → roll Cloud Run → disable the old version |
| [`rotate-worker-signing-secret.yml`](docs/rotate-worker-signing-secret.md) | Rotate an HMAC secret shared by a Cloudflare Worker + Cloud Run signer, zero-downtime via a two-slot grace window |
| [`rotate-cloudflare-token.yml`](docs/rotate-cloudflare-token.md) | Verify the Cloudflare API token is active + print a rotation runbook |

### Backups, alerts & housekeeping

| Workflow | Purpose |
|---|---|
| [`neon-backup.yml`](docs/neon-backup.md) | `pg_dump` a Postgres database to a private artifact (custom or plain-gz) |
| [`cleanup-gar-images.yml`](docs/cleanup-gar-images.md) | Age-sweep Artifact Registry images, protecting digests live on Cloud Run Services **and** Jobs |
| [`bootstrap-alerts.yml`](docs/bootstrap-alerts.md) | Apply a Cloud Monitoring channel + alert policies from the caller's `infra/alerts/` |
| [`deploy-cloudflare-pages.yml`](docs/deploy-cloudflare-pages.md) | Build a static site and deploy it to Cloudflare Pages |

Each workflow has a `docs/<name>.md` page with its full input/secret contract and
copy-paste caller examples. Background on why the CI/deploy set exists (and how it
replaces the external `zopsmart/workflows`) is in
[docs/convergence-audit.md](docs/convergence-audit.md) and [DECISIONS.md](DECISIONS.md).

## Usage

Call a workflow with `uses:`, pin an exact release tag, and pass inputs. Grant
`id-token: write` for any workflow that authenticates to GCP with WIF.

```yaml
name: CI
on: [push, pull_request]

permissions:
  contents: read

jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v1.4.0
    with:
      go_version_file: go.mod
      coverage_threshold: 50
```

```yaml
name: Deploy
on:
  push:
    tags: ['v*.*.*']

permissions:
  contents: read
  id-token: write            # required for keyless WIF

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v1.4.0
    with:
      gcp_project: my-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      gar_repo: backend
      image_name: api
      service: api
```

## Versioning

**Pin an exact `vX.Y.Z` tag.** Releases are immutable — once cut, a tag is never
moved — so upgrading is a reviewed commit in *your* repo, and a fix here can never
change your production ops behind your back. **Never use `@main`.**

- `v1` is a **frozen legacy alias** left pointing at the first release; it does
  not track new releases and lacks later workflows. Don't pin new callers to it.
- Semver tracks the **input contract**: a new required input, a removed input, a
  changed default, or a behaviour change on a destructive path is a major bump.
  Read the [DECISIONS.md](DECISIONS.md) entry for a release before upgrading.

## Conventions & security

- **No secrets are committed here.** Callers pass every secret at call time. The
  repo is public because GitHub only allows *cross-organization* reuse from a
  public host — and a cross-org caller therefore **cannot use `secrets: inherit`**;
  each secret must be passed explicitly (every doc page shows the call).
- **WIF provider and service account are inputs, not secrets** — they are resource
  identifiers, not credentials, and letting callers name their own vars is handy.
  The keyless path is the default; stored keys are confined to `deploy-cluster-keyed`.
- **Callers own their trigger.** These workflows declare no `schedule` of their
  own; add the `schedule` / `workflow_dispatch` that suits you.
- **The caller repo is what gets checked out**, so files like `infra/alerts/`
  stay in the repo they describe.
- **Destructive workflows take `dry_run`** and default it to the safe value. Run
  the plan, read it, then apply.
- **Third-party actions are pinned to full commit SHAs** (version in a trailing
  comment). These workflows mint cloud credentials and dump databases, so a moved
  tag would be a supply-chain event. CI enforces this on every PR.
- **Every `run:` declares `shell: bash`.** GitHub's implicit default is `bash -e`
  — errexit on, but **`pipefail` off** — which masks a failing head-of-pipe. An
  explicit `shell: bash` runs with `-eo pipefail`.

## Contributing

`.github/workflows/ci.yml` runs `actionlint` (which includes `shellcheck` over
every `run:` body) and a check that every third-party action is SHA-pinned. Run
`actionlint` locally before pushing.

Changes here run in other people's production. Open a pull request, and record
the reasoning in [DECISIONS.md](DECISIONS.md).

## License

[MIT](LICENSE).
