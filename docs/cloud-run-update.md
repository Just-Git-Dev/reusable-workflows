# `cloud-run-update.yml`

Apply configuration to an **existing** Cloud Run service — runtime identity, sizing, scaling,
env vars, mounted secrets, probes — then gate on the service's own health endpoint.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/cloud-run-update.yml@v2.4.1
```

## It never deploys an image

`deploy-cloud-run` and `promote-image` own **which revision runs**. This workflow owns **how
that revision is configured**. Keeping them apart is what makes a config change reviewable
without a rebuild, and a rollback a pure image operation.

## Empty means "do not touch"

Every sizing input defaults to `''`, and an empty input produces **no flag at all**.
`gcloud run services update` leaves any flag it is not given exactly as it was, and this
workflow preserves that property:

```yaml
with:
  service: my-api
  gcp_project: my-project
  max_instances: '10'      # this changes
  # everything else on the service is untouched
```

A workflow that always sent every flag would silently reset settings the caller never
mentioned back to *this file's* defaults — the failure mode where bumping `max_instances`
also quietly halves the memory. There is a step test asserting a bare run sends nothing but
the service, project and region.

`cpu_boost` is a **string** (`'true'` / `'false'` / `''`) rather than a boolean for exactly
this reason: a boolean cannot express "leave it alone".

## Env vars, secrets and labels

Newline-separated `KEY=VALUE`:

```yaml
env_vars: |
  ACCESS_CONTROL_ALLOW_METHODS=GET,POST,PUT,PATCH,DELETE,OPTIONS
  ACCESS_CONTROL_MAX_AGE=86400
secrets: |
  /configs/.env=app-env:latest
  API_KEY=api-key:3
```

`secrets` uses gcloud's own syntax: `ENV_NAME=secret:version` for an environment variable,
`/path/to/file=secret:version` for a file mount.

### The delimiter is chosen, not hardcoded

`gcloud` accepts `^delim^a=1delimb=2` to allow commas inside values. The workflow picks the
first of `@ # % | ~ ! +` that appears in **none** of the values. A hardcoded delimiter is how
a CORS method list (`GET,POST,PUT,…`) or a DSN silently splits into junk variables. If every
candidate occurs in some value, the run **fails and says so** rather than guessing.

### `update` vs `set`

`update` (default) merges, leaving unlisted variables alone. `set` makes the environment
*exactly* the listed pairs, removing anything else — declarative, and the right choice for a
caller that owns the whole environment. `clear_env_vars` only means something with `update`,
which otherwise cannot remove anything.

## `extra_args`

The long tail of `gcloud run services update` flags that do not deserve a typed input, one
flag per line:

```yaml
extra_args: |
  --set-cloudsql-instances=project:region:instance
  --description=Public API service
```

Each line becomes **one** argument, so a value containing spaces survives intact.

## The health gate

A configuration change fails in ways a revision rollout does not notice. A bad DSN inside a
secret starts cleanly, passes the startup probe, and only fails on the first query.

```yaml
health_path: /.well-known/health
health_jq: .data.sql.status
health_expect: UP
```

`health_jq` is applied to the response body, and its output must equal `health_expect`. Use
it whenever the endpoint returns `200` while *reporting* a dependency as down — the case a
status-code check cannot catch. With `health_jq` empty, only the HTTP status is asserted;
with `health_path` empty, no check runs at all.

## IAM

**On `service_account`** (the CI identity): `run.services.get`, `run.services.update` —
`roles/run.admin`, or narrower. Plus `iam.serviceAccounts.actAs` **on
`runtime_service_account`** whenever that input is set.

The **runtime** service account needs its own access to every secret named in `secrets`.
Granting that is the config repo's job, not this workflow's — see `infra-provisioning`.

## Copy-paste

```yaml
name: Provision the API service

on:
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Print the gcloud command without running it'
        required: false
        type: boolean
        default: false

permissions:
  contents: read
  id-token: write

jobs:
  configure:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/cloud-run-update.yml@v2.4.1
    with:
      service: my-api
      gcp_project: my-project
      gcp_region: asia-southeast1
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_RELEASER_SA }}
      runtime_service_account: api-run@my-project.iam.gserviceaccount.com
      port: '8000'
      cpu: '1'
      memory: 512Mi
      concurrency: '80'
      min_instances: '0'
      max_instances: '3'
      cpu_boost: 'true'
      request_timeout: 60s
      startup_probe: httpGet.path=/.well-known/alive,initialDelaySeconds=2,timeoutSeconds=3,failureThreshold=20,periodSeconds=3
      env_vars_mode: set
      env_vars: |
        ACCESS_CONTROL_ALLOW_METHODS=GET,POST,PUT,PATCH,DELETE,OPTIONS
        ACCESS_CONTROL_MAX_AGE=86400
      secrets: |
        /configs/.env=api-env:latest
      health_path: /.well-known/health
      health_jq: .data.sql.status
      health_expect: UP
      dry_run: ${{ inputs.dry_run }}
```

Run with `dry_run: true` to see the exact `gcloud` command, shell-quoted, without applying it.

## Concurrency

`cloud-run-update-<project>-<service>`, without `cancel-in-progress`. Two concurrent updates
race to create revisions and the loser's configuration is simply gone; a cancelled update can
leave a revision mid-rollout.
