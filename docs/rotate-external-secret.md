# rotate-external-secret

Rotates a secret that is shared with an **external system**, here a **Cloudflare Worker secret**
that a backend service also holds. It runs in the org's project repo (`<Org>/project`) and needs
**no GCP identity**: the service's own bundle sync is the only writer of its Secret Manager bundle.

It replaces [`rotate-worker-signing-secret`](rotate-worker-signing-secret.md), which is deprecated
and removed in v6. Since v5.0.0 the sync is merge-only, so the rotated key survives every other sync.

## How it works

The Worker holds the secret in one of **two slots** (`slot_a`, `slot_b`) that alternate. The
rotation never reads or stores the old value: it writes the new value into the empty slot, so the
old slot stays valid until it is deleted.

One run does ONE step of a small state machine. A **non-secret** GitHub variable in the project
repo (`state_variable`) holds `{"current": "<slot>", "pending": "<slot or empty>", "rotated_at": <epoch seconds>}`.
Because the grace period (default 24 h) outlives a job (6 h at most), the old slot is retired by a
LATER scheduled run: run the workflow daily.

| State seen | Branch | What it does |
|---|---|---|
| `pending` set | **pending-sync** | Dispatch the service sync again, wait up to `wait_minutes`. Success: `current=pending`, `pending=""`, `rotated_at=now`. Failure: fail the run, change nothing. |
| both slots exist, nothing pending, `now - rotated_at >= grace_hours` | **retire** | DELETE the slot that is not `current`. |
| both slots exist, nothing pending, grace not reached | **no-op** | Success. The summary says when the old slot retires ("retires at ..."). |
| one slot exists (= `current`), `now - rotated_at >= rotate_every_days` or `force: true` | **rotate** | Generate; PUT into the EMPTY slot; write it to the service repo's environment secret via the App token; set `pending=<new slot>`; dispatch the sync with `correlation_id`; wait for that run; on success `current=<new slot>`. |
| one slot exists, `rotate_every_days` not reached | **no-op** | Success. The summary says when the next rotation is due. |
| no state, one slot exists | **bootstrap (adopt)** | Adopt it as `current`, `rotated_at=now`. |
| no state, no slot exists | **bootstrap (rotate)** | Rotate into `slot_a`. |
| state names a slot that does not exist; both slots exist and no state; state JSON unreadable; any API error | **refuse** | Fail closed, nothing changed. The error says what to check. |

If a rotation fails after the PUT, `pending` is left set (or, if it failed before `pending` was
written, both slots exist with no pending and the next retire run deletes the unused new slot).
Either way the old value stays valid and nothing is retired while `pending` is set. `force: true`
cannot rotate while both slots exist: there is no empty slot.

`dry_run: true` (the default) reads the Worker secret names and the state variable and prints the
chosen branch and planned calls. It makes no write call: no PUT, DELETE, secret set, variable set
or workflow dispatch.

The new value is masked the moment it is generated, lives only in a `0600` file under
`$RUNNER_TEMP` that is shredded in an `always()` step, and reaches `gh secret set` on stdin and
Cloudflare through `curl --data @-`. It is never an output, an env var or a summary line.

## Inputs

| Name | Kind | Default | Notes |
|---|---|---|---|
| `cf_account_id` | input (req) | none | Cloudflare account owning the Worker |
| `worker_script` | input (req) | none | Worker script name |
| `slot_a`, `slot_b` | input (req) | none | the two Worker secret names that alternate |
| `target_repo` | input (req) | none | service repo NAME (same owner as the project repo) |
| `target_environment` | input | `prod` | environment in `target_repo` that holds the secret |
| `target_secret_name` | input (req) | none | environment secret name written in `target_repo` |
| `sync_workflow` | input (req) | none | file name of the service's sync workflow, e.g. `sync-secrets.yml` |
| `sync_ref` | input | `main` | ref the sync is dispatched on |
| `sync_inputs_json` | input | `{"dry_run":"false"}` | extra dispatch inputs (JSON object); `correlation_id` is added and must not be listed |
| `state_variable` | input (req) | none | name of the state variable in the project repo |
| `rotate_every_days` | input | `30` | age at which a rotation is due |
| `grace_hours` | input | `24` | at least the longest lifetime of anything signed with the old value, plus a margin |
| `wait_minutes` | input | `30` | sync wait, 1 to 30 (the wrapper job timeout is 40 minutes) |
| `secret_bytes` | input | `32` | random bytes, hex-encoded (16 to 128) |
| `force` | input | `false` | rotate now if exactly one slot exists |
| `dry_run` | input | `true` | print the plan, write nothing |
| `app_id` | input (req) | none | id of the org's relay GitHub App |
| `environment` | input | `''` | job environment holding `app_key` and the Cloudflare token |
| `cloudflare_api_token` | **secret** (req) | none | Workers Scripts:Edit on `cf_account_id` |
| `app_key` | **secret** (req) | none | private key of the App |

## GitHub App permissions

On `target_repo`: **Environments: write** (the secret) and **Actions: write** (dispatch and read the
sync run). On the project repo: **Variables: write** (the state). Metadata: read. The workflow
mints one token scoped to exactly those two repos.

## Required service-side change

1. The sync workflow in `target_repo` accepts a `correlation_id` input under `workflow_dispatch`
   and sets `run-name: sync ${{ inputs.correlation_id }}`. The rotation finds the run it dispatched
   by that exact token in the run name (`<run_id>-<attempt>`), and refuses if more than one run matches.
2. The sync must read `target_secret_name` from the environment secret into the bundle key.
3. The Worker accepts a signature made with EITHER slot name, as long as that slot is set.

## Caller template

```yaml
name: Rotate external secret
on:
  workflow_dispatch:
    inputs:
      force:
        type: boolean
        default: false
      dry_run:
        type: boolean
        default: true
  schedule:
    - cron: '17 3 * * *'   # daily: advances the state machine one step

permissions:
  contents: read

jobs:
  rotate:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rotate-external-secret.yml@v4.1.1
    with:
      cf_account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      worker_script: service-files-cdn
      slot_a: FILES_SIGNING_A
      slot_b: FILES_SIGNING_B
      target_repo: service
      target_secret_name: FILES_SIGNING_SECRET
      sync_workflow: sync-secrets.yml
      state_variable: ROTATE_FILES_SIGNING_STATE
      app_id: ${{ vars.RELAY_APP_ID }}
      environment: rotation
      force: ${{ github.event_name == 'workflow_dispatch' && inputs.force }}
      dry_run: ${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      app_key: ${{ secrets.RELAY_APP_KEY }}
```

The schedule runs with `dry_run: false`; a manual run defaults to `true`. The `rotation`
environment holds the App key and the Cloudflare token.

## Failure and recovery

- **Sync failed or timed out**: the run fails, `pending` stays set, both slots stay valid. Fix the
  sync and re-run (or wait for the next daily run): it re-dispatches the sync and promotes.
- **Refuse**: nothing changed. "State names a slot that does not exist": check the Worker secret
  names and the state variable, and edit the variable by hand. "Both slots exist and no state":
  decide which slot is live, and set the variable to `{"current":"<slot>","pending":"","rotated_at":<epoch>}`.
- **Retire DELETE failed**: the run fails; the next run retries.
- Concurrency: one run at a time per Worker script and `slot_a` (`rotate-external-<worker_script>-<slot_a>`).
