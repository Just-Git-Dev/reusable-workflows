# sync-bundle-key

Writes one or more keys into a Secret Manager **bundle** secret (a dotenv blob
of `KEY=value` lines, mounted into Cloud Run as a file), adds a new secret
version N+1, rolls the named Cloud Run service(s) onto that **numbered version**
(`<bundle>:N+1`, never `:latest`), and disables superseded versions per the
[keep-set](#version-retention--the-keep-set).

> **v4.0.0 changes the defaults of this workflow** (pinning on, `mode: replace`,
> `strict_values: true`; `mode` was removed again in v5.0.0, see [Merge and explicit removal](#merge-and-explicit-removal)). See [MIGRATION-v4.md](MIGRATION-v4.md) for what a v3.x caller must
> do first, and [runtime-config.md](runtime-config.md) for where this bundle sits among the
> four config homes. Sections below describe v4 and later; where v3 differed it says so, and the merge-only change of
> v5.0.0 is in [Merge and explicit removal](#merge-and-explicit-removal).

The payload is a single JSON secret whose **keys are the destination bundle
keys**. That absorbs both the number of keys and any naming drift between apps,
so one workflow covers every rotation without branching. Build it with
`toJSON()` so the values stay masked in logs.

## Step order (v4)

1. **S0 environment guard** (only when `environment` is set): `GET
   /repos/{repo}/environments/{env}` with `github.token` and refuse unless the environment has a
   deployment branch policy. A job that names a missing environment makes GitHub create it with
   **no** branch policy, so without this guard the first run would silently create an unprotected
   environment. Failing here leaves an empty environment, which
   [`repos-environments`](repos-environments.md) converges on its next run. Needs `actions: read`.
2. Validate the payload (strict by default, see [Value safety](#value-safety)).
3. Read the current bundle, then compute the new bundle as a [merge with explicit removal](#merge-and-explicit-removal).
4. `ping_datastores` gate (opt-in), then add version N+1.
5. **Roll, pinned:** for each service,
   `services update --update-secrets=<mount>=<bundle>:<N+1> --update-labels=jgd_env_version=<N+1>,jgd_run=<run id>`.
6. **Disable per the keep-set**; never destroy.
7. Summary: key NAMES and their source, bundle `:N+1`, the `+added ~updated -removed` diff, revisions rolled.

## Ordering contract

Superseded secret versions are disabled **only after every service has rolled
successfully**. If any roll fails, the job fails with the old version still
enabled, so no running service is left pointing at a disabled secret version.
Re-run after fixing the cause; the disable happens on the next green run.

## Merge and explicit removal

The sync is **merge-only** (v5.0.0). The new bundle is the current bundle overlaid with the
payload: every payload key is added or updated, and every other key already in the bundle is kept
byte-for-byte. A key leaves the bundle only when you name it in `remove_keys`. There is no `mode`
input and no `confirm_removed` input.

`remove_keys` (CSV, default empty) is the only way a key is removed. Names are trimmed (a newline also separates names), empty
entries are ignored, names are case-sensitive and each must match `^[A-Za-z_][A-Za-z0-9_]*$`.
Naming a key is the explicit confirmation, so no second input repeats it.

- A name that is also in the payload (or, with `payload_source: environment`, also listed in
  `secret_keys_file`) is **refused** as a contradiction: the same run cannot both write and remove
  a key. Nothing is written.
- A name that is not in the current bundle logs a `::warning::` naming it and is otherwise a no-op.
- An invalid name is refused and nothing is written.

The dry run prints `+added ~updated -removed` by **name only**, never a value, plus a count of
the kept keys that are unchanged. Because every revision pins its own bundle version, a wrong
removal is undone by rolling back to a revision that pins the earlier version.

`secret_keys_file` (default `deploy/secret-keys.txt`) has one job here, and only with
`payload_source: environment`: it names the keys to **read** from the job's environment secrets.
A listed key the job's secrets do not hold is still refused (the sync will not build a partial
payload). It does not describe the bundle's desired state and need not list keys that
[`rotate-signing-keypair`](rotate-signing-keypair.md) or
[`rotate-worker-signing-secret`](rotate-worker-signing-secret.md) write: those stay in the bundle
because the sync never drops what it was not told to. With `payload_source: caller` the file is
not read by the sync.

An identical payload (every value equal to the current one, no removals) still adds a new
bundle version and rolls, exactly as before; the sync has no skip-if-unchanged step.

### Migrating from v4

- Drop `mode:` and `confirm_removed:` from every caller. The wrapper workflow no longer declares
  them, so a workflow caller that still passes one fails the call contract. The composite action
  keeps both as tombstone inputs that refuse any non-empty value, because a composite action only
  warns on an unknown `with:` key and the run would otherwise go green with the key not removed.
- A key you used to remove by deleting it from `secret_keys_file` must now be named in
  `remove_keys` (for example `remove_keys: OLD_API_KEY`). Deleting it from the file alone no longer
  removes it from the bundle.
- A caller on `mode: merge` only needs to drop that line: the behaviour is the same.
- A caller on the v4 default `replace` that never removed a key needs no `remove_keys`; the
  bundle simply stops being trimmed to the list.

## Version retention — the keep-set

The disable step never destroys; see [cleanup-secret-versions](cleanup-secret-versions.md) for
that. In v4 the versions kept ENABLED are the union of:

- the new version N+1;
- the version pinned by each of the **two newest revisions before the one just rolled**, per
  service (read only from volumes that a `volumeMount` actually uses; an orphan declared volume is
  ignored);
- the version pinned by **every revision that still takes traffic** (`status.traffic` percent > 0,
  or a 0% entry that carries a `tag`, which is served at its tag URL), however old, read **by
  name** (not out of a newest-50 revision list): after `rollback-service` `to_revision`, traffic stays pinned to the old revision
  until `gcloud run services update-traffic <svc> --to-latest`, so that revision's pin is live;
- the pin of every **Cloud Run Job** that mounts the bundle;
- all of the above are scanned across **every Service and Job in the project, in every region**
  that mounts the bundle secret, not only the ones in `services_csv` (which is scanned as well, in
  `gcp_region`). A pin is a secret volume item a `volumeMount` uses **or** an env var
  `valueFrom.secretKeyRef{name,key}`, the same two places `rollback-service` and
  `cleanup-secret-versions` read;
- the `keep_enabled_count` newest ENABLED versions, which is now a **floor**.

Everything else is disabled. Two revisions are kept so the previous revision stays a valid
rollback target: [`rollback-service`](rollback-service.md) refuses a target whose pinned version
is disabled.

### `keep_enabled_count`

With the floor semantics, `keep_enabled_count` still means "keep at least this many of the newest
ENABLED versions":

| Value | Effect |
|---|---|
| `1` (default) | only the version this run wrote stays ENABLED |
| `2` | the previous version stays ENABLED as a rollback target needing no re-enable |
| `0` | **rejected** — it would disable every version and leave `latest` unresolvable |

The newest version is never in the disable set. In v4 the services mount a numbered version, so
disabling a version that some retained revision pins would make that revision unstartable; the
keep-set above is what prevents it.

**Behaviour note for v3 callers.** At the default of `1` this was identical
to the previous single-version disable *whenever the secret carries no
pre-existing ENABLED tail* — which is the steady state these workflows
themselves maintain. If a tail does exist (a hand-added version, or one written
by `manage-config-secrets`), the first run now disables all of it and emits a
`::warning::` naming the count. That is reversible with `gcloud secrets versions
enable`; per [AGENTS.md §5](../AGENTS.md) dry-run both pins and compare before
upgrading if the secret has been written outside these workflows.

## Value safety

The payload is validated before any cloud call. Every refusal names the **key only**,
never the value.

Always on (these corrupted the bundle in v3.7.0):

- A key containing a newline, carriage return or NUL, or a value with an interior one, is refused (trailing newlines of a value are stripped, as in v3.7.0): a bundle
  line is `KEY=value` on one line.
- Values are written with their backslashes intact, on replace as well as append.
- A key is matched against the existing bundle as a literal string, never as a regex
  (`A.B` does not touch `AxB`).
- Appending to a bundle whose last line has no trailing newline adds one first, so the
  last existing line is not merged with the new key.

On by default since v4.0.0 (**`strict_values: true`**; it was `false` in v3.x, set `false`
explicitly to keep the v3 leniency while you fix the payload):

- Keys must match `^[A-Za-z_][A-Za-z0-9_]*$`.
- An empty or whitespace-only value, and a value that is wholly a placeholder (`-`,
  `changeme`, `change-me`, `placeholder`, `todo`, `tbd`, `dummy`, `example`, `xxx...`,
  `<...>`, `${...}`; case-insensitive, trimmed), is refused even with
  `min_value_length: 0`. A real value that merely contains one of these passes.

Secret values come only from GitHub secrets (see [PLATFORM.md](PLATFORM.md)); these
guards make this workflow safe to be the only path into the bundle.

## Serialisation — one lock across all three bundle writers

`sync-bundle-key`, `rotate-signing-keypair` and `rotate-worker-signing-secret`
each read the latest version of the same `app-secrets` bundle, patch one or two
keys, and add a new version. They therefore declare an **identical**
`concurrency.group`:

```yaml
group: bundle-write-${{ inputs.gcp_project }}-${{ inputs.bundle_secret }}
```

so any two of them queue rather than interleave. Before v2.3.1 the three used
three different prefixes: two concurrent runs both read version N and the second
write silently dropped the first one's keys. `cancel-in-progress` is `false` — a
writer cancelled mid-run may already have added a version.

The group is keyed on the **blob**, never on `bundle_key`: two runs patching
different keys still collide on the whole-blob read-modify-write.

**Caveat.** GitHub scopes a concurrency group to the repository that declares it,
which for a called workflow is the **caller's** repo. Two different caller repos
writing the same bundle are not serialised by this; give one repo ownership of a
bundle if that is a real risk.

**All three writers pin (v4).** The two rotators also roll onto `<bundle>:N+1` with the same
labels and apply the same keep-set. If only the sync pinned, the next key rotation would put every
service back on `:latest` and silently un-pin it. A test asserts the roll and keep-set step bodies
of the three workflows are identical.

## Deployer auth — per-service secrets (repos-secrets)

When the project runs [`repos-secrets`](repos-secrets.md) (F8), a service's blob is `<service>-env`
and its IAM policy has one writer, F8. The service repo's caller authenticates as **that
service's own deployer**: pass `service_account: <service>-deployer@<project>.iam.gserviceaccount.com`
(the repo's WIF link comes from F5) and `bundle_secret: <service>-env`. F8 grants that deployer the
secret-level roles the sync needs (permissions granted: read, add, disable, destroy and `describe`; the sync itself
only reads, adds, disables and describes), so nothing in this
workflow writes IAM and one repo owns each blob, which also removes the two-callers caveat above.
Values still come only from the owning repo's workflow, never by hand.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `gcp_project` | input (req) | — | |
| `wif_provider` / `service_account` | input (req) | — | |
| `gcp_region` | input | `asia-southeast1` | region of the Cloud Run services |
| `bundle_secret` | input | `app-secrets` | |
| `mount_path` | input (req) | — | container path the bundle mounts at; must match the service's existing mount, e.g. `/secrets/app.env` (no default since v3.0.0) |
| `services_csv` | input (req) | — | comma-separated Cloud Run service names |
| `title` | input | `secrets` | label for the run summary |
| `dry_run` | input | `false` | validate + print the plan; write nothing |
| `min_value_length` | input | `8` | refuse the run if any payload value is shorter than this; `0` disables |
| `strict_values` | input | **`true`** (was `false`) | refuse non-env-name keys, empty/whitespace-only values and placeholders (even at `min_value_length: 0`) |
| `keep_enabled_count` | input | `'1'` | a **floor** under the [keep-set](#version-retention--the-keep-set): at least this many newest ENABLED versions stay; minimum `1` |
| `environment` | input | `''` | GitHub environment the job runs in (`environment: ${{ inputs.environment }}`). Empty = no environment, as in v3. When set, step S0 refuses an environment without a deployment branch policy |
| `payload_source` | input | `caller` | `caller` = the `payload_json` secret below. `environment` = read the keys named in `secret_keys_file` from the job's environment secrets. Does not work cross-org through this workflow; use the [action](sync-bundle-key-action.md) |
| `remove_keys` | input | `''` | CSV of key names to remove from the bundle; the only way a key leaves it. See [Merge and explicit removal](#merge-and-explicit-removal) |
| `secret_keys_file` | input | `deploy/secret-keys.txt` | committed key-name list in the caller's checkout; with `payload_source: environment` only, the names of keys to read from the job's secrets |
| `pin_versions` | input | **`true`** | roll with `<bundle>:<N+1>` and the `jgd_env_version`/`jgd_run` labels instead of `:latest` |
| `require_branch_policy` | input | `true` | step S0; only meaningful with `environment` |
| `ping_datastores` / `datastore_env_file` / `ping_timeout_seconds` | input | `''` / `''` / `10` | opt-in datastore reachability gate before the new version is added. May ship in v4.0 or v4.1; either way it is not a breaking input |
| `payload_json` | **secret** (req unless `payload_source: environment`) | — | `{"DEST_KEY": "value", ...}` |

### `payload_source: environment` is UNPROVEN

> **`payload_source: caller` cannot read ENVIRONMENT secrets.** `payload_json` is evaluated in
> the CALLER job, and a job that calls a reusable workflow cannot declare `environment:` (GitHub:
> "The job that calls the reusable workflow can't use the `environment` keyword"). So
> `${{ secrets.X }}` there is the REPO or ORG secret `X`, or empty. Passing `environment: prod`
> as an input does not change that. If a repo-level copy of `X` also exists, the bundle silently
> gets that copy, which may be stale. Use `caller` only with repo- or org-level secrets.

**`payload_source: environment` through this reusable WORKFLOW does NOT work from a caller in
another organisation** (proven by two cross-org dry runs on 2026-10-21, PR #151). The callee job
did run in the caller's environment (step S0 passed), but refused with "No environment secret
for listed key(s): ...", both for a key held in the environment and for a key held only at repo
level. It fails closed and writes nothing. Why: GitHub gives a callee job the environment's value
only for a secret the caller PASSES ("The caller workflow must still pass the secret"; one not
passed "resolves to an empty string"), and `secrets: inherit` works within one organisation only.

**Use the composite action instead.** [`actions/sync-bundle-key`](sync-bundle-key-action.md)
runs as a step of the CALLER's own job, which declares `environment:`, so the environment's
secrets reach it as `secrets_json: ${{ toJSON(secrets) }}` with no organisation boundary in the
way. This workflow is now a thin wrapper that calls that same action, with the same inputs,
secret and outputs; the logic lives once, in the action's scripts. A cross-org caller needing
environment-level secrets copies the job template in
[sync-bundle-key-action.md](sync-bundle-key-action.md), including its `concurrency:` block.
The action was proven cross-org on 2026-10-21: an environment-only key reached it from a
consumer's `prod` environment job. Note what that run also showed: the job's `secrets` context
MERGES org, repo and environment secrets, so a listed key that is missing from the environment
is read silently from a repo- or org-level copy. Keep every listed key in the environment, and
delete same-named repo/org copies (sync-bundle-key-action.md, "Inputs").

The `actions: read` permission is required in the caller (step S0 reads the environment).

## Outputs

`old_version`, `new_version`, `services_rolled`.

## Required IAM

On `service_account`: `roles/secretmanager.secretVersionManager` and
`roles/secretmanager.secretAccessor` on `bundle_secret`, plus
`roles/run.developer` on the target services. The run also calls
`gcloud secrets describe`, which needs `secretmanager.secrets.get` on `bundle_secret`;
the two roles above are not documented to carry it, so grant a role that does (for
example `roles/secretmanager.viewer`; verify with `gcloud iam roles describe`).
The v4 keep-set also lists the project's services and jobs, each service's traffic and its revisions
(`gcloud run services list|describe`, `run revisions list`, `run jobs list|describe`).
`roles/run.developer` on the services does not cover the project-wide listings: the service
account also needs PROJECT-level `run.services.list`, `run.jobs.list`, `run.jobs.get`,
`run.revisions.list` and `run.revisions.get` (for example project-level `roles/run.viewer` in
addition to the service-level `roles/run.developer`). A caller bound only on its own services gets
a 403 and the keep step fails, disabling nothing. A listing failure, or an all-region listing that
reports a region "did not respond" (results "may be incomplete"), also stops the step before
anything is disabled.
The rotators' "roll back the new SM version on failure" step refuses to disable N+1 while any
live revision still pins it (a partial roll): it leaves N+1 ENABLED and fails the job. "Live" here
means a revision with traffic or a tag, the latest ready and latest created revisions, and the
service template itself, so a new revision that is ready but not yet taking traffic counts.

## Example caller

```yaml
name: Sync DB + Redis passwords
on:
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: true     # run the dry run first: it prints the +added ~updated -removed diff

permissions:
  contents: read
  id-token: write
  actions: read           # v4: step S0 reads the environment

jobs:
  sync:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/sync-bundle-key.yml@v5.2.0
    with:
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_ROTATOR_SA }}
      services_csv: myapp-api,myapp-cron
      mount_path: /secrets/app.env
      environment: stage
      title: DB + Redis passwords
      dry_run: ${{ inputs.dry_run }}
    secrets:
      # Evaluated in THIS caller job: these are REPO/ORG secrets, never the `stage` environment's
      # (see "payload_source: environment is UNPROVEN" above).
      payload_json: |
        {"DB_PASSWORD": ${{ toJSON(secrets.DB_PASSWORD) }},
         "REDIS_PASSWORD": ${{ toJSON(secrets.REDIS_PASSWORD) }}}
```

`deploy/secret-keys.txt` in the same repo is not read with this (caller) source; it only matters with `payload_source: environment`, where it lists the keys to read:

```text
DB_PASSWORD
REDIS_PASSWORD
```

The same workflow rotates object-storage credentials — only the payload keys
change, and they are chosen entirely by the caller:

```yaml
    with:
      services_csv: myapp-api
      title: Object storage credentials
    secrets:
      payload_json: |
        {"FILE_STORAGE_ACCESS_KEY": ${{ toJSON(secrets.S3_ACCESS_KEY_ID) }},
         "FILE_STORAGE_SECRET_KEY": ${{ toJSON(secrets.S3_SECRET_ACCESS_KEY) }}}
```

## Notes

- Payload values must be JSON strings. Numbers and booleans are rejected up
  front rather than silently stringified into the bundle.
- Values are base64-encoded on the way through the shell, so shell metacharacters
  and backslashes survive intact (newlines are refused; see Value safety).
- The local copy of the bundle is removed in an `always()` step.
