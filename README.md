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
| `rotate-worker-signing-secret.yml` | Rotate an HMAC signing secret shared by a Cloudflare Worker (verifier) and a Cloud Run signer, zero-downtime via a two-slot grace window | [docs](docs/rotate-worker-signing-secret.md) |
| `rotate-signing-keypair.yml` | Rotate an RS256 (JWT) signing keypair in a Secret Manager bundle → roll Cloud Run → disable the old version | [docs](docs/rotate-signing-keypair.md) |

## Versioning — pin to a release tag

```yaml
jobs:
  backup:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/neon-backup.yml@v1.1.0
```

**Pin an exact `vX.Y.Z` tag.** Releases are immutable: once cut, a tag is never
moved. Upgrading is therefore a commit in your own repo, reviewed like any other
change — a fix here can never alter your production ops behind your back.

`v1` is a **frozen legacy alias**, left pointing at the first release so the
original callers keep working. It does not track new releases, and
`deploy-cloudflare-pages.yml` does not exist at `v1`. Don't pin new callers to it.

Never use `@main`.

We follow semver on the *input contract*: a new required input, a removed input,
a changed default, or a behaviour change on a destructive path is a major bump.
Read the [DECISIONS.md](DECISIONS.md) entry for a release before upgrading — in
`v1.1.0`, `sync-bundle-key` now **fails** a rotation whose Cloud Run rollout was
previously only warned about.

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
