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
repo (`state_variable`) holds `{"current": "<slot>", "pending": "<slot or empty>", "phase": "<put|env>", "rotated_at": <epoch seconds>}`.
`phase` is only present while `pending` is set: `put` means the pending slot may hold a stale or
missing value and the service's environment secret may or may not carry the new one; `env` means
both the Worker slot and the environment secret hold the new value. A state with `pending` but no
`phase` is refused: every state this action writes carries a phase, so it was edited by hand.
Because the grace period (default 24 h) outlives a job (6 h at most), the old slot is retired by a
LATER scheduled run: run the workflow daily.

| State seen | Branch | What it does |
|---|---|---|
| `pending` set, `phase` `put` | **resume-put** | The Worker PUT and the environment write may or may not have happened, and a Worker secret value cannot be read back. So: generate a FRESH value, PUT it into the pending slot (this overwrites it, or creates it if absent), write the environment secret, set `phase=env`, dispatch the sync, wait, promote. |
| `pending` set, `phase` `env` | **pending-sync** | Dispatch the service sync again, wait up to `wait_minutes`. Success: `current=pending`, `pending=""`, `phase` cleared, `rotated_at=now`. Failure: fail the run, change nothing. The pending slot must exist on the Worker, else refuse. |
| both slots exist, nothing pending, `now - rotated_at >= grace_hours` | **retire** | DELETE the slot that is not `current`. Both slots with nothing pending arise only after a promote, so the other slot really is the old value. |
| both slots exist, nothing pending, grace not reached | **no-op** | Success. The summary says when the old slot retires ("retires at ..."). |
| one slot exists (= `current`), `now - rotated_at >= rotate_every_days` or `force: true` | **rotate** | Generate; record `pending=<new slot>, phase=put` FIRST; PUT into the EMPTY slot; write the service repo's environment secret via the App token; set `phase=env`; dispatch the sync with `correlation_id`; wait for that run; on success `current=<new slot>`, `pending` and `phase` cleared. |
| one slot exists, `rotate_every_days` not reached | **no-op** | Success. The summary says when the next rotation is due. |
| no state, one slot exists | **bootstrap (adopt)** | Adopt it as `current`, `rotated_at=now`. |
| no state, no slot exists | **bootstrap (rotate)** | Rotate into `slot_a`. |
| pending slot missing on the Worker with `phase` `env`; both slots exist and no state; state JSON unreadable; `pending` with no `phase`, or a `phase` neither `put` nor `env`; any API error | **refuse** | Fail closed, nothing changed. The error says what to check. |

The intent is recorded BEFORE the first write. If the run dies at any point after `pending` is
written, the next run sees `pending` and never retires anything, because retire runs only when
`pending` is empty. The two windows:

- Failure after the PUT and before `phase=env`: `phase` is still `put`, so the next run takes
  **resume-put**, which replaces whatever the slot and the environment secret hold with one fresh
  value and re-syncs. **Accepted residual window**, which needs three faults together: the earlier
  environment write was stored, `Mark env written` was lost, AND a sync this workflow did not start
  shipped that earlier value (value1) in between. After resume-put, value1 is in no Worker slot until
  a sync succeeds: resume-put's own sync, or a later daily pending-sync if that one fails. It cannot
  be closed, because a Worker secret cannot be read back to compare.
- Failure in dispatch, wait or promote: `phase` is `env`, so **pending-sync** re-dispatches only.

Either way the old value stays valid until a successful promote plus the grace period.
`force: true` cannot rotate while both slots exist: there is no empty slot.

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
| `sync_inputs_json` | input | `{"dry_run":"false"}` | extra dispatch inputs (JSON object); `correlation_id` is added and must not be listed; a `dry_run` key that is truthy (`true`, `"true"`, `1`, `"1"`, any case) is refused |
| `state_variable` | input (req) | none | name of the state variable in the project repo |
| `rotate_every_days` | input | `30` | age at which a rotation is due |
| `grace_hours` | input | `24` | 1 to 8760; at least the longest lifetime of anything signed with the old value, plus a margin. `0` is refused: a re-run right after a promote would retire the old slot at once and reject signatures still in flight |
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
4. **The sync workflow's success MUST mean the bundle was written AND the signer rolled to it.** The
   rotation promotes on the run's conclusion alone and cannot read the result back (it has no GCP
   identity, and a Worker secret value cannot be read). A sync that only plans, or whose jobs are
   skipped yet conclude "success", breaks the rotation: the new slot is promoted, the old one is
   retired after the grace period, and the signer still holds the old value. For this reason
   `sync_inputs_json` may not carry a truthy `dry_run` key. The sync workflow's DEFAULTS must write
   too: a `dry_run` left out of `sync_inputs_json` falls to the sync's own default, so that default
   must be a real write.

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/rotate-external-secret.yml@v5.2.0
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

- **Sync failed or timed out**: the run fails, `pending` stays set with `phase` `env`, both slots stay
  valid. Fix the sync and re-run (or wait for the next daily run): it re-dispatches the sync and promotes.
- **Run died between recording `pending` and `phase=env`**: the next run does resume-put (a fresh
  value into the pending slot and the environment secret, then a sync). Nothing is retired meanwhile.
- **Refuse**: nothing changed. "State names a slot that does not exist": check the Worker secret
  names and the state variable, and edit the variable by hand. "Both slots exist and no state":
  decide which slot is live, and set the variable to `{"current":"<slot>","pending":"","rotated_at":<epoch>}`.
- **Retire DELETE failed**: the run fails; the next run retries.
- Concurrency: one run at a time per Worker script and `slot_a` (`rotate-external-<worker_script>-<slot_a>`).
