# rotate-cloudflare-token

A verify-only "nag". It confirms the current `CLOUDFLARE_API_TOKEN` is still
active, warns when it is close to expiry, and prints a rotation runbook to the
step summary.

It deliberately does **not** mint a token. Minting requires the
`User -> API Tokens -> Edit` permission; a token with that permission can create
a token with any other permission, so giving it to CI would be a privilege
escalation. Rotation stays a human action in the Cloudflare dashboard.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `zone_name` | input (req) | — | DNS zone the token is scoped to; used in the runbook text |
| `scopes_md` | input (req) | — | markdown bullet lines describing the custom-token scopes |
| `secret_targets` | input (req) | — | space-separated `org/repo` list whose secret must be updated |
| `expiry_warn_days` | input | `30` | warn when the token expires within this many days |
| `cloudflare_api_token` | **secret** (req) | — | the token to verify |

## Outputs

`token_status`, `expires_on` (empty when the token never expires).

## When the verify step fails

The `check` job fails, and its message names the cause it can tell apart:

| What the step sees | Message says |
|---|---|
| the `cloudflare_api_token` secret is empty | the secret is empty or not passed to the call (nothing is sent to Cloudflare) |
| HTTP non-200 with Cloudflare error code `6003` or `6111` | the `Authorization` header was rejected as malformed — the value has stray whitespace or a newline, or is not a scoped API token (a Global API Key cannot be sent as `Bearer`) |
| any other HTTP non-200 | the token may be expired, revoked or invalid |
| HTTP 200 but `status` is not `active` | the token status, e.g. `disabled` |

Every non-200 message also lists the `code: message` pairs from Cloudflare's `errors` (and their
`error_chain`), so the raw cause is in the log even when the step cannot name it.

## Example caller

```yaml
name: Rotate Cloudflare API token (nag)
on:
  workflow_dispatch: {}
  schedule:
    - cron: '0 3 15 */3 *'   # quarterly

permissions:
  contents: read

jobs:
  check:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rotate-cloudflare-token.yml@v6.0.0
    with:
      zone_name: example.com
      secret_targets: my-org/api my-org/web
      scopes_md: |
        - **Account → Cloudflare Pages → Edit**
        - **Account → Workers Scripts → Edit**
        - **Account → R2 → Edit**
        - **Zone → DNS → Edit** (scope: `example.com`)
        - **Zone → Zone → Read** (scope: `example.com`)
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

The job fails when the token is missing, revoked, or not `active`, so a
scheduled run turns a silent future outage into a today notification.
