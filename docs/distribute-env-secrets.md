# distribute-env-secrets

Copy a secret that the project repo holds into the **environment** of one or more service repos.
Runs in the project repo (`<org>/project`) only. It never creates a repo or an environment, never
prints a value, and fails loudly on an empty source or a missing target.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/distribute-env-secrets.yml@v4.1.0
```

## When to use it, and when not

Use it only for a secret that **several repos need the same value of** (for example a storage key
pair read by two services). The project repo holds the one source copy and this workflow copies it
out.

Do **not** use it for a secret only one service uses. That service's repo owns it: it is set by
hand in that repo's environment, and listed in that repo's `deploy/secret-keys.txt`. Copying such a
secret through the project repo only adds one more stale copy and one more hop where a value can
arrive empty. The mapping lists what is copied, not every secret.

The flow is top-down: the project repo writes into service repos; a service repo never writes up.
A rotation updates the source in the project repo first, then runs this workflow, then the service
repo's bundle sync picks the new value up.

## The mapping file

`mapping_file` (default `.github/distribute-env-secrets.yaml`), committed in the project repo:

```yaml
distribute:
  - {source: R2_ACCESS_KEY_ID,     repo: api, environment: prod, name: R2_ACCESS_KEY_ID}
  - {source: R2_SECRET_ACCESS_KEY, repo: api, environment: prod, name: R2_SECRET_ACCESS_KEY}
```

`source` is the name of a secret in the project repo, `repo` a service repo of the same org,
`environment` that repo's environment, `name` the secret name to write there. The triple
`repo` / `environment` / `name` must be unique in the file; a duplicate refuses the whole run.
The file holds names only, never values.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `mapping_file` | input | `.github/distribute-env-secrets.yaml` | see above |
| `environment` | input | `repo-admin` | the project repo's environment the job runs in (holds the App key); `main` only |
| `app_id` | input (req) | — | id of the GitHub App that writes the secrets |
| `dry_run` | input | `true` | print what would be written; write nothing |
| `only` | input | `''` | optional: distribute only this `source` |
| `app_key` | secret (req) | — | the App private key, passed by name |
| `sources_json` | secret (req) | — | the source secrets as a JSON object; the caller passes `${{ toJSON(secrets) }}` |

## What it does

1. Validates the mapping against its schema and the uniqueness rule.
2. Refuses the run if the job is not in the configured environment or `github.ref` is not
   `refs/heads/main`.
3. Refuses an **empty** source value (same rule as `strict_values` in
   [sync-bundle-key](sync-bundle-key.md)).
4. Mints an App installation token narrowed to the target repos, with `environments: write`,
   `actions: read` and `metadata: read`.
5. For each target, `GET` the environment. A `404` fails the run: `missing environment
   <repo>/<env>; run repos-environments first`. This workflow **never creates** an environment;
   [repos-environments](repos-environments.md) does, with its branch rule, before any secret is
   distributed into it.
6. Writes the secret with `gh secret set <name> --env <env> --repo <org>/<repo>`; the value goes on
   stdin, never in argv. Writing the same value again is idempotent.
7. Summarises names and targets, never values, and reports how many targets it examined. Zero
   targets fails the run.

`dry_run` is `true` by default: a first run prints the plan and writes nothing. Set it to `false`
to write.

## Credential

The token needs `Environments: write` on the target repos, not `Administration`.

**Ruling Q2 (owner, 2026-10-21):** the token comes from the org's automation App (`<org>-automation`, formerly the release App), which gains
`Environments: write` for this workflow (the same App also holds `Administration: write` for
[repos-environments](repos-environments.md)). The access-provisioning distributor App is not
used: it runs from a different repo and is not available to a project-repo job. Dry runs need no
write permission.
## Copy-paste

```yaml
name: distribute
on:
  workflow_dispatch:
    inputs:
      dry_run: { type: boolean, default: true }

permissions:
  contents: read

jobs:
  distribute:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/distribute-env-secrets.yml@v4.1.0
    with:
      app_id: ${{ vars.RELEASE_APP_ID }}
      dry_run: ${{ inputs.dry_run }}
    secrets:
      app_key: ${{ secrets.RELEASE_APP_KEY }}
      sources_json: ${{ toJSON(secrets) }}
```
