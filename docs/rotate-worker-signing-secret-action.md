# rotate-worker-signing-secret (composite action)

> **Deprecated since v5.2.0, removed in v6.** Use [`rotate-external-secret`](rotate-external-secret.md): it needs no GCP identity and never reads or stores the old value. This page stays until the callers have moved.

The same operation as the [`rotate-worker-signing-secret`](rotate-worker-signing-secret.md)
reusable workflow, as a **composite action** that runs as a step of the **caller's own job**. Use
it when the Cloudflare token (and the rest of the secrets) live in a GitHub **environment**
(`environment:` on the job) and the caller is in a different organisation than this repo:
environment secrets cannot cross an org boundary into a reusable workflow, but they do reach a step
of the job that declares the environment.

```yaml
- uses: Just-Git-Dev/reusable-workflows/actions/rotate-worker-signing-secret@v5.2.0
```

The action is the single source of truth. The reusable workflow is a thin wrapper that calls it
with the same inputs, secret and outputs, so the behaviour (two-slot grace window, pinned roll,
keep-set, roll-forward rollback) is documented once, in
[rotate-worker-signing-secret.md](rotate-worker-signing-secret.md). This page covers only what is
different when you call the action yourself.

## What the caller's job must declare

A composite action cannot declare `environment:`, `permissions:`, `concurrency:` or
`timeout-minutes:`. The calling job does, and the action cannot check any of it.

| Job key | Value | Why |
|---|---|---|
| `environment` | the environment holding the Cloudflare token | its secrets are what `secrets_json` carries |
| `permissions` | `contents: read`, `id-token: write` | `id-token` for the WIF login |
| `concurrency` | `group: bundle-write-<gcp_project>-<bundle_secret>`, `cancel-in-progress: false` | one lock across every writer of the same bundle blob |
| `timeout-minutes` | longer than `grace_seconds` plus the rolls (the wrapper uses `30`) | the action sets none, and the run sleeps for the whole grace window |

**Concurrency is the one that bites.** `sync-bundle-key`, `rotate-signing-keypair` and
`rotate-worker-signing-secret` each read the latest bundle version, patch a key and add a new
version; two at once silently drop each other's keys. No GitHub context exposes the running job's
concurrency group, so the action cannot detect a missing one: **every direct call prints a
`::warning::` naming the exact block**. Treat it as the reminder, not as a failure. The reusable
workflow wrapper declares the group itself and sets `concurrency_declared: 'true'`, which turns the
message into a `::notice::`; direct callers leave it unset. GitHub scopes the group to the caller's
repo, so two caller repos writing one bundle are still not serialised.

## Caller job template

```yaml
name: Rotate the files signing secret
on:
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: true     # run the dry run first: it prints the plan and writes nothing

jobs:
  rotate:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    environment: production             # the Cloudflare token lives in THIS environment
    permissions:
      contents: read
      id-token: write                   # WIF
    concurrency:
      group: bundle-write-my-gcp-project-app-secrets   # bundle-write-<gcp_project>-<bundle_secret>
      cancel-in-progress: false
    steps:
      - uses: Just-Git-Dev/reusable-workflows/actions/rotate-worker-signing-secret@v5.2.0
        with:
          secrets_json: ${{ toJSON(secrets) }}   # the action reads only cloudflare_api_token
          gcp_project: my-gcp-project
          wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
          service_account: ${{ vars.GCP_ROTATOR_SA }}
          bundle_key: FILES_SIGNING_SECRET
          mount_path: /secrets/app.env
          services_csv: myapp-api
          cf_account_id: ${{ vars.CF_ACCOUNT_ID }}
          cf_worker_script: myapp-files-cdn
          cf_primary_secret_name: SIGNING_SECRET
          grace_seconds: '900'          # must be longer than your longest signed-URL TTL
          dry_run: ${{ inputs.dry_run }}
```

The key it writes (`bundle_key`) survives `sync-bundle-key`, which is merge-only since v5.0.0 and
drops a key only when it is named in `remove_keys`.

## Inputs, secrets and outputs

Every input of the [workflow](rotate-worker-signing-secret.md#inputs--secrets) has the same name,
meaning and default here, with these differences:

- **Values are strings.** `dry_run: 'true'`, `grace_seconds: '900'`, as for any composite action.
  The workflow wrapper passes `${{ inputs.x }}`, which GitHub stringifies.
- **`secrets_json` (required)** replaces the `cloudflare_api_token` secret: set it to
  `${{ toJSON(secrets) }}` in the job that declares `environment:`. The action reads only
  `cloudflare_api_token` out of it (and not at all on a dry run); nothing else leaves its step.
  The caller must define exactly one secret named `cloudflare_api_token`; the name is matched
  case-insensitively, so `CLOUDFLARE_API_TOKEN` works.
- **Booleans are exactly `'true'` or `'false'`.** `bootstrap`, `dry_run`, `pin_versions` and
  `concurrency_declared` are checked by the first step, which refuses anything else (`yes`, `1`,
  `True`). GitHub's `if:` compares case-insensitively and bash does not, so a loose value would be
  read two ways and could turn a dry run into a live write.
- **`concurrency_declared`** is set by the wrapper only (see above).

Outputs are the workflow's: `old_version`, `new_version`.

## How secrets are handled

`secrets_json` carries registered secrets, so their values stay masked in the log. The action also
runs `::add-mask::` on every value it derives: the Cloudflare token, the generated signing secret
and the old one read from the bundle. They travel between steps as step outputs and reach a script
only through `env:` (`NEW_SECRET`, `OLD_SECRET`, `CF_API_TOKEN`), read as `"$VAR"`. **No secret is
ever written into a `run:` body with `${{ }}`**: that would put the value in the script text
before bash runs, and a value with shell metacharacters would execute. The Worker payload is built
with `jq --arg`, so any value stays valid JSON. `tests/run_rotator_action_tests.py` enforces both.

## Layout

```text
actions/rotate-worker-signing-secret/
  action.yml            inputs, outputs, one step per script; every run is '"$GITHUB_ACTION_PATH/x.sh"'
  warn-concurrency.sh   warns (direct caller) or notes (wrapper) which concurrency block is needed
  read-cloudflare-token.sh   reads cloudflare_api_token out of secrets_json
  generate-secret.sh, read-current-bundle.sh, replace-key.sh, roll-services.sh, set-worker-*.sh, ...
```

Tests reach the scripts through `tests/action_steps.py`, so the step-body runners exercise the
shipped script text.

## Pinning

Pin the action to an exact `vX.Y.Z` tag (`@main` is not allowed). A `./actions/...` reference would
resolve to the caller's own repository, so always use the full
`Just-Git-Dev/reusable-workflows/actions/rotate-worker-signing-secret@vX.Y.Z` form.

## Trade-off

Calling the action puts the whole job in your workflow: you own its `permissions:`,
`concurrency:` and `timeout-minutes:`. The reusable workflow declares them for you, so prefer it
whenever the caller is in the same organisation or the secrets are repo- or org-level.
