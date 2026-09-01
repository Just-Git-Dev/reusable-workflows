# validate-alerts

PR-time preflight for the alert-policy files that [`bootstrap-alerts`](bootstrap-alerts.md)
applies.

It exists because of an RCA: five latent bugs in one policy set were found only by running
the apply loop against the live project — each an `INVALID_ARGUMENT` that a human fixed and
re-ran, one at a time. This moves that discovery to the PR.

## Why not `--validate-only`

**The Monitoring API has no such mode.** `projects.alertPolicies.create` in the v3 discovery
document accepts exactly one parameter (`name`); there is no `validateOnly` query param, and
`gcloud alpha monitoring policies create` exposes no `--validate` flag. The only server-side
check available is to actually create the policy. So this validates in two cheaper layers
instead.

### Layer 1 — offline lint (no credentials)

Structural rules encoding the exact constraints that produced the RCA's `INVALID_ARGUMENT`s:

- a log-based policy must declare a notification rate limit;
- `autoClose` has a `30m`..`168h` domain;
- `displayName` must be greppable;
- the channel placeholder must be present, or the apply writes a literal string into the
  policy.

### Layer 2 — query execution (needs GCP auth)

Every policy's query is run against the API that will later evaluate it. Short of creating the
policy for real, this is the only way to catch a semantically invalid query — the RCA's
headline bug was a `ratio numerator:/denominator:` form that is not MQL at all.

| Condition kind | Endpoint |
|---|---|
| `conditionMonitoringQueryLanguage` | `projects.timeSeries.query` (MQL) |
| `conditionPrometheusQueryLanguage` | `v1/projects/<p>/location/global/prometheus/api/v1/query` (PromQL) |

Both run, and a policy set may mix them. Two rules the layer holds to in either language:

- **A 2xx is not consent.** The Prometheus-compatible endpoint can answer `200` with an
  `{"status":"error"}` envelope; reading only the status code would pass a rejected query.
- **"Could not check" is never "checked and fine".** A `401`/`403` fails the job outright and
  writes no `*_checked` count, rather than reporting zero validated queries as success.

PromQL was **lint-only until 2026-09-01** — `conditionPrometheusQueryLanguage` was accepted by
the structural lint and then never executed, so a PromQL policy earned a green tick from a
check that had not checked it. Metrics ingested through Managed Prometheus/OTel land as
`prometheus.googleapis.com/<name>/<kind>` and are queried in PromQL, so that is the path
application-level policies take. See DECISIONS.md 2026-09-01.

**Omit `gcp_project` to run layer 1 alone**, with no credentials. That is the useful default
for a fork PR.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `alerts_dir` | no | `infra/alerts` | directory in the caller repo |
| `channel_file` | no | `email-channel.yaml` | relative to `alerts_dir` |
| `policy_glob` | no | `policy-*.yaml` | relative to `alerts_dir` |
| `gcp_project` | no | `''` | set to enable layer 2; empty = offline lint only |
| `wif_provider` | no | `''` | required when `gcp_project` is set |
| `service_account` | no | `''` | required when `gcp_project` is set |

## Outputs

`policies_checked` (files that passed the offline lint), `mql_checked` and `promql_checked`
(queries actually executed in each language — `0` when layer 2 is skipped).

The two `*_checked` counts are worth asserting on in a caller: they are how you tell "layer 2
passed" from "layer 2 never ran". A policy set that is entirely PromQL has `mql_checked: 0`
and vice versa, so assert the one that matches your policies.

## Required IAM

Layer 2 only. On `service_account`: `monitoring.timeSeries.list` —
`roles/monitoring.viewer` is enough, and covers both the MQL and the Prometheus-compatible
read path.

## Example caller

```yaml
name: Validate alert policies
on:
  pull_request:
    paths: ['infra/alerts/**']

permissions:
  contents: read
  id-token: write

jobs:
  validate:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/validate-alerts.yml@v2.6.0
    with:
      # Omit the three GCP inputs to run the offline lint only.
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_INFRA_SA }}
```
