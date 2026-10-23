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
>
> **Designing a test strategy across several repos?** Read the
> [testing standard](docs/TESTING-STANDARD.md) — the umbrella-repo pattern: how a repo
> gates code it does not contain, the seven ways a CI gate ends up green without ever
> running, and the eleven principles + adoption scorecard that follow from fixing them.
> It **follows** the `testing` skill, which is the source of truth for the general rules;
> this document is their umbrella-repo application.

> **v4 is coming (pending release; not yet tagged).** v4.0.0 flips three defaults (bundle
> pinning on, `strict_values: true`; v5.0.0 made `sync-bundle-key` merge-only) and adds env-file deploys, revision labels
> and a loud rollback refusal. Read [runtime-config](docs/runtime-config.md) for the model and
> [MIGRATION-v4](docs/MIGRATION-v4.md) for the per-caller checklist. The additive new workflows
> (`repos-environments`, `distribute-env-secrets`, `deploy-env-lint`) ship in the same v4.0.0
> release (owner ruling 2026-10-21; there is no v3.10.0); until it is cut, pin the current latest tag.

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

### Release

Composite actions under `actions/`, used as a **step** (`uses: Just-Git-Dev/reusable-workflows/actions/<name>@<tag>`), not as a job.

| Action | Purpose |
|---|---|
| [`check-release-gate`](docs/check-release-gate.md) | **Read-only** root-release gate: for each service, the tag still points at the listed commit and the newest GitHub Actions `release-gate` check on it succeeded. It never waits and reports every service before failing |
| [`release-flow`](docs/release-flow.md) | The shared **multi-repo release flow**: a `release-flow` CLI action plus four reusable workflows (`release-pr-check`, `release-plan`, `release-drafts`, `release-publish`). A merged manifest is validated read-only, drafted, smoke-tested by the caller, then published one service at a time with each deploy proven live. `rehearsal: true` runs it with zero writes |
| [`release-pr-check`](docs/release-pr-check.md) | Release flow stage 1: on a release PR, exactly one new manifest, nothing else changed, valid shape. No secret, no App token |
| [`release-plan`](docs/release-plan.md) | Release flow stage 2: merge guard, CLI self-test, plan, validate, CI-green, resolve, contract states, service gates. Read-only |
| [`release-drafts`](docs/release-drafts.md) | Release flow stage 3: one draft Release per listed service. The first write; none in a rehearsal |
| [`release-publish`](docs/release-publish.md) | Release flow stage 4: publish each draft in order (six slots), prove each deploy live, then report |

### API contracts

| Action | Purpose |
|---|---|
| [`refresh-api-spec`](docs/refresh-api-spec.md) | Scheduled refresh of a committed copy of another service's **OpenAPI document** from its published URL: compares by meaning, opens one `spec-refresh/<name>` PR, runs the repo's own checks, and **merges only if they pass** — else comments the output and fails. Refuses a non-spec response (e.g. a Swagger UI HTML page served with 200) |

### Secrets & rotation

| Workflow | Purpose |
|---|---|
| [`manage-config-secrets.yml`](docs/manage-config-secrets.md) | Manage a **GKE** service's config **values**: dotenv → ConfigMap (keyvalue / react-`window.env`) + secrets into a backend (`k8s` / `gsm` blob or per-key). Values only — no deploy, no pod wiring |
| [`sync-bundle-key.yml`](docs/sync-bundle-key.md) | Upsert key(s) into a Secret Manager bundle → roll Cloud Run → disable the old version |
| [`actions/sync-bundle-key`](docs/sync-bundle-key-action.md) | The same sync as a **composite action** for a caller's own `environment:` job, so environment secrets reach it across an org boundary. The workflow above is a thin wrapper around it |
| [`rotate-signing-keypair.yml`](docs/rotate-signing-keypair.md) | Rotate an RS256 (JWT) signing keypair in a bundle → roll Cloud Run → disable the old version |
| [`rotate-worker-signing-secret.yml`](docs/rotate-worker-signing-secret.md) | Rotate an HMAC secret shared by a Cloudflare Worker + Cloud Run signer, zero-downtime via a two-slot grace window |
| [`actions/rotate-worker-signing-secret`](docs/rotate-worker-signing-secret-action.md) | The same rotation as a **composite action** for a caller's own `environment:` job, so environment secrets reach it across an org boundary. The workflow above is a thin wrapper around it |
| [`rotate-cloudflare-token.yml`](docs/rotate-cloudflare-token.md) | Verify the Cloudflare API token is active + print a rotation runbook |

### Repos as code

A project lists its GitHub repos in one `repos.yaml`; each feature below is a separate workflow over
a pure planner. Contract: [repos-register](docs/repos-register.md).

| Workflow | Purpose |
|---|---|
| [`repos-register-check.yml`](docs/repos-register-check.md) | F1: validate `repos.yaml` against `schemas/repos.v1.json`. No token, writes nothing |
| [`repos-create.yml`](docs/repos-create.md) | F2: create `status: new` repos that are missing; rename only via `rename_from`. Report or enforce |
| [`repos-settings.yml`](docs/repos-settings.md) | F3: description, visibility (never public), default branch and settings against live. Report or enforce |
| [`repos-variables.yml`](docs/repos-variables.md) | F4: the listed NON-secret repository variables. Never deletes one. Report or enforce |
| [`repos-wif-link.yml`](docs/repos-wif-link.md) | F5: link each repo's deployer SA to the WIF pool, scoped to one repo and environment. Report or enforce |
| [`repos-service-accounts.yml`](docs/repos-service-accounts.md) | F6: create the registered service accounts that are missing. Never deletes one, never creates a key. Report or enforce |
| [`repos-deploy-scope.yml`](docs/repos-deploy-scope.md) | F7: each repo may deploy only its own service (resource-level IAM). Report or enforce |
| [`repos-secrets.yml`](docs/repos-secrets.md) | F8: one `<service>-env` secret per service, its whole IAM policy written here only (runtime reads, own deployer syncs). Report or enforce, prune opt-in |
| [`repos-environments`](docs/repos-environments.md) | F9 (v4.0.0): GitHub environments per repo declared in `repos.yaml` (branch rules, never deletes) |
| [`distribute-env-secrets`](docs/distribute-env-secrets.md) | v4.0.0: copy a project-repo secret into the environment of service repos |
| [`deploy-env-lint`](docs/deploy-env-lint.md) | v4.0.0: lint `deploy/env.<stage>.yaml` and `deploy/secret-keys.txt` before deploy |

### Backups, alerts & housekeeping

| Workflow | Purpose |
|---|---|
| [`neon-backup.yml`](docs/neon-backup.md) | `pg_dump` a Postgres database to a private artifact (custom or plain-gz) |
| [`cleanup-gar-images.yml`](docs/cleanup-gar-images.md) | Age-sweep Artifact Registry images, protecting digests live on Cloud Run Services **and** Jobs |
| [`cleanup-secret-versions.yml`](docs/cleanup-secret-versions.md) | Quarantine-sweep Secret Manager versions (`ENABLED`→`DISABLED`→`DESTROYED`), never touching what `latest` resolves to |
| [`retire-gar-packages.yml`](docs/retire-gar-packages.md) | Delete **entire** Artifact Registry packages for retired services, refusing any package with a live reference |
| [`bootstrap-alerts.yml`](docs/bootstrap-alerts.md) | Apply a Cloud Monitoring channel + alert policies from the caller's `infra/alerts/` |
| [`service-alerts.yml`](docs/service-alerts.md) | **Alerts as data**: render an [AlertSpec](docs/alertspec.md) (built-in Cloud Run / GoFr / log packs + per-app overrides + custom rules) into policies, prove each rule has live data, lint, and apply — `dry_run` by default |
| [`validate-alerts.yml`](docs/validate-alerts.md) | **PR-time preflight** for those policy files — offline structural lint, plus real MQL execution when given a project (the Monitoring API has no `validateOnly`) |
| [`verify-metrics-arrival.yml`](docs/verify-metrics-arrival.md) | **Post-deploy probe** that metrics actually reached Cloud Monitoring — three outcomes (pass / no-metrics / cannot-verify), so a probe that could not see never reads as one that is happy |
| [`bootstrap-dashboards.yml`](docs/bootstrap-dashboards.md) | Apply Cloud Monitoring **dashboards** from the caller's `infra/dashboards/`; updates in place so dashboard ids and bookmarks survive |
| [`cleanup-cloud-run-revisions.yml`](docs/cleanup-cloud-run-revisions.md) | Prune inactive Cloud Run revisions, releasing the GAR digests they pin — schedule **before** `cleanup-gar-images` |
| [`deploy-cloudflare-pages.yml`](docs/deploy-cloudflare-pages.md) | Build a static site and deploy it to Cloudflare Pages |
| [`deploy-cloudflare-worker.yml`](docs/deploy-cloudflare-worker.md) | Deploy a Cloudflare Worker with `wrangler deploy`, with an optional change-skip and smoke check |
| [`cloud-run-update.yml`](docs/cloud-run-update.md) | Apply config to an existing Cloud Run service — identity, sizing, scaling, env, secrets — with a health gate; never deploys an image |
| [`bootstrap-cf-dns.yml`](docs/bootstrap-cf-dns.md) | Converge a Cloudflare zone's DNS records and Origin Rules, preserving rules other writers own |
| [`bootstrap-cf-service.yml`](docs/bootstrap-cf-service.md) | Give a Cloud Run service a public hostname — Cloud Run domain mapping + DNS-only CNAME, or a proxied CNAME + Origin Rule host override |
| [`bootstrap-r2-bucket.yml`](docs/bootstrap-r2-bucket.md) | Converge a Cloudflare R2 bucket for public downloads — bucket, custom domain, `r2.dev` off — and prove it with an upload / public-GET / delete probe |
| [`publish-r2-artifact.yml`](docs/publish-r2-artifact.md) | Publish a build artifact to R2 as an immutable `<prefix>/<version>/` and advance `<prefix>/latest/` forward-only, with sha256 sidecars and a public read-back |

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v5.1.0
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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v5.1.0
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

Merge that, then **cut the release via the `Release` workflow**, not a bare
`git tag && git push --tags`:

```bash
gh workflow run release.yml -f version=v1.2.3
```

`release.yml` (`workflow_dispatch`) runs `stamp_version.py --check --expect
v1.2.3` — the exact same tag-vs-tree comparison CI used to only run *after*
the tag existed — and creates no tag and publishes no release if it fails.
Only once that's green does it create the tag and publish the GitHub Release.
This is the fix for the `v2.6.1` incident: that check caught the tree still
stamped `v2.6.0`, but only on the tag-push CI run, by which point the broken
tag was already live. Moving the same check before tag creation is what
closes the gap — a GitHub ruleset can't, because a release publish isn't a
ruleset target and a tag-push ruleset would still evaluate before the
tag-triggered CI run exists. See `plans/provenance-and-release-gate.md` §2
for the full analysis.

**Consequence — the tag-push CI run no longer fires for releases.** `release.yml`
pushes the tag using the default `GITHUB_TOKEN`, and a tag pushed by
`GITHUB_TOKEN` does not trigger `on: push` workflows — so `ci.yml`'s
`tags: ['v*.*.*']` trigger will not run for tags cut this way. That's fine:
`release.yml`'s own gate runs the identical `--check --expect`, before the
tag exists, so nothing depends on that downstream run to catch a drift. If a
tag ever gets cut some other way (hand-pushed with a real user token), the
tag-push CI run still fires as belt-and-braces.

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
  First-party `Just-Git-Dev/reusable-workflows/...@vX.Y.Z` refs are exempt on
  purpose — semver here tracks the *input contract*, and a SHA would pin the bytes
  and discard it. To check that exemption in a consumer repo, run the gate rather
  than grepping for it:

  ```bash
  scripts/pin_gate_behaviour.sh ../../<consumer-repo>/<service> ../../<consumer-B-repo>/ui   # any repo paths
  scripts/pin_gate_behaviour.sh --self-test                           # prove it goes red
  ```

  It executes each repo's own `Reject mutable action refs` step under GNU grep in
  a container and asserts all four cases, including that the exemption has not
  widened into an org-wide hole. Not wired to CI: its subjects are sibling repos
  absent from this checkout, so a job here would find nothing and go green. See
  [DECISIONS.md](DECISIONS.md#2026-09-05--the-pin-gate-is-verified-by-running-it-not-by-grepping-for-it).
- **Every `run:` declares `shell: bash`.** GitHub's implicit default is `bash -e`
  — errexit on, but **`pipefail` off** — which masks a failing head-of-pipe. An
  explicit `shell: bash` runs with `-eo pipefail`.

## Contributing

### Local gate

`make ci` runs exactly the checks `.github/workflows/ci.yml` runs, in CI's order; `ci.yml` calls
the same make targets, so the two cannot drift (`tests/run_ci_make_tests.py` fails if they do).

- `make hooks` once per clone: installs the committed pre-push hook (`core.hooksPath=.githooks`).
- `make ci` before pushing (the hook runs it for you). It stops at the first failing check, names
  the target, and prints how many checks ran (26 of 26 today).
- What it runs: `tools` (local shellcheck and actionlint must equal CI's pinned versions, else it
  prints the install hint), `actionlint`, `canary`, `shellcheck`, `preflight` (vendored workflow-preflight), `zizmor` (workflow security audit, policy `zizmor.yml`), `venv` (`.venv` built from
  `requirements-ci.txt`, the same file CI installs), the catalog, docs, version-sweep, v1-alias and
  doc-example checks, the fixture and step-body test suites, `tools-promtool` (promtool must be the
  pinned 3.13.1, the alertgen oracle), `alertgen`, `pinned` and the gate's own tests.
- The hook checks the commit being pushed, not just the tree: it refuses a dirty tree, or a pushed
  ref whose sha is not `HEAD` (an annotated tag is peeled to its commit first), and says what to
  do. It scrubs git's env before running checks. No environment variable can replace its gate.
- Needs on the laptop: shellcheck 0.11.0, actionlint 1.7.12 and zizmor 1.31.1 on `PATH`, and `python3.12` or
  `python3.13`. promtool is exact-pinned too (3.13.1): if `PATH` has another version,
  `make tools-promtool` fetches the pinned release for your OS/arch into the gitignored `.tools/bin`,
  verifies its sha256, and puts it first on `PATH`. The `v1` tag must be present locally
  (`git fetch --tags`).
- Over ssh GitHub can drop the idle connection while the hook runs (rc 141/128); then push over
  HTTPS with the global git config skipped:
  `GIT_CONFIG_GLOBAL=/dev/null git push https://github.com/Just-Git-Dev/reusable-workflows.git <branch>`.
- Emergency bypass only: `git push --no-verify`. CI still runs the same checks.

Run `make ci` before pushing; it is what CI runs.

Changes here run in other people's production. Open a pull request, and record
the reasoning in [DECISIONS.md](DECISIONS.md).

## License

[MIT](LICENSE).
