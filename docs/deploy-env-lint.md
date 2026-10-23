# deploy-env-lint

Lint a service repo's committed env files before they are deployed. The plain (non-secret)
configuration of a service lives in `deploy/env.<stage>.yaml`; the names of the secret keys the sync
reads live in `deploy/secret-keys.txt`. This workflow reads only those files, calls no
cloud and needs no credential, and refuses the mistakes that otherwise surface as an outage on
the first deploy of a stage.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-env-lint.yml@v5.1.0
```

It is a standalone reusable workflow, not a step inside the deploy workflows, so a repo can run
it on every pull request that touches `deploy/` without building or deploying anything. (The
deploy workflows repeat the secret-looking-key refusal as defence in depth; see
[deploy-cloud-run](deploy-cloud-run.md#render).)

## What it reads

| File | Content |
|---|---|
| `deploy/env.<stage>.yaml` (every stage the repo has) | flat map of plain environment variables |
| `deploy/secret-keys.txt` | the key NAMES of the bundle secret, one per line; the keys the sync reads from the environment; keys a rotator writes are deliberately not listed |

Input names for the two paths, and their defaults, are fixed by the workflow and listed in its
`inputs:` block; the table above is the contract for what is read.

## What it refuses

Any one finding fails the run. Every finding is printed with the file and the key; values are
shown only for non-secret rules where the value is the problem.

1. **Stage files whose key sets differ.** `env.stage.yaml` and `env.prod.yaml` (any pair of stage
   files) must carry the same keys; values may differ.
2. **A stage-pattern host in the prod file.** A host matching the stage naming (for example a
   stage database or Redis endpoint) in the prod file.
3. **Connection-string keys:** `REDIS_URL`, `DATABASE_URL`, `DB_URL`, and any `*_DSN`.
4. **Pool and lifetime tuning keys:** `REDIS_POOL_SIZE`,
   `DB_MAX_OPEN_CONN`, `DB_MAX_IDLE_CONN`, `DB_MAX_CONN_LIFETIME_MIN`.
5. **Redis on a managed serverless host:** `REDIS_DB` other than `0`; `PUBSUB_BACKEND=REDIS`
   without `REDIS_PUBSUB_DB=0`.
6. **Unencrypted datastore transport** for any host that is not `localhost`, `127.0.0.1`, `redis`
   or `postgres`: `REDIS_TLS_ENABLED` other than `true`; `DB_SSL_MODE` unset, `disable`, `allow`
   or `prefer`.
7. **A password in plain config:** any `*_PASSWORD` key in an env file.
8. **`DB_MAX_OPEN_CONNECTION` unset** where `DB_HOST` is set.
9. **Datastore keys present on one database-using service and missing on another** (a repo with
   several services is checked service against service).

Rules 3 to 9 are the datastore standard's deploy-env lint; rule 1 and 2 are the owner's addition
that the env file is the only plain-config home.

## Output

The run summary lists every file examined and every finding. A run that examined **zero** env
files fails: a lint that looked at nothing proves nothing.

## Caller

```yaml
name: deploy-env-lint
on:
  pull_request:
    paths: ['deploy/**']

permissions:
  contents: read

jobs:
  lint:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-env-lint.yml@v5.1.0
```
