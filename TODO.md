# TODO — reusable-workflows

## Fallout from immutable-tag enforcement (opened 2026-08-12, v2.1.1)

- [x] **`retire-gar-packages` has no immutability handling and will fail on a locked repo.**
      Done 2026-08-13 — detect → pre-flight → unlock → act → `always()` restore, mirroring
      `cleanup-gar-images` but with no policy input (a retirement preserves the repo's
      protection, it does not decide it) and no degraded mode (a package delete is
      all-or-nothing, so a locked repo with no update permission fails BEFORE anything is
      deleted). Header IAM corrected to `roles/artifactregistry.admin`. 17 step-body tests.
      See DECISIONS.md 2026-08-13.

- [ ] **`retire-gar-packages` has no `docs/` page and no README catalog row** — every other
      workflow has both (`docs/<workflow>.md`, a README table row). Noticed 2026-08-13 while
      adding immutability handling; the new IAM requirement and the unlock/re-lock behaviour
      are documented only in the workflow's own header comment.

- [ ] **`keep_tags` defaults to `latest,buildcache` — both are MOVING tags, which the default
      `immutable_tags_policy: enforce` makes impossible to push.** The default keep-set
      therefore advertises a workflow the default policy forbids. Nothing is broken (keeping a
      tag that can no longer move is harmless), but the two defaults tell a new caller opposite
      stories. Decide whether `keep_tags` should default to empty, or whether the docs should
      simply say these entries are for `preserve`-mode repos.

- [ ] **Stale `:latest` tags are now frozen in both backend repos.** `Realm-ID/api`,
      `Traide-Co/api` and `Realm-ID/issuer` stopped pushing `:latest` (2026-08-12), but the
      last-pushed tag is still there, pinning its digest alive and shielded by `keep_tags`.
      Removing it now needs an unlock → `gcloud artifacts docker tags delete` → relock. Not
      urgent, not a one-way door — just permanent until someone does it.

- [ ] **13 of 15 fleet call sites are still pinned `@v2.0.0`** (only the two
      `cleanup-gar-images` callers moved to `@v2.1.1`). v2.1.x changed exactly one workflow's
      contract, so nothing is stale in behaviour — but `fleet_drift.py` will report them a
      minor behind until a fleet-wide repin sweep.

## Build attestations

- [ ] **Decide a `provenance` policy for the build reusables — right now it is inherited, not
      chosen.** Neither `deploy-cloud-run.yml` nor `promote-image.yml` sets `provenance:` or
      `sbom:` anywhere (verified by grep), so buildx's default applies and every push adds an
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
- [ ] **Reusables still to build**, each blocking specific left-inline caller workflows:
      `bootstrap-cf`, `deploy-cloudflare-worker`, `cloud-run-update`. ~~`run-db-job`~~ —
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
- [ ] ~~`ci-node.yml` / `deploy-cloudflare-pages.yml` — **optional `node_modules` caching.**~~ Both
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
- [ ] **Repin the three GAR callers onto `v2.0.0`** (release-relative retention). `Realm-ID/project`
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
- [ ] ~~build-once/promote for frontends~~ — **considered and rejected 2026-08-11.** Adding
  `build_only` + cross-run artifact download + a `predeploy_command` seam to
  `deploy-cloudflare-pages` (so one bundle could serve stage and prod, differing only in a
  generated `environment.js`) was scoped for the eazyupdates-ui migration and dropped. A fleet
  check found **all seven** platform frontends are single-environment, tag-triggered, build-and-
  deploy-in-one-job, with config injected at build time from `vars.*` — so it would have added an
  artifact race, retention tuning, a `github_token`, and a **second `eval` seam** to a
  credential-minting workflow that five repos depend on, to serve exactly one caller. Revisit only
  if a second frontend genuinely grows a stage environment.
- [ ] branch protection on `main` — set `enforce_admins: true` so admin direct-pushes cannot bypass the required `actionlint + shellcheck` / SHA-pin checks (they already gate PR merges, but a direct push landed a red `main`; see DECISIONS.md 2026-07-24 SC2020 entry)
