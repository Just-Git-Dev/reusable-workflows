# Decisions — reusable-workflows

## Index

Newest first. Entries below the split live in [`DECISIONS-ARCHIVE.md`](DECISIONS-ARCHIVE.md) —
archived by age only; nothing is deleted, and both files are greppable.

- `2026-09-05` — [The pin gate is verified by running it, not by grepping for it](#2026-09-05--the-pin-gate-is-verified-by-running-it-not-by-grepping-for-it)
- `2026-09-05` — [The `testing` skill becomes source of truth; TESTING-STANDARD.md follows it](#2026-09-05--the-testing-skill-becomes-source-of-truth-testing-standardmd-follows-it)
- `2026-09-01` — [RCA: testing the MQL layer found two bugs in it — a missing query list read as "zero, all fine", and a GNU-only word boundary](#2026-09-01--rca-testing-the-mql-layer-found-two-bugs-in-it--a-missing-query-list-read-as-zero-all-fine-and-a-gnu-only-word-boundary)
- `2026-09-01` — [`validate-alerts` executed MQL only: PromQL passed a lint and was never run](#2026-09-01--validate-alerts-executed-mql-only-promql-passed-a-lint-and-was-never-run)
- `2026-08-25` — [A testing standard ships as docs, before it ships as a reusable workflow](#2026-08-25--a-testing-standard-ships-as-docs-before-it-ships-as-a-reusable-workflow)
- `2026-08-24` — [`cloud-run-update`: empty means "do not touch", and it never deploys an image](#2026-08-24--cloud-run-update-empty-means-do-not-touch-and-it-never-deploys-an-image)
- `2026-08-24` — [`bootstrap-cf-dns`: the full-ruleset PUT was deleting another workflow's Origin Rules](#2026-08-24--bootstrap-cf-dns-the-full-ruleset-put-was-deleting-another-workflows-origin-rules)
- `2026-08-24` — [`bootstrap-cf-service`: two routes to one hostname, and the origin host stops being hand-copied](#2026-08-24--bootstrap-cf-service-two-routes-to-one-hostname-and-the-origin-host-stops-being-hand-copied)
- `2026-08-24` — [`deploy-cloudflare-worker`: wrangler owns the worker's config, this workflow owns everything around the deploy](#2026-08-24--deploy-cloudflare-worker-wrangler-owns-the-workers-config-this-workflow-owns-everything-around-the-deploy)
- `2026-08-24` — [RCA: the sweep demanded a project-wide role to check a typo, and collapsed multi-secret lists](#2026-08-24--rca-the-sweep-demanded-a-project-wide-role-to-check-a-typo-and-collapsed-multi-secret-lists)
- `2026-08-21` — [`setup-buildx-action` 4.3.0 merged without a release: a tag is a fleet event, a patch bump is not](#2026-08-21--setup-buildx-action-430-merged-without-a-release-a-tag-is-a-fleet-event-a-patch-bump-is-not)
- `2026-08-21` — [v2.4.0: `buildcache` leaves the default keep-set — a moving tag the default policy forbids](#2026-08-21--v240-buildcache-leaves-the-default-keep-set--a-moving-tag-the-default-policy-forbids)
- `2026-08-21` — [Three workflows shipped undocumented; a generator cannot catch absence from a hand-maintained list](#2026-08-21--three-workflows-shipped-undocumented-a-generator-cannot-catch-absence-from-a-hand-maintained-list)
- `2026-08-20` — [Three writers of one secret blob held three different locks (bug fix)](#2026-08-20--three-writers-of-one-secret-blob-held-three-different-locks-bug-fix)
- `2026-08-17` — [Delayed destruction (`version_destroy_ttl`) exists — it simplifies the sweeper but does not replace it](#2026-08-17--delayed-destruction-version_destroy_ttl-exists--it-simplifies-the-sweeper-but-does-not-replace-it)
- `2026-08-17` — [`keep_enabled_count` on the writers: disable is inline, destroy stays in the sweeper](#2026-08-17--keep_enabled_count-on-the-writers-disable-is-inline-destroy-stays-in-the-sweeper)
- `2026-08-16` — [`cleanup-secret-versions`: quarantine, not deletion — and the `:latest`-resolves-at-deploy premise was wrong](#2026-08-16--cleanup-secret-versions-quarantine-not-deletion--and-the-latest-resolves-at-deploy-premise-was-wrong)
- `2026-08-13` — [`cleanup_latest_tag` (v2.2.0): a stranded `:latest` is cleaned by the sweep that strands it, as a convergence rule](#2026-08-13--cleanup_latest_tag-v220-a-stranded-latest-is-cleaned-by-the-sweep-that-strands-it-as-a-convergence-rule)
- `2026-08-13` — [Fleet repinned to v2.1.2: drift is closed to zero on a behaviour-neutral tag, deliberately](#2026-08-13--fleet-repinned-to-v212-drift-is-closed-to-zero-on-a-behaviour-neutral-tag-deliberately)
- `2026-08-13` — [`retire-gar-packages` handles immutability, and preserves it rather than deciding it](#2026-08-13--retire-gar-packages-handles-immutability-and-preserves-it-rather-than-deciding-it)
- `2026-08-12` — [A locked repo the sweep cannot unlock degrades to untagged-only instead of failing](#2026-08-12--a-locked-repo-the-sweep-cannot-unlock-degrades-to-untagged-only-instead-of-failing)
- `2026-08-12` — [`cleanup-gar-images` v2.1.0: the sweep now ENABLES immutable tags, it does not merely restore them](#2026-08-12--cleanup-gar-images-v210-the-sweep-now-enables-immutable-tags-it-does-not-merely-restore-them)
- `2026-08-11` — [`cleanup-gar-images` plans are mostly impossible fleet-wide; one caller stalled completely (bug fix)](#2026-08-11--cleanup-gar-images-plans-are-mostly-impossible-fleet-wide-one-caller-stalled-completely-bug-fix)
- `2026-08-11` — [`badge_insert`: default-on badges may still be given to a repo, but it is now a nameable choice](#2026-08-11--badge_insert-default-on-badges-may-still-be-given-to-a-repo-but-it-is-now-a-nameable-choice)
- `2026-08-11` — [`cleanup-gar-images` v2.0.0: retention is release-relative, not age-based](#2026-08-11--cleanup-gar-images-v200-retention-is-release-relative-not-age-based)
- `2026-08-11` — [Hard-error audit: a badge push failure could fail a caller's CI (bug fix)](#2026-08-11--hard-error-audit-a-badge-push-failure-could-fail-a-callers-ci-bug-fix)
- `2026-08-11` — [The GAR 105-vs-103 delta is a wall-clock boundary crossing, not a logic change (root cause; corrects the earlier correction)](#2026-08-11--the-gar-105-vs-103-delta-is-a-wall-clock-boundary-crossing-not-a-logic-change-root-cause-corrects-the-earlier-correction)
- `2026-08-11` — [Opt-in `node_modules` caching on `ci-node` and `deploy-cloudflare-pages`; Pages gains a separate `install_command`](#2026-08-11--opt-in-node_modules-caching-on-ci-node-and-deploy-cloudflare-pages-pages-gains-a-separate-install_command)
- `2026-08-11` — [Release version sweep automated: doc pins + a `WORKFLOW_VERSION` stamp, enforced twice](#2026-08-11--release-version-sweep-automated-doc-pins--a-workflow_version-stamp-enforced-twice)
- `2026-08-11` — [`deploy-cloudflare-pages` gains an opt-in, blocking post-deploy smoke check](#2026-08-11--deploy-cloudflare-pages-gains-an-opt-in-blocking-post-deploy-smoke-check)
- `2026-08-11` — [`cleanup-gar-images` unlocks and relocks immutable tags, and fails closed on both ends](#2026-08-11--cleanup-gar-images-unlocks-and-relocks-immutable-tags-and-fails-closed-on-both-ends)
- `2026-08-11` — [Onboarding retrospective: a generated contract file, an agent guide, and CI that keeps both honest](#2026-08-11--onboarding-retrospective-a-generated-contract-file-an-agent-guide-and-ci-that-keeps-both-honest)
- `2026-08-11` — [The `cleanup-gar-images` "keep-only" invariant is not true (correction)](#2026-08-11--the-cleanup-gar-images-keep-only-invariant-is-not-true-correction)
- `2026-08-11` — [Default-on badges must not fail CI for callers without a coverage report (bug fix)](#2026-08-11--default-on-badges-must-not-fail-ci-for-callers-without-a-coverage-report-bug-fix)
- `2026-08-11` — [README badges on by default; the badge job stops dictating caller permissions](#2026-08-11--readme-badges-on-by-default-the-badge-job-stops-dictating-caller-permissions)
- `2026-08-11` — [Private npm registry auth on `ci-node` + `deploy-cloudflare-pages`, delegated to `setup-node`](#2026-08-11-private-npm-registry-auth-on-ci-node--deploy-cloudflare-pages-delegated-to-setup-node)
- `2026-07-28` — [`promote-image` races the build it promotes from: bounded `source_wait_seconds`, plus the first executable `run:`-body tests (bug fix)](#2026-07-28-promote-image-races-the-build-it-promotes-from-bounded-source_wait_seconds-plus-the-first-executable-run-body-tests-bug-fix)
- `2026-07-28` — [`run-db-job` built; `docker_target` added; the runner-side prebuild hook deliberately left out](#2026-07-28-run-db-job-built-docker_target-added-the-runner-side-prebuild-hook-deliberately-left-out)
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

## 2026-09-05 — The pin gate is verified by running it, not by grepping for it

**Context.** Consumer repos carry a `pinned` gate in `workflow-hygiene.yml` that rejects
unpinned third-party actions while exempting first-party
`Just-Git-Dev/reusable-workflows/...@vX.Y.Z` refs, because semver there tracks the input
contract (2026-07-01, ADR-001). Three sessions in one day tried to confirm that exemption had
landed across the fleet by grepping for its *implementation*:

```bash
grep -c "grep -v 'Just-Git-Dev/reusable-workflows/'" <file>
```

Two of the three got `0` and concluded the fix was missing — one filed it as a P1 against four
repos. Both zeroes were measurement errors: one session guessed a filename that does not exist,
the other ran from the wrong directory. `grep -c` returns `0` for "path does not resolve", not
an error, so absence of the file and absence of the fix are indistinguishable in its output.

**Decision.** Ship `scripts/pin_gate_behaviour.sh` and verify the gate behaviourally. It
extracts the `Reject mutable action refs` step's `run:` body from each repo's own
`workflow-hygiene.yml` (`scripts/pin_gate_extract.py`, stdlib only) and executes it against
four inputs: the repo's real tree, a planted `actions/checkout@v4`, a planted first-party
`@v2.6.0`, and a planted `Just-Git-Dev/other-repo@main`. Verdicts come from the gate's own exit
status.

**Why, beyond "the grep was wrong".**

- *A grep for an implementation is not a test of a behaviour.* It reports green for a `grep -v`
  that is present but broken, and red for a correct regex-only implementation. It errs in both
  directions, which is worse than a check that errs in one.
- *The harness must run the repo's gate, not a copy of it.* The first draft pasted the pipeline
  into the test. That draft would have gone green against a repo whose real gate was broken —
  reproducing the exact defect it was written to detect. The file header says never to
  reintroduce a local copy.
- *Under GNU grep, in a container.* Dev laptops here resolve `grep` to ugrep, whose `-P` differs
  from CI's. A host pass is not evidence about CI.
- *The fourth assertion exists to catch a widened exemption.* Assertions 1-3 all still pass if
  someone broadens the exclusion from the `reusable-workflows` path to the whole `Just-Git-Dev`
  org. Only a first-party ref that *must* be rejected distinguishes an exemption from a hole.
- *Vacuity is reported, not silently banked.* "The gate accepts the real tree" proves nothing in
  a repo with zero first-party callers — 7 of the 14 audited. Those print `VACUOUS` and name the
  assertion actually carrying their coverage.
- *`--self-test` mutates a known-good gate three ways* (exemption deleted, exemption widened to
  the org, matcher neutered) and requires the harness to go red on each, alongside an unmutated
  control that must stay green. A checker whose red path nobody has watched fire is not evidence.

**Not wired to CI, deliberately.** Its subjects are sibling consumer repos absent from this
repo's checkout, so a CI job here would find nothing to test and go green — the inert-gate
failure the script exists to catch. It is an operator tool: run it by hand when the gate changes
or when a repo's copy is in doubt.

**Result.** 14 repos across RI, Traide and AutoMahn: all four assertions pass in every one, and
the P1 was withdrawn. The alleged bug was never real; had it been, the `no-exemption` mutant in
the self-test shows exactly the output it would have produced.

**Two defects found by running the harness rather than reading it.** It reused a single staging
path, so two back-to-back runs raced Docker Desktop's file sharing and the second saw an empty
mount — it now stages per-PID. And an empty mount iterated the literal glob and printed a `FAIL`
attributed to a repo it had never read; it now exits 2. A harness that can return a verdict
about a tree it did not read is worse than one that crashes.
## 2026-09-05 — The `testing` skill becomes source of truth; TESTING-STANDARD.md follows it

**What.** `docs/TESTING-STANDARD.md` now declares the `testing` skill as source of truth and
positions itself as that skill's umbrella-repo application. Seven rules derived from auditing
RI, Traide and AutoMahn were written into the skill; this document gained a pointer on each
principle the skill now owns (P1, P2, P3, P5, P6, P7, P9), one new failure mode (§1.7), one new
principle (11), a sixth layer in the layer cake, three scorecard blocks and seven anti-pattern
rows. README's "ten principles" was corrected to eleven.

**Why one of them had to win.** The two documents had converged independently on the same rules
— this file's Principle 1 is the skill's §9, Principle 7 is its §14 — and were beginning to
diverge on others: Principle 2's SUT-span rule was strictly sharper than the skill's "E2E lives
in the umbrella", while the skill had material (the skip taxonomy, guard self-tests, the
test-result cache) this file lacked. Two documents drifting on one subject is the failure both
of them warn about. The skill is the one loaded into every session on every project, so it is
the one that must be right; a document that only some repos read cannot be the authority.

**Why this document still exists.** The skill is project-agnostic. The failure modes here —
a gate that spans repos it does not contain, a cross-repo checkout credential, a guard that is
inert in CI because nothing checks out the sibling — only appear at a repository boundary, and
that is what this file is for. Where a principle is the skill's rule wearing a cross-repo hat it
now says so and cites the section, rather than restating it in words that will drift.

**What the audit actually found**, for the record, since it is what these edits are made of:
- `Realm-ID/api`'s `await_ci` exits 0 when no CI run exists for the tagged SHA, which is the
  shape that let `issuer` promote a red CI to prod in v0.106.0. **It is not an unported fix**,
  which is what a first pass here recorded and what this bullet said until the claim was
  checked: `api/.github/workflows/deploy.yml:173-186` carries a dated (2026-08-31) note saying
  the asymmetry with `issuer` is deliberate and must not be "made consistent" without
  re-checking why — the issuer needs its walk-back because `issuer/tests.yml` has
  `paths-ignore`, while `api/ci.yml` has none and triggers on `branches: ['**']`, so the branch
  is unreachable there. It is a real §1.7 hazard for a different reason: the fact that makes it
  safe lives in a different file in a different repo, so adding a `paths-ignore` to `api/ci.yml`
  reopens the v0.106.0 hole silently. Rationale: root `DECISIONS.md` 2026-08-31.
- `automahn/api/scripts/check-request-struct-coverage.sh` resolves `../ui/e2e` and exits 0 when
  it is absent. No CI job checks out `ui`, so it has never run there — while ADR-033 and
  `ui/e2e/README.md` both describe it as a CI gate. That is §1.7, and it is why §1.7 is here.
- 1 of 15 AutoMahn guards has a `--self-test`. The unburned ones include the ADR-047
  cross-tenant backstop, whose failure mode is a regex that silently matches nothing.
- 193 skips across the three projects, concentrated on tests named as *proofs*, and the worst
  shape is a skip guarded by the test's own two-subject precondition.

**Not changed.** Principles 4, 8 and 10 are umbrella-specific and have no skill counterpart;
they stand as written. Nothing in the skill was weakened to accommodate this file.

## 2026-09-01 — RCA: testing the MQL layer found two bugs in it — a missing query list read as "zero, all fine", and a GNU-only word boundary

Mirroring the new PromQL tests onto the MQL execution layer (the follow-up opened earlier the
same day) was expected to be mechanical. It found two live defects instead — which is the
argument for having written them, and a reminder that the untested half of a pair is untested
regardless of how closely it resembles the tested half.

**Symptom** — neither had reached a user. Both were found by the first tests ever pointed at
this step:
1. With `mql_queries.txt` absent, the step printed `All 0 MQL query/queries validated.` and
   exited **0**.
2. The `| condition` strip silently did nothing under any non-GNU `sed`, so the alerting-only
   clause would be POSTed to `timeSeries.query`, which rejects it — every MQL policy failing
   validation for a reason that is not the policy's fault.

**Root cause**
1. `done < "$TMPD/mql_queries.txt"` was assumed to abort the step when the file is missing. It
   does not: under `set -e` the failed redirect kills the loop, not the script, and execution
   continues to the success print with `COUNT=0`. The PromQL layer, written hours earlier, had
   an explicit guard for exactly this — the assumption was never carried back to the older step.
2. `sed -E '…condition\b…'`. `\b` is a **GNU extension**, not POSIX ERE. GitHub's ubuntu
   runners ship GNU sed, so the pattern works in production and the defect is invisible there.
   Any other sed treats it as a literal `b`, the line never matches, and the strip becomes a
   no-op with no error.

**Why it wasn't caught** — `validate-alerts` had **zero** tests until today. It could not have
them: every step wrote to hardcoded `/tmp` paths that `tests/run_step_tests.py` cannot isolate.
So the repo's own validation workflow was the one workflow whose bodies had never been executed
by anything but a live run. Both bugs are also the sort CI structurally cannot see — #1 needs a
state (no query list) that only arises if the lint didn't run, and #2 is invisible on the exact
platform CI uses.

**Fix**
1. The MQL step now checks for the query list explicitly and exits 1 if it is absent, matching
   the PromQL layer: an empty list is the normal no-MQL-policies case; a *missing* one means the
   lint did not run, and "could not check" is never "checked and fine."
2. The word boundary is spelled out as `condition([[:space:]]|$)` — POSIX ERE, identical
   behaviour on GNU and BSD sed. Verified both ways.

Both fixes address the root cause rather than the symptom: the guard makes the failure mode
impossible to reach silently, and the portable pattern removes the platform dependency instead
of documenting it.

**Prevention** — 23 further step-body tests, so both execution layers now hold the same
contract under test: valid query passes and is counted; the query travels in the right shape
(JSON body for MQL, url-encoded form for PromQL) to the right endpoint; `| condition` is
stripped but the pipeline survives; empty list passes with a zero count; missing list fails
with none; `400` fails and surfaces the API's message; `403` exits and writes no count; an
unexpected status is a failure; every query runs, and one bad one among many fails the step.
Each of four mutations — removing the guard, reverting `\b`, downgrading `403` to a warning,
treating `400` as a pass — was confirmed to fail them. The wider lesson is already in
`TODO.md`: **"clean locally" and "clean in CI" are different claims**, and this is the second
instance this week (shellcheck 0.11.0 disagreeing with the runner's was the first).


## 2026-09-01 — `validate-alerts` executed MQL only: PromQL passed a lint and was never run

**The gap.** Layer 2 ran `projects.timeSeries.query` for `conditionMonitoringQueryLanguage`
and nothing else. `conditionPrometheusQueryLanguage` was in the accepted-kinds set, so it
cleared the offline structural lint and then fell through the execution branch untouched — a
PromQL policy earned a green tick from a workflow whose entire reason for existing is that a
lint cannot catch a semantically invalid query. That is THE PATTERN this repo keeps hitting: a
clean report over a surface nothing actually read.

**Why now, ahead of any caller.** No policy in the fleet uses PromQL today, so this fixes
nothing currently broken. It is deliberately pre-emptive: metrics ingested through Managed
Prometheus/OTel land as `prometheus.googleapis.com/<name>/<kind>` and are queried in PromQL, so
every application-level alert policy the fleet is about to grow takes this path (see
`infra-provisioning/DECISIONS.md` 2026-09-01). Landing the gate first means the first such
policy cannot merge lint-only. Fixing it after would mean trusting whatever had already shipped.

**What it does.** `conditionPrometheusQueryLanguage` queries are collected by the lint
alongside the MQL ones and POSTed to the Prometheus-compatible read endpoint,
`v1/projects/<p>/location/global/prometheus/api/v1/query`. New `promql_checked` output
mirroring `mql_checked`, plus `promql_found` in the summary. No new inputs, no new IAM:
`monitoring.timeSeries.list` covers both read paths, so an existing caller gains the check with
no change at all.

Two rules the new layer holds that are worth stating, because both are ways a validator lies:

- **A 2xx is not consent.** The Prometheus API can answer `200` carrying
  `{"status":"error", …}`. Reading only the HTTP code — the obvious implementation, and what
  the MQL layer can get away with because `timeSeries.query` does not do this — would pass a
  rejected query. The step parses the envelope.
- **"Could not check" is never "checked and fine."** `401`/`403` exits the step and writes *no*
  `promql_checked` at all, rather than reporting `0` validated queries as a pass. Same rule as
  the MQL layer, restated because it is the one that decays first.

**Testability was a design constraint, not an afterthought.** The step bodies wrote to
hardcoded `/tmp` paths, which `tests/run_step_tests.py` cannot isolate — which is why
`validate-alerts` had **zero** tests despite being the repo's validation workflow. All three
steps now resolve their scratch paths through `${RUNNER_TEMP:-/tmp}` (the idiom
`deploy-cloudflare-pages` already uses). That seam is what makes the 21 new step-body tests
possible; they execute the shipped bodies verbatim, and three mutations — deleting the
envelope check, downgrading `403` to a warning, dropping the lint's query collection — were
each confirmed to fail them.

**Not done here:** no version bump. `scripts/stamp_version.py --check` asserts the tree agrees
with *itself*, so the stamp moves at release-sweep time, not in this PR. The additive output
makes the next release a minor.


## 2026-08-25 — A testing standard ships as docs, before it ships as a reusable workflow

`docs/TESTING-STANDARD.md` is the first document here that is not about a workflow in
this repo. It describes the **umbrella-repo testing pattern**: how a repository gates
code it does not contain, the six mechanisms by which a CI gate ends up green without
ever having run, and ten principles plus an adoption scorecard derived from fixing them.

Two decisions are embedded in shipping it this way.

**It goes in `reusable-workflows`, not in an app repo or the private access repo.** The
audit that produced it covered three platforms; a document filed in one of them is
invisible to the other two. This repo is already the fleet's public, shared-ops surface
and the only one every platform reads. It is also the repo whose `ci-go`/`ci-node`
bodies the standard tells callers to adopt — the guidance and the mechanism now sit
together. The document is deliberately **project-agnostic**: no org, repo, service or
hostname appears in it, so it can be published as-is or dropped into a template repo by
someone outside this fleet. The three per-project remediation briefs live separately, in
`infra-provisioning/projects/<key>/TESTING-HANDOFF.md`.

**It is documentation, not a workflow — for now, and on purpose.** The obvious next step
is an `e2e-compose.yml` reusable: sibling checkout by ref, mandatory credential presence
check, ref echo, `compose run --rm --build`, artifact upload on failure, teardown on
always. That would collapse several hundred lines of near-duplicate YAML across two
umbrella repos. It is not being written yet, because the two existing implementations
still disagree on the shape of the thing being abstracted — one drives four compose tiers
inline from workflow YAML, the other drives a single shared `stack.sh` through a shim. An
input contract frozen across that disagreement would encode the disagreement. The
standard's §3.3 verb contract (`up · down · seed · reset-data · test · logs`) is the
convergence target; once both umbrellas call a driver rather than compose directly, the
reusable has one shape to serve and can be cut against a real second caller instead of a
hypothesis. Same rule as everywhere else here: everything in this repo is a
`workflow_call` input, and a body written for one caller is not yet reusable.

---

## 2026-08-24 — `cloud-run-update`: empty means "do not touch", and it never deploys an image

**Decision.** New reusable applying configuration to an existing Cloud Run service — runtime
identity, sizing, scaling, env vars, mounted secrets, probes — with a health gate. It is the
last of the four convergence reusables built today.

**It never deploys an image.** `deploy-cloud-run` and `promote-image` own which revision runs;
this owns how that revision is configured. Splitting them is what makes a config change
reviewable without a rebuild, and keeps rollback a pure image operation.

**The central property: an unset input produces no flag.** `gcloud run services update` leaves
any flag it is not given untouched, and this workflow preserves that rather than substituting
its own defaults. The alternative — always sending every flag — has a specific, quiet failure
mode: a caller bumping `max_instances` also resets memory, concurrency and probes to whatever
this file happens to say. A step test asserts a bare run sends nothing but the service, project
and region.

`cpu_boost` is therefore a **string** (`'true'`/`'false'`/`''`), not a boolean: a boolean
cannot express "leave it alone", and Cloud Run's boost setting is exactly the kind of thing a
caller updating scaling has no opinion about.

**The env-var delimiter is chosen at runtime, not hardcoded.** gcloud's `^delim^k=v delim k=v`
form exists because values contain commas. The Realm-ID caller this replaces hardcoded `@` —
fine for its values, and a silent corruption for anyone whose values contain an email address.
The workflow picks the first of `@ # % | ~ ! +` absent from every value, and **fails loudly**
if all of them occur. Guessing would produce environment variables nobody declared, which is
worse than a failed run.

**`extra_args` is a deliberate escape hatch, one flag per line.** Cloud Run has far more flags
than deserve typed inputs, and a reusable that must be released every time someone needs
`--set-cloudsql-instances` is a bottleneck. One flag per line (rather than a single string)
keeps a value containing spaces intact instead of word-splitting it.

**The health gate generalises Realm-ID's `sql.status` check.** Its caller asserts
`.data.sql.status == "UP"` because GoFr lazy-connects to Postgres: a bad DSN passes the startup
probe and fails on the first query — the May 2026 v2-DSN incident. `health_jq` +
`health_expect` express that for any service: apply a jq filter to the health body and require
a value. A status-code check alone cannot catch an endpoint that returns 200 while reporting a
dependency as down.

**Built with no caller to adopt it.** Every caller is in Realm-ID, which is frozen on a billing
issue, so this ships with green CI and step tests but **no runtime signal** — nothing has run
it against a real service. That is a deliberate, user-approved trade (build now, adopt later),
and worth remembering when the first real run happens: treat it as unproven in execution, the
same way `resource_roles.secrets` was until an apply actually exercised it.

---

## 2026-08-24 — `bootstrap-cf-dns`: the full-ruleset PUT was deleting another workflow's Origin Rules

**Decision.** New reusable for zone-level Cloudflare state — DNS records plus Origin Rules —
collapsing `AutoMahn/project`'s `bootstrap-cf-dns.yml` and `bootstrap-cf-origin-rules.yml`
and `Traide-Co/project`'s `bootstrap-cf-dns.yml`. Records and rules are JSON-array inputs,
because `workflow_call` inputs cannot be objects and a per-record input set would cap the
number of records a caller may declare.

**The finding, from reading the two callers side by side.** `bootstrap-cf-origin-rules.yml`
does a **full-ruleset PUT**: "replaces the entire origin ruleset each run with the canonical
set of rules defined here". `bootstrap-cf-service-proxy.sh` *splices* a per-hostname rule
into that same ruleset. Both target `automahn.in`. A zone has exactly one entrypoint ruleset
per phase, so **running the origin-rules workflow deletes the service workflow's rule**, with
no error and no output saying so — the hostname simply stops reaching its origin.

We have not confirmed this has happened on the live zone (that needs a Cloudflare token we do
not hold here); the collision is read off the two implementations, which is enough to design
against.

So the new workflow edits **by expression**: declared rules are upserted, undeclared rules are
preserved with their server-assigned fields stripped. That is what lets it and
`bootstrap-cf-service` share a zone. `prune_unmanaged_origin_rules: true` restores the old
declarative behaviour for a zone with a single owner, and logs a warning naming every rule it
drops — the old behaviour was not wrong, it was just silent.

**TXT records are matched on content, not just name.** Traide's caller already did this and
AutoMahn's did not, and Traide's is right: several TXT records legitimately share a name (SPF,
DMARC, one token per verifying vendor). Matching on name+type alone updates whichever the API
returns first, which can be another vendor's token. Generalising the stricter rule costs
nothing and removes a way to silently break someone else's domain verification.

**`replaces` rather than a global "clean up conflicting types" switch.** AutoMahn's caller
deletes a stale `AAAA` before writing a `CNAME` at the same name — how a hostname moves off a
worker route. Expressed per record, the destructive act is visible next to the record that
needs it; a zone-wide boolean would apply it to records that never asked.

**Everything is validated before the first write.** A run that creates three records and dies
on a malformed fourth leaves the zone in a state nobody declared, and re-running does not
obviously fix it. Validation names the offending index.

**A jq scoping bug the step tests caught.** The preserve filter was
`select(([$d[].expression] | index(.expression)) == null)` — inside the pipeline `.` is the
array just built, so `.expression` indexes an array with a string and jq aborts. Fixed by
binding first: `select(.expression as $e | ([$d[].expression] | index($e)) == null)`.
actionlint and shellcheck both pass on the broken version: neither looks inside a jq program.
This is the second time in this session that a defect invisible to the linters was found only
by executing the shipped step body.

**Not done:** no caller is migrated; the three inline workflows stay until their own repos'
PRs. Whether AutoMahn's live zone currently has a missing Origin Rule is worth checking with a
token when someone has one.

---

## 2026-08-24 — `bootstrap-cf-service`: two routes to one hostname, and the origin host stops being hand-copied

**Decision.** New reusable, absorbing `AutoMahn/project`'s `infra/cloudflare/bootstrap-cf-service-dns-only.sh`
(192 lines) and `bootstrap-cf-service-proxy.sh` (226 lines) together with the two thin
workflows that wrapped them. One workflow, `mode: dns-only | proxied`.

**Why one workflow with a mode, when `AGENTS.md` forbids a `target:` switch.** The rule is
one reusable per *target type*, and both modes have the same target: a public hostname for
one Cloud Run service. They differ in the route taken to it — Google-terminated TLS behind a
domain mapping, versus Cloudflare-terminated TLS behind a proxied CNAME and a Host-override
Origin Rule — and that choice is forced by the zone's Cloudflare plan, not by what the caller
is trying to achieve. A caller on Free and a caller on Pro want the identical outcome. Two
workflows would make every caller learn which of two names matches their billing tier.

This is also why `bootstrap-cf` did **not** become one workflow: its other callers manage
zone-level DNS records and Origin Rules, which are a genuinely different target. That split
is `bootstrap-cf-dns`.

**The origin host is now resolved, not pasted.** `bootstrap-cf-service-proxy.sh` required the
operator to supply `CLOUD_RUN_URL` — the `*.run.app` host — by hand on every dispatch, and
the caller workflow had no GCP credentials at all. That value changes when a service is
recreated, and a stale one points the Origin Rule at a dead origin with **nothing failing**
until traffic does. The workflow now reads it from the live service and strips the scheme.
`cloud_run_url` survives as an input purely for the no-GCP-access case, documented as the
hazard it is.

Because that is the *only* reason a proxied run needs GCP, WIF is optional: `mode: proxied`
plus an explicit `cloud_run_url` runs no auth step. `dns-only` always needs it — the domain
mapping *is* the route.

**Two things deliberately warn instead of failing.**

- *Certificate wait.* Google issues the managed cert once it observes the CNAME — minutes to
  half an hour on a first provision. On timeout the mapping and the DNS record are already
  correct, so failing would make a green run mean "Google was quick today" rather than "the
  hostname is configured".
- *Zone SSL mode.* It is zone-wide. A per-service workflow that flipped it would change every
  other hostname on the zone as a side effect. Below Full it breaks validation to the
  `*.run.app` origin and leaves a man-in-the-middle gap — worth reporting loudly, not worth
  fixing from here.

**The Origin Rule splice is the dangerous part, so it is the most tested.** A zone has exactly
one entrypoint ruleset per phase and it is written *whole*: a read-modify-write that forgets
someone else's rule deletes it silently, zone-wide. Step tests assert that an unrelated
hostname's rule survives, that server-assigned fields (`id`, `version`, `last_updated`, `ref`
— Cloudflare 400s if echoed back) are stripped from kept rules, that a re-run refreshes our
rule in place rather than stacking a duplicate, and that a missing entrypoint is created
rather than PUT to.

**Concurrency is per hostname, not per service or per zone.** Per zone would serialise
unrelated hostnames; per service would let two runs for one hostname race on both the DNS
record and the entrypoint ruleset. `cancel-in-progress` is off for the same reason as
`deploy-cloudflare-worker`.

**Not done:** the two callers are not migrated, and the two shell scripts are not deleted
from `AutoMahn/project`. Both happen in that repo's own PR, after this is tagged.

---

## 2026-08-24 — `deploy-cloudflare-worker`: wrangler owns the worker's config, this workflow owns everything around the deploy

**Decision.** New reusable, collapsing `AutoMahn/api`'s two inline worker deploys
(`deploy-api-proxy-worker.yml`, `deploy-files-worker.yml`). It takes a `worker_directory` and
runs `wrangler deploy`; it takes **no** input for routes, bindings, vars or the worker name.

**Why not model the worker's config.** Those all live in `wrangler.toml`, and wrangler applies
them on every deploy whether or not this workflow has an opinion. Adding inputs for them would
produce two sources of truth where only one is load-bearing: the workflow's copy would be
advisory, the file's copy would be real, and the two would drift without anything failing. The
same argument the `AGENTS.md` "one reusable per target type" rule makes about `target:`
switches applies to configuration the tool already owns.

So the boundary is: **wrangler owns what the worker IS, this workflow owns whether/when/from
what it ships** — ref selection, the change-skip, install, the test gate, dry-run, and the
smoke check.

**wrangler is deliberately not installed.** `npx` resolves it from the worker directory's own
lockfile, so the deploying version is one that was committed and that Dependabot updates.
Installing a floating `wrangler@latest` would mean two identical runs could deploy through
different tooling. `wrangler_version` exists only for a worker with no wrangler dependency.

**`watch_paths` — and why the checkout is unconditionally deep.** Both callers hand-rolled a
"skip if unchanged since the previous tag" gate, because a caller wired to `v*.*.*` runs on
every release tag including the many that touch nothing it cares about. Generalising it here
also delivers the `watch_paths` change-skip that TODO.md had filed as a post-migration
follow-up. `fetch-depth: 0` is unconditional rather than keyed off `watch_paths`: a shallow
clone contains no previous tag, so a conditional depth would make the skip silently wrong for
exactly the callers who enabled it — every run would look like a first release and deploy.

**`node_version` defaults to `22`, not to current LTS `24`.** Both production workers pin 22.
A reusable whose adoption also moves the runtime a worker is built on is asking callers to
change two variables in one PR, and to debug the result if it breaks. The default matches
what runs today; moving to 24 is a separate, deliberate one-line change.

**Concurrency is not `cancel-in-progress`.** Unlike a Pages build, cancelling wrangler
mid-upload can leave the worker live against a half-applied set of bindings. A queued deploy
costs a minute.

**Two portability defects were found by writing the step tests, not by CI:**

1. The change-skip step used `mapfile`, which is bash 4+. macOS ships bash 3.2, so
   `run_step_tests.py` — which executes the *shipped* body — could not run on a developer's
   laptop at all. GitHub runners have bash 5, so CI would have stayed green and the gap would
   have surfaced only as "the tests don't work on my machine". Replaced with a `while read`
   loop.
2. `run_step_tests.py`'s new git helper failed for anyone with `tag.annotate=true` set
   globally (`fatal: no tag message?` from a plain `git tag`). Tests must not depend on
   ambient developer config, so the helper now passes `-c tag.annotate=false -c
   tag.gpgSign=false -c commit.gpgSign=false`.

The deploy step's flag assembly was also rewritten from `[ -n "$X" ] && args+=(…)` to explicit
`if` blocks. The AND-list form is correct where it sits, but it exits non-zero when the test
fails, so it fails the step the moment anyone appends nothing after it — the same shape as the
Summary-step AND-list bug that `run_step_tests.py` was built for.

**Not done:** the two callers are not migrated. Callers move one repo at a time, in their own
PRs, after this is tagged.

---

## 2026-08-24 — RCA: the sweep demanded a project-wide role to check a typo, and collapsed multi-secret lists

Found while adopting `cleanup-secret-versions` on AutoMahn and Traide-Co — the first callers
it has ever had. It shipped in v2.3.0 on 2026-08-16 and nobody had run it, so both defects
were latent in a workflow that CI called green.

**Symptom.** Two, in the one step (`Collect target secrets`):

1. The step opened with an unconditional `gcloud secrets list --project=…`. Under
   `set -euo pipefail` a caller without **project-level** `secretmanager.secrets.list` dies
   there, before the sweep starts — even when it named exactly the secrets it holds
   resource-scoped grants on. The workflow's own IAM contract never mentioned that
   permission, so the failure would arrive as a `PERMISSION_DENIED` for a role the docs
   said was not needed.
2. `secrets_list: app-secrets,api-env` collapsed into the single bogus name
   `app-secretsapi-env`. `tr ',' '\n' | tr -d '[:space:]'` splits on the comma and then
   deletes **every** whitespace character — including the newlines the split just made.
   `[:space:]` was the wrong class; `[:blank:]` (space + tab) is the one that strips
   ` a, b ` without rejoining the lines. Single-secret callers — every real one, since
   both target projects hold exactly one secret — never saw it.

**Root cause.** Both come from validating by *enumeration* instead of by *identity*. The
step proved a name existed by listing the project and diffing with `comm`, which needs a
project-wide read, needs the names in a sorted file, and made the newline handling
load-bearing in a way nothing tested. Bug 2 was masked by bug 1's own error path: the
collapsed name failed the `comm` check and aborted with "names secrets that do not exist",
which reads like a caller typo rather than a workflow defect.

**Why it wasn't caught.** No caller. The 16 plan fixtures cover the sweep's dangerous half —
the keep-set, the quarantine clock, the `latest` invariant — and `run_step_tests.py` covers
other workflows' bash bodies, but nothing executed *this* step. Reviewing bash for a
character-class bug is exactly what review is worst at. And a zero-caller workflow gets no
runtime signal at all: CI proved the YAML parsed and the plan logic was right, which is not
the same as proving the thing can run.

**Fix.** Validate each named secret with `gcloud secrets describe`, which needs
`secretmanager.secrets.get` **on that secret** — a permission a resource-scoped caller
already holds. `secrets list` now runs only on the `secrets_list: ''` path, which is the one
that genuinely must enumerate (and already warns about its blast radius). `[:space:]` →
`[:blank:]`. The error message covers denied as well as absent, because `describe` cannot
distinguish them and both mean stop.

**Why this matters beyond one workflow.** The fleet moved to resource-scoped IAM in
ADR-005 precisely so an ops identity is not handed project-wide roles. A reusable that
demands a project-level role to check a typo quietly undoes that — the caller either grants
too much or cannot adopt the workflow. Reusables should ask for the narrowest scope their
work actually needs, and say so in permissions rather than role names.

**Prevention.** Five checks in `run_step_tests.py` execute the shipped step body against a
stubbed `gcloud` whose `secrets list` **fails** with `PERMISSION_DENIED`: named secrets
still resolve; a multi-secret list resolves to N distinct names; a typo still aborts and is
named; and the empty-list path still enumerates and still warns. The IAM contract in the
workflow header and in `docs/cleanup-secret-versions.md` is now stated as permissions, with
the resource-scope note and the one project-level exception spelled out.

## 2026-08-21 — `setup-buildx-action` 4.3.0 merged without a release: a tag is a fleet event, a patch bump is not

**Change.** Dependabot PR #63 bumped `docker/setup-buildx-action` 4.2.0 → 4.3.0 (SHA and trailing
version comment together, as the pin convention requires) in `deploy-cloud-run.yml`,
`deploy-cluster-keyed.yml` and `deploy-gke-service.yml`. All ten required checks green; merged as
`cb012a2`, main CI success.

**The decision was not the merge — it was the non-release.** These are workflow *bodies*, and a
consumer pinned at `@v2.4.0` runs the workflow as it existed at that tag. So the bump reaches
nobody until a new release is cut. The obvious move was `v2.4.1`; we deliberately did not.

- **Nothing consumer-visible changed.** The input contract is untouched, and semver here tracks the
  input contract. A patch action bump inside a `run:`-less setup step changes no behaviour a caller
  can observe.
- **It would have instantly staled two repos that were repinned hours earlier.**
  `AutoMahn/project` and `Traide-Co/project` moved to `@v2.4.0` the same day. Cutting `v2.4.1`
  makes both out-of-date immediately, for no gain.
- **The release ceremony is disproportionate.** Cutting one is four steps — stamp sweep PR
  (`scripts/stamp_version.py`) → merge → tag → `gh release create` — plus a repin PR per caller
  afterwards. Paying that per Dependabot bump means the fleet spends more time repinning than the
  bumps are worth.

**So: Dependabot bumps ride to the next functional release rather than driving one.** The bump sits
on `main` and ships with whatever lands next. The risk this accepts is the one worth naming — an
*urgent* action bump (a CVE in a pinned action) must NOT inherit this rule; that one cuts a patch
release immediately, because "it's on main" is not a fix for anybody still pinned.

## 2026-08-21 — v2.4.0: `buildcache` leaves the default keep-set — a moving tag the default policy forbids

**The incoherence.** `keep_tags` defaulted to `latest,buildcache` while
`immutable_tags_policy` defaults to `enforce`. `buildcache` is only meaningful for a BuildKit
**registry** cache (`cache-to: type=registry,ref=…:buildcache`), which is a **moving** tag —
every build overwrites it. Immutable tags permit *creating* a tag but never *moving* one, so on
an enforcing repository the first `cache-to` push succeeds and every later one fails: the cache
freezes at its first push and silently stops helping. Nothing errors; builds just quietly stop
getting cache hits. The default keep-set was protecting a tag that, under the default policy,
could not usefully exist.

**Half the original TODO was already answered.** It also flagged `latest` as a moving tag in the
same default. That was resolved on 2026-08-13 by `cleanup_latest_tag`: **`keep_tags` protects
the DIGEST during the sweep; `cleanup_latest_tag` removes the stranded POINTER after it.**
Different objects, hence no conflict — dropping `latest` from `keep_tags` would let the sweep
delete the digest, and under build-once/promote a released digest also carries `:<sha>` and
`vX.Y.Z`, so that would take a release with it. Only `buildcache` was ever open.

**The fleet decided it, and the scan method is worth recording.** `gh search code` returns
**empty** for these private repos — two control searches for strings that certainly exist came
back with nothing, so "no results" there is not evidence of absence. Scanned instead by fetching
every workflow file through the git-trees + contents APIs: **19 active repos, 91 workflow files.
Zero registry build caches.** Every cache in the fleet is `type=gha` (AutoMahn/api,
Traide-Co/api, Realm-ID/api, Realm-ID/project) — GitHub's Actions cache, which never creates a
tagged image in Artifact Registry. The only `buildcache` string anywhere is a comment. Of the
three `cleanup-gar-images` callers, two run `enforce` (Traide-Co, Realm-ID), one `preserve`
(AutoMahn), and **none overrides `keep_tags`**.

**Decision: opt-in, not default.** `keep_tags` now defaults to `latest`. A registry cache and
`immutable_tags_policy: enforce` are mutually exclusive, so choosing the cache means choosing
`preserve`/`unlock` — and making `buildcache` opt-in puts that decision with the caller who
actually runs one, at the moment they run it. Live impact is nil: no such tag exists in the
fleet and all three callers pin `@v2.3.1`, so nothing changes for them until they repin.

*Rejected: leave the default and only fix the docs.* Cheapest, and the keep genuinely costs
nothing at runtime — shielding a tag that isn't there is harmless. But it leaves two defaults
telling a new caller opposite stories about whether moving tags are part of the model, and the
docs are the wrong place to resolve a contradiction the inputs themselves state.

**A warning, because the docs are not where people are looking.** Setting `keep_tags` to include
`buildcache` under `enforce` is still legal — it is the caller's call — but the resolver now
warns at run time, mirroring how the workflow already warns about a missing update permission. It
never fails. The check normalises whitespace before matching, because the plan step's `csv()`
strips it and `latest, buildcache` is a valid keep-set — without that, the check would silently
miss the exact spaced form it exists to catch. Eight step-body assertions cover it, including
that `mybuildcache`, `buildcache-old` and `buildcaches` do **not** trip it.

**Rode along:** `SERVICE_ACCOUNT` was interpolated by two immutability warnings but never set on
their step, so both always printed the generic "the deploy service account" fallback — defeating
the point of a message whose whole job is naming the identity an operator must grant a role to.
Same file, same feature area, so it ships here rather than accruing another release.

## 2026-08-21 — Three workflows shipped undocumented; a generator cannot catch absence from a hand-maintained list

Found in an org-wide cleanup review of the four `Just-Git-Dev` repos.

**`bootstrap-dashboards`, `cleanup-cloud-run-revisions` and `validate-alerts` had no
`docs/<name>.md` page and no README row.** The only way to discover them was to list
`.github/workflows/`. The README meanwhile asserts, in prose, "Each workflow has a
`docs/<name>.md` page with its full input/secret contract" — so the docs were not merely
incomplete, they contained a false claim about their own completeness.

**Why nine CI jobs missed it.** Every existing gate checks the *content* of something
already tracked. `gen_catalog.py --check` regenerates `catalog.json` **from** the workflow
files, so all three appeared there and looked perfectly healthy — a generator sees what
exists, never what is missing from a list maintained by hand. `doc-examples` lints the
examples that are present. `version-sweep` checks the pins that are present. Absence from a
hand-maintained list is structurally invisible to all of them, so it needed its own gate:
`scripts/check_docs_coverage.py`, wired in as `every workflow is documented`. It checks both
directions — a workflow with no docs page or README link, and a docs page whose workflow was
deleted or renamed. Confirmed red on the pre-fix tree before being wired in; a gate never
observed failing is not yet a gate.

The three pages are written from each workflow's own header comments, which were good — the
rationale existed, it just lived where only someone already reading the YAML would find it.
Two things worth having in the README rather than a file header: `cleanup-cloud-run-revisions`
must be scheduled **before** `cleanup-gar-images` (an idle revision costs no compute but pins
a GAR digest, so the GAR sweep cannot reclaim it), and `validate-alerts` exists because the
Monitoring API has **no** `validateOnly` mode — `alertPolicies.create` takes exactly one
parameter, so actually creating the policy is the only server-side check, and the workflow
substitutes an offline structural lint plus real MQL execution for it.

**Eight workflows had a bare filename as their `name:`** (`ci-go`, `deploy-cloud-run`,
`promote-image`, …), so `catalog.json` — the file a consuming repo's agent reads instead of
~7,500 lines of YAML — mixed filenames with prose titles, and those eight rendered as a bare
slug in every caller's Actions UI. All eight now carry a `… (reusable)` title matching the
other fourteen; `catalog.json` regenerated.

## 2026-08-20 — Three writers of one secret blob held three different locks (bug fix)

Released as **v2.3.1**. `sync-bundle-key`, `rotate-signing-keypair` and
`rotate-worker-signing-secret` now declare a byte-identical
`concurrency.group: bundle-write-${{ inputs.gcp_project }}-${{ inputs.bundle_secret }}`,
replacing `secrets-rotation-…`, `keypair-rotation-…` and
`signing-rotation-…-${{ inputs.bundle_key }}`.

**Symptom.** None observed — this was found by reading, not by an incident. Two of the three
workflows running concurrently against one `app-secrets` bundle would each read version N,
patch their own keys, and add version N+1 and N+2; whichever wrote second would silently drop
the other's keys. The failure surfaces later and somewhere else — a worker that stops verifying
signatures, with nothing in either run's log suggesting why.

**Root cause.** A `concurrency.group` is an opaque string, and the three workflows were written
at different times, each naming its group after *itself* (`keypair-rotation`, `signing-rotation`)
rather than after the resource it mutates. All three do the same read-modify-write of the same
blob, so the resource — not the operation — is the thing that needs the lock. The third
compounded it by keying on `bundle_key`: two runs patching different keys inside one bundle
still collide on the whole-blob write, so a per-key lock is no lock at all.

**Why it wasn't caught.** Nothing mechanical could see it. `actionlint` validates that a
`concurrency:` block is well-formed, not that two well-formed blocks refer to the same lock;
three plausible, self-consistent prefixes are indistinguishable from a deliberate choice to run
them in parallel. Nor did run history disprove it: no overlap has been observed, because the
exposure needs a quarterly or annual scheduled rotation to land on a manual sync — rare enough
to stay invisible for a long time and still be real. AutoMahn's caller-level
`group: secrets-rotation` covered two of its four callers, which is the kind of partial mitigation
that makes the gap look closed.

**Fix.** One group string in all three files, keyed on `gcp_project` + `bundle_secret`.
`cancel-in-progress` stays `false`: a writer cancelled mid-run may already have added a version,
which is worse than queueing behind one.

**Prevention.** `tests/run_concurrency_tests.py` asserts the three group expressions are
*identical strings* — the only assertion that means anything about a lock — that the key is
absent from them, and that none of the three cancels the others. Wired into CI as its own job.
The test file lists the writers explicitly, so a fourth writer of this blob has to be added to
the list by hand; that is the intended prompt.

**Known residual, not fixable here.** GitHub scopes a concurrency group to the repository that
*declares* it, which for a `workflow_call` reusable is the **caller's** repo. Two different caller
repos writing the same bundle are still not serialised. Recorded in the docs rather than worked
around: the alternative is a lock outside GitHub (a GSM-etag CAS retry, or a lease secret), which
is a materially bigger change than the exposure justifies while one repo owns each bundle.

## 2026-08-17 — Delayed destruction (`version_destroy_ttl`) exists — it simplifies the sweeper but does not replace it

Recorded as a finding, not a change: nothing in this repo sets or reads `version_destroy_ttl`
today, and no workflow was modified for it. `grep` across all 22 workflows, `docs/` and this log
returned nothing for it before this entry.

**What it is.** Secret Manager supports **delayed destruction**, configured per secret:
`gcloud secrets create|update SECRET_ID --version-destroy-ttl=DURATION` (API field
`version_destroy_ttl`), minimum 1 day, maximum 1000 days, removed with
`--remove-version-destroy-ttl`. With it set, destroying a version does not delete the material —
the version moves to **`DISABLED`** and gains a **`scheduledDestroyTime`**, and destruction is
cancelled by enabling *or* disabling the version any time before that. Verified against Google's
docs rather than recalled, per the standard this repo adopted on 2026-08-16.

Note the state precisely: the version is `DISABLED` with `scheduledDestroyTime` set.
`SECRET_VERSION_DESTROY_SCHEDULED` is the name of the Pub/Sub *notification*, not a version
state — a workflow must detect scheduling by the field, not by a state string.

**What it corrects.** The 2026-08-16 entry built the quarantine on Admin Activity audit logs
because Secret Manager stores no disabled-at timestamp. That premise is still true, but the
conclusion drawn from it — that the clock must be reconstructed client-side — was reached without
knowing this feature exists. `scheduledDestroyTime` is a plain metadata field, so with a TTL
configured the delay is enforced *server-side and cannot be wrong*, and
`cleanup-secret-versions` could drop `quarantine_days`, `roles/logging.viewer`, and the
"disable event not found ⇒ HELD forever" branch. That is a real simplification of shipped code
and is filed in `TODO.md`.

**Why it does not remove the need for the sweeper**, which is the question it prompted.
`version_destroy_ttl` is an **undo window, not a retention policy**. The TTL clock starts when
something calls `DestroySecretVersion`; nothing inside Secret Manager ever makes that call. With
the TTL set and no sweeper, versions accumulate exactly as they do today and the TTL never fires
because nothing arms it. (GSM's only automatic destruction is secret-level expiry, which deletes
the entire secret — a different tool.)

**Why the writers still do not absorb it.** Two of the original objections genuinely dissolve
under a TTL: destruction stops being irreversible, and the audit-log clock stops being needed. A
third weakens — a destroyed-under-TTL version lands in `DISABLED`, the same immediate blast
radius as the disable the writers already perform without a consumer scan. The coverage argument
also proved narrower than first stated: versions are only created by writes, so a writer-owned
sweep is eventually correct for any secret still being rotated.

What decided it is reviewability. The sweep's safety model is *run it dry, read the plan, then
opt in* — `dry_run` defaults true and `enable_destroy` defaults false. That requires an
invocation with **no side effects**. Inside a writer there is no such invocation: `dry_run`
suppresses the write, and with it the disable and the destroy, so the plan is never computed;
and `dry_run: false` reaches the destroy only by minting a credential, rolling Cloud Run and
flipping the Cloudflare Worker slots. Reviewing a destroy plan would require performing a
production rotation. AGENTS.md §5 exists because on 2026-08-11 a retention change was *reasoned*
safe and a dry-run measurement showed the opposite; that measurement has to be cheap and
side-effect-free or it stops being taken. Secondary: a retention bug would fail a rotation
mid-flight rather than a sweep, and dormant or externally-written secrets (`manage-config-secrets`,
hand edits) would never be swept at all.

**Open before acting on any of this** — both filed in `TODO.md`, neither verified:
whether a version awaiting `scheduledDestroyTime` is still billed (if it is, the cost saving
that started this is deferred by the TTL, not avoided), and which role grants
`secretmanager.secrets.update` — setting the TTL mutates the *secret*, not a version, so
`roles/secretmanager.secretVersionManager` may not cover it. There is also an interaction to
check: a version awaiting destruction is `DISABLED`, so the sweep's current DISABLED-selection
would re-enter it as a candidate on the next run.

## 2026-08-17 — `keep_enabled_count` on the writers: disable is inline, destroy stays in the sweeper

`sync-bundle-key`, `rotate-signing-keypair` and `rotate-worker-signing-secret` each disabled
exactly one version after a successful roll — the one they had just superseded, hard-coded.
That is now `keep_enabled_count` (default `'1'`), a keep-set: the newest N ENABLED versions
survive and everything older is disabled.

**Why not put the whole retention story in the writers.** The question raised was whether
`cleanup-secret-versions` needed to exist at all, or whether the update flow could own version
lifecycle end to end. The state machine's two halves have genuinely different requirements, and
that is what decided it:

- **Disable** needs only the version list and `secretVersionManager`, which every writer already
  holds. It was already inline. Generalising it to a keep-set costs nothing new.
- **Destroy** needs a quarantine clock and a consumer scan. Secret Manager stores no disabled-at
  timestamp, so the clock comes from Admin Activity audit logs (`roles/logging.viewer`), and
  number-pinned Cloud Run consumers are only visible with `roles/run.viewer`. Granting both to
  the identities that mint credentials widens their blast radius for no gain.

Decisive beyond IAM: **a writer-owned sweep only runs when you write.** `app-secrets` rotates
quarterly and annually, and the two sync callers are dispatch-only. Retention that fires when
rotation fires never reaches the secrets that most need it — the ones nobody rotates — and
never covers versions written by `manage-config-secrets` or by hand. A retention bug would also
fail a *rotation* run, which is the safety-critical path.

**A run cannot destroy what it just disabled**, either: the quarantine clock starts at the
`DisableSecretVersion` event, so dwell is zero by construction. Inline destroy would always be
operating on a tail left by earlier runs, which is the sweeper's job by another name.

**On cost, since it was raised.** Disabled versions *are* billed — $0.06 per version per month,
as recorded in the 2026-08-16 entry. But total Secret Manager spend across all three projects
measured ~$0.78/month on 2026-08-16, so destroying the entire tail saves single-digit dollars a
year. Cost is the weakest argument for destruction; reducing the number of retrievable
plaintexts is the real one, and it is `cleanup-secret-versions` that acts on it.

**The behaviour change, stated rather than claimed away.** At `keep_enabled_count: '1'` this is
identical to the old single-version disable *only when the secret carries no pre-existing
ENABLED tail*. That is the steady state these workflows maintain, so in practice the default is
a no-op — but a secret written outside them can carry a tail, and the first run will now disable
all of it. AGENTS.md §5 exists because on 2026-08-11 this repo's docs claimed a retention change
"could only ever delete less" and a dry-run measurement showed the opposite; that lesson applies
here, so the step emits a `::warning::` naming the count whenever it disables more than one, and
the docs tell upgraders to dry-run both pins. Every action remains reversible with
`gcloud secrets versions enable`.

`0` is rejected outright: it would disable every version and leave `latest` unresolvable. The
newest ENABLED version is never in the disable set, so the step cannot silently repoint `latest`
— the live-rollback failure mode the 2026-08-16 entry documents.

Covered by nine assertions per workflow in `tests/run_step_tests.py`, executed against the
shipped step bodies: keep-set arithmetic at 1 and 2, the tail sweep and its warning, the
newest-version guard, rejection of `0` and of non-numeric input, that no path ever calls
`versions destroy`, and that the step is ordered after the Cloud Run roll.

## 2026-08-16 — `cleanup-secret-versions`: quarantine, not deletion — and the `:latest`-resolves-at-deploy premise was wrong

**What.** New reusable `cleanup-secret-versions.yml`, closing the TODO filed as #51: four
reusables add Secret Manager versions (`manage-config-secrets`, `rotate-signing-keypair`,
`rotate-worker-signing-secret`, `sync-bundle-key`) and none ever removed one, so every
rotation increased the number of retrievable plaintexts.

**Why a quarantine rather than a delete-set.** `cleanup-gar-images` can afford to be wrong:
a deleted image rebuilds from its commit. A destroyed secret version cannot — *"After a
version is destroyed, you can't access the secret data or restore the version to another
state."* So the sweep moves `ENABLED → DISABLED → DESTROYED` with a mandatory dwell time,
and `enable_destroy` defaults to **false**. Out of the box the workflow only performs
actions that `gcloud secrets versions enable` can undo. Holding a version disabled for a
month costs $0.06; getting it wrong costs a credential.

**The premise correction, which is the substantive finding.** The design note in TODO.md
recorded that Cloud Run mounts `:latest` and that this "resolves at *deploy* time", and
concluded that `not :latest ≠ not in use`. The conclusion was right; the stated reason was
wrong, and wrong in the unsafe direction. Per Google's Cloud Run docs, verified rather than
recalled:

- **Volume mounts** — *"When reading a volume, Cloud Run always fetches the secret value
  from the Secret Manager"*, and *"during runtime, if a secret is inaccessible, attempts to
  read the mounted volume fail."* Resolution is at **runtime, on every read**.
- **Env vars** — *"resolved at instance startup time."*

Every Cloud Run service across `realm-id`, `auto-mahn` and `traide-in` uses the **volume**
form. So there is no "safe until the next deploy" grace window that the original premise
implied: a wrong destroy breaks a **running** service on its next read. The keep-set is
therefore stricter than specced, not looser.

**The `latest` invariant.** `latest` resolves server-side to the highest-numbered ENABLED
version, which makes *disabling* the newest enabled version a silent live rollback — it
repoints `latest` at an older payload with no deploy and no signal. The version `latest`
resolves to is consequently never actionable: hard-coded, not an input, asserted as a
plan-time invariant, and re-resolved immediately before each destroy. The guard is
mathematically redundant with the keep-count in the steady state; it earns its place only
when a rotation lands between the two collection calls, which is precisely when an
irreversible mistake would otherwise happen. A fixture
(`s15-latest-diverges-from-highest-enabled`) exists solely to keep it load-bearing —
mutation testing showed that without it, removing the guard broke nothing.

**The quarantine clock comes from audit logs, because the resource has no clock.** A secret
version carries `createTime`, `state` and `etag` and nothing else — there is no
disabled-at timestamp to read. Admin Activity logs record `DisableSecretVersion`, retain it
400 days and cannot be disabled, so that is the source; the most recent event governs a
version that was disabled, re-enabled and disabled again. A version with no discoverable
disable event is **held**, never destroyed: absence of evidence is not evidence of an
old-enough disable. This is why `roles/logging.viewer` is required.

**`secretmanager.secretAccessor` is deliberately not required.** The sweep reads metadata
only and never reads a payload, so it cannot leak one.

**Fail-safe.** Zero live consumers for a target secret aborts the run, mirroring
`cleanup-gar-images`' "no live digests resolved" — a broken scan, a wrong `gcp_region` or a
missing role all present identically to an unused secret, and are far more likely.
`require_consumers: false` is the explicit opt-out for secrets consumed outside Cloud Run.

**Verification.** 16 fixtures in `tests/fixtures-secrets/`, run against the heredoc
extracted from the workflow itself (no second copy to drift), wired into CI as
`secret-plan-fixtures`. The suite was mutation-tested — dropping the `latest` guard, an
off-by-one on the quarantine boundary, substituting `max(version)` for the resolved
`latest`, ignoring consumer pins, and destroying on an unknown clock each now fail at least
one fixture; the first two survived the initial suite and drove two extra fixtures. The
full collection-plus-plan pipeline was additionally driven against live `realm-id`,
`auto-mahn` and `traide-in` data read-only: the `auto-mahn` plan (disable `5`, destroy
`8,6,4,3,2,1`) matches fixture `s11` exactly, and `realm-id`'s `issuer-env:1` is correctly
held at 6.7 days of a 30-day quarantine.

**Also caught, and worth recording as a lint win:** shellcheck's SC2259 flagged
`gcloud … | python3 - <<'PY'` in two collection steps. The heredoc claims stdin, so the pipe
was silently overridden and the script would have parsed its own source instead of the
gcloud output. Both now write to a file and read that. actionlint's shellcheck does not
descend into heredoc *bodies*, but it does see the redirection — the bug was invisible to
the fixture suite, which only covers the plan block.

## 2026-08-13 — `cleanup_latest_tag` (v2.2.0): a stranded `:latest` is cleaned by the sweep that strands it, as a convergence rule

**Context.** `Realm-ID/api`, `Traide-Co/api` and `Realm-ID/issuer` stopped pushing `:latest`
on 2026-08-12 so that `realm-id/backend` and `traide-in/backend` could be locked with immutable
tags. The builds changed, but the **last-pushed `:latest` tag stayed**. In a locked repository
that is permanent: the tag pins its digest alive, `keep_tags` (default `latest,buildcache`)
shields it from the sweep, and an immutable repository refuses to move or remove it. Nothing
converges — every future sweep keeps it, forever.

**Discovered while scoping this: the premise could not be verified with anything that existed.**
The raw `images list --include-tags` output is captured into a Python variable and never
printed, and the plan JSON enumerates only `to_delete` and `blocked_by_parent` — a keep-set
digest appears nowhere. `akshat@revvup.ai` gets `IAM_PERMISSION_DENIED` on
`artifacts repositories describe` for **both** projects, and only `github-cleaner` holds
`artifactregistry.admin`, reachable exclusively via WIF inside Actions. So there was no read
path to confirm the tags were still there. That shaped the design: **`dry_run: true` is now the
read path**, reporting which packages carry `:latest` and on which digests, mutating nothing.
As of this entry **the tags have still never been observed.**

**Decision.** Add a `cleanup_latest_tag` boolean to `cleanup-gar-images`, **default `true`**,
rather than build a separate `delete-gar-tags` reusable.

**Why fold it into the sweep.** It already owns everything the job needs: WIF auth as the SA
with `artifactregistry.admin`, the `--include-tags` listing, and the whole detect → pre-flight →
unlock → act → `always()` re-lock window. A new reusable would have duplicated that immutability
sequence — the exact duplication `retire-gar-packages` was careful about. Decisively, **both
callers are already wired**: `workflow_dispatch` only fires from a repo's default branch, so a
standalone workflow (or even a throwaway read-only diagnostic) would have cost two PRs of churn
per repo before it could run once.

**It deletes a tag reference, never a digest — and that is the whole point.** The apparent
shortcut, dropping `latest` from `keep_tags` and letting the sweep take the digest, is **not
equivalent**. Under build-once/promote a released digest carries both a `:<sha>` tag and
`vX.Y.Z`, so deleting it would take a release with it. `gcloud artifacts docker tags delete`
removes only the pointer.

**Why a default of `true` is safe, and why it is gated rather than trusted.** `:latest` is
legitimately live in some repositories — that is exactly what `immutable_tags_policy: preserve`
exists for ("a repository whose build still pushes a moving tag such as `:latest`"). An
ungated default-true would delete a working tag there. So the step acts only where `:latest`
**cannot** be live: under `enforce` (a moving tag is unpushable, so any `:latest` present is
stranded by definition), or under `preserve` on an already-locked repository. Under `unlock`,
or `preserve` on an unlocked repository, it declines and says so.

That gate also dissolves the apparent contradiction with `keep_tags: latest,buildcache`:
**`keep_tags` protects the digest during the sweep; `cleanup_latest_tag` removes the stranded
pointer after it.** They operate on different things, in that order.

**Reframed from one-shot to convergence rule — a correction to the first design.** This began
as a CSV `delete_tags` input defaulting to empty, ignored on `schedule` so that a value left in
a caller's `with:` block could not arm a recurring tag deleter. As a purpose-named boolean
gated on the policy, that guard became wrong: the step deletes `:latest`, then finds nothing,
forever. It is idempotent and self-limiting, so it belongs on the schedule like the rest of the
sweep. The practical consequence is that **the two stranded tags will clear themselves on the
next scheduled sweep after the repin, with no caller change and no manual dispatch.**

**The CSV was dropped as speculative.** The only same-class candidate is `buildcache`, the other
entry in the default `keep_tags` — but the PR that would have introduced it
(`Realm-ID/issuer#2`, registry build cache) was closed as obsolete on 2026-08-12, so it was
probably never pushed. That could not be confirmed: a `gh search code` sweep of both orgs
returned nothing for `buildcache`, but a control query for `cleanup-gar-images` also returned
nothing, so the search does not index these private repos and **proves nothing either way**.
Adding a second boolean if `buildcache` ever appears beats carrying a free-form input nobody
uses.

**Two further deliberate divergences:**

1. **It runs after the sweep, before the re-lock.** After, because the plan is computed long
   before any tag is touched — that is what preserves plan/apply parity, the property that let
   both repos' applied runs match their reviewed dry-run digest sets byte-for-byte during the
   v2.0.0 migration. The consequence is intended and documented: once the tag is gone its
   digest is untagged and is reclaimed by the **next** sweep, not this one. Before the re-lock,
   because deleting a tag in a locked repository is refused exactly like deleting a tagged
   image, and needs the same unlock window.
2. **It fails rather than degrades.** The sweep's pre-flight degrades on locked+no-permission —
   skip tagged images, exit green — which is right for a retention policy, where losing
   retention on some images beats failing the job. It is the wrong trade for a cleanup the
   caller asked for: exiting green having removed nothing is the "green tick means it did not
   run" failure. Same reasoning that gave `retire-gar-packages` no degraded mode.

**Matching is exact, deliberately not `--filter=tag:latest`.** gcloud's `:` is a has/contains
operator, not equality, so a repository carrying `latest-rc` could read as having `latest` —
and the delete would then fail on a tag that never existed. Nothing would be destroyed (the
delete targets the literal `pkg:latest`, never the digest the lookup returned), but a confusing
red run is not an acceptable substitute for a clean no-op. Uses `value(tag,version)` + `awk`
string equality instead.

**Tests first, RED confirmed** (`step 'Clean up stranded :latest tag' not found`), then 30
green: the dry-run read path, apply, convergence on a second run, exact-match rejection of
`latest-rc`, multi-package sweep, all four policy/lock combinations, the degraded failure, and
structural assertions pinning the input's default and type, the absence of the old CSV input,
that the step is **not** restricted to `workflow_dispatch`, and its **position** between
`Execute deletions` and `Ensure immutable-tag end-state` — the ordering is load-bearing and a
future edit could silently move it.

**Release note.** Unlike the last several fleet repins, which were adopted on explicitly
verified behaviour-neutral grounds, **this one changes behaviour on upgrade** for callers using
the default `enforce` policy: their next sweep removes `:latest`. That is the intent, but it
means a v2.2.0 repin is not a no-op and should not be described as one.

**Outcome (same day).** Released v2.2.0, repinned both GAR callers (`Realm-ID/project#10`,
`Traide-Co/project#72`), and applied. **The tags were real** — the first `dry_run: true`
dispatch was the first time anyone had ever observed them:

| package | `:latest` digest |
|---|---|
| `realm-id/backend/api` | `sha256:54efb487939aefb9f477bbdc5362e0244a2ee699de7dfb5b5fd942952ae08b53` |
| `realm-id/backend/bff-api` | `sha256:ef66703bf2122144f73b30702813fd390e3afeffbd8bf01851107e4d2672f2b6` |
| `traide-in/backend/api` | `sha256:4a751f54654ba40e1b61058888c6881cc3669930dcf71794fc1cfd44fe094366` |

Applied runs `31701095105` (RI) / `31701099146` (TC), both green. Both emitted
`immutable-tag policy: enforce`, `repository has immutable tags enabled`, `permission to toggle
immutable tags confirmed` and `immutable tags re-enabled` — so the policy gate acted rather than
declining, and the unlock/re-lock window closed correctly on both. That is also a **fresh
independent confirmation that both repositories are locked**, which until now rested only on the
2026-08-12 workflow readback.

**Convergence proven on live infrastructure, not just in tests.** Verification dry runs
`31701325700` / `31701329799` report `not present, nothing to do` for all three packages. The
step is now a permanent no-op on both repos.

**Still not verified:** whether those three digests are live on Cloud Run, i.e. whether the next
sweep reclaims them or holds them as live. The delete-set summary goes to
`$GITHUB_STEP_SUMMARY`, not stdout, so it is absent from `gh run view --log` — a real gap in the
log-based read path worth knowing about.

**Noted, not fixed (scope):** `SERVICE_ACCOUNT` is referenced in three messages in this
workflow but never set, so the two pre-existing uses always print the generic fallback. Wired
it in the new step (and test-pinned); the other two are in `TODO.md`.

## 2026-08-13 — Fleet repinned to v2.1.2: drift is closed to zero on a behaviour-neutral tag, deliberately

**Context.** `fleet_drift.py` reported 13 of 15 call sites at `@v2.0.0` and 2 at `@v2.1.1`.
None were flagged STALE or MUTABLE — the tool was reporting lag, not breakage.

**Decision.** Repin **all 15** to `v2.1.2` in one sweep, including the two already at v2.1.1,
so the fleet lands at exactly one version rather than two-versions-of-nearly-current.

**Why repin at all, when nothing was behaviourally stale.** Verified before doing it, rather
than inferred from the release notes: for all 8 workflows those 13 sites call, the *only* diff
between `v2.0.0` and `v2.1.1` is the `WORKFLOW_VERSION` stamp line. So this bought no
behaviour — and that is the argument for doing it, not against. Accumulated lag is what made
the 2026-07-27 sweep find 18 of 27 lines six-plus releases back: drift is cheap to close while
it is uniform and cosmetic, and expensive once a real change is buried under it. A fleet at one
version also means the *next* drift report is signal.

**Why v2.1.2 and not v2.1.1.** The retirement fix (entry below) was in flight the same day.
Cutting it first and repinning once to the result is one sweep instead of two, and leaves no
window where the fleet is pinned to a tag that is already superseded.

**How the mechanical risk was bounded.** A repin sweep across 6 repos is exactly the shape of
change that quietly rewrites something it should not. The script rewrote only refs matching
`Just-Git-Dev/reusable-workflows/.github/workflows/<name>.yml@vX.Y.Z` — third-party action pins
untouched — and asserted per repo that the number of changed lines NOT containing
`Just-Git-Dev/reusable-workflows` was **0**. It was 0 in all six. The 15 rewritten pins also
reconcile exactly against the 15 the pre-sweep scan found.

**Result.** All 6 PRs merged; `fleet_drift.py` re-run against live state reports 15/15 at
`v2.1.2`, zero stale, zero mutable.

**`Realm-ID/ui` was included, knowingly.** Its tag-deploy path is still unproven end-to-end (an
open follow-up). The repin cannot change its behaviour — version stamp only — but the first
real `v*.*.*` tag will now exercise a line touched today. Called out here so that, if that
deploy misbehaves, this is not mistaken for the cause and the actual unproven surface is
looked at first.

## 2026-08-13 — `retire-gar-packages` handles immutability, and preserves it rather than deciding it

**Context.** Enforcing immutable tags fleet-wide (v2.1.0, entries below) locked
`realm-id/backend` and `traide-in/backend`. `retire-gar-packages` deletes whole packages via
`gcloud artifacts packages delete`, which a locked repository refuses for any package holding a
tagged image — and the executor `exit 1`s on that raw error. The workflow was left a trap:
green in `dry_run`, red on the first apply, with a gcloud message naming neither the cause nor
the fix. Latent only because no repo in either org calls it today (verified by grepping all 50
workflow files across Realm-ID + Traide-Co), which is exactly the kind of thing that is
discovered by the person retiring a service under time pressure.

**Decision.** Give it the same detect → pre-flight → unlock → act → `always()` restore sequence
as `cleanup-gar-images`, with two deliberate differences.

**Difference 1 — no policy input.** `cleanup-gar-images` takes `immutable_tags_policy`
(`enforce`/`preserve`/`unlock`) because it *owns* a repository's retention posture and runs on
a schedule; deciding the end state is its job. A retirement is a one-off surgical delete, and
nothing about removing a dead service's package is an argument for changing whether the repo is
protected. So there is exactly one end state — **as it was found** — and no knob. A caller who
wants to change a repo's protection has a one-line gcloud command for that.

**Difference 2 — no degraded mode.** The 2026-08-12 entry below degrades a locked sweep to
untagged-only because half a sweep is real work. That reasoning does not port: a package delete
takes every tag with it or fails, so there is no partial version to fall back to. A locked repo
whose SA cannot unlock it therefore **fails the pre-flight, before anything is deleted**, with
an error that names immutability, says nothing has been deleted, and gives both fixes (grant
`artifactregistry.repositories.update`, or unlock out-of-band). The failure mode being guarded
against is the same one as always — not partiality, but a run that stops halfway and does not
say why.

The executor also now captures stderr and recognises the immutability error, so if the unlock
is ever skipped or does not take, the message says so instead of surfacing raw gcloud.

**Header IAM corrected.** It advertised `roles/artifactregistry.repoAdmin`. That still covers
deleting packages, but not `repositories.update`, so it cannot unlock — the same
name-versus-permissions trap recorded on 2026-08-12. Now documents
`roles/artifactregistry.admin`, with the repoAdmin caveat spelled out.

**Not a contract change.** No input added or changed; `catalog.json` is byte-identical after a
regen. Per this repo's rule that semver tracks the *input contract*, this is a patch.

**Tested.** 17 new checks in `run_step_tests.py` drive all four new step bodies against stubbed
`gcloud`/`curl`: detection (locked / unlocked / undescribable-reads-as-unlocked), the
pre-flight's fail-closed path and its wording, restore-and-verify-by-readback, the
never-locked repo being left alone with no update call, and the executor naming immutability on
failure. Written first and confirmed red (`step 'Check tag immutability' not found`).

## 2026-08-12 — A locked repo the sweep cannot unlock degrades to untagged-only instead of failing

**Context.** v2.1.0 (entry below) kept the 2026-08-11 rule that a repository which *started*
locked fails the run when the SA cannot unlock it. For `realm-id/backend` and
`traide-in/backend` that branch had never been reachable — they were never locked. Enforcing
immutability makes it reachable, so a permission the platform did not need yesterday becomes
load-bearing for every future sweep: revoke `artifactregistry.admin` and both nightly sweeps
go red.

**Decision.** On a locked repository with no update permission, **delete the untagged
manifests and skip every tagged candidate**, warning loudly, exit 0. Immutability blocks
deleting tagged images, not untagged ones, so there is real work still available.

**Why this is not the "half-succeed" outcome the 2026-08-11 entry rejected.** That entry was
about a sweep discovering the problem *mid-flight* — partial deletions, an unlocked repo, and
nothing in the run saying so. Here the limitation is known **before** anything is deleted, the
tagged phase is skipped wholesale rather than attempted and failing one error at a time, and
both the log and the step summary name the count and the missing grant. The failure mode being
guarded against was silence, not partiality.

**Why not fail closed anyway.** The thing a locked, un-sweepable repository actually does is
accumulate untagged buildx children — which is the growth this job exists to stop, and which
degrading still handles. Trading that for a red pipeline buys nothing except an outage.

**Why not exit 0 doing nothing.** A green no-op is what hid `traide-in` growing to 580 MB over
six days. The degraded run is explicitly not that: it does the available work and reports the
gap in the summary, and the pre-existing "planned N, deleted 0" warning is suppressed here
because on a degraded run it would read as a keep-set bug rather than a missing grant.

**Consequence for IAM.** `infra-provisioning` moved both `github-cleaner` SAs from
`artifactregistry.repoAdmin` to `artifactregistry.admin` the same day — repoAdmin manages
artifacts, not repository settings, and lacks `repositories.update`. That grant buys
enforcement; this change means losing it degrades protection rather than breaking cleanup.

**Tested.** The executor is now driven directly in `run_step_tests.py` against a stubbed
gcloud with a 2-tagged/2-untagged plan: a normal run deletes all four, a degraded run deletes
exactly the two untagged ones, stays green, warns, and reports the skip count.

## 2026-08-12 — `cleanup-gar-images` v2.1.0: the sweep now ENABLES immutable tags, it does not merely restore them

**Context.** The 2026-08-11 entry below built detect → unlock → sweep → relock, and stated
the principle as *"a repository without immutability never has its settings touched."*
That principle had an unnoticed consequence: **a repository that was never locked is never
protected, and nothing in the platform ever locks it.** It surfaced when the `realm-id/backend`
GAR console still showed immutability disabled after the 2026-08-12 sweep. Nothing was
broken — run `31573158323` shows detection returning false and both toggle steps skipped
(zero occurrences of `--immutable-tags` in the run log) — but "relock is on by default" had
been read as "the platform makes repositories immutable", and it never did.

**Decision.** Make the sweep the enforcement point. `immutable_tags_policy` (default
`enforce`) replaces the `relock_immutable_tags` boolean: an applied run ends with the
repository **locked whether or not it started that way**. `preserve` is the old behaviour;
`unlock` is the old opt-out. `relock_immutable_tags: false` still resolves to `unlock`, so
no caller breaks — only an explicit `false` is distinguishable from a boolean default,
which is exactly the value with an unambiguous meaning.

**Why the sweep, rather than provisioning.** It is the one job that already holds
`artifactregistry.repositories.update`, already knows how to work around the lock, and
already runs on a schedule against every repository worth protecting. Putting enforcement
in `infra-provisioning` would mean granting a second identity the same power to satisfy the
ownership split, for a setting that is a property of the artifact lifecycle this workflow
already owns.

**The permission verdict is deliberately asymmetric**, and this is the subtle part:

- **Started locked, permission missing ⇒ fail, nothing deleted.** Unchanged. The sweep
  genuinely cannot work, and half-doing it is the worst outcome.
- **Started unlocked, permission missing, policy `enforce` ⇒ warn, sweep anyway.**
  Enforcement is a guarantee being *gained*; failing to gain it loses nothing that existed
  a minute ago. Failing the run would convert every repository whose SA lacks
  `roles/artifactregistry.admin` from "sweeps fine, unprotected" to "red pipeline" — a
  self-inflicted outage in exchange for no additional safety.

Symmetric fail-closed was the tempting choice, since the 2026-08-11 design is built on
failing closed. It is wrong here because the two failures are not the same event.

**The real cost, and why the fleet needed three edits first.** An immutable repository
rejects *any* push that moves an existing tag — which includes `:latest`. Three pipelines
push `:latest` into the two repositories being locked (`Realm-ID/api` `deploy.yml`,
`Traide-Co/api` `deploy.yml`, and `Realm-ID/issuer` via `promote-image`'s `also_tag_latest`).
Turning enforcement on without removing them would have failed the *builds*, not the sweep,
and only on the second push. Nothing consumes those tags — Cloud Run deploys reference
semver/sha — so they were retired rather than the policy weakened. **This is documented as
the way the new default bites**, because the failure appears in an unrelated repository's
deploy job.

**Tested.** `run_step_tests.py` gained the policy resolver (enum validation, deprecated-alias
folding), the pre-flight's two verdicts, and the end-state matrix — including the case that
motivated the asymmetry (missing permission on a repo that started unlocked must not fail)
and the one that must never regress (a readback saying "still unlocked" fails the job).

## 2026-08-11 — `cleanup-gar-images` plans are mostly impossible fleet-wide; one caller stalled completely (bug fix)

**Symptom.** A caller (`Traide-Co/project`, pinned `@v1.15.0`) ran the daily sweep for six
consecutive days at `deleted=0`, `failed=0`, exit 0 — a green check every morning while its
GAR repo grew to 580 MB / 78 image versions. The plan was never empty: it queued 8, then 8,
8, 12, 14, 16 candidates. Every one was skipped at execution.

**Root cause — two defects that lock together.**

1. **Age came from `updateTime`.** GAR bumps `updateTime` when a tag is *moved off* a
   digest, so each new release re-ages the previous ones and effective retention becomes
   *threshold + churn interval*. `v0.4.0`, pushed 2026-06-30, read as 28d on 2026-08-11
   against a 30d limit because `latest` left it on 07-14. **This is a delay, not a
   universal stall** — see the correction below; the stall happens only where tags churn
   faster than `tagged_max_age_days`, which is exactly this caller's release cadence.
2. **Untagged children of a surviving index were queued.** A buildx push is an OCI index:
   the tag names a manifest list whose `linux/amd64` and `unknown/unknown` (attestation)
   children are untagged manifests. They trip `untagged_max_age_days` immediately, but GAR
   refuses to delete a child while its parent exists (`referenced by parent manifests`).
   Measured on the caller's repo: **52 untagged versions, 52 child links, zero orphans** —
   every "untagged" image the sweep saw was structurally undeletable.

Together they are absorbing: (1) holds parent indexes past their threshold, so (2) pins
their children for as long as that lasts. On a repo whose churn outruns the threshold —
this caller — the two close the loop completely and the sweep can only attempt things that
cannot happen. Elsewhere it degrades rather than stalls: a few real deletions per run,
around a plan that is mostly impossible.

**Why it wasn't caught.** The executor classifies `referenced by parent manifests` as
`OK skipped(kept-parent)` — correct for the cascade case, but it made a plan that was 100%
impossible indistinguishable from a healthy run. Nothing compared *planned* against
*achieved*. The 12 existing fixtures all built images with `days_ago`, which writes
`createTime`/`uploadTime`/`updateTime` to the *same* stamp, so no test could see which field
the age rule read, and no fixture modelled the index/child relationship at all.

**Fix.**
- Age from `createTime` (then `uploadTime`, then `updateTime`) — the field that answers the
  question the rule is asking.
- A new step resolves index → child links from the registry v2 API and the plan drops any
  candidate held by a **surviving** parent, reporting it under `blocked_by_parent`. A child
  whose parent is doomed in the same run stays queued, because phase 1 cascades.
- Best-effort by design: an unreachable registry yields an empty map and the previous
  behaviour (queue, absorb the error) — this must never become a new way for a sweep to fail.
- `planned > 0 && deleted == 0` now emits a workflow warning.

**Measured across the fleet, not reasoned** (AGENTS.md §5, and the correction entry below
it). The first draft of this entry claimed the sweep "never deletes anything" and that no
tagged image can ever age out. **That generalised one caller to the fleet and was wrong** —
`AutoMahn/project` deletes ~3 per run and `RealmID` cleared 125 in one. Both plan builders
were then run against real dumps of all three registries:

| repo | before (queued) | of which impossible | after (queued) | newly deleted | reported as held |
|---|---|---|---|---|---|
| `traide-in` | 20 | 18 | 3 | 1 (`v0.4.0`, 42d) | 18 |
| `auto-mahn` | 20 | 20 | 3 | 1 (`v0.0.104`, 31d) | 18 |
| `realm-id` | 112 | 111 | 9 | 2 (`v0.31.0` 32d, `v0.18.1` 31d) | 105 |

Two things that only the measurement shows. **The child defect is fleet-wide** — 50/50 and
200/200 untagged manifests on `auto-mahn` and `realm-id` are index children, and 18 of the
19 `kept-parent` skips in AutoMahn's 2026-08-11 run are confirmed children by digest. Those
repos looked healthy because a handful of real deletions hid a plan that was ~95% noise.
**The age change is small, not sweeping** — one or two extra images per repo, each 31–42
days old and outside the keep-set. It is still *more* deletion, so it remains a behaviour
change and callers should dry-run before repinning; it is not the mass prune the first
draft implied.

**Tested.** `t26` gives one image divergent per-field timestamps (created 90d, updated 3d)
and requires it to be deleted; `t25` models the buildx shape — index + amd64 + attestation
across a kept, a doomed and an orphan case — and asserts the split between `to_delete` and
`blocked_by_parent`. Both fail against the pre-fix source and pass after. `run_plan_tests.py`
now always writes the child map, so the suite cannot read a stray `/tmp` file from the host.
## 2026-08-11 — `badge_insert`: default-on badges may still be given to a repo, but it is now a nameable choice

**The open question from the hard-error audit, now decided.** The badge job *inserts* badges
after the first `# ` heading when a README has none, so the first default-branch build after
upgrading commits `chore(ci): update README badges` into a repo that never asked for badges.
Live since `v1.21.0` for every caller with `contents: write`.

**Decision: add `badge_insert`, default `true`.** Behaviour is unchanged for everyone —
nothing about existing callers moves — but the insertion stops being an unnamed side effect of
a different input. A caller who does not want to be given badges sets one boolean instead of
turning the whole feature off.

**Why not update-only-by-default.** That was the tempting option: no repo is ever committed to
unasked. But refresh-only makes default-on inert — no repo ever *gains* badges without someone
hand-seeding a badge line, which is the discoverability the default flip existed to buy. The
cost being avoided is one commit, once, in a repo whose owner granted `contents: write`.

**Why not leave it unnamed.** Because "the tool did something to my repo that no input
described" is the complaint, and `update_badges: false` answers it only by removing the
feature. A named opt-out is the smallest thing that makes the behaviour legible.

Docs for both workflows describe it; `catalog.json` regenerated so the contract is machine-
readable. A stale claim in `docs/ci-node.md` — that a missing coverage report fails the job
whenever badges are on — was corrected in the same pass: since `v1.21.1` that is an error only
when `coverage_threshold` is non-zero, and a warning otherwise.

## 2026-08-11 — `cleanup-gar-images` v2.0.0: retention is release-relative, not age-based

**The change.** Retention is now defined by release history. Per image name every artifact is
a **RELEASE** (carries a tag matching `release_tag_pattern`) or a **BUILD** (everything else —
sha tags, `:latest`-only images, other schemes, untagged manifests). Keep the last
`keep_semver_count` releases, plus every build newer than the `build_retention_releases`-th
most recent release, plus untagged children of kept releases. Delete the rest once it is more
than `grace_period_days` older than the oldest release-policy-retained image.

Out: `sha_tag_pattern`, `sha_retention_releases`, `untagged_max_age_days`,
`tagged_max_age_days`. In: `release_tag_pattern`, `build_retention_releases`,
`grace_period_days`, and a floor of 2 on `keep_semver_count`.

**Why the age model had to go, rather than be fixed.** Three defects found in one day were all
the same defect wearing different clothes:

- A repo whose tags churn faster than `tagged_max_age_days` never ages anything out, so
  `Traide-Co/project` ran green at `deleted=0` for six consecutive days while its registry grew
  to 580 MB.
- Two dry runs 2m27s apart produced different plans because two untagged digests crossed the
  15-day line between them — and the difference was investigated as a behaviour change in the
  workflow. It was the clock.
- The window that was supposed to protect promotion sources recognised images by
  `sha_tag_pattern`, so on the two registries that publish no sha tags it protected **nothing**
  and age made every decision unobserved.

Each was individually fixable. What they have in common is that *wall-clock age is not the
thing anyone actually means*. Nobody wants "delete images older than 30 days"; they want "keep
the last few releases and whatever has been built since". Encoding the real intent removes the
whole class.

**What the user specified, and where the implementation differs.** The rule as given was: keep
the last 2 releases and the non-release versions since the last release, falling back to the
2nd-last when the last release is the newest artifact. The conditional is not implemented —
`build_retention_releases: 2` always anchors at the 2nd-most-recent release, which is a
superset of that rule (it keeps strictly more, and coincides in the fallback case). A fixed
boundary is far easier to reason about at 3am than one that moves depending on what was pushed
last, and nothing the rule wanted kept is deleted.

**`grace_period_days` is anchored to the artifacts, not to `now`.** An artifact outside the
keep-set is deleted once it is more than N days *older than the oldest image the release policy
retained*. That is the reading of "older than (last retained image + grace period)" that ages
add up in, and it is the only one implementable without persistent state — the sweep sees a
registry listing, not history. Its real value is that the plan stops depending on the clock:
the 105-vs-103 investigation cannot recur.

Live digests and `keep_tags` protections deliberately **do not** move that anchor. They keep
their own digest, but if they moved the cutoff, one service pinned to a year-old image would
silently disable the sweep for the entire repo.

**The fail-safe is the point, not a side effect.** Fewer releases than the window needs ⇒ no
boundary ⇒ nothing is deleted, at any age. A repo that has never released, or whose
`release_tag_pattern` is wrong, is left alone. The cost is that a misconfigured repo is
indistinguishable from a healthy pre-release one — so a package with no release-tagged
artifacts now emits a `::warning::`. Six silent green days is the failure this pairs against.

**One clock.** v1 read three different notions of time in adjacent blocks: the keep-set ranked
on raw `updateTime`, the boundary on the oldest available field, the age rule on `createTime`.
So the keep-set and the window could disagree about which release was second-most-recent.
Everything now reads `created()`.

**Children of kept parents are kept, not reported.** #46 established that GAR refuses to delete
a child while its parent lives, and reported them under `blocked_by_parent`. v2 goes further:
if we are keeping the parent, the child belongs in the keep-set. `blocked_by_parent` remains
for the genuinely unexpected case. This is why #46 had to land first — v2 consumes its
parent/child map rather than duplicating the manifest walk.

**Breaking, and deliberately loudly so.** The four removed inputs are removed, not
accepted-and-ignored: a caller who believes they still have a 15-day grace period and does not
is worse off than one whose run refuses to start. Every caller pins an exact tag, so nobody
moves until they choose to.

**Expect a bigger first sweep.** v2 deletes more than v1 on an actively-released repo, because
v1 was silently retaining a backlog. Dry-run both pins per caller before repinning, per
AGENTS.md §5.

**Tests.** The v1 fixture suite asserted age-threshold behaviour that no longer exists; all 15
were retired and 14 written, each naming the v1 fixture whose intent it carries. The structural
probe changed too: v1 re-ran every fixture with the window off and asserted keep-only, which v2
has no switch for. v2 re-runs each fixture with a longer window and with a large grace period
and asserts neither deletes anything the default does not — both monotonicity claims the policy
makes.

## 2026-08-11 — Hard-error audit: a badge push failure could fail a caller's CI (bug fix)

Result of the hard-error audit `TODO.md` asked for before any future default flip. Every
`::error::` site in the 21 reusables (133 emissions across 68 steps) was classified by its
guard chain: is this reachable by a caller who never opted into the feature?

**Symptom.** None observed in the wild — found by audit. `ci-go`/`ci-node`'s `badges` job
ended `cat "$ERR" >&2; exit 1` for any push failure that did not match the read-only-token
regex (`403|permission|denied|not authorized|read-only|protected branch`). Badges are **on by
default** since `v1.21.0`, so a caller that never asked for them, but did grant
`contents: write`, gets a **red CI run over a cosmetic README commit** whenever the push fails
for any other reason: a protected branch whose rejection message doesn't match those words, a
required status check, a second concurrent push after the one rebase retry. The
`git pull --rebase` on the retry path was also unguarded, so under `set -e` a rebase conflict
failed the step outright before reaching any of the handling.

**Root cause.** The `v1.21.0` flip to default-on re-triaged the *permission* error path — the
one that was already known — into a warning, and stopped there. Every other failure branch in
that step kept the semantics it was written with when badges were opt-in, where failing loudly
was the right call because the caller had explicitly asked for the feature.

**Why it wasn't caught — and this is the interesting part.** It *was* covered.
`run_step_tests.py` executes this exact step body against a stubbed git remote, and carried an
assertion named **`genuine failure still exits 1`**. The behaviour was not an oversight; it was
pinned by a passing test. The test was written when badges were opt-in, where failing loudly
was correct, and the `v1.21.0` default flip never revisited it — so the suite went on
certifying opt-in semantics for a default-on feature, and its green tick actively discouraged
looking. Changing the code without changing that assertion is what surfaced it.

**Fix.** No badge failure fails the run. The rebase is guarded, and the terminal branch warns,
prints the underlying error on stderr, and exits 0. The information is preserved; it just
stops gating the build. Docs for both workflows now state this as a property, not a footnote.

**Prevention.** The generalisable rule, now stated in both docs: **a cosmetic, default-on
feature may never fail a caller's build.** And the sharper one, from how this hid: **flipping a
default invalidates the tests written for the opt-in era.** A test asserting `exit 1` encodes
"the caller asked for this"; when the caller no longer has to ask, that assertion has to be
re-derived, not inherited. The suite is now updated to assert the new contract, including that
the error is still surfaced. The wider audit found no other fatal path reachable
without opting in — the 22 always-reachable fatal steps are all core-purpose (resolve an image
ref, validate inputs, apply the alerts you asked to apply), and the remaining fatal paths are
gated by a caller's own configuration (`dry_run`, `deploy_target`, `deploy_method`,
`wif_provider`). The audit script is not shipped: it is a one-off structural pass, and a
permanent version would need to model guard semantics well enough to avoid false confidence.

**Left open, deliberately (needs a decision, not a fix).** The badge job *inserts* badges after
the first `# ` heading when none exist, so the first default-branch build after upgrading
commits `chore(ci): update README badges` to a repo that never asked. That is live today for
every caller with `contents: write`. Changing it is a behaviour change for existing callers,
so it is recorded in `TODO.md` rather than decided here.

## 2026-08-11 — The GAR 105-vs-103 delta is a wall-clock boundary crossing, not a logic change (root cause; corrects the earlier correction)

**Closes the open question** left by the "keep-only invariant is not true" entry below.

**What the evidence is.** Both dry-run plans were recovered from the actual runs
(`Realm-ID/project` run `31492420279` at 12:41 on `v1.15.0`, run `31492618604` at 12:43 on
`v1.21.1`) and diffed digest by digest. The two extra entries are:

```
api@sha256:01ce4ed…  tags: []  age_days: 15  reason: untagged>=15d
api@sha256:67a9d23…  tags: []  age_days: 15  reason: untagged>=15d
```

`untagged_max_age_days` is **15**, and the test is `age_days >= 15`. Both images sit
*exactly* on the boundary.

**Why that is a proof, not a hypothesis.** In the earlier run those digests were untagged,
not in the keep-set (the keep-set only ever grew — see below) and not selected, which is
possible only if `age_days < 15` at 12:42. In the later run `age_days == 15`. The threshold is
evaluated against `now` at plan time, and the two plans printed 2m27s apart. They aged past
the cut-off *between the two runs*. Two crossing together is what a single CI build produces:
it pushes both digests within a couple of minutes, so they cross a day-boundary together.

**So the keep-only invariant does hold — for the same input.** Independently checked three
ways: the delete loop and the live-digest collection step are **byte-identical** across the
two tags (`git diff v1.15.0 v1.21.1` touches neither); the keep-set can only grow
(`EFF_SEMVER_COUNT = max(KEEP_SEMVER_COUNT, N+1)`, the sha pass only calls `keep.add`);
and running **both tags' plan code over the same 13 fixtures** gives a delete-set that is a
strict subset at HEAD on every one. The earlier entry's claim — that the invariant is false —
was itself an inference from two numbers, and it was wrong. The measurement it rested on was
sound; the *comparison* was confounded, because the independent variable was not the only
thing that changed between the two runs.

**What this means for a repin proof.** A plan diff across two pins is only meaningful if
nothing else moved, and wall-clock time always moves. Any image within a day of a threshold
can flip between two runs minutes apart. So: a repin dry-run diff that shows only untagged
images at exactly the threshold age is **noise**, not evidence of a behaviour change. A diff
showing tagged images, live digests, or ages away from the boundary is real.

**What shipped.** `tests/fixtures/t23-untagged-age-boundary.json` pins the `>=` semantics at
14.99 / 15.01 days, so the boundary is now asserted rather than remembered. The per-fixture
monotonicity probe already in `run_plan_tests.py` (re-runs each fixture with
`SHA_RETENTION_RELEASES=0` and fails if the window run deletes anything extra) is what
executably guards the keep-only property — it passed throughout, including on the day the
invariant was declared broken. That signal was there and was not consulted.

**Lesson, refined.** "Measure, don't reason" was applied — and still produced a wrong
conclusion, because the measurement did not control its variable. The full form is: measure,
**and hold everything else fixed**, or you have measured the wrong difference.

## 2026-08-11 — Opt-in `node_modules` caching on `ci-node` and `deploy-cloudflare-pages`; Pages gains a separate `install_command`

**What changed.** New `cache_node_modules` input (default `false`) on both workflows: caches
`<working_directory>/node_modules` and **skips the install** on an exact lockfile hit.
`deploy-cloudflare-pages` also gains `install_command` (default `''`, i.e. today's behaviour).

**Why.** `node_cache` is `setup-node`'s cache of `~/.npm` only — npm still unpacks and links
the tree every run, which for a large app is most of the install. `eazyupdates-ui`'s outgoing
GKE workflow caches the tree itself and puts it at ~1.2 GB, so migrating it onto these
reusables as-is would have been a measurable build-time regression.

**Why the skip is mandatory, not an extra.** `npm ci` removes `node_modules` before
installing, so caching the tree while still running the install buys exactly nothing. The
value is entirely in not running the install — which is also the entire risk, because
lifecycle scripts (`postinstall`, `prisma generate`, `husky`, `playwright install`) then never
run. That is why it is opt-in, documented at length, and prints a `::notice::` when it skips:
a silently-skipped install is a miserable thing to debug from a build failure downstream.

**Why Pages needed a second input.** Its default `build_command` is `npm ci && npm run build`
— one string that installs *and* builds — so there was no install step to skip. Rather than
change that default (a behaviour change for every existing caller), `install_command` is
opt-in and empty by default. `cache_node_modules` without it is a **hard error at the top of
the job**: the alternative is deploying a build that quietly never used the cache the caller
asked for, and a wrong "this is cached" belief costs more than a failed run.

**Key design, deliberately strict:**

- **No `restore-keys`.** A prefix fallback restores a tree built from a *different* lockfile
  and then skips the install that would have reconciled it. A lockfile change must be a clean
  miss. (`eazyupdates-ui`'s own version had no fallback either — for the same reason.)
- **Keyed on the version `setup-node` resolved**, not the requested spec, so `lts/*` sliding
  to a new major misses rather than restoring native modules built against the old ABI.
- **Top-level `node_modules` only** — nested monorepo trees are explicitly not covered, and
  the docs say so rather than leaving a caller to discover a half-restored workspace.

**Not tested executably.** `tests/run_step_tests.py` runs `run:` bodies; this change is
`uses:`/`if:` expressions with no shell to exercise. Coverage is actionlint + the doc-example
lint. The behaviour worth asserting — a hit skips the install — needs a real runner.

## 2026-08-11 — Release version sweep automated: doc pins + a `WORKFLOW_VERSION` stamp, enforced twice

**What changed.** `scripts/stamp_version.py` sweeps the release version into both places
it appears: the `@vX.Y.Z` example pins across `docs/` + `README.md` (36 of them), and a new
`WORKFLOW_VERSION` key in each of the 21 reusables' top-level `env:`. CI gains a
`version-sweep` job, and `ci.yml` now also triggers on `v*.*.*` tags. `tests/run_stamp_tests.py`
covers the rewrites. Repo swept to `v1.24.0` — the tag this ships in.

**Why.** Every release since `v1.20.0` needed a manual `perl -pi` over the docs; skipping it
is how 39 pins once sat on twelve different tags. A chore that only a human remembers is a
chore that eventually doesn't happen.

**Why a stamp at all.** A called workflow cannot discover which version of *itself* is
running — a probe on 2026-08-11 established that `GITHUB_WORKFLOW_REF`/`_SHA` describe the
**caller**, and the `github` context carries no `job_workflow_sha` key (actionlint's model
doesn't know it either, and actionlint gates CI). Baking the version in at release time is
the only mechanism left, and it is the prerequisite for telling a caller it is out of date.

**Why two different checks rather than "is the newest pin older than the latest release".**
That phrasing was the obvious one and is wrong: it fails every unrelated PR opened in the
window between a release and its sweep, punishing people who touched nothing. Instead:

- **on PR/push** — `--check` asserts only that the tree agrees with *itself*. No network, no
  release ordering, no false failure.
- **on tag push** — `--check --expect <tag>` additionally asserts the tree agrees with the
  tag being cut. A skipped sweep fails the release, at the one moment it is actually wrong.

The sweep therefore belongs in the PR **before** the tag. Between merge and tag, `main`
advertises a version that isn't released yet; that window is inherent to stamping and is
bounded by the tag guard.

**Deliberately not swept:** the `v1` alias. It is a frozen legacy pointer, so a doc that
names it means it — the regex requires a full `vX.Y.Z` and leaves `@v1` alone (tested).

## 2026-08-11 — `deploy-cloudflare-pages` gains an opt-in, blocking post-deploy smoke check

**Context.** A successful `wrangler pages deploy` means the upload succeeded. It says
nothing about whether the site works. `Realm-ID/ui` learned this on **2026-06-29**, when a
stale bundle sat in production with a broken client-routed path and nothing noticed; it
hand-rolled a polling check afterwards, and that check is part of why the repo never
migrated onto this reusable. Six callers had the same gap.

**Decision.** Lift it: `smoke_path` (opt-in), `smoke_expect`, `smoke_status`, and a bounded
retry. Blocking when set — a check that reports without failing would not have caught the
original outage.

**Retry is not optional.** Pages deploys are eventually consistent, so a single request
false-fails on slow propagation. Defaults are 8 attempts at 5s, exiting the moment the
response is healthy rather than always spending the budget.

**The URL default matters more than it looks.** It tests **this run's deployment URL**, so
it verifies the bundle just uploaded. Pointing it at a custom domain is supported but only
correct for production-branch deploys: a preview deploy does not move the custom domain, so
a check against it would test the *previous* release and pass regardless of what shipped —
a check that cannot fail is worse than no check.

**Markers, not hashes.** Documented to use a root element id or `<title>`; hashed asset
filenames change every build.

**Tested.** `run_step_tests.py` runs the shipped body against a stubbed curl: healthy first
response (one request only), 404→404→200 propagation (passes, stops at three), persistent
bad status (fails, exhausts attempts, names the URL), **200 with a missing marker** — the
outage case — and a missing deployment URL failing with an explanation.

**Unblocks** migrating `Realm-ID/ui` off `cloudflare/wrangler-action@v4`, a mutable tag on a
workflow holding a Pages deploy token.

## 2026-08-11 — `cleanup-gar-images` unlocks and relocks immutable tags, and fails closed on both ends

> **Partly superseded 2026-08-12** (see the v2.1.0 entry above). "A repository without
> immutability never has its settings touched" is no longer true under the default
> `immutable_tags_policy: enforce`; everything else here still holds.

**Context.** GAR repositories can enforce **immutable tags**, which is how a `:v1.2.3` tag
stays a trustworthy deploy target — nothing can move it to a different digest. Verified
from `gcloud artifacts repositories update --help`: *"Tags cannot be deleted or moved to a
different image digest, and tagged images cannot be deleted."* Untagged versions remain
deletable. So on such a repository this sweep would **half-succeed**: untagged versions
deleted, every aged-out tagged image failing. For a destructive job that is the worst shape
— partial, and repeated weekly.

**Decision.** Detect immutability, unlock, sweep, relock. Automatic: no input turns the
*handling* on, because the sweep either can do its job or cannot, and a flag to half-do it
is not useful. The relock is opt-out (`relock_immutable_tags`, default `true`).

**The unlock window is the whole risk, so the design is built around closing it.**

- **Detect first.** A repository without immutability never has its settings touched.
- **Pre-flight the permission before deleting anything**, via `:testIamPermissions` on
  `artifactregistry.repositories.update` (there is no `gcloud artifacts repositories
  test-iam-permissions` subcommand). Missing ⇒ fail with **nothing deleted**. Discovering
  it mid-sweep is the bad outcome: partial deletions *and* an unlocked repository.
- **Relock under `if: always()`** — the deletion step exits 1 on unexpected failures, and a
  repo left unlocked by a *failed* sweep is a silent loss of the guarantee.
- **Verify by readback, not exit code**, and **fail the job** if the repository is still
  unlocked, printing the exact `gcloud` command. An unlocked repo must never be a quiet
  outcome.
- **`dry_run` never toggles.** Concurrency was already keyed per project+repo, so two runs
  cannot interleave and have one relock while the other is mid-delete.

**Why IAM is the real gate.** Rather than an input deciding whether this workflow may
change repository settings, the service account's permissions decide. A repo whose settings
should not be touched simply does not grant `artifactregistry.repositories.update`, and the
workflow fails with an actionable message. That is harder to get wrong than a boolean, and
it cannot be flipped by editing a caller.

**Opt-out is documented as dangerous, not neutral.** `relock_immutable_tags: false` warns
loudly and prints the re-enable command; the docs say plainly it must not be used in a
scheduled sweep.

**Tested.** `run_step_tests.py` executes the shipped relock body against a stubbed gcloud:
happy path, **update reports success but readback says unlocked** (must fail), update fails
while readback says protected (must pass — trust the readback), genuine failure, and the
opt-out path (warns, touches nothing, exits 0).

## 2026-08-11 — Onboarding retrospective: a generated contract file, an agent guide, and CI that keeps both honest

**Context.** Migrating one app (`eazyupdates-ui`) and repinning four caller repos in a day
produced five failures worth generalising. None were caused by a workflow being wrong; all
were caused by **what a consumer could not discover**:

1. **A shipped example that could not work.** The `v1.20.0` copy-paste example granted
   `contents: read` and called `ci-node`, whose badge job declared `contents: write`. GitHub
   aborts such a run at startup with no logs. `actionlint` cannot see cross-workflow
   permission caps, and the example was prose, so nothing checked it.
2. **A default flip that broke the first real caller.** `update_badges: true` switched
   coverage measurement on everywhere, and a missing report was a hard error (`v1.21.1`).
3. **A documented invariant that was never measured.** "keep-only, so it can only ever
   delete less" was false; a dry-run diff showed 103 → 105 candidates.
4. **Pin drift as the normal state.** 39 example pins across twelve tags, oldest six
   releases behind; `Traide-Co/webapp` frozen at `v1.15.0` by trap 1.
5. **An EOL default.** `node_version: '20'`, three months past end-of-life, reached every
   caller that omitted the input.

**Decision.** Three artifacts, chosen because each attacks a *class* of these rather than an
instance.

**`catalog.json` — generated, CI-verified.** Every workflow's inputs, types, defaults,
required flags, secrets, outputs and per-job declared permissions, derived from the shipped
YAML by `scripts/gen_catalog.py`. A consuming agent reads one JSON file instead of ~7,500
lines of YAML, and the file cannot drift: CI fails when a contract changes without
regeneration. It deliberately **omits the version to pin** — embedding it would recreate the
staleness problem between releases, so `AGENTS.md` tells the reader to resolve the latest
release at read time.

**`AGENTS.md` — the judgement layer.** What `catalog.json` cannot express: which workflow
fits which task, the one-file-per-repo caller shape, and a §4 of traps that each cost real
debugging time (permission caps failing silently, `environment:` being illegal on a caller
job, tokens belonging in `secrets:` not `with:`, static hosts having no runtime config). §5
requires a contract diff before any repin and a **dry-run plan diff** before repinning a
destructive workflow — the direct lesson of failure 3.

**CI that keeps both honest.** Two new jobs: `catalog.json is current`, and
`doc examples are valid workflows`, which extracts every fenced YAML block in `docs/` that
has both `on:` and `jobs:` — 25 of them today — and runs `actionlint` over each. That turns
examples from prose into code. It would not have caught failure 1 (a permission cap is
invisible to a linter), which is exactly why that trap is written out longhand in §4
instead.

**What was rejected.** A `~/.claude/skills/` skill: it would help one operator on one
machine, while the people onboarding are in other repos and other orgs. `AGENTS.md` in the
public repo reaches every consumer's agent and every human, and sits next to the thing it
describes.

**Known gap.** Nothing here detects a *caller* falling behind — the drift report in
`TODO.md` remains the missing piece, and today's work is more evidence it should be built:
every problem above was found by a human noticing, not by a system.

## 2026-08-11 — the `cleanup-gar-images` "keep-only" invariant is not true (correction)

> **Superseded the same day — this entry's conclusion is wrong.** The invariant does hold for
> identical input; the two runs compared here were 2m27s apart and both extra digests had
> aged past the untagged threshold in between. See *"The GAR 105-vs-103 delta is a wall-clock
> boundary crossing"* above for the recovered plans and the proof. Kept unedited below,
> because how the wrong conclusion was reached is the useful part.

**What we claimed.** The 2026-07-27 build-once entry, and `TODO.md` after it, described the
release-relative sha retention added in `v1.17.0` as **keep-only — "so it can only ever
delete less."** That claim was reasoning about the intent of the change, not a measurement,
and it was then used to justify treating `cleanup-gar-images` repins as low risk.

**What a measurement shows.** Repinning `Realm-ID/project` from `v1.15.0` to `v1.21.1`,
dry-run on both pins against the same `backend` repo minutes apart (310 images, 2 live
digests):

| | `v1.15.0` | `v1.21.1` |
|---|---|---|
| kept | 20 | 24 |
| delete candidates | **103** | **105** |

Diffed by digest: **2 digests are in the new plan and not the old, 0 the other way.** A
strict superset. Both additions are untagged `api` images, so the practical risk is low —
nothing tagged, nothing live — but the invariant is wrong, and it was load-bearing.

**Why it matters more than two images.** The claim is exactly what let a repin look safe
without evidence. `TODO.md` separately prescribed a dry-run proof per GAR repo; had that not
existed, this would have shipped on the strength of a sentence someone wrote from intent.
The lesson is the same one `v1.21.1` taught a few hours earlier: **a property that was
reasoned about is not a property that was measured**, and the difference only shows up
against a real caller.

**Action.** The claim is corrected in `TODO.md` with the measured numbers, and repinning a
`cleanup-gar-images` caller now explicitly requires a dry-run plan diff first. The root
cause of the two extra deletions is **not yet established** — the plausible mechanism is
that classifying sha-tagged images against the new window changes which untagged digests
fall outside the protected set, but that is untested. Deliberately recorded as open rather
than papered over.

## 2026-08-11 — Default-on badges must not fail CI for callers without a coverage report (bug fix)

**Symptom.** `Traide-Co/webapp`, repinned to `v1.21.0`, failed its first run:
`::error::coverage summary "coverage/coverage-summary.json" not found`. Install, lint and
test all passed — including the jump to Node 24 — and the run started cleanly, so the
`v1.21.0` permission fix worked. The Coverage step is what failed.

**Root cause.** The Coverage step runs when `coverage_threshold != 0` **or**
`update_badges` is on. Defaulting `update_badges` to `true` therefore switched coverage
measurement on for every caller, and a missing Istanbul `json-summary` was a hard
`::error::` + `exit 1`. That was defensible while badges were opt-in — you asked for badges,
so emit the report — but as a default it fails every caller whose `test_command` does not
produce coverage. Traide's is `npm test -- --run`: vitest, no `--coverage`.

**Why it wasn't caught.** When making default-on safe I reasoned through the paths that run
against repos that never opted in, and softened the missing-`readme_path` error for exactly
this reason — then missed the sibling case one step earlier in the same job. The step tests
added in `v1.21.0` covered the push, not the coverage gate. Linting and a green
reusable-workflows CI cannot catch it either: it only appears when a real caller without a
coverage reporter runs.

**Fix.** A missing report is fatal **only when `coverage_threshold > 0`** — an explicit gate
the caller asked for. Otherwise it emits a `::warning::` naming the reporter flag and exits
0; the badge step already omits the coverage badge when no value is available and still
writes the suppression badge. `ci-go` needs no equivalent change: it generates its own
profile with `go test -coverprofile`, so the report cannot be absent, and it only fails on
the threshold.

**Prevention.** `tests/run_step_tests.py` now executes the shipped Coverage body across all
five paths — missing report with and without a gate, present report under and over
threshold, and the value it emits. The broader lesson is recorded in `TODO.md`: flipping a
default turns every previously opt-in error path into a default one, and each needs
re-triaging as "would this be fair to a caller who never asked?"

## 2026-08-11 — README badges on by default; the badge job stops dictating caller permissions

**Context.** `update_badges` shipped opt-in (v1.16.0/v1.17.0) with the badge job declaring
`permissions: contents: write`. That declaration is static — permissions cannot be
conditional — and GitHub validates a **called** workflow's permissions against the caller
**at startup, before any job-level `if:` is evaluated**. So a caller granting
`contents: read` failed the entire run with `startup_failure` and no logs, *even with
`update_badges: false`*. `Traide-Co/webapp` hit this on a real upgrade and froze at
`v1.15.0` with a comment explaining why; the copy-paste example shipped in `v1.20.0` had
the same defect, patched in `v1.20.1`.

**Decision.** Badges default to **on** (opt out with `update_badges: false`), and the
permission trap is removed first — flipping the default before fixing it would have broken
every caller that had not granted write, which is most of them.

**Three changes make default-on safe.** The workflow-level `permissions: contents: read`
is gone and the badge job declares nothing, so it **inherits whatever the caller granted**;
the build/test jobs declare `contents: read` explicitly, so least privilege is unchanged
where it matters. The push then degrades: a permissions rejection emits a `::warning::`
naming both the fix and the opt-out, and exits 0. And a missing `readme_path` became a
warning-and-skip instead of `::error::` + exit 1 — defensible when someone opted in,
unacceptable when the feature runs against repos that never asked.

**Insert, not update-only** (user's call). Badges are inserted after the first `# ` heading
when absent, so the first upgrade lands a `github-actions[bot]` commit on callers' default
branches. Update-only was the conservative alternative and was rejected: it would mean the
feature never reaches anyone who has not already opted in, which defeats defaulting it on.

**The degradation is tested, not asserted.** `tests/run_step_tests.py` gained cases that
execute the shipped `Commit + push` body against a stubbed git: clean push, read-only token
(exits 0, warns, names `contents: write` and the opt-out, does not retry), concurrent-push
rebase-and-retry, genuine failure (still exits 1, error surfaced), and no-change. It also
asserts the `ci-node` and `ci-go` bodies are byte-identical, since the two silently drifting
is the likely way this regresses.

## 2026-08-11 — Private npm registry auth on `ci-node` + `deploy-cloudflare-pages`, delegated to `setup-node`

**Context.** Planning the `zopsmart/eazyupdates-ui` migration from GKE/nginx to Cloudflare
Pages surfaced the first hard blocker to reusing our own CI/deploy workflows: the app
depends on `@zopsmart/zs-components`, published to GitHub Packages. Its existing workflow
hand-writes `~/.npmrc` with a PAT before `npm ci`. Neither `ci-node` nor
`deploy-cloudflare-pages` could authenticate to any registry, so the caller could not have
been migrated at all — a capability gap, not a preference.

**Decision.** Add `npm_registry_url` + `npm_registry_scope` inputs and an optional
`npm_auth_token` secret to both workflows, and wire them to `actions/setup-node`'s
`registry-url` / `scope` inputs plus a step-level `NODE_AUTH_TOKEN`. Ships as `v1.20.0`.

**Why a secret, not an input.** `workflow_call` **inputs are not masked in logs**; secrets
are. A token passed as an input would be one `set -x` or a verbose npm error away from
appearing in a public run log. The registry URL and scope are not credentials and stay
inputs.

**Why delegate to `setup-node` rather than write `.npmrc` ourselves.** We already depend on
the action, and its behaviour was verified at our pinned SHA (`8207627…`, v7.0.0) rather
than assumed: `src/main.ts:65-67` only calls `configAuthentication` when `registry-url` is
non-empty, and `src/authutil.ts` writes `$RUNNER_TEMP/.npmrc` containing
`//<host>/:_authToken=${NODE_AUTH_TOKEN}` plus `@scope:registry=<url>`, exporting
`NPM_CONFIG_USERCONFIG`. The token is expanded by npm at install time, so setting it as
step-level `env:` works even though `setup-node` ran earlier. Owning that file ourselves
would mean owning yarn/pnpm compatibility too, for no gain.

**That guard is what makes this non-breaking**, and it is the reason the defaults are empty
strings rather than anything cleverer: an existing caller that passes neither input gets a
runner state byte-identical to before — no `.npmrc`, no `NPM_CONFIG_USERCONFIG`. The added
`NODE_AUTH_TOKEN: ''` on the install step is inert, since nothing references it unless a
registry was configured (and npm errors on *unset* config references, not empty ones).
`ci-node` gained its first `secrets:` block; a `required: false` secret is invisible to
existing callers, including those using `secrets: inherit`.

**Placement of the token differs by workflow, deliberately.** `ci-node` has a dedicated
install step, so the token goes there and nowhere else. `deploy-cloudflare-pages` has no
install step — its `build_command` defaults to `npm ci && npm run build` — so the token
goes on the build step. Narrower is better: a token on a step that never installs is
exposure without purpose.

**Also in this tag: the default `node_version` moves `20` → `24`.** Node 20 reached
**end-of-life on 2026-04-30** (verified against `nodejs/Release`'s `schedule.json`, not from
memory), so the default was handing every caller that omits the input a runtime with no
security patches — and the docs were teaching it, with `'20'` in four examples. 24 is the
active LTS (EOL 2028-04-30); 22 remains supported until 2027-04-30 for anyone who wants a
smaller jump.

Strictly, changing a default is behaviour-affecting rather than a contract change, which
argues for a major. It ships in a minor because the blast radius was measured, not assumed:
of the migrated callers, **only `AutoMahn/website` omits `node_version`, and its
`build_command` is `'true'` — it never executes Node.** Every other Pages/CI caller pins
`'22'` explicitly and is unaffected. Callers who genuinely need the old runtime can pin
`node_version: '20'`, though they should not. Called out in the release notes.

**Shipped alongside, in the same tag:** a copy-paste **CI + stage + prod** example in
`docs/deploy-cloudflare-pages.md`, and a sweep of **every** example pin in `docs/` and
`README.md` to `v1.20.0`. The sweep is the more consequential of the two: all 39
`uses: …@vX.Y.Z` lines were spread across twelve tags, the oldest `v1.4.0` — six-plus
releases behind — so a reader copying almost any example silently adopted a stale input
contract. That is the same drift the 2026-07-27 caller repin found in real repos, and the
docs were quietly teaching it. The example is checked, not just written: its YAML block is
extracted, parsed and run through `actionlint` clean.

The single-workflow shape it documents is deliberate. Callers wanting "one workflow for
CI/CD" get it by composing `ci-node` and `deploy-cloudflare-pages` as two jobs joined by
`needs:` — **not** by adding test/lint inputs to the deploy workflow. Gates chained into
`build_command` (as two fleet callers do today) collapse into one opaque step with no
coverage gate, no service containers and no per-stage reporting, and do nothing on pull
requests, where you want the gates but must not deploy. `needs:` is a real dependency;
`&&` in a shell string is not.

**Known limits, documented rather than engineered around.** `setup-node` writes exactly one
registry line, so a repo pulling scoped packages from two private registries must still
hand-roll `.npmrc`; and because its file is the npm *user* config, a repo-committed
`.npmrc` outranks it. Generalising to multiple registries is in `TODO.md`, deliberately
deferred — no caller needs it, and the moment we support a list we are back to owning the
file. For GitHub Packages the token needs `read:packages` and must be a PAT when the
package lives in a different repo than the caller; `GITHUB_TOKEN` does not reach it.

## 2026-07-28 — `promote-image` races the build it promotes from: bounded `source_wait_seconds`, plus the first executable `run:`-body tests (bug fix)

**Context.** The build-once model (see the 2026-07-27 entry) splits what used to be one
job into two independent workflow *runs*: a push to `main` builds `:<sha>`, and a release
tag promotes it. Nothing connects them — `needs:` cannot span runs — so the handoff is
ordered only by wall-clock luck. Cutting the release in the same breath as the merge (the
normal human motion, and what a release-on-merge automation does by construction) lands
the promote first, and it fails on a healthy build.

### RCA

**Symptom** — a release tag cut right after a merge fails in `promote-image` with
`source image not found: …:<sha>`. Re-running the same release minutes later succeeds
with no code change, which is the signature of a race rather than a config error.

**Root cause** — the source-image preflight was a *single* `gcloud container images
describe` (`promote-image.yml`, "Retag" step). It encodes an assumption the architecture
does not provide: that the build for this commit has already pushed by the time the
promote starts. Splitting build from promote into separate runs removed the ordering
guarantee that the old single-job build-and-deploy had, and the preflight was never
revisited — a contract mismatch introduced by the build-once split, not a bad line.

**Why it wasn't caught** — three gaps compounded. (1) The build-once rollout is still
pre-pilot (`TODO.md`: no repo converted yet), so the two-run handoff had never run
against a real registry. (2) A race only reproduces under a specific interleaving; the
happy path is indistinguishable. (3) Nothing in CI could *execute* a `run:` body —
actionlint/shellcheck lint the script but never run it, the gap `TODO.md` already
recorded after the `deploy-cloud-run` Summary bug shipped the same way.

**Fix** — a new `source_wait_seconds` input (default `0` = probe once and fail, the
historical behaviour). When set, a "Wait for source image" step polls for `:source_tag`
with 10s → 20s → 30s-capped backoff, clamped so the last sleep cannot overshoot the
budget, and probes once more *after* the deadline. Exhausting the budget fails with a
message naming the image, the budget, and the build run to go look at — the actual
diagnosis, since after the wait a missing image means the build failed, not that it was
slow. `timeout_minutes` is validated against the wait up front: a budget the job timeout
cannot accommodate is a config error, not a mysterious cancellation. The wait is skipped
under `dry_run` (a plan should report presence, not block on it), and the immediate
failure path now names `source_wait_seconds` in its error.

**Prevention** — `tests/run_step_tests.py` plus a `step-bodies` CI job: it extracts a
named step's `run:` script from the shipped YAML and executes it under `bash -eo
pipefail` against stubbed `gcloud`/`date`/`sleep`, with time faked so the backoff
schedule is asserted exactly and the suite is instant. Mutation-checked — removing the
30s cap or the budget clamp each turn the suite red. This closes the `TODO.md` item
"CI cannot execute a workflow *step*" for any body worth covering, not just this one.

**Why wait on the artifact, not on the build run.** The alternative was polling the
GitHub API for the workflow run on the same SHA, which fails fast (seconds) when the
build *failed* instead of burning the whole budget. Rejected: it couples `promote-image`
to a caller-supplied workflow filename and job naming, and it asserts the wrong thing —
the retag needs the image to exist, and "a run succeeded" is a proxy for that, not the
thing itself. Waiting on the artifact stays correct no matter which workflow, trigger, or
repo produced it, which is what "callers own their trigger" demands. The cost is bounded
and paid only on the failure path.

**Not fixed here (caller-side).** A caller that would rather not wait at all can gate the
tag on the build with `workflow_run` instead of `push: tags` — documented in
`docs/promote-image.md` as the alternative, not adopted as the default because it is
per-repo boilerplate across all five repos and re-derives the tag from the run payload.

Ships as **`v1.19.0`**, together with the `run-db-job`/`docker_target` entry below —
one tag, both additive, defaults preserve today's behaviour. (`v1.18.0` is already cut
against the `min_value_length` secrets work; `v1.16.0` remains claimed by the badges
work.) The two are unrelated in subject but land on `main` in the same merge, and semver
here tracks the input contract, not the topic.

## 2026-07-28 — `run-db-job` built; `docker_target` added; the runner-side prebuild hook deliberately left out

**Context.** Driven by the `AutoMahn/api` conversion — the last of the five in the
build-once rollout and, per `TODO.md`, the hardest: it drives three Cloud Run resources
off one image. Auditing what that caller actually needs turned up **fewer** gaps than
expected, and one input we chose not to add.

**Two of the four apparent gaps needed no change here.**

- *Three resources off one image.* `deploy-cloud-run` already exposes `service_url` as a
  workflow output, so a caller chains eventworker → api with
  `needs.<job>.outputs.service_url`. Multi-service orchestration is caller-side
  composition, not a missing feature.
- *Post-deploy health assertion* (poll `/…/health` until it reports the deployed tag).
  Caller-side. The library has no business knowing an app's health-check shape.

**Built: `run-db-job`.** Converge a Cloud Run **Job** from an already-built image, then
execute with `--wait`. Already on `TODO.md` under "Reusables still to build". Design
notes worth keeping:

- **Create-or-update, not create-then-ignore.** `describe` picks the verb, so a fresh
  project needs no bootstrap and re-runs are not errors.
- **A non-zero task exit fails the workflow.** That is the entire value — it lets a
  caller gate the service roll on `needs:` so a new revision never meets a schema it
  predates.
- **Failure diagnostics are part of the contract.** `gcloud run jobs execute` reports
  *that* an execution failed, never why, so the workflow prints the execution status and
  a Logs Explorer link. It also names the empty-log case explicitly — a batch binary
  wired to a discarded logger is indistinguishable from a silent crash (cost a caller
  ~1h on `AutoMahn/api` v0.0.7).
- **No `jgd_commit` stamp, no GitHub Deployment record** — deliberately unlike
  `deploy-cloud-run`/`promote-image`/`rollback-service`. Forward-only reads an
  environment's live commit from what its *services* serve; a one-shot Job is not "live",
  so stamping one would write a second, conflicting answer into that baseline.
- Ordering (migrate → service) stays in the caller via `needs:`, consistent with how
  pre-deploy gates are already expressed.

**Added: `docker_target`** on `deploy-cloud-run` — a passthrough to
`build-push-action`'s `target:`, default `''`, which is what the action already assumes
(last stage). For Dockerfiles carrying several leaves.

**Not added: a runner-side prebuild hook — and this is the substantive call.**
`AutoMahn/api` compiles Go on the runner and `COPY`s the binary into a `app-prebuilt`
stage, because BuildKit cache mounts are not exported by `cache-to: type=gha`, so an
in-image `go build` starts cold every run. A reusable workflow is a separate job that
does its own checkout, so that binary cannot cross the boundary — supporting it means
either a Go toolchain step in this workflow (`prebuild_run:` can't reach
`actions/setup-go`'s cache, which is the whole point, so it degrades to a typed
language input) or an artifact-transport pair of inputs.

Rejected for now on three grounds. **(1)** Language creep: `deploy-cloud-run` is
deliberately language-agnostic, and `ci-go`/`ci-node` are where language knowledge
lives. **(2)** Correctness moves out of reach: with caller-supplied shell this workflow
cannot verify the artifact matches the Dockerfile's target platform, and a `GOARCH`
mismatch builds clean and dies on Cloud Run with `exec format error`. **(3)** The premise
is unmeasured — the caller's on-runner build currently takes 111–116s, not the ~27s it
was designed around, because `actions/setup-go` reports an exact cache hit and therefore
never re-saves, freezing a build cache compiled with different flags. Under build-once
that compile also moves off the release path onto `main` pushes.

So: fix the cache on the caller side, measure, and only then decide. If runner-side
compilation proves worth preserving, the shape to add is **artifact transport**
(`prebuilt_artifact` + `prebuilt_path`) — the one that doesn't teach a cloud-deploy
workflow about programming languages. Adding an input to a shared library on a
projection is how the caller got here in the first place.

**Compatibility.** Both changes are additive with defaults that reproduce current
behaviour, and every caller pins a tag, so nothing moves until a caller repins.
*Caveat:* the consumer list was **not** fully enumerated — `gh search code` returns
nothing for the private orgs, and only two callers were confirmed directly
(`Realm-ID/issuer` @v1.17.1, `AutoMahn/image-service` @v1.15.0). Additive-only is what
makes that acceptable rather than verified.

Ships as **`v1.19.0`**, in the same tag as the `promote-image` race fix above.

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
