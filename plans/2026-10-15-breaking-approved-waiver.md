# Plan — `breaking-approved` waiver for release-flow `spec-compat` (reusable-workflows)

## Decision summary (one screen)

- **What:** a spec removal that breaks a live consumer can ship in ONE release, if the owner labels
  the root release PR `breaking-approved` and the PR body lists every break exactly. Otherwise
  nothing changes: an unlisted break fails the release, as it does today.
- **Where the exact list is checked (Q-A, ruled 2026-10-15):**
  - **pre-merge** by a rehearsal run, which already runs the caller's contracts with zero writes;
  - **post-merge** by the real Release, before its first write (drafts).
  - `release-pr-check` itself only checks that the block is well-formed and matches the label. It
    gets no token. (The relayed ruling text proposed that it recompute the breaks; the owner chose
    the rehearsal instead under Q-A.)
- **Never waivable:** spec-compat exit 2 (crash, unreadable file) or 0 operations examined.
- **Caller cost:** one new env var on the existing `spec-compat` line in the contracts job, and
  `labeled`/`unlabeled`/`edited` added to the release PR trigger. No new secret and no new
  permission: the plan job already has `pull-requests: read`.
- **Release:** rw **v3.5.0**, a minor release (additive input contract; the CLI tree changes, so
  callers bump their pin). Building it needs the owner's go after this plan. The release itself
  needs a separate explicit ask.
- **Supersedes** DECISIONS 2026-10-15 "Root release checks contracts between services only — no
  removal-approval list". The between-services-only half stands; the no-approval half is
  reversed (owner, 2026-10-15, confirmed in this session after the consumer relayed the ruling).

## Context

A consumer burned two patch versions (core + gateway) because `spec-compat` refuses any removal,
even a deliberate one that is already inert on the wire. On 2026-10-15 the owner first ruled
"no approval; two releases". After the consumer's session relayed a fuller ruling, the owner
confirmed here that a label-gated, exact-list waiver should be built in the shared flow. Owner
rulings (relayed by the consumer, confirmed by the owner in this session):
1. A removal is a BREAKING change and must be flagged. If approved it ships in one release;
   otherwise it takes two (the consumer drops it from its pin first).
2. The owner approves by adding the label `breaking-approved` to the root release PR before merge.
3. The approval covers only the EXACT list of breaks shown before merge.
4. Every waived break is printed in the Release run's job summary.
5. spec-compat crashing, or examining 0 operations, stays red even with the label.
6. Accepted risk signed by the label: between the provider deploy and the consumer deploy, the
   live consumer talks to a provider that no longer has the removed item.

## Facts the design rests on (from the Explore agent; ★ = I checked it in source myself)

- ★ `spec-compat` prints `INCOMPATIBLE {where}: {msg}` per finding. Exit 1 covers both "breaks"
  and "0 operations"; exit 2 is usage/unreadable (`spec_compat.py` `main()`, ~L390-421).
- Findings are deterministic (they follow the baseline's path order; messages hold only names).
  But the consumer→provider pair appears only in the header line, so a waiver entry must name
  the pair itself. (agent, `spec_compat.py:118-119`, :305, :381 — unverified)
- `release-pr-check` has no token and no `live_ref`, and no spec paths exist in the shared config.
  The caller fetches its own specs. Recomputing breaks there would need the release App key in a
  `pull_request`-triggered workflow, plus a per-caller spec locator. (agent; release-pr-check.yml
  :7-9, :83-94; config.py:66 — unverified)
- The plan job's guard already fetches the merged PR object (`guard.py:31`) and has
  `pull-requests: read` (release-plan.yml:126). Body and labels are on that object per the GitHub
  docs (agent — unverified; the build checks this first).
- ★ A rehearsal runs the caller's contracts with zero writes, on a PR branch that is not merged
  (docs/release-flow.md §Rehearsal). A post-merge failure before drafts writes nothing, so the same
  tags can be re-released through a corrected PR. Only a code change forces a new version.
- Each release-flow workflow pins `RELEASE_FLOW_TREE`, and every CLI change needs a new tag
  (README.md:168-180, `scripts/stamp_version.py`). The release-plan self-test runs every
  `test_*.py` inside every caller's Release.

## Design

**The block (PR body), one line per break, pair first:**
````
```breaking
gateway -> core | POST /login: request property extra_fields removed in candidate
```
````
The text after `|` is the spec-compat finding exactly (`{where}: {msg}`). The pair uses
`services.json` repo names, with no refs, because the manifest fixes the refs.

**Rules (the CLI's `waiver` module, stdlib only):**
- R1 Label without block, or block without label → fail. (At `release-pr-check`, rehearsal, and Release.)
- R2 Block syntax: every line parses, no duplicate lines, and the pair is a configured contract.
- R3 Plan (post-merge, and in a rehearsal via the open PR for `manifest-ref`) reads label + body.
  It refuses a block entry whose pair is not in the `checks` matrix, and outputs `breaking` (JSON
  list) for the caller.
- R4 `spec-compat … --pair "gateway -> core"` with env `RELEASE_BREAKING` = plan's output:
  - each finding listed for this pair → printed `WAIVED`, and written to `$GITHUB_STEP_SUMMARY`;
  - any unlisted finding → fail (as today);
  - any listed entry for this pair that did not occur → fail (no stale approvals);
  - exit 2 or 0 operations → fail, whatever is listed (ruling 5).
  R3 + R4 together make "the union of waived findings == the block".
- R5 The label must have been added BEFORE `merged_at`: the latest `labeled` event in
  `issues/{n}/events`, with no later `unlabeled` before the merge. That way a label added after
  merge cannot approve anything.
- R6 On any failure, spec-compat prints a ready-to-paste `breaking` block of what it found. The
  author gets the exact text from a rehearsal.

**Pre-merge flow for the author:** open the release PR → run a rehearsal → copy the block from its
failure output into the PR body → owner adds the label → rehearsal again (green, with WAIVED lines
in the summary) → merge → the Release re-checks the same thing post-merge before drafts.

## Steps (Design → Doc → Test → Implement)

1. **Docs first.**
   - `docs/release-flow.md`: new § "Contract checks" (the heading `spec_compat.py` already cites
     but which does not exist). It covers between-services-only, breaking changes, the label, the
     block grammar, R1-R6, the author flow, the accepted risk window (ruling 6), and the two-release
     route without a label.
   - Inputs/outputs: the `breaking` output, the caller's env var, the PR trigger types.
   - Caller example updated (release-pr.yml trigger; contracts `run:` line).
2. **Decision log.** New DECISIONS entry superseding the 2026-10-15 one (WHY: owner reversal,
   rulings 1-6, why `release-pr-check` gets no token). Rewrite the TODO.md spec-compat section:
   close "no approval"; keep the docstring-leak item.
3. **Red tests**, confirmed failing:
   - `test_waiver.py`: block parse, R1/R2, matching, stale entry, duplicates, pair not in matrix;
   - `test_spec_compat_*`: `--pair` + `RELEASE_BREAKING` → WAIVED / unlisted fails / stale fails /
     0 ops fails / exit 2 fails;
   - guard/plan tests on `fake_github.py`: label present/absent, label added after merge, block
     output, rehearsal PR lookup;
   - pr-check: shape rules against a fake event payload;
   - workflow-shape tests under `tests/release_flow_workflows/` for the new output and step.
4. **Implement.**
   - `releaseflow/waiver.py`;
   - `spec_compat.py` (`--pair`, env, summary, paste block);
   - guard/plan command (read body + labels + events; `breaking` output);
   - `release-plan.yml` output wiring; `release-pr-check.yml` shape step (from `github.event`, no
     token).
5. **Scrub** the consumer paths in the `release_flow.py` / `spec_compat.py` docstrings (the
   TODO item), since those files are being edited anyway.
6. **Gates:** `python3 tests/run_release_flow_tests.py` (fails on a skip or 0 tests), `actionlint`,
   SHA-pin check, `stamp_version.py --check`, consumer-name grep over diff + PR text.
7. **PR** → CI green → owner merges.
8. **Release v3.5.0** only on an explicit ask: `stamp_version.py v3.5.0` PR, then this repo's
   `release.yml`. Then send the consumer the tag, SHA, the `RELEASE_FLOW_TREE`, and the
   caller-side changes.

## Verification

- Unit + workflow-shape suite green with a stated non-zero test count; each red test was seen
  failing first.
- End-to-end: the consumer runs a **rehearsal** on a real breaking release PR at v3.5.0 —
  (a) no label → red with a paste-ready block; (b) block + label → green, WAIVED lines in the
  summary; (c) one line edited → red (stale/unlisted).
- Read-only check of the consumer's adoption afterwards (its pin, env line, trigger types).

## Open questions (owner)

- **Q-A — RULED (owner, 2026-10-15):** Before merge, a rehearsal run on the open release PR checks
  the exact list. After merge, the real Release checks it again before its first write.
  `release-pr-check` checks only that the block is well-formed and matches the label, and it gets
  no token. The release-bot key therefore never enters a PR-triggered workflow.
