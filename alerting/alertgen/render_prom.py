"""Rules -> a Prometheus rule file (or a PrometheusRule CR).

Two uses. For a Prometheus / Kubernetes target, only portable rules render; a GCP-only rule
(Cloud Run metrics, log matches) is an error rather than a rule that could never fire. With
oracle=True every PromQL rule renders, GCP-only ones included, so `promtool test rules` can
execute the exact expressions GMP will evaluate against synthetic series — this repo's
semantic test oracle.
"""
from .spec import SpecError
from .units import fmt_duration


def alert_name(key: str) -> str:
    return key.replace(".", "_").replace("-", "_")


def render(rules, *, oracle=False, crd_name=None):
    if not oracle:
        gcp_only = [r.key for r in rules if "prometheus" not in r.platforms]
        if gcp_only:
            raise SpecError(f"these rules are GCP-only and cannot render for Prometheus: "
                            f"{', '.join(gcp_only)} — drop their packs or disable them")
    out = []
    for r in rules:
        if r.is_log:
            continue
        out.append({
            "alert": alert_name(r.key),
            "expr": r.expr,
            "for": fmt_duration(r.for_),
            "labels": {"severity": r.severity},
            "annotations": {"summary": f"{r.summary} ({{{{ $labels.{r.metric.service_label} }}}})",
                            "description": r.triage},
        })
    groups = {"groups": [{"name": "alertgen", "rules": out}]}
    if crd_name:
        return {"apiVersion": "monitoring.coreos.com/v1", "kind": "PrometheusRule",
                "metadata": {"name": crd_name}, "spec": groups}
    return groups
