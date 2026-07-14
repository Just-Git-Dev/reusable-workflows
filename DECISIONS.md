# Decisions — reusable-workflows

## 2026-07-14 — Capability parity with `zopsmart/workflows`, verified from live callers (v1.4.0)

**Problem.** The v1.3.0 `deploy-gke-service` migration note claimed the external
system did "multi-registry resolution, language auto-detection, host-side builds
and a ConfigMap-diff apply" — a list written from memory, and partly wrong
(`ConfigMap-diff` is not a diff; it is git-change-routing + generate-from-env +
`kubectl apply --force`). "Don't reduce capabilities" needed a *verified* answer,
not a remembered one.

**What I actually verified.** Read the `zopsmart/workflows` source (the composite
actions + `_*.yaml` bodies) and the `with:` blocks of its live callers
(`quizzing-pro/{api,ui,engine,admin-ui}`, `zopsmart/{skillup-ui,auth-service-v2,
hiring-portal-api,…}`). Findings:

- **Not used by any caller → dropping them is correct, not a regression.**
  Multi-registry (every caller → `us-central1-docker.pkg.dev`, GAR), multi-cloud
  EKS/AKS (every caller → `CLUSTER_PROJECT`, GKE), language auto-detect (every
  caller passes `LANGUAGE:` explicitly).
- **Used, and genuinely missing from JGD.** (1) **Stage→prod retag/promote** —
  `stage-deploy` builds `:sha`, `prod-deploy` retags `:sha`→`:release` with *no
  build*. JGD's deploy-* always rebuild → a real correctness gap (prod could
  differ from stage). (2) DB **service containers** + **coverage threshold** in
  CI (`MYSQL_ENABLE`/`REDIS_ENABLE`/`TESTCOVERAGE_THRESHOLD`).
- **Used, but a deliberate improvement to keep.** SA-JSON creds
  (`PROD_DEPLOY_KEY`) → keyless WIF.

**Decision.** Ship four additive changes as **v1.4.0**:

1. **`promote-image`** — server-side retag (`gcloud container images add-tag`, no
   pull/push) + optional roll of GKE (kubectl/helm) or Cloud Run. Keyless WIF.
   The JGD equivalent of zopsmart `prod-deploy`; guarantees prod runs stage's bytes.
2. **`deploy-cluster-keyed`** — the one place multi-cloud (GKE/EKS/AKS/kubeconfig)
   **and** multi-registry (gar/gcr/ecr/acr/ghcr/dockerhub/custom) live, **key-based
   by design**. Explicitly separated from the WIF-native deploy-* so the keyless
   path never regresses to stored keys. Auth is CLI-based (gcloud/aws/az/docker)
   except GKE, which uses the SHA-pinned Google actions for the auth plugin.
3. **`ci-go` + `ci-node`: `enable_services`** (postgres+mysql+redis service
   containers, run in a second `*-db` job — GitHub can't attach a service
   conditionally to one job) **+ `coverage_threshold`** on `ci-go`. Service
   containers are language-agnostic, so both CI workflows get them.
4. Doc corrections: the `ConfigMap-diff` mislabel, a stale
   `configmap_from_env_file` reference in `deploy-gke-service.yml`, and
   unverified `zop-mannai`/`geo-engine` caller names (the real callers are
   `zopsmart/*` + `quizzing-pro/*`).

**Why key-based multi-cloud is a *separate* workflow, not a mode on deploy-gke.**
Folding EKS/AKS + stored keys into the WIF-native workflow would blur its one
guarantee (keyless). A caller reaching for `deploy-cluster-keyed` is opting into a
long-lived credential explicitly; the split makes that visible and rotatable, and
keeps the recommended path (`deploy-cloud-run`/`deploy-gke-service`) keyless.

**Config on GKE — deferred, not solved.** Callers keep config in a git
`.env`→ConfigMap; JGD's model is Secret-Manager bundles. On GKE (unlike Cloud
Run's `--set-secrets`) a bundle needs an in-cluster mechanism (External Secrets
Operator / initContainer). Documented as a per-caller migration decision; no new
reusable. Chosen over porting the ConfigMap flow to avoid running two config
models.

**Not done here.** Caller migrations remain per-repo PRs (user-driven, one at a
time). `promote-image` for Cloud Run overlaps `deploy-cloud-run --update-image`
but skips the rebuild — kept distinct on purpose.

**Release.** All additive → **v1.4.0** (minor). `actionlint` + the SHA-pin grep
pass locally; no new third-party action SHAs were introduced (auth is CLI or
reuses already-pinned Google/Docker/Azure actions).

## 2026-07-14 — Fleet-wide audit; reverse the "deploy/CI kept per-repo" call

**Problem.** A one-time survey of every workflow across all 16 accessible orgs
(379 repos → ~60 with workflows; full findings in
[docs/convergence-audit.md](docs/convergence-audit.md)) showed that the two
*most*-duplicated workflows are the two this library deliberately left out in the
first pass: **Cloud-Run deploy** and **language CI**. ~13 repos hand-roll CI and
~7 hand-roll a deploy, sharing no code. Separately, RevvUp-AI and quizzing-pro
deploy through **`zopsmart/workflows@main`** — an external org, a mutable ref that
mints cloud creds and pushes images.

**Decision.** Reverse the first-pass exclusion. Build, in reach × safety order:
`ci-go`, `ci-node`, `deploy-cloud-run`, `deploy-gke-service`, then the long tail
(`bootstrap-cf`, `deploy-cloudflare-worker`, `cloud-run-update`, `run-db-job`).
The **stated goal is to let platform app repos drop `zopsmart/workflows`
entirely**, which is what puts a GKE service-deploy reusable in-scope here even
though this library is otherwise Cloud-Run-centric.

**Why the first pass was right *then* and wrong *now*.** The original call
("backend Cloud Run deploys too divergent; ci/lint/release same filename but
different jobs") was correct for a 5-workflow library proving a pattern. The
audit shows the divergence is mostly **surface** (build target, language,
service name) and cleanly parameterizable; the cost of *not* converging is real —
duplicated deploy logic is where the failing runs and the un-pinned, un-`pipefail`
`run:` blocks concentrate.

**Constraints carried forward.** Every new reusable keeps the house rules:
`workflow_call` inputs for all project-specific values, no `secrets: inherit`,
WIF provider + SA as inputs, SHA-pinned third-party actions, `shell: bash` on
every `run:`, `dry_run` on destructive paths, and a `docs/<name>.md` page. CI
enforcement (`actionlint` + the SHA-pin grep) applies to the new files.

**Adoption debt found (fix at caller-migration time, not here).** Every live
adopter pins the frozen `@v1` alias (`bootstrap-alerts`, `cleanup-gar-images`,
`neon-backup`/`backup-db`) — repin to `v1.2.0`. `bootstrap-alerts` — the one
workflow with real adoption — is failing 86–100% where used; triage before
promoting it as the template.

**Not converged.** Legacy `zopsmart` (its own platform, separate ownership; the
thing we want callers to *leave*, not fold in), `Zopsmart-HIMS` spec-lint
(already 40→1 in-org, domain-specific), and single-repo publishers (goreleaser,
maven/npm) stay put.

**Release.** `v1.3.0` ships the first four together — `ci-go`, `ci-node`,
`deploy-cloud-run`, `deploy-gke-service` — plus a failure-isolation fix to
`bootstrap-alerts` (a single invalid policy no longer aborts the apply loop; a
new additive `policies_failed` output; the pass/fail contract is unchanged).
All additive → minor bump. The long tail (`bootstrap-cf`,
`deploy-cloudflare-worker`, `cloud-run-update`, `run-db-job`) follows in later
minors. Caller migrations are separate PRs in each app repo, one at a time,
after the tag is cut.

## 2026-07-13 — Add `rotate-signing-keypair` (v1.2.0, with `rotate-worker-signing-secret`)

**Problem.** Reviewing AutoMahn's workflows for reuse candidates surfaced
`rotate-jwt-keys.yml`: a scheduled, bespoke ~125-line workflow that generates an
RS256 keypair + `kid`, writes `JWT_*` into the SM bundle, rolls Cloud Run, and
disables the old version. Same rotation family as `rotate-worker-signing-secret`,
and just as copy-pasted-per-app.

**Decision.** Extract it as `rotate-signing-keypair`, generalised past AutoMahn:
the `JWT_*` destination key names, `rsa_bits`, `services_csv`, and project are all
inputs. Named "signing-keypair" (not "jwt") because it's a generic asymmetric-key
rotation; the JWT-shaped defaults are just defaults.

**Options weighed.**

- *Thin caller of `sync-bundle-key` vs. standalone.* Tempting, since the SM-write +
  Cloud-Run-roll is exactly `sync-bundle-key`'s job and there's no CF/grace/dual-slot
  to interleave (this is why JWT rotation is *simpler* than the HMAC one). Rejected
  anyway, for a security reason specific to key material: the keypair is **generated
  in-workflow**, and a reusable workflow's `outputs` are **not** treated as secrets,
  so generating in a caller job and handing the private key to `sync-bundle-key`
  would print it in logs. Generation and consumption must share one workflow →
  standalone. Cost: ~40 lines of SM/roll logic overlapping `sync-bundle-key`.
- *Grace window?* No. Unlike the HMAC secret, asymmetric JWTs carry a `kid` and
  short-lived tokens churn onto the new key naturally, so the old version is disabled
  as soon as the roll succeeds — matching AutoMahn's original. Documented the
  contraindication: a verifier that caches one key with no `kid` selection, or
  long-lived tokens, must NOT use this (needs the two-slot pattern instead).

**Improvements over AutoMahn's inline version** (beyond the standard conventions —
SHA-pinned actions, `shell: bash`, `dry_run`, `--limit=1` over `| head -1` to
survive pipefail): added the **roll-forward rollback** the HMAC workflow uses
(AutoMahn's JWT one had none, so a failed roll left SM ahead of the running
revisions), and a real `bootstrap` input replacing the derived-from-state flag.
Separately noted for the AutoMahn repo: its inline summary claims *"disabled after
30 min grace"* but there is no grace step — stale text the extraction retires.

**Release.** Additive, and ships together with `rotate-worker-signing-secret` in a
single **v1.2.0** — both are new workflows landing in one PR, and this repo already
bundles additive changes per minor (v1.1.0 shipped `deploy-cloudflare-pages` plus
the de-brand and fixes). Two identical tags one commit apart would be noise. AutoMahn
migration to a thin caller deferred to a follow-up in that repo, alongside the
`rotate-signing-secret` and `rotate-cloudflare-token` migrations (the reusable
CF-token workflow already exists at v1.1.0 and is a superset of AutoMahn's inline
copy, which still carries the `curl -f` error-body-swallow bug the reusable one fixed).

## 2026-07-13 — Add `rotate-worker-signing-secret` (v1.2.0)

**Problem.** Rotating an HMAC signing secret shared between a Cloudflare Worker
(which *verifies* signed URLs) and a Cloud Run backend (which *signs* them from an
SM bundle) is a real ops task — AutoMahn does it quarterly for its `files-cdn`
Worker fronting R2 — but it lived as a bespoke ~200-line inline workflow in the app
repo. Every other app with a Worker-signed-URL scheme would have to re-derive the
same zero-downtime dance and the same two hard-won failure modes.

**Decision.** Extract it into a reusable `workflow_call` workflow, generalised past
R2: the mechanism (generate → SM bundle write + Cloud Run roll → Worker two-slot
push → grace → cleanup) is object-storage-agnostic, so it is named
`rotate-worker-signing-secret`, not `rotate-r2-*`. Verified the contract against
the consumer before extracting — `automahn-files-cdn`'s Worker verifies PRIMARY
then falls back to PREVIOUS, and the signed-URL TTL is 10 min (`files.go`), which
the 900s grace default clears.

**Options weighed.**

- *Compose on `sync-bundle-key` vs. standalone.* The SM-write + Cloud-Run-roll
  overlaps `sync-bundle-key` almost exactly, so nesting was tempting. Rejected:
  the Worker `PREVIOUS` push, the grace sleep, the **delayed** disable (after grace,
  not right after the roll), and the roll-forward rollback all interleave *around*
  that write. Delegating it would force the CF push before the sub-call and the
  grace/disable after, contorting the ordering `sync-bundle-key`'s own contract
  guarantees. Chose standalone; the cost is ~40 duplicated lines of SM/roll logic.
- *Keep AutoMahn's bootstrap tolerance vs. require the bundle to pre-exist
  (`sync-bundle-key`'s stance).* Kept it, as a `bootstrap` input (default `false`):
  when true, a missing bundle / missing services degrade to warnings and grace +
  disable are skipped, so first-run setup doesn't block. Scheduled rotations run
  with `bootstrap: false`.

**Preserved verbatim from AutoMahn's inline version (both learned in production):**

- **CF calls capture status + body, never `curl -f`** — `-f` swallowed
  Cloudflare's JSON error body, so a 403 surfaced with no error code (AutoMahn run
  28499686263).
- **Rollback is roll-forward, not disable-`latest`** — `latest` tracks the highest
  version number, so disabling it strands `access latest` and Cloud Run's `:latest`
  mount (AutoMahn run 28500860707). Revert by adding a fresh version with the prior
  content, then disabling the bad one. And it fires *only* when the Cloud Run roll
  didn't succeed — reverting after the signer has moved would break signing.

**Conventions applied on the way in** (differ from the app-repo original): the two
`google-github-actions` actions are SHA-pinned (CI rejects tag refs), `shell: bash`
via `defaults.run`, and a `dry_run` input like every destructive workflow here.

**Release.** Additive (new workflow, no change to existing contracts) → minor bump,
**v1.2.0**. Migrating AutoMahn's inline workflow to a thin caller is deliberately
deferred to a follow-up in that repo.

## 2026-07-10 — Make the library genuinely public: de-brand, harden, release properly

**Problem.** The repo was public because GitHub forces it (cross-org
`workflow_call` requires a public host), but it read like an internal repo that
happened to be world-readable. Consumer names and project ids were baked into
workflow bodies, input descriptions, and every doc example. Separately, an audit
turned up defects that only matter once other people depend on these workflows.

**Decision.** Treat the repo as a library with external users. Three groups of
change:

### 1. De-branding

Every consumer-specific identifier (org names, GCP project ids, DNS zones,
service names, artifact prefixes) is gone from workflow bodies, `description:`
strings and docs. All of it was already an input or trivially became one; the
docs now use `my-gcp-project` / `example.com` placeholders. `neon-backup.yml`
keeps its filename to avoid breaking existing callers, but nothing in it is
Neon-specific — that is stated in its docs page.

New inputs added purely to remove hard-coded assumptions: `channel_file` and
`policy_glob` (bootstrap-alerts); `password_key` and `pg_major` (neon-backup);
`keep_tags`, `keep_tag_prefixes` (cleanup-gar-images); `node_cache`,
`cache_dependency_path` (deploy-cloudflare-pages).

### 2. Correctness

- **`sync-bundle-key` rollout atomicity** — see the separate entry below; it
  landed on its own so the destructive path could be reviewed in isolation.

- **`neon-backup` ignored `gzip` failures.** The `plain-gz` path checked
  `PIPESTATUS[0]` (`pg_dump`) and never `PIPESTATUS[1]` (`gzip`), so a truncated
  or failed compression produced a green run and a corrupt artifact. Both stages
  are now asserted. The `custom` path recorded `rc=$?` after a command that
  errexit had already aborted on, so `dump.log` was never printed on failure;
  errexit is now disabled around the dump so the Postgres error is always shown.

- **`bootstrap-alerts` could write an empty notification channel into every
  policy.** If `channels create` exited 0 but printed nothing, the empty
  `CHANNEL_NAME` was `sed` into all of them. It now fails instead. The policy
  glob runs under `nullglob` and fails on zero matches, rather than looping once
  over a literal `policy-*.yaml` filename.

- **`deploy-cloudflare-pages` never worked as a reusable workflow.** An input
  `description:` embedded a live `${{ vars.CLOUDFLARE_ACCOUNT_ID }}` expression.
  `vars` is not a valid context there, so the called workflow fails to parse and
  every caller startup-fails at 0s. `actionlint` rejects it outright ("context
  `vars` is not allowed here"), and at least one consumer had already given up
  and vendored a private copy of the workflow rather than call it. Removing the
  expression is what makes this workflow adoptable at all — which, together with
  the fact that it was never included in a release tag, explains why it had zero
  callers.

- **`pipefail` and `head -1`.** GitHub's implicit `run:` shell on Linux is
  `bash -e {0}` — errexit **on**, pipefail **off**. So "missing `set -e`" was
  never the defect; masked pipe failures were. Every job now sets
  `shell: bash` (which yields `-eo pipefail`). Turning pipefail on makes
  `gcloud ... | head -1` newly dangerous — `head` closing the pipe can SIGPIPE
  `gcloud` — so those became `--limit=1`, and `grep|head|cut` chains became
  single-process `awk`.

### 3. Supply chain and contract

- **All third-party actions are pinned to full commit SHAs** with the version in
  a trailing comment. These jobs mint GCP credentials via WIF, hold a Cloudflare
  Pages-Edit token, and produce PII-bearing database dumps; a mutable tag is a
  standing supply-chain risk. Dependabot bumps the SHA and the comment together,
  so the pin costs no maintenance. A CI job rejects any non-SHA `uses:` ref.
- **A CI workflow** runs `actionlint` (and `shellcheck` over every `run:` body).
  A syntax error here ships straight into a consumer's production ops run.
- **`concurrency:` on all six.** Only `sync-bundle-key` had one. It matters most
  for `cleanup-gar-images`, whose deletions run under `xargs -P 8` and could
  race a scheduled sweep against a delete-set computed before it started.
- **`outputs:` on all six.** None declared any, so callers could not chain — the
  new bundle version, artifact name, and deployment URL were all computed and
  discarded.
- **Every input has a `description:`** (22 were missing). Numeric-looking inputs
  deliberately stay `type: string` — see the trade-off below.
- **Caller-controlled strings move out of `run:` bodies into `env:`**
  (`build_command`, `reason`, `title`). A `${{ }}` value interpolated into a
  script body is a script-injection seam; via `env:` it is inert data.

**Key trade-offs.**

- **`cleanup-gar-images` now keeps `buildcache` by default.** A BuildKit
  registry cache (`cache-to: type=registry,ref=...:buildcache`) is an ordinary
  tagged image in the same repo. Without this, a repo going 30 days without a
  release has its build cache age-deleted and the next build is a cold rebuild.
  The keep-set is now `keep_tags` + `keep_tag_prefixes` inputs rather than a
  hard-coded tuple.

- **No `gcp-wif-auth` composite action, for now.** The WIF-auth + `setup-gcloud`
  pair is duplicated across four workflows and extracting it was tempting. But
  GitHub's documentation does not specify whether a relative `uses: ./...` inside
  a *reusable* workflow resolves against the caller's checkout or against this
  repo — and getting it wrong breaks every consumer. A fully-qualified
  self-reference (`Just-Git-Dev/reusable-workflows/.github/actions/...@vX`) would
  work but couples the workflow to a tag that does not exist until release time.
  Since Dependabot updates all four SHA pins in one PR, the duplication costs
  little. Revisit if the pair grows beyond two steps.

- **Numeric-looking inputs stay `type: string`.** Retyping `keep_semver_count`,
  `untagged_max_age_days`, `tagged_max_age_days`, `db_port`, `retention_days`
  to `type: number` was drafted and then reverted. In GitHub Actions, both
  `${{ vars.X }}` and `${{ needs.job.outputs.Y }}` are **always strings**, so a
  `number` input cannot be fed from a repo variable or an upstream job output —
  the two most natural ways to configure a reusable workflow. Existing callers
  do exactly that (`keep_semver_count: '5'`, `db_port: ${{ vars.DB_PORT }}`,
  `tagged_max_age_days: ${{ needs.resolve.outputs.tagged }}`), so the change
  would have broken them for a cosmetic gain. `number` is a reasonable type for
  a `workflow_dispatch` input, where a human fills the box; it is a trap on
  `workflow_call`. The shell and Python already coerce, and the values are
  range-checked where it matters.

- **`v1` is frozen, not moved. Releases are immutable.** The old README told
  callers to pin `@v1` while `v1` was a single movable lightweight tag — and
  `deploy-cloudflare-pages.yml` did not exist at `v1` at all, so every caller
  following the README got a 404.

  The tempting fix was to move `v1` onto the new release, handing all eight
  existing callers the fixes for free. Rejected: `sync-bundle-key` now **fails** a
  rotation whose Cloud Run rollout previously only warned, so moving `v1` would
  turn a green scheduled workflow red in repos whose owners never approved a
  change. Correct behaviour, but it should arrive as a reviewed commit in each
  caller, not as a surprise. So `v1` stays pinned at the first release as a legacy
  alias, releases are immutable `vX.Y.Z` tags, and callers migrate to `@v1.1.0`
  deliberately.

- **Region default `asia-southeast1` is retained.** It encodes one deployment's
  choice, but changing a default silently changes behaviour for any caller that
  omits the input. It is a candidate for `required: true` in a v2.

**Settings, not commits.** `main` was unprotected (`"protected": false`) despite
CODEOWNERS. It is now protected: pull request required, one approving review,
both CI checks required, force-push and deletion blocked. Releases are cut from
`main`, so an unreviewed push was the one path that could change ops behaviour
for every consumer at once.

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

**Problem.** Several sibling organisations ran the same infra stack (Cloud Run +
Postgres + Cloudflare, WIF auth, a Secret Manager config bundle) and each held
near-verbatim copies of the same ops workflows: secret rotation, monitoring
bootstrap, DB backup, image cleanup, CF-token nag. Every fix had to be applied
two or three times, and the copies drifted — the auth action pinned `@v2` in one
place and `@v3` in another, different bundle key names for the same credential,
different variable names for the same service account.

**Decision.** Host `workflow_call` reusable workflows in one repo, consumed by
all of them. First pass = the five workflows whose logic was genuinely identical:
`bootstrap-alerts`, `sync-bundle-key`, `neon-backup`, `cleanup-gar-images`,
`rotate-cloudflare-token`.

**Key trade-offs.**
- **Public repo (forced).** The consuming orgs are on GitHub Free with no shared
  enterprise, and GitHub forbids cross-org use of a *private* reusable-workflow
  repo. So the host repo is public. No secrets are committed (callers pass them
  at call time). Accepted as the only way to get real `workflow_call` reuse
  without an enterprise plan. The alternative — a private repo plus a sync-copy
  workflow — was rejected: it isn't reuse, and copies drift.
- **No `secrets: inherit`.** Cross-org callers must pass each secret explicitly.
- **WIF provider + SA as inputs, not secrets.** They are resource identifiers,
  not credentials. Passing them as inputs also erases the per-org variable-name
  drift.
- **Callers pin to a release tag, never `@main`** — a change here can't silently
  mutate anyone's ops until they bump the tag.
- **`sync-bundle-key` takes a JSON payload** whose keys are the *destination*
  bundle keys, so one workflow covers every rotation and every naming convention
  with zero branches.
- **`cleanup-gar-images` standardised on the safest existing implementation** —
  the one that protects digests referenced by live Cloud Run Services *and*
  Jobs. The others had no such protection (a strictly weaker subset), so every
  consumer gains the safety net.
- **`neon-backup` merges both prior variants' extras** — the sha256 MANIFEST
  from one and the integrity/sanity checks from the other — behind a
  `dump_format` input (`custom` | `plain-gz`).

**Out of first pass (kept per-repo).** Backend Cloud Run deploys (too divergent:
different build targets, languages, and triggers), the `lint`/`ci`/`release`
workflows (same filename, entirely different jobs), single-consumer rotations,
and the Cloudflare Pages deploy family (deferred to pass 2; landed later).

**Rollout.** Phase 1 = `bootstrap-alerts` end-to-end (idempotent, safest) to
validate the pattern, then `cleanup-gar-images` (dry-run first) → `neon-backup`
→ `sync-bundle-key` (mutates live Secret Manager, so last) →
`rotate-cloudflare-token`. Each old workflow was kept one cycle and deleted after
one green real run.
