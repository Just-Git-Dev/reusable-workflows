# rotate-worker-signing-secret

Rotates an HMAC signing secret shared between a **Cloudflare Worker** that
*verifies* signed URLs and a **backend** that *signs* them from a Secret Manager
bundle mounted into Cloud Run. Zero-downtime: URLs already signed with the old
secret keep verifying until they expire.

Typical shape — a Worker fronting an R2 bucket that streams objects only for URLs
of the form `https://files.example.com/<key>?exp=<unix>&sig=<hmac>`, where
`sig = HMAC-SHA256(secret, "<key>|<exp>")`. The signer and verifier must agree on
the secret; rotating it naively would reject every URL already in flight.

## How the grace window works

The Worker is expected to verify against a **primary** slot, then fall back to a
**previous** slot when that binding is set:

```js
ok = eq(hmac(env.PRIMARY, data), sig)
     || (env.PREVIOUS && eq(hmac(env.PREVIOUS, data), sig))
```

The rotation drives both sides through an overlap:

1. Generate a new secret (`openssl rand -hex <secret_bytes>`).
2. Write it into the bundle under `bundle_key`, add a new SM version, and roll
   the Cloud Run service(s) — **the signer now emits new-secret URLs.**
3. Set the Worker `PREVIOUS` slot = old secret, `PRIMARY` slot = new secret —
   **the verifier now accepts both.**
4. Sleep `grace_seconds`, long enough for every old-signed URL to expire.
5. Delete the `PREVIOUS` slot and disable the old SM version.

## Ordering & safety contract

- **Signer moves before the verifier narrows.** The Cloud Run roll (step 2)
  happens before the `PRIMARY` slot is overwritten (step 3), and the old secret
  is preserved in `PREVIOUS` for the whole grace window — so there is no instant
  at which a freshly minted URL can't be verified.
- **`grace_seconds` must exceed your longest signed-URL TTL**, not just the
  default one. If any caller mints URLs with a longer expiry, size grace to that.
- **Roll-forward rollback.** If the run fails *before the Cloud Run roll
  succeeds*, the new SM version is reverted by adding a fresh version with the
  prior content (never by disabling `latest`, which would strand the `:latest`
  mount). If the failure lands *after* the signer moved over — on grace or
  cleanup — SM is deliberately left alone, because reverting then would break
  signing.
- **Cleanup is non-fatal.** Removing the `PREVIOUS` slot and disabling the old
  SM version tolerate errors; after grace they are unused either way. Cloudflare
  error bodies are surfaced (never swallowed by `curl -f`).

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `gcp_project` | input (req) | — | holds the bundle secret + Cloud Run services |
| `wif_provider` / `service_account` | input (req) | — | |
| `gcp_region` | input | `asia-southeast1` | region of the services |
| `bundle_secret` | input | `app-secrets` | dotenv bundle secret |
| `bundle_key` | input (req) | — | key inside the bundle to rotate |
| `mount_path` | input | `/app/configs/.prod.env` | container path the bundle mounts at |
| `services_csv` | input (req) | — | comma-separated Cloud Run service names |
| `cf_account_id` | input (req) | — | Cloudflare account owning the Worker |
| `cf_worker_script` | input (req) | — | Worker script name that verifies |
| `cf_primary_secret_name` | input (req) | — | Worker binding for the current secret |
| `cf_previous_secret_name` | input | `<primary>_PREVIOUS` | Worker binding used during grace |
| `grace_seconds` | input | `900` | **must be > longest signed-URL TTL** |
| `secret_bytes` | input | `32` | generated secret length (hex, so 2x chars) |
| `bootstrap` | input | `false` | tolerate a missing secret / missing services on first run; no grace, no disable |
| `dry_run` | input | `false` | print the plan; generate/write/roll nothing |
| `cloudflare_api_token` | **secret** (req) | — | needs Workers Scripts:Edit on `cf_account_id` |

## Outputs

`old_version`, `new_version`.

## Required IAM

On `service_account`: `roles/secretmanager.secretVersionManager` and
`roles/secretmanager.secretAccessor` on `bundle_secret`, plus
`roles/run.developer` on the target services. The Cloudflare token needs
**Workers Scripts:Edit** on the account.

## Example caller

```yaml
name: Rotate files signing secret
on:
  workflow_dispatch: {}
  schedule:
    - cron: '0 3 1 */3 *'   # quarterly

permissions:
  contents: read
  id-token: write

concurrency:
  group: secrets-rotation
  cancel-in-progress: false

jobs:
  rotate:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rotate-worker-signing-secret.yml@v1.2.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_ROTATOR_SA }}
      bundle_secret: app-secrets
      bundle_key: FILES_SIGNING_SECRET
      services_csv: myapp-api,myapp-cron
      cf_account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      cf_worker_script: myapp-files-cdn
      cf_primary_secret_name: FILES_CDN_SIGNING_SECRET
      grace_seconds: 900
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

## Notes

- The `bundle_key` (backend/dotenv name) and `cf_primary_secret_name` (Worker
  binding name) are independent — they need not match, and often don't.
- On a `bootstrap: true` run the grace and disable steps are skipped, so a
  first-time setup never blocks on services or a bundle that don't exist yet.
  Run scheduled rotations with `bootstrap: false`.
- The local copies of the bundle are removed in an `always()` step.
