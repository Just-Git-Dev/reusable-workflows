# sync-bundle-key (composite action)

The same operation as the [`sync-bundle-key`](sync-bundle-key.md) reusable workflow, as a
**composite action** that runs as a step of the **caller's own job**. Use it when the secrets
live in a GitHub **environment** (`environment:` on the job) and the caller is in a different
organisation than this repo: environment secrets cannot cross an org boundary into a reusable
workflow (proven in PR #151), but they do reach a step of the job that declares the environment.

```yaml
- uses: Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@v4.0.0
```

The action is the single source of truth. The reusable workflow is a thin wrapper that calls it
with the same inputs, secret and outputs, so the behaviour (S0 guard, `mode`, `strict_values`,
pinned roll, keep-set) is documented once, in [sync-bundle-key.md](sync-bundle-key.md). This page
covers only what is different when you call the action yourself.

## What the caller's job must declare

A composite action cannot declare `environment:`, `permissions:`, `concurrency:` or
`timeout-minutes:`. The calling job does, and the action cannot check any of it.

| Job key | Value | Why |
|---|---|---|
| `environment` | the environment holding the secrets | its secrets are what `secrets_json` carries |
| `permissions` | `contents: read`, `id-token: write`, `actions: read` | `id-token` for the WIF login; `actions: read` for the branch-policy guard (S0), which reads the environment |
| `concurrency` | `group: bundle-write-<gcp_project>-<bundle_secret>`, `cancel-in-progress: false` | one lock across every writer of the same bundle blob (see below) |
| `timeout-minutes` | `10` | the wrapper's value; the action sets none |

**Concurrency is the one that bites.** `sync-bundle-key`, `rotate-signing-keypair` and
`rotate-worker-signing-secret` each read the latest bundle version, patch a key or two and add a
new version. Two at once both read version N and the second write silently drops the first one's
keys. The group string must match the one the workflows use
(`tests/run_concurrency_tests.py` pins it). No GitHub context exposes the running job's
concurrency group, so the action cannot detect a missing one: **every direct call prints a
`::warning::` naming the exact block**. Treat that warning as the reminder, not as a sign something
failed. The reusable workflow wrapper declares the group itself and sets the input
`concurrency_declared: 'true'`, which turns the message into a `::notice::`; direct callers leave
it unset.
GitHub scopes the group to the caller's repo, so two caller repos writing one bundle are still
not serialised.

## Caller job template

```yaml
name: Sync secrets
on:
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: true     # run the dry run first: it prints the +added -removed =kept diff

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: stage                  # the secrets below live in THIS environment
    permissions:
      contents: read
      id-token: write                   # WIF
      actions: read                     # step S0 reads the environment's branch policy
    concurrency:
      group: bundle-write-my-gcp-project-app-secrets   # bundle-write-<gcp_project>-<bundle_secret>
      cancel-in-progress: false
    steps:
      - uses: Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@v4.0.0
        with:
          secrets_json: ${{ toJSON(secrets) }}
          gcp_project: my-gcp-project
          wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
          service_account: ${{ vars.GCP_ROTATOR_SA }}
          services_csv: myapp-api,myapp-cron
          mount_path: /secrets/app.env
          environment: stage            # same name as above; only the S0 guard reads it
          payload_source: environment   # keys named in deploy/secret-keys.txt, read from the environment
          dry_run: ${{ inputs.dry_run }}
```

`deploy/secret-keys.txt` in the same repo lists the bundle's keys by name, as for the workflow.
With `payload_source: caller` (the default) the action reads one secret named `payload_json` out
of `secrets_json` instead.

## Inputs, secrets and outputs

Every input of the [workflow](sync-bundle-key.md#inputs--secrets) has the same name, meaning and default
here, with two differences:

- **Values are strings.** `dry_run: 'true'`, not a boolean, as for any composite action. The
  workflow wrapper passes `${{ inputs.x }}`, which GitHub stringifies.
- **`secrets_json` (required)** replaces the `payload_json` secret: set it to
  `${{ toJSON(secrets) }}` in the job that declares `environment:`. The action reads only
  `payload_json` (caller source) or the keys listed in `secret_keys_file` (environment source)
  out of it; nothing else leaves its step.
- **`environment`** is only the name for the S0 guard. The action cannot read its own job's
  `environment:`, so the caller repeats it. Leave it empty to skip S0.

Outputs are the workflow's: `old_version`, `new_version`, `services_rolled`.

## How secrets are handled

`secrets_json` carries registered secrets, so their values stay masked in the log. The action also
runs `::add-mask::` on every value it derives from the JSON. Each script receives its inputs
through `env:`, never through `${{ }}` in a `run:` body (zizmor enforces it), and every script is
under `make shellcheck`.

## Layout (for the next action that copies this pattern)

```text
actions/sync-bundle-key/
  action.yml            inputs, outputs, one step per script; every run is '"$GITHUB_ACTION_PATH/x.sh"'
  warn-concurrency.sh   always warns which concurrency block the caller job needs
  read-caller-payload.sh / build-env-payload.sh   read payload_json / the listed keys out of secrets_json
  validate-payload.sh, compute-bundle.sh, roll-services.sh, disable-superseded.sh, ...
```

Tests reach the scripts through `tests/action_steps.py` (`extract_action_step`), so the step-body
runners exercise the shipped script text.

## Pinning

Pin the action to an exact `vX.Y.Z` tag, as for the workflows (`@main` is not allowed). A
`./actions/...` reference would resolve to the caller's own repository, so always use the full
`Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@vX.Y.Z` form.

## Trade-off

Calling the action puts the whole job in your workflow: you own its `permissions:`,
`concurrency:` and `timeout-minutes:`. The reusable workflow declares them for you, so prefer it
whenever the caller is in the same organisation or the secrets are repo- or org-level.
