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
| `keep_tags` | no | `latest,buildcache` | exact tags never deleted |
| `keep_tag_prefixes` | no | `hotfix-,rc-,debug-` | tag prefixes never deleted |
| `relock_immutable_tags` | `true` | re-enable immutable tags after the sweep — **on by default**; see [Immutable tags](#immutable-tags) |
| `dry_run` | no | `true` | `true` prints the plan and deletes nothing |

The repo path is derived as `<gcp_region>-docker.pkg.dev/<gcp_project>/<gar_repo>`.


## Immutable tags

If the Artifact Registry repository has **immutable tags** enabled, tagged images
**cannot be deleted at all** — per `gcloud artifacts repositories update --help`:
*"Tags cannot be deleted or moved to a different image digest, and tagged images
cannot be deleted."* Untagged versions can still be deleted, so without handling this
a sweep half-succeeds: untagged versions gone, every aged-out tagged image failing.

This workflow handles it automatically, in this order:

1. **Detect.** `describe` the repository. If immutability is off, nothing below runs —
   no repository setting is ever touched on a repo that does not need it.
2. **Pre-flight the permission**, *before deleting anything*. It POSTs to
   `:testIamPermissions` for `artifactregistry.repositories.update` (there is no
   `gcloud artifacts repositories test-iam-permissions` subcommand). Missing ⇒ the run
   **fails with nothing deleted**, naming the permission and the role that grants it.
   Discovering this halfway through would leave the repo unlocked and the sweep partial.
3. **Unlock**, emitting a `::warning::` that protection is off for the duration.
4. **Sweep.**
5. **Relock — always.** The step runs under `if: always()`, so it fires even when the
   deletion step fails or the job is cancelled mid-sweep. It then **verifies by reading
   the setting back** rather than trusting the exit code, and **fails the job** if the
   repository is still unlocked, printing the exact `gcloud` command to fix it. A repo
   left unlocked by a failed sweep is a silent loss of the guarantee.

**`dry_run: true` never toggles anything.** The plan is printed and the repository is
left exactly as found.

### Opting out of the relock

`relock_immutable_tags: false` leaves the repository unlocked after the sweep. The only
legitimate uses are a maintenance window or debugging a failed sweep. The run warns
loudly and prints the command to re-enable protection.

> **Leaving it unlocked means any actor can move a tag to a different digest** — which is
> precisely what immutable tags exist to prevent, and what makes a `:v1.2.3` tag a
> trustworthy deploy target. Do not set this in a scheduled sweep.

### What the service account needs

`artifactregistry.repositories.update`, i.e. `roles/artifactregistry.admin` on the
repository, **only if** immutability is enabled. Repos without it need nothing extra —
which also means IAM, not a workflow input, is the real gate on whether this workflow can
change a repository's settings at all.

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

On `service_account`: `roles/artifactregistry.repoAdmin` (on the target repo)
and `roles/run.viewer` (to enumerate live Services and Jobs).

## `buildcache` and registry build caches

If you use a BuildKit **registry** cache (`cache-to:
type=registry,ref=...:buildcache`), that cache is an ordinary tagged image in
the same repo. It is in the default `keep_tags` for exactly this reason — with it removed, the
cache would be classified as a BUILD, fall outside the release window as soon as
two releases passed, and be deleted, making the next build a cold rebuild.

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/cleanup-gar-images.yml@v2.0.0
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
