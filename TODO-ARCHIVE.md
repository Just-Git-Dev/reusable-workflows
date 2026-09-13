# TODO archive — reusable-workflows

Fully-closed sections moved out of `TODO.md` on 2026-09-13. Same log, split by
state only — both files are greppable. Nothing here is open work.

## Index

- [`validate-alerts` executes MQL only — ✅ DONE 2026-09-01 (opened and closed same day)](#validate-alerts-executes-mql-only---done-2026-09-01-opened-and-closed-same-day) — 2 closed
- [Fallout from immutable-tag enforcement (opened 2026-08-12, v2.1.1)](#fallout-from-immutable-tag-enforcement-opened-2026-08-12-v211) — 5 closed
- [`DECISIONS.md` index anchors (found 2026-09-13)](#decisionsmd-index-anchors-found-2026-09-13) — 2 closed

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
      repinned to `@v2.1.2` across 6 repos (Realm-ID/{issuer, ui, project},
      Traide-Co/{project, website, webapp}), all merged. `fleet_drift.py` now reports
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
