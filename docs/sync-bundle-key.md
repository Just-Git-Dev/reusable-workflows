# sync-bundle-key

Upserts one or more keys into the `app-secrets` Secret Manager bundle, adds a
new version, rolls the given Cloud Run service(s) onto `:latest`, and disables
the previous version. Replaces the per-org `rotate-db-redis-passwords` and
`rotate-r2-token` workflows.

The payload is a single JSON secret whose **keys are the destination bundle
keys** — this absorbs both the number of keys and the cross-app naming drift
(`FILE_STORE_*` vs `FILE_STORAGE_*`). Build it with `toJSON()` so values stay
masked.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `gcp_project` | input (req) | — | |
| `gcp_region` | input | `asia-southeast1` | |
| `wif_provider` / `service_account` | input (req) | — | |
| `bundle_secret` | input | `app-secrets` | |
| `mount_path` | input | `/app/configs/.prod.env` | Traide uses `/app/configs/.env` |
| `services_csv` | input (req) | — | e.g. `automahn-api,automahn-cron` |
| `title` | input | `secrets` | label for the summary |
| `payload_json` | **secret** (req) | — | `{"DEST_KEY": value, ...}` |

## Example caller — AutoMahn/project DB + Redis

```yaml
name: Sync DB + Redis passwords
on: { workflow_dispatch: {} }
jobs:
  sync:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/sync-bundle-key.yml@v1
    with:
      gcp_project: auto-mahn
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_ROTATOR_SA }}
      services_csv: automahn-api,automahn-cron
      mount_path: /app/configs/.prod.env
      title: DB + Redis passwords
    secrets:
      payload_json: |
        {"DB_PASSWORD": ${{ toJSON(secrets.DB_PASSWORD) }},
         "REDIS_PASSWORD": ${{ toJSON(secrets.REDIS_PASSWORD) }}}
```

## Example caller — Traide-Co/project R2 credentials

```yaml
    with:
      gcp_project: traide-in
      service_account: ${{ vars.GCP_INFRA_SA }}
      services_csv: traide-api
      mount_path: /app/configs/.env
      title: R2 credentials
    secrets:
      payload_json: |
        {"FILE_STORAGE_ACCESS_KEY": ${{ toJSON(secrets.R2_ACCESS_KEY_ID) }},
         "FILE_STORAGE_SECRET_KEY": ${{ toJSON(secrets.R2_SECRET_ACCESS_KEY) }}}
```

(AutoMahn's R2 caller uses `FILE_STORE_ACCESS_KEY` / `FILE_STORE_SECRET` — the
destination key names are chosen entirely in the caller's payload.)
