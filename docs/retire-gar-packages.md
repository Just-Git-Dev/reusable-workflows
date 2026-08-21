# retire-gar-packages

Deletes **entire** Artifact Registry packages — every version and tag — for
services that have been retired. Destructive and irreversible.

This exists because [`cleanup-gar-images`](cleanup-gar-images.md) will never
remove them. That sweep keeps the most recent `keep_semver_count` releases *per
package*, and it applies that rule whether or not anything still deploys the
package. A dead service's images are therefore protected forever by a retention
policy that is working exactly as designed. Retiring the package is a separate,
deliberate act — hence a separate workflow, a caller-supplied package list, and
`dry_run: true` by default.

## The safety rule

Before deleting anything it builds the same live-digest set as the image sweep —
every digest referenced by a live Cloud Run **Service or Job** in-region — and
**refuses to delete any named package that still has a live reference**. One
live hit aborts the whole run with nothing deleted, rather than skipping that
package and proceeding.

That is deliberate: a package you believed was dead but is not means the list is
wrong, and the safe response to a wrong list is to stop, not to execute the part
of it that happens to be safe. Cron and migration containers commonly run on
Jobs rather than Services, which is the case a Services-only check would miss.

A package that does not exist is skipped as already-gone, not treated as an
error.

## Immutable tags

A repository with immutable tags enabled refuses to delete any package holding a
tagged image. An applied run therefore **detects the lock, verifies it can
toggle it, unlocks, retires, and restores the lock** — the restore step runs
even if the retirement fails or the job is cancelled, because a repository left
unlocked by a failed run is a silent loss of protection.

Two differences from `cleanup-gar-images`, both intentional:

- **There is no policy input.** That workflow takes `immutable_tags_policy`
  because it owns a repository's retention posture and runs on a schedule.
  A retirement is a one-off surgical delete, so it has exactly one end state:
  **the repository is left as it was found**, locked or unlocked. Nothing about
  removing a dead service's package is an argument for changing whether the
  repository is protected.
- **There is no degraded mode.** The sweep degrades to untagged-only under a
  lock it cannot open, because half a sweep is still real work. A package delete
  takes every tag with it or fails — there is no partial version. So a locked
  repository whose service account cannot unlock it **fails the pre-flight
  before anything is deleted**, naming immutability and both fixes.

## Required IAM on `service_account`

| Role | Why |
|---|---|
| `roles/artifactregistry.admin` | delete packages, and toggle immutability |
| `roles/run.viewer` | enumerate live Services + Jobs for the safety check |

`roles/artifactregistry.repoAdmin` is **not** enough on a repository with
immutable tags. It manages *artifacts*, not repository settings, so it lacks
`artifactregistry.repositories.update` and cannot unlock. On a repository that
has never been locked, repoAdmin alone still works — which is exactly why this
gap stayed invisible until immutability was enforced fleet-wide.

## Inputs

| Name | Kind | Default | Notes |
|---|---|---|---|
| `gcp_project` | input (req) | — | project owning the Artifact Registry repo |
| `gar_repo` | input (req) | — | repository name (e.g. `backend`) |
| `packages` | input (req) | — | comma/space-separated package names to retire |
| `wif_provider` | input (req) | — | Workload Identity provider resource name |
| `service_account` | input (req) | — | SA to impersonate |
| `gcp_region` | input | `asia-southeast1` | region of the AR repo and the Cloud Run workloads |
| `dry_run` | input | `true` | `true` = print the plan, delete nothing |

## Outputs

`retired` — number of packages actually deleted (`0` on a dry run).

## Example caller

```yaml
name: Retire dead GAR packages
on:
  workflow_dispatch:
    inputs:
      packages:
        description: 'Package names to retire (comma-separated)'
        required: true
      dry_run:
        type: boolean
        default: true

permissions:
  contents: read
  id-token: write

jobs:
  retire:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/retire-gar-packages.yml@v2.4.0
    with:
      gcp_project: my-project
      gar_repo: backend
      packages: ${{ inputs.packages }}
      dry_run: ${{ inputs.dry_run }}
      wif_provider: projects/123/locations/global/workloadIdentityPools/github/providers/github
      service_account: github-cleaner@my-project.iam.gserviceaccount.com
```

`workflow_dispatch` rather than a schedule, on purpose: there is no such thing as
a package that becomes retirable on a timer. Run it with `dry_run: true` first
and read the plan — it names every package, its image count, and whether the
live-reference check cleared it.
