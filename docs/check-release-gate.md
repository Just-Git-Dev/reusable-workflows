# check-release-gate

A **composite action** (not a reusable workflow) that a project's root release workflow calls
once, before it drafts or publishes anything. For each listed service it checks two things:

1. the release **tag still points at the listed commit**, and
2. the **newest `release-gate` check run from GitHub Actions** on that commit finished with
   **success**.

It only reads. It never waits for a run, never starts one and never re-runs one.

```yaml
- uses: Just-Git-Dev/reusable-workflows/actions/check-release-gate@v3.1.0
```

## Why this exists

A multi-repo project releases its services from a root repo: each service repo runs its own
`release-gate` (tests, scans, budgets) on the commit it is about to tag, and the root then
drafts a release that pins those tags. Without a check at the root, nothing stops the root from
drafting a service whose gate was red, never ran, is still running, or whose tag was moved
after the gate passed. The root would ship a commit nobody verified.

Every project needs the same check, and a copy per project drifts. This is the one shared
reader.

## Design

**Read-only, and never waits.** The gate runs in the service repo, *before* the service's
release PR. By the time the root release runs, the verdict is already final. So a run that is
`queued` or `in_progress` is a **failure** ("not finished (never waited on)"), not something to
poll. A poller can hang a release for as long as the slowest gate takes, and it hides a
service that was tagged before its gate finished.

**Only a finished success passes.** Every other outcome fails: no run at all, `neutral`,
`skipped`, `cancelled`, `timed_out`, `action_required`, `failure`, or any status other than
`completed`. Zero services is a failure, never a vacuous pass.

**The newest run from GitHub Actions is the one that counts.**

- *GitHub Actions only* (`app.slug == "github-actions"`): any GitHub App with `checks:write` can
  post a check run with the same name. A green `release-gate` from another app is ignored, so
  the service is reported as having no run.
- *Newest only*: a gate that went red and was then fixed by a re-run is green, and a gate that
  was green and then went red on a re-run is red. Newest is sorted by `started_at`, with ties
  broken by the higher `id`. The order the API lists runs in is not used.

**The tag must still point at the listed commit.** Annotated tags are followed to their
commit, for at most 5 hops. A moved tag fails as `tag moved: points at <sha>`, because a gate
that passed on the old commit says nothing about the new one.

**Every service is reported, then the step fails once.** One red service does not hide a
second one. The log ends with `examined N services, M passed`, and a check that cannot state
how many services it examined is not evidence.

**Fails closed.** Any API error other than a 404 on the tag (for example a 403 or a 500)
fails that service, with the HTTP status named in the reason.

**Why a composite action, not a reusable workflow.** The token that reads the service repos
is minted from a GitHub App key, and that key is a secret scoped to the caller's `release`
environment. A `workflow_call` cannot be handed an environment-scoped secret. A composite
action runs inside the caller's own `environment: release` job, so the caller mints the token
there and passes it in.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `token` | yes | — | A token that can read checks and contents on every listed repo. Use a GitHub App installation token; see [Required permissions](#required-permissions). |
| `services` | yes | — | A JSON array of `{"repo": "owner/name", "tag": "vX.Y.Z", "sha": "<40-hex commit>"}`. |
| `check_name` | no | `release-gate` | The name of the check run that is each service's release gate. Override it only to point a positive-control test at a check that really exists. |

Every entry is validated before the first API call, and any bad entry fails the step:

- `repo` must be `owner/name`.
- `sha` must be a full 40-character lowercase hex commit SHA.
- `tag` must be non-empty and use only `[A-Za-z0-9._/-]`, with no `..`.

Inputs reach the script through `env:` and are never interpolated into it.

## Outputs

| Output | Meaning |
|---|---|
| `result` | A JSON array with one entry per service: `{repo, tag, sha, verdict, reason}`, where `verdict` is `pass` or `fail`. |

A table of the same rows is written to the job summary.

| Reason | Meaning |
|---|---|
| `release-gate succeeded` | pass |
| `tag missing` | The tag does not exist (HTTP 404). |
| `tag moved: points at <sha>` | The tag resolves to a different commit. |
| `no release-gate run` | No run with that name from GitHub Actions on the commit. |
| `not finished: status=<s> (never waited on)` | The newest run is still queued or in progress. |
| `conclusion=<c>` | The newest run finished, but not with `success`. |
| `... failed (HTTP <code>)` | An API error. The step fails closed. |

## Required permissions

The App whose token is passed in needs these **repository** permissions on every listed repo:

- **Checks: read** — to list check runs.
- **Contents: read** — to resolve tags.

Scope the token to the listed repos (`repositories:` on the token mint). The action needs no
`GITHUB_TOKEN` permissions of its own.

## Example caller

```yaml
name: Release
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  gate:
    runs-on: ubuntu-latest
    environment: release
    steps:
      - id: app
        uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0
        with:
          client-id: ${{ vars.RELEASE_APP_CLIENT_ID }}
          private-key: ${{ secrets.RELEASE_APP_KEY }}
          owner: ${{ github.repository_owner }}
          repositories: service-a,service-b
          permission-checks: read
          permission-contents: read

      # Pin the commit SHA of the release tag if your repo SHA-pins every action.
      - uses: Just-Git-Dev/reusable-workflows/actions/check-release-gate@v3.1.0
        with:
          token: ${{ steps.app.outputs.token }}
          services: |
            [
              {"repo": "example-org/service-a", "tag": "v1.4.0", "sha": "0123456789abcdef0123456789abcdef01234567"},
              {"repo": "example-org/service-b", "tag": "v2.0.1", "sha": "89abcdef0123456789abcdef0123456789abcdef"}
            ]
```

In a real caller, `services` is built from the release manifest by an earlier step, not
hard-coded.

## Verification

- `tests/run_check_release_gate_tests.py` runs the shipped `check.sh` against a `gh` stub
  serving fixture JSON. It covers every verdict above, the newest-run rule both ways, the
  other-app rule, annotated and lightweight tags, a moved or missing tag, malformed input, and
  API 5xx errors.
- Before each release, a live positive control runs the script against this repository's own
  tagged commit: a real CI check name must pass, `release-gate` must fail as missing, and a
  wrong SHA must fail as a moved tag. This proves the real API shapes match the fixtures.

## Where not to adopt it

- **A single-repo project.** If the gate and the release run in the same repo, make the release
  job `needs:` the gate job instead.
- **A service whose gate is not a GitHub Actions job named `release-gate`.** A gate run by
  another CI system or another app is ignored by design, so every release would fail as
  `no release-gate run`. Move the gate into GitHub Actions first.
- **A flow that wants to wait for gates.** This action never waits. If the gate is meant to
  run *during* the root release, that is a different design.
