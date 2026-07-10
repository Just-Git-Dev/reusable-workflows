# neon-backup

Full logical backup of a Postgres database into a **private workflow artifact**.
Built for [Neon](https://neon.tech), but it works against any reachable Postgres.

The database password is read at run time from a key inside a Secret Manager
*bundle* secret (a dotenv blob of `KEY=value` lines), so it never has to exist as
a GitHub secret. Host, port, user and database name are plain inputs.

> The workflow file is named `neon-backup.yml` for backwards compatibility with
> existing callers. Nothing in it is Neon-specific.

## Formats

| `dump_format` | Output | Integrity check |
|---|---|---|
| `custom` (default) | `.dump`, `pg_restore`-compatible | `pg_restore --list` must parse the archive |
| `plain-gz` | `.sql.gz` | `gzip -t` plus a dump-header check; **both** `pg_dump` and `gzip` exit codes are asserted |

Both formats emit a `MANIFEST.txt` (reason, timestamp, table count, sha256).

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | yes | — | project holding the bundle secret |
| `wif_provider` / `service_account` | yes | — | |
| `db_host` / `db_user` / `db_name` | yes | — | |
| `bundle_secret` | no | `app-secrets` | dotenv secret to read the password from |
| `password_key` | no | `DB_PASSWORD` | key inside the bundle |
| `db_port` | no | `5432` | |
| `db_ssl_mode` | no | `require` | libpq `sslmode` |
| `pg_major` | no | `18` | client major version; must be ≥ the server major |
| `dump_format` | no | `custom` | `custom` or `plain-gz` |
| `name_prefix` | no | `db` | artifact and file name prefix |
| `reason` | no | `''` | free-text note recorded in `MANIFEST.txt` |
| `retention_days` | no | `30` | artifact retention |

## Outputs

`artifact_name`, `dump_file`, `sha256`, `tables`.

## Required IAM

On `service_account`: `roles/secretmanager.secretAccessor` on `bundle_secret`.

## The dump contains your data

Whatever is in the database is in the artifact — very likely PII. The artifact
is private to repo collaborators and expires after `retention_days`. This is a
convenience/portability backup: provider-side PITR or branch snapshots remain
the stronger disaster-recovery story.

## Example caller

```yaml
name: Backup prod DB (artifact)
on:
  workflow_dispatch:
    inputs:
      reason:
        type: string
        required: false
      retention_days:
        type: number
        default: 30

permissions:
  contents: read
  id-token: write

jobs:
  backup:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/neon-backup.yml@v1.1.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_BACKUP_SA }}
      db_host: ${{ vars.DB_HOST }}
      db_port: ${{ vars.DB_PORT }}
      db_user: ${{ vars.DB_USER }}
      db_name: ${{ vars.DB_NAME }}
      db_ssl_mode: ${{ vars.DB_SSL_MODE }}
      dump_format: custom
      name_prefix: myapp
      reason: ${{ inputs.reason }}
      retention_days: ${{ inputs.retention_days }}
```

For a gzipped plain-SQL dump instead, pass `dump_format: plain-gz`.
