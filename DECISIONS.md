# Decisions — reusable-workflows

## Index

Newest first. Entries below the split live in [`DECISIONS-ARCHIVE.md`](DECISIONS-ARCHIVE.md) —
archived by age only; nothing is deleted, and both files are greppable.

- `2026-07-27` — [`deploy-cloud-run` Summary step fails a successful job when there is no service URL (bug fix)](#2026-07-27-deploy-cloud-run-summary-step-fails-a-successful-job-when-there-is-no-service-url-bug-fix)
- `2026-07-27` — [Secret-distribution workflows refuse values too short to be a credential](#2026-07-27-secret-distribution-workflows-refuse-values-too-short-to-be-a-credential)
- `2026-07-27` — [build-once/promote-to-prod: `build_only`, release-relative GAR retention, and the first tests in this repo](#2026-07-27-build-oncepromote-to-prod-build_only-release-relative-gar-retention-and-the-first-tests-in-this-repo)
- `2026-07-27` — [`DECISIONS.md` restructured: index + age-based archive (no deletions)](#2026-07-27-decisionsmd-restructured-index--age-based-archive-no-deletions)
- `2026-07-27` — [Fleet-wide caller repin to `v1.15.0`, driven by an annotation sweep](#2026-07-27-fleet-wide-caller-repin-to-v1150-driven-by-an-annotation-sweep)
- `2026-07-27` — [`ci-go`/`ci-node`: opt-in README badges close the last test-and-lint parity gap](#2026-07-27-ci-goci-node-opt-in-readme-badges-close-the-last-test-and-lint-parity-gap)
- `2026-07-24` — [actions-group major bumps (#18): Node-24 runner floor is the only breaking change](#2026-07-24-actions-group-major-bumps-18-node-24-runner-floor-is-the-only-breaking-change)
- `2026-07-24` — [`retire-gar-packages` shellcheck SC2020 breaking CI on every PR (bug fix)](#2026-07-24-retire-gar-packages-shellcheck-sc2020-breaking-ci-on-every-pr-bug-fix)
- `2026-07-15` — [`ci-go` secret renamed `github_token` → `go_private_token` (bug fix)](#2026-07-15-ci-go-secret-renamed-github_token-go_private_token-bug-fix)
- `2026-07-15` — [forward-only extended to the stage build workflows (opt-in)](#2026-07-15-forward-only-extended-to-the-stage-build-workflows-opt-in)
- `2026-07-15` — [forward-only guard on `promote-image` (phase 3; opt-in)](#2026-07-15-forward-only-guard-on-promote-image-phase-3-opt-in)
- `2026-07-15` — [live-commit stamping across deploy/promote (phase 2 of the release-process plan)](#2026-07-15-live-commit-stamping-across-deploypromote-phase-2-of-the-release-process-plan)
- `2026-07-15` — [`rollback-service` built; no pin (push-based, not GitOps); triggers stay caller-owned](#2026-07-15-rollback-service-built-no-pin-push-based-not-gitops-triggers-stay-caller-owned)
- `2026-07-15` — [release-process model documented; transient rollback fenced out-of-band](#2026-07-15-release-process-model-documented-transient-rollback-fenced-out-of-band)

<details><summary>Archived — 10 earlier entries in <code>DECISIONS-ARCHIVE.md</code></summary>

- `2026-07-14` — [key-based auth for `promote-image` (quizzing-pro prod parity)](DECISIONS-ARCHIVE.md#2026-07-14-key-based-auth-for-promote-image-quizzing-pro-prod-parity)
- `2026-07-14` — [quizzing-pro convergence: parity audit + `manage-config-secrets`](DECISIONS-ARCHIVE.md#2026-07-14-quizzing-pro-convergence-parity-audit-manage-config-secrets)
- `2026-07-14` — [Deploy-reusable gaps surfaced by the AutoMahn/Traide-Co caller migration (v1.5.0)](DECISIONS-ARCHIVE.md#2026-07-14-deploy-reusable-gaps-surfaced-by-the-automahntraide-co-caller-migration-v150)
- `2026-07-14` — [Capability parity with `zopsmart/workflows`, verified from live callers (v1.4.0)](DECISIONS-ARCHIVE.md#2026-07-14-capability-parity-with-zopsmartworkflows-verified-from-live-callers-v140)
- `2026-07-14` — [Fleet-wide audit; reverse the "deploy/CI kept per-repo" call](DECISIONS-ARCHIVE.md#2026-07-14-fleet-wide-audit-reverse-the-deployci-kept-per-repo-call)
- `2026-07-13` — [Add `rotate-signing-keypair` (v1.2.0, with `rotate-worker-signing-secret`)](DECISIONS-ARCHIVE.md#2026-07-13-add-rotate-signing-keypair-v120-with-rotate-worker-signing-secret)
- `2026-07-13` — [Add `rotate-worker-signing-secret` (v1.2.0)](DECISIONS-ARCHIVE.md#2026-07-13-add-rotate-worker-signing-secret-v120)
- `2026-07-10` — [Make the library genuinely public: de-brand, harden, release properly](DECISIONS-ARCHIVE.md#2026-07-10-make-the-library-genuinely-public-de-brand-harden-release-properly)
- `2026-07-10` — [`sync-bundle-key`: never disable a version a live service still reads](DECISIONS-ARCHIVE.md#2026-07-10-sync-bundle-key-never-disable-a-version-a-live-service-still-reads)
- `2026-07-01` — [Create shared cross-org reusable-workflows host](DECISIONS-ARCHIVE.md#2026-07-01-create-shared-cross-org-reusable-workflows-host)

</details>


> **Release note (2026-07-15): the entries below dated 2026-07-15 all ship in a single
> tag, `v1.11.0`.** Nothing was tagged between `v1.7.0` and this release. The per-phase
> version numbers in the individual entries (`v1.8.0` rollback-service, `v1.9.0`
> live-commit stamping, `v1.10.0` prod forward-only, `v1.11.0` stage forward-only) are
> **logical phase markers**, not separate published tags — they were developed in
> sequence and cut together as `v1.11.0`, which also folds in the `ci-go` secret-rename
> fix. Intermediate numbers `v1.8.0`–`v1.10.0` are intentionally skipped in the tag
> series.

## 2026-07-27 — `deploy-cloud-run` Summary step fails a successful job when there is no service URL (bug fix)

Ships as **`v1.17.1`**. Found by the first real `build_only` run (`Realm-ID/issuer`), not by CI.

**Symptom.** The `build_only` job built the image, pushed it, and set its `image` output — then
the job went red. The failing step was `Summary`, after all real work had succeeded. The image
`api:48cf1c6a…` was in Artifact Registry and correct; only the reporting step failed, so a
working pipeline looked broken and the dependent `promote` job would not run.

**Root cause.** The step ends with

```bash
{ …; [ -n "${URL:-}" ] && echo "- Service URL: $URL"; } >> "$GITHUB_STEP_SUMMARY"
```

The `{ … }` group is the **last statement in the script**, so the script's exit status *is* the
group's, and the group's status is that of its last command. With `URL` empty the trailing
AND-list evaluates false and returns 1 → the step exits 1.

This is **not** `set -e`. `set -e` explicitly exempts a command inside an AND-list, and the first
attempt to reproduce it appeared to pass — because that test had another statement after the
group, which masked the real mechanism. Same construct, opposite result, purely from position.
The reproduction only became faithful once the group was genuinely last.

**Why it was not caught.** `actionlint`/shellcheck do not flag a trailing AND-list (it is valid
and often intentional), and this repo has no way to execute a workflow step — the new fixture
harness covers the `cleanup-gar-images` plan logic only. More to the point, **the bug needs
`URL` to be empty, and before `build_only` that only happened under `dry_run: true`** — a path
nobody had exercised on this workflow. So `build_only` did not introduce the defect, it made a
latent one reachable on the normal path. `dry_run: true` was already silently broken.

**Fix.** Use `if [ -n "$URL" ]; then … fi` so the group's final command always succeeds.
Structural, not a `|| true` suppression: `|| true` would have hidden a real failure in the same
position later.

**Fixed alongside, same block:** `- Mode: \`$MODE\`${DRY_RUN:+ (dry run)}` always printed
"(dry run)", because `DRY_RUN` holds the *string* `false`, which is non-empty. Every summary this
workflow has ever written claimed to be a dry run. It was on the TODO as cosmetic; it is in scope
now because the line was being rewritten anyway.

**Prevention.** The general rule, worth applying beyond this step: **a `{ … } >> $GITHUB_STEP_SUMMARY`
group must not end in a bare conditional.** Two sibling instances were checked —
`manage-config-secrets.yml:361` and `sync-bundle-key.yml:145` — and both are safe: each sits
inside a `while` loop with further statements after it, so neither is the script's last command.
No change needed there. What is still missing is any ability to execute a step in CI; the fixture
harness only reaches embedded Python. Logged in TODO.md.

## 2026-07-27 — Secret-distribution workflows refuse values too short to be a credential

Ships as **`v1.18.0`** (`v1.16.0` is claimed by the unreleased `ci-go`/`ci-node` badges work,
`v1.17.0` by build-once/promote-to-prod).

`sync-bundle-key.yml` and `manage-config-secrets.yml` both validated `payload_json` as
"non-empty JSON object" + "every value is a string" and nothing else. Those two checks are
satisfied by the literal string `-`.

That is not hypothetical. A Traide rotation run in May 2026 **succeeded** while distributing
exactly that value as the R2 credentials; it sat in the `app-secrets` bundle for two months and
surfaced only as the 2026-07-26 object-storage outage. Every layer behaved "correctly" — the
workflow distributed what it was given, Cloud Run mounted it, the app read it. Nothing along the
path had an opinion about whether the value could possibly be a credential.

**New input `min_value_length`, default `8`**, on both workflows: any payload value shorter than
the floor fails the run before anything is written or rolled.

- **Default is on, not off.** An opt-in guard protects only the caller who remembers to opt in,
  which is never the caller who is about to ship a placeholder. Consumers pinned to `v1.15.0` are
  unaffected until they repin, so nothing breaks silently — the floor arrives as a deliberate
  version bump, and `min_value_length: 0` is the documented escape hatch for a caller with a
  legitimately short value.
- **8 characters**, matching the floor Traide's api already enforces at boot (`mustCredEnv`), so
  the distribution path and the consumption path agree rather than each inventing a threshold.
- **The error names the KEY, never the value.** Values are masked secrets; printing a too-short
  one to the run log to explain the failure would be its own leak.
- **Length only — no placeholder pattern-matching.** A denylist of `-`, `changeme`, `TODO` is
  unbounded and gives false confidence. Length is a crude but total check: it cannot be argued
  with, and every real credential clears it.

This does not make a *wrong-but-plausible* credential detectable — a revoked or mis-scoped key is
still well-formed and still distributes. That case is covered downstream by the consumer's boot
probe, not here.
## 2026-07-27 — build-once/promote-to-prod: `build_only`, release-relative GAR retention, and the first tests in this repo

Ships as **`v1.17.0`** (`v1.16.0` is already claimed by the unreleased `ci-go`/`ci-node`
badges work).

**The defect, restated.** The premise going in was that the container repos double-build —
once for stage, once at release. They do not. All five (`AutoMahn/api`,
`AutoMahn/image-service`, `Realm-ID/api`, `Realm-ID/issuer`, `Traide-Co/api`) are a single
`deploy.yml` triggered only on `push: tags`, and there is no stage. The real problem is worse
than a wasted build: **the artifact that ships to production is built at release time, from
source, and has never run anywhere before production.** A re-run or a re-cut tag produces
different bytes than whatever was reviewed — base-image drift, dependency resolution,
`GOPROXY=direct` fallbacks. So the fix is not "stop rebuilding", it is "move the build to
merge-on-`main` and make the release a retag".

**`build_only` on `deploy-cloud-run`.** `deploy_mode` was `update-image | deploy` — both
deploy — so there was no way for `main` to publish `image:<sha>` using the shared build path.
`build_only: true` pushes and stops. It deliberately mirrors `promote-image.yml`'s existing
`deploy_target: none` so the two reusables read as symmetric halves of one flow rather than
two unrelated escape hatches. `service` became optional (validated at runtime: required unless
`build_only`), and `build_only` runs key concurrency per-commit instead of per-service — a
`main` build must not serialise behind a production roll of the same service.

**GAR retention had to change first, and it was the part that could lose data.** Under
build-once the `:<sha>` image *is* the promotion source, but `cleanup-gar-images` treated it as
an ordinary tagged image and deleted it on `tagged_max_age_days` alone; nothing in the keep-set
(live digests + N recent semvers + `keep_tags`) protects an unpromoted build. Shipping
`build_only` without this would have introduced a silent, cycle-time-dependent failure: a slow
release destroys the artifact the release is supposed to promote. New rule, per package: keep
sha images newer than the `sha_retention_releases`-th most recent release.

**Ordered by time, not semver precedence — this is the non-obvious call.** A sha image carries
no semver, so the boundary comparison is time-based no matter what; the only question is how the
*releases* are ranked. Semver ranking breaks on backports: `v3.0.0` released 100 days ago plus a
freshly cut `v2.9.0` would rank `v2.9.0` second and put the boundary at *today*, deleting a
genuine unpromoted `main` build from 60 days ago. Time ordering keeps it. Encoded as fixture T7
so the reasoning survives as an executable regression guard, not a comment.

**Implemented as a keep-only pass, and that structure is the point.** The block may only
`keep.add(...)` — it never appends to `to_delete`, never removes from `keep`, and runs before the
delete loop. This makes "never deletes more than today" true *by construction* rather than by
case analysis, which is what let it ship **on by default**: enabling it can only ever delete
less. Off-by-default would have left silent-destruction as the default behaviour for anyone
adopting build-once. `sha_retention_releases: 0` reproduces the old delete-set exactly (fixture
T13). Timestamps are asymmetric on purpose — `newest()` on the sha side, `oldest()` on the
boundary release — so every ambiguity resolves toward keeping. `buildTime` is excluded because
reproducible builds report 1970-01-01, which would pin every boundary to the epoch.

**Rejected: making window membership sufficient to delete.** Falling outside the window is *not*
grounds for deletion; age is still required. The AND is what preserves monotonicity — without it,
a package that cuts two releases in a day would immediately widen its own delete-set.

**Known asymmetry, documented rather than fixed:** a package with fewer than
`sha_retention_releases + 1` releases has no boundary, so *every* sha image is kept regardless of
age. There is nothing to prove such a sha was superseded. A package that never releases will
accumulate; the doc says to set `sha_retention_releases: 0` there.

**Also fixed while in this code: a latent crash, confirmed by running it.** `semver_imgs.sort()`
compared `(updateTime, version)` tuples, so a single image missing `updateTime` raised
`TypeError: '<' not supported between 'NoneType' and 'str'` and aborted the entire sweep — not a
hypothetical, reproduced against the old code as fixture T18.

**First tests in this repo, and the shape was forced.** The delete-plan algorithm is ~120 lines
of Python inside a `python3 <<'PY'` heredoc that `actionlint`'s shellcheck does not enter — the
code deciding what gets permanently deleted from a registry was entirely unlinted and untested.
It cannot move to `scripts/*.py`: every `actions/checkout` in a reusable workflow checks out the
**caller's** repo, so a script shipped here would not exist at runtime. (Same trap as the
local-composite-action finding recorded 2026-07-15.) So `tests/run_plan_tests.py` **extracts the
heredoc from the workflow file and executes that exact source** against synthetic registries via
a new `PLAN_FIXTURE` env seam. No duplicated algorithm, therefore no drift — if the workflow
changes, the tests test the change.

**The suite was mutation-tested, not just written.** Seven deliberate mutations were injected
into the extracted source (revert the sort fix, rank by semver, disable the pass, flip
`newest`/`oldest` on either side, off-by-one the boundary, drop the `EFF_SEMVER_COUNT` floor,
fail-open on a bad regex); the first pass caught only 5 of 7, and fixtures T21 (divergent
per-field timestamps) and T22 (`keep_semver_count` below the floor) were added specifically to
close the two gaps. Asserting a green suite without checking it can fail would have proved
nothing. The runner additionally re-runs *every* fixture with `sha_retention_releases: 0` and
asserts the window run never deletes anything the legacy run would not — the keep-only invariant
checked structurally rather than case by case.

**Fail closed on a bad `sha_tag_pattern`** (`::error::` + exit 1) rather than silently disabling
the window, matching the existing "zero live digests ⇒ abort" stance. A typo'd pattern that
quietly turned protection off is exactly the failure mode this rule exists to prevent.

## 2026-07-27 — `DECISIONS.md` restructured: index + age-based archive (no deletions)

**Change.** Added a `## Index` (one line per entry, newest first, anchor-linked) at the top of
`DECISIONS.md` and moved the 10 entries older than 2026-07-14 into a sibling
`DECISIONS-ARCHIVE.md`. The index lists archived entries too, behind a `<details>` fold, so it
remains the single answer to "what decisions exist?". Doc maps updated to say *navigate via the
index, never `cat` the file*.

**Why.** The log had reached 1129 lines / 72 KB (infra-provisioning: 712 / 51 KB). At that size
the default read is ~18k tokens, so any agent or human who opens it to append one entry pays for
the entire history — and the newest entries, the ones most likely to matter, are the furthest
from the top. This was measured, not assumed: a review of what consumed context in the
2026-07-27 session put full reads of these two files second only to an unbatched fleet audit.

**Nothing was deleted, and that was the constraint.** The split is by age only; both files are in
the working tree and both are greppable. Verified mechanically rather than by eye: all 20 entries
in each repo were parsed before and after and compared body-for-body — 0 missing, 0 modified.
"It's still in git history" was explicitly rejected as a substitute — an archived file is
greppable by the next agent, a deleted one is only recoverable by someone who already knows to
look for it.

**Rejected: splitting by version or by topic.** Every entry here is from a single month, so a
year-based split does nothing, and a topic split would force a judgement call on every future
entry and break the chronological narrative that makes reversals ("this corrects the same-day
decision above") legible. Age is the only axis that needs no ongoing decisions.

**Tradeoff.** Two files instead of one means a `grep` for a decision must cover both, and the
index needs updating whenever an entry is added. The index is cheap to maintain and the archive
threshold is intentionally coarse — expect to re-split roughly annually, not per release. The
generalised rule (index at ~400 lines, archive at ~600) is recorded in the `decision-log` skill.

## 2026-07-27 — Fleet-wide caller repin to `v1.15.0`, driven by an annotation sweep

**Change.** Repinned every `Just-Git-Dev/reusable-workflows` caller across the platform to
`@v1.15.0` — 26 `uses:` lines in 8 repos, pin-only, **all merged**: `AutoMahn/project#28`,
`AutoMahn/api#27`, `AutoMahn/ui#7`, `AutoMahn/image-service#5`, `AutoMahn/admin-ui#2`,
`AutoMahn/website#2`, `Traide-Co/project#23`, `Realm-ID/project#3`. **`quizzing-pro/api`
deliberately excluded — see below.**

**Why.** A sweep of check-run *annotations* (not just conclusions) over the last 3 runs of
every caller workflow surfaced recurring `Node.js 20 actions are deprecated` warnings on
`ci-go`, `neon-backup`, `deploy-cloud-run`, `deploy-cloudflare-pages` and
`deploy-cluster-keyed` jobs. Every instance traced to a **stale caller pin, not a defect in
the reusable**: `main`/`v1.15.0` already carries the Node-24-era versions
(`checkout@v7.0.1`, `setup-go@v7.0.0`, `setup-node@v7.0.0`, `upload-artifact@v7.0.1`,
`build-push-action@v7.3.0`, `wrangler-action@v4.0.0`). Four of those six arrived in the
Dependabot group bump #18; `upload-artifact@v7.0.1` came in #4 (`3358d35`) and
`wrangler-action@v4.0.0` in #3 (`818c957`) — all six are present at the `v1.15.0` tag.
**18 of the fleet's 27 caller `uses:` lines** were still on `@v1.4.0`/`@v1.5.0`. GitHub
forces Node 24 as the default on 2026-06-16 (already in effect — the annotations say
"being forced to run on Node.js 24"); removal of the Node 20 runtime is announced only as
"later in the fall of 2026", with no firm date. Either way this had a deadline attached.

**The deeper problem this exposes: pin drift is invisible.** Nothing in this repo or the
caller repos notices that a caller is six releases behind — the annotation sweep was manual
and ad hoc. Callers silently miss fixes for months; `bootstrap-alerts`' failure-isolation fix
and `deploy-cloud-run`'s unquoted-`extra_deploy_flags` word-splitting fix were both shipped
and both unconsumed by repos that needed them. Filed in `TODO.md` as a candidate for a
scheduled cross-org pin-drift report.

**Compatibility was proven, not assumed.** Before touching anything, the
`on.workflow_call` `inputs`/`secrets` block of each reusable was parsed at the caller's
current pin and at `v1.15.0` and diffed: no removed inputs, no removed secrets, no newly
required inputs, for all 22 (workflow, old-pin) pairs checked — the 17 distinct pairs actually
repinned, plus `quizzing-pro`'s 4 held-back pairs and the Realm-ID `@v1` pair. This mattered
concretely — `ci-go`'s
`github_token`→`go_private_token` secret rename (v1.11.0) is a real breaking change for any
caller in the `v1.6.0`–`v1.10.0` window; the check confirmed our callers sit at `v1.5.0` and
`v1.11.0`, i.e. either side of it, so none are affected. Guessing here would have broken
`AutoMahn/api`.

**What is *not* proven:** contract compatibility is static. Runtime behaviour on `v1.15.0` is
only exercised by each workflow's next real run. This is stated in every PR body rather than
implied. Several of these are rotation workflows that run rarely or (see below) never.

**Chose `v1.15.0`, not "wait for `v1.16.0`".** `v1.16.0` is gated on the README-badges
dogfood landing in `quizzing-pro/api#2045`, which is itself gated on human merge. Coupling a
deadline-bearing Node-20 fix to an unrelated release gate would have held 26 pin lines hostage to
one PR. The badges work reaches these callers on the next sweep.

**`quizzing-pro/api` held back on purpose.** Its references to 4 distinct reusables
(`ci-go`, `deploy-cluster-keyed`, `manage-config-secrets`, `promote-image`) are at
`@v1.11.0`, but its `main.yaml` is concurrently edited by the open `#2045` (which pins the
`ci-go` job to SHA `3d60a0d`, the squash-merge of #22 on `main`, as the badges dogfood) and
`#2041`. Repinning that file now would conflict with the
very PR that unblocks `v1.16.0`, and would move a live GKE prod deploy/promote path in a
drive-by chore PR. It gets repinned to the tag as part of the `v1.16.0` cut instead.

**A mutable ref was hiding in the fleet.** `Realm-ID/project`'s `cleanup-gar-images.yml` was
pinned to **`@v1`** — the frozen legacy alias this repo's own consumer rule says never to point
new callers at. `v1` resolves to `b96d0e3`, the *original* 5-workflow commit, so that caller had
been running the first-ever version of `cleanup-gar-images` continuously, and would have silently
changed behaviour the moment anyone moved the alias. Now `@v1.15.0`. This is the exact failure the
"pin an exact `vX.Y.Z`" rule exists to prevent, and it survived undetected in a live caller —
further argument for the automated drift report filed in `TODO.md`, which should flag mutable refs
as well as stale ones.

**Process note — the first sweep was incomplete, and that is the point.** The initial pass
enumerated `Just-Git-Dev`, `AutoMahn`, `Traide-Co`, `RevvUp-AI`, `quizzing-pro`, `zop-mannai`
and **missed the `Realm-ID` org entirely**, despite Realm-ID being one of the three projects
`infra-provisioning` onboards. It was caught only because a human named it. A hand-maintained
org list is exactly the wrong source of truth for a fleet audit; the drift report should derive
its org list from something authoritative (e.g. `infra-provisioning/projects/*` plus the CF/GitHub
target configs) rather than from whatever was typed that day.

**Also found, not fixed here** (logged to `infra-provisioning/TODO.md`): `rotate-cloudflare-token`
warns that AutoMahn's CF token lacks `Pages -> Edit`, `R2 -> Edit` and `Workers Scripts -> Edit`
(three HTTP 403s) while the job still reports success; and four rotation workflows have **never
been run at all**, so their IAM paths are unproven in either direction.

## 2026-07-27 — `ci-go`/`ci-node`: opt-in README badges close the last test-and-lint parity gap

**Change.** Both `ci-*` workflows gained a default-off `update_badges` path (plus
`readme_path`, `badge_branch`; `ci-node` also gained `coverage_threshold` +
`coverage_summary_path`, which it had no coverage plumbing for at all). When on, a
third `badges` job rewrites shields.io Coverage + suppression-count badges into the
caller's README and commits the change back on default-branch pushes.

**Why.** `ci-go.yml`'s own header claims it "match[es] zopsmart/workflows test-and-lint
so callers lose nothing on migration". Reading the legacy source rather than a summary
of it showed that was not true: `zopsmart/workflows/.github/workflows/_test-go.yaml`
lines 264-318 install `gobadge`, rewrite the README, count `nolint`s, commit and push —
and `zopsmart/hiring-portal-api`'s README line 3 is exactly those two badges, baked into
the committed markdown. A case-insensitive grep for `badge`/`nolint` across this repo
returned zero hits. A caller migrating off legacy would have silently lost a visible
feature; that blocks the stated goal (`docs/convergence-audit.md`) of dropping
`zopsmart/workflows` entirely.

**This is not hypothetical — a caller has already regressed.** `quizzing-pro/api` was
migrated onto `ci-go.yml@v1.11.0` (its `main.yaml` now mentions `zopsmart/workflows` only
in comments), and its README still carries `Coverage-90.3%` and `nolint_count-78` —
numbers **frozen at the moment of migration**, because nothing has updated them since.
By contrast `quizzing-pro/engine`, still on `zopsmart/workflows/test-and-lint.yaml@main`,
has a badge that is still live. The gap is already costing us on the exact repos the
convergence effort has touched, and it worsens silently with every further migration.
`quizzing-pro/api` is therefore the dogfood target: it is already on our `ci-go`, it has
both badge shapes present (exercising the replace-in-place path against genuine legacy
markup), and its `nolint` count will visibly drop from 78 under the narrower grep —
making deviation 3 below observable rather than merely asserted.

**Options weighed.** (a) A **status/pass-fail lint badge** — cheaper, but not what
legacy produced; a repo migrating would see its `nolint_count-7` badge become something
else. Rejected for parity. (b) A **gist/endpoint badge** (dynamic JSON in a gist,
shields.io `endpoint` URL) — no write access to the caller's repo needed, so branch
protection is a non-issue. Rejected because it changes the README contents on migration
(the URL is different), needs a gist + a PAT with `gist` scope per org, and puts the
badge's availability behind a second service. (c) **Commit-back**, chosen: identical
end state to legacy, no new credential, no external dependency.

**Tradeoffs.** Commit-back is the honest weak point and it is documented as such in
both docs: **branch protection on the default branch will reject the push**, and the
calling job must itself grant `permissions: contents: write` because a reusable
workflow's permissions are capped by its caller. Both are why the feature is
**default-off** — every existing caller keeps a read-only token and is completely
unaffected. Write is scoped to the `badges` job alone; `go`/`go-db`/`node`/`node-db`
stay `contents: read`.

**Four deliberate deviations from the legacy implementation, each a fix:**

1. `go install …/gobadge@latest` → **inline `sed`**. This repo SHA-pins third-party
   actions precisely because these workflows mint creds; an `@latest` tool that
   rewrites a file which is then committed with a write token is the same class of
   supply-chain exposure. The badge is a URL string — it does not need a Go program.
2. `ad-m/github-push-action@v0.8.0` → **plain `git push`**. `convergence-audit.md`
   already lists legacy's `github-push-action@master` as debt to retire; this avoids
   inheriting it. A rebase-once retry covers two callers landing on `main` back to back.
3. `grep -r -E '//\s*nolint' .` → **`grep -rIE --include='*.go' --exclude-dir=vendor`**.
   Legacy counted `.git/`, `vendor/` and binary files, and `\s` is a GNU extension.
   **Our count will be lower than legacy's for the same repo — that is the bug being
   fixed, not a regression**, and it is called out in `docs/ci-go.md` so a migrating
   caller is not surprised by the number dropping.
4. Coverage **measuring is decoupled from gating**. Previously `-coverprofile` only ran
   when `coverage_threshold != 0`; a badge needs the number with no gate. The threshold
   comparison is still applied only when the threshold is non-zero, so existing
   behaviour is byte-for-byte unchanged.

**Correctness.** Badges are matched on alt text and replaced in place, so an existing
legacy badge line is updated rather than duplicated, and a run that changes nothing
makes no commit. That idempotency is the property most likely to break, so the extracted
`run:` bodies were exercised in a GNU-userland container against a README with (a) no
badges, (b) legacy zopsmart badges, (c) already-current badges, plus no-`# `-heading,
zero-suppressions, absent-coverage and missing-README cases — and end-to-end against a
local bare remote, asserting two consecutive passes yield exactly one commit.

**Not yet verified: the push itself.** Nothing about `contents: write`, caller
permission capping, or the push can be exercised locally. Logged in `TODO.md` as a
release gate — `v1.16.0` is not to be tagged until `update_badges` has run on a real
caller against a sandbox `badge_branch`.

**Release.** All new inputs are optional with defaults that preserve current behaviour
exactly → **minor** bump, `v1.16.0`.

## 2026-07-24 — actions-group major bumps (#18): Node-24 runner floor is the only breaking change

**Change.** Dependabot #18 bumped six actions (all SHA-pinned): `actions/checkout`
7.0.0→7.0.1 (patch) plus five **majors** — `setup-go` 6.5.0→**7.0.0**, `setup-node`
6.4.0→**7.0.0**, `docker/setup-buildx-action` 3.12.0→**4.2.0**, `docker/build-push-action`
6.19.2→**7.3.0**, `azure/setup-helm` 4.3.1→**5.0.1**. Merged, then release-notes audited
before cutting a tag.

**Audit result — one load-bearing breaking change: the Node-24 runtime.** Every one of
the five majors is the same ESM/Node-24 migration wave: `runs.using: node24`, which
**requires Actions Runner ≥ v2.327.1**. Everything else was verified non-impacting *for
our usage*:
- `setup-go`/`setup-node` v7 — confirmed against the pinned `action.yml`s that every input
  we pass still exists (`go-version`, `go-version-file`, `cache`; `node-version`, `cache`,
  `cache-dependency-path`). No input renames. We don't set `registry-url`, so the
  setup-node `NODE_AUTH_TOKEN` change is moot.
- `setup-buildx` v4 removed deprecated inputs/outputs — we call it **bare** (no `with:`,
  no `id:`, no outputs referenced), so unaffected.
- `build-push` v7 removed the `DOCKER_BUILD_NO_SUMMARY` / `DOCKER_BUILD_EXPORT_RETENTION_DAYS`
  envs — grep confirms we set neither. All inputs we pass (`context`, `file`, `platforms`,
  `push`, `build-args`, `secrets`, `tags`, `cache-from`, `cache-to`) are unchanged.
- `setup-helm` v5 — used bare (no `version`), behavior unchanged (installs latest).

**Exposure + fix.** All jobs are `runs-on: ubuntu-latest` (GitHub-hosted, already on
runner ≥ 2.336) **except** `ci-go`/`ci-node`, whose `runs_on` input is consumer-supplied
(default `ubuntu-latest`). A consumer pointing those at a **self-hosted runner older than
v2.327.1** will now fail with a runner-too-old error — the one real behavioral change.
Documented the floor at both consumer-facing surfaces: the `runs_on` input `description`
(+ a code comment) in `ci-go.yml`/`ci-node.yml`, and the inputs table in
`docs/ci-go.md`/`docs/ci-node.md`. No invocation changes were needed.

**Release.** No input-contract change, but a new runtime *requirement* for self-hosted
`ci-go`/`ci-node` consumers → cut as a **minor** bump with the runner-floor note called out
in the release notes, not a patch.

## 2026-07-24 — `retire-gar-packages` shellcheck SC2020 breaking CI on every PR (bug fix)

**Symptom.** The `actionlint + shellcheck` CI check went red on `main` immediately after
`retire-gar-packages.yml` landed (run 30076527607), and every subsequent PR — including
the Dependabot actions-group bump (#18) — inherited the same single failure even though
none of them touch that file:
`retire-gar-packages.yml:138:9: SC2020:info: tr replaces sets of chars, not words`.

**Root cause.** The "Verify named packages are dead + plan" step split the `packages`
input with `tr ', ' '\n\n'` — a single `tr` given a *multi-char* SET1 (`, `). That is
correct behavior (comma→newline, space→newline as a char set), but shellcheck's SC2020
flags any multi-char `tr` set as a likely word-replacement mistake, and this repo's CI
fails on **any** shellcheck finding, info-level included.

**Why it wasn't caught.** `actionlint + shellcheck` *is* a required, strict status check
on `main` — but required checks only gate **PR merges**, not direct pushes. Commit
`4706789` has **no associated PR** (verified via the commits→pulls API): the workflow was
pushed **straight to `main`**. The required check ran on that push and *did* report
`failure`, but with `enforce_admins: false` an admin push bypasses both the required
review and the required-check gate, so the red landed anyway. It was also not linted
locally first (`actionlint` was available and would have caught it).

**Fix.** Split into two single-char translations — `tr ',' '\n' | tr ' ' '\n'` — which is
unambiguous, identical in behavior, and does not trip SC2020. `actionlint` now passes
clean locally. No input-contract change (internal script only) → no version bump; folds
into the next tag.

**Prevention.** Land all changes via PR (the required checks already block a red merge —
they only failed to help here because this skipped the PR path). Consider setting
`enforce_admins: true` on `main` so admins can't push past the gate, and run `actionlint`
locally before pushing. Logged to TODO.

## 2026-07-15 — `ci-go` secret renamed `github_token` → `go_private_token` (bug fix)

**Symptom.** The quizzing-pro migration PR (#2041) pinning `ci-go.yml@v1.7.0` failed
to load with *"secret name `github_token` within `workflow_call` can not be used since
it would collide with system reserved name."* — a **parse-time** rejection, so v1.7.0
was un-callable by anyone, not just that repo.

**Root cause.** GitHub reserves `github_token`/`GITHUB_TOKEN` (case-insensitive) as a
secret name inside `workflow_call` — the auto-injected `secrets.GITHUB_TOKEN` owns it.
Declaring a same-named `secrets:` entry is invalid. We named the private-modules token
`github_token` out of habit; it can't be that name.

**Why it wasn't caught.** `actionlint` does not flag the reserved-name collision (it
lints syntax/shell, not this GitHub-side rule), and we had no caller exercising
`go_private` end-to-end before publishing v1.7.0 — the collision only surfaces when a
caller actually invokes the reusable.

**Fix.** Renamed the secret to `go_private_token` (both `secrets.` references + input
description + error text), with an inline comment on the `secrets:` block warning off
the reserved name. Updated `docs/ci-go.md` (secret name + a note + the
`secrets: { go_private_token: ${{ secrets.GITHUB_TOKEN }} }` caller snippet).

**Prevention.** Doc note + code comment record the rule at the collision site. Callers
map their own `GITHUB_TOKEN` (or a cross-repo PAT) into `go_private_token`.

**Contract change, but the broken workflow was un-callable.** The secret name is part
of the input contract, so it needs a fresh tag. The `github_token` secret was
introduced in **v1.6.0** and still present in **v1.7.0** — both are DOA (any caller of
`ci-go` at those tags hits the parse error), so no *working* caller depends on the old
name and this is a **fix, not a break** (no major bump). It ships in the single
**v1.11.0** release cut this session (see the reconciling note at the top of this file).
quizzing-pro/api #2041 re-pins `ci-go` to `@v1.11.0` and renames its `secrets:` key
`github_token` → `go_private_token` (value stays `${{ secrets.PAT }}`).

## 2026-07-15 — forward-only extended to the stage build workflows (opt-in)

**Lifted the forward-only guard onto `deploy-cloud-run` + `deploy-gke-service`** so
stage rejects out-of-order deploys too, not just prod. Same opt-in
`enforce_forward_only`, same "block iff behind" rule, same fail-closed. On the stage
workflows the guard runs **before the build** (it needs only `github.token` + the
checked-out commit), so a blocked deploy wastes no build.

**Why the rule works unchanged on the shared stage env.** "Block iff `behind`"
permits `diverged` — and a `main` squash commit is `diverged` (not `behind`) versus a
`development` tip. So the intentional stage lineage switch (development-tip →
release-candidate) passes, while an actual older/replayed commit is blocked. The
single rule covers stage and prod without a per-env mode, as the model predicted.

**Duplicated the guard step; did NOT extract a composite action — verified, not
assumed.** A `./` local composite action referenced from a *reusable* workflow
resolves against the **caller's** checkout, not the workflow's own repo (confirmed:
GitHub community discussions [#18601](https://github.com/orgs/community/discussions/18601),
[#25289](https://github.com/orgs/community/discussions/25289)). The workarounds
(have every caller check out *our* repo + supply a token, or self-reference by full
`owner/repo/...@sha`) push fragility onto cross-org consumers — the opposite of this
library's contract. So the ~30-line guard is duplicated across the three workflows,
each staying self-contained and independently consumable. Cost: three copies to keep
in sync — the core logic (baseline lookup → compare → block iff behind → fail closed)
is identical; they differ only in the `HEAD` source (`commit_sha`/`github.sha` on
promote, the built `git rev-parse HEAD` on the deploys) and the "release" vs "deploy"
wording.

**Additive/opt-in → v1.11.0.**

## 2026-07-15 — forward-only guard on `promote-image` (phase 3; opt-in)

**Shipped the forward-only guard** — `promote-image` can now reject an out-of-order
(older) release. Completes the three-phase plan (rollback → stamping → guard).
Opt-in via `enforce_forward_only` (default off — runs in others' prod).

**Live-commit source = latest successful GitHub Deployment for the env, not the
running service.** Both were options (the service label/annotation is ground-truth
for what's running). Chose the Deployment record because it is **auth-agnostic** —
read with `github.token`, no cloud auth — so the guard runs *first* and *fails
fast*, before the WIF/key auth and the retag. Reading the live commit off the
service would need cloud auth active before the guard, which the key-based path only
sets up right before the roll (ordering headache). Trade-off accepted: the record
can drift from reality if someone deploys fully out-of-band — but out-of-band deploys
are already against policy, and phase-2 stamping keeps the record in lock-step with
every sanctioned roll.

**Rule = "block iff `behind`."** Compare `live...candidate` via the GitHub compare
API; block only `behind` (candidate is an ancestor of live). `ahead`/`identical`/
`diverged` pass. One rule gives strict latest-only on prod (linear `main` never
diverges) *and* permits a stage lineage switch (a `main` squash is `diverged` vs a
`development` tip, not `behind`) — the same simplification the model called for. No
baseline (first release) ⇒ allow.

**Fails closed.** A compare API error / unknown commit **blocks** rather than
allowing — a safety guard must not wave a release through on a transient error.
Operationally the escape hatch is a re-run or `enforce_forward_only: false`. Chose
fail-closed over fail-open because a silent backward prod deploy is worse than a
blocked release.

**Concurrency re-keyed to per-env** (`deploy-<proj>-<image>-<environment>`, matching
`rollback-service`) so a promote and a rollback for one env can't race — the gap
flagged when `rollback-service` shipped. Falls back to the legacy per-`target_tag`
key when `environment` is empty, so **existing callers are unchanged**.

**Additive/opt-in → v1.10.0.** No behaviour change unless a caller sets
`enforce_forward_only` (and, for the concurrency change, `environment`).

## 2026-07-15 — live-commit stamping across deploy/promote (phase 2 of the release-process plan)

**Shipped stamping in `deploy-cloud-run`, `deploy-gke-service`, `promote-image`** —
the prerequisite for the forward-only guard (phase 3), which needs to read back
"what commit is live" per environment. Each roll now stamps the source commit and,
opt-in, records a GitHub Deployment (the "both" recording choice, matching
`rollback-service`).

- **What is stamped.** Cloud Run → resource label `jgd_commit=<sha>` (label keys are
  slash-free, so no `jgd.dev/…`); GKE (kubectl path) → annotation
  `jgd.dev/commit=<sha>` (annotations allow slashes + arbitrary values). Helm path:
  no annotation (resource name isn't knowable generically) — relies on the
  Deployment record. `commit` is `git rev-parse HEAD` post-checkout for the build
  workflows (the exact built commit, honouring `checkout_ref`), and
  `commit_sha`/`github.sha` for `promote-image` (no checkout there).
- **GitHub Deployment is opt-in via `environment`, and best-effort.** The step only
  fires when `environment != ''`, so **existing callers are untouched** (no new
  required input, no noise). It is wrapped so a Deployments API failure (e.g. the
  caller didn't grant `deployments: write`) **warns but never fails the deploy** —
  the roll already happened; an audit-record hiccup must not break shipping. Body is
  built with `jq` and sends `required_contexts:[]` so creation isn't blocked by the
  (old) commit's status checks.
- **`deployments: write` added** to all three `permissions:` blocks. In a reusable
  this is a ceiling intersected with the caller's grant — absent the grant, the
  best-effort step just warns. Safe to add.
- **Backward-compatible, additive inputs** (`environment`, `record_github_deployment`;
  `commit_sha` on promote). New label/annotation is inert for callers that don't read
  it. → **v1.9.0.**

Phase 3 (opt-in forward-only guard reading these stamps + per-env concurrency
re-key) remains in `TODO.md`.

## 2026-07-15 — `rollback-service` built; no pin (push-based, not GitOps); triggers stay caller-owned

**Shipped `rollback-service.yml`** — the out-of-band transient-rollback bridge the
release-process doc called for. Rolls a running Cloud Run / GKE service back onto an
already-built image (by `vX.Y.Z` tag or `sha256:` digest), **no rebuild, no retag**.
Mirrors `promote-image`'s dual-auth (WIF / key-based) and roll surface
(kubectl/helm/cloud-run), minus the retag, plus live-commit stamping. First of the
three-phase plan (rollback → live-commit stamping → forward-only guard).

**Decision — no pin/freeze.** The design doc originally mandated a pin (fast
rollback freezes promotion so nothing clobbers it). On review that was **imported
from GitOps-reconciler thinking** (Argo/Flux constantly drive cluster state to
"latest tag in git", so a manual rollback is reverted within seconds unless the
reconciler is frozen). This stack is **push-based**: Cloud Run serves the deployed
revision and GKE holds the ReplicaSet image — **no reconciler re-derives desired
state**, so nothing autonomously undoes a rollback. The only re-clobber path is a
human manually re-promoting the bad tag mid-incident. A blanket pin is a heavy fix
for that (it also freezes the *fix*, creating the unpin lifecycle we disliked). If
guarding is ever wanted, **quarantine the specific bad artifact** in `promote-image`
(refuse that digest/tag) — the permanent fix is a *new* tag, so it promotes with no
unpin dance. `rollback-service` therefore sets no pin; quarantine logged in `TODO.md`.

**Live-commit recording = annotation/label + GitHub Deployment (both).** So a later
forward-only check can read back "what is live" per env after a rollback:
Cloud Run resource label `jgd_commit=<sha>` (label keys are slash-free), GKE
annotation `jgd.dev/commit=<sha>`, and a `success` GitHub Deployment on the commit
for the environment (git-native, queryable; opt-out via `record_github_deployment`).
Stamping is skipped when `commit_sha` is empty — callers are pushed to pass it.

**Triggers stay caller-owned — for stage AND prod.** Confirmed both stage
("push to `development`") and prod ("release on `main`") are **defaults, not enforced
by the reusables**. Every workflow here is `workflow_call`; the caller wires the
trigger (tag on `development`, push to `main`, `workflow_dispatch`, … all valid).
`rollback-service` follows suit — `workflow_call` only, caller adds the
`workflow_dispatch`. release-process.md reworded to frame both flows as overridable
defaults.

**Version.** New workflow = additive input contract → **v1.8.0** (doc examples pin
it). No change to existing workflows.

## 2026-07-15 — release-process model documented; transient rollback fenced out-of-band

**Context.** `promote-image` (retag `:<sha>`→`:vX.Y.Z`, no rebuild, roll prod)
already implements the *mechanism* of stage→prod promotion, but the surrounding
**model** — trunk-based flow, what feeds stage, forward-only, and where rollback
fits — was undocumented. Wrote [docs/release-process.md](docs/release-process.md)
to capture it. This entry records the reasoning behind the choices in that doc.

**Trunk-based, build-once, promote-by-retag.** `development` + `main` both feed the
**same stage env**; prod is a retag of a stage-proven digest. Kept because it
guarantees prod runs the identical bytes stage tested — the property `promote-image`
was built for. The load-bearing simplification: the promote decision keys on
**"does `main`'s tip already have a stage-green digest?"**, *not* on the merge
strategy. That single predicate handles ff (already green → promote) and
squash/merge-commit (new SHA → build, stage, then promote) uniformly — which is what
lets callers keep **squash merges** without breaking build-once. Building from
`main`'s own tip (not `development`'s) means stage tests the *exact* prod artifact
even when squash mints a new commit, which is strictly stronger than testing
`development` and shipping `main`.

**Forward-only, all environments.** Rule: reject a deploy whose candidate commit is
an *ancestor of* (already contained in) the env's live commit. On the shared stage
env this must permit a *divergent* commit (a `main` squash is not a descendant of
`development`'s tip) — a strict "must descend" rule would block the release candidate
from reaching stage. On prod the same rule auto-strengthens to strict "latest-only"
because `main` is linear and prod releases only from `main`. **Not yet enforced** —
`promote-image` gates semver but not ancestry; logged in `TODO.md`.

**Rollback split into two actions, and transient rollback fenced OUT of the promote
flow.** The promote pipeline is forward-only and immutable-tag driven; a fast
rollback is a temporary *backward* artifact move. Mixing them would corrupt the
forward-only invariant, so they are kept separate by design:
- **Permanent fix = `git revert` + new linear tag.** The revert commit is a
  *descendant* of the bad commit, so it is forward on the tree and flows through the
  normal promote path unchanged. This is the git-native, cleanly-tracked incident
  record.
- **Transient fast rollback = out-of-band bridge.** Re-select an existing
  prod-proven digest in seconds (no rebuild), valid only until the revert tag ships.
  It **must pin/freeze** the env so normal tag-driven promotion can't re-derive
  "latest tag" and clobber the rollback mid-incident — the pin is the whole point.

**Two steady-states considered for the bridge.** (a) *Tag-driven primary + transient
bridge* — prod = latest linear tag; rollback is an exception path with a temporary
pin. (b) *Always pointer-driven (full GitOps)* — prod = whatever a committed pointer
file says, forever; promote and rollback are one uniform mechanism with no divergence
window. **Chose (a).** It matches how `promote-image` already works (immutable
`vX.Y.Z` tags), keeps the steady state simple, and confines the pointer/pin apparatus
to the incident window instead of maintaining a parallel deploy-state source of truth.
Cost accepted: during the bridge window live-state isn't derivable from tags alone,
which is exactly why the pin is mandatory.

**Fast rollback is only as safe as migrations are backward-compatible** (expand/
contract, N/N+1). A non-backward-compatible migration in the bad release makes the
prior image unrunnable against the migrated schema — then the bridge is off the table
and you must roll forward with a data fix. This is a caller-side discipline the
pipeline can't enforce.

**Separate manual rollback workflow — noted, not built.** A standalone,
manually-triggered reusable (tag/digest input → roll the service + set the pin) would
package the bridge cleanly. Deliberately left as an **independent, future** workflow —
it is orthogonal to the release pipeline and not a dependency of this documentation.
Logged in `TODO.md`.
