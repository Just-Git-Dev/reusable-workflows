"""Rule -> PromQL, in the dialect GMP accepts (which is also plain Prometheus).

GMP specifics: no regex on __name__ (never emitted), and Cloud Run series need the
`monitored_resource` matcher (carried by the Metric). Every ratio and quantile carries a
traffic guard joined with `and`, and both sides aggregate `by` the SAME single label, so they
match one to one — a guard grouped differently matches nothing and the alert never fires.

Each rule also yields a PROBE: an un-thresholded expression that returns >=1 series when the
underlying metric exists for the rule's services over the last day. service-alerts runs every
probe against live data before applying, because an alert on a metric that does not exist is
syntactically valid, passes every lint, and can never fire.
"""
import re

from .units import fmt_duration, fmt_num

PROBE_LOOKBACK = "1d"


def _q(v: str) -> str:
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


_RE2_META = re.compile(r"([\\.+*?()|\[\]{}^$])")


def _re_alt(values) -> str:
    """Literal alternation. Only RE2 metacharacters are escaped (Python's re.escape also
    escapes '-', which is legal but turns `my-svc` into `my\\-svc` in every query)."""
    return "|".join(_RE2_META.sub(r"\\\1", v) for v in values)


def _filter_matchers(filters):
    out = []
    for label, v in sorted((filters or {}).items()):
        if v is None:
            continue
        if isinstance(v, str):
            out.append((label, "=", v))
            continue
        op, arg = next(iter(v.items()))
        out.append({
            "in": (label, "=~", _re_alt(arg) if isinstance(arg, list) else arg),
            "not_in": (label, "!~", _re_alt(arg) if isinstance(arg, list) else arg),
            "regex": (label, "=~", arg),
            "not_regex": (label, "!~", arg),
            "not": (label, "!=", arg),
        }[op])
    return out


def _svc_matcher(label, services):
    if len(services) == 1:
        return (label, "=", services[0])
    return (label, "=~", _re_alt(sorted(services)))


def selector(metric, services, filters=None, extra=None, part=None):
    ms = list(metric.matchers) + [_svc_matcher(metric.service_label, services)]
    ms += _filter_matchers(filters) + _filter_matchers(extra)
    body = ",".join(f"{l}{op}{_q(v)}" for l, op, v in ms)
    return f"{metric.series(part)}{{{body}}}"


def _count_part(metric):
    return "count" if metric.type == "histogram" else None


def build(rule):
    """-> (alert expression, probe expression)."""
    m, L, W = rule.metric, rule.metric.service_label, fmt_duration(rule.window)
    T = fmt_num(rule.threshold) if rule.threshold is not None else None
    op = rule.op
    # The `bad` labels must EXIST, or the numerator is always empty and the rule can never
    # fire (`bad: {stauts: "500"}` renders fine and passes every other check). Their values
    # are not probed: a day with no errors is normal.
    exists = {label: {"not": ""} for label in (rule.bad or {})}
    probe_sel = selector(m, rule.services, rule.filters, exists, part=_count_part(m) or
                         ("bucket" if m.type == "histogram" else None))
    probe = f"group by ({L}) (last_over_time({probe_sel}[{PROBE_LOOKBACK}]))"

    def guard(all_sel):
        return f"sum by ({L}) (increase({all_sel}[{W}])) >= {rule.min_requests}"

    if rule.kind == "error_ratio":
        part = _count_part(m)
        all_sel = selector(m, rule.services, rule.filters, part=part)
        bad_sel = selector(m, rule.services, rule.filters, rule.bad, part=part)
        expr = (f"(sum by ({L}) (rate({bad_sel}[{W}])) / sum by ({L}) (rate({all_sel}[{W}]))) "
                f"{op} {T} and {guard(all_sel)}")
    elif rule.kind == "count":
        bad_sel = selector(m, rule.services, rule.filters, rule.bad, part=_count_part(m))
        expr = f"sum by ({L}) (increase({bad_sel}[{W}])) {op} {T}"
    elif rule.kind == "rate":
        sel = selector(m, rule.services, rule.filters, part=_count_part(m))
        expr = f"sum by ({L}) (rate({sel}[{W}])) {op} {T}"
    elif rule.kind == "latency_quantile":
        bucket = selector(m, rule.services, rule.filters, part="bucket")
        q = (f"histogram_quantile({fmt_num(rule.quantile)}, "
             f"sum by ({L}, le) (rate({bucket}[{W}]))) {op} {T}")
        if rule.min_requests is not None:
            q += f" and {guard(selector(m, rule.services, rule.filters, part='count'))}"
        probe = f"group by ({L}) (last_over_time({bucket}[{PROBE_LOOKBACK}]))"
        expr = q
    elif rule.kind == "value":
        sel = selector(m, rule.services, rule.filters)
        inner = "last" if rule.agg == "sum" else rule.agg
        expr = f"{rule.agg} by ({L}) ({inner}_over_time({sel}[{W}])) {op} {T}"
    elif rule.kind == "gauge_ratio":
        num = selector(m, rule.services, rule.filters)
        den = selector(rule.denominator, rule.services, rule.filters)
        expr = (f"sum by ({L}) (avg_over_time({num}[{W}])) / "
                f"sum by ({L}) (avg_over_time({den}[{W}])) {op} {T}")
    elif rule.kind == "silent_while_serving":
        # Cloud Run's label is service_name, GoFr's is job; label_replace copies one onto the
        # other so `unless on (job)` can join them. VERIFIED on realm-id history: returns the
        # broken services at 2026-09-22T13:00Z and nothing after the fix.
        ex = rule.exporter
        serving = selector(m, rule.services)
        exporting = selector(ex, rule.services, part=_count_part(ex))
        expr = (f'label_replace(sum by ({L}) (rate({serving}[{W}])), '
                f'"{ex.service_label}", "$1", "{L}", "(.*)") > 0 '
                f"unless on ({ex.service_label}) "
                f"sum by ({ex.service_label}) (rate({exporting}[{W}])) > 0")
        probe = f"group by ({L}) (last_over_time({serving}[{PROBE_LOOKBACK}]))"
    else:
        raise ValueError(f"no PromQL rendering for kind {rule.kind!r}")
    return expr, probe
