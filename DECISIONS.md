# Decisions — reusable-workflows

> **Release note (2026-07-15): the entries below dated 2026-07-15 all ship in a single
> tag, `v1.11.0`.** Nothing was tagged between `v1.7.0` and this release. The per-phase
> version numbers in the individual entries (`v1.8.0` rollback-service, `v1.9.0`
> live-commit stamping, `v1.10.0` prod forward-only, `v1.11.0` stage forward-only) are
> **logical phase markers**, not separate published tags — they were developed in
> sequence and cut together as `v1.11.0`, which also folds in the `ci-go` secret-rename
> fix. Intermediate numbers `v1.8.0`–`v1.10.0` are intentionally skipped in the tag
> series.

## 2026-07-15 — `ci-go` secret renamed `github_token` → `go_private_token` (bug fix)

**Symptom.** The quizzing-pro migration PR (#2041) pinning `ci-go.yml@v1.7.0` failed
to load with *"secret name `github_token` within `workflow_call` can not be used since
it would collide with system reserved name."* — a **parse-time** rejection, so v1.7.0
was un-callable by anyone, not just that repo.

**Root cause.** GitHub reserves `github_token`/`GITHUB_TOKEN` (case-insensitive) as a
secret name inside `workflow_call` — the auto-injected `secrets.GITHUB_TOKEN` owns it.
Declaring a same-named `secrets:` entry is invalid. We named the private-modules token
`github_token` out of habit; it can't be that name.

**Why it wasn't caught.** `actionlint` does not flag the reserved-name collision (it
lints syntax/shell, not this GitHub-side rule), and we had no caller exercising
`go_private` end-to-end before publishing v1.7.0 — the collision only surfaces when a
caller actually invokes the reusable.

**Fix.** Renamed the secret to `go_private_token` (both `secrets.` references + input
description + error text), with an inline comment on the `secrets:` block warning off
the reserved name. Updated `docs/ci-go.md` (secret name + a note + the
`secrets: { go_private_token: ${{ secrets.GITHUB_TOKEN }} }` caller snippet).

**Prevention.** Doc note + code comment record the rule at the collision site. Callers
map their own `GITHUB_TOKEN` (or a cross-repo PAT) into `go_private_token`.

**Contract change, but the broken workflow was un-callable.** The secret name is part
of the input contract, so it needs a fresh tag. The `github_token` secret was
introduced in **v1.6.0** and still present in **v1.7.0** — both are DOA (any caller of
`ci-go` at those tags hits the parse error), so no *working* caller depends on the old
name and this is a **fix, not a break** (no major bump). It ships in the single
**v1.11.0** release cut this session (see the reconciling note at the top of this file).
quizzing-pro/api #2041 re-pins `ci-go` to `@v1.11.0` and renames its `secrets:` key
`github_token` → `go_private_token` (value stays `${{ secrets.PAT }}`).

## 2026-07-15 — forward-only extended to the stage build workflows (opt-in)

**Lifted the forward-only guard onto `deploy-cloud-run` + `deploy-gke-service`** so
stage rejects out-of-order deploys too, not just prod. Same opt-in
`enforce_forward_only`, same "block iff behind" rule, same fail-closed. On the stage
workflows the guard runs **before the build** (it needs only `github.token` + the
checked-out commit), so a blocked deploy wastes no build.

**Why the rule works unchanged on the shared stage env.** "Block iff `behind`"
permits `diverged` — and a `main` squash commit is `diverged` (not `behind`) versus a
`development` tip. So the intentional stage lineage switch (development-tip →
release-candidate) passes, while an actual older/replayed commit is blocked. The
single rule covers stage and prod without a per-env mode, as the model predicted.

**Duplicated the guard step; did NOT extract a composite action — verified, not
assumed.** A `./` local composite action referenced from a *reusable* workflow
resolves against the **caller's** checkout, not the workflow's own repo (confirmed:
GitHub community discussions [#18601](https://github.com/orgs/community/discussions/18601),
[#25289](https://github.com/orgs/community/discussions/25289)). The workarounds
(have every caller check out *our* repo + supply a token, or self-reference by full
`owner/repo/...@sha`) push fragility onto cross-org consumers — the opposite of this
library's contract. So the ~30-line guard is duplicated across the three workflows,
each staying self-contained and independently consumable. Cost: three copies to keep
in sync — the core logic (baseline lookup → compare → block iff behind → fail closed)
is identical; they differ only in the `HEAD` source (`commit_sha`/`github.sha` on
promote, the built `git rev-parse HEAD` on the deploys) and the "release" vs "deploy"
wording.

**Additive/opt-in → v1.11.0.**

## 2026-07-15 — forward-only guard on `promote-image` (phase 3; opt-in)

**Shipped the forward-only guard** — `promote-image` can now reject an out-of-order
(older) release. Completes the three-phase plan (rollback → stamping → guard).
Opt-in via `enforce_forward_only` (default off — runs in others' prod).

**Live-commit source = latest successful GitHub Deployment for the env, not the
running service.** Both were options (the service label/annotation is ground-truth
for what's running). Chose the Deployment record because it is **auth-agnostic** —
read with `github.token`, no cloud auth — so the guard runs *first* and *fails
fast*, before the WIF/key auth and the retag. Reading the live commit off the
service would need cloud auth active before the guard, which the key-based path only
sets up right before the roll (ordering headache). Trade-off accepted: the record
can drift from reality if someone deploys fully out-of-band — but out-of-band deploys
are already against policy, and phase-2 stamping keeps the record in lock-step with
every sanctioned roll.

**Rule = "block iff `behind`."** Compare `live...candidate` via the GitHub compare
API; block only `behind` (candidate is an ancestor of live). `ahead`/`identical`/
`diverged` pass. One rule gives strict latest-only on prod (linear `main` never
diverges) *and* permits a stage lineage switch (a `main` squash is `diverged` vs a
`development` tip, not `behind`) — the same simplification the model called for. No
baseline (first release) ⇒ allow.

**Fails closed.** A compare API error / unknown commit **blocks** rather than
allowing — a safety guard must not wave a release through on a transient error.
Operationally the escape hatch is a re-run or `enforce_forward_only: false`. Chose
fail-closed over fail-open because a silent backward prod deploy is worse than a
blocked release.

**Concurrency re-keyed to per-env** (`deploy-<proj>-<image>-<environment>`, matching
`rollback-service`) so a promote and a rollback for one env can't race — the gap
flagged when `rollback-service` shipped. Falls back to the legacy per-`target_tag`
key when `environment` is empty, so **existing callers are unchanged**.

**Additive/opt-in → v1.10.0.** No behaviour change unless a caller sets
`enforce_forward_only` (and, for the concurrency change, `environment`).

## 2026-07-15 — live-commit stamping across deploy/promote (phase 2 of the release-process plan)

**Shipped stamping in `deploy-cloud-run`, `deploy-gke-service`, `promote-image`** —
the prerequisite for the forward-only guard (phase 3), which needs to read back
"what commit is live" per environment. Each roll now stamps the source commit and,
opt-in, records a GitHub Deployment (the "both" recording choice, matching
`rollback-service`).

- **What is stamped.** Cloud Run → resource label `jgd_commit=<sha>` (label keys are
  slash-free, so no `jgd.dev/…`); GKE (kubectl path) → annotation
  `jgd.dev/commit=<sha>` (annotations allow slashes + arbitrary values). Helm path:
  no annotation (resource name isn't knowable generically) — relies on the
  Deployment record. `commit` is `git rev-parse HEAD` post-checkout for the build
  workflows (the exact built commit, honouring `checkout_ref`), and
  `commit_sha`/`github.sha` for `promote-image` (no checkout there).
- **GitHub Deployment is opt-in via `environment`, and best-effort.** The step only
  fires when `environment != ''`, so **existing callers are untouched** (no new
  required input, no noise). It is wrapped so a Deployments API failure (e.g. the
  caller didn't grant `deployments: write`) **warns but never fails the deploy** —
  the roll already happened; an audit-record hiccup must not break shipping. Body is
  built with `jq` and sends `required_contexts:[]` so creation isn't blocked by the
  (old) commit's status checks.
- **`deployments: write` added** to all three `permissions:` blocks. In a reusable
  this is a ceiling intersected with the caller's grant — absent the grant, the
  best-effort step just warns. Safe to add.
- **Backward-compatible, additive inputs** (`environment`, `record_github_deployment`;
  `commit_sha` on promote). New label/annotation is inert for callers that don't read
  it. → **v1.9.0.**

Phase 3 (opt-in forward-only guard reading these stamps + per-env concurrency
re-key) remains in `TODO.md`.

## 2026-07-15 — `rollback-service` built; no pin (push-based, not GitOps); triggers stay caller-owned

**Shipped `rollback-service.yml`** — the out-of-band transient-rollback bridge the
release-process doc called for. Rolls a running Cloud Run / GKE service back onto an
already-built image (by `vX.Y.Z` tag or `sha256:` digest), **no rebuild, no retag**.
Mirrors `promote-image`'s dual-auth (WIF / key-based) and roll surface
(kubectl/helm/cloud-run), minus the retag, plus live-commit stamping. First of the
three-phase plan (rollback → live-commit stamping → forward-only guard).

**Decision — no pin/freeze.** The design doc originally mandated a pin (fast
rollback freezes promotion so nothing clobbers it). On review that was **imported
from GitOps-reconciler thinking** (Argo/Flux constantly drive cluster state to
"latest tag in git", so a manual rollback is reverted within seconds unless the
reconciler is frozen). This stack is **push-based**: Cloud Run serves the deployed
revision and GKE holds the ReplicaSet image — **no reconciler re-derives desired
state**, so nothing autonomously undoes a rollback. The only re-clobber path is a
human manually re-promoting the bad tag mid-incident. A blanket pin is a heavy fix
for that (it also freezes the *fix*, creating the unpin lifecycle we disliked). If
guarding is ever wanted, **quarantine the specific bad artifact** in `promote-image`
(refuse that digest/tag) — the permanent fix is a *new* tag, so it promotes with no
unpin dance. `rollback-service` therefore sets no pin; quarantine logged in `TODO.md`.

**Live-commit recording = annotation/label + GitHub Deployment (both).** So a later
forward-only check can read back "what is live" per env after a rollback:
Cloud Run resource label `jgd_commit=<sha>` (label keys are slash-free), GKE
annotation `jgd.dev/commit=<sha>`, and a `success` GitHub Deployment on the commit
for the environment (git-native, queryable; opt-out via `record_github_deployment`).
Stamping is skipped when `commit_sha` is empty — callers are pushed to pass it.

**Triggers stay caller-owned — for stage AND prod.** Confirmed both stage
("push to `development`") and prod ("release on `main`") are **defaults, not enforced
by the reusables**. Every workflow here is `workflow_call`; the caller wires the
trigger (tag on `development`, push to `main`, `workflow_dispatch`, … all valid).
`rollback-service` follows suit — `workflow_call` only, caller adds the
`workflow_dispatch`. release-process.md reworded to frame both flows as overridable
defaults.

**Version.** New workflow = additive input contract → **v1.8.0** (doc examples pin
it). No change to existing workflows.

## 2026-07-15 — release-process model documented; transient rollback fenced out-of-band

**Context.** `promote-image` (retag `:<sha>`→`:vX.Y.Z`, no rebuild, roll prod)
already implements the *mechanism* of stage→prod promotion, but the surrounding
**model** — trunk-based flow, what feeds stage, forward-only, and where rollback
fits — was undocumented. Wrote [docs/release-process.md](docs/release-process.md)
to capture it. This entry records the reasoning behind the choices in that doc.

**Trunk-based, build-once, promote-by-retag.** `development` + `main` both feed the
**same stage env**; prod is a retag of a stage-proven digest. Kept because it
guarantees prod runs the identical bytes stage tested — the property `promote-image`
was built for. The load-bearing simplification: the promote decision keys on
**"does `main`'s tip already have a stage-green digest?"**, *not* on the merge
strategy. That single predicate handles ff (already green → promote) and
squash/merge-commit (new SHA → build, stage, then promote) uniformly — which is what
lets callers keep **squash merges** without breaking build-once. Building from
`main`'s own tip (not `development`'s) means stage tests the *exact* prod artifact
even when squash mints a new commit, which is strictly stronger than testing
`development` and shipping `main`.

**Forward-only, all environments.** Rule: reject a deploy whose candidate commit is
an *ancestor of* (already contained in) the env's live commit. On the shared stage
env this must permit a *divergent* commit (a `main` squash is not a descendant of
`development`'s tip) — a strict "must descend" rule would block the release candidate
from reaching stage. On prod the same rule auto-strengthens to strict "latest-only"
because `main` is linear and prod releases only from `main`. **Not yet enforced** —
`promote-image` gates semver but not ancestry; logged in `TODO.md`.

**Rollback split into two actions, and transient rollback fenced OUT of the promote
flow.** The promote pipeline is forward-only and immutable-tag driven; a fast
rollback is a temporary *backward* artifact move. Mixing them would corrupt the
forward-only invariant, so they are kept separate by design:
- **Permanent fix = `git revert` + new linear tag.** The revert commit is a
  *descendant* of the bad commit, so it is forward on the tree and flows through the
  normal promote path unchanged. This is the git-native, cleanly-tracked incident
  record.
- **Transient fast rollback = out-of-band bridge.** Re-select an existing
  prod-proven digest in seconds (no rebuild), valid only until the revert tag ships.
  It **must pin/freeze** the env so normal tag-driven promotion can't re-derive
  "latest tag" and clobber the rollback mid-incident — the pin is the whole point.

**Two steady-states considered for the bridge.** (a) *Tag-driven primary + transient
bridge* — prod = latest linear tag; rollback is an exception path with a temporary
pin. (b) *Always pointer-driven (full GitOps)* — prod = whatever a committed pointer
file says, forever; promote and rollback are one uniform mechanism with no divergence
window. **Chose (a).** It matches how `promote-image` already works (immutable
`vX.Y.Z` tags), keeps the steady state simple, and confines the pointer/pin apparatus
to the incident window instead of maintaining a parallel deploy-state source of truth.
Cost accepted: during the bridge window live-state isn't derivable from tags alone,
which is exactly why the pin is mandatory.

**Fast rollback is only as safe as migrations are backward-compatible** (expand/
contract, N/N+1). A non-backward-compatible migration in the bad release makes the
prior image unrunnable against the migrated schema — then the bridge is off the table
and you must roll forward with a data fix. This is a caller-side discipline the
pipeline can't enforce.

**Separate manual rollback workflow — noted, not built.** A standalone,
manually-triggered reusable (tag/digest input → roll the service + set the pin) would
package the bridge cleanly. Deliberately left as an **independent, future** workflow —
it is orthogonal to the release pipeline and not a dependency of this documentation.
Logged in `TODO.md`.

## 2026-07-14 — key-based auth for `promote-image` (quizzing-pro prod parity)

**Problem.** quizzing-pro/api stage migrated onto JGD reusables (v1.6.0), but
**prod stayed on `zopsmart/workflows` prod-deploy@main**. Prod is a *no-rebuild
promote* — retag the exact `image:<sha>` stage tested to `:<vX.Y.Z>` and roll —
and the JGD equivalent, `promote-image`, was **WIF-only** (`wif_provider` +
`service_account` required). quizzing-pro has no WIF, only a stored
`PROD_DEPLOY_KEY`, so prod could not migrate. This was the last zopsmart
dependency in that repo.

**Read the zopsmart prod-deploy to confirm what parity needs.** On `refs/tags/v*`
it: validate-tag (semver) → server-side retag `github.sha` → `github.ref_name`
(`add-tag`, no rebuild) → conditionally apply the configmap if `.prod.env` diffed
→ `kubectl set image` + `set env APP_VERSION=<tag>`, all key-based. `promote-image`
already covered the semver gate (`require_semver`), the identical `add-tag` retag,
and the kubectl/cron roll + `app_version`. **Only the auth mode differed.**

**Decision — add a key-based fallback to `promote-image`, mirroring the dual-auth
pattern already shipped on `manage-config-secrets` + `deploy-cluster-keyed`.**
`wif_provider`/`service_account` became optional; when `wif_provider == ''`:
- the retag activates `registry_credentials` (SA-key JSON) on the gcloud CLI
  before `add-tag`;
- the GKE roll re-auths via `google-github-actions/auth` with
  `credentials_json: cluster_credentials` before `get-gke-credentials` (so ADC is
  built from the cluster key, which may differ from the registry key);
- the Cloud Run roll activates `cluster_credentials` on the CLI before
  `run services update`.
A guard fails fast if key-based auth is selected but the required credential
secret is empty. WIF path unchanged; both secrets ignored there. `id-token: write`
stays (harmless when unused; still needed by the WIF path). actionlint + SHA-pin
gate green. **Cut v1.7.0.**

**Also added `image_registry` (optional) to `promote-image`.** It derived the GAR
host from `gcp_region` (`<region>-docker.pkg.dev`) — brittle, and it must match the
exact host the stage build pushed to. The keyed deploy path uses `vars.IMAGE_REGISTRY`
directly; without an override, prod could construct a different host than stage
and the source `:<sha>` lookup would miss. `image_registry` (empty ⇒ old
region-derivation, backward-compatible) lets the caller pass the identical host.

**Why not the configmap diff-gate.** zopsmart applies the prod configmap only when
it changed between tags. In the JGD split, config VALUES are owned by
`manage-config-secrets` (a separate job), and its `kubectl create … --dry-run |
apply` is idempotent — applying every release is a no-op when unchanged. So prod
gets a `prod-config` job (manage-config-secrets over `.prod.env`) instead of
porting the diff machinery. Simpler, and keeps the value-manager the single owner
of config.

**Caller (quizzing-pro/api).** Replaced the `prod_deployment` zopsmart job with
`prod-config` (manage-config-secrets, 5 `.prod.env`, PROD_DEPLOY_KEY) +
`prod-promote` (promote-image matrix, `source_tag: github.sha`, `target_tag:
github.ref_name`, `deploy_target: gke`, key-based, PROD_DEPLOY_KEY, cron for
payment-enquiry), pinned @v1.7.0. Tag trigger narrowed `['*']` → `['v*']` to match
zopsmart's `refs/tags/v` gate with `require_semver: true`. Precondition unchanged
from zopsmart: the `:<sha>` image must exist (stage builds it on the merged commit)
before the release tag is cut; prod retags in-place in the same GAR repo.

**Follow-up (unchanged).** WIF onboarding via infra-provisioning then drop the
keys (`promote-image` WIF path + `deploy-gke-service`), retiring `PROD_DEPLOY_KEY`.

## 2026-07-14 — quizzing-pro convergence: parity audit + `manage-config-secrets`

**Problem.** Before migrating quizzing-pro (the smart-quiz candidate-assessment
"hiring motion": `api`, `engine`, `admin-ui`, `ui`) off `zopsmart/workflows@main`
onto `deploy-gke-service`, we evaluated the runtime saving. There is **none**.
Read the live zopsmart internals (`_test-go`, `_build`, `docker-build-push`,
`stage/prod-deploy`, and measured real Actions run durations):

- **Test path caches identically.** zopsmart `_test-go` already does `setup-go
  cache:true` + `actions/cache` for the linter and go-bin — same as JGD `ci-go`.
  The 256–359s is inherent (`go test -count=1 -coverpkg=./...`), not the workflow.
- **Build path is already optimized** (host `setup-go` build cache + `type=gha`
  docker cache with per-service scope). The prod path is a **83s server-side
  retag**, not a rebuild.

So the convergence is a **risk play, not a speed play** — kill the mutable
external `@main` (one bad commit red-lit 40 repos on 2026-06-26), stored-SA-key →
WIF, SHA-pin. Runtime ≈ 0, and naïve mapping *regresses* it.

**Regressions found in `deploy-gke-service` vs zopsmart `stage-deploy`, and the decisions:**

1. **Per-service BuildKit cache scope (R3).** `deploy-gke-service` hardcoded
   unscoped `cache-from/to type=gha`; in a matrix, legs evict each other
   (mode=max is per-scope). zopsmart scopes by `svc_name`. **Fixed:** added a
   `cache_scope` input (default `image_name`), wired into cache-from/to.
   Backward-compatible; benefits every caller (incl. RevvUp).

2. **In-docker build cache (R4).** zopsmart builds on the host (warm `setup-go`
   cache) then a trivial `FROM alpine + COPY main`. `deploy-gke-service` compiles
   *in* Docker, so parity requires multi-stage Dockerfiles with
   `RUN --mount=type=cache` for go-build+mod. We **fix the caller convention**
   (proper hermetic multi-stage) rather than teaching the reusable to mimic the
   host-build+COPY shortcut. (Caller-side; per-repo in the migration PRs.)

3. **Config/secret VALUES (R6/R2) — `manage-config-secrets.yml` (new).**
   `deploy-gke-service` manages no config, and `DECISIONS.md` had deferred "config
   on GKE." `sync-bundle-key` is **Cloud Run only**. Migrating as-is would silently
   **drop config**. Decision: **harden the reusable set** with a dedicated
   value-manager. It transforms a caller `dotenv` file into a ConfigMap
   (`kubectl create … --dry-run=client -o yaml | apply` — escaping-safe, unlike
   zopsmart's `cut`/`echo` YAML which corrupts values with `:`/quotes; supports a
   `react-env-js` `window.env` target for the UIs) and materializes a **masked JSON
   secret payload** into a selectable backend: `k8s` Opaque Secret, `gsm` (blob =
   one secret / individual = one per key), and a reserved `eso` value.

   - **Scope boundary (per user):** this workflow *only manages values*. **Pod
     wiring** (GSM→pod via CSI/`SecretProviderClass` or ESO `ExternalSecret`) is a
     **separate provisioning workflow** — logged in `TODO.md`. `eso` is the
     reserved extension point; factored in, not built.
   - **Secrets are never a git file** — masked JSON via `toJSON()` (the
     `sync-bundle-key` pattern). Config *is* a git file (non-sensitive).

4. **Per-service change-skip / env-only path (R1/R2).** zopsmart skips building
   unchanged services and has an env-only→configmap fast path. Not yet ported;
   caller `on.paths` is coarse for a single matrixed workflow. Tracked as
   follow-up (a `watch_paths` gate on `deploy-gke-service`).

**R5 (private-module auth) — build-secret plumbing + ci-go GOPRIVATE.** quizzing
imports the **private** `github.com/zopsmart/auth-service-v2` in `main.go` + ~30
source files. The old build fetched it host-side (setup-go + PAT `git insteadOf`)
then `COPY`ed the binary — the shortcut we're replacing. Hermetic compile-in-docker
must fetch it too. Decision: (a) `ci-go` gains `go_private` + a `github_token`
secret (git insteadOf + GOPRIVATE, in **both** the `go` and `go-db` jobs); (b)
`deploy-cluster-keyed` and `deploy-gke-service` gain a `build_secrets` secret
forwarded to build-push-action `secrets:`, so the Dockerfile uses
`RUN --mount=type=secret,id=gh_pat` — the token never lands in a build-arg or
image layer. Also: `manage-config-secrets` and both cache fixes were extended to
key-based auth so **not-yet-WIF** callers (quizzing) can use them —
`deploy-cluster-keyed` is the sanctioned stored-key path until infra-provisioning
onboards quizzing to WIF.

**Runtime finding recorded so the next person doesn't re-justify on speed:** for
these GKE monorepo callers, both libraries are performance peers. The win is
supply-chain + auth, and the *risk* is losing zopsmart's change-detection/config
handling — which is why we hardened the reusable set instead of a lift-and-shift.

## 2026-07-14 — Deploy-reusable gaps surfaced by the AutoMahn/Traide-Co caller migration (v1.5.0)

**Problem.** Migrating all ~11 AutoMahn + Traide-Co caller repos onto the
reusables (one PR per repo) surfaced four places where a faithful re-expression of
a caller's existing workflow either lost a capability or introduced a latent bug.
These are library defects, not caller mistakes, so they belong here — fixed once,
not worked around 11 times.

**The four gaps (each confirmed against a real caller, not hypothesised).**

1. **`deploy-cloudflare-pages` had no `ref` input.** Callers with a
   `workflow_dispatch` "re-deploy tag X" flow (AutoMahn `website`/`admin-ui`,
   Traide-Co `website`/`webapp`) validated the tag then `checkout`ed it. The
   reusable always built the triggering ref, so tag-pinned manual re-deploy was
   silently lost.
2. **`deploy-cloudflare-pages` had no `build_env` passthrough.** The build step
   `eval`s `build_command` with no way to inject build-time vars, so callers
   (AutoMahn `admin-ui`/`ui`) had to splice 6 `VITE_*`/`FIREBASE_*` values into
   `build_command` — less isolated than the old `env:` block.
3. **`deploy-cloud-run` expanded `extra_deploy_flags` unquoted** (`… $EXTRA` with
   a blanket `SC2086` disable). Multiple flags need the word-split, but a *value*
   containing a space (e.g. `--set-env-vars=CORS_ORIGINS=https://a, https://b`)
   also splits and corrupts argv — a live hazard in Traide-Co `api`.
4. **`deploy-cloud-run` conflated the image tag with the git checkout ref.** The
   single `image_tag` fed both the Docker tag *and* `checkout.ref`, so you could
   not tag an image `0.1.8` while building git tag `v0.1.8` (checkout would fail).
   Hit in AutoMahn `image-service`, whose old workflow tagged the un-prefixed
   pyproject version.

**Decision.** Ship four **additive, backward-compatible** inputs as **v1.5.0**
(no existing caller changes behaviour; every default reproduces today's output):

1. `deploy-cloudflare-pages.ref` — git ref to check out; empty ⇒ triggering ref.
2. `deploy-cloudflare-pages.build_env` — newline `KEY=VALUE`, exported into the
   build step's shell **only** (never `$GITHUB_ENV`, so a smuggled newline can't
   inject an env entry and vars don't leak to later steps).
3. `deploy-cloud-run.deploy_flags` — deploy flags **one per line**; spaces within
   a line are preserved (built into a bash array, not word-split). `extra_deploy_flags`
   kept as a documented legacy input, not removed.
4. `deploy-cloud-run.checkout_ref` — git ref to build from; empty ⇒ the resolved
   image tag (today's behaviour). Decouples "what to tag" from "what to build".

**Why minor, not major.** Semver here tracks the *input contract*. All four are
new optional inputs with defaults equal to prior behaviour; nothing is removed or
re-defaulted, so no caller breaks → minor bump. (Contrast: removing
`extra_deploy_flags` would be major — so it stays.)

**Also in v1.5.0 — `ci-go` golangci-lint-action v8 → v9.3.0.** Wiring golangci-lint
into AutoMahn/api + Traide-Co/api CI for the first time surfaced two things: (a)
real pre-existing lint debt (handled in those callers, not here), and (b) a
`Node.js 20 is deprecated … golangci-lint-action forced to run on Node 24`
warning — the action wrapper was pinned at v8.0.0 (a node20 action). The *linter*
was never stale: `golangci_version` already defaults to `latest` and is
overridable. Bumped the **action** to v9.3.0 (SHA `ba0d7d2…`), whose only
substantive change is the node20→node24 runtime (two other changes are additive:
install-only, module plugin system) — no config break, so it rides the same minor
bump. Both the linter-version default (`latest`) and its override input are
unchanged; this only clears the deprecation on the wrapper.

**Caller follow-ups this unblocks.** The AutoMahn/Traide-Co PRs that inlined
`build_env`, dropped tag re-deploy, or unquoted `extra_deploy_flags` can be
simplified to the new inputs once v1.5.0 is tagged — noted on each PR. Still
open: `deploy-cloudflare-worker`, `bootstrap-cf`, `cloud-run-update`,
`run-db-job` (block the workflows left inline in those PRs).

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
