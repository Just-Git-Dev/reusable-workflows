# Release fast-track: three shared fixes in reusable-workflows

## Decision summary (one screen)
| # | fix | where | version |
|---|---|---|---|
| F1 | Publish polling survives GitHub 5xx and network errors (retry inside the existing deadline) | `actions/release-flow` CLI `publish.py` / `gh.py` | patch-level behaviour, ships in v6.1.0 |
| F2 | `ci-verdict` action: a service gate asks "did CI already pass for this exact code?" and skips the suites CI ran | new `actions/ci-verdict` (reuses CLI `ci.py`) | v6.1.0 (additive) |
| F3 | Auto-open the root release PR once a service gate is green | RECOMMENDED: local CLI command `release-flow propose`, 0 Actions minutes (Q1) | v6.1.0 (additive) |
Semver: all additive, so the input contract is unchanged → **v6.1.0**. Consumers re-pin when ready.

## Context
The 2026-11-03 review of consumers A, B and C (evidence: private review notes)
found three release slow-downs that every project shares:
- **The human gap.** After a green gate, someone hand-writes the manifest and opens the root PR:
  1-49 min in consumer B, often overnight (10-16 h) in consumer A. Five consumer-B failures came from ordering
  slips: dispatching before the tag existed, or a dotted manifest filename.
- **Re-testing.** Every gate re-runs unit/race/lint that CI already passed on the same code:
  about 100-340 billed min/mo per project, and 4-6 min of gate wall time.
- **One 504 burns a version.** A consumer-B run: `_wait_run` (publish.py) called
  `reader.get_ok` on the deploy-runs list, got HTTP 504, raised, and the release stopped after
  the api was already live. A re-run never publishes, by design, so it needed a new release PR.
(The billing blocks are an owner/org action, outside this plan.)

## Owner answers (2026-11-03)
- **A1.** The release PR is opened by a local command, `release-flow propose`, which the project's
  own session runs after the tag push. No scheduled workflow, and the service repo never triggers
  the root.
- **A2.** `propose` turns on GitHub auto-merge, so the release PR merges by itself once its
  required check (`release-pr-check`) is green. Consequences written into the spec:
  (a) the root repo must make `release-pr-check` a **required** status check and allow auto-merge.
  If it doesn't, `gh pr merge --auto` would merge at once, untested, so `propose` refuses to
  enable auto-merge unless it reads the branch protection back and finds the check required.
  (b) Auto-merge adds no new risk for breaking changes. Without the label and block, plan fails
  before drafts, so nothing is written and the same tags can be released again through a
  corrected PR (release-flow.md, §Contract checks).
  (c) Under auto mode `gh pr merge` may be denied; then `propose` prints the exact `!` command.
- **A3.** Code counts as already tested when a green CI run exists for the same commit, or for a
  PR head whose git tree is identical to the tag commit's tree. Any other case runs the full suite.
- **A4.** Only the steps a project marks as duplicates of CI may be skipped. Integration tests on
  the built image always run.

## Open questions (as asked; answers above)
1. **F3, where the release PR is opened.** A service repo may not trigger the root repo (global
   rule "Repo Awareness"), so the options are:
   A. *(recommended)* A local command, `release-flow propose <repo>@<tag> ...`, run by the
      project's session right after the tag push. It waits for the gate (`gh run watch` style,
      polling read-only), checks the same things the PR check does (one manifest, filename with no
      dots, annotated tag, changelog heading), writes the manifest and opens the root PR.
      0 Actions minutes.
   B. A scheduled root workflow that finds green gates and opens the PR. Every 15 min that is
      about 2,900 billed min/mo, which is more than it saves.
2. **F3, merge.** Should `propose` also turn on GitHub auto-merge, so the PR merges as soon as
   `release-pr-check` is green? Today your merge is the approval, and the merge guard relies on
   it being a real merged PR (auto-merge still is one). Recommended: **no auto-merge**; keep the
   merge as your one click.
3. **F2, what counts as "already tested".** Consumers A and C run CI on push to main, so the tag
   sha has its own CI run. Consumer B's api CI is PR-only by design, so the tag sha never has one.
   Recommended rule: reuse when a green CI run exists for the **same sha**, or for a PR head whose
   **git tree equals the tag commit's tree** (true when the PR was up to date with main when
   merged). Otherwise run the full suite (fail safe: a miss costs minutes, never a wrong verdict).
4. **F2, what may be skipped.** Recommended: only the steps the project marks as duplicates of CI
   (`if: steps.verdict.outputs.reuse != 'true'`). Integration-on-the-built-image never skips; it is
   the gate's real job.

F1 needs no question: retry only idempotent GETs, only on 5xx or a network error, sleeping
`POLL_S` between tries, inside the existing `DEPLOY_TIMEOUT_S`; writes (publish PATCH, rerun)
never retry; 5 consecutive errors stop the publish as today.

## Plan (after answers)
Order per Development Workflow: spec/doc → red tests → implement → release.

### Wave 1 — docs (spec first), one agent per file
- `docs/release-flow.md` §Stages 4 + §Safety properties: the GET-retry rule (F1); new section
  "Proposing a release" (F3) with the command, its checks, and the UX: what it prints while waiting,
  and on gate red/timeout/PR opened.
- New `docs/ci-verdict.md` (F2): inputs (`repo`, `sha`, `workflows`, `match: sha|tree`), outputs
  (`reuse`, `run_url`, `why`), the fail-safe rule, caller example; add to README catalog +
  `catalog.json`.
- `DECISIONS.md` entry (the WHY of all three, incl. why F3 is local, not a workflow).

### Wave 2 — red tests (builder, confirm failing)
- `test_publish.py`: fake_github returns 504 then 200 on the runs list → publish succeeds; 5×504 →
  stops with the HTTP status in the message; a PATCH 502 is NOT retried.
- `test_ci.py` (or new `test_verdict_reuse.py`): same-sha green → reuse; tree-equal PR head green →
  reuse; tree differs / red / missing / API error → no reuse with a reason.
- `test_propose.py`: dotted filename refused; tag not annotated refused; gate red → no PR; happy path
  writes exactly one manifest and calls create-PR once.

### Wave 3 — implement (builder), files partitioned
- A: `releaseflow/publish.py` (+ `gh.py` helper) for F1.
- B: `releaseflow/ci.py` + `release_flow.py` subcommand `ci-verdict` + `actions/ci-verdict/action.yml`.
- C: `releaseflow/propose.py` + `release_flow.py` subcommand `propose` (B and C both touch
  `release_flow.py` → C runs after B, or B owns that file and C hands its parser block over).

### Wave 4 — gates and release
`make` test target, `actionlint`, SHA-pin check, critic review of the diff, PR, owner merges,
cut v6.1.0 only on your explicit ask. Then send each project the pin and its adoption steps
(consumer B item 2 is on HOLD for F2).

## Verification
- Unit suites green, each new test was seen red first.
- F1: rehearsal run in a consumer is the project's job; here, the fake-GitHub 504 test.
- F2/F3: run `release-flow ci-verdict` and `propose --dry-run` read-only against a real public
  repo sha, and check the printed verdict by hand.

## Checklist
- [x] Q1-Q4 answered and written back (2026-11-03)
- [x] docs + DECISIONS (2026-11-03, efb89a2)
- [x] red tests seen failing (each builder report; mutation checks on review fixes)
- [x] F1 / F2 / F3 implemented, suites green (make ci 29/29, 582 tests)
- [x] PR merged (owner) — PR #179 merged 2026-11-03; v6.1.0 released
- [x] pins + adoption steps sent to consumers A, B, C (2026-11-03)
