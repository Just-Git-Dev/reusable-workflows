# verify-metrics-arrival

A post-deploy probe that asks, from **outside** the container, whether the observability
pipeline actually delivers — and fails the release when it does not.

## Why this exists

Traide's api ran **for weeks** exporting zero metrics. Its `OTEL_RESOURCE_ATTRIBUTES` lacked
`gcp.project_id`, so every 30-second export was assembled, authenticated, sent, and rejected
with `InvalidArgument`. Every gate stayed green the whole time — deploy, the Cloud Run startup
probe, `/.well-known/alive`, `migrate-smoke`, `storage-probe` — because the only evidence was a
log line *inside* the container, and the thing that would have raised the alarm was the
pipeline that was down.

> A broken write path announces itself; a broken observability path removes the very signal
> that would announce it.

Above the container log, "exporter broken" and "quiet system" are indistinguishable. It even
survived a direct review of this exact area: a dependency bump was argued and shipped on the
reasoning that unbounded `path` labels would degrade Cloud Monitoring — while no metric had
ever reached Cloud Monitoring. **Configuration that expresses an intent is not evidence the
intent is met.**

## Three outcomes, not two

This is the whole design. The probe reports one of:

| Outcome | Meaning | Job |
|---|---|---|
| **PASS** | descriptors exist under at least one app prefix | green |
| **FAIL — no metrics** | the control proved the probe *can* see, and there is nothing | red |
| **FAIL — cannot verify** | the probe could not see at all | red |

The third is the point. A probe that returns zero because it queried the wrong project, under
an account without permission, or against a project whose Monitoring API is off must **fail
loudly** — never read as "no metrics yet", and never pass. This extends the house rule already
written into [`validate-alerts`](validate-alerts.md): *never treat "could not check" as
"checked and fine".*

### The positive control

Before asking the real question, the probe runs an **unfiltered** `metricDescriptors.list`
with `pageSize=1`. Every live project carries Google's own built-in descriptors, so a non-empty
answer proves four things at once: the project id resolves, the credentials work, the service
account holds `monitoring.metricDescriptors.list`, and the Monitoring API is enabled.

An empty control is therefore **not** a quiet project — it is a project id that resolved to
something the probe is not looking at. That is `cannot-verify`.

## The two checks

They catch different things, and neither subsumes the other.

**1 — Descriptor existence** catches *never worked* (Traide's bug). Descriptors are created on
first ingestion, so their absence proves nothing was ever accepted. But they **persist for
~24h** after ingestion stops, so this check cannot see a breakage that started an hour ago.

**2 — The exporter log grep** catches a *new* breakage within minutes, which descriptors
cannot. It reads the **serving** revision — the one carrying traffic. Grepping a superseded
revision reports on code that is no longer running: it would go green over a broken deploy and
red over a fixed one. Set `cloud_run_service` + `region` to enable it; it is off by default.

## Two traps this workflow is built around

Both measured on 2026-09-18, and either one sinks a naive implementation.

- **`gcloud monitoring metrics-descriptors` does not exist.** It errors `Invalid choice`, and
  `| wc -l` over the empty stdout returns `0` — i.e. it reports "no metrics ever arrived". This
  workflow uses the Monitoring REST API and asserts the HTTP status.
- **A wrong prefix returns a truthful-looking zero.** On `realm-id`, `custom.googleapis.com/`
  = 0 and `workload.googleapis.com/` = 0, while `prometheus.googleapis.com/` = 7 — Managed
  Prometheus publishes under the `prometheus.` prefix. So `metric_prefixes` is a **list**, and
  PASS is the **union**: at least one prefix must hold a descriptor.

Pagination is deliberately not a correctness concern: the question is always "is there at least
one?", never "how many". Every call uses `pageSize=1` and tests the array for non-emptiness —
which matters, because `traide-in` holds 8,925 descriptors.

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `gcp_project` | **yes** | — | project whose Cloud Monitoring is queried |
| `wif_provider` | **yes** | — | Workload Identity Federation provider |
| `service_account` | **yes** | — | impersonated SA; see *Required IAM* |
| `metric_prefixes` | no | `prometheus.googleapis.com/,workload.googleapis.com/,custom.googleapis.com/,external.googleapis.com/` | comma-separated; PASS is the union |
| `cloud_run_service` | no | `''` | set (with `region`) to enable the log check |
| `region` | no | `''` | required when `cloud_run_service` is set |
| `log_error_pattern` | no | `failed to upload metrics` | any hit on the serving revision fails |
| `log_lookback_minutes` | no | `15` | how far back to read |

## Outputs

`prefixes_matched` (how many prefixes held a descriptor), `matched_prefixes` (which ones), and
`log_errors` (matching lines on the serving revision).

`log_errors` is the **empty string** when the log check was skipped, and `0` when it ran and
found nothing — that is how a caller tells "checked, clean" from "never ran".

## Required IAM

On `service_account`:

- `monitoring.metricDescriptors.list` — `roles/monitoring.viewer`.
- For the log check only: `logging.logEntries.list` (`roles/logging.viewer`) and
  `run.services.get` (`roles/run.viewer`).

In this fleet those are granted through the `observability-read` **capability** in
`infra-provisioning` (`bootstrap/capabilities.yaml`), and access is **WIF-only** — no service
account keys.

## Example caller

```yaml
name: Verify metrics arrival
on:
  workflow_run:
    workflows: ['Deploy']
    types: [completed]

permissions:
  contents: read
  id-token: write

jobs:
  verify:
    if: github.event.workflow_run.conclusion == 'success'
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/verify-metrics-arrival.yml@v2.10.0
    with:
      gcp_project: traide-in
      wif_provider: ${{ vars.GCP_WIF_PROVIDER }}
      service_account: ${{ vars.GCP_LOG_READER_SA }}
      # Enable the "is it broken right now?" half:
      cloud_run_service: traide-api
      region: asia-south1
```

## Where not to adopt it

A service that exports no metrics **at all** will red every release under this probe. Fix the
exporter first, then adopt. AutoMahn is the current example: it imports no GCP metrics
exporter, so its zero descriptors are an accurate report of a service that exports nothing.
