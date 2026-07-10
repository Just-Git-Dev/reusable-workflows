# Decisions — reusable-workflows

## 2026-07-10 — `sync-bundle-key`: never disable a version a live service still reads

Bug fix. RCA below.

**Symptom.** A rotation run finishes green, with a `::warning::Failed to update
<service>` buried in the log. The service keeps serving from the *previous*
bundle version — which the same run then disabled. Nothing breaks until that
container next restarts or scales out, at which point Cloud Run cannot mount the
secret and the revision fails to come up. The failure surfaces far from the run
that caused it.

**Root cause.** The workflow performed a two-phase change (roll every service
onto `:latest`, then retire the old version) without making phase 2 conditional
on phase 1. Concretely, the roll swallowed its own failure:

```
gcloud run services update "$svc" ... || echo "::warning::Failed to update $svc"
```

and the retire step ran regardless, guarded only on "an old version existed":

```
if: steps.cur.outputs.current_version != ''
run: gcloud secrets versions disable ... || true
```

The originating mistake is treating a partial rollout as an acceptable outcome.
`|| echo` converts a hard failure into a log line, and `|| true` then suppresses
the one signal that would have caught the inconsistency.

**Why it wasn't caught.** No test exercises the failure path — a failed
`services update` needs a service that exists but rejects the update (wrong
region, missing IAM, bad mount path), which the happy-path runs never produce.
The step summary reported the old version as "(disabled)" unconditionally, so
the artifact a human reviews after a run *asserted* the very thing that had gone
wrong. And a green check on a rotation workflow is exactly the kind of thing
nobody re-reads.

**Fix.** The roll step now collects failures and exits non-zero. Because a later
step's `if:` implies `success()`, the disable step is simply never reached on a
partial rollout, and the old version stays **enabled** — the safe state, since
services on it keep working and a re-run retires it once every service rolls.
The disable step also drops its `|| true`: if retiring the old version fails,
that is a real error worth seeing. The ordering guarantee is stated in the
workflow header and in `docs/sync-bundle-key.md`, so it is a contract rather
than an implementation detail. A `dry_run` input was added — this was the only
destructive workflow without one.

**Prevention.**
- The invariant is now written down where a future editor will see it before
  reordering the steps.
- `actionlint` + `shellcheck` run in CI, which flags newly-introduced
  unconditional `|| true` on a command whose result is load-bearing.
- Wider lesson applied across the repo: an explicit `|| echo` / `|| true` on a
  mutating command is the thing to audit. GitHub's default `run:` shell is
  already `bash -e`, so bare commands *do* fail the step — it is only the
  explicit swallows (and masked pipe failures, `pipefail` being off by default)
  that let a broken run go green.

## 2026-07-01 — Create shared cross-org reusable-workflows host

**Problem.** AutoMahn, Realm-ID and Traide-Co each run the same infra stack and
had near-verbatim copies of the same ops workflows (secret rotation, monitoring
bootstrap, DB backup, GAR cleanup, CF-token nag). Fixes had to be applied 2–3×
and drifted (auth action `@v2` vs `@v3`, `FILE_STORE_*` vs `FILE_STORAGE_*` key
names, `GCP_ROTATOR_SA` vs `GCP_INFRA_SA`).

**Decision.** Host `workflow_call` reusable workflows in `Just-Git-Dev`,
consumed by all three orgs. First pass = the 5 STRONG-verdict workflows only:
`bootstrap-alerts`, `sync-bundle-key` (db/redis + r2), `neon-backup`,
`cleanup-gar-images`, `rotate-cloudflare-token`.

**Key trade-offs.**
- **Public repo (forced).** All three orgs are GitHub Free with no shared
  enterprise; GitHub forbids cross-org use of a *private* reusable-workflow repo.
  So the host repo is public. No secrets are committed (callers pass them), but
  infra topology becomes public. Accepted as the only way to get true `workflow_call`
  reuse without paying for an enterprise. Alternative (private + a sync-copy
  workflow) was rejected — it isn't real reuse and copies drift.
- **No `secrets: inherit`.** Cross-org callers must pass each secret explicitly.
- **WIF provider + SA as inputs, not secrets.** They are resource identifiers,
  not credentials; passing them as inputs erases the per-org SA var-name drift.
- **Callers pin to a release tag (`@v1`), never `@main`** — a change here can't
  silently mutate every org's ops until the tag is bumped.
- **`sync-bundle-key` takes a JSON payload** whose keys are the *destination*
  bundle keys — one workflow covers both db/redis and r2 and both orgs' naming
  drift with zero branches.
- **`cleanup-gar-images` standardized on AutoMahn's version** — it protects
  digests referenced by live Cloud Run Services *and* Jobs; Realm-ID's prior
  version had no such protection (a strictly weaker subset). Realm-ID gains the
  safety net.
- **`neon-backup` merges both orgs' extras** — AutoMahn's sha256 MANIFEST +
  Traide's integrity/sanity checks — behind a `dump_format` input (custom | plain-gz).

**Out of first pass (kept per-repo).** Backend Cloud Run deploys (AutoMahn/api
is an ADR-045 3-target build; image-service is Python; Traide uses
`release:published`), all `lint.yml`/`ci.yml`/`release.yml` (same filename,
different jobs), single-org rotations (`rotate-jwt-keys`, `rotate-signing-secret`,
`rotate-api-key`), and the CF-Pages deploy family (deferred to pass 2).

**Rollout.** Phase 1 = `bootstrap-alerts` end-to-end (idempotent, safest) to
validate the pattern, then cleanup-gar (dry-run first) → neon-backup →
sync-bundle-key (mutates live SM, do last) → rotate-cloudflare-token. Old
workflow kept one cycle, deleted after one green real run.
