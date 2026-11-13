# Plan — caller-declared waiver kinds (`waiver_pairs`) + plan outputs the PR label list (RW1)

Status: **plan, not approved for build.** Owner ruling RW1 = option B (DECISIONS.md 2026-11-13
"Owner ruling: release-flow waivers extend to caller-declared pairs (waiver_pairs) + plan outputs
PR labels"). TODO item: `TODO.md:"Caller-declared waiver kinds (`. Ends at "PR merged, release
pending owner". Marks: **VERIFIED** = read in source at the cited line; **UNVERIFIED** = inference
or not checked.

## 1. Decision summary (one screen)

- **What.** Today the `breaking-approved` label can only waive a break on a `services.json`
  `contracts` pair (VERIFIED `actions/release-flow/releaseflow/waiver.py:107-110`, R2) that also
  has a live-consumer `checks` entry (VERIFIED `waiver.py:138-145`, R3). A caller with an extra
  compatibility stage of its own (example: consumer A checks the *oldest published client SDK*
  against the candidate backend spec) cannot get a waiver for that stage, so it keeps its own
  labels job and its own waiver logic (the rejected option A).
- **Change (ruling B).** New optional input **`waiver_pairs`**: a list of `consumer -> provider`
  pairs that are NOT `contracts` pairs. The same label + ```` ```breaking ```` block approves
  breaks on them. R1, R4, R5, R6 are unchanged. **R2** accepts a pair that is a configured
  contract OR a declared pair. **R3** for a declared pair is met by its presence in the declared
  list (ruling text); for a contracts pair R3 is unchanged (live-consumer check required).
- **New output `labels`** on `release-plan.yml`: JSON list of the release PR's label names, so a
  caller needs no labels job. Rehearsal without `manifest-ref` (no PR) gives `[]`.
- **Safety invariant (from the ruling's word "non-`contracts`"):** a declared pair that is also a
  configured contract is refused (exit 2). Otherwise a caller could turn off R3's live-consumer
  check for a real contract by redeclaring it.
- **Where it is wired:** `release-pr-check.yml` (R2 runs there, VERIFIED
  `.github/workflows/release-pr-check.yml:143-151`) and `release-plan.yml` (R1/R2/R5 in `plan`,
  VERIFIED `release-plan.yml:273-296`; R3 in `resolve`, VERIFIED `release-plan.yml:489-499`).
  Both get the same input; the caller passes the same string to both (Q1).
- **R4 for a declared pair is the caller's job:** its own stage runs
  `release-flow spec-compat BASE CAND --pair "<c> -> <p>" --consumer-side live` with
  `RELEASE_BREAKING: ${{ needs.plan.outputs.breaking }}`. spec-compat already accepts any
  well-formed pair (VERIFIED `spec_compat.py:442-444`, only `parse_pair`), so spec_compat.py needs
  no change. Stale entries fail there as today (VERIFIED `spec_compat.py:464-465`).
- **Accepted by the ruling:** if the caller's stage does not run spec-compat for a declared pair,
  approved lines for it are never matched against findings. R3 no longer forces "every waived
  finding == the block" for declared pairs. The ruling accepts this ("a declared list gives the
  same anchor").
- **Semver:** minor, **v6.3.0** (latest tag v6.2.0, VERIFIED `git tag`; 5 commits since, none
  changing an input contract per their titles — titles only, UNVERIFIED in diff). Existing callers
  pass no `waiver_pairs` and behave exactly as before. The CLI tree changes, so
  `RELEASE_FLOW_TREE` is restamped in the PR (§6 Wave 4). Release only on the owner's explicit ask.

## 2. Owner questions (only what the ruling leaves open)

**ANSWERED (owner, 2026-11-13) — these are spec text; the `[Q*]` markers below resolve as follows:**
- **Q1 = A.** The caller lists its extra waiver pairs in a `waiver_pairs` workflow input on BOTH
  release-pr-check and release-plan (not a services.json key). If the two copies drift, the Release
  refuses before any write.
- **Q2 = B.** The provider side of every declared pair must be a configured service; an unknown
  name (e.g. the typo `sdk-oldest -> backned`) fails the PR check immediately with a clear error.
- **Q3 = B.** release-plan's `labels` output is the PR's labels at the moment it merged: label
  events are replayed up to `merged_at` (the same rule as R5), so a label added after the merge
  does not count. Build only the `[Q3-B]` paths; drop `[Q3-A]`.

**Q1. Where does the caller write the list?** The ruling says "input". R2 runs in two workflows,
so both need the list.
- *Example:* consumer A writes `waiver_pairs: "sdk-oldest -> backend"` in `release-pr.yml`
  (calls `release-pr-check`) AND in `release.yml` (calls `release-plan`).
- **A (ruling literal):** an input on both workflows. Cost: the list is written twice. If the two
  drift, `release-pr-check` and the Release disagree. The Release still refuses before any write,
  so drift is safe.
- **B:** a `waiver_pairs` key in `services.json` next to `contracts`. Written once, and
  `release-pr-check` reads it from the base commit. This changes the ruling's word "input", and
  `config.py` is strict, so it needs a schema change.
- **Rejected C:** the input only on `release-plan`, with `release-pr-check` skipping the pair
  check for unknown pairs. That weakens R2 in the place the author sees first.
- **Recommendation: A.** It is what was ruled, and the drift is fail-safe. **Blocks:** every wave
  (B moves the parse into `config.py` and drops both workflow inputs).

**Q2. Must the provider side of a declared pair be a configured service?**
- *Example:* a typo `waiver_pairs: "sdk-oldest -> backned"`. Under A it is accepted, and it fails
  later: the block line `sdk-oldest -> backend | …` is refused by R2 as "not configured". Under B
  the typo fails at once, on the first run, with "provider 'backned' is not a service in
  services.json".
- **A:** any well-formed pair (ruling literal).
- **B:** the provider must be a `services.json` service; the consumer side is a free name.
- **Recommendation: B.** It is cheap, it fails earlier, and no case needs a provider outside the
  release (spec-compat compares a candidate *provider* spec). **Blocks:** one validation and its
  test in Wave 2/3 (marked `[Q2]`).

**Q3. Is `labels` the labels on the PR now, or the labels it had when it was merged?**
- *Example:* someone adds `skip-smoke` to the merged release PR 3 s after the merge. Under A,
  the plan (which reads seconds after the merge) may output it. Under B, it is not in `labels`.
- **A:** the current labels, as read (one read, no event replay).
- **B:** for a real release, replay `labeled`/`unlabeled` events strictly before `merged_at`. This
  is the R5 rule generalised from one label to all. A rehearsal uses the open PR's current labels.
- **Recommendation: B.** It matches R5's "a label added after the merge approves nothing", so a
  caller gating a stage on a label gets the same guarantee. Cost: issue events are read on every
  real release, not only when a block exists (VERIFIED, today only when `entries`:
  `guard.py:113`). **Blocks:** the label half of Wave 2/3 (marked `[Q3]`).

## 3. Design detail (builder reads this; spec text)

**Input `waiver_pairs`** (both workflows): `type: string`, `required: false`, `default: ''`.
Pairs separated by commas or newlines; surrounding whitespace is ignored; empty items are
dropped. Each item must match the existing pair grammar `consumer -> provider` (VERIFIED
`waiver.py:26-27`). These fail with **exit 2** (caller config error, like `--checks` not JSON,
VERIFIED `release_flow.py:378-381`): a malformed item, a duplicate, a pair that is a configured
contract, and `[Q2]` a provider that is not a configured service. Empty = today's behaviour,
byte for byte.

**CLI (`actions/release-flow/releaseflow/`)**
- `waiver.py`: add `parse_declared(text, contracts[, services])` → frozenset of pairs (raises
  `WaiverError`). `check_shape(labels, body, contracts, declared=frozenset())`: a pair passes R2
  if it is in `contracts | declared`. The error message names both sources. `check_matrix(entries,
  checks, declared=frozenset())`: a declared pair passes R3 by presence. `[Q3]`
  `labels_at(events, merged_at)` → sorted label names whose last labeled/unlabeled event before
  `merged_at` is `labeled`. `label_before_merge` stays (or becomes `LABEL in labels_at(...)`,
  with its tests unchanged).
- `guard.py` `breaking_approval(..., declared=frozenset())` returns `(entries, labels)`. Rehearsal:
  the open PR's current label names. Real release: `[Q3-B]` `labels_at(events, merged_at)` (events
  always read), `[Q3-A]` current names.
- `release_flow.py`: `--waiver-pairs S` (default `''`) on `breaking-shape`, `breaking-approval`,
  `breaking-matrix`. `breaking-matrix` gains `--config` (default as elsewhere) so it can refuse an
  overlap with contracts too. `breaking-approval --labels-out FILE` writes the labels JSON from
  the SAME PR read; a second read would race a label change. stdout stays the entries list, so
  the existing `jq` checks do not change. Update the help text (VERIFIED `release_flow.py:102-112`)
  and the module docstring (`waiver.py:11-15`).

**Workflows**
- `release-pr-check.yml`: input `waiver_pairs`. The breaking step passes `WAIVER_PAIRS:
  ${{ inputs.waiver_pairs }}` via `env:` and calls `--waiver-pairs "$WAIVER_PAIRS"`.
- `release-plan.yml`: input `waiver_pairs`. Plan step `brk` passes it and `--labels-out
  "$RUNNER_TEMP/labels.json"`, then writes `labels=<compact JSON>` to `$GITHUB_OUTPUT`. A
  rehearsal without `manifest-ref` writes `labels=[]`. `jobs.plan.outputs.labels`. Workflow output
  `labels` (value `${{ jobs.plan.outputs.labels }}`). Resolve step `brk` passes `WAIVER_PAIRS`
  and `CONFIG`. Inputs reach shell only via `env:` (header rule, VERIFIED `release-plan.yml:15`).
  `shell: bash` comes from the workflow-level `defaults.run.shell` (VERIFIED
  `release-plan.yml:127-129`); keep it that way.
- `catalog.json` regenerated (`scripts/gen_catalog.py` reads inputs/outputs, VERIFIED
  `scripts/gen_catalog.py:45-63`).

**Caller-side trap to document:** the drafts verdict fails on any job in `needs` that is not
`success`, except the contracts job when `checks` is `[]` (VERIFIED `verdict.py:68-76`). So a
caller's declared-pair stage listed in drafts' `needs` must always run and pass when it has
nothing to compare. It must not be `if:`-skipped.

## 4. Documentation steps (Wave 1, before tests)

1. `docs/release-flow.md` §Breaking changes: a new subsection, "Caller-declared pairs
   (`waiver_pairs`)". It covers what a declared pair is, the generic example `sdk-oldest -> backend`,
   R3-by-presence and the accepted risk (§1), the overlap refusal, `[Q2]`, the caller's stage using
   `--consumer-side live`, and the drafts-`needs` trap (§3).
2. Same file, the rules table (VERIFIED `docs/release-flow.md:101-108`): R2 "every pair is a
   configured contract **or a declared `waiver_pairs` pair**"; R3 "…; a declared pair needs only
   its presence in `waiver_pairs`".
3. Same file, the input tables for `release-pr-check.yml` (`:584-587`) and `release-plan.yml`
   (`:597-611`): add a `waiver_pairs` row each. Outputs table: add `labels` (the `[Q3]` wording).
4. Same file, the caller example (`:652-748`): `waiver_pairs` on the `plan` call and on the
   `release-pr` call. One declared-pair stage (`sdk-compat`) with `--pair`/`--consumer-side live`/
   `RELEASE_BREAKING`, added to drafts' `needs`. One line showing
   `fromJSON(needs.plan.outputs.labels)`. No consumer or project names: the repo is public.
5. Same file, the CLI reference (`:806-808`): `--waiver-pairs`, `--labels-out` and `--config` on
   the three `breaking-*` rows.
6. `docs/release-plan.md:9`: add `labels` to the outputs list. `docs/release-pr-check.md:5`: one
   clause, "pairs are configured contracts or the caller's `waiver_pairs`".
7. Doc review (global rule `doc-review`) by a fresh agent before the owner sees it.

## 5. Test steps (Wave 2, red first; harness `make release-flow` → `tests/run_release_flow_tests.py`,
which fails on any failure, skip or zero tests — VERIFIED `tests/run_release_flow_tests.py:1-8`)

`actions/release-flow/releaseflow/test_waiver.py` (unittest, existing classes `ShapeTests`,
`LabelBeforeMergeTests`):
- `parse_declared`: comma and newline lists; whitespace; empty → empty set; malformed item,
  duplicate, overlap with a contract → `WaiverError`; `[Q2]` unknown provider → error.
- `check_shape`: a declared pair passes R2; an undeclared non-contract pair still fails (existing
  `test_pair_must_be_a_configured_contract` stays green); R1 is unchanged for declared pairs.
- `check_matrix`: a declared pair passes with no `checks` entry; a contract pair still needs
  `consumer_side: live`, even when `declared` is non-empty.
- `[Q3-B]` `labels_at`: before/at/after merge, re-add, order independence, other events ignored
  (mirror `LabelBeforeMergeTests`).

`actions/release-flow/releaseflow/test_breaking_cli.py` (fake GitHub, `main(argv, env, deps)`):
- `breaking-shape --waiver-pairs`: declared pair → list printed, exit 0; overlap → exit 2.
- `breaking-approval --waiver-pairs … --labels-out F`: real release writes the `[Q3]` labels;
  rehearsal writes the open PR's labels; no flag → today's output, byte for byte.
- `breaking-matrix --waiver-pairs`: a declared pair with `checks=[]` → exit 0; malformed → exit 2.

`tests/release_flow_workflows/test_workflow_breaking.py` (shape tests via `wf.py`):
- Both workflows declare input `waiver_pairs` (string, not required, default `''`).
- `release-pr-check` breaking step: `env.WAIVER_PAIRS == '${{ inputs.waiver_pairs }}'`, and run
  contains `--waiver-pairs "$WAIVER_PAIRS"`.
- `release-plan` plan `brk` and resolve `brk`: the same, plus `--labels-out`, plus
  `jobs.plan.outputs.labels == '${{ steps.brk.outputs.labels }}'` and the workflow output `labels`.
- `CallerExampleTests`: the doc example passes `waiver_pairs` to both calls and the `sdk-compat`
  stage uses `--consumer-side live`.

Each test agent runs `make release-flow` and reports the new tests FAILING (red) and every
pre-existing test still passing.

## 6. Dispatcher waves (no two agents in one wave share a file)

**Wave 0 (dispatcher):** owner answers Q1-Q3. Commit a `wip/` checkpoint before dispatching.
Every brief says: never run `git checkout`/`restore`/`stash`/`reset`/`clean`; never commit; write
scratch only under `reusable-workflows/.scratch/`.

**Wave 1 — docs (1 agent, `builder`).** Owns `docs/release-flow.md`, `docs/release-plan.md`,
`docs/release-pr-check.md`. Brief: §3 and §4 of this plan. Read `docs/release-flow.md` by
`dsec`/offset, never whole. Gates: `make doc-examples docs-coverage doc-anchors`. Then a fresh
`doc-review` agent (read-only). Return: STATUS, files, the gate output lines, review verdict.

**Wave 2 — red tests (2 agents in parallel, `builder`).**
- 2a owns `actions/release-flow/releaseflow/test_waiver.py` and `test_breaking_cli.py`.
- 2b owns `tests/release_flow_workflows/test_workflow_breaking.py`.
Brief: §5. Return: STATUS, the count of new tests, the names of the failing tests, and
`make release-flow` summary line(s) proving red for the new tests and green for the rest.

**Wave 3 — implementation (2 agents in parallel, `builder`).**
- 3a owns `actions/release-flow/releaseflow/waiver.py`, `guard.py`, `release_flow.py`.
- 3b owns `.github/workflows/release-plan.yml`, `.github/workflows/release-pr-check.yml`,
  `catalog.json` (regenerated with `scripts/gen_catalog.py`, never hand-edited).
Brief: §3. 3b: narrow `Edit`s only (the YAMLs are 611/162 lines); inputs via `env:` only; no
`${{ }}` inside `run:`. Gates: 3a `make release-flow`; 3b `make actionlint shellcheck preflight
zizmor catalog`. Each returns STATUS, files, gate lines. After both: the dispatcher runs `make
release-flow`, which must be all green, then commits.

**Wave 4 — restamp + records (1 agent, `builder`, after the Wave 3 commit).** Owns the four
workflows that carry `RELEASE_FLOW_TREE` (VERIFIED by grep: `release-drafts.yml`,
`release-plan.yml`, `release-pr-check.yml`, `release-publish.yml`), `DECISIONS.md` and `TODO.md`.
- Run `python3 scripts/stamp_version.py v6.2.0`. That run re-sets only the tree hash, because
  the version is unchanged. UNVERIFIED that it leaves `WORKFLOW_VERSION` byte-identical; check
  with `git diff`.
- `DECISIONS.md` via `decisions add`: "Release flow: caller-declared waiver pairs + plan `labels`
  output built (RW1)". It records what was built, the Q1-Q3 answers, the overlap refusal and the
  accepted R3 trade-off, and links this plan.
- `TODO.md`: tick the item with evidence (PR number).
- Gate: the full `make ci`, `ci: OK, N of N`. Return: STATUS, files, the `make ci` final line.

**Wave 5 (dispatcher):** commit, PR, CI green, merge on the owner's approval. **Stop: release
v6.3.0 pending the owner's explicit "release".**

## 7. Implementation order recap

Docs (W1) → red tests (W2) → CLI + workflows (W3) → tree restamp + DECISIONS/TODO (W4) → PR (W5).

## 8. Release note (draft, for the GitHub release body at release time; this repo has no
CHANGELOG.md — VERIFIED `ls`, and `git log -- CHANGELOG.md` is empty)

> **v6.3.0 (minor).** `release-plan` and `release-pr-check` gain an optional `waiver_pairs`
> input: caller-declared `consumer -> provider` pairs (not `contracts` pairs) whose breaks the
> `breaking-approved` label + ```` ```breaking ```` block can approve. The caller's own stage
> applies the list with `spec-compat --pair … --consumer-side live`. `release-plan` gains a
> `labels` output (the release PR's labels [Q3 wording]). A caller that passes neither input
> behaves exactly as on v6.2.0. To adopt: move the pin to `v6.3.0`, pass the same
> `waiver_pairs` to both calls, and drop any caller-owned labels job.

At release time a separate DECISIONS entry "`v6.3.0` released" follows the `v3.5.0` pattern
(VERIFIED `DECISIONS.md:1527`).

## 9. Out-of-scope finding (for TODO.md, not this change)

- `docs/release-flow.md:825-827` says the release-flow tests run "in `step-bodies`". The Makefile
  runs them in the `release-flow` target (VERIFIED `Makefile` target `release-flow:`
  `tests/run_release_flow_tests.py`), and `step-bodies` does not (VERIFIED `Makefile:170-175`
  lists no release-flow runner).
