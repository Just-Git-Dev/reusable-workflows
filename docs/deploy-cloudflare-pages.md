# deploy-cloudflare-pages

Builds a static site and deploys it to a Cloudflare Pages project via
[`cloudflare/wrangler-action`](https://github.com/cloudflare/wrangler-action).
Everything project-specific is an input: Pages project name, account id, build
command, output directory, Node version.

Pushes authored by `dependabot[bot]` or `renovate*` are skipped — bot actors
cannot hold deploy credentials, so those runs would only fail noisily.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `project_name` | input (req) | — | Cloudflare Pages project |
| `account_id` | input (req) | — | Cloudflare account id — not a credential, pass a repo/org variable |
| `working_directory` | input | `.` | build and deploy from here |
| `build_command` | input | `npm ci && npm run build` | run in `working_directory` |
| `output_dir` | input | `dist` | static assets, relative to `working_directory` |
| `node_version` | input | `20` | any setup-node spec: `20`, `20.x`, `lts/*` |
| `node_cache` | input | `npm` | `npm`/`yarn`/`pnpm`; empty string disables caching |
| `cache_dependency_path` | input | `<working_directory>/package-lock.json` | lockfile the cache keys on |
| `branch` | input | `main` | Pages deployment branch |
| `ref` | input | `''` | git ref to check out and deploy; empty ⇒ the triggering ref. Set it to re-deploy a specific tag from a `workflow_dispatch` run |
| `build_env` | input | `''` | extra build environment, newline-separated `KEY=VALUE` (values may contain spaces); scoped to the build step only |
| `cloudflare_api_token` | **secret** (req) | — | needs `Cloudflare Pages: Edit` |

## Outputs

`deployment_url` — the URL of the deployment this run produced.

## The API token

`cloudflare_api_token` must be a token with the **Cloudflare Pages: Edit**
permission, minted in the Cloudflare dashboard by a human. See
[rotate-cloudflare-token](rotate-cloudflare-token.md) for the rotation runbook
and an expiry nag you can schedule.

## Example caller

```yaml
name: Deploy website
on:
  push:
    tags: ['v*.*.*']
  workflow_dispatch: {}

permissions:
  contents: read

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-pages.yml@v1.1.0
    with:
      project_name: my-website
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      build_command: npm ci && npm run build
      output_dir: dist
      node_version: '20'
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

A monorepo subdirectory:

```yaml
    with:
      project_name: my-docs
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      working_directory: apps/docs
      output_dir: build
```

Re-deploy a specific tag from a manual run, with build-time variables:

```yaml
on:
  workflow_dispatch:
    inputs:
      tag: { description: 'Tag to (re)deploy', required: true }

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-pages.yml@v1.5.0
    with:
      project_name: my-app
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      ref: ${{ github.event.inputs.tag }}   # check out & deploy that tag, not the default branch
      build_command: npm ci && npm run build
      build_env: |
        VITE_API_BASE=${{ vars.API_BASE }}
        VITE_FIREBASE_PROJECT=${{ vars.FIREBASE_PROJECT }}
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

`build_env` keeps caller build vars out of `build_command` — they're exported
into the build step's shell only, never `$GITHUB_ENV`, so nothing leaks to later
steps.

## Concurrency

Keyed on `<project_name>-<branch>` with `cancel-in-progress: true` — a newer
deploy of the same branch supersedes an in-flight one rather than racing it.
