# image-identity

A **composite action** that proves "the image the smoke job tests is exactly the image the
pull job pulled", across two jobs that may run on different runner images. It has two modes,
`record` and `verify`, of one action.

It replaces the hand-rolled check that compared `docker image inspect --format '{{.Id}}'` in
the pulling job with the same command after `docker load` in the consuming job. That check
reports a mismatch for identical bytes when the two jobs use different Docker image stores
(see [Why not `.Id`](#why-not-id)).

```yaml
name: Release smoke
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  pull:
    runs-on: ubuntu-latest
    outputs:
      tar_sha256: ${{ steps.rec.outputs.tar_sha256 }}
      identity: ${{ steps.rec.outputs.identity }}
    steps:
      - name: Pull the images under test
        shell: bash
        run: docker pull alpine:3.20
      - id: rec
        uses: Just-Git-Dev/reusable-workflows/actions/image-identity@v6.3.0
        with:
          mode: record
          images: |
            alpine:3.20
          path: ${{ runner.temp }}/images.tar
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: images
          path: ${{ runner.temp }}/images.tar
          retention-days: 1
  smoke:
    needs: pull
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          name: images
          path: ${{ runner.temp }}/in
      - uses: Just-Git-Dev/reusable-workflows/actions/image-identity@v6.3.0
        with:
          mode: verify
          path: ${{ runner.temp }}/in/images.tar
          tar_sha256: ${{ needs.pull.outputs.tar_sha256 }}
          identity: ${{ needs.pull.outputs.identity }}
      - name: Smoke test the loaded image
        shell: bash
        run: docker run --rm --pull never alpine:3.20 true
```

The two jobs deliberately run on different labels here to show that this is safe. The
`--pull never` in the smoke step makes sure it runs the loaded, verified image and never fetches
one from the registry.

## The two modes

`mode` is required and must be `record` or `verify`; any other value is an error. Both modes
print the runner's image store (`image store: classic`, `containerd` or `unknown`) to the log,
for diagnosis only.

**`record`** runs in the job that pulled the images.

1. Every ref in `images` must be a tag (see [Refs](#refs)); a digest ref is refused before
   anything is saved.
2. `docker save` of every ref into ONE tarball at `path`, then the `sha256` of that tarball.
3. For each ref, the **config digest** is read from the tarball's own `manifest.json`. The file
   has a different layout per store, and both are understood: the classic one
   (`"Config": "<hex>.json"`) and the containerd/OCI one (`"Config": "blobs/sha256/<hex>"`).
   Refs are matched to entries through `RepoTags`.
4. `RepoDigests[0]` of each ref is read from `docker image inspect`. It is recorded for tracing
   and never compared, but it must exist: an image with no registry digest (built locally, not
   pulled) is refused, because this action exists to prove what was *pulled*.
5. The identity JSON is also written next to the tarball, as `<path>.identity.json`. That copy
   is optional: upload it beside the tarball if you want a durable record of what was verified.
   `verify` reads only its `identity` input, never this file.

**`verify`** runs in the consuming job, after the artifact is downloaded.

1. The tarball is hashed again and must equal `tar_sha256`.
2. `docker load` of the tarball.
3. Every ref named in `identity` must be present after the load.
4. The config digests are printed to `$GITHUB_STEP_SUMMARY`. They are not compared again: the
   hash match already implies them, because they are read from inside the hashed tarball.

## Inputs and outputs

| Name | Mode | Kind | Meaning |
|---|---|---|---|
| `mode` | both | input, required | `record` or `verify` |
| `path` | both | input, required | Tarball path: written by `record`, read by `verify` |
| `images` | record | input | Newline-separated image refs (tags), all already pulled. Must not be empty |
| `tar_sha256` | verify | input | The `tar_sha256` output of `record` |
| `identity` | verify | input | The `identity` output of `record` |
| `tar_sha256` | record | output | sha256 of the tarball (64 lowercase hex) |
| `identity` | record | output | Compact JSON `{"<ref>": {"config": "sha256:<hex>", "repo_digest": "<repo@sha256:...>"}}` |

## Refs

Refs are matched to the manifest through `RepoTags`, so each ref in `images` must be a tag
(`name:tag`; a bare name means `:latest`). `docker save` of a `name@sha256:...` ref writes no
`RepoTags`, so `record` refuses any ref containing `@`. To pin by digest, pull the digest,
`docker tag` it to a local tag, record that tag, and use **the same tag** in every later step:

```bash
docker pull "registry.example/app@sha256:<hex>"
docker tag "registry.example/app@sha256:<hex>" app-under-test:1
# images: app-under-test:1   ...and later: docker run --pull never app-under-test:1
```

## Fails closed

Every one of these is a non-zero exit with an `::error::` line, and two empty values are never
treated as equal:

- `mode` that is not `record` or `verify`;
- an empty input: `images`, `path`, `tar_sha256` or `identity`;
- a digest ref in `images`;
- `docker save` or `docker load` failing;
- a `manifest.json` that is missing, unparseable, empty, or has a `Config` in neither layout;
- a ref that is not in the tarball's manifest;
- a ref with no `RepoDigests[0]`;
- a `tar_sha256` that is not 64 hex characters, or a missing tarball;
- an `identity` that is not a non-empty JSON object, or an entry with no config digest;
- a hash mismatch;
- a ref missing after `docker load`.

**A trap with job outputs:** GitHub drops a job output that contains a secret's value. If any
image ref contains a string that is also a secret (a registry project id kept as a secret, for
example), `identity` reaches the consuming job empty and `verify` fails with "input identity is
empty". The fix is to stop keeping that non-secret value as a secret.

## Why not `.Id`

`docker image inspect --format '{{.Id}}'` depends on which image store the Docker daemon uses:

- the **classic** store (`ubuntu-24.04` runners) reports the **config digest**;
- the **containerd** image store (`ubuntu-26.04`, which is the current `ubuntu-latest`) reports
  the **manifest or index digest**.

The bytes are the same and the `.Id` is not. A consumer's release run hit this on 2026-11-11.
The pull job ran on `ubuntu-latest`, which had moved to 26.04, and recorded an `.Id` equal to the
`RepoDigest`. The smoke job had been pinned to `ubuntu-24.04` (Playwright does not install on
26.04). It loaded the very same tarball and reported a different `.Id`, so the "smoke tests
exactly what was pulled" check failed a release. An earlier run with both jobs on the same store
had matched.

This action never reads `.Id`. The tarball's layout differs by store, but the config digest
read from its `manifest.json` does not, and the tarball's sha256 is the proof the bytes did not
change between the jobs.

## The runner lint after adoption

The workflow-preflight `runners` lint reads `docker save`, `docker load`, `docker image inspect`
and `{{.Id}}` only in a job's own `run:` steps, never inside a `uses:` action. Its silence about
the docker work inside this action is correct, because the action does not depend on the image
store. But it means a `0 findings` from the lint no longer proves your own steps are right:

- **Delete every `.Id` read when you switch.** The lint flags `{{.Id}}` only when it comes after
  a `docker load` in the same job's `run:` text. Once the load happens inside this action, a
  leftover `.Id` comparison is not flagged, and `verify` does not check it either.
- **Every job that loads the tarball must call `mode: verify`.** The lint finds the saving job by
  its own `docker save`. Once that job calls `record`, the runner-split check no longer sees the
  pair, so a loader that skips `verify` gets neither a finding nor a hash check.
- A job that calls the action and also runs `docker load`, `docker save` or
  `docker image inspect` itself is still checked for those steps as before.

For that pair, `verify` is then the only check that both jobs handled the same bytes. To show the
lint did work on your tree, run it once on the workflow from before the switch, in a scratch copy
of the repo with the old file in `.github/workflows/`:
`python3 scripts/workflow_preflight.py runners`. Read the `WARN` lines and the
`runners: examined … K findings` line: in report-only mode the final `ok:` line reads
`0 finding(s)` even when the lint fired. If the old workflow read the digest some other way
(`{{.ID}}`, a jq read, save and load in different workflows), the lint misses it there too, so
check that by hand.

## Verification

`tests/test_image_identity.py` (`make image-identity`) builds tarballs in both layouts by hand,
and covers every failure above that does not need a real daemon, with no Docker. This repo's CI
also has four jobs for the real round trip both ways: record on `ubuntu-24.04` and verify on
`ubuntu-latest`, then the reverse. Each side prints its `image store:` line, which is how a run
shows it really crossed stores. The jobs do not assert the store, so if both labels ever share a
store they still pass but no longer test the crossing.
