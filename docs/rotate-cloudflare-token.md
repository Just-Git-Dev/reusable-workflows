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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rotate-cloudflare-token.yml@v1.1.0
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
