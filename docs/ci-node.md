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
| `runs_on` | `ubuntu-latest` | runner label |
| `working_directory` | `.` | package root (monorepo) |
| `node_version` | `20` | any setup-node spec: `20`, `22`, `lts/*` |
| `node_cache` | `npm` | `npm`/`yarn`/`pnpm`; empty string disables caching |
| `cache_dependency_path` | `<working_directory>/package-lock.json` | lockfile the cache keys on |
| `enable_corepack` | `false` | run `corepack enable` before setup-node (pnpm / modern yarn) |
| `timeout_minutes` | `15` | job timeout |
| `install` / `install_command` | `true` / `npm ci` | dependency install |
| `run_lint` / `lint_command` | `true` / `npm run lint` | lint |
| `lint_blocking` | `true` | `false` = report lint failures without failing the job |
| `run_tests` / `test_command` | `true` / `npm test` | test |
| `enable_services` | `false` | run tests in a `node-db` job with postgres + mysql + redis service containers on localhost (`5432`/`3306`/`6379`) — for DB-backed Node backends |
| `postgres_image` / `postgres_db` / `postgres_password` | `postgres:16` / `test` / `postgres` | postgres service (`enable_services` only) |
| `mysql_image` / `mysql_database` / `mysql_root_password` | `mysql:8` / `test` / `root` | mysql service (`enable_services` only) |
| `redis_image` | `redis:7` | redis service (`enable_services` only) |
| `run_build` / `build_command` | `true` / `npm run build` | build |

No secrets — public/read-only CI. (Need a private sibling repo for specs? Do that
checkout in a caller job; this workflow takes no secrets by design.)

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-node.yml@v1.4.0
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

## Concurrency

Keyed on `<workflow>-<ref>` with `cancel-in-progress: true`.
