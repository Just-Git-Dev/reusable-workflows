# Decisions — reusable-workflows

## Index

Newest first. Entries below the split live in [`DECISIONS-ARCHIVE.md`](DECISIONS-ARCHIVE.md) —
archived by age only; nothing is deleted, and both files are greppable.

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
