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
| `runs_on` | `ubuntu-latest` | runner label. **Self-hosted must be on Actions Runner ≥ v2.327.1** — `setup-go` v7 runs on Node 24. GitHub-hosted runners already satisfy this. |
| `working_directory` | `.` | module root (monorepo) |
| `go_version` | `''` | explicit version (e.g. `1.25`); empty ⇒ derive from `go_version_file` |
| `go_version_file` | `go.mod` | repo-root-relative `go.mod` to read the version from |
| `timeout_minutes` | `15` | job timeout |
| `run_build` / `build_packages` | `true` / `./...` | `go build` |
| `run_vet` | `true` | `go vet ./...` |
| `run_tests` / `test_args` | `true` / `-race -count=1 ./...` | `go test`; set `run_tests: false` when the suite needs a DB/stack the caller stands up itself |
| `coverage_threshold` | `0` | when non-zero, tests run with `-coverprofile` and the job **fails** below this total statement-coverage percent. Measuring is decoupled from gating: `update_badges: true` also turns `-coverprofile` on, with no gate |
| `enable_services` | `false` | run tests in a `go-db` job with postgres + mysql + redis service containers on localhost (`5432`/`3306`/`6379`) |
| `postgres_image` / `postgres_db` / `postgres_password` | `postgres:16` / `test` / `postgres` | postgres service (`enable_services` only) |
| `mysql_image` / `mysql_database` / `mysql_root_password` | `mysql:8` / `test` / `root` | mysql service (`enable_services` only) |
| `redis_image` | `redis:7` | redis service (`enable_services` only) |
| `run_lint` | `true` | golangci-lint via `golangci-lint-action` |
| `golangci_version` | `latest` | linter version — tracks latest by default, override e.g. `v2.5` (v9 action ⇒ golangci-lint v2 config) |
| `golangci_args` | `--timeout=5m` | passed to golangci-lint |
| `lint_blocking` | `true` | `false` = report lint failures without failing the job (paydown mode) |
| `go_private` | `''` | GOPRIVATE glob (e.g. `github.com/zopsmart/*`); when set, git fetches private modules over HTTPS using the `go_private_token` **secret** (required then) |
| `update_badges` | **`true`** | commit Coverage + nolint-count badges into the README on default-branch pushes — see [README badges](#readme-badges). **On by default**; set `false` to opt out. Needs `permissions: contents: write` **in the caller** to push — without it the push warns instead of failing |
| `badge_insert` | `true` | when a README has **no** badges yet, insert them after the first `# ` heading. `false` = only ever refresh badges that already exist, so no repo is committed to unasked |
| `readme_path` | `README.md` | README the badges are written into — **repo-root relative**, *not* `working_directory` relative |
| `badge_branch` | `''` | branch the badge commit is pushed to; empty ⇒ the repository default branch. Point it at a sandbox branch to trial the feature |

**Secrets:** only `go_private_token` — a PAT/token for fetching private Go modules,
required when `go_private` is set (otherwise none; public CI needs no secrets). It is
**not** named `github_token`: GitHub reserves `github_token`/`GITHUB_TOKEN` as a
`workflow_call` secret name and rejects the workflow at parse time
("would collide with system reserved name"). Pass it from the caller as
`secrets: { go_private_token: ${{ secrets.GITHUB_TOKEN }} }` (or a PAT with cross-repo
read).

**Service containers are language-agnostic** — the same `enable_services` inputs
exist on [`ci-node`](ci-node.md). When `enable_services: true`, all three
containers start (GitHub cannot attach a service conditionally); a suite connects
to whichever it needs. `build`/`vet`/`lint` stay in the `go` job; tests move to
the `go-db` job.

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v2.1.2
    with:
      go_version_file: go.mod
      test_args: '-race -count=1 ./...'
      golangci_version: v2.5
```

DB-backed suite — inline service containers + a coverage gate:

```yaml
jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v2.1.2
    with:
      enable_services: true     # postgres + mysql + redis on localhost
      coverage_threshold: 50    # fail under 50% total coverage
      test_args: '-race -count=1 ./...'
```

Prefer to stand the stack up yourself? Keep build+vet+lint here and run the DB
tests in your own job instead:

```yaml
jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v2.1.2
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

## README badges

`zopsmart/workflows` test-and-lint kept two shields.io badges *baked into the
committed README* — a coverage percentage and a `nolint` count — by rewriting the
file and pushing the change back on every `main` build. `update_badges: true`
reproduces that, so a repo migrating off the legacy workflow keeps a
self-updating README:

```markdown
![Coverage](https://img.shields.io/badge/Coverage-90.8%25-brightgreen) ![nolint count](https://img.shields.io/badge/nolint_count-7-orange)
```

A third `badges` job runs **only** when all of these hold: `update_badges: true`,
the event is a `push`, the test job succeeded, and `github.ref_name` equals
`badge_branch` (or the repository default branch when it is empty). It is the only
job that gets `contents: write`; build/test/lint stay `contents: read`.

An existing badge is matched on its alt text (`![Coverage](…)`,
`![nolint count](…)`) and **replaced in place**, so a legacy zopsmart badge line
is updated rather than duplicated; if neither is present the badges are inserted
after the first `# ` heading — set `badge_insert: false` to refresh only, never
insert, so a repo that never asked for badges is not committed to. When nothing
changes, no commit is made — re-running is a no-op.

**No badge failure can fail your run.** A rejected push, a failed rebase, a missing
`readme_path` — all warn and exit 0. The feature is cosmetic and on by default, so it
runs for callers that never asked for it and must never gate their build. Set
`update_badges: false` to turn it off entirely.

The coverage colour ramp is ≥90 `brightgreen`, ≥80 `green`, ≥70 `yellowgreen`,
≥60 `yellow`, ≥50 `orange`, else `red`. The suppression badge is `brightgreen` at
zero and `orange` otherwise.

**Two caller-side requirements — both are easy to miss:**

```yaml
jobs:
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v2.1.2
    permissions:
      contents: write        # REQUIRED — a reusable workflow's permissions are
                             # capped by the caller; without this the push fails
    with:
      update_badges: true
      # badge_branch: badges-trial   # trial it off the default branch first
```

1. **`permissions: contents: write` on the calling job.** A called workflow can
   never hold a permission the caller did not grant, so the `badges` job's own
   `contents: write` is not enough on its own. This is why the feature is
   default-off — every other caller keeps a read-only token.
2. **Branch protection on the default branch will reject the push.** This is the
   honest limitation of commit-back: if `main` requires PRs or status checks, the
   `badges` job fails at `git push`. The two escapes are to exempt the GitHub
   Actions app from the protection rule, or to leave `update_badges: false` and
   read the coverage number off the `::notice::total coverage …%` annotation that
   is emitted regardless.

**Deliberate differences from the legacy implementation.** The nolint count is
taken with `grep -rIE --include='*.go' --exclude-dir=vendor` over
`working_directory`; legacy ran `grep -r -E '//\s*nolint' .`, which also counted
`.git/`, `vendor/` and binary files. **Expect a lower number than legacy reported
for the same repo — that is the bug being fixed, not a regression.** Legacy also
shelled out to `gobadge@latest` and `ad-m/github-push-action`; this uses inline
`sed` and a plain `git push`, adding no unpinned third-party dependency to a job
that holds a write token. See `DECISIONS.md` (2026-07-27).

## Concurrency

Keyed on `<workflow>-<ref>` with `cancel-in-progress: true`.
