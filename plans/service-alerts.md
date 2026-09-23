# Plan — shared, platform-neutral service alerts (GoFr + Cloud Run + logs + health probe)

## Decision summary (one screen)

| # | Decision | Basis |
|---|---|---|
| 1 | Apps write a short **AlertSpec** (`infra/alerts/alerts.yaml`): turn on built-in *packs*, override thresholds, add custom alerts. No PromQL needed. | owner: "structured" |
| 2 | The spec is **semantic** (metric + kind + filters + window + threshold-with-units) and a compiler renders it per backend. **GMP is live now; PrometheusRule is rendered and used as the offline test oracle; Dynatrace (DQL) is a documented mapping, built later.** Stays our own format because OpenSLO puts a raw per-vendor query in every SLI, so it wouldn't be portable (§2). | owner asked; researched |
| 3 | New reusable **`service-alerts.yml`** renders in CI and hands the policies to the **existing** `validate-alerts` and `bootstrap-alerts` (each gains one additive input). Two possible mechanisms; spike 0c picks one before any code. | owner: "render at apply" |
| 4 | Every metric alert on GMP is a **PromQL condition**. Checked live: GoFr series and `run_googleapis_com:*` (with the `monitored_resource` matcher) both work, including `histogram_quantile`. | VERIFIED |
| 5 | **Thresholds carry units** (`5s`, `250ms`, `0.1/s`), converted per metric. GoFr mixes s/ms/µs and Cloud Run latency is ms. A bare number on a duration metric is an error. | design |
| 6 | New rule **`gofr.metrics.silent_while_serving`**: Cloud Run has traffic but GoFr exports nothing. It fires on the 2026-09-22 broken window and is empty now. | VERIFIED on history |
| 7 | `bootstrap-alerts` gains `dry_run` and hash-based update of *managed* policies, scoped by an owner label. `prune` is deferred. | RealmID ask 5 + review |
| 8 | realm-id `github-rotator` gets `monitoring.editor` (fleet precedent). `logging.configWriter` is decided by the first apply. | owner applies |
| 9 | **Slice 1 = v2.10.0**: core, 6 packs whose metrics exist in GMP today, 4 custom kinds, and `dry_run`. Deferred: the rest (§6). | review: was overbuilt |
| 10 | Release only on explicit ask. Catalog semver rules are in §4. | CLAUDE.md |

Rollout: RealmID first (its session offered; prod has had no alerts since 2026-09-22), then Traide and AutoMahn swap their hand-written 5xx/p95/memory/crash-loop policies for packs. Their 5xx policies are MQL, whose support ended 2025-07-22.

---

## 1. Context

- **Today every app hand-writes its alert policies.** Traide and AutoMahn have near-identical
  policies differing only by service name. **None alerts on a GoFr metric**, and none uses
  PromQL. RealmID prod has no active alerts: its uptime check probed `/alive`, which stayed green
  through a 27h46m Neon outage, and the check was deleted.
- **Owner's ask (2026-09-23):**
  - reusable alerts on GoFr metrics, with defaults, per-app threshold overrides, and custom
    alerts on app metrics;
  - a config not tied to GMP, wired to GMP for now.
- **RealmID's session asked devops for the generic layer:**
  - Cloud Run templates;
  - a health probe that checks the response body, not just the status code;
  - fixes to the shared applier;
  - the IAM grant.
- **GoFr ships no alert rules.** Its only example is a docs PrometheusRule for a demo service
  (`docs/guides/production-prometheus-kubernetes/page.md:103-168` in the gofr source). It
  alerts on:
  - 5xx above 5% for 10m (page);
  - p95 above 0.5s for 10m (ticket);
  - CPU above 85% for 15m;
  - `up == 0` for 2m.

## 2. Neutral format — structured, not OpenSLO (researched, primary docs)

- **Dynatrace can do everything the structured form needs.** It keeps bucket counts for OTLP
  *explicit-bucket* histograms, which is what GoFr emits, so `timeseries percentile(m,95)` works.
  DQL alerts can be managed as code through the Settings 2.0 schema
  `builtin:davis.anomaly-detectors` (Monaco or Terraform). So each `kind` has a DQL rendering.
- **Dynatrace has no PromQL at all.** So raw `promql:` is correctly non-portable, and the
  renderer must refuse it for a DQL target.
- **OpenSLO would not make alerts portable:**
  - `metricSource.spec` is a raw query written for one vendor;
  - core has no Dynatrace or GCP-alert converter;
  - its `AlertPolicy`/`AlertCondition` are SLO burn-rate alerts, not threshold alerts;
  - Sloth ignores its alerting section.
  Adopting it means writing every query once per backend. An SLO/burn-rate `kind` that emits
  OpenSLO can be added later.
- **Cloud Monitoring constraints:**
  - PromQL `evaluationInterval` must be a positive multiple of 30s (enforced).
  - `duration ≥ 2×` is guidance only, so it becomes a lint warning.
  - PromQL policies ignore `autoClose`; they close after max(270s, 2× interval) with no data.
    We still emit `autoClose` because the linter requires it, but the docs won't claim it does
    anything.
- **Sources:** OpenSLO README; sloth.dev/specs/openslo; Dynatrace docs (histograms, OTLP ingest,
  anomaly-detector API, Monaco); cloud.google.com `monitoring/promql/promql-in-alerting` and
  `deprecations/mql`.

## 3. Facts the design rests on (VERIFIED live on realm-id unless marked)

**How GoFr metrics look in GMP**
- Names are stored unsuffixed: `prometheus.googleapis.com/app_http_response/histogram`, labels
  `path`, `method`, `status`. The `job` label is the service name (`APP_NAME`).
- GMP PromQL rejects `=~` on `__name__`.
- Cloud Run metrics need `{monitored_resource="cloud_run_revision"}`.
- Only 7 descriptors exist per project. A metric that is registered but never recorded does not
  exist in GMP.

**GoFr v1.61.0 metric inventory** (source file:line in the explore report; spot-check during the
build)
- HTTP server: `app_http_response` (s).
- Outbound HTTP: `app_http_service_response` (s; `path` is the base URL), retries, circuit breaker.
- SQL: `app_sql_stats` (**ms**) and pool gauges.
- Redis: `app_redis_stats` (**µs**).
- pubsub total/success counters by topic; cron duration/total/success/failures by job.
- gRPC, GraphQL, LLM and file families exist, but no fleet app uses them.

**Excluded from the catalog**
- `app_go_*`/`app_sys_*` are only set inside the `/metrics` pull handler, so they are never
  emitted under push.
- 5 names are recorded but never registered.

**The GoFr vs Cloud Run gap was a window artifact**
- The 1d gap (80 vs 1,795) was the pre-fix gofr#4266 window: GoFr exported zero for 9.5h, until
  `METRICS_CARDINALITY_LIMIT=100` on revisions created 2026-09-22 18:28Z. On top of that, 1,479
  requests were since-deleted uptime probes. (RealmID localised this.)
- **I re-checked a post-fix 12h window. Counts:** issuer 32 GoFr / 25 Cloud Run; api 6 / 3.
  **p95:** issuer 1.88s / 1.35s. They track.
- **The fix is NOT yet proven.** The defect grows with a revision's *uptime*
  (label sets pile up over days warm). Post-fix revisions scale to zero and recycle before they
  could fail, and one uncapped revision also shows zero failures. Only RealmID's soak check
  against a days-warm revision (~2026-09-26) can tell "fixed" from "never ran long enough".
- **Silent-while-serving expression, checked on history:** `label_replace(Cloud Run rate→job) > 0
  unless on(job) GoFr rate > 0` returns api and issuer at 2026-09-22T13:00Z and nothing at
  2026-09-23T03:00Z.

**Cloud Run and log-alert constraints** (from RealmID's descriptor/discovery reads, not re-read by
me)
- `request_count` excludes requests that never reach an instance, such as auth-layer rejects or
  hitting the max-instances wall.
- Log-match conditions REQUIRE `notificationRateLimit` and never notify on close.

**Repo constraints**
- No composite actions: a local `./actions/x` resolves in the CALLER's workspace (DECISIONS
  2026-09-15).
- CI rejects any non-`./` `uses:` that isn't a 40-hex SHA (`ci.yml:246-248`).
- `stamp_version.py` does not sweep workflow bodies (`:40`, `:200`).

## 4. The AlertSpec (app-owned)

```yaml
apiVersion: alertspec/v1
services: [issuer, api]            # GoFr `job` label == Cloud Run service_name
packs: [cloudrun, gofr-http, gofr-sql, gofr-meta, gcp-logs]
overrides:
  cloudrun.5xx_count:           {threshold: 5, window: 5m}
  cloudrun.latency_p95:         {threshold: 5s, for: 10m}      # → 5000 (ms) for GMP
  gofr.http.server.error_ratio: {severity: ticket}              # until the soak re-check passes
  gofr.sql.pool_saturation:     {enabled: false}
  logs.error_match:             {filter: 'jsonPayload.message:"neon" AND severity>=ERROR'}
custom:
  - id: bff-upstream-errors
    metric: {name: bff_upstream_error, type: counter}
    kind: rate                     # error_ratio | rate | latency_quantile | value
    filters: {code: {in: ["502","503"]}}
    window: 5m
    op: ">"
    threshold: 0.1/s
    for: 10m
    severity: page                 # page | ticket  → AlertPolicy.severity CRITICAL | WARNING
    summary: "BFF upstream 5xx rate is high"
    triage: "…≥80 chars: what to check first…"
    may_be_absent: true            # metric may not exist yet → disableMetricValidation
```

**Precedence and grouping**
- Precedence runs catalog default → `overrides.<id>` → `overrides.<id>.services`.
- Services with identical parameters render as ONE policy (`sum by (job)`, one incident per
  series). Conditions stay close to one per rule, not rules × services.

**Guard shape** (golden-tested so both sides of `and` share the same `by`):
`(sum by (job)(rate(bad[W])) / sum by (job)(rate(all[W]))) > T and sum by (job)(increase(all[W])) >= N`.
- 0/0 is NaN, which compares false. A missing numerator raises no alert.
- p95 rules carry the same `and` guard.
- Default windows are ≥10m, because scale-to-zero makes shorter windows flap.

**Catalog semver** (applies the 2026-09-07 precedent)
- Minor, flagged at the top of the release notes: tightening or loosening a default, or adding
  a rule to a pack.
- Major: removing or renaming a rule id, or turning a ticket into a page.
- `catalog_version` is stamped into userLabels.

## 5. Slice-1 catalog (defaults; all overridable)

| Pack | Rule id | Signal | Default |
|---|---|---|---|
| cloudrun | `cloudrun.5xx_ratio` | `run_googleapis_com:request_count` 5xx/all by service, min 20 req | >5%, 10m window, for 10m, page |
| | `cloudrun.5xx_count` | same, absolute count (low-traffic apps) | off unless enabled; >5 per window |
| | `cloudrun.latency_p95` | `histogram_quantile(.95, …request_latencies_bucket)` (ms) + min-req guard | >2s, for 10m, ticket |
| | `cloudrun.memory_p99` | `…container_memory_utilizations_bucket` | >0.85, for 10m, ticket |
| gofr-http | `gofr.http.server.error_ratio` | `app_http_response_count` 5xx/all by job, min 20 | >5%, for 10m, page (the GoFr docs anchor) |
| | `gofr.http.server.latency_p95` | `app_http_response_bucket` (s) + guard | >2s, for 10m, ticket |
| gofr-sql | `gofr.sql.latency_p95` | `app_sql_stats_bucket` (ms) by job | >500ms, for 10m, ticket |
| | `gofr.sql.pool_saturation` | inUse / open connections | >0.9, for 10m, ticket |
| gofr-redis | `gofr.redis.latency_p95` | `app_redis_stats_bucket` (µs) | >50ms, for 10m, ticket |
| gofr-meta (GCP) | `gofr.metrics.silent_while_serving` | the verified expression in §3 | for 30m, ticket (k8s: `up == 0`) |
| gcp-logs (GCP-only) | `logs.crash_loop` | severity≥CRITICAL or `panic:` on cloud_run_revision | rateLimit 300s, page, no close promise |
| | `logs.error_match` | `filter` param required | rateLimit 300s, page |

**Deferred to v2.11+** (§6):
- `gofr-http-client` (errors, p95, circuit open), `gofr-pubsub`, `gofr-cron`: their metrics
  don't exist in GMP yet, so they can't be live-verified.
- `probe.health_body`: uptime check on `/.well-known/health` asserting `"status":"UP"`. Opt-in
  when it ships, because it keeps scale-to-zero instances warm and wakes Neon.

## 6. Architecture (reusable-workflows, public; never names consumers)

```
alerting/alertgen/   stdlib + PyYAML; `python3 -m alertgen {validate,render} --target gmp|prometheus`
  spec.py      load/validate/merge (catalog ⊕ overrides ⊕ custom); rejects unknown ids, bare numbers
  units.py     "5s" / "250ms" / "0.1/s" → per-metric unit
  metrics.py   registry: name, type, unit, label semantics, may_be_absent, platforms
  compile.py   kind → IR (selector, aggregation, window, op, threshold, guard)
  promql.py    IR → PromQL; GMP dialect (no __name__ regex, monitored_resource matcher, label_replace join)
  render_gmp.py   → AlertPolicy JSON: conditionPrometheusQueryLanguage (evaluationInterval 60s) or
                    conditionMatchedLog + notificationRateLimit; severity; documentation ≥80 chars;
                    NOTIFICATION_CHANNEL_PLACEHOLDER; autoClose 1800s; userLabels
                    {managed_by: alertgen, alertgen_owner: <repo-slug>, rule_id: gofr-http-server-error_ratio,
                     spec_hash: <16 hex>, catalog_version}; disableMetricValidation when may_be_absent;
                    PLUS a sidecar list of each rule's UN-thresholded expression, for the live data check
  render_prom.py  → PrometheusRule; used offline by `promtool test rules` as the semantic oracle
alerting/catalog/*.yaml   one file per pack; docs table generated from it
.github/workflows/service-alerts.yml
```

**`service-alerts.yml`**
- **Inputs:** `gcp_project`, `wif_provider`, `service_account`, `spec_file` (default
  `infra/alerts/alerts.yaml`), `channel_file`, `dry_run` (default `true` for `pull_request`
  callers per the docs example).
- **Permissions:** declared explicitly (`id-token: write`, `contents: read`), with the grant
  documented.
- **Getting its own code:** the render job checks out this repo **at the OIDC `job_workflow_sha`
  claim**, the exact commit of the called workflow. That works on PR branches, tags and this
  repo's CI, with no stamp gymnastics. `WORKFLOW_VERSION` stays display-only.
- **Render job:** runs `alertgen render`. Every un-thresholded expression must return ≥1 series,
  otherwise CANNOT-VERIFY (fatal unless `may_be_absent`). Then a job summary shows rendered
  policies against live.
- **Mechanism, decided by spike 0c:**
  - **(A) if `./` resolves inside a called workflow:** job 2 is `uses:
    ./.github/workflows/validate-alerts.yml`, job 3 is `bootstrap-alerts.yml`. Both take
    `policies_artifact` (artifact name `alertgen-<project>-<spec hash>`; a download failure
    fails the job).
  - **(B) otherwise:** one job runs the lint and apply `run:` bodies extracted at runtime from
    those two workflow files at the same `job_workflow_sha`. That keeps one parser (TESTING
    Principle 11), with no refactor of the two tested workflows and no tag pins.

**`bootstrap-alerts.yml` additions (additive)**
- `policies_artifact`.
- `dry_run`: plan only; prints create/update/skip per policy and warns when an update would
  overwrite a hand edit.
- **Managed update:** identify the policy by `alertgen_owner` + `rule_id` labels, never by
  displayName. Update when the live `spec_hash` differs from the render's. A hand-written policy
  holding a managed displayName is an ERROR, not a skip.
- Out-of-band edit detection: project the live policy onto the rendered key paths, canonicalise,
  compare. Also flag `mutationRecord.mutatedBy` ≠ the applier SA.
- `prune` is deferred, and will be owner-scoped when it lands.

**`validate-alerts.yml`:** gains `policies_artifact` only. Its "200 with empty result is fine"
behaviour stays, because the render job's data check covers that gap.

**Deferred to v2.11+:** `prune`; uptime probe; the http-client, pubsub and cron packs;
`absence`; raw `promql:`; the drift WARN for hand-written policies; `render_dynatrace`.

## 7. Phases — Design ✔ → Docs → Tests (RED) → Implement → Refactor

### Wave 0 — go/no-go spikes, before any code
- **0a ✔ DONE.** `histogram_quantile` works for GoFr and Cloud Run in GMP; the memory metric
  name is confirmed.
- **0b ✔ Gap explained.** RealmID's soak re-check (~09-26) gates GoFr rules from ticket to page.
- **0b2 ✔ DONE.** `silent_while_serving` fires on history and is empty now.
- **0c ⏳ Nested `./` resolution.**
  - Method: push a throwaway branch here with a called workflow that `uses: ./…` another, and
    call it from a real consumer repo (the 2026-09-15 method).
  - Result picks design (A) or (B); both are pre-written above.
  - Owner OK is needed to run a probe workflow in a consumer repo.
- **0d ⏳ OIDC `job_workflow_sha`.** Confirm it appears in the token of a called workflow, and
  step-test the JWT decode.
- **0e ⏳ `logging.configWriter`.** Settled by the first realm-id apply. Traide's config comment
  says `logging.notificationRules.create` is needed; RealmID's schema read says it isn't.

### Wave 1 — documentation
- `docs/alertspec.md`: format, precedence, units, kinds, guards, escape hatch, portability matrix
  (GMP / PrometheusRule / DQL), catalog semver.
- `docs/service-alerts.md`: contract, caller example, IAM and permissions, `dry_run`, managed
  update, **migrating from hand-written policies** (parity check, then delete).
- Catalog table: `scripts/gen_alert_catalog.py --check` in CI.
- Updates to README, AGENTS §2/§4 (id-token trap), and the docs for `bootstrap-alerts` and
  `validate-alerts`.

### Wave 2 — tests, confirmed RED (`tests/run_alertgen_tests.py`, standalone runner style)
- **Spec:**
  - unknown id and bare-number duration are errors;
  - unit conversions: `5s`→5000 (Cloud Run ms), `2s`→2 (GoFr s), `500ms`→500 (SQL ms),
    `50ms`→50000 (Redis µs);
  - precedence, service grouping, disabled rules;
  - custom-rule validation; `promql:` rejected where unsupported.
- **Golden files** per pack for GMP JSON and PrometheusRule. They assert `by` sets are equal
  across `and`, and that labels match `[a-z0-9_-]{1,63}`.
- **`promtool test rules`** on synthetic series: 0/0, 3 requests, and 100 requests with 10% 5xx.
  Also silent-while-serving with one side missing. This is the semantic oracle; promtool is
  SHA-pinned in CI.
- **Conformance:** every rendered GMP policy passes the *shipped* validate-alerts lint body
  (`extract_step`).
- **Step tests** with gcloud and curl stubs:
  - dry_run writes nothing;
  - managed update by hash;
  - a displayName collision errors;
  - the artifact input;
  - the render job's data check (empty → CANNOT-VERIFY);
  - the JWT sha decode.

### Wave 3 — implement (dispatcher waves, one owner per file)
- **builder A:** `alerting/**`, `tests/run_alertgen_tests.py`, fixtures,
  `scripts/gen_alert_catalog.py`.
- **builder B:** `bootstrap-alerts.yml`, `validate-alerts.yml`, their docs, and the
  `run_step_tests.py` sections.
- **then builder C:** `service-alerts.yml`, README/AGENTS/`catalog.json`, `ci.yml` wiring
  (promtool and the new runner).
- **critic:** adversarial review of rendered policies before merge. Would each page wake someone
  for a real reason? Are the units and guards right?
- **Rule for every brief:** never `git checkout/restore/stash/reset/clean`; commit a `wip/`
  checkpoint before dispatch.

### Wave 4 — rollout (each step owner-gated)
1. PRs merged. **v2.10.0 only on explicit ask.** DECISIONS entries in reusable-workflows.
2. infra-provisioning: realm-id `github-rotator` += `monitoring.editor`. Dry-run as the fleet SA,
   then the owner applies.
3. RealmID, in its own session: write `alerts.yaml` as in §4, run with `dry_run`, then apply.
4. Traide and AutoMahn, in their sessions: swap in the packs, run a parity check, then delete
   the MQL/hand-written files.

## 8. Verification
- **Local:** `run_alertgen_tests.py`, `run_step_tests.py`, `promtool test rules`,
  `gen_*_catalog --check`, `actionlint`.
- **Live, read-only:** every un-thresholded expression returns ≥1 series on realm-id. The
  thresholded expressions run through validate-alerts layer 2.
- **First apply:** `dry_run` on realm-id, then a real apply. Read each policy back from the API.
- **Fire test:** a throwaway override (e.g. `cloudrun.latency_p95 > 1ms`). The email arrives,
  then revert. That proves the far end, not just the config.

## 9. Open risks
- **GoFr metric reliability degrades with revision age (gofr#4266).** `silent_while_serving` is
  the backstop. GoFr rules ticket until the soak passes.
- **GoFr counters may undercount on scale-to-zero** (INFERRED: `rate` needs two samples per
  instance). So Cloud Run is the default paging source for low-traffic services.
- **Traffic-based rules detect a hurt user, not a broken idle service.** Only a DB-aware probe
  closes that gap (deferred; RealmID tracks it).
- **Cloud Monitoring pricing is per condition and per series scanned** (UNVERIFIED current
  numbers). Grouping keeps conditions ≈ rules.
