# reusable-workflows

Shared **`workflow_call`** GitHub Actions workflows for teams running apps on
**Google Cloud Run + Postgres + Cloudflare**, authenticating to GCP with
[Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
and mounting application config from a Secret Manager "bundle" secret.

They are the ops workflows that every such repo ends up copy-pasting: apply
monitoring alerts, rotate a secret and roll the services onto it, back up the
database, sweep old container images, deploy a static site, nag about an
expiring API token. Hosting them once means a fix lands everywhere.

Nothing here is specific to any one project. Every project-specific value —
GCP project id, region, service names, secret names, Cloudflare account and zone
— is a `workflow_call` input.

## Workflows

| Workflow | Purpose | Docs |
|---|---|---|
| `bootstrap-alerts.yml` | Apply a Cloud Monitoring channel + alert policies from the caller's `infra/alerts/` | [docs](docs/bootstrap-alerts.md) |
| `sync-bundle-key.yml` | Upsert key(s) into a Secret Manager bundle → roll Cloud Run → disable the old version | [docs](docs/sync-bundle-key.md) |
| `neon-backup.yml` | `pg_dump` a Postgres database to a private artifact (custom or plain-gz) | [docs](docs/neon-backup.md) |
| `cleanup-gar-images.yml` | Age-sweep Artifact Registry images, protecting digests live on Cloud Run Services **and** Jobs | [docs](docs/cleanup-gar-images.md) |
| `deploy-cloudflare-pages.yml` | Build a static site and deploy it to Cloudflare Pages | [docs](docs/deploy-cloudflare-pages.md) |
| `rotate-cloudflare-token.yml` | Verify the Cloudflare API token is active + print a rotation runbook | [docs](docs/rotate-cloudflare-token.md) |

## Versioning — pin to a release tag

```yaml
jobs:
  backup:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/neon-backup.yml@v1.1.0
```

Releases are immutable `vX.Y.Z` tags. `v1` is a **floating alias** that moves to
the newest backwards-compatible release — convenient, but it means a change here
can alter your ops without a commit in your repo. Pin the exact version for
anything that mutates production; use `v1` only if you want the updates.

Never use `@main`.

We follow semver for the *input contract*: a new required input, a removed
input, a changed default, or a behaviour change on a destructive path is a major
bump.

## Why this repo is public

GitHub only allows a repository to call a reusable workflow from a **private**
repository in the same organization or enterprise. Sharing workflows across
organizations therefore requires the host repo to be public.

- **No secrets live here.** Callers pass every secret at call time; nothing
  sensitive is committed.
- Callers in a different organization **cannot use `secrets: inherit`** — every
  secret must be passed explicitly. Each doc page shows the call.

## Conventions

- **WIF provider and service account are inputs, not secrets.** They are
  resource identifiers, not credentials. Passing them as inputs also lets each
  caller keep its own variable naming.
- **Callers own their trigger.** These workflows have no `schedule` of their
  own; you add the `schedule` / `workflow_dispatch` that suits you.
- **The caller repo is what gets checked out**, so files like `infra/alerts/`
  stay in the repo they describe.
- **Destructive workflows take a `dry_run` input** and default it to the safe
  value. Run the plan, read it, then apply.
- **Third-party actions are pinned to full commit SHAs**, with the version in a
  trailing comment. A tag is mutable; these workflows mint cloud credentials and
  handle database dumps, so a moved tag would be a supply-chain event. CI
  enforces this on every pull request.
- **Every `run:` block declares `shell: bash`.** GitHub's implicit default on
  Linux is `bash -e {0}` — errexit on, but **`pipefail` off**, so a failing
  command at the head of a pipe is masked by a successful tail. An explicit
  `shell: bash` runs with `-eo pipefail`.

## Contributing

`.github/workflows/ci.yml` runs `actionlint` (which includes `shellcheck` over
every `run:` body) and a check that every third-party action is SHA-pinned.

Changes here run in other people's production. Open a pull request, and record
the reasoning in [DECISIONS.md](DECISIONS.md).

## License

[MIT](LICENSE).
