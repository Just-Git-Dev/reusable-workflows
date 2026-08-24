# `bootstrap-cf-dns.yml`

Converge DNS records — and optionally Origin Rules — on **one** Cloudflare zone. Idempotent:
every record is upserted, and re-running changes nothing.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-cf-dns.yml@v2.4.1
```

## This or `bootstrap-cf-service`?

| You want to… | Use |
|---|---|
| Give one Cloud Run service a public hostname | [`bootstrap-cf-service`](bootstrap-cf-service.md) |
| Manage the zone's own records — apex, verification TXT, worker routes | **this one** |
| Steer proxied hostnames at an origin with Origin Rules | **this one** |

They are designed to coexist on one zone. See [Origin Rules](#origin-rules) for the part
that makes that true.

## `records`

A JSON array. Each entry:

| Key | | Notes |
|---|---|---|
| `type` | required | `CNAME`, `A`, `AAAA`, `TXT`, `MX`, … |
| `name` | required | Short (`api`), fully-qualified (`api.example.com`), or `@` for the apex |
| `content` | required | The record value |
| `proxied` | optional, `false` | Cloudflare-proxied (orange cloud) |
| `ttl` | optional, `1` | `1` means automatic |
| `priority` | optional | MX/SRV |
| `comment` | optional | Shown in the Cloudflare dashboard |
| `replaces` | optional | Array of record **types** to delete at this name first |

```yaml
records: |
  [
    {"type":"AAAA","name":"files","content":"100::","proxied":true,
     "comment":"Worker route — files CDN"},
    {"type":"CNAME","name":"api","content":"ghs.googlehosted.com",
     "replaces":["AAAA"],"comment":"Cloud Run custom domain"}
  ]
```

### Every entry is validated before anything is written

A run that creates three records and then dies on a malformed fourth leaves the zone in a
state nobody declared. Missing `type`/`name`/`content` fails up front, naming the index.

### TXT records are matched on content, not just name

Several TXT records legitimately share one name — SPF, DMARC, and one verification token per
vendor. Matching on name+type alone would overwrite a sibling token belonging to someone
else, so TXT is matched on `name` + `type` + `content`: a new value is **added**, and only an
exact content match is updated in place.

### `replaces` is the only thing that deletes

Nothing is removed unless a record asks for it. `replaces: ["AAAA"]` is how a hostname moves
between routing models — off an `AAAA` worker route onto a `CNAME`, say — where leaving the
old type behind would keep resolving the old path.

## Origin Rules

```yaml
origin_rules: |
  [
    {"hostname":"api.example.com","host_header":"svc-abc-as.a.run.app"},
    {"hostname":"api-cr.example.com","host_header":"svc-abc-as.a.run.app"}
  ]
```

| Key | | Notes |
|---|---|---|
| `hostname` | required¹ | Matched exactly |
| `expression` | optional¹ | Raw Cloudflare filter expression, overriding `hostname` |
| `host_header` | required | The `Host` sent to the origin |
| `origin_host` | optional | Defaults to `host_header` |
| `origin_port` | optional, `443` | |
| `sni` | optional | Defaults to `origin_host` |
| `description` | optional | |

¹ one of `hostname` or `expression`.

Empty (the default) leaves the ruleset completely alone — it is not even read.

### Undeclared rules are preserved by default

A zone has exactly **one** entrypoint ruleset for the `http_request_origin` phase, and the
API writes it as a whole document. `bootstrap-cf-service` splices its own per-hostname rule
into that same document.

So this workflow edits **by expression**: rules it declares are upserted, and every rule it
does not declare is kept, with server-assigned fields (`id`, `version`, `last_updated`,
`ref`) stripped — Cloudflare 400s if those are echoed back.

> **This is a deliberate change from the inline predecessor**, which did a full-ruleset PUT
> and replaced whatever was there. On a zone where anything else also writes Origin Rules,
> that silently deleted the other writer's rules on every run.

`prune_unmanaged_origin_rules: true` restores the declarative behaviour: the zone's Origin
Rules become exactly what the run declared, and anything else is deleted. It logs a warning
naming every rule it drops. Use it only on a zone whose Origin Rules are owned solely by this
caller — never alongside `bootstrap-cf-service` on the same zone.

## Token scopes

`Zone:Zone:Read` + `Zone:DNS:Edit` for records; `Zone:Rulesets:Edit` additionally for
`origin_rules`. A `not entitled to use the HostHeader override` error means the zone is on
the Free plan — `host_header` is a Pro entitlement.

## Copy-paste

```yaml
name: Bootstrap zone DNS

on:
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Print the plan without changing anything'
        required: false
        type: boolean
        default: true

permissions:
  contents: read

jobs:
  dns:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-cf-dns.yml@v2.4.1
    with:
      cf_zone_name: example.com
      dry_run: ${{ inputs.dry_run }}
      records: |
        [
          {"type":"AAAA","name":"files","content":"100::","proxied":true,
           "comment":"Worker route — files CDN"},
          {"type":"CNAME","name":"api","content":"ghs.googlehosted.com",
           "replaces":["AAAA"],"comment":"Cloud Run custom domain"},
          {"type":"TXT","name":"@","content":"verify=abc123",
           "comment":"Domain claim"}
        ]
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

Run it with `dry_run: true` first and read the plan — it prints every create, update and
delete it would perform.

## Concurrency

`bootstrap-cf-dns-<zone>`, without `cancel-in-progress`. Per **zone**, not per record: every
write and the single Origin Rule entrypoint belong to one zone, and that entrypoint is
read-modify-written whole.
