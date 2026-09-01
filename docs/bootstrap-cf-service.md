# `bootstrap-cf-service.yml`

Give a Cloud Run service a public hostname on a Cloudflare zone. Idempotent — safe to
re-run; nothing is created twice.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-cf-service.yml@v2.6.0
```

## Pick a mode

|  | `dns-only` | `proxied` |
|---|---|---|
| What resolves the name | Cloud Run **domain mapping** + DNS-only CNAME → `ghs.googlehosted.com` | **Proxied** CNAME → the service's `*.run.app` host |
| Who terminates TLS | Google (managed cert) | Cloudflare |
| Also creates | — | An **Origin Rule** rewriting the Host header |
| Cloudflare plan | Any, including **Free** | **Pro or higher** |
| You get WAF / cache / rate-limiting | ✗ | ✓ |

**`proxied` requires Cloudflare Pro.** `host_header` on an Origin Rule is a paid
entitlement; on Free the rules API returns `400 — not entitled to use the HostHeader
override`. The workflow says so explicitly when that happens, rather than surfacing a raw
400.

### Why `proxied` needs an Origin Rule at all

Cloud Run routes by `Host`. A proxied request reaches the origin carrying the *user-facing*
host (`img.example.com`), which Cloud Run does not recognise — unless a domain mapping
registers it, and creating one defeats the point of proxying. So the Host is rewritten to
the canonical `*.run.app` name, which Cloud Run always accepts as the service's own
identity.

## Inputs

`catalog.json` is the authoritative contract. The ones that carry a decision:

| Input | Default | Notes |
|---|---|---|
| `mode` | *required* | `dns-only` or `proxied`. Anything else fails immediately. |
| `hostname` | *required* | The public name, e.g. `img.example.com`. |
| `cf_zone_name` | *required* | Apex zone; the zone id is looked up from it. |
| `service` | `''` | Required for `dns-only`, and for a `proxied` run that resolves its own origin. |
| `cloud_run_url` | `''` | **Prefer leaving empty** — see below. |
| `wif_provider` / `service_account` / `gcp_project` | `''` | Required unless `proxied` **and** `cloud_run_url` is set. |
| `dry_run` | `false` | Prints the zone id, the DNS record and the Origin Rule it would write. |
| `wait_for_certificate` | `true` | `dns-only` only. A timeout **warns**, see below. |
| `check_ssl_mode` | `true` | `proxied` only. Warns, never flips. |
| `smoke_path` / `smoke_status` | `''` / `''` | Probe after bootstrapping. |

### Leave `cloud_run_url` empty

It is read from the live service with `gcloud run services describe`, and the scheme is
stripped (it is used as a CNAME target and a Host header — `https://…` is valid as neither).

Setting it by hand is supported for the one case that has no GCP access at all, but it is a
standing hazard: the `*.run.app` host changes when a service is recreated, and a stale value
points the Origin Rule at a dead origin with nothing failing until traffic does. The inline
predecessor of this workflow required the operator to paste it on every run.

### The certificate wait warns, it does not fail

Google issues the managed cert once it observes the CNAME, typically 5–30 minutes on a first
provision and instantly on re-runs. On timeout the workflow **warns and succeeds**: the
domain mapping and the DNS record are already correct at that point, and the cert lands on
Google's schedule. Failing there would make a green run mean "Google was quick today".

### The SSL-mode check warns, it does not fix

SSL/TLS mode is **zone-wide**. A per-service workflow must not flip a zone-wide setting, so
it reports and moves on. Anything below Full breaks certificate validation to the
`*.run.app` origin and leaves a man-in-the-middle gap between Cloudflare and Google — worth
fixing, but not from here. If the token cannot read zone settings the check is skipped, not
failed.

## IAM and token scopes

**On `service_account`** — stated as permissions, not role names; all can be held at
resource scope:

| Permission | When |
|---|---|
| `run.services.get` | Resolving the `*.run.app` URL (`roles/run.viewer` covers it) |
| `run.domainmappings.create`, `run.domainmappings.get` | `mode: dns-only` (needs `roles/run.admin` or a custom role) |

A `proxied` caller that passes `cloud_run_url` explicitly needs **no GCP access**: leave
`wif_provider`/`service_account` empty and no auth step runs at all.

**Cloudflare API token:** `Zone:Zone:Read` + `Zone:DNS:Edit` (both modes),
`Zone:Rulesets:Edit` (`proxied`), `Zone:Zone Settings:Read` (optional, for the SSL check).

## Copy-paste

```yaml
name: Bootstrap a service hostname

on:
  workflow_dispatch:
    inputs:
      hostname:
        description: 'Public hostname, e.g. img.example.com'
        required: true
        type: string
      service:
        description: 'Cloud Run service name'
        required: true
        type: string
      dry_run:
        description: 'Print the plan without changing anything'
        required: false
        type: boolean
        default: true

permissions:
  contents: read
  id-token: write

jobs:
  bootstrap:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-cf-service.yml@v2.6.0
    with:
      mode: dns-only
      hostname: ${{ inputs.hostname }}
      service: ${{ inputs.service }}
      cf_zone_name: example.com
      gcp_project: my-project
      gcp_region: asia-southeast1
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_ROTATOR_SA }}
      dry_run: ${{ inputs.dry_run }}
      smoke_path: /healthz
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

Switch to `mode: proxied` on a Pro zone; `service` still resolves the origin host, so no
`*.run.app` value needs pasting.

## Concurrency

`bootstrap-cf-service-<hostname>` without `cancel-in-progress`. Two runs against one
hostname would race on the same DNS record **and** on the zone's Origin Rule entrypoint —
which is read-modify-written as a whole document, so the loser's rule vanishes silently.
Different hostnames never contend.

## The Origin Rule splice

There is exactly one entrypoint ruleset per phase per zone, and it is written whole. The
workflow therefore reads it, drops any prior rule matching **this** hostname, strips
server-assigned fields (`id`, `version`, `last_updated`, `ref` — Cloudflare 400s if they are
echoed back), appends the fresh rule, and PUTs the result. Consequences worth knowing, each
covered by a step test:

- **Rules for other hostnames survive.** Losing them would be a silent zone-wide outage.
- **Re-running refreshes in place** rather than stacking a second rule for the same host.
- If no entrypoint ruleset exists yet, one is created for the `http_request_origin` phase.
