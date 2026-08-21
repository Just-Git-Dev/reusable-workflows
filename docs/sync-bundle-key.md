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

Superseded secret versions are disabled **only after every service has rolled
successfully**. If any roll fails, the job fails with the old version still
enabled, so no running service is left pointing at a disabled secret version.
Re-run after fixing the cause; the disable happens on the next green run.

## Version retention — `keep_enabled_count`

The disable step keeps the newest `keep_enabled_count` ENABLED versions and
disables everything older. It **never destroys**; see
[cleanup-secret-versions](cleanup-secret-versions.md) for that.

| Value | Effect |
|---|---|
| `1` (default) | only the version this run wrote stays ENABLED |
| `2` | the previous version stays ENABLED as a rollback target needing no re-enable |
| `0` | **rejected** — it would disable every version and leave `latest` unresolvable |

`latest` resolves server-side to the newest ENABLED version, so the newest is
never in the disable set and this step cannot silently repoint it.

**Behaviour note for existing callers.** At the default of `1` this is identical
to the previous single-version disable *whenever the secret carries no
pre-existing ENABLED tail* — which is the steady state these workflows
themselves maintain. If a tail does exist (a hand-added version, or one written
by `manage-config-secrets`), the first run now disables all of it and emits a
`::warning::` naming the count. That is reversible with `gcloud secrets versions
enable`; per [AGENTS.md §5](../AGENTS.md) dry-run both pins and compare before
upgrading if the secret has been written outside these workflows.

## Serialisation — one lock across all three bundle writers

`sync-bundle-key`, `rotate-signing-keypair` and `rotate-worker-signing-secret`
each read the latest version of the same `app-secrets` bundle, patch one or two
keys, and add a new version. They therefore declare an **identical**
`concurrency.group`:

```yaml
group: bundle-write-${{ inputs.gcp_project }}-${{ inputs.bundle_secret }}
```

so any two of them queue rather than interleave. Before v2.3.1 the three used
three different prefixes: two concurrent runs both read version N and the second
write silently dropped the first one's keys. `cancel-in-progress` is `false` — a
writer cancelled mid-run may already have added a version.

The group is keyed on the **blob**, never on `bundle_key`: two runs patching
different keys still collide on the whole-blob read-modify-write.

**Caveat.** GitHub scopes a concurrency group to the repository that declares it,
which for a called workflow is the **caller's** repo. Two different caller repos
writing the same bundle are not serialised by this; give one repo ownership of a
bundle if that is a real risk.

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
| `min_value_length` | input | `8` | refuse the run if any payload value is shorter than this; `0` disables |
| `keep_enabled_count` | input | `'1'` | keep this many newest ENABLED versions, disable the rest; minimum `1` |
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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/sync-bundle-key.yml@v2.4.0
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
