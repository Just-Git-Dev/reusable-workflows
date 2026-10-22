# sync-bundle-key (composite action)

The same operation as the [`sync-bundle-key`](sync-bundle-key.md) reusable workflow, as a
**composite action** that runs as a step of the **caller's own job**. Use it when the secrets
live in a GitHub **environment** (`environment:` on the job) and the caller is in a different
organisation than this repo: environment secrets cannot cross an org boundary into a reusable
workflow (proven in PR #151), but they do reach a step of the job that declares the environment.

```yaml
- uses: Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@v4.1.1
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
      - uses: Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@v4.1.1
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
  out of it; nothing else leaves its step. With the caller source the caller must define a
  secret named `payload_json`; that name is matched case-insensitively (`PAYLOAD_JSON` works).
  The keys listed in `secret_keys_file` (environment source) are matched exactly, because they
  become the payload's key names.
- **"Environment source" means the job's MERGED secrets, not the environment's alone.** In a job
  that declares `environment:`, GitHub's `secrets` context holds the org, repo AND environment
  secrets together, with the environment winning a name clash. `toJSON(secrets)` cannot tell them
  apart. So a key listed in `secret_keys_file` but missing from the environment is read silently
  from a repo- or org-level secret of the same name. A consumer's live run proved this
  (2026-10-21): a key held only at repo level was upserted from the `prod` environment job. The
  action cannot guard against it, because a `GITHUB_TOKEN` cannot list an environment's secret
  names. **Caller hygiene is therefore required:** define every listed key in the environment,
  and delete any repo- or org-level secret that shares a name with a listed key, or a stale copy
  will ship the day the environment copy is removed.
- **A key that only a rotator writes cannot be listed with the environment source.** See
  [Mode](sync-bundle-key.md#mode-replace-and-removal-by-list): use `mode: merge` with only the
  environment-held keys listed, until a carry-over input exists.
- **Booleans are exactly `'true'` or `'false'`.** `dry_run`, `strict_values`,
  `require_branch_policy`, `pin_versions` and `concurrency_declared` are checked by the first
  step, which refuses anything else (`yes`, `1`, `True`). GitHub's `if:` compares
  case-insensitively and bash does not, so a loose value would be read two ways and could turn a
  dry run into a live write.
- **The key list is checked out into `.rw-sync-bundle-key/`** under the workspace (sparse, only
  `secret_keys_file`), never into the workspace root: `actions/checkout` cleans its target, and a
  root checkout would wipe the caller's own checkout and build. Do not use that directory name.
  The checkout path must be inside `$GITHUB_WORKSPACE`, so `runner.temp` cannot be used.
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
