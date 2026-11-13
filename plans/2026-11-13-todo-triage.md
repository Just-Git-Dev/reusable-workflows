# reusable-workflows TODO.md triage — 2026-11-13

Source: `reusable-workflows/TODO.md` at `c5131d3` (469 lines). Every row was checked against the
repo at that commit unless the Evidence column says UNVERIFIED. Consumer repos were NOT read
(project sessions own reads of their repos), so consumer-side status is UNVERIFIED throughout.
Raw check output: `.scratch/todo-triage/checks.out`, `.scratch/todo-triage/zizmor.out`.

Classes: DONE, OBSOLETE, READY (size S/M/L), WAITING/BLOCKED, REFERENCE, WRONG-HOME, NEEDS-OWNER.

| # | Section | Item (short) | Class | Evidence | Size / blocker / home |
|---|---|---|---|---|---|
| 1 | Waivers beyond `contracts` (11-13) | Plan stage outputs the release PR's label list | BLOCKED (owner) | `release-plan.yml:88-110` outputs are manifest, manifest-sha256, pr, order, rehearsal, resolved, checks, breaking, ci-filters; no labels. Section says "not ruled, not built" | S once ruled. Owner: build the waiver extension at all? |
| 2 | same | Caller-declared waiver kinds (`waiver_pairs`) | BLOCKED (owner) | `waiver_pairs` appears nowhere outside TODO (`/usr/bin/grep -rn`, 0 hits) | M once ruled. Owner: how R3 applies to a kind with no `checks` entry |
| 3 | Rotate external secret (11-12) | `read-state.sh` captures `gh variable get … 2>&1` as state | READY | `actions/rotate-external-secret/read-state.sh:8` `OUT=$(gh variable get … 2>&1)` — confirmed | S. Red test with a `gh` stub that warns on stderr and exits 0; then `2>"$errf"`. Patch release |
| 4 | ci-green `paths` allowlist (11-01) | [x] native `paths` support in `ci.py` | DONE | `a9066ff` (#173), in tag `v6.0.0`; `actions/release-flow/releaseflow/ci.py:7-14,105` | Leaves TODO. Residual live proof → row 4b |
| 4b | same (residual) | Consumer C removes its `["**"]` workaround and re-runs its rehearsal on v6 | WAITING (consumer C) | DECISIONS.md:434 names the step; no live-proof record found in DECISIONS | Kept as one WAITING line |
| 5 | App-token `app-id` deprecated (10-28) | [x] `app-id` → `client-id`, plus `github-token` mode | DONE | `3dd44ec` (#175), in `v6.0.0`; workflows describe `client-id` / `github-token` (e.g. `release-plan.yml:37`) | Section closes |
| 6 | Owner rulings (10-21) | [x] remove rotate-worker-signing-secret | DONE | `ee35ddc` (#174), in `v6.0.0`; `actions/rotate-worker-signing-secret` and its workflow are absent | Leaves TODO |
| 7 | same | v5.1.0 live proof of `public: true` | WAITING (first adopter) | No DECISIONS hit for "public services in the register"; consumer adoption UNVERIFIED | Blocker: a consumer calls `repos-deploy-scope` with `public: true` |
| 8 | same | `catalog.json` lists App-key / `github-token` recipients; workflow-preflight checks callers | READY (rw half) + WRONG-HOME (preflight half) | `catalog.json` workflow entries carry only inputs/jobs/name/outputs/path/secrets/workflow; no recipient field. Preflight is vendored (`Makefile:221-227`, re-vendored `cc4aad0`), so its check lands upstream | M. First step: add a `credential_recipients` (name TBD) block to `scripts/gen_catalog.py` output. Upstream preflight source not located |
| 9 | zizmor ignores (10-21) | template-injection: move `${{ }}` in `run:` into `env:` | READY | `zizmor.yml:113-128` ignores 10 files (TODO says 11). `zizmor --offline --no-config` on `.github/workflows` today: 30 `error[template-injection]` findings (TODO's "57 sites" is a different count, stale) | L. First step: the files `tests/run_step_tests.py` covers best, one file per PR, drop its ignore |
| 10 | same | Re-check the other ignores | READY (partly BLOCKED) | `zizmor.yml:134-163`. github-app needs the per-App permission set from the owner (`zizmor.yml:136-138`); unpinned-images and unsound-ternary have reasons that look permanent | S. Re-label permanent ones as accepted-with-reason; ask owner for App permission sets |
| 11 | spec-compat removals (10-15) | `v3.5.0` breaking-approved rehearsal on a real breaking PR | WAITING (consumer C) | No live record in DECISIONS (index grep for "breaking-approved" + live/rehearsal: 0) | Blocker: consumer C's first tagged provider release that removes something |
| 12 | app-id from environment (10-13) | Fall back to `vars.RELEASE_APP_CLIENT_ID` in env-scoped mint jobs | WAITING (second consumer) | Not built: `RELEASE_APP_CLIENT_ID` appears only in comments/descriptions (`release-plan.yml:14,37` etc.). Item's own trigger: "only when a second consumer hits it" | Blocker: second consumer |
| 13 | same | `docs/release-flow.md` Smoke: say which ref the specs come from | READY | `docs/release-flow.md:46-47` still reads "against the resolved refs and images", silent on spec ref | S, doc-only. First step: add the rule + the `fromJSON(needs.plan.outputs.resolved).<ui>.ref` wiring example |
| 14 | Pre-commit gates (09-27) | Gate reads a neighbouring working tree | WRONG-HOME | Developer-tooling class, not a `workflow_call` body; section says "each project fixes its own hooks". Not present in `~/.claude/TODO.md` (grep 0) | Home: fleet tooling TODO (`~/.claude/TODO.md`, devops session) |
| 15 | same | Pre-commit tier lacks the cross-layer tier | WRONG-HOME | same | same |
| 16 | same | Flaky / false-positive guards (a)-(d) | WRONG-HOME | same; (a)/(c) may be shared developer-tooling guards per the item | same |
| 17 | Third-party images (09-24) | Mirror pinned third-party images (GHCR or GAR) | BLOCKED (owner) | Item: "Owner to decide on the registry and which images are in scope" | Blocker: owner picks registry + scope |
| 18 | same | Scheduled probe: every pinned image still resolves | READY | No such workflow in `.github/workflows/` (listing checked) | M. Must be a caller-invoked reusable on the caller's own repo, not an org-wide scanner (see the 2026-08-11 de-scope fact, row R4). First step: plan with the three-outcome shape of `verify-metrics-arrival` |
| 19 | Service alerts (09-23) | v2.11 slice: `prune`, `probe.health_body`, gofr packs, absence, raw promql, drift WARN, `render_dynatrace` | WAITING (demand / metrics) | `plans/service-alerts.md:13,15,181,237,242` defer these on review ("was overbuilt"); `prune`/`health_body` absent from `service-alerts.yml` | L. Packs blocked until their metrics exist; the rest waits on a consumer ask |
| 20 | same | Data check fails only when EVERY service is empty | WAITING (watch) | Item is "revisit if quiet services hide real breakage" — a trigger, not a task | Blocker: evidence of hidden breakage |
| 21 | Release hygiene (09-06) | Runbook: never publish until tag-push CI is green | OBSOLETE | Superseded structurally: `release.yml:7-16,83` runs `stamp_version.py --check --expect` BEFORE the tag; `360d70a` (#90) item 4d | Leaves TODO |
| 22 | same | Price a ruleset gating release publish on the tag check | OBSOLETE | Ruled out: `release.yml:12-15` ("a GitHub ruleset cannot fix this"), `360d70a` 4d, `plans/provenance-and-release-gate.md` §2 (named at `release.yml:7`, not read) | Leaves TODO |
| 23 | same | Stamp gate does not assert its own coverage | READY | `scripts/stamp_version.py:182-187` `pin_files()` is a fixed set; no function checks that every pin-bearing file is in it (def list `:69-312`). The 2026-10-21 RCA (DECISIONS.md:675) was a second instance of the same file-set gap. No live instance today: 0 tracked files outside the set carry a `reusable-workflows/...@vN` pin (positive control: the same grep matched `.scratch/` copies) | S. Red test in `tests/run_stamp_tests.py`: a pin in a file outside `pin_files` must fail `--check` |
| 24 | same | Audit other gates for derived comparands / assumed scopes | READY (partly DONE) | validate-alerts audited: `plans/validate-alerts-audit-2026-09-15.md` (both shapes "not found"), `360d70a` 4b | M. Remaining: `check_docs_coverage.py`, `check_pinned_actions.py`, `check_v1_frozen.py`, `deploy_env_lint.py`, ci-green |
| 25 | same | Consumer pin inventory (sub-section) | OBSOLETE (data) + WRONG-HOME (repin) | Numbers dated 2026-09-15 at v2.x; current tag `v6.2.0`. Item itself: "the repin itself is consumer-repo work" | Drop the numbers; keep the `scripts/fleet_drift.py` command in Reference |
| 26 | Build attestations | Decide a `provenance` policy | DONE (confirm) | `360d70a` (#90, in `v2.8.0`) 4c: `provenance` (default `mode=min`) and `sbom` (default `false`) inputs on all three build surfaces — `deploy-cloud-run.yml:112-126,454-455`, `deploy-gke-service.yml:102,326`, `deploy-cluster-keyed.yml:152`; `docs/deploy-cloud-run.md:91` | Chosen = explicit buildx default + caller input. NEEDS-OWNER to confirm this closes it |
| 27 | Build-once | Pilot `<consumer-C-org>/core` end-to-end | WRONG-HOME | All edits are in a consumer repo; reusable side done (`v1.17.0`). Status UNVERIFIED | Home: `infra-provisioning/TODO.md` §"Consumer follow-ups (moved from reusable-workflows 2026-10-29)" |
| 28 | same | Roll to the remaining four | WRONG-HOME | same | same |
| 29 | same | Post-pilot proof on the real repos | WRONG-HOME | same (runs against consumer GAR repos) | same |
| 30 | same | Stage environments out of scope | REFERENCE | A scope ruling, not a task | Home: DECISIONS entry or `docs/promote-image.md` |
| 31 | same | Encode the Summary-step rule (no bare trailing conditional) | READY | Step-body tests exist (`ci.yml:321-326`, `make step-bodies`) but no bare-conditional rule (grep for the rule in `tests/`, `scripts/`, `Makefile`, `ci.yml`: 0) | S. First step: a grep check in `make ci` over every `>> $GITHUB_STEP_SUMMARY` group, red on the 2026-07-27 shape |
| 32 | Convergence remaining | `promote-image` artifact quarantine (optional) | WAITING (demand) | No `quarantin` in `promote-image.yml` | M. Blocker: a real incident or owner priority |
| 33 | same | GSM→k8s wiring workflow | WAITING (demand) | Not built; `manage-config-secrets.yml:19-20` points at it | L. Blocker: a consumer workload needing GSM delivery into pods |
| 34 | same | Implement the reserved `eso` backend | WAITING (paired with 33) | `manage-config-secrets.yml:16,108,241-242` still "reserved, not implemented" | M |
| 35 | same | Private-registry auth beyond one npm registry | WAITING (second registry) | Item: "revisit when a second registry actually shows up" | Blocker: a caller with two registries |
| 36 | same | Tell callers in their run when they are behind | READY (design first) | No `releases/latest` call in any workflow (`/usr/bin/grep -rl` hits only `actions/release-flow` python) | M. First step: plan answering its 3 open questions (which workflows, token, opt-out) |
| 37 | same | `cleanup-secret-versions`: adopt delayed destruction | READY (spike first) | Not adopted: `quarantine_days` still at `cleanup-secret-versions.yml:133,217,459`. DECISIONS 2026-08-17: it "simplifies the sweeper but does not replace it" | S spike (answer a/b/c), then M |
| R1 | Operating facts | Current tag is looked up (`gh release list`) | REFERENCE | — | Home: README "Pinning" text |
| R2 | same | API edits to workflow files need the `workflow` OAuth scope | REFERENCE | — | Home: `docs/PLATFORM.md` maintainer notes |
| R3 | same | `gh pr merge` may be refused by the permission classifier | OBSOLETE (duplicate) | Already in workspace `CLAUDE.md` §Workspace traps (4th bullet) | Drop from TODO |
| R4 | same | Do not build consumer monitoring (de-scoped 2026-08-11) | REFERENCE (a ruling) | No DECISIONS entry found (`/usr/bin/grep` "scanner/caller-drift/consumer monitoring" in both DECISIONS files: 0) | Home: a DECISIONS.md entry |
| 38 | same (stray checkbox) | `manage-config-secrets` refuses a `gsm` create of a `*-env` secret | READY | Not built: gsm validation `manage-config-secrets.yml:245-250` checks payload/name/mode only. Ruling 24: DECISIONS.md:1038 | S. Red test: `secret_name=<svc>-env` with `secrets_backend=gsm` must fail |
| 39 | same (stray checkbox) | `repos-secrets` IAM-condition redesign | READY | Refusal shipped: `repos-secrets.yml:160-164`; redesign (carry condition into state) open | M. First step: a plan fixture in `scripts/repos_secrets_plan.py` tests with a conditional binding |

## Counts
DONE 4 (rows 4, 5, 6, 26) · OBSOLETE 4 (21, 22, 25-data, R3) · READY 13 (3, 8, 9, 10, 13, 18, 23,
24, 31, 36, 37, 38, 39) · WAITING/BLOCKED 13 (1, 2, 4b, 7, 11, 12, 17, 19, 20, 32, 33, 34, 35) ·
WRONG-HOME 6 (14-16, 27-29) plus the preflight half of 8 · REFERENCE 4 (30, R1, R2, R4).

## Could not verify
- Consumer-side status of rows 4b, 7, 11, 27-29 (consumer repos not read, by rule).
- `plans/provenance-and-release-gate.md` content (cited by `release.yml:7`; not opened).
- Where workflow-preflight's upstream source lives (row 8 preflight half).
- zizmor counts are from `--no-config` on `.github/workflows` only; `action.yml` (github-env) not scanned.
