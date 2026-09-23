# AlertSpec — service alerts as data

An **AlertSpec** is a short YAML file an app repo keeps at `infra/alerts/alerts.yaml`. It says
which built-in rule *packs* to turn on, which thresholds to change, and which extra alerts to
add on the app's own metrics. No PromQL is needed.

The spec is **semantic**: every rule is a metric, a *kind* (error ratio, rate, latency
quantile, value), label filters, a window and a threshold with units. A compiler
(`alerting/alertgen/`) turns that into whatever the backend needs. Today that is Cloud
Monitoring alert policies over Google Managed Prometheus (GMP); the same rules also render as a
Prometheus rule file, which this repo's tests run through `promtool` to check the rules
behave correctly.

[`service-alerts`](service-alerts.md) is the workflow that renders a spec and applies it.
This page covers the format.

## A complete example

```yaml
apiVersion: alertspec/v1
services: [issuer, api]            # GoFr `job` label == Cloud Run service_name
packs: [cloudrun, gofr-http, gofr-sql, gofr-meta, gcp-logs]
overrides:
  cloudrun.5xx_count:           {threshold: 5, window: 10m}  # a default-off rule: configuring it turns it on
  cloudrun.latency_p95:         {threshold: 5s, for: 10m}    # → 5000 (ms) for Cloud Run
  gofr.http.server.error_ratio: {severity: ticket}
  gofr.sql.pool_saturation:     {enabled: false}
  gofr.http.server.latency_p95:
    services:
      issuer: {threshold: 4s}      # issuer gets its own policy; api keeps the default
  logs.error_match:             {filter: 'jsonPayload.message:"exceeded the quota" OR jsonPayload.message:"could not connect"'}
custom:
  - id: bff-upstream-errors
    metric: {name: bff_upstream_error, type: counter}
    kind: rate
    filters: {code: {in: ["502", "503"]}}
    window: 10m
    op: ">"
    threshold: 0.1/s
    for: 10m
    severity: page
    summary: "BFF upstream 5xx rate is high"
    triage: >-
      The BFF is getting 502/503 from an upstream. Check which upstream in the logs
      (jsonPayload.upstream), then that upstream's own dashboard and recent deploys.
    may_be_absent: true            # metric may not exist yet
```

## Top-level keys

| Key | Required | Meaning |
|---|---|---|
| `apiVersion` | yes | Must be `alertspec/v1`. |
| `services` | yes | The services the packs cover. For GoFr metrics this is the `job` label (`APP_NAME`); for Cloud Run it is `service_name`. Keep the two equal. |
| `packs` | no | Built-in packs to turn on. See the [catalog](#catalog). |
| `overrides` | no | Per-rule changes, keyed by rule id. Unknown ids are an error. |
| `custom` | no | Extra alerts on your own metrics. |

Anything else is an error, so a typo can't silently turn a rule off.

## Precedence

For every rule, parameters are resolved in this order; later wins:

1. the catalog default;
2. `overrides.<rule id>`;
3. `overrides.<rule id>.services.<service>`.

Services that end up with **identical** parameters render as **one** policy, which fires one
incident per service (`sum by (job)`). A service with its own thresholds gets its own policy.
So the number of policies stays close to the number of rules, not rules × services.

**Turning rules on and off.**

- A default-on rule covers every service. `services: {worker: {enabled: false}}` drops one.
- A **default-off** rule (`cloudrun.5xx_count`, `logs.error_match`) turns on for every service
  when you write a rule-level override for it (`{threshold: 5}`) or `enabled: true`. Configured
  *only* per service (`services: {api: {enabled: true}}`), it covers just those services.
- `{enabled: false}` at rule level turns the rule off. Combining it with `enabled: true` for a
  service is an error, because the spec contradicts itself.
- A default-off rule that needs a parameter (`logs.error_match` needs `filter`) is an error if
  you enable it without one.

**Log filters on a GoFr app: never filter on `severity`.** GoFr writes its level as
`jsonPayload.level` (`"ERROR"`, `"FATAL"`, …) and never sets Cloud Logging's `severity`, so
every GoFr entry is stored at DEFAULT severity. `severity>=ERROR` silently matches nothing
the app itself logged. On realm-id, across a 27-hour outage, it matched 0 of 500+ datastore
errors; it only caught Cloud Run's own readiness-check messages.

**Don't narrow by `jsonPayload.level` either.** `level="ERROR"` excludes `FATAL`, which is the
worst entry there is. It also drops a `WARN` where the app downgraded a failure to
"transient". Of the 500 outage entries RealmID's text filter matched, the breakdown was ERROR
493, FATAL 6, WARN 1, so an `AND jsonPayload.level="ERROR"` clause loses the six fatal exits.
Match the **failure text** instead, as in the example above. Check the filter in Logs
Explorer against a window where the failure happened (it should match) and a healthy one (it
shouldn't).

**Service names** follow Cloud Run's rule: lowercase letters, digits and `-`, starting with a
letter. Two rules whose ids reduce to the same `rule_id` label (for example a custom
`gofr-http-server-error_ratio` next to the catalog's `gofr.http.server.error_ratio`) are an
error, rather than one silently overwriting the other.

Override keys: `enabled`, `threshold`, `window`, `for`, `severity`, `min_requests`,
`filters`, `filter` (log rules), `rate_limit` (log rules), `services`. Anything else is an
error.

## Units

A threshold carries its unit, and the compiler converts it to the unit the metric is stored
in. GoFr and Cloud Run do not agree:

| Metric | Stored in | `2s` becomes | `250ms` becomes |
|---|---|---|---|
| Cloud Run `request_latencies` | ms | `2000` | `250` |
| GoFr `app_http_response` | s | `2` | `0.25` |
| GoFr `app_sql_stats` | ms | `2000` | `250` |
| GoFr `app_redis_stats` | µs | `2000000` | `250000` |

| You write | Means | Allowed on |
|---|---|---|
| `2s`, `250ms`, `500us`, `1m` | a duration | latency quantiles |
| `5%` or `0.05` | a ratio | error ratios, saturation, memory |
| `0.1/s`, `6/m`, `100/h` | events per second after conversion | `rate` |
| `5` | a plain count | `cloudrun.5xx_count`, `value` on unitless gauges |

**A bare number on a duration metric is an error.** `threshold: 5` on a latency could mean 5
ms or 5 s depending on the metric, and guessing wrong silences the alert. A bare ratio above
1 (`threshold: 5` on an error ratio) is also an error; write `5%`.

Windows and `for` are durations: `10m`, `1h`, `90s`. `for` becomes the policy condition's
`duration`.

## Kinds (for `custom`)

| Kind | Needs | Expression shape |
|---|---|---|
| `error_ratio` | counter or histogram; `bad` filters | `sum(rate(bad)) / sum(rate(all)) > T` **and** at least `min_requests` in the window |
| `rate` | counter or histogram | `sum(rate(m)) > T` (T per second) |
| `latency_quantile` | histogram with `unit` (`s`, `ms`, `us`); optional `quantile` (default 0.95) | `histogram_quantile(q, …) > T` **and** at least `min_requests` in the window |
| `value` | gauge; optional `agg` (`max` default, `min`, `avg`, `sum`) | `agg by (job)(agg_over_time(m[W])) op T` |

Custom rule fields: `id` (lowercase, `[a-z0-9._-]`), `metric: {name, type, unit?,
service_label?}` (`service_label` defaults to `job`), `kind`, `filters`, `bad` (error_ratio
only), `window`, `op` (`>`, `>=`, `<`, `<=`), `threshold`, `for`, `severity`, `summary`,
`triage` (at least 80 characters — say what broke and what to check first), `services`
(defaults to all), `may_be_absent`. `op` defaults to `>` and `for` to `10m`. Kind-specific:
`bad` and `min_requests` (error_ratio), `quantile` and `min_requests` (latency_quantile), `agg`
(value). A kind-specific key on the wrong kind is an error, not ignored: `bad:` on a `rate`
rule would otherwise alert on all traffic. `min_requests` defaults to 20 for error ratios and
for latency histograms in `s`/`ms`/`us`. It has no default for other histograms, because
there it would count samples, not requests.

**Filters.** `{label: "v"}` is equality. `{label: {in: [a, b]}}`, `{label: {not_in: [...]}}`,
`{label: {regex: "5.."}}`, `{label: {not_regex: ...}}`, `{label: {not: "v"}}` do what they
say. Values are escaped for you.

**`may_be_absent: true`** is for a metric that may not exist yet (a code path nobody has hit).
The live data check then warns instead of failing, and the policy is created with metric
validation off. Without it, a rule on a metric that has never been exported fails the render,
because an alert on a metric that doesn't exist can never fire.

**Raw `promql:` is not accepted** in `alertspec/v1`. It can't be ported to a backend with no
PromQL (see the portability table), and the escape hatch is deferred until a real need shows up.

## Guards: why a quiet service does not page

Every ratio and quantile rule carries a traffic guard:

```
(sum by (job)(rate(bad[W])) / sum by (job)(rate(all[W]))) > T
  and sum by (job)(increase(all[W])) >= N
```

- 0 requests: `0/0` is NaN, and NaN compares false. No alert.
- 3 requests, 1 failed (33%): below `min_requests` (default 20). No alert.
- 100 requests, 10 failed (10%): fires.

Both sides of `and` group by the same label, so they match series one to one. The golden tests
check this. Default windows are 10 minutes or more, because scale-to-zero services flap on
shorter ones.

## Severity

`page` → policy severity `CRITICAL`; `ticket` → `WARNING`. Route them to different
notification channels in the Cloud Monitoring console if you want pages and tickets split.

## Catalog

<!-- BEGIN GENERATED CATALOG (scripts/gen_alert_catalog.py) -->
| Pack | Rule id | Signal | Default | Severity | On by default |
|---|---|---|---|---|---|
| `cloudrun` | `cloudrun.5xx_ratio` | Cloud Run 5xx / all requests, per service | > 5% over 10m, for 10m, min 20 req | page | yes |
| `cloudrun` | `cloudrun.5xx_count` | Cloud Run 5xx count per window (low-traffic services) | > 5 over 10m, for 0s | page | no |
| `cloudrun` | `cloudrun.latency_p95` | Cloud Run p95 request latency | > 2s over 10m, for 10m, min 20 req | ticket | yes |
| `cloudrun` | `cloudrun.memory_p99` | Cloud Run p99 container memory utilisation | > 85% over 10m, for 10m | ticket | yes |
| `gcp-logs` | `logs.crash_loop` | FATAL / CRITICAL log entries or unrecovered Go panics on a Cloud Run revision | any match, rate limit 300s | page | yes |
| `gcp-logs` | `logs.error_match` | Log entries matching a filter you supply | any match, rate limit 300s | page | no |
| `gofr-http` | `gofr.http.server.error_ratio` | GoFr HTTP 5xx / all responses, per service | > 5% over 10m, for 10m, min 20 req | page | yes |
| `gofr-http` | `gofr.http.server.latency_p95` | GoFr HTTP p95 response time | > 2s over 10m, for 10m, min 20 req | ticket | yes |
| `gofr-meta` | `gofr.metrics.silent_while_serving` | Cloud Run is serving traffic but GoFr exports no HTTP metrics | over 30m, for 30m | ticket | yes |
| `gofr-redis` | `gofr.redis.latency_p95` | GoFr Redis p95 command time | > 50ms over 10m, for 10m, min 20 req | ticket | yes |
| `gofr-sql` | `gofr.sql.latency_p95` | GoFr SQL p95 query time | > 500ms over 10m, for 10m, min 20 req | ticket | yes |
| `gofr-sql` | `gofr.sql.pool_saturation` | GoFr SQL connections in use / open | > 90% over 10m, for 10m | ticket | yes |
<!-- END GENERATED CATALOG -->

`gofr-meta` and `gcp-logs` are GCP-only. The GoFr packs work on any Prometheus.

## Portability

| Backend | Status | How each kind renders |
|---|---|---|
| Cloud Monitoring (GMP) | **live** | `conditionPrometheusQueryLanguage`; log rules → `conditionMatchedLog` |
| Prometheus / `PrometheusRule` | **rendered** (`--target prometheus`); used as the test oracle | the same PromQL as a rule file |
| Dynatrace (DQL) | **documented mapping, not built** | see below |

The Dynatrace mapping, for when it is built: a GoFr histogram arrives in Dynatrace as an OTLP
explicit-bucket histogram and keeps its buckets, so `latency_quantile` becomes
`timeseries percentile(app_http_response, 95), by:{job}`; `error_ratio` becomes two
`timeseries sum(…)` series divided; `rate` and `value` map directly. The alert itself is a
Settings 2.0 `builtin:davis.anomaly-detectors` object, managed with Monaco or Terraform. Cloud
Run metrics and log rules have no Dynatrace meaning and are not rendered there. Dynatrace has no
PromQL, which is why raw `promql:` is refused.

**Why not OpenSLO?** Its `metricSource.spec` is a raw query written for one vendor, so a spec
would still need one query per backend. Its alerting objects are burn-rate alerts on SLOs, not
threshold alerts. An SLO kind that emits OpenSLO can be added later without changing this format.

## Catalog versioning

The catalog ships inside this repo's releases, so it follows the same semver:

- **Minor** (called out at the top of the release notes): a default threshold tightened or
  loosened, or a rule added to a pack.
- **Major**: a rule id removed or renamed, or a rule changed from `ticket` to `page`.

Each policy carries `catalog_version` in its `userLabels`, so you can see which catalog built it.

## Running it locally

```bash
PYTHONPATH=alerting python3 -m alertgen validate --spec infra/alerts/alerts.yaml
PYTHONPATH=alerting python3 -m alertgen render --spec infra/alerts/alerts.yaml \
  --target gmp --owner my-org_my-repo --out rendered/
```

`validate` prints the resolved rules and any warnings. `render --target gmp` writes one
`policy-<rule>.yaml` per policy plus `probes.json`, the un-thresholded expressions the workflow
runs against live data. `render --target prometheus` writes `prometheus-rules.yaml`.
