# cleanup-gar-images

Sweeps a Google Artifact Registry Docker repo on a **release-relative** policy:
what survives is decided by your release history, not by the calendar.

> **v2.0.0 is a breaking change.** `sha_tag_pattern`, `sha_retention_releases`,
> `untagged_max_age_days` and `tagged_max_age_days` are **gone**. See
> [Migrating from v1](#migrating-from-v1) — and read
> [DECISIONS.md](../DECISIONS.md) for why the age model was retired.

## The model

Per image name, every artifact is one of two things:

- **RELEASE** — carries a tag matching `release_tag_pattern` (default `vX.Y.Z`)
- **BUILD** — everything else: commit-sha tags, `:latest`-only images, other tag
  schemes, and untagged manifests including buildx index children

There is no third category, so there is no artifact the policy cannot see. That
is the fix for v1's worst trait: its window only recognised images whose tag
matched `sha_tag_pattern`, so on a repo that tags no commit shas the window
protected *nothing* and age silently made every decision.

An artifact is **kept** if any of these holds:

1. its digest is live on a Cloud Run Service or Job
2. it carries a tag in `keep_tags` or matching `keep_tag_prefixes`
3. it is among the most-recent `keep_semver_count` **releases**
4. it is a **build newer than the boundary** — the `build_retention_releases`-th
   most recent release. That is your pending builds plus a rollback window, and
   it is what protects the `:<sha>` promotion source under build-once
5. it is an untagged **child of a release being kept** (see below)

Everything else is deleted once it is more than `grace_period_days` **older than
the oldest image kept by rules 3–4**.

If **zero** live digests resolve, the workflow aborts rather than treating the
whole repo as garbage.

### The fail-safe: no releases means nothing is deleted

Fewer than `build_retention_releases` releases for an image ⇒ no boundary ⇒
**every build is kept, at any age**. A repo that has never released, or one whose
`release_tag_pattern` is wrong, is left completely alone.

That is deliberate, and it is the direction a destructive workflow should fail
in. The cost is that a *misconfigured* repo looks exactly like a healthy
pre-release one, so the run **warns** when an image has no release-tagged
artifacts at all. Silence is the thing to be afraid of: `traide-in` ran green at
`deleted=0` for six consecutive days while its registry grew to 580 MB.

### The cutoff is anchored to your artifacts, not to `now`

`grace_period_days` is measured back from the oldest image the release policy
retained — not from the current time. At the default `0` the cutoff *is* that
image, so anything older goes on the next sweep.

This is what makes a plan reproducible. Under v1's `age >= 15d` rule, two dry
runs 2m27s apart legitimately produced different plans, because two untagged
digests crossed the 15-day line in between — and the difference was read as a
behaviour change in the workflow. Nothing here depends on the wall clock, so two
sweeps minutes apart agree.

**Deliberately excluded from the anchor:** live digests and `keep_tags`
protections. They still keep their own digest, but they do not move the cutoff —
otherwise one service pinned to a year-old image, or an ancient `buildcache` tag,
would drag the cutoff back with it and quietly disable the sweep for the whole
repo.

### Age comes from `createTime`

Not `updateTime`. GAR bumps `updateTime` whenever a tag is **moved off** a
digest, so an image reads as "days since the last tag churn" rather than its real
age. A digest pushed 2026-06-30 still reported 28d on 2026-08-11 because
`latest` had moved off it two weeks after the push.

v2 uses one clock everywhere — ranking releases, placing the boundary, measuring
the cutoff. v1 used three different notions of time in adjacent blocks, so its
keep-set and its window could disagree about which release was second-most-recent.
`createTime` first, falling back to `uploadTime` then `updateTime` for the rare
record that omits it.

### Multi-arch indexes: children of kept releases are kept

A `docker buildx` push is an **index**, not an image. The tag names a manifest
list whose children — `linux/amd64`, plus the `unknown/unknown` attestation
manifest — are untagged manifests in their own right, and therefore *builds*.

GAR refuses to delete a child while its parent index exists (`referenced by
parent manifests`). So a child of a release we are keeping is **kept**, not
queued: attempting it every run is guaranteed waste, and it is what made these
plans ~95% impossible candidates fleet-wide. A child whose parent is being
deleted in the same run **is** queued — phase 1 removes tagged indexes first and
`--delete-tags` cascades.

Anything still blocked at execution time is reported under `blocked_by_parent`
with the parent holding it. If a run plans deletions and removes none, it emits a
warning rather than passing quietly.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | yes | — | |
| `gar_repo` | yes | — | Artifact Registry repository name |
| `wif_provider` / `service_account` | yes | — | |
| `gcp_region` | no | `asia-southeast1` | region of both the GAR repo and Cloud Run |
| `keep_semver_count` | no | `5` | most-recent `vX.Y.Z` digests kept per image |
| `release_tag_pattern` | no | `^v\d+\.\d+\.\d+$` | regex (Python `re.match`); an artifact carrying a matching tag is a RELEASE, everything else is a BUILD |
| `build_retention_releases` | no | `2` | keep builds newer than the Nth-most-recent release. Must be ≥1 and ≤ `keep_semver_count` |
| `grace_period_days` | no | `0` | reprieve for artifacts outside the keep-set, measured back from the oldest release-policy-retained image |
| `keep_tags` | no | `latest` | exact tags never deleted. **`buildcache` was removed from this default in v2.4.0** — see [`buildcache` and registry build caches](#buildcache-and-registry-build-caches) |
| `keep_tag_prefixes` | no | `hotfix-,rc-,debug-` | tag prefixes never deleted |
| `cleanup_latest_tag` | no | `true` | delete a **stranded** `:latest` tag. Removes the tag reference only, never a digest, and only where `:latest` cannot be live. See [Stranded `:latest`](#stranded-latest) |
| `immutable_tags_policy` | no | `enforce` | state the repository is left in after an applied sweep: `enforce` \| `preserve` \| `unlock`; see [Immutable tags](#immutable-tags) |
| `relock_immutable_tags` | no | `true` | **deprecated** — `false` still means "leave it unlocked" and folds into `immutable_tags_policy: unlock` |
| `dry_run` | no | `true` | `true` prints the plan and deletes nothing |

The repo path is derived as `<gcp_region>-docker.pkg.dev/<gcp_project>/<gar_repo>`.


## Immutable tags

If the Artifact Registry repository has **immutable tags** enabled, tagged images
**cannot be deleted at all** — per `gcloud artifacts repositories update --help`:
*"Tags cannot be deleted or moved to a different image digest, and tagged images
cannot be deleted."* Untagged versions can still be deleted, so without handling this
a sweep half-succeeds: untagged versions gone, every aged-out tagged image failing.

Since **v2.1.0 the sweep is also what turns immutability ON**. An applied run ends with
the repository locked whether or not it started that way — the sweep is the one job that
already holds `artifactregistry.repositories.update` and already knows how to work around
the lock, so making it the enforcement point means no repository quietly stays unprotected
just because nobody enabled the setting when it was created.

This workflow handles it automatically, in this order:

1. **Resolve the policy.** `immutable_tags_policy` (default `enforce`), with a deprecated
   `relock_immutable_tags: false` folded in as `unlock`. An unrecognised value fails the run.
2. **Detect.** `describe` the repository, recording whether it *started* locked.
3. **Pre-flight the permission**, *before deleting anything*. It POSTs to
   `:testIamPermissions` for `artifactregistry.repositories.update` (there is no
   `gcloud artifacts repositories test-iam-permissions` subcommand). The verdict is
   **asymmetric**, because the two cases risk different things:
   - Repository **started locked** ⇒ missing permission **degrades the sweep** rather
     than failing it (since v2.1.1). Tagged images cannot be deleted while the repository
     is immutable, but untagged manifests can — so the run deletes those, skips every
     tagged candidate, and warns that retention is not being enforced. Losing the grant
     must not take the whole sweep down with it, and untagged buildx children are exactly
     the growth this job exists to stop.
   - Repository **started unlocked**, under `enforce` ⇒ missing permission **warns and
     the sweep proceeds**. Enforcement is a gain that cannot be made; no protection is
     lost, so failing here would turn a missing nice-to-have into a red pipeline.
4. **Unlock** (only if it started locked), emitting a `::warning::` that protection is off
   for the duration.
5. **Sweep.**
6. **Ensure the end-state — always.** The step runs under `if: always()`, so it fires even
   when the deletion step fails or the job is cancelled mid-sweep. It **verifies by reading
   the setting back** rather than trusting the exit code, and **fails the job** if the
   repository is still unlocked, printing the exact `gcloud` command to fix it. A repo left
   unlocked by a failed sweep is a silent loss of the guarantee.

**`dry_run: true` never toggles anything.** The plan is printed and the repository is
left exactly as found.

### Choosing a policy

| Value | Started locked | Started unlocked |
|---|---|---|
| `enforce` (default) | relocked | **locked** |
| `preserve` | relocked | left unlocked, untouched |
| `unlock` | left unlocked (loud warning) | left unlocked |

> **`enforce` will break a build that pushes a moving tag.** An immutable repository
> rejects any push that moves an existing tag to a new digest — `:latest`, a BuildKit
> `buildcache` tag, a rolling `:stage`. If images in this repository are tagged that way,
> either retire the moving tag first or set `immutable_tags_policy: preserve`. This is the
> single most likely way the default bites, and it bites the *build*, not the sweep.

`preserve` is the pre-v2.1.0 behaviour: restore what was there, never add protection.

`unlock` leaves the repository unlocked after the sweep. The only legitimate uses are a
maintenance window or debugging a failed sweep. The run warns loudly and prints the command
to re-enable protection.

> **Leaving it unlocked means any actor can move a tag to a different digest** — which is
> precisely what immutable tags exist to prevent, and what makes a `:v1.2.3` tag a
> trustworthy deploy target. Do not set this in a scheduled sweep.

### What the service account needs

`artifactregistry.repositories.update`, i.e. `roles/artifactregistry.admin` on the
repository — **not** `roles/artifactregistry.repoAdmin`, which manages *artifacts* rather
than the repository and does not carry `artifactregistry.repositories.update`. Under the
default `enforce` this is needed on **every** repository, not only ones that already have
immutability enabled.

**The permission being absent never fails the run.** On an unlocked repository the sweep
warns and proceeds normally; on a locked one it degrades to untagged-only and says so. The
cost of losing the grant is protection and retention, never a red pipeline. IAM therefore remains the real
gate on whether this workflow can change a repository's settings: a repository that must
never be touched simply does not grant the permission, and no caller-side input can
override that.

## Migrating from v1

`v2.0.0` removes four inputs. A caller passing any of them fails at startup with
GitHub's "unexpected input" error — deliberately, rather than accepting and
ignoring them, because a caller who believes they still have a 15-day grace
period and does not is worse off than one whose run refuses to start.

| v1 input | v2 |
|---|---|
| `sha_tag_pattern` | **gone.** Classification is "carries a release tag" vs not, so build tags need no pattern of their own |
| `sha_retention_releases: 1` | `build_retention_releases: 2` — same boundary, counted as "how many releases of builds do I keep" rather than an offset |
| `untagged_max_age_days: 15` | `grace_period_days` — one knob for both, and relative to your releases rather than to `now` |
| `tagged_max_age_days: 30` | as above |

**What changes on the ground.** v2 deletes *more* than v1 on an actively-released
repo — v1's real behaviour was "delete things older than 15/30 days", and a repo
whose tags churn faster than that deleted nothing at all. Under v2, everything
outside the release window goes at the default `grace_period_days: 0`.

**So dry-run both pins before repinning**, per [AGENTS.md](../AGENTS.md) §5, and
read the diff. Expect a larger first sweep that drains a backlog v1 had been
silently retaining, then a small steady state.

**Set `grace_period_days: 1` (or more) on a repo doing build-once/promote**, so a
digest that is mid-promotion when the sweep runs is not removed underneath it.

## Outputs

`candidates`, `deleted`, `skipped`.

## Required IAM

On `service_account`: **`roles/artifactregistry.admin`** (on the target repo) and
`roles/run.viewer` (to enumerate live Services and Jobs).

`repoAdmin` is not enough — it is *"access to manage artifacts in repositories"*, so it
carries `repositories.deleteArtifacts` but not `repositories.update`, and
`immutable_tags_policy` silently cannot take effect. See
[What the service account needs](#what-the-service-account-needs) for what happens when the
permission is absent (short version: the run never fails because of it).

## `buildcache` and registry build caches

If you use a BuildKit **registry** cache (`cache-to:
type=registry,ref=...:buildcache`), that cache is an ordinary tagged image in
the same repo. Without protection it would be classified as a BUILD, fall outside the
release window as soon as two releases passed, and be deleted — making the next build a
cold rebuild. So if you run one, add it: `keep_tags: latest,buildcache`.

### Why it is not in the default (changed in v2.4.0)

It used to be, and that was incoherent with the *other* default. A registry cache is a
**moving** tag — every build overwrites `:buildcache` — and the default
`immutable_tags_policy` is `enforce`. Immutable tags let you **create** a tag but never
**move** one, so on an enforcing repository the first `cache-to` push succeeds and every
later one fails: the cache freezes at its first push and silently stops helping. Nothing
errors loudly; builds just quietly stop getting cache hits.

So the old default protected a tag that, under the default policy, could not usefully
exist. Keeping it cost nothing at runtime — shielding a tag that isn't there is harmless —
but the two defaults told a new caller opposite stories about whether moving tags were
part of the model.

**A registry cache and `immutable_tags_policy: enforce` are mutually exclusive.** Choosing
the cache means choosing `preserve` or `unlock`. Making `buildcache` opt-in puts that
decision where it belongs — with the caller who actually runs one. If you set it under
`enforce`, the workflow now warns at run time rather than leaving you to find it here.

## Stranded `:latest`

A moving `:latest` left behind in a repository that has since been **locked** is
permanent otherwise. It pins its digest alive, `keep_tags` shields it from the
sweep, and an immutable repository refuses to move or remove it. Nothing
converges: every future sweep keeps it, forever.

`cleanup_latest_tag` (**default `true`**) removes it.

**It deletes the tag reference, never a digest.** That distinction is the whole
point. Dropping `latest` from `keep_tags` instead would let the sweep delete the
*digest* — and under build-once/promote a released digest carries both a `:<sha>`
tag and `vX.Y.Z`, so that would take a release with it. `gcloud artifacts docker
tags delete` removes only the pointer.

### Why defaulting to true is safe

It only acts where `:latest` **cannot be a live tag**:

| policy | repo state | `:latest` cleaned? |
|---|---|---|
| `enforce` (default) | either | **yes** — a moving tag is unpushable, so any `:latest` is stranded by definition |
| `preserve` | already locked | **yes** — it stays locked, so the tag can never move again |
| `preserve` | unlocked | no — the build may still be pushing `:latest`; this is the case `preserve` exists for |
| `unlock` | either | no — the repository is deliberately left writable |

So keeping `latest` in `keep_tags` and `cleanup_latest_tag: true` are not in
conflict, despite reading that way: **`keep_tags` protects the digest during the
sweep; `cleanup_latest_tag` removes the stranded pointer after it.** Set it to
`false` to opt out entirely.

### It is a convergence rule, not a one-shot

It deletes `:latest`, then finds nothing, forever — idempotent, and green either
way. That is why it runs on the schedule like the rest of the sweep rather than
being restricted to a manual dispatch: a stranded tag clears itself on the next
scheduled run with no human action.

Two more behaviours worth knowing:

- **It runs after the sweep, inside the unlock window.** The plan is computed
  before any tag is touched, so a reviewed dry-run digest set still matches the
  applied run. The consequence is intended: once the tag is gone its digest is
  untagged, and it is reclaimed by the **next** sweep, not this one.
- **`dry_run: true` is the read path.** It reports which packages carry `:latest`
  and which digests it points at, and deletes nothing. This is the only way to
  see a keep-set digest at all — the plan JSON enumerates `to_delete` and
  `blocked_by_parent`, never the kept.

Matching is **exact**: a repository carrying `latest-rc` but no `latest` has
nothing to clean. (Deliberately not `--filter=tag:latest` — gcloud's `:` is a
has/contains operator, not equality.)

Unlike the sweep, it **fails rather than degrades**. If the repository is locked
and the service account cannot unlock it, the sweep skips tagged images and stays
green — the right trade for a retention policy. It is the wrong trade for a
cleanup the caller asked for, where exiting green having removed nothing is the
failure mode. So that case exits 1 and names the missing permission.

## Always dry-run first

`dry_run: true` prints the full plan to the step summary. Read it before you let
a first real sweep run against a repo — the keep-set is the only thing standing
between the sweep and an image you still need.

## Example caller

Real deletions daily, with a dry-run preview on the 1st of the month.

```yaml
name: Cleanup GAR images
on:
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: true
  schedule:
    - cron: '0 4 * * *'

permissions:
  contents: read
  id-token: write

jobs:
  resolve:
    runs-on: ubuntu-latest
    outputs:
      dry: ${{ steps.d.outputs.dry }}
    steps:
      - id: d
        env:
          EVENT: ${{ github.event_name }}
          REQUESTED: ${{ inputs.dry_run }}
        run: |
          if [ "$EVENT" = "workflow_dispatch" ]; then D="$REQUESTED"
          elif [ "$(date -u +%d)" -eq 1 ]; then D=true
          else D=false
          fi
          echo "dry=$D" >> "$GITHUB_OUTPUT"

  cleanup:
    needs: resolve
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/cleanup-gar-images.yml@v2.6.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_CLEANER_SA }}
      gar_repo: backend
      dry_run: ${{ needs.resolve.outputs.dry == 'true' }}
```

## Tests

The delete-plan algorithm lives inline in a `python3 <<'PY'` heredoc, which
`actionlint`'s shellcheck does not descend into. It must stay inline: every
`actions/checkout` in a reusable workflow checks out the *caller's* repo, so a
`scripts/*.py` shipped here would not exist at runtime.

`tests/run_plan_tests.py` therefore **extracts that heredoc from the workflow
file and executes it** against synthetic registries, via the `PLAN_FIXTURE`
environment seam (unset in every real run). There is no second copy of the
algorithm to drift.

```bash
python3 tests/run_plan_tests.py     # also runs in CI on every PR
```

Fixtures live in `tests/fixtures/*.json` and declare image ages relative to now.
Beyond each fixture's expected delete-set, the runner re-runs every fixture twice
more — once with a longer `build_retention_releases`, once with a large
`grace_period_days` — and asserts neither plan deletes anything the default does
not. Both are monotonicity claims the policy makes, checked structurally on every
fixture rather than case by case.

## Concurrency

Deletions run with `xargs -P 8`. The workflow holds a concurrency group keyed on
`<gcp_project>-<gar_repo>` so a manual dispatch cannot race the scheduled sweep
and act on a delete-set computed before the other run started.
