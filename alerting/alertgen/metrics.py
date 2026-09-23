"""Registry of the metrics the built-in catalog uses.

Names are as GMP's PromQL view exposes them (VERIFIED on realm-id, 2026-09-23): GoFr metrics
unsuffixed with the service in `job`; Cloud Run metrics as `run_googleapis_com:<name>` with the
`monitored_resource` matcher, which GMP requires to find them. GoFr v1.61.0 units checked in
source: app_http_response seconds, app_sql_stats milliseconds, app_redis_stats microseconds.

`app_go_*` / `app_sys_*` are deliberately absent: GoFr only sets them inside the /metrics pull
handler, so they are never emitted when metrics are pushed over OTLP.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Metric:
    name: str                    # PromQL base name
    type: str                    # counter | histogram | gauge
    unit: str = "1"              # s | ms | us | ratio | count | 1
    service_label: str = "job"
    matchers: tuple = ()         # fixed (label, op, value) matchers every selector carries
    platforms: frozenset = field(default_factory=lambda: frozenset({"gmp", "prometheus"}))

    def series(self, part=None) -> str:
        """The series name for a histogram part ('bucket'|'count'|'sum') or the metric itself."""
        return f"{self.name}_{part}" if part else self.name


_CR = (("monitored_resource", "=", "cloud_run_revision"),)
_GCP = frozenset({"gmp"})

REGISTRY = {
    "cloudrun.request_count": Metric("run_googleapis_com:request_count", "counter", "count",
                                     "service_name", _CR, _GCP),
    "cloudrun.request_latencies": Metric("run_googleapis_com:request_latencies", "histogram", "ms",
                                         "service_name", _CR, _GCP),
    "cloudrun.memory_utilization": Metric("run_googleapis_com:container_memory_utilizations",
                                          "histogram", "ratio", "service_name", _CR, _GCP),
    "gofr.http_response": Metric("app_http_response", "histogram", "s"),
    "gofr.sql_stats": Metric("app_sql_stats", "histogram", "ms"),
    "gofr.sql_open": Metric("app_sql_open_connections", "gauge", "count"),
    "gofr.sql_in_use": Metric("app_sql_inUse_connections", "gauge", "count"),
    "gofr.redis_stats": Metric("app_redis_stats", "histogram", "us"),
}
