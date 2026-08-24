# `deploy-cloudflare-worker.yml`

Deploy a Cloudflare Worker with `wrangler deploy`, from a worker directory inside the
caller's repo.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-worker.yml@v2.4.1
```

## What it does and does not own

**Routes, bindings, vars, and the worker's own name are not inputs.** They live in the
worker directory's `wrangler.toml`, wrangler applies them on every deploy, and modelling
them here would create a second source of truth that drifts silently — the workflow's copy
would be advisory while wrangler's copy would be real.

What this workflow owns is everything *around* the deploy:

| Concern | How |
|---|---|
| Which ref ships | `ref`, plus an optional `require_semver_ref` gate |
| Whether to ship at all | `watch_paths` — skip when the worker did not change |
| Build inputs | `node_version`, `install_command` |
| Correctness gate | `test_command` — a non-zero exit blocks the deploy |
| Which config | `wrangler_environment`, `dry_run` |
| Did it actually work | `smoke_url` + `smoke_expect` |

### wrangler is not installed by this workflow

`npx` resolves it from the worker directory's own lockfile, so the version that deploys
your worker is the version you committed and Dependabot updates — not a floating latest
that can change under you between two identical runs. `wrangler_version` overrides this,
and exists only for a worker that has no wrangler dependency of its own.

## Inputs

`catalog.json` is the authoritative contract (generated from the YAML, checked in CI). The
notable ones:

| Input | Default | Notes |
|---|---|---|
| `worker_directory` | *required* | Directory holding `wrangler.toml`. |
| `worker_name` | `worker_directory` | Concurrency group + summary only. The deployed name comes from `wrangler.toml`. |
| `ref` | trigger ref | Set it to re-deploy a specific tag from a `workflow_dispatch`. |
| `require_semver_ref` | `false` | Fail fast unless the ref is `vX.Y.Z`. |
| `watch_paths` | `''` (always deploy) | See below. |
| `node_version` | `'22'` | **Not** current LTS — see below. |
| `install_command` | `npm ci \|\| npm install` | Empty skips installing. |
| `test_command` | `''` | Runs after install, before deploy. |
| `wrangler_environment` | `''` | `--env`. |
| `wrangler_version` | `''` | Empty ⇒ from your lockfile. Prefer empty. |
| `dry_run` | `false` | `wrangler deploy --dry-run`: builds and validates, uploads nothing. |
| `smoke_url` / `smoke_expect` / `smoke_status` | `''` / `''` / `200` | Skipped when the deploy was skipped or dry. |

**Secrets:** `cloudflare_api_token` (required) needs **Account → Workers Scripts → Edit**.
If the worker binds R2, KV, D1 or Queues, the token needs Edit on those too — wrangler
reconciles bindings as part of the deploy, so a token that can only write scripts fails
*after* the script upload, leaving the worker live with stale bindings.
`cloudflare_account_id` is optional when `wrangler.toml` sets `account_id`.

### `node_version` defaults to 22, not to current LTS

Both production workers pin `22` today. Defaulting to `24` would mean that adopting this
workflow silently changes the runtime a worker is built on — a migration should not move
two variables at once. Pass `'24'` when you want that move, deliberately and on its own.

### `watch_paths` — skip a deploy that would change nothing

Callers wired to a `v*.*.*` tag push get a run for **every** release tag, including the many
that touch nothing the worker cares about. `watch_paths` diffs the deployed tag against the
previous `vX.Y.Z` tag and skips when none of the listed paths changed. The job still
succeeds, and `outputs.skipped` is `true`.

```yaml
watch_paths: |
  cf-worker-files/
  .github/workflows/deploy-files-worker.yml
```

Include the caller workflow file itself if a change to it should force a deploy.

Three behaviours worth knowing, each covered by a step test:

- **The first tag never skips.** With no earlier tag there is nothing to diff, so it deploys.
- **Any one path changing deploys.** The skip needs *all* of them unchanged.
- Blank and padded lines in the block scalar are ignored, not treated as paths.

The checkout is unconditionally `fetch-depth: 0`. Making the depth depend on `watch_paths`
would leave the skip quietly wrong for anyone who set it — a shallow clone has no previous
tag, so every run would look like a first release.

## Copy-paste: deploy a worker on every release tag

```yaml
name: Deploy files worker

on:
  push:
    tags: ['v*.*.*']
  workflow_dispatch:
    inputs:
      tag:
        description: 'Existing vX.Y.Z tag to re-deploy'
        required: true
        type: string

permissions:
  contents: read

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-worker.yml@v2.4.1
    with:
      worker_directory: cf-worker-files
      worker_name: automahn-files-cdn
      ref: ${{ inputs.tag }}
      require_semver_ref: true
      watch_paths: |
        cf-worker-files/
        .github/workflows/deploy-files-worker.yml
      test_command: npm test
      smoke_url: https://files.example.com/healthz
      summary_notes: |
        - Route: files.example.com/*
        - Bucket binding: FILES_BUCKET
        - Signing secrets are rotated by `rotate-signing-secret.yml`.
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      cloudflare_account_id: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

`ref: ${{ inputs.tag }}` is empty on a tag push, which is exactly right — the workflow then
falls back to the ref that triggered the run.

## Concurrency

`cf-worker-deploy-<worker>-<env>`, **without** `cancel-in-progress`. Unlike a Pages build,
cancelling here can interrupt wrangler mid-upload and leave the worker running against a
half-applied set of bindings. A queued second deploy costs a minute; a half-applied one
costs an incident.

## Notes

- Bot-authored pushes (`dependabot[bot]`, `renovate*`) are skipped — they cannot hold deploy
  credentials, so the run would fail confusingly rather than usefully.
- `test_command` is the only gate between a bad handler and production: a worker has no
  staging environment unless you build one with `wrangler_environment`.
