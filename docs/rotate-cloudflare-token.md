# rotate-cloudflare-token

Verify-only "nag". Confirms the current `CLOUDFLARE_API_TOKEN` is active and
prints an org-specific rotation runbook to the step summary. Does not mint
(that stays a manual dashboard action).

## Inputs / secrets

`zone_name` (req), `scopes_md` (req — markdown bullet lines for the custom-token
scopes), `secret_targets` (req — space-separated `org/repo` list);
secret `cloudflare_api_token` (req).

## Example caller — AutoMahn/project

```yaml
name: Rotate Cloudflare API token (nag)
on:
  workflow_dispatch: {}
  schedule:
    - cron: '0 3 15 */3 *'
jobs:
  check:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rotate-cloudflare-token.yml@v1
    with:
      zone_name: automahn.in
      secret_targets: AutoMahn/api AutoMahn/ui AutoMahn/admin-ui AutoMahn/website
      scopes_md: |
        - **Account → Cloudflare Pages → Edit**
        - **Account → Workers Scripts → Edit**
        - **Account → R2 → Edit**
        - **Zone → DNS → Edit** (scope: `automahn.in`)
        - **Zone → Zone → Read** (scope: `automahn.in`)
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

Traide-Co/project: `zone_name: traide.co.in`, its own repo list, Pages+DNS+Zone scopes.
