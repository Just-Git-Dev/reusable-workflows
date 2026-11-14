# ci-verdict

A **composite action** that a service repo's `release-gate` workflow calls first. It answers
one question: **"did CI already pass for this exact code?"** When the answer is yes, the gate
skips the steps that only repeat CI (unit tests, race, lint) and runs only what is its own
job (integration tests on the built image, scans, budgets).

```yaml
- id: verdict
  uses: Just-Git-Dev/reusable-workflows/actions/ci-verdict@v6.3.0
  with:
    workflows: ci.yml
- name: Unit tests (skipped when CI already passed on this code)
  if: steps.verdict.outputs.reuse != 'true'
  run: make test
```

It only reads. It never waits for a run, never starts one and never re-runs one.

## Why this exists

The 2026-11-03 release review of three projects found that every `release-gate` re-ran unit,
race and lint suites that CI had already passed on the same code: about 100-340 billed minutes
a month per project, and 4-6 minutes of gate wall time per release. The gate cannot simply drop
those steps, because nothing proves CI ran on the code being tagged. This action is that proof,
and when the proof is missing the gate runs everything, as before.

## The rule

The code at `sha` counts as **already tested** only when, for **every** workflow listed in
`workflows`, one of these holds:

1. **Same commit.** The newest run of that workflow whose `head_sha` is `sha` finished with
   `success`. (A repo that runs CI on push to `main` has this for a tag on a `main` commit.)
2. **Same tree** (only with `match: tree`, the default). A pull request associated with `sha`
   (GitHub's `commits/{sha}/pulls`) has a head commit whose **git tree is identical** to the
   tree of `sha`, and the newest run of that workflow on that head commit finished with
   `success`. (A repo whose CI runs on pull requests only never has a run on the tag commit
   itself. When the PR was up to date with `main` at merge, the squash or merge commit has the
   same tree as the PR head, which is the code CI tested.)

**Only runs whose event tests the commit they name count:** `push`, `pull_request` and
`merge_group`. A run from any other event is ignored, as if it did not exist. For example, a
`pull_request_target` run's `head_sha` is the base-branch tip while its job usually checks out
the PR head, and a `workflow_dispatch` run may check out whatever its inputs say, so a green
run of either says nothing certain about the code at its `head_sha`. (H8's *ci-green* reads
only `push` runs because it needs the run of the tagged commit on `main`; ci-verdict also needs
PR runs, for rule 2.)

A pull request whose `head` is missing or malformed in the API response is skipped with a
reason; it never fails the step.

**A red run at the sha itself is final.** When the newest run of a workflow on `sha` has
finished with anything but `success`, rule 2 is not tried for that workflow: the exact code
failed CI, and a green run on a tree-equal PR head does not override that. A run on `sha` that
has not finished yet does not block rule 2.

The tree is compared by its git object id: identical ids mean identical files, byte for byte.
Commit message, author and parents may differ; content may not.

**Newest run only.** Of the runs on one commit, the most recently created one decides. A run
that went red and was then re-run green counts as green; one that was green and then re-ran red
counts as red. A run still queued or in progress is **not** a pass: the action never waits.

**Fail safe.** Every other case is "not already tested", and the gate runs its full suite:
no run, a red or cancelled run, a run not finished, a tree that differs, more than one
candidate PR none of which qualifies, an API error of any kind (403, 404, 5xx, network), a bad
input. A miss costs a few minutes of CI; a wrong "yes" would ship untested code, so the action
is built never to say yes by accident. It does not fail the step for these: `reuse` is
`false` and `why` names the reason. The step fails (exit 2) only on a usage error, such as an
empty `workflows` list or a `sha` that is not 40 lowercase hex.

**Only what the project marks may be skipped.** The action decides nothing about the gate's
steps. The caller puts `if: steps.verdict.outputs.reuse != 'true'` on each step that duplicates
CI, and on nothing else. Integration tests on the built image always run: they are the gate's
real job and CI never ran them on that image.

## Inputs

| input | required | default | meaning |
|---|---|---|---|
| `workflows` | yes | — | Comma-separated CI workflow file names in this repo, e.g. `ci.yml` or `ci.yml,lint.yml`. Every one must qualify. Empty is a usage error. |
| `sha` | no | `github.sha` | The commit the gate is testing (the tag's commit). 40 lowercase hex. |
| `repo` | no | `github.repository` | `owner/name` of the repo whose CI is read. |
| `match` | no | `tree` | `sha`: only rule 1. `tree`: rule 1, else rule 2. |
| `token` | no | `github.token` | A token that can read actions, contents and pull requests on `repo`. The default `GITHUB_TOKEN` works when the job grants `actions: read`, `contents: read`, `pull-requests: read`. |

## Outputs

| output | meaning |
|---|---|
| `reuse` | `true` when the code at `sha` is already tested under the rule above, else `false`. Never empty. |
| `run_url` | The green run(s) that justify `reuse=true`, space-separated, one per workflow. Empty when `reuse` is `false`. |
| `why` | One line: which rule matched for each workflow (`ci.yml: same sha, run <url>` / `ci.yml: PR #12 head 1a2b3c4d has the same tree, run <url>`), or the first reason it did not. |

The step log ends with `examined N workflow(s): reuse=<true|false>`. A verdict that cannot say
how many workflows it examined is not evidence.

## Caller example

```yaml
# .github/workflows/release-gate.yml in a service repo
on:
  push:
    tags: ["v*.*.*"]
permissions:
  actions: read
  contents: read
  pull-requests: read
jobs:
  release-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha> # vX
      - id: verdict
        uses: Just-Git-Dev/reusable-workflows/actions/ci-verdict@v6.3.0
        with:
          workflows: ci.yml
      - run: echo "CI reuse - ${VERDICT_WHY}"
        shell: bash
        env:
          VERDICT_WHY: ${{ steps.verdict.outputs.why }}
      - name: Unit + race + lint (duplicates CI)
        if: steps.verdict.outputs.reuse != 'true'
        shell: bash
        run: make test lint
      - name: Build the image and run integration tests on it (never skipped)
        shell: bash
        run: make image integration
```

## CLI

The action runs `release-flow ci-verdict` from the sibling [`release-flow`](release-flow.md)
action, so it can be run by hand, read-only, against any repo the token can read:

```bash
RELEASE_FLOW_READ_TOKEN=$(gh auth token) \
  actions/release-flow/release-flow ci-verdict --repo owner/name --sha <40hex> \
  --workflows ci.yml [--match sha|tree] [--github-output FILE]
```

It prints one compact JSON line `{"reuse", "run_url", "why", "examined"}` and exits 0 whether
or not the code is reused (2 on a usage error). With `--github-output` it also appends
`reuse=`, `run_url=` and `why=` lines to that file.

## Testing

`actions/release-flow/releaseflow/test_ci_verdict.py`, against the in-memory fake GitHub: same
sha green, tree-equal PR head green, tree differs, red, in progress, no run, re-run newest wins,
API error, two workflows of which one misses.
