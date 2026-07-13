# rotate-signing-keypair

Rotates an **RS256 asymmetric signing keypair** (JWT-shaped by default) held in a
Secret Manager **bundle** mounted into Cloud Run. Generates a fresh keypair and a
`kid`, upserts the private key / public key / key id into the bundle, adds a new SM
version, rolls the named Cloud Run service(s) onto it, and disables the old version.

## No grace window — and when NOT to use this

Unlike [`rotate-worker-signing-secret`](rotate-worker-signing-secret.md), there is
**no dual-slot overlap**. Asymmetric JWTs carry a `kid`, and short-lived tokens
churn onto the new key naturally once the signer rolls, so the old key is disabled
as soon as the Cloud Run roll succeeds.

**Do not use this if your verifier caches a single public key with no `kid`
selection**, or if tokens are long-lived — you'd reject everything signed with the
old key the moment it's disabled. That case needs the two-slot grace pattern
instead.

## Why it's standalone (not a `sync-bundle-key` caller)

The keypair is **generated inside the workflow**. A reusable workflow's outputs are
not treated as secrets, so generating the key in one workflow and passing the
private key to `sync-bundle-key` in another would print it in logs. Generation and
consumption must share one workflow — hence the ~40 lines of SM-write/roll logic
that overlap `sync-bundle-key`.

## Safety contract

- **Roll-forward rollback.** If the run fails *before the Cloud Run roll succeeds*,
  the new SM version is reverted by adding a fresh version with the prior content
  (never by disabling `latest`, which would strand the `:latest` mount). If the
  failure lands *after* the signer moved over, SM is left alone.
- **`bootstrap: true`** tolerates a missing bundle / missing services and skips the
  old-version disable, so first-run setup doesn't block. Run scheduled rotations
  with `bootstrap: false`.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `gcp_project` | input (req) | — | holds the bundle secret + Cloud Run services |
| `wif_provider` / `service_account` | input (req) | — | |
| `gcp_region` | input | `asia-southeast1` | region of the services |
| `bundle_secret` | input | `app-secrets` | dotenv bundle secret |
| `mount_path` | input | `/app/configs/.prod.env` | container path the bundle mounts at |
| `services_csv` | input (req) | — | comma-separated Cloud Run service names |
| `rsa_bits` | input | `2048` | RSA key size |
| `private_key_name` | input | `JWT_PRIVATE_KEY_BASE64` | bundle key for the base64 private PEM |
| `public_key_name` | input | `JWT_PUBLIC_KEY_BASE64` | bundle key for the base64 public PEM |
| `key_id_name` | input | `JWT_KEY_ID` | bundle key for the `kid` |
| `title` | input | `JWT signing keys` | label for the run summary |
| `bootstrap` | input | `false` | tolerate missing secret/services; skip disable |
| `dry_run` | input | `false` | print the plan; generate/write/roll nothing |

No `secrets:` — the keypair is generated in-workflow.

## Outputs

`old_version`, `new_version`, `key_id`.

The `kid` is the first 16 hex chars of `SHA-256` over the public PEM — stable for a
given key, so a JWKS builder can key on it.

## Required IAM

On `service_account`: `roles/secretmanager.secretVersionManager` and
`roles/secretmanager.secretAccessor` on `bundle_secret`, plus
`roles/run.developer` on the target services.

## Example caller

```yaml
name: Rotate JWT signing keys
on:
  workflow_dispatch: {}
  schedule:
    - cron: '0 3 2 1 *'   # annual — JWT keys rotate less often than CDN secrets

permissions:
  contents: read
  id-token: write

concurrency:
  group: secrets-rotation
  cancel-in-progress: false

jobs:
  rotate:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rotate-signing-keypair.yml@v1.2.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_ROTATOR_SA }}
      services_csv: myapp-api,myapp-cron
      title: JWT signing keys
```

## Notes

- RSA/RS256 only in this version. An EC/EdDSA variant would change only the
  `openssl genpkey` line; open an issue if you need it.
- The key values are base64-encoded PEMs, so `+`/`/`/`=` survive the dotenv bundle;
  the upsert uses `awk`, not `sed`, for the same reason.
- The private key is masked in logs and the local copies are removed in an
  `always()` step.
