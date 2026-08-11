# TODO — reusable-workflows

## Build-once, promote-to-prod

Reusable-side work is **done** (`v1.17.0`): `deploy-cloud-run` gained `build_only`,
`cleanup-gar-images` gained the release-relative sha retention window (keep-only, default on)
plus the first test suite in this repo. See DECISIONS.md 2026-07-27.

- [x] **GAR retention is release-relative.** `cleanup-gar-images` no longer age-deletes the
      `:<sha>` promotion source: per package it keeps sha images newer than the
      `sha_retention_releases`-th most recent release (ordered by time, not semver). Keep-only,
      so it can only ever delete less. Latent `TypeError` on a missing `updateTime` fixed in the
      same pass.
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
      `candidates` **drops** (keep-only ⇒ it can never rise). Then assert the prod digest equals
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
- [ ] `docs/ci-go.md` / `docs/ci-node.md` — every `Example caller` block still pins
  `@v1.4.0` while the repo is at `v1.15.0`; the new README-badges examples pin
  `@v1.16.0`, so the two docs now contradict themselves. Sweep all example pins to
  the current tag (and check the other `docs/*.md` for the same staleness).
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
- [ ] **caller pin-drift is invisible — build a drift report.** The 2026-07-27 repin sweep
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
- [ ] `ci-node.yml` / `deploy-cloudflare-pages.yml` — **optional `node_modules` caching.** Both
  rely on `setup-node`'s cache, which covers only `~/.npm`; npm still unpacks and links the tree
  on every run. `eazyupdates-ui`'s outgoing GKE workflow caches `node_modules` itself, keyed on
  `hashFiles('package-lock.json')` with no `restore-keys` (a prefix fallback would restore a tree
  built from a different lockfile), and its comment puts the tree at **~1.2 GB** — so migrating it
  to the reusables is a measurable build-time regression. Worth an opt-in
  `cache_node_modules` input. Note the key must include the Node version, and it is only sound
  because `npm ci` is deterministic.
- [ ] `deploy-cloudflare-pages.yml` — **add a post-deploy smoke check** (`smoke_path` + bounded
  retry poll, fail the deploy if the live site doesn't serve it). Not speculative: `Realm-ID/ui`
  hand-rolls exactly this after the **2026-06-29 `/device` outage**, where a stale bundle went
  live with a broken client-routed path and nothing caught it — Pages deploys are
  eventually-consistent, so the poll needs a bounded retry, not a single curl. It is also part of
  why that repo has not migrated to the reusable. **Six consumers**: the five current callers
  (`AutoMahn/{ui,admin-ui,website}`, `Traide-Co/{webapp,website}`) plus `eazyupdates-ui`. Lift the
  logic from `Realm-ID/ui`'s `deploy.yml` rather than reinventing it.
- [ ] **`Realm-ID/ui` + `Realm-ID/website` are the unmigrated Cloudflare Pages tail.** `ui` pins
  `cloudflare/wrangler-action@v4` — a **mutable tag**, which is precisely what this repo's SHA-pin
  CI rule exists to prevent, on a workflow holding a Pages deploy token; `website` shells out to
  `npx wrangler`. Both should move to `deploy-cloudflare-pages`, but the smoke-check gap above is
  a real blocker for `ui` — do that first, then migrate.
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
