# `bootstrap-r2-bucket.yml`

Converge **one** Cloudflare R2 bucket for public downloads: the bucket exists, a custom domain
on your zone serves it, the `r2.dev` managed public URL is **off**, and a real object round
trip proves the public path works. Idempotent: a second run changes nothing and says so.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-r2-bucket.yml@v5.1.0
```

## What a run does

| Step | Cloudflare API call | Rule |
|---|---|---|
| Ensure the bucket | `GET` then `POST /accounts/{id}/r2/buckets` | Created only if `GET` answers 404 |
| Ensure the custom domain | `GET` then `POST .../buckets/{name}/domains/custom` | Attached only if absent; re-enabled if attached but disabled; **fails** if already attached under a different zone |
| Ensure `r2.dev` is off | `GET` then `PUT .../buckets/{name}/domains/managed` | Switched off only if on |
| Probe | `PUT`/`DELETE .../buckets/{name}/objects/{key}` + public `GET`s | See below; also fails if `GET /` answers `200` (a public listing) |

Every call is checked for `success: true`; a failed call stops the run and prints
Cloudflare's own error text. Bucket and domain endpoints carry the `cf-r2-jurisdiction`
header (`jurisdiction` input).

### Why `r2.dev` is switched off

The managed `r2.dev` URL is rate-limited, uncached and meant for development. A bucket
served from a custom domain gets Cloudflare's CDN, and leaving `r2.dev` on would publish the
same objects at a second, uncontrolled address.

### The probe

1. Upload a one-line object `_probe-<run_id>-<attempt>.txt` through the Cloudflare REST API
   (`PUT .../objects/{key}`), **using the same API token** — no S3 keys are needed here.
2. `GET https://<custom_domain>/<probe key>?cb=<run_id>-<attempt>` until it answers `200`
   **with the bytes just uploaded**. A fresh custom domain needs time for ownership checks and
   its certificate, so the poll retries every `probe_poll_seconds` up to
   `probe_timeout_seconds`, then fails.
3. `GET https://<custom_domain>/` and assert it does **not** answer `200`. A bucket must not
   publish a listing of its objects; a `200` at the root is treated as a public listing and
   fails the run. Any other status (`403`, `404`, ...) passes; no answer or a `5xx` fails
   because the absence of a listing could not be verified. The check runs once, after the
   domain is serving.
4. Delete the probe — on success **and** on failure, because a probe left behind is public.
   The delete is armed *before* the upload is sent, so it also runs when the upload's response
   is lost (a timeout after the object was stored). Deleting an object that is not there
   (`404`) counts as deleted.

The REST upload endpoint is capped at 300 MB per object; a probe is a few bytes.

## Inputs

| Input | | Default | Notes |
|---|---|---|---|
| `account_id` | required | | Cloudflare account id (32 hex characters) |
| `bucket_name` | required | | 3–63 chars, lower-case letters, digits, hyphens |
| `custom_domain` | required | | Hostname to serve the bucket on, e.g. `downloads.example.com` |
| `zone_id` | required | | Id of the zone that owns `custom_domain` (32 hex characters) |
| `jurisdiction` | optional | `default` | `default`, `eu`, `us`, `fedramp` or `fedramp-high`; fixed at bucket creation |
| `location_hint` | optional | empty | `apac`, `eeur`, `enam`, `weur`, `wnam` or `oc`; only used when the bucket is **created** |
| `probe_timeout_seconds` | optional | `300` | How long to wait for the custom domain to start serving |
| `probe_poll_seconds` | optional | `15` | Seconds between probe attempts |
| `timeout_minutes` | optional | `15` | Job timeout |

## Secrets

| Secret | | Notes |
|---|---|---|
| `cloudflare_api_token` | required | See token permissions below |

### Token permissions

An **account-scoped** token with:

- **Workers R2 Storage: Edit** — create the bucket, manage its domains, upload and delete the
  probe object.
- **Zone: Zone: Read** and **Zone: DNS: Edit** on the zone named by `zone_id` — attaching a
  custom domain creates its DNS record on that zone.

Verify these against the token-permission list in the Cloudflare dashboard before first use;
a missing permission surfaces as a Cloudflare `authentication`/`permission` error naming the
failed call.

## Outputs

| Output | Value |
|---|---|
| `changed` | `true` if the run created or modified anything, else `false` |
| `bucket_created` | `true` if this run created the bucket |
| `domain_attached` | `true` if this run attached or re-enabled the custom domain |
| `public_url` | `https://<custom_domain>` |

## Copy-paste

```yaml
name: Bootstrap downloads bucket

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  bucket:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/bootstrap-r2-bucket.yml@v5.1.0
    with:
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      bucket_name: my-bucket
      custom_domain: downloads.example.com
      zone_id: ${{ vars.CLOUDFLARE_ZONE_ID }}
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

Pair it with [`publish-r2-artifact`](publish-r2-artifact.md): this workflow makes the bucket
and its public address; that one puts files in it.

## Concurrency

`bootstrap-r2-bucket-<account>-<bucket>`, without `cancel-in-progress`. Two runs against one
bucket would race on the create and the domain attach.
