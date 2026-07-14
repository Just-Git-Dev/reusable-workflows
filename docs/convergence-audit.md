# Convergence & optimization audit — 2026-07-14

A one-time survey of every GitHub Actions workflow across all orgs the maintainer
can access, to decide **what should converge into this repo** and **what to
optimize** here. Scope decision and the resulting build are recorded in
[DECISIONS.md](../DECISIONS.md) (2026-07-14 entry).

## Method

- Enumerated **379 repos across 16 orgs**; **140** pushed since 2025-01-01;
  **~60** carry `.github/workflows`.
- For each active workflow: fetched the body, classified it, checked whether it
  already `uses:` a reusable, scanned for tech-debt (action versions, node
  version, `::set-output`, SHA-pinning, `shell: bash`), and pulled the last ~15
  run outcomes/durations via `gh run list`.

## Three worlds

| World | Orgs | Reusable home | Verdict |
|---|---|---|---|
| **Just-Git-Dev platform** (Cloud Run + Cloudflare + WIF) | AutoMahn, Realm-ID, Traide-Co, RevvUp-AI, quizzing-pro, zop-mannai, Just-Git-Dev | **this repo** | primary convergence target |
| **Legacy ZopSmart** (GKE + GCR/GAR) | zopsmart | `zopsmart/workflows` (modern) + `zopsmart/zs-workflows` (legacy) | do **not** fold in — separate platform. But it is the thing we want app repos to *leave* (see goal below) |
| **Zopsmart-HIMS** (OpenAPI spec-lint) | Zopsmart-HIMS | `Zopsmart-HIMS/project` | already converged 40→1; leave in-org |

**Stated goal (2026-07-14):** grow this library until platform app repos can drop
their dependency on **`zopsmart/workflows`** entirely. That makes a GKE
service-deploy reusable and language CI reusables in-scope, reversing the first
pass's "kept per-repo" call.

## Headline findings

1. **The two most-duplicated workflows are the two we don't offer: Cloud-Run
   deploy and CI.** ~13 repos hand-roll CI; ~7 hand-roll a deploy. None share
   code because no reusable exists.
2. **Adoption of existing reusables is low and stuck on the frozen `@v1` alias.**
   The only live adopters — `bootstrap-alerts`, `cleanup-gar-images`,
   `neon-backup`/`backup-db` — all pin `@v1`, which CLAUDE.md says never to pin
   new callers to. Move them to `v1.2.0` (the current release).
3. **Several repos hand-rolled inline copies of workflows that already exist as
   reusables:** Traide-Co/api `neon-backup.yml`, Traide-Co/project
   `rotate-cloudflare-token.yml`, and 8× Cloudflare-Pages deploys.
4. **The classic "old node / deprecated action" rot lives in legacy zopsmart, not
   the platform.** Platform repos are on node 20/22 and checkout@v4–v6. Their
   real debt is: **no `shell: bash` (no `pipefail`) anywhere**, **no SHA-pinned
   third-party actions**, **gcloud-auth v2/v3 drift**, **wrangler-action v3-vs-v4
   skew**.
5. **Cross-org supply-chain exposure:** RevvUp-AI and quizzing-pro deploy via
   **`zopsmart/workflows@main`** — external org, mutable ref, mints cloud creds
   and pushes images. Retiring this is the goal above.

> **Unverified claim, flagged:** one survey pass reported a `${{ vars.* }}` parse
> bug in `deploy-cloudflare-pages.yml` at `@main` that startup-fails callers.
> Checked against the actual file — local `==` origin/main, clean, **no `vars.`
> misuse**. Does not reproduce on current `main`. Do not treat as a live defect;
> ask the RevvUp caller why they inlined.

## Per-repo migration assessment (platform)

"% improvement" = **Maint** (duplicated config retired) + **Runtime/Reliability**
(from run data; estimates flagged *est.*).

| Repo | n | Migrate to reusable? | Est. improvement | Debt cleaned up |
|---|---|---|---|---|
| AutoMahn/api | 8 | Yes — deploy→*new* cloud-run; 2 workers→*new* cf-worker; lint→*new* ci-go; backup-db already (repin) | Maint ~60%; deploy 322s→~200s *est.* (gha cache) | gcloud v2→v3; `shell: bash`; SHA-pin; drop @v1 |
| AutoMahn/image-service | 1 | Yes — deploy→*new* cloud-run | Maint ~70%; 197s→~130s *est.*; fixes 22% fail | gcloud v2→v3; `shell: bash` |
| AutoMahn/project | 15 | Mostly — 4 rotate-*→*existing*; 4 bootstrap-cf→*new*; alerts+gar already (repin) | Maint ~50%; reliability (proxy 100%, signing-secret 100%, alerts 86% fail) | `shell: bash`; drop @v1 |
| AutoMahn/{admin-ui,ui,website} | 4 | Yes — *existing* deploy-cloudflare-pages (3); ui/lint→*new* ci-node | Maint ~65% | wrangler v3-vs-v4 unify |
| Realm-ID/api | 2 | Yes — ci→*new* ci-go; deploy→*new* cloud-run | Maint ~55%; ci 724s→~300s *est.* | gcloud v2→v3; `shell: bash` |
| Realm-ID/issuer | 4 | Yes — deploy→*new* cloud-run; seed/botuser→*new* run-db-job; flip-audit stays | Maint ~50%; fixes seed 80%/botuser 50% fail | `shell: bash`; SHA-pin |
| Realm-ID/project | 6 | Yes — provision-*+scaling→*new* cloud-run-update; test→*new* ci-go; gar already (repin) | Maint ~45%; **test.yml 93% fail / 568s** = #1 problem child | `shell: bash`; gcloud v2→v3; drop @v1 |
| Realm-ID/{ui,website} | 2 | Yes — *existing* deploy-cloudflare-pages | Maint ~65% | wrangler@v3; `shell: bash` |
| Realm-ID/{sdk,cli} | 3 | No/low — publish maven/npm, goreleaser single-repo | — | SHA-pin only |
| Traide-Co/api | 3 | Yes — ci→*new* ci-go; deploy→*new* cloud-run; **neon-backup = stale inline → *existing*** | Maint ~55%; fixes backup 75%, deploy 33% | gcloud v2 drift; `shell: bash` |
| Traide-Co/project | 5 | Yes — rotate-db-redis + rotate-r2→*existing* sync-bundle-key; bootstrap-cf-dns→*new*; rotate-cf-token+alerts stale/legacy-pin | Maint ~50% | drop @v1; align rotate-cf-token semantics |
| Traide-Co/{webapp,website} | 3 | Partial — deploy→*existing* pages; ci(node)→*new* ci-node | Maint ~50%; **website 78% fail** | `shell: bash` |
| Traide-Co/sync | 1 | No — WiX/MSI desktop build | — | SHA-pin only |
| RevvUp-AI/geo-engine | 12 | Yes — **5 ci→2** (ci-go+ci-node); **6 stage + prod→*new* gke deploy** (retires external @main) | **Maint ~70%** (11→~3); retires cross-org creds risk | SHA-pin; `shell: bash`; kill @main |
| RevvUp-AI/project | 1 | Yes — *new* gke/helm deploy (cleanest WIF template) | Maint ~40% | pin azure/setup-helm |
| RevvUp-AI/public-audit-api | 1 | Yes — *new* gke deploy | fixes 33% fail | kill external @main |
| RevvUp-AI/website | 3 | Partial — pages→*existing*; test→*new* ci-node; branch-guard→*new* util | Maint ~40% | SHA-pin wrangler |
| quizzing-pro/{api,engine,admin-ui,ui} | 4 | Strategic — already DRY on external `zopsmart/workflows@main` (GKE). Converge to JGD gke deploy to drop external @main | Maint low; **risk-retirement high** | node 18→20/22; replace @main |
| zop-mannai/api | 2 | Yes — 2 inline Java→GKE deploys→*new* gke deploy; **both broken, use stored SA-JSON key** | Maint ~50%; fix broken + move to WIF | **SA-JSON→WIF**; docker-login@v2/setup-gcloud@v2; `shell: bash` |
| Just-Git-Dev/infra-provisioning | 2 | No — provisioning plane, keyless WIF, modern; ownership split keeps it out | — | none (healthy) |

**Non-candidates:** zop-mannai/demo-repository (template demo),
Zopsmart-Training/* (training assignments), Zopsmart-HIMS/* (already converged).

## Convergence catalog

| Priority | Reusable | Status | Collapses | Reach |
|---|---|---|---|---|
| 1 | `deploy-cloud-run.yml` (build→push→`run deploy`, WIF, gha cache) | 🆕 build | AutoMahn api+image-svc, Realm api+issuer, Traide api | 5 repos / 3 orgs |
| 2 | `ci-go.yml` + `ci-node.yml` (setup→lint→test, cache, `blocking` input) | 🆕 build | AutoMahn 2, Realm 3, Traide 2, RevvUp 6 | ~13 repos / 4 orgs |
| 3 | `deploy-cloudflare-pages.yml` | ✅ adopt | AutoMahn 3, Realm 2, Traide 2, RevvUp 1 | 8 callers — quick win |
| 4 | `sync-bundle-key` / `rotate-signing-keypair` / `rotate-worker-signing-secret` | ✅ adopt | AutoMahn 4, Traide 2 (inline today) | 6 callers |
| 5 | `deploy-gke-service.yml` (kubectl set-image / helm, WIF) | 🆕 build *(strategic)* | RevvUp 9, quizzing 4, zop-mannai 2 | ~10 repos — retires external @main |
| 6 | `bootstrap-cf.yml` (DNS/origin-rules/routes) | 🆕 build | AutoMahn 4, Traide 1 | worst failure rates |
| 7 | `deploy-cloudflare-worker.yml` (`wrangler deploy`) | 🆕 build | AutoMahn 2 | 2 callers |
| 8 | `cloud-run-update.yml` (env/secret/scale) + `run-db-job.yml` (one-shot WIF DB job) | 🆕 build | Realm 4 + 3 | Realm-heavy |
| 9 | `neon-backup.yml` | ✅ adopt | Traide api (stale inline) | 1 caller |

## Optimize the existing library (from run data)

| Item | Evidence | Fix |
|---|---|---|
| All adopters pin frozen `@v1` | AutoMahn/Realm/Traide callers | repin to `v1.2.0`; documented in each caller PR |
| `bootstrap-alerts` failing where adopted | AutoMahn 86% (7 runs), Traide 100% (1) | triage the one workflow that has real adoption **before** promoting others |
| No `ci-*`/`deploy-*` in library | 13+ hand-roll CI, 7 deploy | build catalog items 1, 2, 5 |
| CF-Pages callers failing | Traide website 78%, webapp 33% | reusable itself verified clean on `main`; publish known-good SHA, drive adoption |

## Warnings / deprecations cleaned up by this work

- **Platform:** add `shell: bash` fleet-wide; unify gcloud-auth v2→v3; unify
  wrangler-action v3→v4; SHA-pin third-party actions; drop `@v1` alias pins;
  zop-mannai stored SA-JSON key → keyless WIF; RevvUp/quizzing external
  `zopsmart/workflows@main` → pinned JGD reusable.
- **Legacy zopsmart (separate effort):** retire `zs-workflows` (checkout@v2/v3,
  setup-node@v3, setup-java@v1, docker-login@v1, build-push@v2, auth@v1,
  `github-push-action@master`, node-16-era); migrate stragglers + inline holdouts
  (saaj-api on checkout@v2, eazyupdates-ui) onto modern `zopsmart/workflows`;
  finish modernizing that repo's `_test-go`/`_test-node` leaves and cut real tags.
- **Zopsmart-HIMS:** already 40→1 converged (the model). Residual: callers pin
  `@main` (one bad commit red-lit all 40 on 2026-06-26) and non-SHA
  checkout@v5/setup-python@v6. Cut a tag, SHA-pin. Do not move to JGD
  (domain-specific linter).

## Build plan (this repo)

Ordered by reach × safety; each new reusable ships with `docs/<name>.md`, passes
`actionlint`, SHA-pins third-party actions, and sets `shell: bash`.

1. `ci-go.yml`, `ci-node.yml` — cleanest contract, highest reach, first step to
   dropping `zopsmart/workflows` test-and-lint.
2. `deploy-cloud-run.yml` — Cloud-Run build+deploy with layer/module caching.
3. `deploy-gke-service.yml` — replaces `zopsmart/workflows` deploy for GKE apps.
4. Fix `bootstrap-alerts` (real adoption, failing).
5. `bootstrap-cf.yml`, `deploy-cloudflare-worker.yml`, `cloud-run-update.yml`,
   `run-db-job.yml` — the long tail.

Callers are **not** touched here; they will be migrated one repo at a time via
their own PRs after these land and are tagged.
