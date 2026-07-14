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
| `run_build` / `build_command` | `true` / `npm run build` | build |

No secrets — public/read-only CI. (Need a private sibling repo for specs? Do that
checkout in a caller job; this workflow takes no secrets by design.)

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-node.yml@v1.3.0
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

Monorepo package:

```yaml
    with:
      working_directory: frontend/web
      node_version: '22'
```

## Concurrency

Keyed on `<workflow>-<ref>` with `cancel-in-progress: true`.
