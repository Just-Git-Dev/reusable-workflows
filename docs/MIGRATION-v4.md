# Migrating from v3.x to v4

v4.0.0 is a major release because it flips three defaults and changes a destructive path. The
model it implements is described in [runtime-config.md](runtime-config.md); this page is the
checklist for a caller moving from any v3.x. Semver here tracks the input contract
([README](../README.md)); `WORKFLOW_VERSION` is stamped repo-wide, so v4.0.0 re-tags every workflow
and a caller of a workflow v4 did not change only moves its pin.

## What changes, by workflow

| Workflow | What breaks | The caller must |
|---|---|---|
| [`sync-bundle-key`](sync-bundle-key.md) | `mode` defaults to `replace` and needs `deploy/secret-keys.txt`; `strict_values` defaults to `true`; services roll onto `<bundle>:N` not `:latest`; with `environment` set it refuses an environment that has no branch policy; it needs `actions: read` | commit the key list (including keys the two rotate workflows write), fix empty or placeholder secrets, grant `actions: read`, run a dry run first |
| [`rotate-signing-keypair`](rotate-signing-keypair.md), [`rotate-worker-signing-secret`](rotate-worker-signing-secret.md) | they roll onto `<bundle>:N` and apply the same keep-set | nothing beyond moving the pin, **but** the keys they write must be in `deploy/secret-keys.txt` or the next sync drops them |
| [`deploy-cloud-run`](deploy-cloud-run.md) | refuses a service whose template mounts a `*-env` bundle at `:latest` unless `env_secret` is given (it then pins the newest ENABLED version); the forward-only baseline falls back to the service's `jgd_commit` label | add `env_secret` and `env_mount_path`; optionally `env_file` |
| [`cloud-run-update`](cloud-run-update.md) | the same `:latest` refusal when `secrets` names a `*-env` bundle at `:latest` | pass a version number |
| [`rollback-service`](rollback-service.md) (Cloud Run) | refuses when the target revision's pinned `<deployable>-env:<N>` is not ENABLED | see "Rollback refusal" below |
| [`promote-image`](promote-image.md) | none; it inherits the pin | nothing |

## Per-caller checklist

Do these in order, one service at a time. Every step is safe to re-run.

1. **Create the environments first.** A v4 job that names an environment which does not exist
   creates it with no branch policy, and `sync-bundle-key` then refuses to run. Create each
   environment and its branch policy with [`repos-environments`](repos-environments.md), then set
   the secrets (by hand for single-consumer ones, with
   [`distribute-env-secrets`](distribute-env-secrets.md) for ones shared by several repos).
2. **Commit `deploy/secret-keys.txt`.** One bundle key **name** per line, every key the bundle
   should hold, **including the keys written by `rotate-signing-keypair`
   (`private_key_name`, `public_key_name`, `key_id_name`) and `rotate-worker-signing-secret`
   (`bundle_key`)**. A key missing from this file is dropped by the first replace-mode sync.
3. **Commit `deploy/env.<stage>.yaml`** with the non-secret settings that differ per stage, and
   make sure no key appears in two of `configs/.env`, `deploy/env.*.yaml` and
   `deploy/secret-keys.txt` ([runtime-config.md](runtime-config.md)). [`deploy-env-lint`](deploy-env-lint.md)
   checks this (names only, never values).
4. **Fix empty and placeholder secrets.** `strict_values` is now `true`, so an empty value or one
   that is wholly `changeme`, `todo`, `<...>` and similar refuses the run, naming the key. Set a real
   value, or take the key out of the payload and the list.
5. **Grant `actions: read`** in the caller job's `permissions:` (the environment guard reads the
   environment with the job token), alongside `contents: read` and `id-token: write`.
6. **Dry run once.** Call `sync-bundle-key@v4` with `dry_run: true`. It prints the `+added
   -removed =kept` key diff by name only and writes nothing. Review the `-removed` set: it is
   exactly what the live run will drop, and a live run refuses unless `confirm_removed` lists
   exactly that set.
7. **Run it live** (with `confirm_removed` if the diff removes keys). The first live run writes the
   next bundle version and rolls every service onto `<bundle>:N`.
8. **Deploy with `deploy-cloud-run@v4`**, passing `env_secret` and `env_mount_path` (and
   `env_file: deploy/env.<stage>.yaml`). It keeps the pin the sync set, stamps the four revision
   labels, and uploads `config-manifest.json`.
9. **Move the other callers' pins** (`rotate-*`, `promote-image`, and the rest) to `v4.0.0`.

To keep the v3 behaviour of one input while you fix the rest, set it explicitly:
`strict_values: false`, `mode: merge`, or `pin_versions: false`. These are escape hatches for the
migration window, not a recommended steady state.

## Rollback refusal

Before v4 a Cloud Run rollback put an old image on a new revision that inherited the *current*
bundle, so it always started, but ran old code against new secrets. In v4 a rollback to a revision
whose pinned bundle version has been disabled must fail before changing anything:

```
::error::rollback refused: revision <r> pins <d>-env:<N>, which is DISABLED; only the two newest revisions' pins stay enabled.
```

After `rollback-service` `to_revision`, traffic stays pinned to that revision until you run
`gcloud run services update-traffic <svc> --to-latest`. The keep-set keeps the pin of any revision
with traffic > 0, so the rolled-back revision stays startable in the meantime. `bundle_secret` is
required in `to_revision` mode (the refusal is not opt-in).

A manual traffic shift in the Cloud Console cannot be guarded by any workflow; the refusal only
covers rollbacks run through `rollback-service`.

**Ruling Q4 (owner, 2026-10-21):** `rollback-service` gains a `to_revision` mode that shifts
traffic back to the old revision, taking its image, env and pinned bundle together, and refuses
loudly when that revision's pinned bundle version is disabled. The image mode stays, with a
warning in the run summary. Inputs: see [rollback-service](rollback-service.md).

## Retiring the `production` environment name

If a caller passes `environment: production` and moves to a new name such as `prod`, GitHub has no
successful Deployment under the new name, and the v3 forward-only guard **allows** any deploy when
its environment has no successful Deployment. v4 closes that gap: with no Deployment record it
reads the service's `jgd_commit` label as the baseline and still refuses a backwards deploy. It
allows the deploy only when neither exists (a first deploy ever), with a notice.

Whether the `production` environment object is then deleted is a separate, destructive decision.

**Ruling Q5 (owner, 2026-10-21):** the old `production` environment objects are deleted, but only
after a per-environment provenance check (does it hold secrets or variables, is its deployment
history needed) that is put to the owner before any delete. Until then `repos-environments`
reports them as unmanaged. `repos-environments` itself never deletes an environment.

## The `pin_env: false` escape in `deploy-cloud-run`

**Ruling Q8 (owner, 2026-10-21):** v4 ships `pin_env: false` as an opt-out for a service with no
`*-env` bundle yet. Every run that uses it prints a warning in its summary, so adoption can go
service by service.

## Release order

**Ruling Q9 (owner, 2026-10-21): everything ships together in v4.0.0; there is no v3.10.0.** The
additive workflows (`repos-environments`, `distribute-env-secrets`, `deploy-env-lint`) and the
three default flips are one release. Consequence: a caller creates its environments with v4.0.0's
`repos-environments` **before** its first v4 sync or deploy, because the environment guard
refuses otherwise.

## Related

- [runtime-config.md](runtime-config.md): the four homes, pinning, labels and the trace.
- [sync-bundle-key.md](sync-bundle-key.md): inputs, keep-set, and the unproven
  `payload_source: environment`.
