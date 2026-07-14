# ci-go

The Go toolchain core every repo copy-pastes: `go build` · `go vet` · `go test`
· `golangci-lint`, with module/build caching keyed on `go.sum`. Each step is
individually toggleable, so a monorepo module, a lint-only gate, or a repo whose
tests need an external DB all fit without forking the workflow.

**What stays in the caller.** Repo-specific gates — guard scripts (ADR/REQ
checks), ephemeral-DB migration smokes, `GOPROXY=direct` VCS-fallback docker
builds — belong in their own jobs in the caller. This workflow deliberately owns
only the universal core so it stays adoptable everywhere.

## Inputs

| Name | Default | Notes |
|---|---|---|
| `runs_on` | `ubuntu-latest` | runner label |
| `working_directory` | `.` | module root (monorepo) |
| `go_version` | `''` | explicit version (e.g. `1.25`); empty ⇒ derive from `go_version_file` |
| `go_version_file` | `go.mod` | repo-root-relative `go.mod` to read the version from |
| `timeout_minutes` | `15` | job timeout |
| `run_build` / `build_packages` | `true` / `./...` | `go build` |
| `run_vet` | `true` | `go vet ./...` |
| `run_tests` / `test_args` | `true` / `-race -count=1 ./...` | `go test`; set `run_tests: false` when the suite needs a DB/stack the caller stands up itself |
| `run_lint` | `true` | golangci-lint via `golangci-lint-action` |
| `golangci_version` | `latest` | e.g. `v2.5` (v8 action ⇒ golangci-lint v2 config) |
| `golangci_args` | `--timeout=5m` | passed to golangci-lint |
| `lint_blocking` | `true` | `false` = report lint failures without failing the job (paydown mode) |

No secrets — public/read-only CI.

## Example caller

```yaml
name: CI
on:
  push:
    branches: ['**']
    tags-ignore: ['v*.*.*']
  pull_request:

permissions:
  contents: read

jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v1.3.0
    with:
      go_version_file: go.mod
      test_args: '-race -count=1 ./...'
      golangci_version: v2.5
```

DB-backed suite — keep build+vet+lint here, run the DB tests in your own job:

```yaml
jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v1.3.0
    with:
      run_tests: false          # unit-with-DB handled below
  integration:
    runs-on: ubuntu-latest
    services:
      postgres: { image: postgres:16-alpine, ... }
    steps: [ ... your migration smoke / integration suite ... ]
```

Monorepo module:

```yaml
    with:
      working_directory: services/api
      go_version_file: services/api/go.mod
```

## Concurrency

Keyed on `<workflow>-<ref>` with `cancel-in-progress: true`.
