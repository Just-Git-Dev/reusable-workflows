# TODO archive — reusable-workflows

Fully-closed sections moved out of `TODO.md` on 2026-09-13. Same log, split by
state only — both files are greppable. Nothing here is open work. Since 2026-10-29
closed items from live sections are archived too, under a dated heading at the end.

## Index

- [`validate-alerts` executes MQL only — ✅ DONE 2026-09-01 (opened and closed same day)](#validate-alerts-executes-mql-only---done-2026-09-01-opened-and-closed-same-day) — 2 closed
- [Fallout from immutable-tag enforcement (opened 2026-08-12, v2.1.1)](#fallout-from-immutable-tag-enforcement-opened-2026-08-12-v211) — 5 closed
- [`DECISIONS.md` index anchors (found 2026-09-13)](#decisionsmd-index-anchors-found-2026-09-13) — 2 closed
- [Service env settings typed twice — local compose vs deploy workflow (opened 2026-10-04)](#service-env-settings-typed-twice--local-compose-vs-deploy-workflow-opened-2026-10-04) — 2 closed
- [Post-deploy probe — prove the observability pipeline actually DELIVERS (opened 2026-09-18)](#post-deploy-probe--prove-the-observability-pipeline-actually-delivers-opened-2026-09-18) — 1 closed
- [Two items rehomed from the inflight tracker (opened 2026-09-08)](#two-items-rehomed-from-the-inflight-tracker-opened-2026-09-08) — 1 closed
- [Secret Manager](#secret-manager) — 4 closed
- [Archived 2026-10-29 (closed items from live sections)](#archived-2026-10-29-closed-items-from-live-sections) — 30 closed

## `validate-alerts` executes MQL only — ✅ DONE 2026-09-01 (opened and closed same day)

- [x] **Add a PromQL execution layer to `validate-alerts.yml`.** Layer 2 executes queries only
      for `conditionMonitoringQueryLanguage` (the `kind == "conditionMonitoringQueryLanguage"`
      branch at line 220). `conditionPrometheusQueryLanguage` is in the accepted-kinds list
      (line 141), passes the offline structural lint, and is then **never run against the API**
      — so a PromQL policy gets a green tick from a check that did not check it. Add the
      execution step plus a `promql_checked` output mirroring `mql_checked` (lines 70/99/339)
      and its summary line (359).

      **Why it matters now:** Managed-Prometheus/OTel-ingested metrics land as
      `prometheus.googleapis.com/<name>/<kind>` and are naturally queried in PromQL, so the
      first application-level alert policies in the fleet will all take this path. Merging one
      before the gate exists ships a query nobody has ever executed.

      Driven by `infra-provisioning/TODO.md` → *GoFr metrics → Google Cloud* (parked
      2026-09-01 on gofr-dev/gofr#4112). Not blocked by it — this gate is independently
      correct and should land **before** the first `prometheus.googleapis.com/*` policy.

      This is THE PATTERN: a clean report over a surface that was never read.

      **Shipped 2026-09-01.** PromQL queries are collected by the lint and POSTed to
      `v1/projects/<p>/location/global/prometheus/api/v1/query`; `promql_checked` output added
      alongside `mql_checked`; `promql_found` in the summary. No new inputs and no new IAM —
      `monitoring.timeSeries.list` covers both read paths. A `2xx` carrying
      `{"status":"error"}` fails, and `401`/`403` exits without writing a count. See
      DECISIONS.md 2026-09-01.

- [x] **`validate-alerts` had no tests at all before this** because every step wrote to a
      hardcoded `/tmp` path that `tests/run_step_tests.py` cannot isolate. All three steps now
      resolve through `${RUNNER_TEMP:-/tmp}` and 21 step-body tests cover the lint and the
      PromQL layer. The **MQL execution layer is still untested** — the seam now exists, so
      mirroring the PromQL tests onto it is mechanical. Worth doing: it is the layer the whole
      workflow was built for.

      **Done 2026-09-01** — and it was not mechanical: the mirror found two live bugs in the
      MQL layer. A missing query list reported `All 0 MQL query/queries validated` and exited
      0 (`done < missing` kills the loop, not the script), and the `| condition` strip used
      `\b`, a GNU extension that silently no-ops under any other sed. Both fixed, RCA in
      DECISIONS.md 2026-09-01. Both execution layers now hold the same contract under test.

## Fallout from immutable-tag enforcement (opened 2026-08-12, v2.1.1)

- [x] **`retire-gar-packages` has no immutability handling and will fail on a locked repo.**
      Done 2026-08-13 — detect → pre-flight → unlock → act → `always()` restore, mirroring
      `cleanup-gar-images` but with no policy input (a retirement preserves the repo's
      protection, it does not decide it) and no degraded mode (a package delete is
      all-or-nothing, so a locked repo with no update permission fails BEFORE anything is
      deleted). Header IAM corrected to `roles/artifactregistry.admin`. 17 step-body tests.
      See DECISIONS.md 2026-08-13.

- [x] **`retire-gar-packages` has no `docs/` page and no README catalog row.** Done
      2026-08-13 — `docs/retire-gar-packages.md` + README row under "Backups, alerts &
      housekeeping". Covers the live-reference safety rule, the immutability sequence and why
      it has no policy input and no degraded mode, and the `artifactregistry.admin`-not-
      repoAdmin requirement.

- [x] ~~**`keep_tags` defaults to `latest,buildcache` — both are MOVING tags**~~ — **Done
      2026-08-21 (v2.4.0).** Half of this was already stale: the `latest` half was answered by
      the 2026-08-13 `cleanup_latest_tag` work (`keep_tags` protects the DIGEST during the
      sweep, `cleanup_latest_tag` removes the stranded POINTER after it — different objects,
      so no conflict). Only `buildcache` was open, and the fleet decided it: **zero registry
      build caches exist** — all 19 active repos scanned, every cache is `type=gha`, no
      `cache-to: type=registry` anywhere — while 2 of the 3 `cleanup-gar-images` callers run
      `enforce` and none overrides `keep_tags`. Dropped `buildcache` from the default, added a
      run-time warning when a caller opts back into it under `enforce`, and rewrote the docs
      section to state the `preserve`/`unlock` assumption it always relied on. See
      DECISIONS.md 2026-08-21.

- [x] ~~**`SERVICE_ACCOUNT` is referenced but never set in `cleanup-gar-images.yml`.**~~ —
      **Done 2026-08-21 (v2.4.0).** `SERVICE_ACCOUNT: ${{ inputs.service_account }}` added to
      the `Verify permission to toggle immutability` step's `env:`, so both immutability
      warnings now name the identity that needs the role instead of printing the generic
      fallback. Rode along with the `keep_tags` change — same file, same feature area.

- [x] **13 of 15 fleet call sites are still pinned `@v2.0.0`.** Done 2026-08-13 — all 15
      repinned to `@v2.1.2` across 6 repos (<consumer-C-org>/{core, web, project},
      <consumer-A-org>/{project, website, webapp}), all merged. `fleet_drift.py` now reports
      15/15 at latest, zero stale, zero mutable. See DECISIONS.md 2026-08-13.

## `DECISIONS.md` index anchors (found 2026-09-13)

- [x] **FIXED 2026-09-13 — all 17 rewritten.** Root cause below was confirmed: the anchor
      omitted one of the two spaces GitHub leaves behind when it strips the `—`. Regenerated
      every index anchor from its own heading (link text rendered first, since a heading
      ending `— [ADR-00X](url)` contributes `adr-00x` to the anchor). All 58 links in
      `DECISIONS.md` now resolve; `.scratch/todo-cleanup/check_links.py` is the check.
      Original entry:
- [x] **17 of the 58 `DECISIONS.md` index links resolve nowhere.** The entries exist — e.g.
      `2026-08-11 — Private npm registry auth on \`ci-node\`…` is at `DECISIONS.md:2163` — but
      the index anchor collapses the `—` after the date to a single hyphen, while GitHub's
      anchor algorithm removes the em dash and keeps **both** surrounding spaces, yielding `--`.
      Some index lines already use `--` (the 2026-09-07 block), so the convention drifted rather
      than being wrong throughout. Found while restructuring `TODO.md`; not fixed inline per
      the scope rule. Checker: `.scratch/todo-cleanup/check_links.py`.

## Service env settings typed twice — local compose vs deploy workflow (opened 2026-10-04)

Filed for fleet triage with the owner's approval. Seen in two consumer services so far.

**Failure class:** a service's non-secret env settings are hand-typed twice — in the local
docker-compose `environment:` block and in the deploy workflow's `--set-env-vars` string. Nothing
keeps them in step, and drift fails silently: the app just behaves differently locally vs prod.
Observed: CORS keys (`ACCESS_CONTROL_MAX_AGE`, `ACCESS_CONTROL_ALLOW_CREDENTIALS`) set only in
prod, so local Chrome re-sent the preflight every ~5 s; mis-named DB pool keys. In one service the
deploy step typed 27 keys, 12 of them absent from the local config.

**GoFr facts that shape the fix** (`pkg/gofr/config/godotenv.go`, identical v1.59 → v1.61): GoFr
reads the fixed folder `./configs` — `.env` first, then overlays `.<APP_ENV>.env` (or `.local.env`
when `APP_ENV` is unset); process env beats both. A Cloud Run secret volume mounted at
`/app/configs/.env` replaces the whole `/app/configs` directory, hiding anything baked there.

- [x] **Pilot the approved single-source layout on one service.** Approved 2026-10-04: a committed
      `configs/.env` holding only shared, non-secret values is **baked into the image**; the deploy
      workflow keeps passing only prod-specific values (no deploy-time builder); the secrets bundle
      moves from `/app/configs/.env` to `/secrets/app.env`, loaded with `godotenv.Load` before
      `gofr.New()` so it lands as process env; a pre-push drift check fails on a shared key
      re-typed in compose or the workflow, or a secret-looking name in `configs/.env`.
      **Shipped on consumer A, 2026-10-04.** Read back here from the live service the same day: the
      only secret mount is `/secrets`, deploy-time env went 27 → 20 keys with no shared key left,
      and a live CORS preflight returns the baked values (credentials `true`, max-age `86400`).
      Lessons the pilot added (now in the GoFr skill the fleet's sessions use): `configs/.env.*`
      does not match `configs/.local.env`, so ignore it explicitly in `.gitignore` and
      `.dockerignore`; every workflow that re-applies the bundle mount must move with it, because
      `--update-secrets` adds a mount path and never removes one; a boot sentinel key that exists
      only in the baked file makes a re-hidden `configs/` fail at boot instead of silently dropping
      CORS; anything that runs the bare binary from a checkout now reads the committed
      `HTTP_PORT`, not GoFr's default 8000.
- [x] **Three reusable workflows default `mount_path` into the directory the layout must keep
      clear.** Decided 2026-10-05: `mount_path` is now required on `rotate-signing-keypair`,
      `rotate-worker-signing-secret` and `sync-bundle-key` (no default), shipping in `v3.0.0`;
      docs and examples show `/secrets/app.env`. See DECISIONS.md 2026-10-05.

## Post-deploy probe — prove the observability pipeline actually DELIVERS (opened 2026-09-18)

Handed over from the consumer A umbrella session. The owner ruled this a **platform** concern, not a
Consumer A one: the incident was consumer A's, the failure class is generic. **Filed for triage, not
started** — nothing here is designed or agreed yet.

- [x] **A post-deploy probe that fails the release when metrics are not arriving.** ✅ **BUILT
      2026-09-18 as `verify-metrics-arrival.yml`** — see `docs/verify-metrics-arrival.md` and
      `DECISIONS.md` 2026-09-18. Three outcomes (PASS / no-metrics / **cannot-verify**), an
      unfiltered positive control, a *list* of prefixes with PASS on the union, and the log grep
      pinned to the **serving** revision. Six paired step-body tests. Original entry: The failure
      class: *a broken observability path deletes the very signal that would announce it.*
      consumer A's api ran for weeks with its GCP OTel exporter delivering **zero** metrics because
      `OTEL_RESOURCE_ATTRIBUTES` lacked `gcp.project_id`. Every gate stayed green the whole time
      — deploy, Cloud Run startup probe, `/.well-known/alive`, `migrate-smoke`, `storage-probe` —
      because the only evidence was a log line *inside the container*, and the thing that would
      have raised the alarm was the pipeline that was down. Above the container log, "exporter
      broken" and "quiet system" are indistinguishable.

      The concrete check, as handed over (two parts, post-deploy, fails the release):
      1. List `metricDescriptors` for a given prefix on a given GCP project and **fail on zero**
         (consumer A's case: prefix `prometheus.googleapis.com/`, project `<consumer-A-project-id>`).
      2. Grep the **serving** revision's logs for the exporter's upload error and fail on any hit
         (consumer A's case: `failed to upload metrics` on service `<service>-api`).

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
        `<consumer-C-project-id>`, `custom.googleapis.com/` and `workload.googleapis.com/` both return 0 while
        `prometheus.googleapis.com/` returns 7 — GMP publishes under the `prometheus.` prefix.
        This is precisely why the control is mandatory rather than nice-to-have.

      **No fire:** the consumer A instance is fixed (api v0.56.3). Verified by that session on
      2026-09-18 — `<consumer-A-project-id>` now holds 7 `prometheus.googleapis.com/` descriptors (was zero)
      and no `failed to upload metrics` lines on `<service>-api` in the preceding 3 hours. This item
      is the generic prevention.

      Pointers, all in `<consumer-A-org>/api`: `docs/rca-metrics-never-reached-google-2026-09-18.md`
      (full RCA), `DECISIONS.md` 2026-09-18 (b), `TODO.md` L11-21 (the original entry, still
      worded as api-owned; that session is re-pointing it separately).

## Two items rehomed from the inflight tracker (opened 2026-09-08)

Both were carried as live state in `~/.claude/inflight/` for several sessions. Neither is
live state — they are backlog, so they belong here. Recorded verbatim; neither is started.

- [x] **CI guard: assert the `v1` alias has NOT moved.** ⚠️ **Rewritten 2026-09-15 — this item
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
      **DONE (verified 2026-10-29):** `ci.yml` job `v1-alias-frozen` runs `make v1-frozen`
      (`ci.yml:182-201`), which calls `scripts/check_v1_frozen.py`.

## Secret Manager

- [x] **CLOSED 2026-10-20 (superseded): the owner chose the existing `cleanup-secret-versions` sweeper with `enable_destroy: true` on a schedule (it already has the quarantine clock, the --etag re-check and the consumer scan); disabled versions are billed, so consumers should schedule it. Not built in sync-bundle-key.** `.github/workflows/sync-bundle-key.yml` — owner ask 2026-10-20: after a green roll, destroy old DISABLED bundle versions except the newest disabled (disabled versions are billed like enabled; destroyed are free). A first version (input `destroy_old_disabled_versions`, default false) was written and pulled before v3.8.0; the code is in commit 56ff8c0 (reachable via refs/pull/140/head; `git show 56ff8c0` has the step, input, tests and docs). It conflicts with DECISIONS 2026-08-17 ("disable is inline, destroy stays in the sweeper"), whose reasons (number-pinned consumers, a run must not destroy what it just disabled, a retention failure must not fail the write run, cost ~$0.78/month) need an owner ruling to supersede. Required fixes if built inline: record the DISABLED set in the `cur` step BEFORE the disable step and destroy only from that set minus its newest, never anything in `/tmp/to-disable.txt` (else a rollback destroys the last good version and a pre-existing ENABLED tail is disabled then destroyed); the dry run must show the real plan; destroy with `--etag` and re-check `latest` right before each call like `cleanup-secret-versions.yml:615-637`; `</dev/null` on the gcloud call in the read loop and fail if destroyed != planned; decide whether a destroy error may turn a rolled deploy red (08-17 says no, so likely warn-only) and say why. Alternative needing no new code: switch consumers to `cleanup-secret-versions` with `enable_destroy`. Tests must run Disable then Destroy together with a stub that honours `--sort-by`, including the rollback layout.
- [x] **CLOSED 2026-10-20 (v3.8.0).** `.github/workflows/sync-bundle-key.yml` — value-safety gaps found 2026-10-20 by a local run of its merge code (lines 219-234, v3.7.0 = main): (1) the replace path `awk -v v=…` (:224) processes backslash escapes, so a `\` in an EXISTING key's value is corrupted (the append path is fine); (2) a multi-line value is written as raw lines and breaks the `.env`; (3) `grep -q "^${key}="` treats the key as a regex (`A.B` matches `AxB`); (4) empty, whitespace-only and placeholder values are refused only by `min_value_length` (default 8): `changeme` and 10 spaces pass. Fix: pass values via ENVIRON, not `-v`; refuse a newline; match the key literally; add a placeholder/whitespace check. Red step tests first.
- [x] **`cleanup-secret-versions.yml` — ✅ ADOPTED 2026-08-24 (consumer B + <consumer-A-org>).**
      Zero callers since `v2.3.0`; the first adoption attempt immediately surfaced two latent
      defects in the workflow (project-wide `secrets.list` demanded to validate a name;
      `secrets_list` collapsing multi-secret lists) — fixed, with step tests, see DECISIONS
      2026-08-24. **A workflow with no callers has no runtime signal: CI green meant only that
      the YAML parsed and the plan logic was right.**
      Live survey, same day, of what the sweep would actually find:
      | project | secret | versions |
      |---|---|---|
      | `<consumer-B-project-id>` | `app-secrets` | 2 ENABLED (v9, v10), 8 already DESTROYED |
      | `<consumer-A-project-id>` | `app-secrets` | 3 ENABLED (v3–v5), 2 DISABLED (v1, v2, since 2026-05-24) |
      So with the defaults (`keep_enabled_count: 3`, `min_age_days: 7`) **both projects plan zero
      disables today** — the accumulation the workflow was built for is not present. Its value
      here is (a) prospective: the sweep runs on a schedule so it never accumulates, and
      (b) <consumer-A-project-id>'s two DISABLED versions, which are past any quarantine and are the only
      destroy candidates in the fleet. Adopt with `dry_run: true` + `enable_destroy: false`
      first, read a plan, and only then consider the destroy flip.
      **DONE, end to end, same day.** IAM: `infra-provisioning#35` merged and APPLIED to both
      projects (3 binds each — `secretVersionManager` + `viewer` ON `app-secrets`, project
      `logging.viewer` → `github-cleaner`); verified live read-only afterwards, not just from
      the run log. Callers: `<consumer-B-org>/project#42` + `<consumer-A-org>/project#92`, both monthly,
      both pinned `@v2.4.1`, both shaped so the SCHEDULE NEVER ACTS.
      **First real runs (`dry_run: true`) confirm the plan predicted from the survey:**
      | project | latest | enabled | disabled | consumers | to disable | to destroy |
      |---|---:|---:|---:|---:|---|---|
      | `<consumer-B-project-id>` | 10 | 2 | 0 | 6 | — | — |
      | `<consumer-A-project-id>` | 5 | 3 | 2 | 2 | — | 2, 1 |
      consumer B's empty plan is the CORRECT result, not a misfire. <consumer-A-project-id>'s v1+v2 are
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

## Archived 2026-10-29 (closed items from live sections)

Closed `- [x]` items moved out of sections that still hold open work; each group names
its original `TODO.md` section. Text is verbatim.

### From: Owner rulings to build (opened 2026-10-21)

- [x] **CLOSED 2026-10-21 (v4.1.0): the composite action `actions/sync-bundle-key` runs in the
  caller's own `environment:` job and reads environment secrets from `secrets_json`
  (docs/sync-bundle-key-action.md). The rotator got the same treatment
  (`actions/rotate-worker-signing-secret`). Live cross-org proof is the consumer's first run.**
  `.github/workflows/sync-bundle-key.yml` — DESIGN NEEDED (owner): environment-level secrets
  cannot reach the sync from a caller in another organisation. Two cross-org dry runs on
  2026-10-21 refused with "No environment secret for listed key(s)". `payload_source: caller`
  reads repo/org secrets only, because the caller job cannot declare `environment:`. Until it's
  fixed, cross-org callers keep sync-read values at repo level (docs/sync-bundle-key.md).
- [x] **CLOSED 2026-10-22 (v5.0.0), superseded.** `actions/sync-bundle-key/build-env-payload.sh` —
  the `carry_keys` DESIGN NEEDED item (a rotator-owned key could be neither listed nor unlisted with
  `payload_source: environment`). Superseded by merge-only (owner ruling): `mode` and
  `confirm_removed` are gone, the sync keeps every key it is not given, and `remove_keys` is the
  only removal (DECISIONS 2026-10-22). Reported by consumer A 2026-10-22.
- [x] **CLOSED 2026-10-21 (v4.1.0).** `.github/workflows/deploy-cloud-run.yml` — `image` input
  deploys a prebuilt image by DIGEST (tag refused, owner ruling), skipping build/push and keeping
  the full deploy path; a `Verify prebuilt image` step fails if the digest is not in GAR (DECISIONS
  2026-10-21 "digest only").
- [x] **CLOSED 2026-10-21 (v4.1.0), names changed by owner ruling:** `probe_path`/`expected_status`
  are the existing `smoke_path`/`smoke_status`, and `cert_timeout_minutes` is the existing
  `certificate_timeout_seconds` (default 1800; set 3600 for the 60 min below). DECISIONS
  2026-10-21 "a remap fails where a fresh map warns".
  `.github/workflows/bootstrap-cf-service.yml` — map AND remap a Cloud Run domain in the same
  workflow: an opt-in input re-targets a hostname from a named current service (delete → create →
  wait for the certificate → probe the status code); without it, refuse as today (owner,
  2026-10-21). Design agreed with the first consumer 2026-10-21 (build is a minor release):
  - `retarget_from: <service>` (default empty = refuse exactly as today). The run refuses unless the
    live mapping's routeName EQUALS it. Already on `service` = no-op, so a re-run is safe.
  - `probe_path` is REQUIRED whenever `retarget_from` is set: an API often answers `/` with 401, so
    `/` is a poor default. `expected_status` defaults to 200 and is asserted as a status code.
  - Pre-flight before any delete: the target `service` exists, its latest revision is Ready and
    serves 100% of traffic, and its own run.app URL answers `probe_path` with `expected_status`.
    Otherwise refuse with nothing deleted.
  - Then: delete → create → poll the mapping's Ready condition every 30s up to
    `cert_timeout_minutes` (default 60) → probe `https://<host><probe_path>`. A timeout or a failed
    probe FAILS the run, because the old service is already unmapped.
  - No automatic rollback: re-mapping the old service is a second cert issue. On failure the summary
    prints the exact map-back command.
  - `dry_run: true` prints the full plan (current routeName, the target's readiness, what would be
    deleted and created) with no writes.
  - The summary records the outage window: delete time → probe-200 time.
  - IAM: run.domainmappings.get/create/delete + run.services.get (document a custom role; don't
    require run.admin). A CAA record that does not allow Google's CA is reported as a warning.

### From: Release flow — `spec-compat` has no way to acknowledge a deliberate removal (opened 2026-10-15)

- [x] `docs/release-flow.md` §Contract checks — between-services-only rule, the two-release
  route, and the `breaking-approved` waiver (2026-10-15, `feat/breaking-approved-waiver`).
- [x] Ship rw `v3.5.0` and send consumer C the tag, SHA, `RELEASE_FLOW_TREE` and the caller changes
  (release-pr trigger types; `--pair`, `--consumer-side`, `RELEASE_BREAKING` on its spec-compat line).
  Shipped 2026-10-15 (tag object `184c1a9` → `8e6f0bd`). Consumer C adopted it the same day; the
  pins, trigger types and flags were verified read-only at its root main `6bc9fff`.
- [x] Consumer C — move check B out of the root `release.yml` into the provider service's own
  CI. Done 2026-10-15, verified read-only: root `6bc9fff` dropped the `<provider>@live →
  <provider>` pair. Provider main `c76935c` gained a `spec-compat` job in its release gate,
  run against the spec the live service serves.
- [x] `actions/release-flow/releaseflow/ops_subset.py` `load()` — comparing a JSON spec with a
  YAML spec gives false breaks. JSON goes through `json.loads`, which keeps the string `"off"`.
  YAML goes through `yaml.safe_load`, which follows YAML 1.1 and turns an unquoted `off`/`on`/
  `yes`/`no` into a boolean. Consumer C measured this on 2026-10-15: a served `openapi.json`
  against a raw `swagger.yaml` reported 2 false enum narrowings. The mechanism is checked in the
  code; the 2 false hits are consumer C's report and were not re-run here. A same-format
  comparison is not affected, because both sides are misread the same way. Fix: load YAML with a
  loader that keeps those words as strings (one that drops the YAML 1.1 bool resolver), add a
  mixed-format regression test, and ship it in a patch release. FIXED 2026-10-15 on branch
  `fix/spec-yaml-bool-words` (`test_spec_load.py` red → green). Not in a release yet: that
  waits on the owner's explicit ask.
- [x] `release_flow.py` (the `ops-subset` / `spec-compat` usage text) and `spec_compat.py`
  (module docstring) — consumer C's real file paths replaced with generic wording
  (2026-10-15, `feat/breaking-approved-waiver`).
- [x] Wider (owner ruled 2026-10-15) (found 2026-10-15 by a `git ls-files` sweep): the whole
  release-flow package and its tests/testdata used consumer C's service names and matching
  testdata file names. Renamed 2026-10-15 to neutral roles (core, gateway, web, site, tool, lib)
  on the owner's ruling that this public repo names no consumer service. The second, older name
  for `ops-subset` was dropped the same day, after consumer C moved off it (verified read-only at
  its root main).

### From: Service alerts — rollout and deferred slice (opened 2026-09-23)

- [x] **First live `dry_run` on <consumer-C-project-id>** — DONE 2026-09-23, <consumer-C-org>/project run
  35840428112 @v2.10.0.
  - `job_workflow_sha` is present, but for a tag pin it is the annotated TAG OBJECT's SHA
    (1687ae3), not the commit's. Docs now say so.
  - The data check found data for 9 of 9 rules; the plan was 11 × `would create`, with no
    collisions.
  - The `userLabels` filter ran without error, but against an empty project, so it has not
    yet shown a MATCH. The first re-run after the apply proves that: it must read
    `unchanged` × 11.
- [x] **First apply on <consumer-C-project-id> + fire tests** — DONE 2026-09-23. All 11 policies are live
  (read back).
  - Log-match policies DO need `logging.notificationRules.create`: the first apply 403'd, and
    infra-provisioning #81 added `logging.configWriter`.
  - The `userLabels` MATCH is proven: after the apply, the re-run read `unchanged` × 9 with
    drifted 0.
  - Incidents confirmed in `ViolationOpenEventv1`, with the 2026-09-06 control:
    - latency rule: 09:40:14Z;
    - `logs.error_match` on a test filter: 10:28:46Z, and again at 10:45:03Z, because the
      test filter stayed armed until the 11:08Z revert.

  The first latency attempt opened nothing: it was reverted before evaluation.

### From: Build-once, promote-to-prod

- [x] **GAR retention is release-relative.** `cleanup-gar-images` no longer age-deletes the
      `:<sha>` promotion source: per package it keeps sha images newer than the
      `sha_retention_releases`-th most recent release (ordered by time, not semver).
      ✅ **The keep-only claim HOLDS for identical input — root cause of the 105-vs-103
      delta established 2026-08-11** (an earlier note here declared the claim false; that note
      was wrong and is corrected). The `v1.15.0` (103) and `v1.21.1` (105) dry-runs on
      `<consumer-C-org>/project` were 2m27s apart, and both extra digests are **untagged with
      `age_days` exactly 15** against `untagged_max_age_days: 15` (`>=`) — they aged past the
      threshold *between the runs*. The delete loop and live-digest collection are
      byte-identical across the two tags, the keep-set can only grow, and HEAD's delete-set is
      a strict subset of `v1.15.0`'s on all 13 fixtures. See DECISIONS.md; boundary pinned by
      `tests/fixtures/t23-untagged-age-boundary.json`.
      **Still dry-run and diff the plans before repinning a caller** — but read the diff
      properly: untagged digests sitting exactly at the threshold age are wall-clock noise;
      tagged images, live digests, or ages away from the boundary are real. Latent `TypeError`
      on a missing `updateTime` fixed in the same pass.
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

### From: Convergence — remaining work

- [x] **Reusables still to build** — all built 2026-08-24: `deploy-cloudflare-worker`,
      `bootstrap-cf-service` + `bootstrap-cf-dns` (the `bootstrap-cf` item split in two —
      giving one service a hostname and managing a zone's records are different targets;
      see DECISIONS 2026-08-24), and `cloud-run-update`. **No caller is migrated yet**;
      each moves in its own repo's PR after the next release tag. `cloud-run-update` has
      no adoptable caller at all until the <consumer-C-org> hold lifts.
      Superseded note: ~~`run-db-job`~~ —
      **built 2026-07-28** (Cloud Run Job converge + execute/wait), alongside a
      `docker_target` input on `deploy-cloud-run`. Both additive. Driven by the
      `<consumer-B-org>/api` conversion; see DECISIONS.md 2026-07-28, which also records why the
      runner-side prebuild hook that conversion seems to need was **not** added.
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
- [x] `docs/*.md` / `README.md` — **example pins swept to `v1.20.0` (2026-08-11).** All 39
  `uses: …@vX.Y.Z` lines across the docs were spread over twelve different tags, the oldest
  `v1.4.0`, so most copy-paste examples silently gave the reader a stale contract. Now uniform.
  **This will rot again** — the drift-report entry below is the durable fix; until it exists,
  sweep as part of each release.
- [x] **caller pin-drift — reframed 2026-08-11.** Built as a weekly scan over a committed
  list of four orgs, then **de-scoped the same day**: this repo is public, so most callers are
  private and none are ours to watch. Shipping an org list in a public repo also asserts an
  ownership relationship the project does not have. The scheduled workflow and `fleet.json`
  are **removed**; `scripts/fleet_drift.py` survives as an operator tool requiring an explicit
  `--orgs`. **The consumer-facing answer is Dependabot** (documented in AGENTS.md + README) —
  it reaches private callers, which nothing we run can. Original entry:  (`scripts/fleet_drift.py` + `.github/workflows/caller-drift.yml`, weekly + dispatch, org list in `fleet.json`). First real run: **24 of 32 caller pins need attention**, incl. nine in `<consumer-B-org>/project` nobody had looked at. Needs `FLEET_READ_TOKEN` (cross-org read) before the schedule is useful. Original entry:  The 2026-07-27 repin sweep
  (see DECISIONS.md) found 18 of the fleet's 27 caller lines stranded on `@v1.4.0`/`@v1.5.0`, six-plus
  releases behind, and only noticed because someone manually read check-run *annotations*
  across every caller. Nothing detects this. Wanted: a scheduled workflow in this repo that
  walks the platform orgs, greps every `.github/workflows/*` for
  `Just-Git-Dev/reusable-workflows/...@<ref>`, and reports (issue or job summary) any caller
  more than one minor behind the latest tag — plus any pinned to a **mutable ref** (the sweep
  found `<consumer-C-org>/project` on `@v1`, i.e. still running the original `b96d0e3` implementation).
  Cheap to build (the sweep was ~30 lines of `gh api`); the value is that fixes we ship actually
  reach the repos that need them. **Derive the org list from an authoritative source** —
  `infra-provisioning/projects/*` + the CF/GitHub target configs — not a hand-typed list: the
  first manual pass silently omitted the entire `<consumer-C-org>` org.
- [x] **`ci-node` / `ci-go`: the badge job forced `contents: write` on every caller — fixed in `v1.21.0`.** The job
  declares `permissions: contents: write` statically (`ci-node.yml:424`), and GitHub validates a
  called workflow's permissions against the caller **at startup**, before job-level `if:` is
  evaluated — so a `contents: read` caller gets `startup_failure` with no logs **even when
  `update_badges` is false**. This is not theoretical: `<consumer-A-org>/webapp` hit it and is frozen at
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
- [x] **`deploy-cloudflare-pages` post-deploy smoke check — BUILT 2026-08-11** (`smoke_path`, `smoke_expect`, bounded retry, blocking). Next: migrate `<consumer-C-org>/web` onto the reusable, which this unblocks. Original entry:  (`smoke_path` + bounded
  retry poll, fail the deploy if the live site doesn't serve it). Not speculative: `<consumer-C-org>/web`
  hand-rolls exactly this after the **2026-06-29 `/device` outage**, where a stale bundle went
  live with a broken client-routed path and nothing caught it — Pages deploys are
  eventually-consistent, so the poll needs a bounded retry, not a single curl. It is also part of
  why that repo has not migrated to the reusable. **Six consumers**: the five current callers
  (`<consumer-B-org>/{ui,admin-ui,website}`, `<consumer-A-org>/{webapp,website}`) plus `eazyupdates-ui`. Lift the
  logic from `<consumer-C-org>/web`'s `deploy.yml` rather than reinventing it.
- [x] **Repin the three GAR callers onto `v2.0.0`** (release-relative retention). **DONE — overtaken
      by events 2026-08-20:** all three had already reached `@v2.2.0`, and the fleet-wide repin to
      `@v2.3.1` (<consumer-B-org>/project#31, <consumer-C-org>/project#13, <consumer-A-org>/project#82) supersedes this
      item. `<consumer-A-org>/project#65` was closed, so its pin-comment fix did not need folding in; the
      stale pin comments were rewritten to name no version at all in the repin PRs. Original text:
      `<consumer-C-org>/project`
      is on `@v1.21.1`; **`<consumer-A-org>/project` and `<consumer-B-org>/project` are still on `@v1.15.0`**, which
      predates the retention window entirely, so today they run on `keep_semver_count` + age alone.
      Per repo: dry-run BOTH pins, diff the plans, then repin. Expect a larger first sweep — v1 was
      silently retaining a backlog. `<consumer-C-project-id>` takes `grace_period_days: 1` (it is the one doing
      build-once promotion). Fold `<consumer-A-org>/project#65`'s pin-comment fix and incident record into
      the <consumer-A-org> repin PR rather than merging it separately — same file, guaranteed conflict.
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
  write silently drops the first one's keys. Found 2026-08-17 while mapping the consumer B callers;
  no overlap observed in run history (not checked), the exposure is a scheduled quarterly/annual
  rotation landing on a manual sync. Fixing it in the reusables covers every caller at once —
  consumer B's caller-level `group: secrets-rotation` only papers over two of the four.
