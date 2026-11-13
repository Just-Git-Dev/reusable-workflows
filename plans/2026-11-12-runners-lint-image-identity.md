# Plan: runner-label lint + shared image-identity action (fleet fixes 3 + 4)

## Decision summary (one screen)
- **Why:** GitHub's `ubuntu-latest` now resolves to ubuntu-26.04. That burned two of a consumer's release pairs on 2026-11-11 (Playwright refuses 26.04; docker `.Id` means a different thing on 26.04 than on 24.04). Two other consumers carry the same patterns. The rule is already written in the fleet's github-actions guidance (§3c).
- **Owner rulings (2026-11-12):**
  1. The lint ships **report-only** (findings print as WARN, exit unchanged). It becomes failing in a later release, after the three projects have pinned their runners.
  2. The image check becomes **one composite action with two modes**, `record` and `verify`, at `reusable-workflows/actions/image-identity`.
- **Two independent units, one wave, disjoint files:**
  - **U1** is a new `runners` subcommand in the canonical workflow-preflight (claude-config `skills/workflow-preflight/`).
  - **U2** is the new `actions/image-identity` in reusable-workflows, released as **v6.2.0** (a minor: new action, no input contract changed).
- **Devops does:** build, test, re-vendor into our own two repos (reusable-workflows, infra-provisioning), release.
- **Projects do:** adopt it themselves. Each project re-vendors, runs `runners`, pins, and swaps its `.Id` check for the action; devops sends each one the steps. No edits in project repos from here.

## Checklist ("done" = ticked with evidence)
- [x] 1. U1 docs: SKILL.md gains a `## \`runners\`` section with a code table, plus the `runners` key in the config key table. Evidence: claude-config SKILL.md `## \`runners\`` (one heading).
- [x] 2. U1 red tests: written and confirmed failing. Evidence: 25 of 29 new tests failed with `invalid choice: 'runners'` (claude-config DECISIONS 5ed7f93; code fce70e6).
- [x] 3. U1 implementation: the suite is green (174 existing tests plus the new ones), and a mutation check shows each new code is killed by a test. Evidence: 203 tests OK, re-run 2026-11-12; mutation result in claude-config DECISIONS (5ed7f93).
- [x] 4. U2 docs: `docs/image-identity.md`, including an example the `doc-examples` CI job extracts; a README catalog line. Evidence: #181 (f23657a), `doc examples are valid workflows` green.
- [x] 5. U2 red tests: written and confirmed failing. Evidence: written before identity.py in the same unit; the red run itself is not recorded in a durable file.
- [x] 6. U2 implementation: `make ci` is green, plus actionlint and pinned-actions. Evidence: #181 18/18 checks green; `tests/test_image_identity.py` 20 tests OK; cross-store CI run 43184510752.
- [x] 7. Re-vendor workflow-preflight into reusable-workflows and infra-provisioning (both are on the stale 7be1b9f). Run `runners` on both and record what it finds. Evidence: #181 and infra-provisioning #133 (cf0f664); `runners` on main 2026-11-12: this repo 79 jobs in 47 workflows, 0 findings; infra-provisioning 12 jobs in 8 workflows, 0 findings. This repo's only save/load pair (ci.yml) uses the action, so its 0 is the blind kind described in docs/image-identity.md.
- [x] 8. DECISIONS entries: the claude-config `DECISIONS.md` for U1; reusable-workflows `DECISIONS.md` for U2. Evidence: claude-config 5ed7f93 (the code is fce70e6); this repo's entry "image-identity action: prove same image bytes by tarball hash" (#181).
- [x] 9. reusable-workflows PR: owner merges, stamp v6.2.0, owner dispatches the release. Tick the stale :111/:112 boxes of plans/2026-11-03-release-fast-track.md in the same PR. Evidence: #181 merged (f23657a, both boxes ticked there); stamp #182 merged (a482997); release.yml run 43206206958 tagged v6.2.0 → a482997, Release published 2026-11-12.
- [ ] 10. Adoption steps sent to consumers A, B and C; each project confirms back. Status 2026-11-12: steps sent; all three confirmed adoption (per their own reports, not checked from here) (lint re-vendored, each lint caught the old pattern on the pre-fix workflow and reports 0 on the new one, `.Id` compare replaced by this action). Open: one green release or rehearsal run id from each, which each consumer sends after its next release.

## U1: `workflow_preflight.py runners`
Structural parse, reusing the existing helpers: `parse_workflow_text` :197, `steps_of` :228, `step_strings` :241, `job_strings` :1309, `needs_of`/`reaches` :1336/1341. `runs-on` is read from `job["runs-on"]`.

| Code | Fires when |
|---|---|
| `LATEST_PLAYWRIGHT` | A job on `ubuntu-latest` (or on `runs-on` left unset) whose strings or `uses:` mention playwright (install, test, or the action). |
| `LATEST_IMAGE_IO` | A job on `ubuntu-latest` that runs `docker save`, `docker load` or `docker image inspect`. |
| `RUNNER_SPLIT` | Within one workflow, a job that runs `docker save` and a job that `docker load`s it (linked by `needs`) have different `runs-on` values. |
| `ID_COMPARE` | A job reads `{{.Id}}` after a `docker load` in the same job. |
| `UNRESOLVED` | `runs-on` is an expression (`${{ … }}`) on a job that matches any rule above. Reported as a WARN only, never a pass. |

- Config: `"runners": {"enforce": false, "waivers": [{"job": "<wf>:<job>", "code": "…", "reason": "≥20 chars"}]}`. `enforce` defaults to false, so the subcommand is report-only, following the pattern of `triggers` :1418. `runners` is added to `TOP_KEYS` :40.
- The summary line states how many jobs were examined. Zero examined exits 2, as every other subcommand does.
- Red tests: include a fixture where a THIRD job also loads the tarball and compares `.Id`. One consumer's release-gate `push` job does this, and my first scan missed it, so `RUNNER_SPLIT` must check every loader, not just the first. Also a fixture workflow per code, plus negatives (`ubuntu-24.04` on both sides; a job that runs playwright with no docker; a waiver with a short reason → `WAIVER_INVALID`). An enforce-on test checks exit 1; an enforce-off test checks a WARN with exit 0.
- **Prior art to reuse:** A consumer's own `scripts/check-runner-labels.py` (8 tests). It flags Playwright on a `*-latest` label, and 2+ image/Playwright jobs in one workflow that don't share one explicit label. It allows a lone pull-and-run job. Its fixture cases go into U1's red tests, read-only from that consumer's tree. Once `runners` ships, that consumer drops its guard.
- Files: `scripts/workflow_preflight.py`, `scripts/test_workflow_preflight.py`, `SKILL.md`.

## U2: `actions/image-identity` (reusable-workflows)
- **`mode: record`** runs in the job that pulled the images. Inputs: `images` (newline list of refs), `path` (tarball path). Steps:
  1. `docker save` all refs into one tarball and take its `sha256sum`.
  2. Read **each ref's config digest from the tarball's own `manifest.json`**. That handles both layouts: classic `"Config": "<hex>.json"`, and containerd/OCI `"Config": "blobs/sha256/<hex>"`.
  3. Record `RepoDigests[0]` per ref, for tracing only.
  4. Outputs: `tar_sha256`, plus `identity` (JSON {ref: {config, repo_digest}}). The JSON is also written next to the tarball.
- **`mode: verify`** runs in the consuming job after the artifact is downloaded. Inputs: `path`, `tar_sha256`, `identity`. Steps:
  1. Re-hash the tarball; it must equal `tar_sha256`. That proves the bytes are identical, which is the check's whole job: "smoke tests exactly what the images job pulled".
  2. `docker load`, then confirm every ref in `identity` is present. The config digests are printed for the run summary, not compared again, because a matching hash already implies them.
  - **`docker image inspect .Id` is never used.**
- **Fail closed:** any empty value, an unparseable manifest.json, or a ref missing from the tarball is an error, never "equal". This is the same rule promote-image.yml:475 follows.
- Logic lives in `actions/image-identity/identity.py`, stdlib only, called via `$GITHUB_ACTION_PATH`; `action.yml` is a thin wrapper (the pattern of ci-verdict).
- Tests: `tests/test_image_identity.py`, run through a new `make image-identity` target that the `step-bodies` job calls (ci.yml :324-347). Fixtures are hand-built tarballs in both layouts (classic and OCI), with tampered-byte and missing-ref cases. Tests need no docker (load is skipped behind a flag); one CI job runs the real `docker save`/`load` round trip on ubuntu-24.04 **and** on ubuntu-latest, which proves the store-independence claim on both stores.
- Docs: `docs/image-identity.md` covers what it replaces, the two modes, an example, and why not `.Id` (with the consumer's evidence, names stripped per the RW naming rule).

## Execution (dispatcher, one wave, 2 builders in parallel)
- Before dispatching: commit a `wip/` checkpoint in claude-config and confirm reusable-workflows is clean. Briefs forbid `git checkout/restore/stash/reset/clean`.
- **Builder U1** owns claude-config `skills/workflow-preflight/**`.
- **Builder U2** owns `reusable-workflows/{actions/image-identity/**, tests/test_image_identity.py, docs/image-identity.md, Makefile, .github/workflows/ci.yml, README.md}` on a branch.
- Return contract for both: DONE/BLOCKED, files changed, red→green evidence (failing test names, then pass counts), and no guessing (BLOCKED if a ruling is needed).
- Then devops (me): review both diffs, steps 7–10. The PR merge and the `release.yml` dispatch are owner `!` commands.

## Verification
- U1: the full suite passes. Running `runners` on the consumer's pre-fix e2e.yml must report `RUNNER_SPLIT` + `ID_COMPARE`. Running it on the fixed version must report only `ID_COMPARE`.
- U2: `make ci` is green. The real-docker CI job passes on both runner labels, with the identity recorded on one label and verified on the other: exactly the cross-runner case that failed.
- Adoption: each project reports back its `runners` output and a green rehearsal or e2e run.
