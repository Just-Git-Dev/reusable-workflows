# ci-node

The Node/React toolchain core every repo copy-pastes: install · lint · test ·
build, with setup-node dependency caching. Every stage is toggleable and every
command is overridable, so yarn/pnpm, monorepo packages, and no-dependency
suites (`node --test`) all fit.

**What stays in the caller.** Bespoke steps — OpenAPI type-drift verification,
sibling-repo checkouts for shared specs, custom guard scripts — belong in their
own jobs/steps in the caller.

## Inputs

| Name | Default | Notes |
|---|---|---|
| `runs_on` | `ubuntu-latest` | runner label. **Self-hosted must be on Actions Runner ≥ v2.327.1** — `setup-node` v7 runs on Node 24. GitHub-hosted runners already satisfy this. |
| `working_directory` | `.` | package root (monorepo) |
| `node_version` | `20` | any setup-node spec: `20`, `22`, `lts/*` |
| `node_cache` | `npm` | `npm`/`yarn`/`pnpm`; empty string disables caching |
| `cache_dependency_path` | `<working_directory>/package-lock.json` | lockfile the cache keys on |
| `enable_corepack` | `false` | run `corepack enable` before setup-node (pnpm / modern yarn) |
| `npm_registry_url` | `''` | private npm registry to authenticate against, e.g. `https://npm.pkg.github.com`. Empty ⇒ registry auth is untouched — see [Private registries](#private-registries) |
| `npm_registry_scope` | `''` | package scope routed to `npm_registry_url`, e.g. `@acme`. Optional for GitHub Packages, which falls back to the repository owner |
| `timeout_minutes` | `15` | job timeout |
| `install` / `install_command` | `true` / `npm ci` | dependency install |
| `run_lint` / `lint_command` | `true` / `npm run lint` | lint |
| `lint_blocking` | `true` | `false` = report lint failures without failing the job |
| `run_tests` / `test_command` | `true` / `npm test` | test |
| `coverage_threshold` | `0` | when non-zero, total **line** coverage is read from `coverage_summary_path` and the job **fails** below this percent. Measuring is decoupled from gating: `update_badges: true` also reads coverage, with no gate |
| `coverage_summary_path` | `coverage/coverage-summary.json` | Istanbul `json-summary` report, relative to `working_directory`. Read only when a threshold is set or `update_badges` is on — `test_command` must emit it |
| `enable_services` | `false` | run tests in a `node-db` job with postgres + mysql + redis service containers on localhost (`5432`/`3306`/`6379`) — for DB-backed Node backends |
| `postgres_image` / `postgres_db` / `postgres_password` | `postgres:16` / `test` / `postgres` | postgres service (`enable_services` only) |
| `mysql_image` / `mysql_database` / `mysql_root_password` | `mysql:8` / `test` / `root` | mysql service (`enable_services` only) |
| `redis_image` | `redis:7` | redis service (`enable_services` only) |
| `run_build` / `build_command` | `true` / `npm run build` | build |
| `update_badges` | `false` | commit Coverage + eslint-disable-count badges into the README on default-branch pushes — see [README badges](#readme-badges). Requires `permissions: contents: write` **in the caller** |
| `readme_path` | `README.md` | README the badges are written into — **repo-root relative**, *not* `working_directory` relative |
| `badge_branch` | `''` | branch the badge commit is pushed to; empty ⇒ the repository default branch. Point it at a sandbox branch to trial the feature |

## Secrets

| Name | Required | Notes |
|---|---|---|
| `npm_auth_token` | no | token for `npm_registry_url`, exposed to the install step as `NODE_AUTH_TOKEN`. Omit it and CI stays credential-free |

Nothing else — otherwise this is public/read-only CI. (Need a private sibling repo
for specs? Do that checkout in a caller job.)

## Private registries

Installing a scoped package from a private registry needs two inputs and a secret.
The work is delegated to `actions/setup-node`, which writes
`$RUNNER_TEMP/.npmrc` containing `//<registry>/:_authToken=${NODE_AUTH_TOKEN}` plus
`@scope:registry=<url>`, and points `NPM_CONFIG_USERCONFIG` at it; npm expands the
token at install time.

```yaml
    with:
      npm_registry_url: https://npm.pkg.github.com
      npm_registry_scope: '@acme'
      install_command: npm ci --legacy-peer-deps
    secrets:
      npm_auth_token: ${{ secrets.PACKAGES_READ_PAT }}
```

The token must be a **secret**, never an input — `workflow_call` inputs are not
masked in logs. For **GitHub Packages** it needs `read:packages`, and it has to be a
PAT whenever the package lives in a different repo than the caller: `GITHUB_TOKEN`
only reaches packages owned by, or explicitly shared with, the caller repo.

Two limits worth knowing before you reach for this:

- **One registry.** setup-node writes a single registry line, so a repo pulling
  scoped packages from two private registries still has to hand-roll its own
  `.npmrc`. Tracked in `TODO.md`.
- **A committed `.npmrc` wins.** setup-node's file is the npm *user* config, and a
  repo-level `.npmrc` takes precedence over it for any key it sets.

Leaving `npm_registry_url` empty (the default) is a true no-op: setup-node skips
auth setup entirely, writing no `.npmrc` and exporting no `NPM_CONFIG_USERCONFIG`.

**Running CI and deploy from one workflow?** The copy-paste
[CI + stage + prod example](deploy-cloudflare-pages.md#copy-paste-one-workflow-for-ci--stage--prod)
wires this workflow to `deploy-cloudflare-pages` with `needs:`, so a deploy cannot
start unless the gates pass.

**Service containers are language-agnostic** — the same `enable_services` inputs
exist on [`ci-go`](ci-go.md). Set `enable_services: true` for a DB-backed Node
backend and all three containers start; `install`/`lint`/`build` stay in the
`node` job, tests move to the `node-db` job.

## Example caller

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-node.yml@v1.20.0
    with:
      node_version: '22'
      test_command: 'npm test -- --run'
```

No-dependency suite (Node's built-in test runner):

```yaml
    with:
      node_cache: ''
      install: false
      run_lint: false
      run_build: false
      test_command: 'node --test'
```

DB-backed Node backend — inline service containers:

```yaml
    with:
      enable_services: true     # postgres + mysql + redis on localhost
      test_command: 'npm run test:integration'
```

Monorepo package:

```yaml
    with:
      working_directory: frontend/web
      node_version: '22'
```

## README badges

The `ci-go` counterpart of this feature is documented at length in
[`ci-go.md`](ci-go.md#readme-badges) — same inputs, same `badges` job, same
`permissions: contents: write` and branch-protection caveats. Two things differ
for Node.

**1. Coverage must be produced by your `test_command`.** `ci-go` gets coverage
for free from `go test -coverprofile`; there is no equivalent here, so this
workflow reads an **Istanbul `json-summary` report** and takes `total.lines.pct`.
Add the reporter:

```jsonc
// jest
"test": "jest --coverage --coverageReporters=json-summary --coverageReporters=text"
// vitest
"test": "vitest run --coverage --coverage.reporter=json-summary --coverage.reporter=text"
```

If the file is missing while `coverage_threshold` or `update_badges` is on, the
job fails with a `::error::` naming the reporter flag to add. `coverage_summary_path`
is relative to `working_directory` (unlike `readme_path`, which is repo-root
relative).

**2. The suppression badge counts `eslint-disable`,** via
`grep -rIE --include='*.{js,jsx,ts,tsx,vue}' --exclude-dir=node_modules` (also
skipping `dist`, `build`, `coverage`) — the ESLint analogue of `ci-go`'s `nolint`
count. It renders as `![eslint-disable count](…)`; the literal `-` is doubled to
`eslint--disable_count` in the shields.io URL because `-` is that API's field
separator.

```yaml
jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-node.yml@v1.20.0
    permissions:
      contents: write        # REQUIRED — caller permissions cap the called workflow
    with:
      update_badges: true
      test_command: 'vitest run --coverage --coverage.reporter=json-summary'
```

## Concurrency

Keyed on `<workflow>-<ref>` with `cancel-in-progress: true`.
