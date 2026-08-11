# run-db-job

Create-or-update a **Cloud Run Job** from an **already-built** image, then execute it
and wait for it to finish. No build, no push — the image must already exist in
Artifact Registry.

The batch counterpart to [`deploy-cloud-run`](deploy-cloud-run.md): same image, same
`gcloud`/WIF plumbing, but the resource is a Job (runs to completion, then exits)
rather than a Service (stays up serving traffic).

## When to use it

- **Schema migrations before a service roll** — the canonical case. Run the Job, wait
  for exit 0, and only then let the new revision go live, so the app never sees a
  schema it predates.
- **One-shot backfills, seeders, reconciliation sweeps** — anything that shares the
  app image and picks its mode from container args.
- **Defining a Job that something else triggers** (Cloud Scheduler, Eventarc). Set
  `execute: false` to converge the definition without running it.

For rolling a *service*, use [`deploy-cloud-run`](deploy-cloud-run.md). For retagging
an image between environments, [`promote-image`](promote-image.md).

## Create-or-update, then execute

The Job definition is converged idempotently — `gcloud run jobs describe` decides
between `create` and `update`, so the first run in a fresh project and the two
hundredth run behave identically and neither needs a bootstrap step.

Execution then runs with `--wait`. **A non-zero task exit fails the workflow**, which
is the whole point: a caller gating a service roll on `needs:` must not proceed past a
broken migration.

On failure the workflow prints the execution's status and a Logs Explorer link before
exiting, because `gcloud run jobs execute` reports only that the execution failed and
not why.

> **Make sure your task actually logs to stdout/stderr.** A batch binary wired to a
> discarded logger produces a failed execution with an empty log — indistinguishable
> from a silent crash, and expensive to debug. This has bitten a caller before
> (`AutoMahn/api` v0.0.7, ~1h lost to a silent `migrate` exit).

## Ordering is the caller's job

This workflow does one thing. Sequencing — migrate Job first, service second — is
expressed in the caller with `needs:`, the same way pre-deploy gates already are:

```yaml
jobs:
  migrate:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/run-db-job.yml@v1.22.0
    # ...
  api:
    needs: migrate
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v1.22.0
    # ...
```

## No live-commit stamping — deliberate

Unlike `deploy-cloud-run` / `promote-image` / `rollback-service`, this records no
`jgd_commit` label and no GitHub Deployment. Forward-only (see
[release-process.md](release-process.md)) is defined per **environment**, and an
environment's live commit is what its *services* are serving. A Job is a one-shot
task, not a thing that is "live", so stamping one would put a second, conflicting
answer into the baseline the forward-only guard reads back.

## Inputs

| Name | Default | Notes |
|---|---|---|
| `gcp_project` | (req) | Project owning the Cloud Run Job |
| `gcp_region` | `asia-southeast1` | Job region |
| `wif_provider` | (req) | Workload Identity Federation provider resource name |
| `service_account` | (req) | Releaser SA to impersonate via WIF |
| `job` | (req) | Cloud Run Job name |
| `image` | (req) | Fully-qualified image ref. Typically the `image` output of a `deploy-cloud-run` build |
| `args` | `''` | Container args, gcloud's comma-delimited list (e.g. `migrate`). Empty ⇒ flag omitted, image entrypoint decides |
| `runtime_service_account` | `''` | SA the **task** runs as. Distinct from `service_account`, which is the deployer. Empty ⇒ project default |
| `env_vars` | `''` | Passed verbatim to `--set-env-vars`. Use gcloud's custom-delimiter form for values containing commas: `^\|^K=V\|K2=V2` |
| `set_secrets` | `''` | Passed verbatim to `--set-secrets` (e.g. `/app/configs/.prod.env=app-secrets:latest`) |
| `cpu` | `1` | Task CPU |
| `memory` | `512Mi` | Task memory |
| `max_retries` | `1` | Retries before the task is marked failed |
| `task_timeout` | `600s` | Per-task timeout |
| `job_flags` | `''` | Escape hatch: extra `gcloud run jobs create/update` flags, **one per line**. Spaces within a line are preserved |
| `execute` | `true` | Execute after converging. `false` converges the definition only — for Scheduler/Eventarc-triggered Jobs |
| `dry_run` | `false` | Print the commands without executing them |
| `timeout_minutes` | `20` | Job timeout |

### Outputs

| Name | Notes |
|---|---|
| `execution` | Name of the execution that ran, or empty when `execute: false` / `dry_run` |

## Auth

Keyless only — WIF, consistent with `deploy-cloud-run`. The releaser SA needs
`roles/run.developer` on the project (create/update/execute Jobs) and
`roles/iam.serviceAccountUser` on `runtime_service_account` when one is set.

## Example — migrate Job gating a service roll

Mirrors the build-once model: `deploy-cloud-run` publishes the image, the Job runs
against it, and the service rolls only if the Job exits 0.

```yaml
name: Deploy
on:
  push:
    tags: ['v*.*.*']

permissions:
  contents: read
  id-token: write

jobs:
  build:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v1.22.0
    with:
      build_only: true
      gcp_project: auto-mahn
      gar_repo: backend
      image_name: app
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}

  migrate:
    needs: build
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/run-db-job.yml@v1.22.0
    permissions:
      contents: read
      id-token: write
    with:
      gcp_project: auto-mahn
      job: automahn-migrate
      image: ${{ needs.build.outputs.image }}
      args: migrate
      runtime_service_account: automahn-api-run@auto-mahn.iam.gserviceaccount.com
      env_vars: ^|^APP_ENV=prod|CMD_LOGS_FILE=/dev/stderr|DB_HOST=${{ vars.DB_HOST }}
      set_secrets: /app/configs/.prod.env=app-secrets:latest
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}

  api:
    needs: [build, migrate]
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v1.22.0
    # ... rolls the service, only reached if migrate exited 0
```

To skip the Job when nothing changed, gate it in the caller — a `git diff` over
`migrations/` in an earlier job, then `if: needs.plan.outputs.migrations_changed == 'true'`.
Skipping saves the Job's cold start; it is not required for correctness if your
migration runner is a no-op on nothing-pending.

## Example — converge a Scheduler-triggered Job without running it

```yaml
  nightly-reconcile:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/run-db-job.yml@v1.22.0
    with:
      gcp_project: auto-mahn
      job: nightly-reconcile
      image: ${{ needs.build.outputs.image }}
      args: reconcile
      execute: false          # Cloud Scheduler triggers it, not this workflow
      task_timeout: 1800s
      job_flags: |
        --parallelism=1
        --tasks=1
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
```

## Dry run

`dry_run: true` prints the exact `gcloud` commands without executing them, honouring
the repo convention that every mutating workflow has a safe plan mode. Nothing is
created, updated or run, and `execution` comes back empty.

## Concurrency

Keyed on `run-db-job-<gcp_project>-<gcp_region>-<job>` with `cancel-in-progress: false`.
Two releases racing the same migration Job serialize rather than interleave — Cloud Run
would otherwise happily start a second execution while the first is mid-migration.

## Testing note

The logic here is inline `bash` (as it must be — `actions/checkout` inside a reusable
workflow checks out the **caller's** repo, so a `scripts/*.sh` shipped from here would
not exist at runtime). It is covered by `actionlint`'s shellcheck pass in CI. The
fixture harness in `tests/` reaches embedded Python only, so it does not apply; see
`TODO.md` for the open item on executing `run:` bodies against a stubbed env.
