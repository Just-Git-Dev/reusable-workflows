# neon-backup

pg_dump the prod Neon DB → private workflow artifact. `DB_PASSWORD` is read from
the `app-secrets` SM bundle via WIF (never a GitHub secret). Always emits a
`MANIFEST.txt` (reason, timestamp, table count, sha256) and runs integrity
checks. `dump_format` picks the format:

- `custom` — `.dump`, `pg_restore`-compatible, sanity via `pg_restore --list` (AutoMahn default)
- `plain-gz` — `.sql.gz`, sanity via `gzip -t` + header/`COPY`/`CREATE TABLE` checks (Traide)

## Key inputs

`gcp_project`, `wif_provider`, `service_account` (req); `bundle_secret`
(`app-secrets`); `db_host`/`db_user`/`db_name` (req), `db_port` (`5432`),
`db_ssl_mode` (`require`); `dump_format` (`custom`), `name_prefix` (`db`),
`reason`, `retention_days` (`30`).

## Example caller — AutoMahn/api

```yaml
name: Backup prod DB (artifact)
on:
  workflow_dispatch:
    inputs:
      reason: { type: string, required: false }
      retention_days: { type: string, default: '30' }
jobs:
  backup:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/neon-backup.yml@v1
    with:
      gcp_project: auto-mahn
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_ROTATOR_SA }}
      db_host: ${{ vars.DB_HOST }}
      db_port: ${{ vars.DB_PORT }}
      db_user: ${{ vars.DB_USER }}
      db_name: ${{ vars.DB_NAME }}
      db_ssl_mode: ${{ vars.DB_SSL_MODE }}
      dump_format: custom
      name_prefix: automahn
      reason: ${{ inputs.reason }}
      retention_days: ${{ inputs.retention_days }}
```

Traide-Co/api: same, `gcp_project: traide-in`, `service_account: ${{ vars.GCP_RELEASER_SA }}`,
`dump_format: plain-gz`, `name_prefix: neon`.
