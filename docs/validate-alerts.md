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

### Layer 2 — MQL execution (needs GCP auth)

For `conditionMonitoringQueryLanguage` policies, the query is run through
`projects.timeSeries.query`. Short of creating the policy for real, this is the only way to
catch a semantically invalid pipeline — the RCA's headline bug was a
`ratio numerator:/denominator:` form that is not MQL at all.

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

`policies_checked` (files that passed the offline lint), `mql_checked` (MQL queries actually
executed — `0` when layer 2 is skipped).

`mql_checked` is worth asserting on in a caller: it is how you tell "layer 2 passed" from
"layer 2 never ran".

## Required IAM

Layer 2 only. On `service_account`: `monitoring.timeSeries.list` —
`roles/monitoring.viewer` is enough.

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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/validate-alerts.yml@v2.4.1
    with:
      # Omit the three GCP inputs to run the offline lint only.
      gcp_project: my-gcp-project
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_INFRA_SA }}
```
