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

> **Wiring up a repo (or an agent doing it)? Start with [AGENTS.md](AGENTS.md)** — how to
> pick a workflow, the caller shape, the traps that cost real debugging time, and what to
> check before upgrading a pin. The authoritative input contract for every workflow is
> [`catalog.json`](catalog.json), generated from the shipped YAML and verified in CI.
>
> **New here? Read the [platform handbook](docs/PLATFORM.md)** — the connected guide to
> using these workflows end-to-end: the access your repo is granted, an "I want to… → use
> this" index, the full lifecycle (CI → deploy → promote → operate → rollback), and a
> copy-paste app-repo example. The catalog below is the quick reference.

## Workflows

### CI

| Workflow | Purpose |
|---|---|
| [`ci-go.yml`](docs/ci-go.md) | Go core: build · vet · test · golangci-lint, module/build caching; optional coverage gate + postgres/mysql/redis service containers + self-updating README badges (coverage / nolint count) |
| [`ci-node.yml`](docs/ci-node.md) | Node/React core: install · lint · test · build, setup-node caching; optional service containers + coverage gate + self-updating README badges (coverage / eslint-disable count) |

### Build & deploy

| Workflow | Purpose |
|---|---|
| [`deploy-cloud-run.yml`](docs/deploy-cloud-run.md) | Build → push (GAR, gha-cached) → roll a **Cloud Run** service (image-flip or full deploy), keyless WIF |
| [`deploy-gke-service.yml`](docs/deploy-gke-service.md) | Build → push (GAR, gha-cached) → roll a **GKE** workload via kubectl/helm, keyless WIF |
| [`promote-image.yml`](docs/promote-image.md) | Retag an existing image (**no rebuild**) → roll GKE or Cloud Run — stage→prod promotion, keyless WIF |
| [`rollback-service.yml`](docs/rollback-service.md) | Roll a service **back** onto a prior image (by tag/digest, **no rebuild/retag**) — out-of-band incident bridge, stamps the live commit |
| [`deploy-cluster-keyed.yml`](docs/deploy-cluster-keyed.md) | **Key-based** deploy: **multi-cloud** (GKE/EKS/AKS/kubeconfig) + **multi-registry** (GAR/ECR/ACR/GHCR/DockerHub/…) build → push → roll |
| [`run-db-job.yml`](docs/run-db-job.md) | Converge a **Cloud Run Job** from an already-built image → execute + wait — schema migrations that gate a service roll, backfills, one-shot tasks |

### Secrets & rotation

| Workflow | Purpose |
|---|---|
| [`manage-config-secrets.yml`](docs/manage-config-secrets.md) | Manage a **GKE** service's config **values**: dotenv → ConfigMap (keyvalue / react-`window.env`) + secrets into a backend (`k8s` / `gsm` blob or per-key). Values only — no deploy, no pod wiring |
| [`sync-bundle-key.yml`](docs/sync-bundle-key.md) | Upsert key(s) into a Secret Manager bundle → roll Cloud Run → disable the old version |
| [`rotate-signing-keypair.yml`](docs/rotate-signing-keypair.md) | Rotate an RS256 (JWT) signing keypair in a bundle → roll Cloud Run → disable the old version |
| [`rotate-worker-signing-secret.yml`](docs/rotate-worker-signing-secret.md) | Rotate an HMAC secret shared by a Cloudflare Worker + Cloud Run signer, zero-downtime via a two-slot grace window |
| [`rotate-cloudflare-token.yml`](docs/rotate-cloudflare-token.md) | Verify the Cloudflare API token is active + print a rotation runbook |

### Backups, alerts & housekeeping

| Workflow | Purpose |
|---|---|
| [`neon-backup.yml`](docs/neon-backup.md) | `pg_dump` a Postgres database to a private artifact (custom or plain-gz) |
| [`cleanup-gar-images.yml`](docs/cleanup-gar-images.md) | Age-sweep Artifact Registry images, protecting digests live on Cloud Run Services **and** Jobs |
| [`cleanup-secret-versions.yml`](docs/cleanup-secret-versions.md) | Quarantine-sweep Secret Manager versions (`ENABLED`→`DISABLED`→`DESTROYED`), never touching what `latest` resolves to |
| [`retire-gar-packages.yml`](docs/retire-gar-packages.md) | Delete **entire** Artifact Registry packages for retired services, refusing any package with a live reference |
| [`bootstrap-alerts.yml`](docs/bootstrap-alerts.md) | Apply a Cloud Monitoring channel + alert policies from the caller's `infra/alerts/` |
| [`validate-alerts.yml`](docs/validate-alerts.md) | **PR-time preflight** for those policy files — offline structural lint, plus real MQL execution when given a project (the Monitoring API has no `validateOnly`) |
| [`bootstrap-dashboards.yml`](docs/bootstrap-dashboards.md) | Apply Cloud Monitoring **dashboards** from the caller's `infra/dashboards/`; updates in place so dashboard ids and bookmarks survive |
| [`cleanup-cloud-run-revisions.yml`](docs/cleanup-cloud-run-revisions.md) | Prune inactive Cloud Run revisions, releasing the GAR digests they pin — schedule **before** `cleanup-gar-images` |
| [`deploy-cloudflare-pages.yml`](docs/deploy-cloudflare-pages.md) | Build a static site and deploy it to Cloudflare Pages |
| [`deploy-cloudflare-worker.yml`](docs/deploy-cloudflare-worker.md) | Deploy a Cloudflare Worker with `wrangler deploy`, with an optional change-skip and smoke check |
| [`cloud-run-update.yml`](docs/cloud-run-update.md) | Apply config to an existing Cloud Run service — identity, sizing, scaling, env, secrets — with a health gate; never deploys an image |
| [`bootstrap-cf-dns.yml`](docs/bootstrap-cf-dns.md) | Converge a Cloudflare zone's DNS records and Origin Rules, preserving rules other writers own |
| [`bootstrap-cf-service.yml`](docs/bootstrap-cf-service.md) | Give a Cloud Run service a public hostname — Cloud Run domain mapping + DNS-only CNAME, or a proxied CNAME + Origin Rule host override |

Each workflow has a `docs/<name>.md` page with its full input/secret contract and
copy-paste caller examples. The **release model** these deploy/promote workflows
serve — trunk-based, build-once, promote-by-retag, forward-only, and how rollback is
fenced out-of-band — is in [docs/release-process.md](docs/release-process.md).
Background on why the CI/deploy set exists (and how it replaces the external
`zopsmart/workflows`) is in [docs/convergence-audit.md](docs/convergence-audit.md)
and [DECISIONS.md](DECISIONS.md).

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v2.4.1
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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v2.4.1
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
- **Let [Dependabot](AGENTS.md#then-let-dependabot-hold-it-for-you) keep the pin
  current** — it has updated reusable-workflow refs since March 2023. This repo is
  public and most callers are private, so nobody here can see that you are behind;
  a weekly Dependabot PR is the only thing that reliably will.

### Cutting a release

The version appears in two places that used to be swept by hand — the `@vX.Y.Z`
pins in every doc example, and the `WORKFLOW_VERSION` stamp in each workflow's
`env:` (a called workflow cannot discover its own ref at runtime, so the version
has to be baked in). One script does both, **in the PR that precedes the tag**:

```bash
python3 scripts/stamp_version.py v1.2.3    # the tag you are about to cut
python3 scripts/stamp_version.py --check   # what CI asserts on every PR
```

Merge that, then tag it. CI re-runs on the tag with `--expect`, and fails
the release if the tree is stamped with anything else — so a skipped sweep is
caught at the one moment it matters, while ordinary PRs are never failed just
because a release happened elsewhere.

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
every `run:` body), a check that every third-party action is SHA-pinned, and the
version-sweep check above. Run these locally before pushing:

```bash
actionlint
python3 scripts/gen_catalog.py --check
python3 scripts/stamp_version.py --check
python3 tests/run_stamp_tests.py && python3 tests/run_step_tests.py
```

Changes here run in other people's production. Open a pull request, and record
the reasoning in [DECISIONS.md](DECISIONS.md).

## License

[MIT](LICENSE).
