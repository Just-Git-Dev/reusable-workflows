# cleanup-secret-versions

Sweeps Secret Manager versions on a **quarantine** policy: `ENABLED` →
`DISABLED` → `DESTROYED`, with a mandatory dwell time in `DISABLED` between the
last two.

Four reusables here add secret versions and none has ever removed one —
`manage-config-secrets`, `rotate-signing-keypair`, `rotate-worker-signing-secret`
and `sync-bundle-key`. Versions accumulate for the life of the secret, every one
still holding retrievable plaintext, so exposure grows monotonically with
rotation frequency. That is the opposite of what rotating is for. This is the
missing sweep.

## Why this one is more dangerous than the GAR sweep

`cleanup-gar-images` deletes container images. A wrongly deleted image can be
rebuilt from the commit that produced it.

A destroyed secret version cannot. Google's wording is unambiguous: *"After a
version is destroyed, you can't access the secret data or restore the version to
another state."* There is no undelete. So this workflow never destroys as a
first action — a version is disabled, sits in quarantine where re-enabling it is
one command, and only then becomes eligible.

The cost of that quarantine is $0.06 per version per month. The cost of getting
it wrong is a credential you cannot recover.

## The `latest` trap, and how the keep-set answers it

Two facts about `latest`, both verified against Google's docs rather than
assumed, drive the entire design:

**1. `latest` is resolved server-side to the highest-numbered ENABLED version.**
So *disabling the newest enabled version silently repoints `latest` at an older
payload* — a live configuration rollback, with no deploy behind it and no signal
that it happened.

**2. A Cloud Run volume mount re-reads Secret Manager at runtime, on every
read** — not at deploy time: *"When reading a volume, Cloud Run always fetches
the secret value from the Secret Manager."* There is therefore no "safe until the
next deploy" window. A wrong destroy breaks a **running** service on its next
read. (Env-var refs resolve at instance startup instead, which is marginally
laxer; the volume case is the strict one and sets the policy.)

Together these mean the revision spec cannot tell you which version is live. A
service that mounts `app-secrets:latest` is pinned to nothing — so **"not
`:latest`" is not the same as "not in use"**, and the sweep resolves consumers
rather than trusting the spec.

> An earlier draft of this design (TODO.md, from #51) recorded that `:latest`
> resolves at *deploy* time. That was wrong for volume mounts, which is what
> every service in the fleet actually uses. See DECISIONS.md 2026-08-16.

## The keep-set

Per secret, a version is **kept** if any of these holds:

1. it is the version `latest` currently resolves to — **always, not configurable**
2. it is among the newest `keep_enabled_count` `ENABLED` versions (rollback window)
3. a live Cloud Run Service or Job pins it **by number**
4. it is listed in `keep_versions`
5. it is younger than `min_age_days`

Everything else `ENABLED` is **disabled**. Everything else `DISABLED` is
**destroyed** — but only once it has been disabled for *more than*
`quarantine_days`, and only when `enable_destroy: true`.

Rule 1 looks redundant against rule 2, since `latest` is normally the newest
enabled version. It stops being redundant the moment a rotation lands between the
two collection calls — which is exactly the moment an irreversible mistake would
otherwise be made. It is asserted twice more: once as a plan-time invariant, and
again by re-resolving `latest` immediately before each destroy.

## Where the quarantine clock comes from

Secret Manager stores **no disabled-at timestamp**. A version carries
`createTime`, `state` and `etag`, and nothing else — so the dwell time cannot be
read from the resource.

It is read from **Admin Activity audit logs** instead, which record
`DisableSecretVersion`, retain it for 400 days, and cannot be turned off. Where a
version has been disabled, re-enabled and disabled again, the most recent event
governs.

A version whose disable event cannot be found is **held**, never destroyed:
absence of evidence is not evidence of an old-enough disable.

## The fail-safe

If a target secret has **no live Cloud Run consumer at all**, the run aborts
rather than sweeping it — the same reasoning as `cleanup-gar-images`' "no live
digests resolved". A broken scan, a wrong `gcp_region` or a missing IAM role all
look exactly like an unused secret, and they are far more common than a secret
that genuinely has no consumer.

A secret consumed outside Cloud Run (GKE, an external worker) needs
`require_consumers: false`. That input is an explicit statement that you have
checked by hand — it is not a convenience toggle.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `gcp_project` | *required* | Project owning the secrets. |
| `gcp_region` | `asia-southeast1` | Region of the consuming Services/Jobs. |
| `wif_provider` | *required* | WIF provider resource name. |
| `service_account` | *required* | SA to impersonate. |
| `secrets_list` | `''` (all) | Comma-separated secret names. Naming them is safer than sweeping everything. |
| `keep_enabled_count` | `3` | Newest N `ENABLED` versions to keep. `2` is the lowest that expresses a rollback. |
| `min_age_days` | `7` | Never touch a version younger than this. |
| `quarantine_days` | `30` | Dwell time in `DISABLED` before destroy is possible. `0` is rejected. |
| `enable_destroy` | `false` | **Off by default** — quarantine only, so every action is reversible. |
| `require_consumers` | `'true'` | Abort when a secret has no live consumer. |
| `keep_versions` | `''` | `secret:version` pins the scan cannot see. |
| `dry_run` | `true` | Print the plan, change nothing. |

Outputs: `to_disable`, `to_destroy`, `disabled`, `destroyed`, `held`.

## Required IAM

Stated as **permissions**, because the secret-side ones can be held at *resource*
scope — bound on each target secret rather than on the project:

```
secretmanager.versions.list|get|disable|destroy   # the sweep itself
secretmanager.secrets.get                         # `secrets describe`, per target
roles/run.viewer                                  # enumerate live Services + Jobs
roles/logging.viewer                              # read the quarantine clock
```

The least-privilege grant is `roles/secretmanager.secretVersionManager` **and**
`roles/secretmanager.viewer`, bound **on each secret you name**. Neither alone is
enough: `secretVersionManager` does not include `secretmanager.secrets.get`, so
without `viewer` every `secrets describe` 403s. Verify that by permission list, not
by role name.

The one thing that cannot be resource-scoped is *enumerating* a project's secrets.
So `secrets_list: ''` — sweep everything — additionally needs project-level
`secretmanager.secrets.list`. **Name your secrets and you never need it**, which is
another reason to prefer the explicit list.

`secretmanager.secretAccessor` is deliberately **not** required. The sweep reads
metadata and never reads a payload, so it cannot leak one.

## Usage

```yaml
name: Sweep secret versions

on:
  schedule:
    - cron: '0 5 1 * *'      # monthly, after the rotation cadence has settled
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: true
      enable_destroy:
        type: boolean
        default: false

jobs:
  sweep:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/cleanup-secret-versions.yml@v2.4.0
    permissions:
      contents: read
      id-token: write
    with:
      gcp_project:     auto-mahn
      gcp_region:      asia-southeast1
      wif_provider:    projects/750513647348/locations/global/workloadIdentityPools/github/providers/github
      service_account: github-rotator@auto-mahn.iam.gserviceaccount.com
      secrets_list:    app-secrets
      dry_run:         ${{ github.event_name == 'schedule' || inputs.dry_run }}
      enable_destroy:  ${{ github.event_name != 'schedule' && inputs.enable_destroy }}
```

Note what that `dry_run` expression does: the **schedule never applies**. A
monthly cron reports the plan and nothing more; destroying is always a human
pressing the button after reading it. That is the recommended shape for an
irreversible sweep, and it is why `enable_destroy` exists as a separate input
rather than being folded into `dry_run`.

## Rollout

1. Run with the defaults (`dry_run: true`). Read the plan.
2. Run with `dry_run: false`, `enable_destroy: false`. This **disables** the
   versions the plan named and starts their quarantine clock. Everything here is
   reversible with `gcloud secrets versions enable`.
3. Leave it alone for `quarantine_days`. If nothing broke, nothing was in use.
4. Run with `enable_destroy: true` to destroy what has served quarantine.

Steps 2 and 4 are the same command a month apart. That gap is the whole safety
property — do not compress it because the first run looked fine.

## Testing

The sweep-plan algorithm is covered by `tests/run_secret_plan_tests.py`, which
extracts the `python3 <<'PY'` block **from this workflow** and runs that exact
source against fixtures in `tests/fixtures-secrets/` — there is no second copy to
drift. Every fixture additionally asserts the two invariants:

- the version `latest` resolves to is never in the disable or destroy set;
- no secret is ever left with zero `ENABLED` versions.

The suite is mutation-tested: dropping the `latest` guard, moving the quarantine
boundary by one, substituting `max(version)` for the resolved `latest`, ignoring
consumer pins, or destroying on an unknown clock each fail at least one fixture.
