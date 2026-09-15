# Survey fixes 1–4 — reusable-workflows

**Status:** in flight, 2026-09-15. Branch `chore/survey-fixes-1-4` off `main`@`dbb3eb9` (v2.7.0).

## Where this came from

After merging the cleanup-caller cleanup into the three project repos (RI #17, AM #45, TH #149),
the owner asked what else needs fixing *in this repo*. A survey produced four items. Each claim
below was verified in this tree on 2026-09-15 — none is taken from `TODO.md` on trust, and two of
them **contradict** what `TODO.md` currently says.

## Decision summary

| # | Item | Shape | Owner input needed? |
|---|---|---|---|
| 1 | `cleanup-cloud-run-revisions.yml` has **zero** executable test coverage | write tests | no |
| 2 | `TODO.md`'s top-ranked 🔴 item rests on a **false premise** | correct the doc | no |
| 3 | `TODO.md`'s consumer pin inventory is **stale** | refresh with real data | no |
| 4a | `v1`-alias drift CI guard — unbuilt | write a check + wire to CI | no |
| 4b | `validate-alerts` vacuity audit (owed to AutoMahn) | audit → findings | only if it finds something |
| 4c | `provenance:`/`sbom:` policy — inherited, not chosen | **a decision** | **YES** |
| 4d | Release ruleset requiring the tag-push check | repo settings | **YES** (outward-facing) |

4c and 4d are deliberately *not* implemented by an agent. 4c is a supply-chain posture choice
(`TODO.md` itself says "genuinely a decision, not a cleanup"); 4d mutates repository settings.
Both get written up with a recommendation and go to the owner.

---

## Item 1 — `cleanup-cloud-run-revisions.yml` has zero test coverage

**Verified:** `grep -rn 'cloud-run-revisions\|REVISIONS' tests/` returns nothing.

This workflow **deletes Cloud Run revisions**, and all three projects repinned to it on
2026-09-15. It is the only deletion workflow in the repo with no executable coverage of its
`run:` bodies — `cleanup-gar-images` has 5 step tests, `retire-gar-packages` has 4,
`cleanup-secret-versions` has 1.

This was Phase 2 item 3 of the composite-action plan the owner dropped on 2026-09-15. The gap is
**independent** of that refactor: nothing about the decision to skip composite actions makes an
untested deletion workflow acceptable.

Nine other workflows are also uncovered and are **out of scope here** (recorded so the next
session does not re-derive the list): `bootstrap-dashboards`, `deploy-cloud-run`,
`deploy-cluster-keyed`, `deploy-gke-service`, `manage-config-secrets`, `neon-backup`,
`rollback-service`, `rotate-cloudflare-token`, `run-db-job`.

### What to cover

The workflow has two `run:` bodies worth executing, both in job `prune`:

- **`Compute prune plan`** (step id `plan`) — a `python3` heredoc that writes
  `/tmp/prune-plan.json` and emits `candidates=` to `$GITHUB_OUTPUT`.
- **`Execute deletions`** (step id `exec`) — reads that plan file and deletes, classifying each
  failure as in-use / already-gone / real failure.

Required cases, at minimum:

1. **The `keep_last` boundary.** A service with more revisions than `keep_last` deletes exactly
   the surplus; one with fewer deletes nothing.
2. **A revision holding traffic is never a candidate** — `latestReadyRevisionName`, a
   `spec.traffic` entry, and a `status.traffic` entry each protect a revision, including when
   that revision is old enough to fall outside the keep window.
3. **`dry_run` deletes nothing.** Note the guard is `if: inputs.dry_run == false` at the *step*
   level, so the step test executes the body directly — the test must assert the body's own
   behaviour, and the dry-run skip is a workflow-level property asserted separately if at all.
4. **The plan → exec hand-off through `/tmp/prune-plan.json`** survives: exec deletes exactly the
   `(service, revision)` pairs the plan named.
5. **Failure classification** — `gcloud` stderr matching "in use" / "not found" is counted as
   skipped, anything else is a real `FAIL` and exits non-zero.

### How the harness works

`tests/run_step_tests.py` (2,481 lines) — `extract_step(workflow, job, step_name)` at
`tests/run_step_tests.py:55` pulls a step's `run:` body straight out of the YAML and executes it
under `bash -eo pipefail` with stubbed commands on `PATH`. There is no copy of the script to
drift. Follow the existing `cleanup-gar-images` tests (call sites at lines 1292, 1345, 1374,
1447, 1607) for the stub idiom.

⚠️ **The body writes to `/tmp/prune-plan.json`, hard-coded.** That is GitHub-runner-correct and
must not be changed to satisfy a test. Point `TMPDIR` or run the body with a stubbed `HOME`/cwd as
the existing tests do — do **not** edit the workflow to make it testable.

---

## Items 2 + 3 — two `TODO.md` claims that are wrong

Both live in `TODO.md` and are owned by one agent so the file has a single writer.

### Item 2 — the 🔴 item's central claim is false

`TODO.md` §"Release hygiene", the item marked 🔴 and "this outranks the original bug", says:

> `docs/PLATFORM.md` carries **three pins at `v1.23.0`**, pointing readers at the frozen legacy
> `v1` line.

**Verified false on 2026-09-15.** `docs/PLATFORM.md` contains no `v1.23.0` anywhere, and no
version pin at all — its examples use the literal placeholder `@vX.Y.Z` (lines 118, 162, 177,
187). `grep -nE '@v?[0-9]+\.|@main|@v1\b' docs/PLATFORM.md` matches exactly one line, :205, which
is prose telling readers to pin an exact tag.

The **structural** point survives and must be kept: `PIN_RE` in `scripts/stamp_version.py`
requires a literal `Just-Git-Dev/reusable-workflows/…`, so `<org>/` placeholder examples are
invisible to both the sweep and the `--check`, and **an uncovered file is indistinguishable from a
passing one**. What is gone is the live instance. Rewrite the item so it describes the real
remaining risk (a future `docs/*.md` silently exempt from the sweep) without sending the next
reader hunting for `v1.23.0` pins that do not exist.

The repo is currently swept consistently: `python3 scripts/stamp_version.py --check --expect
v2.7.0` → "version sweep is consistent at v2.7.0 (26 workflows, 49 doc pins)", exit 0.

### Item 3 — the consumer pin inventory is stale

`TODO.md` §"Consumer pin inventory" reports AutoMahn's 2026-09-06 numbers ("14 callers across
THREE versions", "`cleanup-gar-images.yml:56` still v2.4.0"). Six of those pins moved to `v2.7.0`
on 2026-09-15 and the section does not know it.

**Real current state**, from this repo's own tool
(`python3 scripts/fleet_drift.py --orgs Realm-ID,Traide-Co,AutoMahn`), raw JSON saved at
`../.scratch/fleet.json`:

- **57 caller lines total — 37 STALE, 20 OK, 0 MUTABLE.**
- Spread `v2.3.1` → `v2.5.0`.
- **Zero mutable pins** — no caller is on `@main` or `@v1`, so the supply-chain risk that
  motivated the section is not currently live anywhere.
- Deepest stragglers are on the **deploy path**: `Realm-ID/api` and `Realm-ID/issuer`
  `deploy.yml` pin `deploy-cloud-run` and `promote-image` at `v2.3.1`, four minors behind.

Replace the narrative numbers with the tool invocation and the current summary, and say plainly
that the repin itself is **consumer-repo work, not this repo's**. Keep the existing warning that
each pin needs its own contract diff before moving — that is still right.

---

## Item 4a — `v1`-alias drift CI guard

`TODO.md` §"Two items rehomed", first bullet. `v1` is a frozen legacy alias; nothing verifies it
still resolves to the newest `v1.x` tag, so it can drift behind and a legacy caller silently gets
an older input contract than `v1` implies.

Wanted as a release-time check alongside the `WORKFLOW_VERSION` stamp sweep, which has the same
failure shape. Wire it into `.github/workflows/ci.yml` as its own job, consistent with the ten
jobs already there.

⚠️ **Make it fail loudly rather than skip.** The whole `v2.6.1` lesson in this repo's `TODO.md` is
a gate that fired correctly and was ignored; the companion failure is a gate that goes green
because it could not run. If the `v1` tag or the `v1.x` series cannot be resolved, that is a
failure, not a skip. Give it a `--self-test` so it is not passing vacuously.

## Item 4b — `validate-alerts` vacuity audit (owed to AutoMahn)

`TODO.md` §"Two items rehomed", second bullet. The linter's checks were reviewed for MQL
execution (closed 2026-09-01) but **not** for two classes it may pass vacuously:

1. a threshold compared against a value the **policy itself derives**, and
2. a check that **assumes a scope** the policy never declares.

This is an audit, not a rewrite: the deliverable is a findings list with `path:line` evidence and
a verdict per check — sound / vacuous / cannot tell. Fixes, if any, are a separate pass.

Context worth carrying: `TODO.md` notes two independent vacuity findings in this one layer, and
says that "says something about how those gates are written."

## Items 4c + 4d — write up, do NOT implement

- **4c `provenance:`/`sbom:`** — neither `deploy-cloud-run.yml` nor `promote-image.yml` sets
  either, so buildx's default applies and every push adds an attestation manifest. Those are the
  `unknown/unknown` children `cleanup-gar-images` already reasons about. Options named in
  `TODO.md`: keep the default and document why; set `provenance: false` and say what is lost; or
  expose it as a `workflow_call` input. It trades real SLSA metadata against registry tidiness in
  a repo that SHA-pins every third-party action precisely because that class of guarantee matters.
- **4d release ruleset** — require the tag-push CI check green before a release can publish.
  `TODO.md` prefers a ruleset over any new script. Price it; do not create it.

Deliverable for both: one options doc with a recommendation, for the owner to choose from.

---

## Execution

Five agents, wave 1, disjoint file ownership. **No agent runs any git command** — the dispatcher
owns all git, so five concurrent workers cannot race on `.git/index.lock`, and no agent can reach
for `git checkout`/`restore`/`stash`/`reset` when its own edit goes wrong.

| agent | item | owns |
|---|---|---|
| `builder` | 1 | `tests/run_step_tests.py` |
| `builder` | 2 + 3 | `TODO.md` |
| `builder` | 4a | `scripts/check_v1_alias.py` (new), `.github/workflows/ci.yml` |
| `investigator` | 4b | nothing (read-only) |
| `architect` | 4c + 4d | `plans/provenance-and-release-gate.md` (new) |

Wave 2: apply any 4b findings, then a `DECISIONS.md` entry covering all of it — plus the
cross-repo probe finding below, which is currently recorded nowhere git-backed.

## The probe finding (record in `DECISIONS.md`, wave 2)

**`uses: ./actions/x` inside a reusable workflow called cross-repo resolves against the CALLER's
workspace, not the workflow's own repo.** Probe run `Realm-ID/project` 34952087036:
`Can't find 'action.yml' … under '/home/runner/work/project/project/actions/probe'`.
A remote SHA-pinned `Just-Git-Dev/reusable-workflows/actions/x@<40-hex>` **does** work with no
checkout (run 34952240998). This is why the 2026-09-15 composite-action refactor was abandoned in
favour of deleting the consumers' `resolve` jobs.
