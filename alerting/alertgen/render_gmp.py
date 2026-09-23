"""Rules -> Cloud Monitoring AlertPolicy documents (GMP / Cloud Logging).

Each policy is shaped to pass validate-alerts' shipped lint unchanged (a conformance test runs
that exact body over every render) and carries the userLabels bootstrap-alerts' managed update
keys on: managed_by, alertgen_owner, rule_id, spec_hash, catalog_version. The policy is found
by owner + rule_id, never by displayName, and replaced only when spec_hash moves.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field

from . import CATALOG_VERSION
from .compile import SEVERITIES
from .spec import SpecError
from .units import fmt_duration, fmt_num

PLACEHOLDER = "NOTIFICATION_CHANNEL_PLACEHOLDER"
EVALUATION_INTERVAL = "60s"   # PromQL evaluationInterval must be a positive multiple of 30s
# PromQL policies ignore autoClose (they close after max(270s, 2x interval) without data),
# but validate-alerts requires it and log-match policies do honour it.
AUTO_CLOSE = "1800s"
_LABEL_BAD = re.compile(r"[^a-z0-9_-]")


@dataclass
class Output:
    policies: list = field(default_factory=list)   # [(filename, policy dict)]
    probes: list = field(default_factory=list)


def label_value(raw: str) -> str:
    """Cloud Monitoring userLabels values: [a-z0-9_-], at most 63 chars."""
    v = _LABEL_BAD.sub("_", raw.lower().replace(".", "-"))
    if len(v) > 63:
        v = v[:54] + "-" + hashlib.sha256(raw.encode()).hexdigest()[:8]
    return v


def owner_label(owner: str) -> str:
    """`Org/Repo` -> `org_repo`."""
    return _LABEL_BAD.sub("_", owner.lower())[:63]


def _log_filter(rule):
    svcs = " OR ".join(f'resource.labels.service_name="{s}"' for s in rule.services)
    return f'resource.type="cloud_run_revision" AND ({svcs}) AND ({rule.log_filter})'


def _condition_text(rule):
    if rule.is_log:
        return (f"any log entry matching the filter; at most one notification per "
                f"{fmt_duration(rule.rate_limit)}")
    parts = []
    if rule.threshold is not None:
        parts.append(f"{rule.op} {rule.threshold_text} (compared as {fmt_num(rule.threshold)})")
    parts.append(f"over {fmt_duration(rule.window)}")
    parts.append(f"for {fmt_duration(rule.for_)}")
    if rule.min_requests is not None:
        parts.append(f"only with at least {rule.min_requests} requests in the window")
    return ", ".join(parts)


def _documentation(rule, rid):
    query = rule.log_filter if rule.is_log else rule.expr
    lines = [
        f"**{rule.summary}** — services: {', '.join(rule.services)}.",
        "",
        rule.triage,
        "",
        f"- Rule: `{rule.id}`" + (f" (pack `{rule.pack}`, catalog {CATALOG_VERSION})" if rule.pack
                                  else " (custom rule)"),
        f"- Condition: {_condition_text(rule)}",
        f"- Query: `{query}`",
        "",
        f"Managed by alertgen from `infra/alerts/alerts.yaml` (rule_id `{rid}`). Change the spec, "
        "not this policy: the next apply that changes the spec overwrites hand edits.",
    ]
    return "\n".join(lines)


def render_policy(rule, owner: str):
    rid = label_value(rule.key)
    cond_name = f"{rule.summary} ({', '.join(rule.services)})"
    if rule.is_log:
        condition = {"displayName": cond_name,
                     "conditionMatchedLog": {"filter": _log_filter(rule)}}
        strategy = {"autoClose": AUTO_CLOSE,
                    "notificationRateLimit": {"period": f"{int(rule.rate_limit)}s"}}
    else:
        cfg = {"query": rule.expr, "evaluationInterval": EVALUATION_INTERVAL}
        # A zero duration is the API default and is dropped from what it returns, so
        # emitting "0s" would read as drift on every run.
        if rule.for_:
            cfg["duration"] = f"{int(rule.for_)}s"
        if rule.may_be_absent:
            cfg["disableMetricValidation"] = True
        condition = {"displayName": cond_name, "conditionPrometheusQueryLanguage": cfg}
        strategy = {"autoClose": AUTO_CLOSE}
    policy = {
        "displayName": f"{rule.summary} ({', '.join(rule.services)}) [{rule.key}]",
        "documentation": {"content": _documentation(rule, rid), "mimeType": "text/markdown"},
        "combiner": "OR",
        "conditions": [condition],
        "alertStrategy": strategy,
        "severity": SEVERITIES[rule.severity],
        "notificationChannels": [PLACEHOLDER],
        "enabled": True,
        "userLabels": {
            "managed_by": "alertgen",
            "alertgen_owner": owner_label(owner),
            "rule_id": rid,
            "catalog_version": label_value(CATALOG_VERSION),
        },
    }
    digest = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:16]
    policy["userLabels"]["spec_hash"] = digest
    return f"policy-{rid}.yaml", policy


def render(rules, *, owner: str) -> Output:
    out = Output()
    seen = {}
    for r in rules:
        fname, pol = render_policy(r, owner)
        # Two rules on one file would overwrite each other and one policy would vanish
        # without a word; two on one rule_id would make the managed update ambiguous.
        if fname in seen:
            raise SpecError(f"rules {seen[fname]!r} and {r.key!r} both render to rule_id "
                            f"{pol['userLabels']['rule_id']!r} — rename one")
        seen[fname] = r.key
        out.policies.append((fname, pol))
        if not r.is_log:
            out.probes.append({
                "rule_id": pol["userLabels"]["rule_id"], "policy_file": fname,
                "expr": r.probe, "services": r.services,
                "service_label": r.metric.service_label, "may_be_absent": r.may_be_absent,
            })
    return out
