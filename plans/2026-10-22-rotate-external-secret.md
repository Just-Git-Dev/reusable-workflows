# rotate-external-secret (v5.2.0) — plan

Approved by the owner 2026-10-22. Consumers are named only by pseudonym (public repo).

## Decision summary

| # | What | Decision |
|---|---|---|
| 1 | New reusable workflow + composite action `rotate-external-secret` | runs in `<Org>/project`; rotates a Cloudflare Worker secret shared with one service |
| 2 | GCP access | **none**: the service's own bundle sync is the only bundle writer |
| 3 | Old value | **alternating slots** A/B on the Worker; the value is never read back or stored in project |
| 4 | Grace (24h default) | longer than a job may run (6h), so **one daily scheduled run advances a small state machine** |
| 5 | State | one non-secret GitHub **variable** in project: `{current, pending, rotated_at}` |
| 6 | Old rotator | `rotate-worker-signing-secret` stays, **deprecated** (notice + docs), removed in the next major |
| 7 | Release | **v5.2.0** (additive), after v5.0.0 ships |

## Rulings (owner, 2026-10-22)

1. Only ROTATION of secrets shared with an EXTERNAL system moves to the org's `<Org>/project` repo
   (Cloudflare API tokens, Cloudflare Worker secrets, other third-party credentials). Bundle SYNC of
   human-set values stays in each service repo, unchanged.
2. Internal-only keys (e.g. signing keypairs verified only through the service's own JWKS) are NOT
   moved for now: a private key would then also live in a GitHub environment secret.
3. Housekeeping (`cleanup-secret-versions`) stays per service.
4. Rotation flow for an external secret, run in `<Org>/project`: generate the new value; set it on the
   external system while the old value stays valid; write it into the service repo's environment
   secret via the org's GitHub App; dispatch the service repo's own bundle sync; wait for that sync run
   to SUCCEED; after a grace period, retire the old value. On any failure before retirement the old
   value stays valid and nothing is retired.
5. The rotation job needs NO GCP identity. The service's sync is the ONLY writer of its bundle, so the
   cross-repo bundle race disappears. Requires the v5.0.0 merge-only sync so other keys are never
   dropped. The service repo holds the rotated value as an environment secret but never generates it.
6. Consumer C's internal keypairs already self-rotate inside its own service, consistent with ruling 2.
7. Shipping: a NEW reusable workflow `rotate-external-secret`. `rotate-worker-signing-secret` stays,
   marked deprecated, until its callers have moved, and is removed in the next major.
8. Grace period: an input, default 24h. Each caller sets it to at least the longest lifetime of anything
   signed with the old value, plus a margin.
9. GitHub App: the org's existing relay App writes the service repo's environment secret and
   dispatches/reads the sync run. It gains Actions write if it lacks it.
10. The sync wait is at most 30 minutes (input, default 30). The rotation finds the run it dispatched by
    a unique correlation id passed as a dispatch input that the sync echoes into its run name; on
    timeout or a failed sync the job fails and the old value stays valid.
11. The first version supports Cloudflare Worker secrets only. A generic variant comes when a second
    case appears.
12. The rotation never reads or stores the old value: two Worker secret slots alternate.
13. Because the grace period outlives a job, retirement of the old slot happens in a LATER scheduled run.

## How one run behaves (cron daily + manual dispatch)

Reads Worker secret NAMES (`GET .../workers/scripts/<script>/secrets`) and the state variable, then does
ONE of:
- **Pending sync** (`pending` set): re-dispatch the service sync, wait (≤ `wait_minutes`); on success
  `current=pending, pending="", rotated_at=now`. On failure: fail the run, change nothing.
- **Retire** (both slots exist, nothing pending, `now - rotated_at ≥ grace_hours`): DELETE the slot that
  is not `current`. Before grace: no-op, success, summary says when it retires.
- **Rotate** (exactly one slot exists = `current`, and `now - rotated_at ≥ rotate_every_days` or
  `force: true`): generate; PUT into the EMPTY slot; write it to `<target_repo>` env
  `<target_environment>` secret `<target_secret_name>` via the App token; set `pending=<new slot>`;
  dispatch `<sync_workflow>` with `correlation_id=<run_id>-<attempt>` and wait for the run whose name
  contains it; success → `current=new`. Failure leaves `pending` set: both slots stay valid, the next
  run retries the sync, and nothing is retired while pending.
- **Bootstrap** (no state): one slot exists → adopt it as `current`; none → rotate into `slot_a`.
- **Refuse** (fail closed, nothing changed): state names a slot that does not exist; both slots exist
  and no state; any API error. The error says what to check.

`dry_run: true` (default) prints the chosen branch and planned calls only.

## Inputs

`cf_account_id`, `worker_script`, `slot_a`, `slot_b`, `target_repo`, `target_environment` (`prod`),
`target_secret_name`, `sync_workflow`, `sync_ref` (`main`), `sync_inputs_json` (`{"dry_run":"false"}`),
`state_variable`, `rotate_every_days` (30), `grace_hours` (24), `wait_minutes` (30), `secret_bytes`
(32), `force` (false), `dry_run` (true), `app_id`, `environment` (''). Secrets: `cloudflare_api_token`,
`app_key`. App permissions: target repo Environments write + Actions write; project repo Variables
write. Workflow `concurrency: rotate-external-<worker_script>-<slot_a>`, `timeout-minutes` = wait + 10.

## Checklist

- [ ] Docs: `docs/rotate-external-secret.md` (flow, state machine, inputs, App permissions, caller
      template, required service-side change: sync accepts `correlation_id` and sets
      `run-name: sync ${{ inputs.correlation_id }}`; Worker verifies both slot names).
- [ ] Red tests: `tests/run_rotate_external_tests.py`, failures pasted in the builder report.
- [ ] Action scripts + `action.yml`, wrapper `.github/workflows/rotate-external-secret.yml`.
- [ ] Deprecation of `rotate-worker-signing-secret` (notice step + docs), README row, catalog,
      Makefile `step-bodies`, DECISIONS entry, TODO (removal in v6).
- [ ] `make ci` green; critic review; fixes.
- [ ] Ship v5.2.0 after v5.0.0; tag verified by ls-remote; action read at the tag.
- [ ] Consumer adoption steps sent (owner-approved).
