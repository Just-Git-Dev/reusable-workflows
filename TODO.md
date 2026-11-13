# TODO — reusable-workflows

## Index — what to pick up next

Ranked by value for effort. Re-triaged 2026-11-13 against `c5131d3`; closed and superseded items
moved to [TODO-ARCHIVE.md](TODO-ARCHIVE.md) (same log, split by state only). Sizes: S < half a
day, M about a day, L several.

1. **S** — `TODO.md:"stores that capture as STATE"` — a shipped action stores `gh` stderr warnings as state.
2. **S** — `TODO.md:"assert its own COVERAGE"` — the stamp gate's file set has already been wrong twice.
3. **S** — `TODO.md:"create of a"` — ruling 24 is enforced only in a doc today.
4. **M** — `TODO.md:"receive the App private key"` — owner-requested 2026-10-21; ends hand-kept key guards.
5. **S** — `TODO.md:"which ref the smoke SPECS come from"` — doc-only; a consumer already failed a rehearsal on it.
6. **S** — `TODO.md:"bare conditional"` — the Summary-step rule, as a CI grep.
7. **M** — `TODO.md:"IAM conditions"` — repos-secrets conditional-binding redesign.
8. **S** — `TODO.md:"re-check the other ignores"` — zizmor ignores that a fix or a reason can retire.
9. **S then M** — `TODO.md:"delayed destruction"` — spike (a)-(c) before any build.
10. **M** — `TODO.md:"Audit the remaining gates"` — derived comparands / assumed scopes.
11. **M** — `TODO.md:"when they are on an old version"` — needs its three questions answered first.
12. **M** — `TODO.md:"every pinned image in the fleet still resolves"` — caller-invoked probe.
13. **L** — `TODO.md:"template-injection: move"` — one workflow per PR.

Waiting on someone else: see [Waiting / blocked](#waiting--blocked). Items that belong in another
tracker are listed under [Flagged: belongs elsewhere](#flagged-belongs-elsewhere) until the owner
confirms the move.

## Ready — release and stamp gates

- [ ] **The stamp gate does not assert its own COVERAGE.** `PIN_RE` in `scripts/stamp_version.py`
      requires a literal `Just-Git-Dev/reusable-workflows/...`, and `pin_files()` is a fixed set
      (docs, README, AGENTS, published workflows). Any file outside that set, or any pin shape
      `PIN_RE` doesn't match, is invisible to both the sweep and `--check` — **an uncovered file is
      indistinguishable from a passing one.** No live instance today (checked 2026-11-13: no
      tracked file outside the set carries a `reusable-workflows/...@vN` pin), but the 2026-10-21
      RCA (action pins inside workflows) was this exact gap. Fix: assert that every tracked file
      containing a `uses: .../reusable-workflows/...@` pin (by a loose regex, not `PIN_RE`) is in
      the swept set, and fail on any that is not. First step: a red case in
      `tests/run_stamp_tests.py`. Size S.
- [ ] **Audit the remaining gates for the same two shapes** — comparands that are all derived, and
      scopes that are assumed rather than computed. `validate-alerts` is done
      (`plans/validate-alerts-audit-2026-09-15.md`: both shapes not found). Remaining:
      `check_docs_coverage.py`, `check_pinned_actions.py`, `check_v1_frozen.py`,
      `deploy_env_lint.py`, and release-flow ci-green. Size M.
- [ ] **Encode the Summary-step rule:** a `{ … } >> $GITHUB_STEP_SUMMARY` group must not end in a
      bare conditional — it is the script's last statement, so its status becomes the step's
      (the 2026-07-27 deploy-cloud-run bug). Either a shellcheck-style grep in CI, or a
      `run_step_tests.py` case per Summary step asserting rc=0 with an empty env. The grep is
      cheaper and catches all of them at once. Size S.

## Ready — release flow

- [ ] `docs/release-flow.md` §Contract checks/Smoke — say which ref the smoke SPECS come from.
      "Against the resolved refs and images" is silent on it, and a consumer whose e2e specs
      track its umbrella `main` failed an api-only rehearsal on 2026-10-13: the UI resolved to its
      LIVE tag, while `main`'s specs already tested unreleased UI screens (23 failures, 0 writes).
      State the rule: the specs must match the refs under test, and name the caller-side options
      (specs gated by the minimum UI version they need, with the skip count printed; or specs taken
      at the commit matching the resolved UI ref). Show the wiring a caller already has:
      `fromJSON(needs.plan.outputs.resolved).<ui>.ref` into its own smoke workflow, as the caller
      example does for `backend_ref`. Doc-only; no input-contract change. Size S.

## Ready — secrets and access workflows

- [ ] `actions/rotate-external-secret/read-state.sh` captures `gh variable get … 2>&1` and stores that
      capture as STATE. If `gh` prints a warning on stderr and still exits 0 (an update
      notice, a deprecation), the warning text becomes part of the stored state. Fix: capture
      stdout only (`2>"$errf"`) and read stderr only to classify a failure. The same bug class
      shipped in a consumer's release workflow on 2026-11-11. Rule: claude-config
      `skills/github-actions` §3d. First step: a red test with a `gh` stub that warns on stderr
      and exits 0. Patch release. Size S.
- [ ] `.github/workflows/manage-config-secrets.yml` — refuse a `gsm` create of a `*-env` secret
      (ruling 24, DECISIONS 2026-10-20: F8 `repos-secrets` is the one writer; only the doc states it
      today). Size S.
- [ ] `.github/workflows/repos-secrets.yml` — IAM conditions: the fetch step and `live_lines`
      (`scripts/repos_secrets_plan.py`) drop `condition`, and gcloud add/remove run without
      `--condition`, so a conditional `<d>-run` line would read in-sync in F8 while the engine's
      secret_audit flags it forever. F8 now refuses a conditional `<d>-env` policy (error, no
      write). Open: the redesign — carry `condition` into state, treat conditional lines as extra,
      `--condition=None` on add. Size M.
- [ ] `catalog.json` + `scripts/workflow_preflight.py` (fleet) — ship the list of workflows that
      receive the App private key (workflow, secret input name, required caller environment) with
      rw, and have workflow-preflight check every caller against it, so projects stop
      hand-maintaining their own key-recipient guards (owner, 2026-10-21; a consumer's guard needed
      a hand exception to adopt `repos-environments`). Since v6 the same list must also name each
      workflow's `github-token` secret. The rw half is `scripts/gen_catalog.py`; the preflight
      check lands in workflow-preflight's upstream and is re-vendored here. Size M.
- [ ] `cleanup-secret-versions.yml` — adopt Secret Manager **delayed destruction** and drop the
      audit-log clock. `gcloud secrets update <secret> --version-destroy-ttl=30d` (API field
      `version_destroy_ttl`, min 1d / max 1000d) makes a destroy land as `DISABLED` +
      `scheduledDestroyTime`, cancellable before that time. The delay is then enforced
      server-side, so the sweep can drop `quarantine_days`, `roles/logging.viewer`, and the
      "disable event not found ⇒ HELD forever" branch. See DECISIONS 2026-08-17 (it simplifies
      the sweeper but does not replace it). **Spike first, none of it confirmed:**
      (a) is a version awaiting `scheduledDestroyTime` still billed at $0.06/mo? If so the saving
      is deferred by the TTL, not avoided.
      (b) which role grants `secretmanager.secrets.update`? Setting the TTL mutates the *secret*,
      so `roles/secretmanager.secretVersionManager` may not cover it, and secret *configuration*
      arguably belongs with `manage-config-secrets`.
      (c) a version awaiting destruction is `DISABLED`, so the sweep would re-select it next run:
      no-op, error, or does it reset the clock?

## Ready — workflow security (zizmor ignores)

zizmor was added to the gate with per-rule, per-file ignores in `zizmor.yml` (reasons in DECISIONS
2026-10-21). Each ignore is debt to pay down, not policy.

- [ ] **`zizmor.yml` — re-check the other ignores** (github-app, unpinned-images, unsound-ternary,
      github-env, cache-poisoning) and remove each one a fix can retire. Where the reason is
      permanent (a caller-chosen service image; a deliberate empty-string ternary in a job name),
      say so as accepted. github-app needs the exact permission set per App from the owner. Size S.
- [ ] `.github/workflows/*.yml` — **template-injection: move** each `${{ }}` used inside `run:`
      into an `env:` entry and reference `"$VAR"`. 10 files ignored; 30 findings on 2026-11-13
      (`zizmor --offline --no-config`). Exercise each deploy body before dropping its ignore; one
      workflow per PR, best-tested first. Size L.

## Ready — new capability

- [ ] **Tell callers, in their own run, when they are on an old version.** `WORKFLOW_VERSION`
      ships in every reusable's `env:` (a called workflow cannot discover its own ref at runtime:
      `GITHUB_WORKFLOW_REF`/`_SHA` describe the caller, and there is no `job_workflow_sha`). What
      remains is a cheap, **never-failing** step that compares `WORKFLOW_VERSION` to the latest
      release and writes a `::notice::` + step-summary line when behind. Open questions for the
      plan: which workflows carry it (all, or only the deploy paths — one API call per run);
      whether it needs a token (`/releases/latest` is public but rate-limited by runner IP, so it
      must degrade silently); an opt-out input for callers who deliberately hold a pin. Size M.
- [ ] **Scheduled probe: every pinned image in the fleet still resolves.** A reusable workflow,
      run by each caller on its own repo, that greps compose/Dockerfile/workflow refs and runs
      `docker manifest inspect` on each, with a positive-control ref, so "couldn't check" never
      reads as "all fine". Same three-outcome shape as `verify-metrics-arrival`. Not an org-wide
      scanner (see `TODO.md:"Do not build consumer monitoring"`). Background: a third-party image
      vanishing from its public registry breaks every pinned consumer at once, and local stacks
      hide it from the image cache (MinIO, 2026-09-24: `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z`,
      `quay.io/minio/mc:latest` and `minio/minio:latest` all failed `docker manifest inspect`).
      Size M.
- [ ] **`validate-alerts`: four checks have no dedicated test** — `combiner`, the channel
      placeholder, the `autoClose` range, and the log-condition rate limit. Add one red-first case
      each (re-filed here 2026-11-13 from infra-provisioning's TODO, where it sat as a pointer).
      Size S.

## Waiting / blocked

**On an owner ruling**
- [ ] Release flow — plan stage outputs the merged release PR's label list (today it exposes
      `resolved`, `checks`, `breaking` and others, no labels), so a caller needs no labels job of
      its own. Recorded 2026-11-13 at a consumer's request (it wants its own "oldest published
      client SDK" stage waivable like a spec break); not ruled, not built.
- [ ] Release flow — caller-declared waiver kinds (working name: a `waiver_pairs` input), so a
      non-`contracts` break is waived through the same R1-R3 path as a spec break (today
      `waiver.py` R1/R2 accept only services.json `contracts` pairs). Design question for the
      owner: how R3's "a live check entry per listed pair" applies to a kind with no `checks` entry.
- [ ] **Mirror pinned third-party images into our own registry (GHCR or GAR).** Consumers pull
      from the mirror, so an upstream withdrawal becomes a sync failure rather than an outage.
      Owner to decide on the registry and which images are in scope.

**On a consumer (live proofs)**
- [ ] v6.0.0 ci-green `paths` allowlist: consumer C removes its `"paths_ignore": ["**"]`
      workaround and re-runs its rehearsal; record the run here and in DECISIONS.
- [ ] v5.1.0 public Cloud Run via F7: on the first adopter's `repos-deploy-scope` run with
      `public: true`, record the run id, check the Plan step printed
      `public services in the register: [...]`, and read the invoker back (`allUsers`
      `roles/run.invoker` on that service only).
- [ ] `v3.5.0` breaking-approved rehearsal, verified read-only: on a real breaking PR the check
      goes red without the label, green with it, red with one line edited. Waits on consumer C's
      first tagged provider release that removes something.

**On demand (build when a caller needs it)**
- [ ] `.github/workflows/release-{plan,drafts,publish}.yml` — fall back to
      `vars.RELEASE_APP_CLIENT_ID` inside the environment-scoped mint jobs when `client-id` is
      empty, so the Client ID can sit beside `RELEASE_APP_KEY` on the environment. Since v6 an
      empty `client-id` means token mode, so the fallback must not change what the guard sees.
      Additive (a minor). Only when a second consumer hits it.
- [ ] Service alerts **v2.11 slice** (`plans/service-alerts.md`): `prune` (owner-scoped),
      `probe.health_body` uptime check (opt-in, it keeps instances warm), the `gofr-http-client` /
      `gofr-pubsub` / `gofr-cron` packs once their metrics exist to verify against, `absence`,
      raw `promql:` (GMP-only), the drift WARN for hand-written policies, and `render_dynatrace`.
- [ ] `.github/workflows/service-alerts.yml` — the data check fails a rule whose service had no
      traffic for a whole day only when EVERY service in it is empty; a per-service gap is only a
      warning. Revisit if quiet services turn out to hide real breakage.
- [ ] `.github/workflows/promote-image.yml` — (optional) **artifact quarantine**: let a bad
      digest/tag be marked quarantined so `promote-image` refuses to promote that specific
      artifact, without freezing all promotion. See the 2026-07-15 no-pin decision.
- [ ] **GSM→k8s wiring/provisioning workflow.** `manage-config-secrets.yml` manages values only
      and deliberately does not wire a GSM secret into pods. A separate reusable should provision
      that path — Secret Manager CSI driver + `SecretProviderClass`, or an External Secrets
      Operator `ExternalSecret`/`SecretStore`.
- [ ] `manage-config-secrets.yml` — implement the reserved `eso` backend (errors "not
      implemented" today): emit an `ExternalSecret` CR referencing the GSM secret written by the
      `gsm` backend. Counterpart of the wiring workflow above.
- [ ] `ci-node.yml` / `deploy-cloudflare-pages.yml` — generalise private-registry auth beyond a
      single npm registry. `setup-node`'s `registry-url` writes exactly one registry line, so a
      repo pulling from two private registries hand-rolls its own `.npmrc`. A list input would
      mean owning the `.npmrc` ourselves. Documented as a known limitation in both docs pages;
      revisit when a second registry shows up.

## Flagged: belongs elsewhere

Not rw work. Listed so nothing is lost; the owner confirms each move.

- **Build-once rollout** (consumer repos; reusable side done in `v1.17.0`, DECISIONS 2026-07-27).
  Proposed home: `infra-provisioning/TODO.md` §"Consumer follow-ups (moved from
  reusable-workflows 2026-10-29)".
  - [ ] Pilot `<consumer-C-org>/core` end-to-end: `main`-triggered `deploy-cloud-run` with
        `build_only: true` → `:<sha>`; migrate-smoke against that image; tag path calls
        `promote-image` (`source_tag: ${{ github.sha }}`, `deploy_target: cloud-run`,
        `environment: production`, `enforce_forward_only: true`), `dry_run: true` first. Set
        `source_wait_seconds` (build p99 + queue, e.g. 900) and `timeout_minutes` above it (the
        2026-07-28 race RCA).
  - [ ] Roll to the remaining four: `<consumer-C-org>/gateway`, `<consumer-A-org>/api`,
        `<consumer-B-org>/image-service`, then `<consumer-B-org>/api` last. Precondition per repo:
        config is runtime-resolved (`APP_ENV=prod` a `--set-env-vars`, not a build arg) —
        re-verify, don't assume.
  - [ ] Post-pilot proof: `cleanup-gar-images` `dry_run: true` against each of the 5 GAR repos,
        confirm `candidates` drops (see the 2026-08-11 boundary-crossing entry before reading a
        small rise as a regression); assert prod digest equals the `:<sha>` digest; exercise
        `promote-image`'s preflight on a tag whose commit never built.
- **Pre-commit gates that check the wrong thing** (developer tooling, not `workflow_call`
  bodies; each project fixes its own hooks). Proposed home: the fleet tooling TODO
  (`~/.claude/TODO.md`, devops session). Reported by one consumer, not re-checked here.
  - [ ] A gate that reads a neighbouring working tree instead of what is being committed (an api
        coverage check read the live sibling `../ui`). Fix shape: read the committed tree
        (`git show <ref>:<path>`) or refuse on a dirty one.
  - [ ] The pre-commit tier doesn't include the tier that catches cross-layer breaks (an api
        commit broke 6 integration tests and passed its hook). Which tier must a commit gate
        include, and what catches the rest before push?
  - [ ] Flaky or false-positive guards: (a) a GoFr lint rule flags `RETURNING id` on valid code;
        (b) a ui visual check's `.run-started-at` marker races; (c) a route-registration edit hook
        gives false positives; (d) an api pre-commit exited rc=1 after "checks passed". (a) and
        (c) may be shared developer-tooling guards; check before assigning an owner.

## Reference — operating facts (not tasks)

Proposed homes in brackets; move them and delete this section.

- **Do not build consumer monitoring.** A scheduled caller-drift scan was built and de-scoped the
  same day (2026-08-11): this repo is public, most callers are private, and shipping an org-wide
  scanner from a public repo is the wrong trade. [a DECISIONS.md entry — none exists today]
- **Caller pin drift is measured, not remembered:** `python3 scripts/fleet_drift.py --orgs <orgs>`.
  The repin itself is consumer-repo work, and each pin needs its own diff read (semver tracks the
  input contract). [docs/release-process.md]
- **Stage environments are out of scope** (owner's call): the `main` job stays build-only; where a
  stage later exists, add the deploy step there. [DECISIONS.md or docs/promote-image.md]
- **The current tag is looked up, not remembered** — `gh release list`. Consumers pin an exact
  `vX.Y.Z`; `@v1` is a frozen legacy alias and `@main` is never acceptable. [README]
- **Editing any `.github/workflows/*` file through the API needs the token's `workflow` OAuth
  scope.** `repo` alone 404s, which looks like a missing file. Fix: `gh auth refresh -s workflow`.
  [docs/PLATFORM.md]
