# Runtime config: how settings and secrets reach a Cloud Run revision

The model behind the v4 workflows: where each kind of configuration lives, how a revision
records exactly what it ran, how a key is removed, and how to trace a running revision back to a
commit. This is a guidance page, not a workflow reference; the workflows it describes are
[`sync-bundle-key`](sync-bundle-key.md), [`deploy-cloud-run`](deploy-cloud-run.md),
[`cloud-run-update`](cloud-run-update.md), [`distribute-env-secrets`](distribute-env-secrets.md)
and [`rollback-service`](rollback-service.md). Moving from v3: [MIGRATION-v4.md](MIGRATION-v4.md).

## The four homes — and the one-place rule

**A key lives in exactly one of four homes.** Two homes for the same key means precedence picks
the value, and precedence differs between services; so a key is never in two.

| # | Home | Holds | Changes by |
|---|---|---|---|
| 1 | `configs/.env`, committed, baked into the image | settings that are identical in every environment | a commit and an image build |
| 2 | `deploy/env.<stage>.yaml`, committed in the service repo, passed to Cloud Run with `--env-vars-file` | **non-secret** settings that differ per environment (hosts, project ids, CORS origins), as literal values | a commit |
| 3 | one Secret Manager dotenv bundle `<deployable>-env`, mounted as a file at a **numbered version**, never `:latest` | **secrets only** | the `sync-bundle-key` workflow, with values from GitHub **environment** secrets |
| 4 | one Secret Manager secret per key | only material a workflow **generates** (signing keypairs, a rotated signing secret) | the rotate workflows |

GitHub repository or environment **variables** are not a home for settings: a value that lives
only in a variable is invisible to code review and drifts from what the service repo declares.

A repo enforces the one-place rule with a build test: `configs/.env`, every
`deploy/env.*.yaml` and `deploy/secret-keys.txt` must be pairwise disjoint, and the first two must
hold no secret-looking key. [`deploy-env-lint`](deploy-env-lint.md) carries the same checks for
callers that do not write that test themselves.

**No connection URLs.** A DSN or `*_URL` carrying credentials is not a config value; a service
reads `DB_*` / `REDIS_*` parts directly, so the plain parts go in home 2 and only the password goes
in home 3. This also removes any "derived key" (a URL built from other keys) and its boot-time guard.

## Where the secret VALUES come from (GitHub side)

Secret values are held only as GitHub **environment** secrets (for example `stage`, `prod`), split
by how many repos consume them. **Gap (2026-10-21):** `sync-bundle-key` cannot yet read
environment secrets from a caller in another organisation (see
[sync-bundle-key](sync-bundle-key.md#payload_source-environment-is-unproven)). Until that is
fixed, values a sync must read stay at repo level in such callers.

- **One consuming repo** (a database password): held only in that repo's environment secrets.
- **Two or more consuming repos** (an object-storage key pair): held in the project repo and
  copied into each consumer's environment secrets by [`distribute-env-secrets`](distribute-env-secrets.md).
  That workflow never creates an environment; it fails when the target is missing.
- Organisation secrets are not used.

The environment itself, with its branch policy, is created by
[`repos-environments`](repos-environments.md) (a feature of the repo register). Environments must
exist before a v4 job names one; see "The environment guard" below.

## Pinning: every revision names its bundle version

Each Cloud Run revision mounts the bundle at a **numbered version** (`<deployable>-env:<N>`).
A revision's spec therefore records exactly which secret version it runs, and shifting traffic
back to an older revision brings that revision's secrets back with it.

- **Only the bundle writers move the pin.** [`sync-bundle-key`](sync-bundle-key.md),
  [`rotate-signing-keypair`](rotate-signing-keypair.md) and
  [`rotate-worker-signing-secret`](rotate-worker-signing-secret.md) add version N+1 and roll each
  service onto `:N+1`. All three pin in v4; otherwise a key rotation would silently un-pin every
  service.
- **A deploy keeps the pin it inherits.** [`deploy-cloud-run`](deploy-cloud-run.md) never moves it.
  If the template still mounts `:latest`, the deploy resolves the newest ENABLED version, pins that
  number, and says so in the summary.
- **A pinned version is never disabled while a retained revision uses it.** The keep-set of the
  bundle writers is: the new version N+1, plus the version pinned by each of the **two newest
  revisions** of every rolled service, plus the `keep_enabled_count` newest as a floor. Everything
  else is disabled. Nothing here destroys a version: that stays in
  [`cleanup-secret-versions`](cleanup-secret-versions.md).
- **Why two revisions.** The previous revision must stay startable so a rollback to it works.
  [`rollback-service`](rollback-service.md) refuses loudly, naming the revision and the
  `<deployable>-env:<N>`, when the target's pinned version is no longer ENABLED, rather than start
  a revision that cannot read its secrets.

A rollback to a revision older than the two newest therefore fails loudly by design unless its
version was re-enabled by hand (`gcloud secrets versions enable`).

## Labels: a revision records how it was made

Every revision carries these labels:

| Label | Value | Written by |
|---|---|---|
| `jgd_commit` | the commit that was deployed | `deploy-cloud-run` (exists in v3) |
| `jgd_env_version` | `<N>`, the pinned bundle version | the bundle writers and the deploys |
| `jgd_env_sha` | first 8 hex of the SHA-256 of the **rendered** env file | `deploy-cloud-run` |
| `jgd_run` | the GitHub Actions run id | the bundle writers and the deploys |

## Trace walk-through: from a running revision to its commit

1. `gcloud run revisions describe <revision> --format='value(metadata.labels)'` gives
   `jgd_commit`, `jgd_env_version`, `jgd_env_sha`, `jgd_run`.
2. `jgd_run` names a GitHub Actions run. Its **run summary** lists every key by **name** and
   **source** (`configs/.env`, env file, bundle `<deployable>-env:<N>`, generated), with the value
   only for non-secrets and `(secret)` otherwise.
3. The same run uploads `config-manifest.json` as an artifact, holding the commit, the image
   digest, the revision, the bundle version, and the keys with their sources. Retention follows
   the `manifest_retention_days` input (default 400); the repository's own maximum artifact
   retention must be at least that, or GitHub caps it.
4. The key list is also committed: `deploy/secret-keys.txt` (bundle key names) and
   `deploy/env.<stage>.yaml` at the labelled commit. `jgd_env_sha` proves the file the revision ran
   is the one rendered from that commit plus its generated values.
5. `gcloud secrets versions describe <N> --secret <deployable>-env` gives the time the bundle
   version was written; the sync run's summary names the keys it wrote (names only, never values).

## Removing a key

`sync-bundle-key` is merge-only (v5.0.0; v4 limited the bundle to the keys listed in
`deploy/secret-keys.txt`):

- the new bundle is the current bundle overlaid with the payload; every other key is kept;
- a key leaves only when the caller names it in `remove_keys`, which is the confirmation;
- the dry run prints `+added ~updated -removed` by name only;
- `deploy/secret-keys.txt` names the keys to read from the environment (environment source), so a
  key that only a rotator writes is never listed and never dropped.

Because the previous revision stays pinned to the previous bundle version (the two-revision
keep-set), a removal that turns out to be wrong is undone by rolling back to that revision.

Keys written by the rotate workflows (`JWT_*`, a worker signing secret) must be in the list too.

## The environment guard

When `sync-bundle-key` is given an `environment`, its first step reads the environment and refuses
unless it has a **deployment branch policy** (for example `main` only). A job that names an
environment which does not exist makes GitHub create it with no policy at all; the guard turns that
into a failure that leaves an empty environment for `repos-environments` to converge, instead of a
silently unprotected one that holds secrets. It needs `actions: read` in the caller.

The deploy workflows deliberately have **no** job-level `environment:`. They need no environment
secrets (keyless WIF plus the pinned bundle), and a deploy triggered by a tag would be rejected by
a `main`-only branch policy. Their `environment` input keeps its v3 meaning: the name of the GitHub
Deployment record.

## Precedence

None is needed: with the one-place rule no key has two values. The deployed env file reaches Cloud
Run as `--env-vars-file`, which **replaces** the service's environment variables with exactly the
file's contents, so a variable removed from the file is removed from the service on the next
deploy.

## Credentials

Per the owner's ruling (2026-10-21), one credential does both jobs: the org's automation App (`<org>-automation`, formerly the release App).
It holds `Administration: write` (for `repos-environments` enforce) and `Environments: write` (for
`distribute-env-secrets`), plus what it already holds. See those two workflows' docs.

## Deploy targets and branch rules

Per the owner's rulings (2026-10-21): the per-stage deploy targets (GCP project id, WIF provider,
deployer service account) live in a committed `deploy/target.<stage>.yaml` in the service repo,
read by the caller; they are not GitHub environment variables and not inline literals. The `stage`
environment is deployable from `main` and from `v*` tags; `stage-seed` (the seed-only
database credential) and `prod` are `main` only.
