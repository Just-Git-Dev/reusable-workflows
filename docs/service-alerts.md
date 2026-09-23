# service-alerts

Turns an [AlertSpec](alertspec.md) (`infra/alerts/alerts.yaml`) into Cloud Monitoring alert
policies and applies them. You pick built-in packs (Cloud Run, GoFr HTTP/SQL/Redis, GoFr
telemetry health, log matches), change the thresholds that don't fit, and add custom alerts on
your own metrics. You write no PromQL and no policy JSON.

## Why this exists

Before this, every app wrote its own policies by hand. Two apps had near-identical 5xx, p95,
memory and crash-loop policies that differed only by service name. None alerted on a GoFr
metric. The 5xx policies were MQL, whose support ended on 2025-07-22. One app had no alerts at
all: its only check was an uptime probe on `/alive`, which stayed green through a 27-hour
database outage.

## What one run does

1. **Resolves its own commit** from the job's OIDC token (`job_workflow_sha`), then checks this
   repository out at exactly that commit. The code that renders is the code you pinned. With a
   tag pin, the log shows the annotated tag *object's* SHA, not the commit's (for `@v2.10.0`
   that is `1687ae3`, which peels to commit `b5678ad`). That is expected.

   If a run fails at the live-data check with `CANNOT VERIFY … HTTP 403 … monitoring.timeSeries.list`,
   the service account is missing its role ([IAM](#iam)). The spec is fine.
2. **Renders** the spec: one `policy-<rule>.yaml` per policy, plus `probes.json` and
   `manifest.json`. They are uploaded as the artifact `alertgen-<project>-<spec hash>`.
3. **Lints** the policies with validate-alerts' offline lint, run as shipped.
4. **Checks live data.** For each rule it runs the rule's series *without* the threshold over the
   last day. No data means the alert can never fire, so the run fails with CANNOT VERIFY. Two
   cases only warn: a custom rule marked `may_be_absent`, and a service that simply had no
   traffic that day. If *no* rule has data, the run fails and says it was probably looking at
   the wrong project or used an identity that can't read metrics.
5. **Executes** every PromQL condition against the Monitoring API (validate-alerts' layer 2).
6. **Applies** with bootstrap-alerts' channel and apply steps, as shipped. With `dry_run` (the
   default) it prints `would create` / `would update` / `unchanged` and writes nothing.

Steps 3 and 6 run the named `run:` bodies of `validate-alerts.yml` and `bootstrap-alerts.yml`
from the same commit, so there is one linter and one applier. The service-alerts workflow
can't call those two workflows directly: a `./` reference inside a called workflow resolves in
*your* repository, not this one.

## Copy-paste: plan on PRs, apply on main

```yaml
name: Alerts
on:
  pull_request:
    paths: ['infra/alerts/**']
  push:
    branches: [main]
    paths: ['infra/alerts/**']

jobs:
  alerts:
    permissions:
      contents: read
      id-token: write
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/service-alerts.yml@v2.10.0
    with:
      gcp_project: my-project
      wif_provider: projects/123456789/locations/global/workloadIdentityPools/github/providers/github
      service_account: github-rotator@my-project.iam.gserviceaccount.com
      dry_run: ${{ github.event_name == 'pull_request' }}
```

Pin the latest release tag (see [AGENTS.md](../AGENTS.md#1-resolve-the-version-to-pin)).
`id-token: write` is required twice over: once for WIF, and once for the step that reads the
workflow's own commit from the token. If it's missing, GitHub fails the whole run at startup
with no logs.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `gcp_project` | — | Project the policies belong to. |
| `wif_provider` | — | WIF provider resource name. |
| `service_account` | — | SA to impersonate; see [IAM](#iam). |
| `spec_file` | `infra/alerts/alerts.yaml` | The AlertSpec, in your repo. |
| `channel_file` | `infra/alerts/email-channel.yaml` | Notification channel, same format as bootstrap-alerts. |
| `dry_run` | `true` | Plan only. Pass `false` (or an expression) to apply. |
| `force_update` | `false` | Rewrite every managed policy even if its spec is unchanged, to reset hand edits reported as drift. |

Outputs: `policies_rendered`, `policies_created`, `policies_updated`, `policies_unchanged`,
`policies_drifted`, `spec_hash`. Under `dry_run` the counts are the plan.

## IAM

`roles/monitoring.editor` on the project covers alert policies, notification channels and
`monitoring.timeSeries.list`, which the data check and the PromQL execution need.

**Log-match rules (pack `gcp-logs`) are UNVERIFIED.** One app's config notes that creating a
log-match policy needs `logging.notificationRules.create`. A read of the API schema suggests it
doesn't. The first real apply will settle it. If it is needed, the create fails with
`PERMISSION_DENIED` naming that permission; grant `roles/logging.configWriter` through
infra-provisioning and re-run. Nothing else in the run is affected.

## How updates work

Every rendered policy carries these `userLabels`:

| Label | Example | Purpose |
|---|---|---|
| `managed_by` | `alertgen` | Marks the policy as generated. |
| `alertgen_owner` | `my-org_my-repo` | Your repo (`github.repository`), so two repos can't overwrite each other's policies. |
| `rule_id` | `gofr-http-server-error_ratio` | Which rule this is. |
| `spec_hash` | `37e44dd9592c348e` | Hash of the rendered policy. |
| `catalog_version` | `1-0-0` | Which catalog built it. |

The applier finds a managed policy by **owner + rule_id**, never by display name:

- **Not found** → create it.
- **Found with the same `spec_hash`** → leave it (`unchanged`). If someone hand-edited it since
  (the live policy no longer matches the render, including a hand-added condition), you get a
  *drift* warning. It is not overwritten, because the spec didn't change; `force_update: true`
  resets it.
- **Found, but notifying a different channel** → update it. The hash is taken before the
  channel is filled in, so without this a recreated channel would never reach the policies.
- **Found with a different `spec_hash`** → update it. If a person, not the applier SA, last
  edited it, you get a warning naming them before their edit is overwritten.
- **A hand-written policy already has the managed policy's display name** → the run fails for
  that policy. See the migration section below.

Removing a rule from the spec does **not** delete its policy yet (`prune` is deferred). Delete
it by hand in the console.

## Migrating from hand-written policies

1. Write `alerts.yaml` with the packs that match your existing policies. Run with `dry_run`
   and read the plan and the rendered artifact.
2. **Parity check.** For each hand-written policy, find the rendered one covering the same
   signal and compare threshold, window and severity. A difference must be deliberate: either
   add an override, or accept the default and say so in your PR.
3. Apply. You now have both sets, briefly, so an incident can alert twice.
4. Delete the hand-written policy files and the policies themselves (console, or `gcloud
   alpha monitoring policies delete`). Keep the channel file; service-alerts uses it.

Do step 4 promptly. Until it's done, a failure pages twice, and people learn to ignore pages.

## Proving it works

A green run proves the policies exist and their queries are valid. It doesn't prove anyone gets
an email. After the first apply, do one fire test: add a throwaway override such as
`cloudrun.latency_p95: {threshold: 1ms, for: 0s, min_requests: 1}`, apply, send the service
a request or two, wait for the email, then revert and apply again.

**Keep `min_requests: 1`.** Without it, the traffic guard's default of 20 requests per 10
minutes still applies. On a quiet service the alert then can't fire however low the
threshold is, and a silent test reads as a broken channel when the guard is working as
designed. Found on realm-id (about 2 requests an hour), 2026-09-23.

For a log-match rule, point its `filter` at a harmless line that appears routinely, then
revert. There is no traffic guard, and the 300s rate limit caps the emails.

**Confirm the incident OPENED before you revert. A true condition is not an incident.**
Running the rule's PromQL yourself and seeing it true proves nothing about the policy: Cloud
Monitoring evaluates on its own schedule (about 3 minutes here), and reverting before that
leaves nothing to show. This happened on realm-id's first fire test, which was reverted 2.5
minutes after arming. Poll the incident-open log instead of sleeping for a fixed time:

```bash
gcloud logging read 'logName:"monitoring.googleapis.com%2FViolationOpenEventv1"' \
  --project=<project> --freshness=30d --format='value(timestamp)'
```

Read it with a **positive control**. It should also show an older incident you know fired, if
the project has one. A new entry means the incident opened; revert after that. If the log is
empty with no known-good entry either, you can't tell "nothing fired" from "wrong project or
identity". Email delivery still has to be confirmed in the inbox.

## Deferred (v2.11+)

`prune`; the uptime probe that checks the health response body; packs for GoFr outbound HTTP,
pub/sub and cron (their metrics don't exist in any fleet project yet, so they can't be checked
live); `absence` rules; raw `promql:`; the Dynatrace renderer.
