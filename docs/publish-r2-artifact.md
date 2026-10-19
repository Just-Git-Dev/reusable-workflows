# `publish-r2-artifact.yml`

Publish the files of a GitHub Actions **artifact** to an R2 bucket under
`<prefix>/<version>/`, and advance `<prefix>/latest/` — **only forward**. Version objects are
immutable; a re-run of the same release is a safe no-op.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/publish-r2-artifact.yml@v3.6.1
```

Talks to R2 through its S3-compatible API (`aws s3api`, endpoint
`https://<account_id>.r2.cloudflarestorage.com`, region `auto`) with an S3 access key pair.
The bucket and its public address come from [`bootstrap-r2-bucket`](bootstrap-r2-bucket.md).

## What a run does

1. **Validate** `version` (`^v[0-9]+\.[0-9]+\.[0-9]+$`, no pre-releases), `prefix` (no leading
   or trailing slash, no `..`, no empty segment) and the rest of the inputs.
2. **Download** the artifact and inventory it: records every file's sha256, prints
   `examined N file(s)`, and **fails on 0 files**.
3. **Publish the version objects** to `<prefix>/<version>/<file>`, each with a
   `<file>.sha256` beside it.
4. **Decide whether `latest/` moves** (`update_latest`).
5. **Advance `latest/`**, if it moves.
6. **Read back** every published file through the public URL.

## The rules

### A present version object is never overwritten

Each upload records its sha256 in object metadata (`x-amz-meta-sha256`). Before writing, the
workflow does a `HeadObject` — **no download** — and decides:

| Object at the key | Result |
|---|---|
| absent | upload |
| present, recorded sha256 equals the new file's | no-op (a re-run is safe) |
| present, recorded sha256 differs | **the run fails** |
| present, no recorded sha256 | **the run fails** — it cannot be proven identical |

To ship different bytes, publish a new version.

### `latest/` only moves forward

With `update_latest: auto` the workflow reads `<prefix>/latest/version.txt`:

| `latest/version.txt` | `latest/` |
|---|---|
| absent | written |
| lower semver than `version` | written |
| equal to `version` | untouched (no-op) |
| higher than `version` | untouched — publishing an old patch release never rolls the channel back |
| not a `vX.Y.Z` string | **the run fails**; the file is corrupt and nothing is guessed |

`version.txt` is written **last**, after every other `latest/` file (and its `.sha256`), so
a reader that sees a version in it never finds a half-copied `latest/`.
`update_latest: never` skips `latest/` entirely.

Files that an older release put in `latest/` and the new one does not contain are **left in
place**; the workflow never deletes.

A job-level `concurrency:` group keyed on bucket and prefix stops two publishes from racing
on `latest/`.

### Checksums beside every file

Each published object has `<file>.sha256` in `sha256sum` format (`<hex>␣␣<basename>`), in
the version directory and in `latest/`, so `sha256sum -c file.sha256` works after a download.
Artifacts may not themselves contain `*.sha256` files, or a top-level `version.txt` — those
names are produced by the workflow.

### Cache headers

| Objects | `Cache-Control` |
|---|---|
| version objects and their `.sha256` | `public, max-age=31536000, immutable` |
| everything in `latest/`, including `version.txt` | `public, max-age=300` |

### Read-back verification

For every published file, version and `latest/`, the workflow does a public `GET` of
`<public_base_url>/<key>?cb=<run_id>-<attempt>` (the query string defeats a cached copy),
asserts HTTP `200`, and compares the sha256 of the downloaded bytes with the published one.
It retries until `readback_timeout_seconds`, then fails.

File names in the artifact are limited to `A-Za-z0-9._/-` so the key and the URL are the
same string.

## Inputs

| Input | | Default | Notes |
|---|---|---|---|
| `artifact_name` | required | | Name of the Actions artifact to publish |
| `account_id` | required | | Cloudflare account id; builds the S3 endpoint |
| `bucket` | required | | R2 bucket name |
| `prefix` | required | | Key prefix, e.g. `downloads` or `tools/cli` |
| `version` | required | | `vX.Y.Z` |
| `public_base_url` | required | | Public `https://` root that serves the bucket, no path, e.g. `https://downloads.example.com` |
| `update_latest` | optional | `auto` | `auto` or `never` |
| `readback_timeout_seconds` | optional | `120` | Per-file budget for the public read-back |
| `timeout_minutes` | optional | `20` | Job timeout |

## Secrets

| Secret | | Notes |
|---|---|---|
| `r2_access_key_id` | required | R2 S3 API token, **Object Read & Write** on this bucket |
| `r2_secret_access_key` | required | The matching secret |

## Outputs

| Output | Value |
|---|---|
| `version_url` | `<public_base_url>/<prefix>/<version>/` |
| `latest_moved` | `true` if this run advanced `latest/`, else `false` |

## Copy-paste

```yaml
name: Publish release files

on:
  push:
    tags: ['v*']

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./build.sh            # writes dist/
        shell: bash
      - uses: actions/upload-artifact@v4
        with:
          name: release-files
          path: dist/

  publish:
    needs: build
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/publish-r2-artifact.yml@v3.6.1
    with:
      artifact_name: release-files
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      bucket: my-bucket
      prefix: downloads
      version: ${{ github.ref_name }}
      public_base_url: https://downloads.example.com
    secrets:
      r2_access_key_id: ${{ secrets.R2_ACCESS_KEY_ID }}
      r2_secret_access_key: ${{ secrets.R2_SECRET_ACCESS_KEY }}
```

## Concurrency

`publish-r2-<bucket>-<prefix>`, without `cancel-in-progress`, declared on the **job**. One
publisher per bucket and prefix at a time, because `latest/` is read, compared and then
rewritten.
