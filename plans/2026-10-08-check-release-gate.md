# Plan — `check-release-gate` composite action (reusable-workflows v3.1.0)

> Approved 2026-10-08. This is the public copy: consumers are pseudonymised (consumer A, B, C)
> and private planning references are dropped, per DECISIONS.md 2026-10-04.

## Decision summary (one screen)
- **What:** a composite action at `actions/check-release-gate/`. A project's root release
  workflow calls it once. For each listed service it confirms two things:
  - the tag still points at the listed commit, and
  - the newest `release-gate` check from GitHub Actions on that commit finished with **success**.
- **Why:** the owner ruled that each service's release gate runs before its release PR, and the
  root release only reads the finished verdict. One shared reader replaces a copy per project.
  The owner chose a composite action over a reusable workflow (2026-10-08). That keeps the App
  key in the caller's own `release`-environment job, because a reusable workflow cannot be
  handed a secret scoped to an environment.
- **Read-only, never waits:** it never waits for, starts, or re-runs a run. Anything queued, in
  progress, missing, neutral, skipped or red fails. It reports EVERY service, then fails once.
- **Release:** v3.1.0, since adding something is a minor bump. The tag is cut only after the
  owner asks for it explicitly.

## Context
A multi-repo project's root release flow must refuse to draft or publish a service whose own
Release gate did not pass on the exact tagged commit. Consumers adopt it in order: consumer A
first, then B, then C. Public-repo rule: the docs and code name no consumer, and the diff and
PR text are grepped for consumer names before pushing.

## Contract
The caller job has `environment: release`. It mints the App token with
`actions/create-github-app-token` (`permission-checks: read`, `permission-contents: read`,
repositories scoped to the listed ones). Then it calls
`uses: Just-Git-Dev/reusable-workflows/actions/check-release-gate@<40-hex sha> # v3.1.0`.

| input | required | default | meaning |
|---|---|---|---|
| `token` | yes | — | a token that can read checks + contents on every listed repo |
| `services` | yes | — | JSON array of `{repo: "owner/name", tag: "vX.Y.Z", sha: "<40-hex>"}` |
| `check_name` | no | `release-gate` | the fleet's gate name; exists so positive-control tests can point at a real check |

Output `result`: JSON `[{repo, tag, sha, verdict, reason}]`. A markdown table is written to
`$GITHUB_STEP_SUMMARY`.

## Logic (`actions/check-release-gate/check.sh`, bash + `gh api` + `jq`)
1. Validate `services` before any API call:
   - it is a non-empty array;
   - each `repo` matches `^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$`;
   - each `sha` is 40-hex;
   - each `tag` is non-empty.

   Zero services is a failure, never a pass.
2. For each service, collect a verdict, and do not stop at the first failure:
   - **Tag:** `GET repos/{repo}/git/ref/tags/{tag}`.
     - Peel an annotated tag through `git/tags/{sha}`, at most 5 hops.
     - 404 → "tag missing".
     - A different commit → "tag moved: points at X".
   - **Gate:** `GET repos/{repo}/commits/{sha}/check-runs?check_name=<name>&filter=all&per_page=100`.
     Keep only runs with `app.slug == "github-actions"`. Take the newest by `started_at`, with
     ties broken on `id`.
     - No run → "no release-gate run".
     - `status != completed` → "not finished (never waited on)".
     - `conclusion != success` → "conclusion=X".
   - Any other API error fails closed, naming the service and the HTTP status.
3. Print "examined N services, M passed". Write the summary and the `result` output. Exit 1 if
   M < N.

`action.yml` is `runs.using: composite`, with one `shell: bash` step running
`"$GITHUB_ACTION_PATH/check.sh"`. Inputs go through `env:` only, never interpolated into the
script.

## Steps (Design → Doc → Test red → Implement → Release)
1. **Docs:**
   - `docs/check-release-gate.md`;
   - a README catalog row in a new "Release" subsection;
   - a dated `DECISIONS.md` entry and Index line.
2. **CI coverage for the repo's first `actions/` directory.** Each extension gets a
   planted-failure proof.
   - `check_docs_coverage.py` covers actions.
   - `gen_catalog.py` includes actions.
   - The `pinned-actions` grep scans `actions/`.
   - `shellcheck` runs over `actions/**/*.sh`.
   - `stamp_version.py`: decide whether actions carry a stamp, and extend `--check` rather than
     silently skipping them.
3. **Tests (red first):** `tests/run_check_release_gate_tests.py` runs `check.sh` against a `gh`
   stub that serves fixture JSON. It covers:
   - all pass;
   - one red, with the others still reported;
   - missing, queued/in_progress, neutral/skipped;
   - newest-run ordering, both ways;
   - other-app ignored;
   - annotated and lightweight tags, tag moved, tag missing;
   - empty, malformed or bad-sha input;
   - API 500 failing closed;
   - the count line.

   Confirm red against an exit-0 stub.
4. **Implement** until green. Run actionlint, shellcheck, every CI script, and the step tests
   locally.
5. **Ship:** a PR, with the consumer-name grep over the diff and the PR text. Merging is the
   owner's approval.
6. **Release (only on the owner's explicit ask):** `stamp_version.py v3.1.0` in a PR, then
   `gh workflow run release.yml -f version=v3.1.0`. Verify with `git ls-remote --tags`.

## Verification
- The unit cases, green in CI. Each CI extension shown failing on a planted violation.
- **Live positive control (read-only) before release**, against this repo's own `v3.0.0` tag:
  - a real CI job name → pass;
  - `release-gate` → missing;
  - a wrong sha → tag moved.
- **End to end:** consumer A's first release run, where a known-red or ungated service must
  block the drafts.

## Out of scope / follow-ups
- A promote-image `skip_existing_tag` input. It depends on whether re-adding an existing
  immutable GAR tag fails, and is a separate minor release.
- Per-service performance baselines (still open with the owner).
