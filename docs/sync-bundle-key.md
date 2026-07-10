# sync-bundle-key

Upserts one or more keys into a Secret Manager **bundle** secret (a dotenv blob
of `KEY=value` lines, mounted into Cloud Run as a file), adds a new secret
version, rolls the named Cloud Run service(s) onto `:latest`, and disables the
previous version.

The payload is a single JSON secret whose **keys are the destination bundle
keys**. That absorbs both the number of keys and any naming drift between apps,
so one workflow covers every rotation without branching. Build it with
`toJSON()` so the values stay masked in logs.

## Ordering contract

The previous secret version is disabled **only after every service has rolled
successfully**. If any roll fails, the job fails with the old version still
enabled, so no running service is left pointing at a disabled secret version.
Re-run after fixing the cause; the disable happens on the next green run.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `gcp_project` | input (req) | — | |
| `wif_provider` / `service_account` | input (req) | — | |
| `gcp_region` | input | `asia-southeast1` | region of the Cloud Run services |
| `bundle_secret` | input | `app-secrets` | |
| `mount_path` | input | `/app/configs/.prod.env` | container path the bundle is mounted at |
| `services_csv` | input (req) | — | comma-separated Cloud Run service names |
| `title` | input | `secrets` | label for the run summary |
| `dry_run` | input | `false` | validate + print the plan; write nothing |
| `payload_json` | **secret** (req) | — | `{"DEST_KEY": "value", ...}` |

## Outputs

`old_version`, `new_version`, `services_rolled`.

## Required IAM

On `service_account`: `roles/secretmanager.secretVersionManager` and
`roles/secretmanager.secretAccessor` on `bundle_secret`, plus
`roles/run.developer` on the target services.

## Example caller

```yaml
name: Sync DB + Redis passwords
on:
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: false

permissions:
  contents: read
  id-token: write

jobs:
  sync:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/sync-bundle-key.yml@v1.1.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_ROTATOR_SA }}
      services_csv: myapp-api,myapp-cron
      mount_path: /app/configs/.prod.env
      title: DB + Redis passwords
      dry_run: ${{ inputs.dry_run }}
    secrets:
      payload_json: |
        {"DB_PASSWORD": ${{ toJSON(secrets.DB_PASSWORD) }},
         "REDIS_PASSWORD": ${{ toJSON(secrets.REDIS_PASSWORD) }}}
```

The same workflow rotates object-storage credentials — only the payload keys
change, and they are chosen entirely by the caller:

```yaml
    with:
      services_csv: myapp-api
      title: Object storage credentials
    secrets:
      payload_json: |
        {"FILE_STORAGE_ACCESS_KEY": ${{ toJSON(secrets.S3_ACCESS_KEY_ID) }},
         "FILE_STORAGE_SECRET_KEY": ${{ toJSON(secrets.S3_SECRET_ACCESS_KEY) }}}
```

## Notes

- Payload values must be JSON strings. Numbers and booleans are rejected up
  front rather than silently stringified into the bundle.
- Values are base64-encoded on the way through the shell, so newlines and shell
  metacharacters survive intact.
- The local copy of the bundle is removed in an `always()` step.
