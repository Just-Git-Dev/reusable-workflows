# v6.0.0 item #3 — `client-id` instead of `app-id`, and a caller `github-token` beside the App

Status: PLAN (no source edited). Written 2026-11-01 on branch `feat/ci-green-paths-allowlist`
(HEAD `7db21b6`). Controlling sources, in order: the owner rulings in `TODO.md` §"App-token mint"
(`TODO.md:"Owner 2026-11-01 (away batch)"`), then the code. Where the TODO and the code disagree,
the code fact is listed under "Contradictions" and the ruling is NOT silently widened.

## 0. Decision summary (one screen)

- **Scope, verified:** 48 workflow files + 6 composite `action.yml` examined (54 files).
  20 `create-github-app-token` steps: 19 in 8 workflows (`distribute-env-secrets`, `release-plan`,
  `release-drafts`, `release-publish`, `repos-create`, `repos-environments`, `repos-settings`,
  `repos-variables`) and **1 in the composite action `actions/rotate-external-secret`**, called by
  `rotate-external-secret.yml`. The TODO's "8 workflows" misses that 9th (open question Q2).
- **Rename** every mint's `app-id:` to `client-id:` (the pinned v3.3.0 action has `client-id`
  and marks `app-id` deprecated: `.scratch/v6-cgat-action.yml:8-14`, fetched at the pinned SHA).
  Our inputs follow each file's own case: `app-id` -> `client-id`, `app_id` -> `client_id`.
  The value changes too (the App's Client ID, not the numeric App ID), so callers need a new
  variable; this plan proposes `vars.RELEASE_APP_CLIENT_ID` in the docs (a proposal, not a ruling).
- **Two modes, settled:** App (`client-id` + the existing key secret) OR one secret `github-token`.
  Both passed = fail with "pass the App or github-token, not both". Neither = fail too.
- **Mechanism (proposed):** one inline guard step, byte-identical, first in EVERY
  job that mints (revised after the critic, §3.2: not the first job, which may lack the
  caller's environment), before any mint. Every mint gets `if: inputs.client-id != ''` (combined with any existing
  `if:`). Every token consumer reads `${{ steps.<mint>.outputs.token || secrets.github-token }}`.
  The client-id input and the key secret become `required: false`.
- **No new action, no CLI change:** `RELEASE_FLOW_TREE` pins `actions/release-flow` only
  (`release-plan.yml:161-162`), so this YAML-only change leaves it at `3b6ca6d` (= HEAD tree, checked).
- **Least privilege in token mode is the caller's job, and the docs say so in one pinned
  sentence.** The App-mode scope tests stay as they are and keep meaning "App mode". A caller
  token gets none of our narrowing: no `permission-*`, no `repositories:` (one repo per publish
  slot), no read-only token for read jobs or rehearsals, no revoke at job end, no 60-min lifetime.
- **Gate before any build (Wave 0):** prove GitHub accepts a `workflow_call` secret named
  `github-token`. GitHub rejects `github_token` at PARSE time, case-insensitively, and actionlint does
  NOT catch it (`DECISIONS.md:4901-4917`). Whether the hyphen form collides is (unverified).
- Ships in v6.0.0 with ci-green and the rotate-worker-signing-secret removal; merge to main when
  done; no tag until the owner asks (settled).

## 1. Open questions (owner's call; settled rulings not re-asked)

**ALL FOUR ANSWERED by the owner 2026-11-01 (each as recommended):**
- **Q1:** Token mode uses one `github-token` secret for every job of the release flow; there is
  no separate read token. The docs state plainly that a caller token gets none of our narrowing
  (no per-job permissions, no repository limit, not revoked at job end), so its scope is the
  caller's responsibility, and App mode remains the least-privilege option.
- **Q2:** `rotate-external-secret` is the 9th workflow with both auth modes (App or
  `github-token`); `validate-inputs.sh` stops accepting only a numeric App ID.
- **Q3:** Any App field set (`client-id` or the private key) counts as "App given": half an App
  plus `github-token` is refused as "both", and half an App alone is refused as "App incomplete:
  missing <field>". Nothing is guessed.
- **Q4:** `app-id` is renamed to `client-id` outright in v6.0.0, with no deprecated alias;
  v5.2.0 was the deprecation window.
Wave 0 approved by the owner 2026-11-01.
**Away answers, owner 2026-11-01:**
- **Build and release:** after Wave 0, waves 1-4 are built, pushed, merged and released as
  v6.0.0 once validated. "Validated" means `make ci` is green, the critic finds no blocker, and
  the three live `repos-settings` checks (§6.4) behave as specified. This is the owner's explicit
  release ask for v6.0.0.
- **If GitHub rejects `github-token`** while the `github_token` control passes, the secret is
  named `github_token` everywhere and the build goes ahead.
- **Live checks:** the dispatcher runs the three report-only `repos-settings` checks itself once
  the PR's CI is green, and records the run ids in DECISIONS.md.

**Q1. Release flow: one `github-token` for every job, or an optional separate read token?**
Today plan/drafts/publish mint a READ-only token in read jobs and in a rehearsal, and a WRITE token
only in `drafts` (non-rehearsal) and the six `publish-N` jobs, each publish slot scoped to one repo
(`test_workflow_tokens.py:79-112`). One caller token cannot be split that way.
Example: a caller passes a fine-grained PAT with `contents: write` on 3 repos. Under (A), the
`resolve` job pip-installs PyYAML unpinned from PyPI (`release-plan.yml:421-422`) and then runs
ci-green with that PAT in its env (`release-plan.yml:424-427`); a rehearsal holds it too; and the
`check-release-gate` action receives it (`release-plan.yml:546-549`). In App mode all three hold a
read-only token.
- (A) Same `github-token` everywhere; the docs tell the caller to scope it. Matches "one secret".
- (B) `github-token` for write jobs + optional `github-read-token` for read jobs and rehearsals,
  falling back to `github-token` when absent. Restores read/write separation for careful callers;
  adds a second secret, which arguably supersedes the "one secret" ruling.
- **Recommendation: A.** The fleet uses the App everywhere (ruling); token mode is for outside
  callers, and B's protection only helps a caller who mints two tokens. Document the exposure list
  above. Blocks: the release-* tests (Wave 2 agent E) and the release-flow doc tables (agent A).

**Q2. Is `rotate-external-secret` the 9th two-mode workflow?** Its mint is inside the composite
action (`actions/rotate-external-secret/action.yml:142-152`), with `app_id`/`app_key` required
(`action.yml:24-29`, `rotate-external-secret.yml:89-92,102-104`). The rename to `client-id` applies
regardless ("every step"). The "all 8" ruling was made from a list that missed it.
Example: a consumer with no App but a PAT can call `repos-settings` in v6 but not
`rotate-external-secret`.
- (A) Yes: `github-token` on the workflow and a `github-token` input on the composite action.
- (B) No: rename only; it stays App-only.
- **Recommendation: A** (the general rule is "every workflow that needs a GitHub credential beyond
  GITHUB_TOKEN"). Blocks: agent I's files and `run_rotate_external_tests.py`.

**Q3. What counts as "passed the App" for the both/neither check?**
Example: a caller passes `github-token` and the key secret but forgets `client-id`. Deciding by
`client-id` alone treats that as token mode and silently ignores the key.
- (A) The App counts as passed when `client-id` OR the key is non-empty. Then: App + token = the
  settled error; `client-id` without key = "client-id needs the private key"; key without
  `client-id` = "the private key needs client-id"; neither = "pass the App (client-id + key) or
  github-token". Needs the key's PRESENCE in the guard (`KEY_SET: ${{ secrets.X != '' }}`), so the
  key-confinement test (`test_workflow_tokens.py:29-51`) is relaxed from "only as `private-key`"
  to "only as `private-key`, or as that one `!= ''` boolean in the guard step".
- (B) Decide by `client-id` only; the key's name never leaves the mint step; half-App passes
  are caught only by the mint's own empty-key error.
- **Recommendation: A**: "nothing guesses which was meant" (ruling) covers the half-App case,
  and the boolean exposes no value. Blocks: the guard text (all of Wave 3) and agent E's test.

**Q4. Rename outright in v6.0.0, or keep `app-id` as a deprecated alias through v6.x?**
The TODO (`TODO.md:"with a deprecation window"`) asked for a window; the ruling says the inputs
"change accordingly".
- (A) Outright rename. v5.2.0 stays callable as it is, and that is the window. A v6 caller sets
  `client-id`.
- (B) Keep `app-id` optional and deprecated in v6 (warn, map to the action's `app-id`), remove in v7.
  Three credential inputs per workflow, and the both/neither guard grows a third case.
- **Recommendation: A.** Blocks: the input lists in every test and doc table.

Not a question, a gate: if Wave 0 shows GitHub rejects `github-token`, the settled name cannot ship
and goes back to the owner with the probe's error text. Nothing past Wave 0 starts until then.

## 2. Contradictions with the TODO (code facts)

1. "8 workflows mint an App token" (`TODO.md:"Checked\n  2026-11-01: 8 workflows"`): true for direct
   `uses:` in workflows. A 9th mints through `actions/rotate-external-secret/action.yml:144`.
   Total mint steps: 20 (19 + 1), not 23. The "23 files" figure is stale, as the TODO itself says.
2. `TODO.md:"a new \`RELEASE_FLOW_TREE\`"` (§"app-id from the environment") says an input change to
   the release workflows needs a new tree hash. The tree pins `actions/release-flow` only
   (`release-plan.yml:161-162`); a workflow-YAML change does not move it. That TODO item also
   names `app-id`/`vars.RELEASE_APP_ID`; it must be rewritten for `client-id`.
3. The rotate-external validator demands a NUMERIC App ID (`validate-inputs.sh:32`,
   `match app_id "$APP_ID" '^[0-9]+$'`). A Client ID is alphanumeric (format unverified, e.g.
   `Iv23li...`), so a rename that skips that line rejects every valid caller.

## 3. Design detail

### 3.1 Inputs and secrets per workflow (v6 contract)

| Workflow | ID input (was -> v6, required) | Key secret (v6 required) | New secret |
|---|---|---|---|
| release-plan / -drafts / -publish | `app-id` -> `client-id`, false | `RELEASE_APP_KEY`, false | `github-token`, false |
| repos-create / -settings / -variables | `app-id` -> `client-id`, false | `REPO_ADMIN_APP_KEY`, false | `github-token`, false |
| repos-environments | `app_id` -> `client_id`, false | `app_key`, false | `github-token`, false |
| distribute-env-secrets | `app_id` -> `client_id`, false | `app_key`, false | `github-token`, false |
| rotate-external-secret (Q2=A) | `app_id` -> `client_id`, false | `app_key`, false | `github-token`, false |
| actions/rotate-external-secret (Q2=A) | input `app_id` -> `client_id` | input `app_key`, false | input `github-token` |

`release-pr-check` is unchanged: no secret, no mint (`test_workflow_tokens.py:70-75`).
Inputs cited: `release-plan.yml:33-36`, `release-publish.yml:34-37,59-61`, `repos-settings.yml:25-37`,
`distribute-env-secrets.yml:35-38,49-51`. The two `GITHUB_`-reserved names are avoided already.

### 3.2 The guard (one body, byte-identical everywhere; a test asserts it)

The first step after any existing refusal (repos-*: after "Refuse unless repo-admin on the main
branch", `repos-settings.yml:60`), in EVERY job that mints a token (REVISED 2026-11-01 after
the critic: release-plan `resolve` + `service-gates`, release-drafts `drafts`, release-publish
`publish-1..6`, the single job elsewhere; NOT `plan`/`verdict`, which declare no environment, so
an environment-only secret reads empty there). Env only, no
`${{ }}` in `run:` (repo rule, `release-plan.yml:12`). `CLIENT_ID` from the input; `KEY_SET`
and `TOKEN_SET` as `!= ''` booleans (Q3=A). It exits 1 with the settled text when both are passed,
and with a clear text for neither and for the half-App cases. **Exact messages (fixed by the
dispatcher 2026-11-01 so docs, tests and code agree; generic so the body stays byte-identical;
each is printed as a `::error::` line, checked in this order):**
1. both (any App field set and the token set): `pass the App or github-token, not both`
2. neither: `no credentials: pass the App (client-id and its private key) or github-token`
3. key set, client-id empty: `App incomplete: missing client-id`
4. client-id set, key empty: `App incomplete: missing private key`
The env names are the same in every file: `CLIENT_ID`, `KEY_SET`, `TOKEN_SET`. If Wave 0 rejects
the hyphen, every `github-token` here becomes `github_token` (owner ruling, §1). `distribute-env-secrets.yml` and
`rotate-external-secret.yml` have NO `defaults: run: shell: bash` (verified by grep: only release-*
and repos-* do), so the step there declares `shell: bash` itself, as its siblings do
(`distribute-env-secrets.yml:72,88,153`). In the composite action the guard lives as
`actions/rotate-external-secret/validate-auth.sh` (that action's convention, `action.yml:132`), and
the body test compares the script's body with the inline one (precedent: `tests/action_steps.py:6-9`).

Why the guard is inline and not a shared composite action: `test_write_jobs_run_nothing_third_party_
and_install_nothing` allows only checkout, the mint and download-artifact in a write job
(`test_workflow_tokens.py:123-138`), and a shared action would be one more remote-`@vX` ref for
`stamp_version.py` to rewrite. **Reuse** that rule; no change to it.

### 3.3 Mint gating and token selection

- Every mint: `if: ${{ inputs.client-id != '' }}`; where an `if:` exists, AND it in:
  drafts `app-ro` / `app` (`release-drafts.yml:199,212`, pinned at `test_workflow_tokens.py:93-102`),
  repos-environments `app-rw` (`repos-environments.yml:202`), and the matching repos-* write mints.
  The mint must be SKIPPED, not called with an empty key: `private-key` is `required: true` in the
  action (`.scratch/v6-cgat-action.yml:15-17`).
- Every consumer of `steps.<mint>.outputs.token` (env `RELEASE_FLOW_READ_TOKEN`,
  `RELEASE_FLOW_WRITE_TOKEN`, `GH_TOKEN`, `with.token` of `check-release-gate`) reads
  `${{ steps.<mint>.outputs.token || secrets.github-token }}`. Only one of the two can be non-empty
  (the guard). `release-plan`'s `plan` job keeps `github.token` (`release-plan.yml:223,227,272`).
- Composite action: `if: ${{ inputs.client_id != '' }}` on the mint (`action.yml:142`), and
  `${{ steps.token.outputs.token || inputs.github-token }}` in its consumers (the mint's id is `token`) (`action.yml:159` and the later `GH_TOKEN` steps).
- `validate-inputs.sh:32`: replace the numeric `app_id` check with a `client_id` check that
  accepts the empty string (token mode). Pattern: `^[A-Za-z0-9.]+$` (proposal; Client ID format
  unverified).
- `zizmor.yml:36-41` `github-app` ignore for `repos-create.yml` stays; re-run zizmor in case
  `secrets.github-token` in step env trips a rule (unverified).

### 3.4 What it means for the token tests and for least privilege

- `WriteScopeTests` and `test_read_mints_state_exactly_the_scopes_they_need`
  (`test_workflow_tokens.py:78-146`) read only the mint steps' `with:`. They stay and keep their
  meaning, but only for App mode. Their docstring gets one line: "token mode is not scope-checked:
  the caller's token scope is the caller's responsibility (docs/release-flow.md §Credentials)".
- `test_write_jobs_run_nothing_third_party_and_install_nothing` keeps covering the same jobs in
  both modes: the job is the same, only the credential source changes.
- Under Q1=A, the read jobs that install PyYAML or call `check-release-gate` hold the caller's
  (possibly write) token. A new doc-pin test asserts the doc says so, so the statement cannot
  quietly go away.
- repos-*: in App mode a `report` run only ever holds a read token, and the admin-write mint runs
  only when the plan writes (`repos-settings.yml:12-13`). In token mode the one caller token is
  present in report runs too. The docs say so, and say that a token is never minted or revoked by us.

## 4. Steps, in order

### Step 1 — Docs (before any test)
1. `docs/release-flow.md`: §Inputs table (`:423,451,464`) `app-id` -> `client-id` (optional);
   new §Credentials: the two modes, the guard errors verbatim, the both = error rule, the
   least-privilege paragraph and exposure list (Q1); the "must resolve in the CALLER" box
   (`:390-397`) reworded for `client-id`; the caller examples (`:508,539,559`) switched to
   `client-id: ${{ vars.RELEASE_APP_CLIENT_ID }}`, plus ONE token-mode example for `release-plan`.
2. `docs/release-plan.md`, `docs/release-drafts.md`, `docs/release-publish.md`: input/secret tables.
3. `docs/repos-create.md`, `repos-environments.md`, `repos-settings.md`, `repos-variables.md`,
   `docs/repos-register.md` (its App/key section): same.
4. `docs/distribute-env-secrets.md`, `docs/rotate-external-secret.md` (Q2), and the header comment
   caller examples (`distribute-env-secrets.yml:8-19` and the repos-*/release-* headers).
5. `docs/PLATFORM.md` (App onboarding: where the Client ID is found; the new variable),
   `docs/TESTING-STANDARD.md` mention, `README.md` rows if they show inputs.
6. `DECISIONS.md` entry (via `decisions add`): WHY two modes, why the guard is inline, why the scope
   tests are App-mode only, the Q1-Q4 answers as full sentences, and the v6 breaking line. Names
   superseded parts: 2026-10-13 "the App key is a declared secret … `RELEASE_APP_KEY` (required)"
   (`DECISIONS.md:1448`): the key is no longer required. 2026-10-21 "one App key"
   (`DECISIONS.md:718`): reused, unchanged.
7. `TODO.md`: tick the item with evidence; rewrite the §"app-id from the environment" item for
   `client-id` and drop its wrong `RELEASE_FLOW_TREE` clause; add `github-token` to the
   key-recipient catalog item (`TODO.md:"ship the list of workflows that\n  receive the App private key"`).
8. Release-notes lines (for the v6 tag body): "set `client-id` (the App's Client ID, not its ID);
   `app-id`/`app_id` are gone"; "or pass `github-token` instead of the App, never both".

### Step 2 — Tests (red, confirmed failing before any workflow edit)
- `tests/release_flow_workflows/test_workflow_tokens.py`: declared secrets = `{RELEASE_APP_KEY,
  github-token}`, both `required: false` (`:38-39`); key confinement as Q3 (`:46-50`); drafts `if:`
  strings (`:97,100`); `client-id` replaces `app-id` (`:173-175`); the doc example regex and count
  (`:192-204`, 4 -> 5 with the token example); docstring (`:1-18`) rewritten.
- `tests/release_flow_workflows/test_workflow_shape.py`: `:21` secret set; `:137-138,236,302`
  required/input sets lose `app-id`, gain `client-id`.
- NEW `tests/release_flow_workflows/test_auth_modes.py`: every mint has `client-id` and the
  client-id `if:`; no `app-id` anywhere; every token consumer uses the `|| secrets.github-token`
  form; `secrets.github-token` appears nowhere else but the guard; the guard is first in every
  minting job, each with `environment:` (revised, see §3.2); the least-privilege sentence is in the doc.
- NEW `tests/run_auth_mode_tests.py` (stdlib runner, like its siblings) over all 9 files: the same
  structural checks; the guard body byte-identical across the 8 workflows and the composite
  script; and BEHAVIOUR: extract the guard body and run it under `bash -eo pipefail -c` for 6 env
  combos (App only, token only, both, neither, client-id only + token, key only), asserting rc and
  the exact settled message. Reuse the extract helpers in `tests/run_step_tests.py` /
  `tests/action_steps.py` (API unverified; read before use).
- `tests/run_distribute_env_tests.py:147-153` and `tests/run_rotate_external_tests.py:556-611`:
  input/secret names and the mint step's `with:`.
- `Makefile:170-180` `step-bodies`: add `$(PY) tests/run_auth_mode_tests.py`.
- Red proof: `make release-flow` and `make step-bodies` fail, and every failure names a NEW
  assertion (not an import or path error). Record the failing test names in the DECISIONS entry.

### Step 3 — Implement (green)
Edit the 9 workflows + the composite action + `validate-inputs.sh` per §3, then
`python3 scripts/gen_catalog.py` (rewrite `catalog.json`; `make catalog` runs `--check`,
`Makefile:114-115`). No action pin changes: the mint stays at `64ab729…` (`test_workflow_tokens.py:61-64`).

### Step 4 — Refactor
Only if the guard or the `||` expression shows up in more than one shape: pick one shape and let
the byte-identity test enforce it. No behaviour change in this step.

## 5. Dispatcher waves (partitioned by file; no file in two agents of one wave)

Before Wave 1: commit a `wip/` checkpoint if the tree is dirty. Every brief says: never run
`git checkout`/`restore`/`stash`/`reset`/`clean`; no consumer names in any file (public repo).

**Wave 0: gate (dispatcher + owner, not an agent).** A throwaway reusable workflow in this repo
declaring `on.workflow_call.secrets.github-token`, and a caller passing it, on a sandbox branch.
GitHub's parse result is the only evidence (actionlint cannot see it). Needs a push + a run: the
owner approves. Record the run id. A rejection stops the plan here.

**Wave 1: docs** (after Q1-Q4 are answered)
| Agent | Type | Files owned | Brief | Return |
|---|---|---|---|---|
| A | doc-writer | docs/release-flow.md, release-plan.md, release-drafts.md, release-publish.md | §3.1, §3.4, Step 1.1-1.2 | standard contract; list of changed anchors |
| B | doc-writer | docs/repos-create.md, repos-environments.md, repos-settings.md, repos-variables.md, repos-register.md | §3.1, Step 1.3 | same |
| C | doc-writer | docs/distribute-env-secrets.md, rotate-external-secret.md, PLATFORM.md, TESTING-STANDARD.md, README.md | Step 1.4-1.5 (docs only, not the YAML headers) | same |
| dispatcher | — | DECISIONS.md, TODO.md | Step 1.6-1.7 (shared append targets: single writer) | — |

**Wave 2: red tests**
| Agent | Type | Files owned | Brief | Return |
|---|---|---|---|---|
| E | builder (tests only) | tests/release_flow_workflows/test_workflow_tokens.py, test_workflow_shape.py, wf.py, test_auth_modes.py (new) | Step 2, release-flow part | red output: failing test names, count examined |
| F | builder (tests only) | tests/run_auth_mode_tests.py (new), tests/run_distribute_env_tests.py, tests/run_rotate_external_tests.py, Makefile | Step 2, rest | same |

**Wave 3: implement**
| Agent | Type | Files owned | Brief | Return |
|---|---|---|---|---|
| G | builder | .github/workflows/release-plan.yml, release-drafts.yml, release-publish.yml (incl. header comments) | §3.2-3.3; tests of Wave 2 E go green | green output of `make release-flow`, actionlint |
| H | builder | .github/workflows/repos-create.yml, repos-environments.yml, repos-settings.yml, repos-variables.yml | same | green `make step-bodies` part, actionlint |
| I | builder | .github/workflows/distribute-env-secrets.yml, rotate-external-secret.yml, actions/rotate-external-secret/action.yml, validate-inputs.sh, validate-auth.sh (new) | same + §2.3 | same |

**Wave 4: catalog + review**
| Agent | Type | Files owned | Brief | Return |
|---|---|---|---|---|
| J | builder | catalog.json (generated only), zizmor.yml (only if a new finding needs a reasoned ignore) | regenerate, run zizmor | diff stat, zizmor result |
| K | critic (read-only) | none | review the whole diff against this plan + the rulings | findings by severity |

Return contract for every agent: the repo's standard (STATUS / SUMMARY / FILES / RULINGS / TRAPS /
QUESTIONS / EVIDENCE).

## 6. Verification

1. `make ci` (all `CHECKS`, `Makefile:19-23`) prints "N of N checks ran and passed"; run it through
   `runlog -- make ci` to get the real rc. It covers actionlint + shellcheck, zizmor, catalog
   `--check`, doc-examples (actionlints the docs' caller snippets, `Makefile:143-147`), step-bodies,
   release-flow.
2. Counts: `/usr/bin/grep -rn 'app-id:\|app_id' .github/workflows actions` = 0 hits outside
   comments that explain the rename; `client-id:` mints = 20; files with `github-token` secret = 9 (Q2=A).
3. `RELEASE_FLOW_TREE` still equals `git rev-parse HEAD:actions/release-flow` in all four files.
4. Live, before the owner tags (devops-owned sandbox caller, pinned to the merge SHA, owner approves the
   runs): `repos-settings` report-only (a) App mode, (b) `github-token` mode, (c) both: must fail
   at the guard with the settled text, zero API writes. Record the run ids in DECISIONS.md.
5. Live, after the tag: a consumer's release rehearsal on v6.0.0 in App mode with `client-id`.
   That is the consumer's session's run, not ours (repo-awareness rule).
6. Unproven until 4-5: that `secrets.github-token` passed by name reaches an environment-scoped job
   (same mechanism as `RELEASE_APP_KEY`, DECISIONS 2026-10-13, which a rehearsal later proved;
   proof not re-checked here).
