# cleanup-gar-images

Age-sweeps every image in a Google Artifact Registry Docker repo.

The keep-set is built from digests that are live on **all** Cloud Run Services
*and* Jobs in-region (cron and migration containers commonly live on Jobs, not
Services), plus the most-recent N semver tags per image, plus any tag listed in
`keep_tags` or matching a prefix in `keep_tag_prefixes`, plus commit-sha-tagged
images inside the [sha retention window](#sha-retention-build-once-promote-to-prod).
Everything else is deleted once it exceeds the untagged/tagged age limits.

If **zero** live digests resolve, the workflow aborts rather than treating the
whole repo as garbage.

### Precedence

An image is kept if **any** of these holds, checked in this order:

1. its digest is live on a Cloud Run Service or Job
2. it carries a tag in `keep_tags` or matching `keep_tag_prefixes`
3. it is among the most-recent `keep_semver_count` semver-tagged digests
4. it is sha-tagged and inside the sha retention window

Otherwise it is deleted **only if** it also exceeds `untagged_max_age_days` /
`tagged_max_age_days`. Window membership is *sufficient* to keep (it overrides
`tagged_max_age_days`); falling outside the window is *not* sufficient to
delete — age is still required. That asymmetry is what keeps the rule from ever
widening the delete-set.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | yes | — | |
| `gar_repo` | yes | — | Artifact Registry repository name |
| `wif_provider` / `service_account` | yes | — | |
| `gcp_region` | no | `asia-southeast1` | region of both the GAR repo and Cloud Run |
| `keep_semver_count` | no | `5` | most-recent `vX.Y.Z` digests kept per image |
| `untagged_max_age_days` | no | `15` | |
| `tagged_max_age_days` | no | `30` | |
| `keep_tags` | no | `latest,buildcache` | exact tags never deleted |
| `keep_tag_prefixes` | no | `hotfix-,rc-,debug-` | tag prefixes never deleted |
| `sha_tag_pattern` | no | `^[0-9a-f]{40}$` | regex (Python `re.search`) matching commit-sha tags; empty ⇒ sha retention off |
| `sha_retention_releases` | no | `1` | keep sha images newer than the Nth-most-recent release; `0` ⇒ off |
| `dry_run` | no | `true` | `true` prints the plan and deletes nothing |

The repo path is derived as `<gcp_region>-docker.pkg.dev/<gcp_project>/<gar_repo>`.

## sha retention (build-once, promote-to-prod)

Under [build-once](deploy-cloud-run.md#build_only-buildonce-promote-to-prod), a
merge to `main` publishes `image:<commit-sha>` and a release only **retags** that
digest — `promote-image` never rebuilds. The `:<sha>` image is therefore the
promotion source, not a disposable build artifact, and an age-only sweep would
silently destroy it on a slow release cycle.

Per package, this workflow keeps every sha-tagged image **newer than the
`sha_retention_releases`-th most recent release**:

```
       ...older releases...      v1.0.0            v2.0.0        HEAD
  ──────────────────────────────────┼──────────────────┼───────────────▶ time
                                 boundary
     sha images here: deletable  │  sha images here: KEPT (window)
                                 │  ├─ one release of rollback headroom
                                 └─ ranked[sha_retention_releases]
```

With the default `1`, that is "everything built since the previous release" —
unreleased-but-pending builds plus one release worth of rollback window.

Three properties worth knowing:

- **Releases are ordered by time, not semver precedence.** A sha image carries no
  semver, so the comparison is time-based regardless — and semver ordering breaks
  on backports (a `v2.9.0` cut today after a long-released `v3.0.0` would put the
  boundary at *today* and delete genuine pending builds).
- **Keep-only.** The pass can only add to the keep-set. Enabling it, or raising
  `sha_retention_releases`, can only ever delete **less** than before — so it is
  on by default. `sha_retention_releases: 0` reproduces the previous behaviour
  exactly.
- **`keep_semver_count` is floored at `sha_retention_releases + 1`**, so the
  releases that define the window cannot themselves age out and move the boundary
  between sweeps.

> **Caveat — a package with fewer than `sha_retention_releases + 1` releases has
> no boundary, so *every* sha image is kept regardless of age.** This is
> deliberate (there is nothing to prove a sha was superseded), but a package that
> never cuts a release will accumulate sha images indefinitely. Set
> `sha_retention_releases: 0` for packages that are not on the build-once flow.

The dry-run plan and step summary carry a `sha_retention` block per package —
the boundary timestamp and tags, release count, and how many sha images were
kept. That is the only review surface for this rule; read it on the first sweep.

## Outputs

`candidates`, `deleted`, `skipped`.

## Required IAM

On `service_account`: `roles/artifactregistry.repoAdmin` (on the target repo)
and `roles/run.viewer` (to enumerate live Services and Jobs).

## `buildcache` and registry build caches

If you use a BuildKit **registry** cache (`cache-to:
type=registry,ref=...:buildcache`), that cache is an ordinary tagged image in
the same repo. It is in the default `keep_tags` for exactly this reason — with
it removed, a repo that goes `tagged_max_age_days` without a release would have
its build cache age-deleted and the next build would be a cold rebuild.

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/cleanup-gar-images.yml@v1.21.0
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
Beyond each fixture's expected delete-set, the runner re-runs every fixture with
`sha_retention_releases: 0` and asserts the window run never deletes anything the
legacy run would not — checking the keep-only invariant structurally rather than
case by case.

## Concurrency

Deletions run with `xargs -P 8`. The workflow holds a concurrency group keyed on
`<gcp_project>-<gar_repo>` so a manual dispatch cannot race the scheduled sweep
and act on a delete-set computed before the other run started.
