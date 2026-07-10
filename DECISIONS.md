# Decisions — reusable-workflows

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

- **`v1` stays a floating alias, and that is now documented as a choice.** The
  previous README told callers to pin `@v1` while `v1` was a single movable
  lightweight tag — and `deploy-cloudflare-pages.yml` did not exist at `v1` at
  all, so every caller following the README got a 404. Releases are now
  immutable `vX.Y.Z` tags; `v1` moves. Docs pin `@v1.1.0`.

- **Region default `asia-southeast1` is retained.** It encodes one deployment's
  choice, but changing a default silently changes behaviour for any caller that
  omits the input. It is a candidate for `required: true` in a v2.

**Not done here.** Branch protection on `main` (`"protected": false` today,
despite CODEOWNERS) has to be set in repo settings, not in a commit. Since `v1`
is cut from `main` and moves, an unreviewed push plus a `git tag -f` would change
ops behaviour for every consumer at once. Enable it before announcing the repo.

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
