# TODO — reusable-workflows

## Index
34 open across 13 live sections. 46 closed items archived.

Status is the section's own, not per item; keep it current by hand when a
section opens or closes. Closed sections live in
[TODO-ARCHIVE.md](TODO-ARCHIVE.md) — same log, split by state only.

- **ACTIVE** — [App-token mint — `app-id` input is deprecated upstream (opened 2026-10-28)](#app-token-mint--app-id-input-is-deprecated-upstream-opened-2026-10-28) — 1 open
- **ACTIVE** — [Owner rulings to build (opened 2026-10-21)](#owner-rulings-to-build-opened-2026-10-21) — 3 open
- **ACTIVE** — [zizmor findings ignored at adoption (opened 2026-10-21)](#zizmor-findings-ignored-at-adoption-opened-2026-10-21) — 2 open
- **ACTIVE** — [Release flow — `spec-compat` has no way to acknowledge a deliberate removal (opened 2026-10-15)](#release-flow--spec-compat-has-no-way-to-acknowledge-a-deliberate-removal-opened-2026-10-15) — 1 open
- **ACTIVE** — [Release flow — app-id from the environment (opened 2026-10-13)](#release-flow--app-id-from-the-environment-opened-2026-10-13) — 2 open
- **ACTIVE** — [Pre-commit gates that check the wrong thing (opened 2026-09-27)](#pre-commit-gates-that-check-the-wrong-thing-opened-2026-09-27) — 3 open
- **ACTIVE** — [Third-party images vanish from public registries — MinIO (opened 2026-09-24)](#third-party-images-vanish-from-public-registries--minio-opened-2026-09-24) — 2 open
- **ACTIVE** — [Service alerts — rollout and deferred slice (opened 2026-09-23)](#service-alerts--rollout-and-deferred-slice-opened-2026-09-23) — 2 open
- **ACTIVE** — [Release hygiene — the `WORKFLOW_VERSION` stamp (regression found 2026-09-06)](#release-hygiene--the-workflow_version-stamp-regression-found-2026-09-06) — 4 open
- **ACTIVE** — [Build attestations](#build-attestations) — 1 open
- **ACTIVE** — [Build-once, promote-to-prod](#build-once-promote-to-prod) — 5 open
- **ACTIVE** — [Convergence — remaining work](#convergence--remaining-work) — 6 open
- **REFERENCE** — [Convergence — operating facts that live nowhere else in this repo](#convergence--operating-facts-that-live-nowhere-else-in-this-repo) — 2 open

## App-token mint — `app-id` input is deprecated upstream (opened 2026-10-28)

- [ ] move every `actions/create-github-app-token` step from `app-id:` to `client-id:`
  The pinned v3.3.0 `action.yml` marks `app-id` with `deprecationMessage: "Use 'client-id'
  instead."` — a warning today, not a failure. 23 files use it (`release-publish.yml`,
  `release-drafts.yml`, `repos-*.yml`, `distribute-env-secrets.yml`, …). Our own `app-id`/`app_id`
  workflow inputs carry the numeric App ID, and `client-id` wants the App's Client ID, a
  different value — so this changes the input contract: plan it for the next major, with a
  deprecation window. No step here passes `permission-actions-variables` (an input that action
  does not define; a consumer found it ignored as "Unexpected input"), checked 2026-10-28.

## Owner rulings to build (opened 2026-10-21)

- [ ] remove rotate-worker-signing-secret in v6 (deprecated v5.2.0, replaced by rotate-external-secret)
  `actions/rotate-worker-signing-secret` + `.github/workflows/rotate-worker-signing-secret.yml` +
  both docs pages and README rows.
- [ ] v5.1.0 live proof (DECISIONS 2026-10-23, public Cloud Run via F7): no consumer calls
  `repos-deploy-scope` with `public: true` yet. On the first adopter's run, record the run id,
  check the Plan step printed `public services in the register: [...]`, and read the invoker back
  (`allUsers` `roles/run.invoker` on that service only).


- [ ] `catalog.json` + `scripts/workflow_preflight.py` (fleet) — ship the list of workflows that
  receive the App private key (workflow, secret input name, required caller environment) with rw,
  and have workflow-preflight check every caller against it, so projects stop hand-maintaining
  their own key-recipient guards (owner, 2026-10-21; a consumer's guard needed a hand exception
  to adopt `repos-environments`).

## zizmor findings ignored at adoption (opened 2026-10-21)

zizmor v1.31.1 was added to the gate with per-rule, per-file ignores in `zizmor.yml` (reasons in
DECISIONS.md). Each ignore is debt to pay down, not policy.

- [ ] `.github/workflows/*.yml` — template-injection: 57 sites across 11 files; move each `${{ }}`
      used inside `run:` into an `env:` entry and reference `"$VAR"`, exercising each deploy body
      before dropping its ignore.
- [ ] `zizmor.yml` — re-check the other ignores (github-app 4, unpinned-images 6, unsound-ternary 2,
      github-env 1, cache-poisoning 2) and remove each one that a fix can retire.

## Release flow — `spec-compat` has no way to acknowledge a deliberate removal (opened 2026-10-15)

Reported by consumer C's session for the owner's triage. `release-flow spec-compat BASELINE
CANDIDATE` fails on ANY removal from a service's OpenAPI spec: an operation, a request
parameter, or a body property. The CLI's only option is `--label`
(`actions/release-flow/releaseflow/spec_compat.py`, `main()`; checked 2026-10-15). Cost to
consumer C: two patch versions were burned before publish. The spec had dropped a login request
field the server already ignored, and a role value the server already refuses. The only way
through was to restore both in the spec, marked deprecated/refused, and cut the next patch. That
delayed a security fix by about a day.

Cause (checked 2026-10-15 in consumer C's caller `release.yml`): the root release runs
`spec-compat` twice per provider. Check A uses the live consumer's PINNED copy of the provider
spec as the baseline. Check B uses the LIVE PROVIDER's own spec as the baseline. Check B can
never pass a removal, even after a full deprecation cycle, because the live provider always
still lists the thing being removed.

Rulings (owner, 2026-10-15):
- Each service is responsible for its own release. The root repo only coordinates the overall
  release, so the root release checks contracts BETWEEN services and nothing else.
- Check A stays in the root release. Check B ("does the provider drop anything its own last
  release had") is the service's own release policy and moves into that service's own CI.
- Q1, REVERSED the same day (owner, confirmed in the devops session after the consumer relayed a
  fuller ruling): a removal that breaks a live consumer is a breaking change. It ships in ONE
  release when the owner labels the root release PR `breaking-approved` and the PR body lists
  every break exactly; without the label it takes two releases (consumer first, then provider).
  Built on branch `feat/breaking-approved-waiver`; rules R1-R6 in `docs/release-flow.md`
  §Contract checks; DECISIONS 2026-10-15 "a `breaking-approved` label waives an exact list".

- [ ] `v3.5.0` rehearsal runs, verified read-only: on a real breaking PR the check goes red without
  the label, green with it, red with one line edited. They wait on consumer C's first tagged
  provider release that removes something.

## Release flow — app-id from the environment (opened 2026-10-13)

A consumer's first `release-flow` rehearsal failed at the mint because `RELEASE_APP_ID` existed
only as a `release`-environment variable. `inputs.app-id` is evaluated in the caller job, which
has no environment, so the input arrived empty. The fix shipped as a doc correction
(`docs/release-flow.md` §Inputs: define a repo/org variable). The consumer chose that route, so
no release was needed.

- [ ] `.github/workflows/release-{plan,drafts,publish}.yml` — optional: make `app-id` not
  required and fall back to `vars.RELEASE_APP_ID` inside the environment-scoped mint jobs, so the
  id can sit beside `RELEASE_APP_KEY` on the environment. This is an additive input-contract
  change, so it means a minor release and a new `RELEASE_FLOW_TREE`, and every caller re-pins.
  Only worth doing when a second consumer hits the same thing.
- [ ] `docs/release-flow.md` §Contract checks/Smoke (L46) — say which ref the smoke SPECS come
  from. "Against the resolved refs and images" is silent on it, and a consumer whose e2e specs
  track its umbrella `main` failed an api-only rehearsal on 2026-10-13: the UI resolved to its
  LIVE tag, while `main`'s specs already tested unreleased UI screens (23 failures, 0 writes).
  State the rule: the specs must match the refs under test, and name the caller-side options
  (specs gated by the minimum UI version they need, with the skip count printed; or specs taken
  at the commit matching the resolved UI ref). Doc-only; no input-contract change. Update
  2026-10-14: that consumer chose the minimum-UI-version option. No rw code change is needed,
  because a caller already passes `fromJSON(needs.plan.outputs.resolved).<ui>.ref` into its own
  smoke workflow, as the caller example does for `backend_ref`. The doc should show that wiring
  for the UI ref.

## Pre-commit gates that check the wrong thing (opened 2026-09-27)

Filed for fleet triage with the owner's approval. **Not started.** Every item below was
**reported by one consumer project and not re-checked here**. Each project fixes its own hooks;
this section is only about the classes, which any repo with local gates can hit.

- [ ] **A gate that reads a neighbouring working tree instead of what is being committed.** An api
      pre-commit coverage check read the live sibling `../ui` tree, not committed ui content. So a
      parallel agent's uncommitted ui edits can fail an api commit, or let a wrong one pass. Fleet
      question: do other repos' gates read sibling clones? The fix shape is to read the committed
      tree (`git show <ref>:<path>`) or refuse to run on a dirty one.
- [ ] **The pre-commit tier doesn't include the tier that catches cross-layer breaks.** An api
      commit broke 6 integration tests and passed its commit hook, because the hook skips the
      integration suite on some paths. Fleet question: which tier must a commit gate include, and
      what catches the rest before push?
- [ ] **Flaky or false-positive guards.** Each one teaches agents to retry or work around a gate.
      (a) A GoFr lint rule flags `RETURNING id` on valid code. (b) A ui visual check's
      `.run-started-at` marker races between concurrent runs. (c) A route-registration edit hook
      gives false positives. (d) An api pre-commit once exited rc=1 after printing "checks
      passed", and an identical retry succeeded (unexplained). (a) and (c) may be shared
      developer-tooling guards rather than the project's own; check before assigning an owner.

## Third-party images vanish from public registries — MinIO (opened 2026-09-24)

Handed over from the consumer A session with the owner's approval. **Filed for fleet triage, not
started.** Each project fixes its own repos; this section is only about the fleet-wide class.

**Failure class:** a third-party image disappears from its public registry, and every consumer
pinned to it breaks at the same moment. Local stacks keep working from the image cache, which
**hides** the breakage on the laptop. Only a clean CI runner or a deploy hits it.

**Verified here, 2026-09-24** (`docker manifest inspect`, exit code per ref):
`quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` → 1, `quay.io/minio/mc:latest` → 1,
`minio/minio:latest` (Docker Hub) → 1. Positive control `quay.io/prometheus/prometheus:latest` → 0.
**Reported by consumer A, not re-checked here:** the quay repo API answers 401; consumer A's api deploy for
v0.58.0 failed at its MinIO smoke step, and its CI integration jobs fail at the pull. Consumer A's
ruling was Chainguard (`cgr.dev/chainguard/minio`, `…/minio-client`) pinned by digest. Those
images are distroless (no shell, no curl), so `sh -c` init scripts and curl healthchecks need
rework. Digests are in `<consumer-repo>/.scratch/minio-digests.txt`, which is scratch and not durable.
This is the second MinIO registry break: consumer A already moved from Docker Hub to quay earlier
(`<consumer-repo>/DECISIONS.md`, "minio/mc").

- [ ] **Mirror pinned third-party images into our own registry (GHCR or GAR).** Consumers pull
      from the mirror, so an upstream withdrawal becomes a sync failure rather than an outage.
      Owner to decide on the registry and which images are in scope.
- [ ] **Scheduled probe: every pinned image in the fleet still resolves.** A reusable workflow
      that greps compose/Dockerfile/workflow refs and runs `docker manifest inspect` on each,
      with a positive-control ref, so "couldn't check" never reads as "all fine". Same
      three-outcome shape as `verify-metrics-arrival`. Concrete check per repo today:
      `/usr/bin/grep -rn "minio/" --include='*.yml' --include='*.yaml' .`, then inspect each hit.

## Service alerts — rollout and deferred slice (opened 2026-09-23)

Plan: `plans/service-alerts.md`. Why: DECISIONS 2026-09-23.

- [ ] **v2.11 slice:** `prune` (owner-scoped), `probe.health_body` uptime check (opt-in, since
  it keeps instances warm), and the `gofr-http-client` / `gofr-pubsub` / `gofr-cron` packs once
  their metrics exist somewhere to verify against. Also `absence`, raw `promql:` (GMP-only),
  the drift WARN for hand-written policies, and `render_dynatrace`.
- [ ] `.github/workflows/service-alerts.yml` — the data check fails a rule whose service had no
  traffic for a whole day only when EVERY service in it is empty. A per-service gap is only a
  warning. Revisit if quiet services turn out to hide real breakage.

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
      real (non-placeholder) pin is silently exempt from the sweep. (Framing owed to consumer B's
      session, 2026-09-06; false live-instance claim corrected 2026-09-15.)
- [ ] **Audit the other gates for the same two shapes** — comparands that are all derived, and
      scopes that are assumed rather than computed. Start with `validate-alerts`, which already
      had a vacuous-check finding on 2026-09-01 for an unrelated reason; two independent vacuity
      findings in one layer says something about how those gates are written.

### Consumer pin inventory (for the separate, unstarted sweep — NOT the v2.6.2 bump)

Regenerate this from this repo's own tool rather than trusting the numbers below to still be
current: `python3 scripts/fleet_drift.py --orgs <consumer-C-org>,<consumer-A-org>,consumer B`.

**Verified 2026-09-15** (after six cleanup-caller pins moved to `v2.7.0` that day across
<consumer-C-org>/project, <consumer-A-org>/project, <consumer-B-org>/project — PRs #17/#149/#45, all merged): **57
caller lines fleet-wide — 37 STALE, 20 OK, 0 MUTABLE**, spread `v2.3.1` → `v2.5.0`. Zero mutable
pins — nothing is on `@main` or the `v1` alias, so the supply-chain risk that motivated this
section is not currently live anywhere. Deepest stragglers are on the deploy path:
`<consumer-C-org>/gateway` and `<consumer-C-org>/core` `deploy.yml` pin `deploy-cloud-run` and `promote-image` at
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
      the consumer A RCA found all 52 untagged manifests were index children of exactly this shape.

      Surfaced 2026-08-12 while closing `<consumer-C-org>/core#2`, which carried `provenance: false`
      on a local build step that no longer exists (build-once moved the build into
      `deploy-cloud-run`). Its stated reason was that Cloud Run consumes a plain image —
      **that claim is unverified here**, and both the core service and the gateway deploy fine today, so this
      is registry clutter and an unmade decision, not a bug.

      It is genuinely a decision, not a cleanup: provenance is SLSA supply-chain metadata, and
      this repo SHA-pins every third-party action precisely because that class of guarantee
      matters. Turning it off to tidy the registry trades a real thing for a cosmetic one.
      Options: keep the default and document why; set `provenance: false` and say what is lost;
      or expose it as a `workflow_call` input and let the caller choose. Whichever, the
      keep-set/attestation interaction in `cleanup-gar-images` should be re-read alongside it.

## Build-once, promote-to-prod

Reusable-side work is **done** (`v1.17.0`): `deploy-cloud-run` gained `build_only`,
`cleanup-gar-images` gained the release-relative sha retention window (keep-only, default on)
plus the first test suite in this repo. See DECISIONS.md 2026-07-27.

- [ ] **Pilot `<consumer-C-org>/core` end-to-end** (lowest blast radius of the five). In its
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
- [ ] **Roll to the remaining four**, in this order: `<consumer-C-org>/gateway`, `<consumer-A-org>/api`,
      `<consumer-B-org>/image-service`, then **`<consumer-B-org>/api` last** — it drives three Cloud Run services
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
- [ ] **Encode the Summary-step rule in the new harness.** Still unwritten: **a
      `{ … } >> $GITHUB_STEP_SUMMARY` group must not end in a bare conditional** — it is the
      script's last statement, so its status becomes the step's. Either a shellcheck-style
      grep in CI, or a `run_step_tests.py` case per Summary step asserting rc=0 with an empty
      env. The grep is cheaper and catches all of them at once.

## Convergence — remaining work

The goal (see `docs/convergence-audit.md`, 2026-07-14) is that platform app repos drop the
external legacy workflow library (`@main`) dependency entirely. Status of the long tail:


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
- [ ] `ci-node.yml` / `deploy-cloudflare-pages.yml` — **generalise private-registry auth beyond a
  single npm registry.** The `npm_registry_url` / `npm_registry_scope` / `npm_auth_token` trio
  delegates to `actions/setup-node`'s `registry-url`, which writes exactly **one** registry line
  into `$RUNNER_TEMP/.npmrc`. A repo pulling scoped packages from two private registries (e.g.
  GitHub Packages *and* Artifact Registry npm) still has to hand-roll its own `.npmrc`. Deferred
  deliberately — no caller needs it yet, and a list-of-registries input would mean writing and
  owning the `.npmrc` ourselves instead of delegating. Documented as a known limitation in
  `docs/ci-node.md` and `docs/deploy-cloudflare-pages.md`; revisit when a second registry
  actually shows up.
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
- [ ] `.github/workflows/manage-config-secrets.yml` — refuse a `gsm` create of a `*-env` secret (ruling 24 says F8 owns it; only the doc states it today)
- [ ] `.github/workflows/repos-secrets.yml` — IAM conditions: the fetch step and `live_lines` (`scripts/repos_secrets_plan.py`) drop `condition` and gcloud add/remove run without `--condition`, so a conditional `<d>-run` line would read in-sync in F8 while the engine's secret_audit flags it forever; F8 now refuses a conditional `<d>-env` policy (error, no write), the redesign (carry condition into state, treat conditional lines as extra, `--condition=None` on add) is open
