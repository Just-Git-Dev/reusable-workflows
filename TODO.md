# TODO — reusable-workflows

## Index
36 open across 10 live sections. 8 closed items archived.

Status is the section's own, not per item; keep it current by hand when a
section opens or closes. Closed sections live in
[TODO-ARCHIVE.md](TODO-ARCHIVE.md) — same log, split by state only.

- **ACTIVE** — [Service alerts — rollout and deferred slice (opened 2026-09-23)](#service-alerts--rollout-and-deferred-slice-opened-2026-09-23) — 6 open
- **ACTIVE** — [Post-deploy probe — prove the observability pipeline actually DELIVERS (opened 2026-09-18)](#post-deploy-probe--prove-the-observability-pipeline-actually-delivers-opened-2026-09-18) — 1 open, 1 closed
- **ACTIVE** — [Two items rehomed from the inflight tracker (opened 2026-09-08)](#two-items-rehomed-from-the-inflight-tracker-opened-2026-09-08) — 2 open
- **ACTIVE** — [RealmID (`realm-id`) has no alerts caller — adopt `bootstrap-alerts` (opened 2026-09-07)](#realmid-realm-id-has-no-alerts-caller--adopt-bootstrap-alerts-opened-2026-09-07) — 3 open
- **ACTIVE** — [Release hygiene — the `WORKFLOW_VERSION` stamp (regression found 2026-09-06)](#release-hygiene--the-workflow_version-stamp-regression-found-2026-09-06) — 4 open
- **ACTIVE** — [Build attestations](#build-attestations) — 1 open
- **ACTIVE** — [Secret Manager](#secret-manager) — 1 open, 2 closed
- **ACTIVE** — [Build-once, promote-to-prod](#build-once-promote-to-prod) — 5 open, 3 closed
- **ACTIVE** — [Convergence — remaining work](#convergence--remaining-work) — 13 open, 16 closed
- **REFERENCE** — [Convergence — operating facts that live nowhere else in this repo](#convergence--operating-facts-that-live-nowhere-else-in-this-repo) — 0 open

## Service alerts — rollout and deferred slice (opened 2026-09-23)

Plan: `plans/service-alerts.md`. Why: DECISIONS 2026-09-23.

- [ ] **First live `dry_run` on realm-id.** Proves three things no test here can:
  `job_workflow_sha` is present in a called workflow's token (spike 0d); gcloud's
  `--filter="userLabels.rule_id=…"` matches; and the data check sees GMP series. Owner-gated:
  it needs the realm-id `github-rotator` SA granted `monitoring.editor` (infra-provisioning).
- [ ] **First apply on realm-id + fire test.** Settles whether log-match policies need
  `logging.notificationRules.create` (spike 0e). Then override `cloudrun.latency_p95` to `1ms`,
  wait for the email, and revert (`docs/service-alerts.md#proving-it-works`).
- [ ] **Promote the GoFr rules from ticket to page after RealmID's soak re-check (~2026-09-26).**
  gofr#4266 degrades with revision uptime, and the fix isn't proven on a days-warm revision.
- [ ] **Traide and AutoMahn migrate** in their own sessions: packs, parity check, then delete
  the MQL / hand-written policy files (`docs/service-alerts.md#migrating-from-hand-written-policies`).
- [ ] **v2.11 slice:** `prune` (owner-scoped), `probe.health_body` uptime check (opt-in, since
  it keeps instances warm), and the `gofr-http-client` / `gofr-pubsub` / `gofr-cron` packs once
  their metrics exist somewhere to verify against. Also `absence`, raw `promql:` (GMP-only),
  the drift WARN for hand-written policies, and `render_dynatrace`.
- [ ] `.github/workflows/service-alerts.yml` — the data check fails a rule whose service had no
  traffic for a whole day only when EVERY service in it is empty. A per-service gap is only a
  warning. Revisit if quiet services turn out to hide real breakage.

## Post-deploy probe — prove the observability pipeline actually DELIVERS (opened 2026-09-18)

Handed over from the Traide umbrella session. The owner ruled this a **platform** concern, not a
Traide one: the incident was Traide's, the failure class is generic. **Filed for triage, not
started** — nothing here is designed or agreed yet.

- [x] **A post-deploy probe that fails the release when metrics are not arriving.** ✅ **BUILT
      2026-09-18 as `verify-metrics-arrival.yml`** — see `docs/verify-metrics-arrival.md` and
      `DECISIONS.md` 2026-09-18. Three outcomes (PASS / no-metrics / **cannot-verify**), an
      unfiltered positive control, a *list* of prefixes with PASS on the union, and the log grep
      pinned to the **serving** revision. Six paired step-body tests. Original entry: The failure
      class: *a broken observability path deletes the very signal that would announce it.*
      Traide's api ran for weeks with its GCP OTel exporter delivering **zero** metrics because
      `OTEL_RESOURCE_ATTRIBUTES` lacked `gcp.project_id`. Every gate stayed green the whole time
      — deploy, Cloud Run startup probe, `/.well-known/alive`, `migrate-smoke`, `storage-probe` —
      because the only evidence was a log line *inside the container*, and the thing that would
      have raised the alarm was the pipeline that was down. Above the container log, "exporter
      broken" and "quiet system" are indistinguishable.

      The concrete check, as handed over (two parts, post-deploy, fails the release):
      1. List `metricDescriptors` for a given prefix on a given GCP project and **fail on zero**
         (Traide's case: prefix `prometheus.googleapis.com/`, project `traide-in`).
      2. Grep the **serving** revision's logs for the exporter's upload error and fail on any hit
         (Traide's case: `failed to upload metrics` on service `traide-api`).

      **The positive-control requirement is the load-bearing part.** A probe that returns zero
      because it queried the wrong project, the wrong prefix, or ran under an account without
      permission must **fail loudly** — never read as "no metrics yet". Zero-results and
      can't-tell have to be distinguishable outcomes. Without that, this probe is just another
      green tick that measures nothing, which is the exact class of bug it exists to catch.

      Two traps measured independently in this workspace on 2026-09-18, both of which would sink
      a naive implementation:
      - **`gcloud monitoring metrics-descriptors` does not exist** as a subcommand. It errors
        `Invalid choice`, and `| wc -l` over the empty stdout returns 0 — i.e. it reports "no
        metrics ever arrived". Use the Monitoring REST API and assert the HTTP status.
      - **The prefix is not obvious and a wrong one returns a truthful-looking 0.** For
        `realm-id`, `custom.googleapis.com/` and `workload.googleapis.com/` both return 0 while
        `prometheus.googleapis.com/` returns 7 — GMP publishes under the `prometheus.` prefix.
        This is precisely why the control is mandatory rather than nice-to-have.

      **No fire:** the Traide instance is fixed (api v0.56.3). Verified by that session on
      2026-09-18 — `traide-in` now holds 7 `prometheus.googleapis.com/` descriptors (was zero)
      and no `failed to upload metrics` lines on `traide-api` in the preceding 3 hours. This item
      is the generic prevention.

      Pointers, all in `Traide-Co/api`: `docs/rca-metrics-never-reached-google-2026-09-18.md`
      (full RCA), `DECISIONS.md` 2026-09-18 (b), `TODO.md` L11-21 (the original entry, still
      worded as api-owned; that session is re-pointing it separately).

- [ ] **Wire the first callers.** The workflow ships; nothing calls it yet, and nothing *can*
      until `infra-provisioning` grants an SA that holds both `monitoring.viewer` and
      `logging.viewer` (the `observability-read` capability, WIF-only). Order: `traide-co` — the
      incident project — then `realm-id`. Each caller is a PR in that app repo, so it is a
      cross-project change, not work for this repo.
      **AutoMahn is deliberately excluded**: it imports no GCP metrics exporter, so it exports
      nothing at all and this probe would red every release until that is fixed. Adopting it
      there is a separate decision about AutoMahn's exporter, not about this probe.

## Two items rehomed from the inflight tracker (opened 2026-09-08)

Both were carried as live state in `~/.claude/inflight/` for several sessions. Neither is
live state — they are backlog, so they belong here. Recorded verbatim; neither is started.

- [ ] **CI guard: assert the `v1` alias has NOT moved.** ⚠️ **Rewritten 2026-09-15 — this item
      previously asked for the exact opposite and was wrong.** It read "assert the `v1` alias
      points at the newest `v1.x` tag", which contradicts its own next sentence ("`v1` is a
      frozen legacy alias") and contradicts the ruling in `DECISIONS-ARCHIVE.md`: *"`v1` is
      frozen, not moved. Releases are immutable."* Moving `v1` onto a newer release was
      considered there and **rejected** — `deploy-cloudflare-pages.yml` did not exist at `v1`,
      so re-pointing it would hand every legacy caller a breaking change as a surprise.
      Measured 2026-09-15: `v1` → `b96d0e3`, the original 5-workflow commit (no `v1.x.y` tag
      sits on it), exactly as `DECISIONS.md` and `README.md:137` say it should.

      A guard built to the old wording went red against this repo on its first run and would
      have made CI permanently red; its natural "fix" (`git tag -f v1 v1.24.0`) is precisely
      the breaking change that decision exists to prevent. **The real invariant is that `v1`
      must never move**, and the failure worth catching is someone "helpfully fixing the
      drift". Build it that way: pin the expected SHA, fail loudly if it changes, and make the
      failure message say `v1` is frozen on purpose rather than suggesting a re-point.

- [ ] **Owed to AutoMahn: audit `validate-alerts` for derived-comparand and assumed-scope
      gates.** The linter's checks were reviewed for MQL execution (closed 2026-09-01, below)
      but not for two classes it may pass vacuously: a threshold compared against a value the
      policy itself derives, and a check that assumes a scope the policy never declares. Until
      audited, a green `validate-alerts` is weaker evidence than it reads as.

      ✅ **AUDITED 2026-09-15 — zero live instances of either class.** Full per-check table with
      verdicts: [`plans/validate-alerts-audit-2026-09-15.md`](plans/validate-alerts-audit-2026-09-15.md).
      Every comparand traces either to a fixed external constant (GCP's own documented enums and
      ranges — `COMBINERS`, `AUTOCLOSE_MIN/MAX`, `CONDITION_KEYS`, `DOC_MIN_CHARS`) or to two
      independently-authored policy fields compared for a real anti-pattern (`documentation.content`
      restating `displayName` — the closest thing to class 1, but neither side is computed from
      the other, so it is not self-derived). The `gcp_project` scope layer-2 runs against is a
      **required `workflow_call` input**, not an assumption, and skipping layer 2 when it is unset
      is a **declared** skip printed in the step summary, not a silent no-op. The two 2026-09-01
      findings were a different shape (execution-layer coverage — "a result that never arrived read
      as a pass") and are both fixed and mutation-tested.

      ⚠️ Leaving this item OPEN for one reason only, and it is not a vacuity finding: four checks
      have **no dedicated test** — `combiner`, the `notificationChannels` placeholder, the
      `autoClose` range, and the log-condition rate-limit requirement. Reading the code says they
      are structurally sound; nothing *executes* them. That is the gap to close, not a rewrite.

## RealmID (`realm-id`) has no alerts caller — adopt `bootstrap-alerts` (opened 2026-09-07)

`auth` hand-rolled `infra/alerts/apply-alerts.sh` instead of calling this repo's
`bootstrap-alerts.yml`, so it re-implements skip-if-exists **without** a `force_update`
escape — editing a `policy-*.json` is a silent no-op against the live policy. The blocker
that made it reach for a local script is fixed as of 2026-09-07 (JSON policy files are now
read by both the linter and the applier; see `DECISIONS.md`).

- [ ] `auth/infra/alerts/policy-*.json` — add `"notificationChannels":
      ["NOTIFICATION_CHANNEL_PLACEHOLDER"]` to each; the files currently carry no such key
      because the script passes `--notification-channels` on the CLI, and
      `validate-alerts.yml` **fails** a policy without it (correctly — it would notify nobody).
- [ ] `auth/infra/alerts/email-channel.json` — no channel file exists yet; the script takes
      the channel id from the `NOTIFY_CHANNEL` env var instead.
- [ ] `auth/.github/workflows/` — add a thin caller with `channel_file: email-channel.json`
      and `policy_glob: 'policy-*.json'`, then retire `apply-alerts.sh`.

**Cross-repo: the checklist above is auth-repo work, not ours.** Recorded here only so the
platform side knows why `realm-id` is the one project not on the shared alerts body.
Still uncovered there and the reason this surfaced: the OTel→GMP app metrics
`app_http_response` / `app_sql_*` have no alert policy at all — uptime only.

## Release hygiene — the `WORKFLOW_VERSION` stamp (regression found 2026-09-06)

`v2.6.1` shipped with **all 26 workflow files still stamping `WORKFLOW_VERSION: v2.6.0`.**
Fixed by `v2.6.2`, which carries the stamp bump and nothing else.

**Root cause: the sweep wasn't run before tagging — and CI CAUGHT IT AND WAS IGNORED.**
`python3 scripts/stamp_version.py vX.Y.Z` sweeps the 26 stamps and 49 doc pins together.
`v2.6.1` was tagged directly onto fix commit `4034d3d` (#83) without it.

⚠️ **The tag-push gate already exists and already worked.** `ci.yml` triggers on
`tags: ['v*.*.*']` and runs `stamp_version.py --check --expect "${{ github.ref_name }}"` when
`github.ref_type == 'tag'`. On the `v2.6.1` tag push (run **34029676674**, 2026-09-06T11:14) ten
jobs passed and *"version stamps and doc pins agree"* **FAILED**, saying:
`repo is swept to v2.6.0 but the tag being released is v2.6.1. Run python3
scripts/stamp_version.py v2.6.1 and merge that before tagging.` The release was published without
reading it. **Nothing needs building here — the control exists, is correct, and was ignored.**
(Earlier drafts of this section claimed first that no gate existed, then that it was vacuous and
green. Both were wrong; the run log settles it.)

⚠️ **Impact was NOT provenance-only.** The same skipped sweep left **49 doc pins saying
`@v2.6.0`** at tag `v2.6.1`, so the published docs told consumers to pin a version *without* the
GAR readback fix that release shipped.

- [ ] **Runbook: never publish a release until the tag-push CI run is green.** This is the whole
      fix and it is procedural, not code. Tagging is not the last step — it is the step that
      starts the only check capable of catching this.
- [ ] **Make it structural rather than remembered:** price a GitHub ruleset requiring the
      tag-push check to pass before a release can be published. Preferred over any new script.
- [ ] **The gate does not assert its own COVERAGE.** `PIN_RE` in `scripts/stamp_version.py`
      requires a literal `Just-Git-Dev/reusable-workflows/...`, so any file whose pins use an
      `<org>/` placeholder (or any other shape `PIN_RE` doesn't match) is invisible to both the
      sweep and `--check` — **an uncovered file is indistinguishable from a passing one.**
      Checked 2026-09-15: `docs/PLATFORM.md` is *not* currently a live instance of this — it has
      no version pin at all, only the literal placeholder `@vX.Y.Z` (lines 118, 162, 177, 187),
      and the repo is swept consistently (`stamp_version.py --check --expect v2.7.0` → "version
      sweep is consistent at v2.7.0 (26 workflows, 49 doc pins)", exit 0). Downgraded from 🔴
      accordingly — there is no live breakage today, just an unguarded structural gap. Still
      worth closing before it bites: fix is to assert that every file containing a
      `uses: .../reusable-workflows/...@` pin (by any regex, not just `PIN_RE`'s) is in the
      swept set, and fail on any that is not — otherwise the next `docs/*.md` added with a
      real (non-placeholder) pin is silently exempt from the sweep. (Framing owed to AutoMahn's
      session, 2026-09-06; false live-instance claim corrected 2026-09-15.)
- [ ] **Audit the other gates for the same two shapes** — comparands that are all derived, and
      scopes that are assumed rather than computed. Start with `validate-alerts`, which already
      had a vacuous-check finding on 2026-09-01 for an unrelated reason; two independent vacuity
      findings in one layer says something about how those gates are written.

### Consumer pin inventory (for the separate, unstarted sweep — NOT the v2.6.2 bump)

Regenerate this from this repo's own tool rather than trusting the numbers below to still be
current: `python3 scripts/fleet_drift.py --orgs Realm-ID,Traide-Co,AutoMahn`.

**Verified 2026-09-15** (after six cleanup-caller pins moved to `v2.7.0` that day across
Realm-ID/project, Traide-Co/project, AutoMahn/project — PRs #17/#149/#45, all merged): **57
caller lines fleet-wide — 37 STALE, 20 OK, 0 MUTABLE**, spread `v2.3.1` → `v2.5.0`. Zero mutable
pins — nothing is on `@main` or the `v1` alias, so the supply-chain risk that motivated this
section is not currently live anywhere. Deepest stragglers are on the deploy path:
`Realm-ID/api` and `Realm-ID/issuer` `deploy.yml` pin `deploy-cloud-run` and `promote-image` at
`v2.3.1`, four minors behind. `cleanup-secret-versions.yml` is deliberately still at `v2.4.1` in
all three consumer repos — that bump is not a no-op, it swaps a project-level `gcloud secrets
list` for a per-secret `gcloud secrets describe` and changes the IAM the caller needs, so it is
not being tracked as drift.

**The repin itself is consumer-repo work, not this repo's.**

Keep this OUT of any stamp/pin one-liner: different workflows, different input contracts, and
semver here tracks the **input contract**, so each pin needs its own diff read before moving.

## Build attestations

- [ ] **Decide a `provenance` policy for the build reusables — right now it is inherited, not
      chosen.** ⚠️ **Corrected 2026-09-15: `promote-image.yml` is NOT a provenance surface** —
      it retags server-side and contains no build step at all (`grep -n 'build-push-action'`
      over it returns nothing). And there are **three** build surfaces, not one:
      `deploy-cloud-run.yml:311`, `deploy-gke-service.yml:300` and `deploy-cluster-keyed.yml:313`,
      all on the same pinned `docker/build-push-action@53b7df9 # v7.3.0`. Applying a policy to
      one of them is drift by construction. None sets `provenance:` or `sbom:`,
      so buildx's default applies and every push adds an
      attestation manifest beside the image. Those are the `unknown/unknown` children
      `cleanup-gar-images` already has to reason about — its own header comment names them, and
      the Traide RCA found all 52 untagged manifests were index children of exactly this shape.

      Surfaced 2026-08-12 while closing `Realm-ID/issuer#2`, which carried `provenance: false`
      on a local build step that no longer exists (build-once moved the build into
      `deploy-cloud-run`). Its stated reason was that Cloud Run consumes a plain image —
      **that claim is unverified here**, and both `issuer` and `api` deploy fine today, so this
      is registry clutter and an unmade decision, not a bug.

      It is genuinely a decision, not a cleanup: provenance is SLSA supply-chain metadata, and
      this repo SHA-pins every third-party action precisely because that class of guarantee
      matters. Turning it off to tidy the registry trades a real thing for a cosmetic one.
      Options: keep the default and document why; set `provenance: false` and say what is lost;
      or expose it as a `workflow_call` input and let the caller choose. Whichever, the
      keep-set/attestation interaction in `cleanup-gar-images` should be re-read alongside it.

## Secret Manager

- [x] **`cleanup-secret-versions.yml` — ✅ ADOPTED 2026-08-24 (AutoMahn + Traide-Co).**
      Zero callers since `v2.3.0`; the first adoption attempt immediately surfaced two latent
      defects in the workflow (project-wide `secrets.list` demanded to validate a name;
      `secrets_list` collapsing multi-secret lists) — fixed, with step tests, see DECISIONS
      2026-08-24. **A workflow with no callers has no runtime signal: CI green meant only that
      the YAML parsed and the plan logic was right.**
      Live survey, same day, of what the sweep would actually find:
      | project | secret | versions |
      |---|---|---|
      | `auto-mahn` | `app-secrets` | 2 ENABLED (v9, v10), 8 already DESTROYED |
      | `traide-in` | `app-secrets` | 3 ENABLED (v3–v5), 2 DISABLED (v1, v2, since 2026-05-24) |
      So with the defaults (`keep_enabled_count: 3`, `min_age_days: 7`) **both projects plan zero
      disables today** — the accumulation the workflow was built for is not present. Its value
      here is (a) prospective: the sweep runs on a schedule so it never accumulates, and
      (b) traide-in's two DISABLED versions, which are past any quarantine and are the only
      destroy candidates in the fleet. Adopt with `dry_run: true` + `enable_destroy: false`
      first, read a plan, and only then consider the destroy flip.
      **DONE, end to end, same day.** IAM: `infra-provisioning#35` merged and APPLIED to both
      projects (3 binds each — `secretVersionManager` + `viewer` ON `app-secrets`, project
      `logging.viewer` → `github-cleaner`); verified live read-only afterwards, not just from
      the run log. Callers: `AutoMahn/project#42` + `Traide-Co/project#92`, both monthly,
      both pinned `@v2.4.1`, both shaped so the SCHEDULE NEVER ACTS.
      **First real runs (`dry_run: true`) confirm the plan predicted from the survey:**
      | project | latest | enabled | disabled | consumers | to disable | to destroy |
      |---|---:|---:|---:|---:|---|---|
      | `auto-mahn` | 10 | 2 | 0 | 6 | — | — |
      | `traide-in` | 5 | 3 | 2 | 2 | — | 2, 1 |
      AutoMahn's empty plan is the CORRECT result, not a misfire. traide-in's v1+v2 are
      eligible and await a human `enable_destroy: true`.
      These runs are also the first live proof of the #66 fixes: a resource-scoped caller
      that never touches project-level `secretmanager.secrets.list` completed `Collect
      target secrets` successfully.

- [x] **A GSM version cleanup workflow.** ✅ **Shipped as `cleanup-secret-versions.yml`**
      (2026-08-16) — quarantine model (`ENABLED`→`DISABLED`→`DESTROYED`), `enable_destroy`
      off by default, 16 fixtures wired into CI as `secret-plan-fixtures`. See
      [docs/cleanup-secret-versions.md](docs/cleanup-secret-versions.md) and DECISIONS.md.
      **⚠️ One design note below was WRONG and is corrected there:** `:latest` does *not*
      resolve at deploy time for the mount style the fleet actually uses. A Cloud Run
      **volume** mount re-fetches from Secret Manager on **every read, at runtime**, so a
      wrong destroy breaks a *running* service rather than waiting for the next deploy.
      The "not `:latest` ≠ not in use" conclusion held; the reason did not, and the real
      behaviour is stricter. Original text kept below as filed.

      Original entry, for reference:

- [ ] **A GSM version cleanup workflow.** Four reusables add Secret Manager versions and
      none ever removes one: `manage-config-secrets`, `rotate-signing-keypair`,
      `rotate-worker-signing-secret`, `sync-bundle-key`. Versions accumulate for the life of
      the secret, every one of them still holding retrievable plaintext, so the exposure grows
      monotonically with rotation frequency — the opposite of what rotating is for. The same
      shape as the GAR sweep before `cleanup-gar-images` existed.

      Design notes, from what the rotators already do:
      - **`disable` before `destroy`, and never destroy the version a service mounts.**
        `rotate-signing-keypair` already disables a superseded version
        (`rotate-signing-keypair.yml:281`), so the primitive and its failure modes are proven
        here; the missing piece is the sweep, and it must resolve every consumer's mounted
        version first. Cloud Run mounts by `:latest` in several services, which resolves at
        *deploy* time — so "not `:latest`" is NOT the same as "not in use". This is the
        keep-set problem, and getting it wrong takes prod down rather than filling a disk.
      - **Retain by count and by age, like the GAR sweep learned to** — keep the N most recent
        ENABLED versions, and never destroy one newer than the rollback window. `DESTROYED` is
        irreversible: there is no undelete, unlike a container image that can be rebuilt.
      - **Dry-run default, and abort if zero consumers resolve** — the same fail-safe as
        `cleanup-gar-images`, for the same reason.
      - Ownership: the sweep is an ops body here; the schedule and the secret names are the
        caller's, as ever.

## Build-once, promote-to-prod

Reusable-side work is **done** (`v1.17.0`): `deploy-cloud-run` gained `build_only`,
`cleanup-gar-images` gained the release-relative sha retention window (keep-only, default on)
plus the first test suite in this repo. See DECISIONS.md 2026-07-27.

- [x] **GAR retention is release-relative.** `cleanup-gar-images` no longer age-deletes the
      `:<sha>` promotion source: per package it keeps sha images newer than the
      `sha_retention_releases`-th most recent release (ordered by time, not semver).
      ✅ **The keep-only claim HOLDS for identical input — root cause of the 105-vs-103
      delta established 2026-08-11** (an earlier note here declared the claim false; that note
      was wrong and is corrected). The `v1.15.0` (103) and `v1.21.1` (105) dry-runs on
      `Realm-ID/project` were 2m27s apart, and both extra digests are **untagged with
      `age_days` exactly 15** against `untagged_max_age_days: 15` (`>=`) — they aged past the
      threshold *between the runs*. The delete loop and live-digest collection are
      byte-identical across the two tags, the keep-set can only grow, and HEAD's delete-set is
      a strict subset of `v1.15.0`'s on all 13 fixtures. See DECISIONS.md; boundary pinned by
      `tests/fixtures/t23-untagged-age-boundary.json`.
      **Still dry-run and diff the plans before repinning a caller** — but read the diff
      properly: untagged digests sitting exactly at the threshold age are wall-clock noise;
      tagged images, live digests, or ages away from the boundary are real. Latent `TypeError`
      on a missing `updateTime` fixed in the same pass.
- [ ] **Pilot `Realm-ID/issuer` end-to-end** (lowest blast radius of the five). In its
      `deploy.yml`: add a `main`-triggered `deploy-cloud-run` job with `build_only: true` →
      `:<sha>`; move the migrate-smoke validation to run against that pushed image; rewrite the
      tag path to call `promote-image` with `source_tag: ${{ github.sha }}`,
      `deploy_target: cloud-run`, `environment: production`, `enforce_forward_only: true` (the
      guard needs `environment` to build its baseline). Run `dry_run: true` first and read the
      plan before one real promote.
      **Also set `source_wait_seconds`** (build p99 + queue; e.g. 900) and raise
      `timeout_minutes` above it — the tag run and the `main` build run are independent, so
      without it a release cut alongside the merge fails on a healthy build. See the
      2026-07-28 race RCA in DECISIONS.md.
- [ ] **Roll to the remaining four**, in this order: `Realm-ID/api`, `Traide-Co/api`,
      `AutoMahn/image-service`, then **`AutoMahn/api` last** — it drives three Cloud Run services
      off one image and has the largest env-var surface.
      **Precondition to confirm per repo before converting:** config is runtime-resolved
      (`APP_ENV=prod` a `--set-env-vars`, not a build arg). That is what makes one image
      legitimately serve two environments. It held on all five at plan time — re-verify, don't
      assume.
- [ ] **Post-pilot proof, on the real repos:** run `cleanup-gar-images` with `dry_run: true`
      against each of the 5 GAR repos, read the new `sha_retention` boundaries, and confirm
      `candidates` **drops** (keep-only ⇒ it can never rise *for the same input* — untagged
      digests sitting exactly at `untagged_max_age_days` can still appear between two runs
      minutes apart; see the 2026-08-11 boundary-crossing entry in DECISIONS.md before reading
      a small rise as a regression). Then assert the prod digest equals
      the `:<sha>` digest — `gcloud artifacts docker images list --include-tags` — since that
      identity is the entire point. Also exercise `promote-image`'s existing preflight on a tag
      whose commit never built, to see it fail loudly.
- [ ] Stage environments are **out of scope** (user's call) — no repo has one today. The
      `main` job stays build-only; where a stage later exists, add the deploy step there.
- [x] `deploy-cloud-run.yml` — Summary step failed an otherwise-successful job whenever there
      was no service URL (`build_only`, and `dry_run` before it). Fixed in `v1.17.1`; the
      always-expanding `${DRY_RUN:+ (dry run)}` was fixed in the same block. See the RCA in
      DECISIONS.md.
- [x] **CI cannot execute a workflow *step*** — **built 2026-07-28** as
      `tests/run_step_tests.py` + the `step-bodies` CI job, driven by the `promote-image`
      race fix (DECISIONS.md). It extracts a named step's `run:` body from the shipped YAML
      and runs it under `bash --noprofile --norc -eo pipefail` against stubbed commands, with
      `date`/`sleep` faked so timing logic is asserted instantly. Covers `promote-image`'s
      "Wait for source image" today; add steps to it as they earn coverage.
- [ ] **Encode the Summary-step rule in the new harness.** Still unwritten: **a
      `{ … } >> $GITHUB_STEP_SUMMARY` group must not end in a bare conditional** — it is the
      script's last statement, so its status becomes the step's. Either a shellcheck-style
      grep in CI, or a `run_step_tests.py` case per Summary step asserting rc=0 with an empty
      env. The grep is cheaper and catches all of them at once.

## Convergence — remaining work

The goal (see `docs/convergence-audit.md`, 2026-07-14) is that platform app repos drop the
external `zopsmart/workflows@main` dependency entirely. Status of the long tail:

- [ ] **Callers not yet migrated:** RevvUp-AI, zop-mannai, and quizzing-pro's other three repos
      (`engine`, `admin-ui`, `ui` — all still on `zopsmart/workflows@main`, GKE, same pattern as
      `api`). Realm-ID has only the two `project` ops callers, now repinned. `tally-extension`
      was never audited and is out of scope until it is.
- [x] **Reusables still to build** — all built 2026-08-24: `deploy-cloudflare-worker`,
      `bootstrap-cf-service` + `bootstrap-cf-dns` (the `bootstrap-cf` item split in two —
      giving one service a hostname and managing a zone's records are different targets;
      see DECISIONS 2026-08-24), and `cloud-run-update`. **No caller is migrated yet**;
      each moves in its own repo's PR after the next release tag. `cloud-run-update` has
      no adoptable caller at all until the Realm-ID hold lifts.
      Superseded note: ~~`run-db-job`~~ —
      **built 2026-07-28** (Cloud Run Job converge + execute/wait), alongside a
      `docker_target` input on `deploy-cloud-run`. Both additive. Driven by the
      `AutoMahn/api` conversion; see DECISIONS.md 2026-07-28, which also records why the
      runner-side prebuild hook that conversion seems to need was **not** added.
- [ ] **quizzing-pro/api #2041** (the migration that removes its last `zopsmart` dependency) has
      been OPEN since 2026-07-14. Note its default branch `development` already carries the
      migrated `main.yaml` @v1.11.0 — confirm whether #2041 landed by another route and is a
      stale leftover before spending review time on it.
- [ ] **Post-migration follow-ups:** WIF onboarding for quizzing-pro (→ `deploy-gke-service`,
      then drop the `promote-image` stored keys); per-service change-skip (`watch_paths` gate).
- [ ] Two caller PRs were left red on **pre-existing** caller code debt, not on the reusables:
      `AutoMahn/api#24` (7 golangci findings) and `Traide-Co/api#17` (3). User declined caller-code
      fixes; they stay red until the code is fixed or `lint_blocking: false` is set.

- [x] `deploy-cloud-run.yml` / `deploy-gke-service.yml` / `promote-image.yml` —
  **stamp the live commit on every roll** (phase 2; done 2026-07-15, v1.9.0). Cloud
  Run label `jgd_commit=<sha>`, GKE annotation `jgd.dev/commit=<sha>`, opt-in GitHub
  Deployment (via `environment`). Prerequisite for the forward-only guard below.
- [x] `.github/workflows/promote-image.yml` — **enforce forward-only (phase 3).**
  Done 2026-07-15 (v1.10.0). Opt-in `enforce_forward_only`: reads the live commit
  from the latest successful GitHub Deployment for `environment`, compares via the
  GitHub compare API ("block iff behind"), fails closed. Also re-keyed promote
  concurrency to per-env to mutually exclude with `rollback-service`.
- [x] **enforce forward-only on the stage build workflows too.** Done 2026-07-15
  (v1.11.0). `deploy-cloud-run` / `deploy-gke-service` gained the same opt-in
  `enforce_forward_only` guard (runs before the build). Kept as a duplicated
  self-contained step rather than a shared composite action — a `./` local action in
  a reusable workflow resolves to the *caller's* repo, not ours, so it would break
  cross-org callers (verified: community discussions #18601 / #25289).
- [ ] `.github/workflows/promote-image.yml` — **(optional) artifact quarantine.**
  Instead of a rollback pin, let a bad digest/tag be marked quarantined so
  `promote-image` refuses to promote *that specific artifact* — targeted protection
  for the incident window without freezing all promotion. See the 2026-07-15
  no-pin decision in DECISIONS.md.

- [ ] `.github/workflows/` — **Create a GSM→k8s wiring/provisioning workflow.**
  `manage-config-secrets.yml` only *manages the values* (writes the ConfigMap and
  writes secrets into the chosen store: k8s Secret / GSM blob / GSM individual).
  It deliberately does **not** wire a GSM secret into pods. A separate reusable
  should provision that delivery path — e.g. install/configure the Secret Manager
  CSI driver + `SecretProviderClass`, or (later) an External Secrets Operator
  `ExternalSecret`/`SecretStore` — so a GSM-backed secret actually reaches the
  workload. `manage-config-secrets.yml` reserves the `eso` backend value as the
  extension point; the wiring workflow is its counterpart.
- [ ] `.github/workflows/manage-config-secrets.yml` — implement the reserved `eso`
  backend (currently errors "not implemented"): emit an `ExternalSecret` CR
  referencing the GSM secret written by the `gsm` backend.
- [x] `docs/*.md` / `README.md` — **example pins swept to `v1.20.0` (2026-08-11).** All 39
  `uses: …@vX.Y.Z` lines across the docs were spread over twelve different tags, the oldest
  `v1.4.0`, so most copy-paste examples silently gave the reader a stale contract. Now uniform.
  **This will rot again** — the drift-report entry below is the durable fix; until it exists,
  sweep as part of each release.
- [ ] `ci-go.yml` / `ci-node.yml` — **`update_badges` is not yet dogfooded; this gates
  the `v1.16.0` tag.** Nothing about `contents: write`, caller permission-capping, or
  the commit-back push is testable locally. Dogfood is **quizzing-pro/api#2045**
  (pins the `ci-go` job to SHA `3d60a0d` — the squash-merge of reusable-workflows#22 on
  `main`, **not** the pre-merge branch commit `200b381` this entry previously named; its deploy/promote
  jobs stay at `@v1.11.0`). The badges job only fires on `push` to the default branch,
  so the proof requires **merging** #2045, not just opening it. Confirm on that merge:
  one `chore(ci): update README badges` commit lands on `development`, coverage matches
  the suite, `nolint_count` reads **57** (down from the frozen 78 — the narrower grep,
  measured against the real tree), **and a second push produces no new commit.** Only
  then tag `v1.16.0` and flip #2045's pin to the tag.
- [x] **caller pin-drift — reframed 2026-08-11.** Built as a weekly scan over a committed
  list of four orgs, then **de-scoped the same day**: this repo is public, so most callers are
  private and none are ours to watch. Shipping an org list in a public repo also asserts an
  ownership relationship the project does not have. The scheduled workflow and `fleet.json`
  are **removed**; `scripts/fleet_drift.py` survives as an operator tool requiring an explicit
  `--orgs`. **The consumer-facing answer is Dependabot** (documented in AGENTS.md + README) —
  it reaches private callers, which nothing we run can. Original entry:  (`scripts/fleet_drift.py` + `.github/workflows/caller-drift.yml`, weekly + dispatch, org list in `fleet.json`). First real run: **24 of 32 caller pins need attention**, incl. nine in `AutoMahn/project` nobody had looked at. Needs `FLEET_READ_TOKEN` (cross-org read) before the schedule is useful. Original entry:  The 2026-07-27 repin sweep
  (see DECISIONS.md) found 18 of the fleet's 27 caller lines stranded on `@v1.4.0`/`@v1.5.0`, six-plus
  releases behind, and only noticed because someone manually read check-run *annotations*
  across every caller. Nothing detects this. Wanted: a scheduled workflow in this repo that
  walks the platform orgs, greps every `.github/workflows/*` for
  `Just-Git-Dev/reusable-workflows/...@<ref>`, and reports (issue or job summary) any caller
  more than one minor behind the latest tag — plus any pinned to a **mutable ref** (the sweep
  found `Realm-ID/project` on `@v1`, i.e. still running the original `b96d0e3` implementation).
  Cheap to build (the sweep was ~30 lines of `gh api`); the value is that fixes we ship actually
  reach the repos that need them. **Derive the org list from an authoritative source** —
  `infra-provisioning/projects/*` + the CF/GitHub target configs — not a hand-typed list: the
  first manual pass silently omitted the entire `Realm-ID` org.
- [ ] **repin `quizzing-pro/api` as part of the `v1.16.0` cut.** Deliberately excluded from
  the 2026-07-27 sweep — its `main.yaml` is concurrently edited by #2045 (badges dogfood,
  `ci-go` pinned to SHA `3d60a0d`) and #2041, and it is a live GKE prod deploy path. Its
  references to 4 reusables (`ci-go`, `deploy-cluster-keyed`, `manage-config-secrets`,
  `promote-image`) are still
  at `@v1.11.0` and still emit the Node-20 `docker/build-push-action` deprecation warning.
- [ ] `ci-node.yml` / `deploy-cloudflare-pages.yml` — **generalise private-registry auth beyond a
  single npm registry.** The `npm_registry_url` / `npm_registry_scope` / `npm_auth_token` trio
  delegates to `actions/setup-node`'s `registry-url`, which writes exactly **one** registry line
  into `$RUNNER_TEMP/.npmrc`. A repo pulling scoped packages from two private registries (e.g.
  GitHub Packages *and* Artifact Registry npm) still has to hand-roll its own `.npmrc`. Deferred
  deliberately — no caller needs it yet, and a list-of-registries input would mean writing and
  owning the `.npmrc` ourselves instead of delegating. Documented as a known limitation in
  `docs/ci-node.md` and `docs/deploy-cloudflare-pages.md`; revisit when a second registry
  actually shows up.
- [x] **`ci-node` / `ci-go`: the badge job forced `contents: write` on every caller — fixed in `v1.21.0`.** The job
  declares `permissions: contents: write` statically (`ci-node.yml:424`), and GitHub validates a
  called workflow's permissions against the caller **at startup**, before job-level `if:` is
  evaluated — so a `contents: read` caller gets `startup_failure` with no logs **even when
  `update_badges` is false**. This is not theoretical: `Traide-Co/webapp` hit it and is frozen at
  `v1.15.0` with a comment explaining why, and the copy-paste example shipped in `v1.20.0` had the
  same defect (patched in `v1.20.1` by granting write on the `ci` job).
  **Fix:** drop the workflow-level `permissions: contents: read` and the badge job's explicit
  block so the job inherits whatever the caller granted; then make the push degrade with a
  `::warning::` when the token is read-only, instead of failing. That un-freezes permission-minimal
  callers *and* is the precondition for defaulting `update_badges` to true — flipping the default
  before this lands would break every caller that has not granted write.
- [x] **`update_badges` defaults to `true`** — shipped in `v1.21.0` (user's call, 2026-08-11).
  Follow-up in `v1.21.1`: a missing coverage report was still a hard error, which broke the
  first real caller. **Rule worth remembering: flipping a default converts every opt-in error
  path into a default one.** Both surviving `::error::` exits in that job needed re-triaging
  against "is this fair to a caller who never asked for the feature?" — the missing-README one
  was caught during design, the missing-coverage one only by running it against a real repo.
  ✅ **Sweep DONE 2026-08-11** — all 133 `::error::` emissions across the 21 reusables
  classified by guard chain. One real finding, now fixed: the badge job's push failure path
  could fail a caller's CI (see DECISIONS.md). No other fatal path is reachable without opting
  in. The `readme_path` hard error described here was **already** warning-and-skip — that half
  of this entry was stale.
  ✅ **Badge insertion DECIDED 2026-08-11** — option (c): `badge_insert`, default `true`.
  Behaviour unchanged for every existing caller; the insertion is now a named boolean a caller
  can decline instead of turning the whole feature off. Update-only-by-default was rejected: it
  makes default-on inert, since no repo would ever gain badges without hand-seeding a badge
  line. See DECISIONS.md.
- [ ] **Tell callers, in their own run, when they are on an old version.** *Unblocked
  2026-08-11* — `WORKFLOW_VERSION` now ships in every reusable's `env:` (see the sweep entry
  below), which was the missing half: a called workflow cannot discover its own ref at runtime
  (`GITHUB_WORKFLOW_REF`/`_SHA` describe the **caller**, and the `github` context has no
  `job_workflow_sha` key — probed 2026-08-11; actionlint's model doesn't know it either, and it
  gates CI). What remains is the notice step itself: a cheap, **never-failing** step that
  compares `WORKFLOW_VERSION` to the latest release and writes a `::notice::` + step-summary
  line when behind. Open questions: which workflows carry it (all, or only the deploy paths —
  it costs an API call per run); whether it needs a token at all (`/releases/latest` is public
  and unauthenticated, but rate-limited by runner IP, so it must degrade silently); and an
  opt-out input for callers who deliberately hold a pin.
- [x] **Automate the doc example pin sweep at release time — BUILT 2026-08-11.**
  `scripts/stamp_version.py <tag>` sweeps doc pins *and* stamps `WORKFLOW_VERSION`;
  `tests/run_stamp_tests.py` covers it; CI's `version-sweep` job asserts internal agreement on
  every PR and agreement **with the tag** on `v*.*.*` pushes. The originally-proposed check
  ("fail when the newest pin is older than the latest release") was rejected — it fails
  unrelated PRs in the window between a release and its sweep. See DECISIONS.md.
- [x] `ci-node.yml` / `deploy-cloudflare-pages.yml` — **optional `node_modules` caching —
  BUILT 2026-08-11.** `cache_node_modules` (default `false`) on both; Pages also gained
  `install_command` because its `build_command` bundled the install and `npm ci` deletes the
  restored tree. Exact-match key (no `restore-keys`), keyed on the resolved Node version;
  install skipped on a hit, with a `::notice::` because lifecycle scripts then don't run.
  **Unverified on a real runner** — no measurement yet of the saving on a large tree; do that
  when `eazyupdates-ui` or another big caller adopts it. Original entry:
- [x] ~~`ci-node.yml` / `deploy-cloudflare-pages.yml` — **optional `node_modules` caching.**~~ Both
  rely on `setup-node`'s cache, which covers only `~/.npm`; npm still unpacks and links the tree
  on every run. `eazyupdates-ui`'s outgoing GKE workflow caches `node_modules` itself, keyed on
  `hashFiles('package-lock.json')` with no `restore-keys` (a prefix fallback would restore a tree
  built from a different lockfile), and its comment puts the tree at **~1.2 GB** — so migrating it
  to the reusables is a measurable build-time regression. Worth an opt-in
  `cache_node_modules` input. Note the key must include the Node version, and it is only sound
  because `npm ci` is deterministic.
- [x] **`deploy-cloudflare-pages` post-deploy smoke check — BUILT 2026-08-11** (`smoke_path`, `smoke_expect`, bounded retry, blocking). Next: migrate `Realm-ID/ui` onto the reusable, which this unblocks. Original entry:  (`smoke_path` + bounded
  retry poll, fail the deploy if the live site doesn't serve it). Not speculative: `Realm-ID/ui`
  hand-rolls exactly this after the **2026-06-29 `/device` outage**, where a stale bundle went
  live with a broken client-routed path and nothing caught it — Pages deploys are
  eventually-consistent, so the poll needs a bounded retry, not a single curl. It is also part of
  why that repo has not migrated to the reusable. **Six consumers**: the five current callers
  (`AutoMahn/{ui,admin-ui,website}`, `Traide-Co/{webapp,website}`) plus `eazyupdates-ui`. Lift the
  logic from `Realm-ID/ui`'s `deploy.yml` rather than reinventing it.
- [x] **Repin the three GAR callers onto `v2.0.0`** (release-relative retention). **DONE — overtaken
      by events 2026-08-20:** all three had already reached `@v2.2.0`, and the fleet-wide repin to
      `@v2.3.1` (AutoMahn/project#31, Realm-ID/project#13, Traide-Co/project#82) supersedes this
      item. `Traide-Co/project#65` was closed, so its pin-comment fix did not need folding in; the
      stale pin comments were rewritten to name no version at all in the repin PRs. Original text:
      `Realm-ID/project`
      is on `@v1.21.1`; **`Traide-Co/project` and `AutoMahn/project` are still on `@v1.15.0`**, which
      predates the retention window entirely, so today they run on `keep_semver_count` + age alone.
      Per repo: dry-run BOTH pins, diff the plans, then repin. Expect a larger first sweep — v1 was
      silently retaining a backlog. `realm-id` takes `grace_period_days: 1` (it is the one doing
      build-once promotion). Fold `Traide-Co/project#65`'s pin-comment fix and incident record into
      the Traide-Co repin PR rather than merging it separately — same file, guaranteed conflict.
- [ ] **`Realm-ID/ui` + `Realm-ID/website` are the unmigrated Cloudflare Pages tail.** `ui` pins
  `cloudflare/wrangler-action@v4` — a **mutable tag**, which is precisely what this repo's SHA-pin
  CI rule exists to prevent, on a workflow holding a Pages deploy token; `website` shells out to
  `npx wrangler`. Both should move to `deploy-cloudflare-pages`, but the smoke-check gap above is
  a real blocker for `ui` — do that first, then migrate.
  ⧖ **`ui` migration OPEN as Realm-ID/ui#3 (2026-08-11)** — pinned `@v1.23.0`; the `guard` job
  (tag reachable from `origin/main`) and the tag→`package.json` stamp stayed caller-side; the
  `/device` smoke check became inputs, still aimed at `app.realmid.dev` rather than the preview
  URL. Node deliberately held at `22` (reusable defaults to 24) — bump separately.
  **Unproven until the first `v*.*.*` tag after merge.** `website` (`npx wrangler`) is untouched
  and still the tail.
- [x] ~~build-once/promote for frontends~~ — **considered and rejected 2026-08-11.** Adding
  `build_only` + cross-run artifact download + a `predeploy_command` seam to
  `deploy-cloudflare-pages` (so one bundle could serve stage and prod, differing only in a
  generated `environment.js`) was scoped for the eazyupdates-ui migration and dropped. A fleet
  check found **all seven** platform frontends are single-environment, tag-triggered, build-and-
  deploy-in-one-job, with config injected at build time from `vars.*` — so it would have added an
  artifact race, retention tuning, a `github_token`, and a **second `eval` seam** to a
  credential-minting workflow that five repos depend on, to serve exactly one caller. Revisit only
  if a second frontend genuinely grows a stage environment.
- [x] **DONE 2026-08-11, re-verified live 2026-09-02.** Branch protection on `main`:
      `enforce_admins: true`, PR required, **0** approving reviews, **10** required status
      contexts. Three traps worth keeping written down:
      - The "require a pull request before merging" toggle **is** the presence of the
        `required_pull_request_reviews` object. Setting it to `null` to drop the review
        requirement silently drops the require-a-PR gate too — set the object with
        `required_approving_review_count: 0` instead.
      - Read `enforce_admins` from `/branches/main/protection/enforce_admins`. The branch
        object reports `"enforce_admins": null`, which looks like "off" and is not.
      - Requiring every `ci.yml` job is safe **only because no job has an `if:`** — a skipped
        job never reports its context and would hang every PR forever.
      Configuration is verified; enforcement is not. `git push --dry-run` does **not** exercise
      server-side pre-receive checks, so a clean dry-run says nothing about whether protection
      would reject the push. Escape hatch: fixing a `main` that CI cannot pass means turning
      `enforce_admins` off first.
- [x] **CLOSED 2026-08-20 (v2.3.1).** `sync-bundle-key.yml` / `rotate-signing-keypair.yml` / `rotate-worker-signing-secret.yml` —
  aligned the `concurrency:` group key on the bundle (`bundle-write-<proj>-<bundle>`, identical in all three;
  `bundle_key` deliberately not in the key). `tests/run_concurrency_tests.py` + a CI job assert the three
  strings stay byte-identical. Residual, unfixable here: GitHub scopes the group to the CALLER's repo, so two
  caller repos writing the same bundle are still not serialised. DECISIONS.md 2026-08-20.
  Original finding: All three do a read-modify-write of the SAME
  `app-secrets` blob but declare three different prefixes (`secrets-rotation-<proj>-<bundle>`,
  `keypair-rotation-<proj>-<bundle>`, `signing-rotation-<proj>-<bundle>-<key>`), so a sync and a
  keypair rotation are NOT serialised against each other: both read v5, both write, the second
  write silently drops the first one's keys. Found 2026-08-17 while mapping the AutoMahn callers;
  no overlap observed in run history (not checked), the exposure is a scheduled quarterly/annual
  rotation landing on a manual sync. Fixing it in the reusables covers every caller at once —
  AutoMahn's caller-level `group: secrets-rotation` only papers over two of the four.
- [ ] `cleanup-secret-versions.yml` — adopt Secret Manager **delayed destruction** and drop the
  audit-log clock. `gcloud secrets update <secret> --version-destroy-ttl=30d` (API field
  `version_destroy_ttl`, min 1d / max 1000d) makes a destroy land as `DISABLED` +
  `scheduledDestroyTime`, cancellable by enabling or disabling before that time. The delay is
  then enforced server-side and cannot be wrong, so the sweep can drop `quarantine_days`,
  `roles/logging.viewer`, and the "disable event not found ⇒ HELD forever" branch — the whole
  reason those exist is that GSM stores no disabled-at timestamp, but `scheduledDestroyTime` IS
  plain metadata. See DECISIONS.md 2026-08-17. **Verify first, none of it confirmed:**
  (a) is a version awaiting `scheduledDestroyTime` still billed at $0.06/mo? If so the cost
  saving is deferred by the TTL, not avoided — which undercuts the motivation.
  (b) which role grants `secretmanager.secrets.update`? Setting the TTL mutates the *secret*,
  not a version, so `roles/secretmanager.secretVersionManager` may not cover it — and secret
  *configuration* arguably belongs with `manage-config-secrets`, which creates them, not with a
  sweep or a rotation.
  (c) a version awaiting destruction is `DISABLED`, so the sweep's current DISABLED-selection
  would re-enter it as a candidate next run. No-op, error, or does it reset the clock?

## Convergence — operating facts that live nowhere else in this repo

Moved out of session memory 2026-09-02 (see the routing rule in `~/.claude/CLAUDE.md`). These
are the few things about running the convergence that the repo did not already record:

- **The current tag is looked up, not remembered** — `gh release list`. Consumers pin an exact
  `vX.Y.Z`; `@v1` is a frozen legacy alias and `@main` is never acceptable.
- **Editing any `.github/workflows/*` file through the API needs the token's `workflow` OAuth
  scope.** `repo` alone 404s — the failure looks like a missing file, not a permission error.
  Fix with `gh auth refresh -s workflow`.
- **`gh pr merge` may be refused by the Claude Code permission classifier**, not by GitHub —
  hit 2026-08-12 for both batched and single-PR forms. If it stays blocked, ask the user to run
  it as `! gh pr merge …`.
- **Do not build consumer monitoring.** A scheduled caller-drift scan was built and de-scoped
  the same day (2026-08-11): this repo is public, most callers are private, and shipping an
  org-wide scanner from a public repo is the wrong trade.
- **`zopsmart/eazyupdates-ui` → Cloudflare Pages is PARKED (2026-08-11)**, at the user's
  request, to do platform fixes first. Nothing live changed; the GKE path still deploys. The
  decided-and-not-to-be-relitigated shape: serve `app.eazyupdates.com` **at the root** (drop the
  `/user` prefix); **no DNS zone move** (a subdomain custom domain works from Google Cloud DNS
  via CNAME — only an apex needs the zone on Cloudflare, and explicit records are mandatory
  because the zone wildcards answer every name); **two Pages projects**, one per environment;
  config baked at build from the committed `configs/.{stage,prod}.env`; the
  `eazyupdates.com/user` 301 belongs on the **ingress**, not in `eazyupdates-web`'s nginx.conf.
  Build-once/promote was rejected; nginx health endpoints dropped (no signal on a CDN). Work is
  preserved as a git bundle at `devops/.eazyupdates-pages-wip.bundle` (branch
  `feat/cloudflare-pages-deploy`, tip `f0728e0`) and closed PR `zopsmart/eazyupdates-ui#4440`.
  The bundle predates the root-mount decision, so it still nests under `user/`.
  Still open: the stage hostname; whether to adopt `ci-node`'s badges; Android App Links (the
  apex `assetlinks.json` returns HTML — already broken); the GKE decommission tail.
