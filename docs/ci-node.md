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
| `node_version` | `24` | any setup-node spec: `24`, `22`, `lts/*`. Defaults to the **active LTS**; Node 20 is EOL (2026-04-30) |
| `node_cache` | `npm` | `npm`/`yarn`/`pnpm`; empty string disables caching |
| `cache_dependency_path` | `<working_directory>/package-lock.json` | lockfile the cache keys on |
| `cache_node_modules` | `false` | cache the installed tree and **skip the install** on an exact lockfile hit — see [Caching node_modules](#caching-node_modules) before enabling |
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
| `update_badges` | **`true`** | commit Coverage + eslint-disable-count badges into the README on default-branch pushes — see [README badges](#readme-badges). **On by default**; set `false` to opt out. Needs `permissions: contents: write` **in the caller** to push — without it the push warns instead of failing |
| `badge_insert` | `true` | when a README has **no** badges yet, insert them after the first `# ` heading. `false` = only ever refresh badges that already exist, so no repo is committed to unasked |
| `readme_path` | `README.md` | README the badges are written into — **repo-root relative**, *not* `working_directory` relative |
| `badge_branch` | `''` | branch the badge commit is pushed to; empty ⇒ the repository default branch. Point it at a sandbox branch to trial the feature |

## Secrets

| Name | Required | Notes |
|---|---|---|
| `npm_auth_token` | no | token for `npm_registry_url`, exposed to the install step as `NODE_AUTH_TOKEN`. Omit it and CI stays credential-free |

Nothing else — otherwise this is public/read-only CI. (Need a private sibling repo
for specs? Do that checkout in a caller job.)

## Caching node_modules

`node_cache` (on by default) is `setup-node`'s cache: it stores the **npm download
cache** (`~/.npm`), so a run skips the network but npm still unpacks and links the
whole tree every time. For a large app that unpack is most of the install —
`eazyupdates-ui`'s tree is around 1.2 GB.

`cache_node_modules: true` caches `<working_directory>/node_modules` itself and
**skips `install_command` entirely** on an exact hit. That skip is the whole point
(`npm ci` deletes `node_modules` before installing, so caching without skipping buys
nothing) and it is also the whole risk:

- **Lifecycle scripts do not run.** No `postinstall`, no `prisma generate`, no
  `husky install`, no `playwright install`. If your build depends on an artefact one
  of those produces, either leave this off or generate the artefact in its own step.
  A skipped install prints a `::notice::` so this is findable in the log.
- **The key is exact-match only** — no `restore-keys`. A prefix fallback would
  restore a tree built from a *different* lockfile and then skip the install that
  would have reconciled it. A lockfile change is a clean miss, by design.
- **The key includes the Node version `setup-node` resolved**, not the one you asked
  for, so `lts/*` sliding to a new major misses rather than restoring native modules
  built against the old ABI.
- **Only the top-level `node_modules` under `working_directory` is cached.** A
  monorepo with nested `node_modules` (npm workspaces hoisting partially, or
  per-package installs) is not fully covered.

```yaml
    with:
      cache_node_modules: true
```

Measure before and after on your own repo. If the install is already short, the
cache upload/download can cost more than it saves.

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

> **README badges are on by default** (since `v1.21.0`). To let the badge commit
> land, grant `permissions: contents: write` on the job that calls this workflow.
> Without it nothing breaks — the badges are generated and the push degrades to a
> `::warning::`. **No badge failure can fail your run**: a rejected push, a failed
> rebase, a missing `readme_path` — all warn and exit 0. The feature is cosmetic and
> on by default, so it must never gate a build. Set `update_badges: false` to turn it
> off entirely.
>
> This workflow declares **no workflow-level `permissions:`**, so the badge job
> inherits whatever you granted. That is deliberate: a reusable workflow declaring
> more than its caller granted fails the whole run at startup with `startup_failure`
> and no logs, before any job-level `if:` is evaluated — which is what froze one
> caller on `v1.15.0` before `v1.21.0` fixed it.

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-node.yml@v2.4.0
    with:
      node_version: '24'
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
      node_version: '24'
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

If the file is missing, what happens depends on whether you asked for a **gate**:
with `coverage_threshold` non-zero the job fails with an `::error::` naming the
reporter flag to add; with badges only (no gate) it is a `::warning::`, the
coverage badge is omitted and the run passes — badges are on by default, so a
missing report is not the caller's fault. `coverage_summary_path` is relative to
`working_directory` (unlike `readme_path`, which is repo-root relative).

**2. The suppression badge counts `eslint-disable`,** via
`grep -rIE --include='*.{js,jsx,ts,tsx,vue}' --exclude-dir=node_modules` (also
skipping `dist`, `build`, `coverage`) — the ESLint analogue of `ci-go`'s `nolint`
count. It renders as `![eslint-disable count](…)`; the literal `-` is doubled to
`eslint--disable_count` in the shields.io URL because `-` is that API's field
separator.

```yaml
jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-node.yml@v2.4.0
    permissions:
      contents: write        # REQUIRED — caller permissions cap the called workflow
    with:
      update_badges: true
      test_command: 'vitest run --coverage --coverage.reporter=json-summary'
```

## Concurrency

Keyed on `<workflow>-<ref>` with `cancel-in-progress: true`.
