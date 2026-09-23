"""Resolve a spec into concrete rules: catalog default -> overrides.<id> -> .services.<svc>.

Services whose resolved parameters are identical become ONE rule (one policy, one incident
per service via `sum by (<service label>)`), so conditions scale with rules, not
rules x services. A service with its own parameters gets its own rule, keyed
`<id>.<service>`; the group that kept the rule-level parameters keeps the plain id, so adding
a per-service override never renames the existing policy.
"""
import json
import re
from dataclasses import dataclass, field

from . import promql
from .metrics import REGISTRY, Metric
from .spec import SpecError, check_top, load_catalog
from .units import convert, parse_duration

SEVERITIES = {"page": "CRITICAL", "ticket": "WARNING"}
OPS = {">", ">=", "<", "<="}
OVERRIDE_KEYS = {"enabled", "threshold", "window", "for", "severity", "min_requests",
                 "filters", "filter", "rate_limit", "services"}
CUSTOM_KINDS = {"error_ratio", "rate", "latency_quantile", "value"}
CUSTOM_KEYS = {"id", "metric", "kind", "filters", "window", "op", "threshold", "for",
               "severity", "summary", "triage", "services", "may_be_absent"}
# Keys only some kinds use. Accepting them elsewhere would silently drop them: a `rate` rule
# with `bad: {code: "502"}` would alert on ALL traffic, not 502s.
CUSTOM_KIND_KEYS = {"error_ratio": {"bad", "min_requests"},
                    "latency_quantile": {"quantile", "min_requests"},
                    "value": {"agg"}, "rate": set()}
AGGS = {"max", "min", "avg", "sum"}
GUARDED = {"error_ratio", "latency_quantile"}
LOG_KINDS = {"log_match"}
DEFAULT_MIN_REQUESTS = 20
MIN_RATE_LIMIT = 300          # Cloud Monitoring's floor for notificationRateLimit.period
TRIAGE_MIN = 80               # validate-alerts' actionability floor (DOC_MIN_CHARS)
LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
METRIC_NAME_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
CUSTOM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,50}$")
FILTER_OPS = {"in", "not_in", "regex", "not_regex", "not"}


@dataclass
class Rule:
    id: str
    key: str
    kind: str
    services: list
    severity: str
    summary: str
    triage: str
    signal: str = ""
    pack: str = None
    window: int = 0
    for_: int = 0
    op: str = ">"
    threshold: float = None
    threshold_text: str = ""
    min_requests: int = None
    quantile: float = None
    agg: str = None
    metric: Metric = None
    denominator: Metric = None
    exporter: Metric = None
    filters: dict = field(default_factory=dict)
    bad: dict = field(default_factory=dict)
    log_filter: str = None
    rate_limit: int = None
    may_be_absent: bool = False
    platforms: frozenset = frozenset()
    expr: str = None
    probe: str = None

    @property
    def is_log(self):
        return self.kind in LOG_KINDS


def value_unit(kind, metric):
    """The unit of the number the rule's expression compares against its threshold."""
    if kind in ("error_ratio", "gauge_ratio"):
        return "ratio"
    if kind == "rate":
        return "per_s"
    if kind == "count":
        return "count"
    return metric.unit


def _check_filters(filters, where, problems):
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        problems.append(f"{where}: filters must be a mapping of label -> value")
        return {}
    for label, v in filters.items():
        if not LABEL_NAME_RE.match(str(label)):
            problems.append(f"{where}: {label!r} is not a valid label name")
        if v is None or isinstance(v, str):
            continue
        if isinstance(v, dict) and len(v) == 1 and set(v) <= FILTER_OPS:
            op, arg = next(iter(v.items()))
            if op in ("in", "not_in"):
                if not isinstance(arg, list) or not arg or not all(isinstance(a, str) for a in arg):
                    problems.append(f"{where}: {label}.{op} must be a non-empty list of strings")
            elif not isinstance(arg, str):
                problems.append(f"{where}: {label}.{op} must be a string")
            continue
        problems.append(f"{where}: filter for {label!r} must be a string or one of "
                        f"{{{', '.join(sorted(FILTER_OPS))}: ...}}")
    return filters


def _merge_filters(base, extra):
    out = dict(base or {})
    for k, v in (extra or {}).items():
        if v is None:
            out.pop(k, None)       # `{path: null}` removes a catalog default filter
        else:
            out[k] = v
    return out


def _resolve_params(rid, raw, where, problems, warnings):
    """Validate one parameter set and return its canonical resolved form (or None)."""
    kind = raw["kind"]
    n0 = len(problems)
    out = {}
    sev = raw.get("severity")
    if sev not in SEVERITIES:
        problems.append(f"{where}: severity must be one of {sorted(SEVERITIES)}, got {sev!r}")
    out["severity"] = sev
    if kind in LOG_KINDS:
        flt = raw.get("filter")
        if not isinstance(flt, str) or not flt.strip():
            problems.append(f"{where}: needs a non-empty `filter` (a Cloud Logging query)")
        out["log_filter"] = flt
        try:
            rl = parse_duration(raw.get("rate_limit", "300s"), f"{where}: rate_limit")
            if rl < MIN_RATE_LIMIT:
                problems.append(f"{where}: rate_limit must be at least {MIN_RATE_LIMIT}s")
            out["rate_limit"] = rl
        except SpecError as e:
            problems.extend(e.problems)
        return out if len(problems) == n0 else None

    try:
        out["window"] = parse_duration(raw.get("window"), f"{where}: window")
        if out["window"] <= 0:
            problems.append(f"{where}: window must be positive")
        elif out["window"] < 600:
            warnings.append(f"{rid}: window {raw.get('window')} is under 10m; scale-to-zero "
                            "services flap on short windows")
    except SpecError as e:
        problems.extend(e.problems)
    try:
        out["for"] = parse_duration(raw.get("for", "0s"), f"{where}: for")
        if 0 < out["for"] < 120:
            warnings.append(f"{rid}: for {raw.get('for')} is under 2x the 60s evaluation "
                            "interval; Cloud Monitoring advises at least 120s")
    except SpecError as e:
        problems.extend(e.problems)
    if kind != "silent_while_serving":
        op = raw.get("op", ">")
        if op not in OPS:
            problems.append(f"{where}: op must be one of {sorted(OPS)}, got {op!r}")
        out["op"] = op
        try:
            out["threshold"] = convert(raw.get("threshold"), value_unit(kind, raw["_metric"]),
                                       f"{where}: threshold")
            out["threshold_text"] = str(raw.get("threshold"))
        except SpecError as e:
            problems.extend(e.problems)
    if kind in GUARDED:
        # The guard counts REQUESTS. A histogram of something else (Cloud Run memory
        # utilisation is sampled once a minute) must not default to "at least 20 in the
        # window": one instance at 95% memory would never satisfy it.
        counts_requests = kind == "error_ratio" or raw["_metric"].unit in ("s", "ms", "us")
        mr = raw.get("min_requests", DEFAULT_MIN_REQUESTS if counts_requests else None)
        if mr is not None and (isinstance(mr, bool) or not isinstance(mr, int) or mr < 0):
            problems.append(f"{where}: min_requests must be a non-negative integer")
        out["min_requests"] = mr
    out["filters"] = _check_filters(raw.get("filters"), where, problems)
    if kind in ("error_ratio", "count"):
        bad = raw.get("bad")
        if not isinstance(bad, dict) or not bad:
            problems.append(f"{where}: {kind} needs `bad:` filters selecting the failing series")
        out["bad"] = _check_filters(bad, where, problems)
    return out if len(problems) == n0 else None


def _applies(kind):
    """Override keys that mean something for a rule of this kind."""
    if kind in LOG_KINDS:
        return {"severity", "filter", "rate_limit"}
    keys = {"severity", "window", "for"}
    if kind != "silent_while_serving":
        keys |= {"threshold", "filters"}
    if kind in GUARDED:
        keys.add("min_requests")
    return keys


def _canon(params):
    return json.dumps(params, sort_keys=True, default=str)


def _catalog_rules(spec, packs, catalog, problems, warnings):
    services = spec["services"]
    enabled_packs = spec.get("packs") or []
    overrides = spec.get("overrides") or {}
    for p in enabled_packs:
        if p not in packs:
            problems.append(f"packs: unknown pack {p!r} (known: {', '.join(sorted(packs))})")
    for rid, ov in overrides.items():
        if rid not in catalog:
            problems.append(f"overrides: unknown rule id {rid!r}")
            continue
        if catalog[rid]["pack"] not in enabled_packs:
            problems.append(f"overrides.{rid}: its pack {catalog[rid]['pack']!r} is not in packs")
        if not isinstance(ov, dict):
            problems.append(f"overrides.{rid}: must be a mapping")
            continue
        for k in sorted(set(ov) - OVERRIDE_KEYS):
            problems.append(f"overrides.{rid}: unknown key {k!r} "
                            f"(allowed: {', '.join(sorted(OVERRIDE_KEYS))})")
        svc_ov = ov.get("services") or {}
        if not isinstance(svc_ov, dict):
            problems.append(f"overrides.{rid}.services: must be a mapping of service -> overrides")
            svc_ov = {}
        for s, sov in svc_ov.items():
            if s not in services:
                problems.append(f"overrides.{rid}.services: {s!r} is not in services")
            elif not isinstance(sov, dict):
                problems.append(f"overrides.{rid}.services.{s}: must be a mapping")
            else:
                for k in sorted(set(sov) - (OVERRIDE_KEYS - {"services"})):
                    problems.append(f"overrides.{rid}.services.{s}: unknown key {k!r}")
    if problems:
        return []

    rules = []
    for pack in enabled_packs:
        for rid in packs[pack]["rules"]:
            d = catalog[rid]
            ov = overrides.get(rid) or {}
            level = {k: v for k, v in ov.items() if k not in ("services", "enabled")}
            svc_ov = ov.get("services") or {}
            flags = [ov.get("enabled")] + [(v or {}).get("enabled") for v in svc_ov.values()]
            if any(f is not None and not isinstance(f, bool) for f in flags):
                problems.append(f"overrides.{rid}: enabled must be true or false")
                continue
            if ov.get("enabled") is False:
                if any((v or {}).get("enabled") is True for v in svc_ov.values()):
                    problems.append(f"overrides.{rid}: enabled: false at rule level contradicts "
                                    "enabled: true for a service — say which one you mean")
                continue
            # Which services the rule covers. A default-on rule, or one configured at rule
            # level (an override that silently did nothing would read as coverage the app
            # does not have), covers every service not switched off. A default-off rule
            # configured only per service covers just the services configured.
            if ov.get("enabled") is True or d.get("enabled", True) or level:
                active = [s for s in services if (svc_ov.get(s) or {}).get("enabled") is not False]
            else:
                active = [s for s in services
                          if s in svc_ov and (svc_ov[s] or {}).get("enabled") is not False]
            if not active:
                continue
            base = {k: v for k, v in d.items()
                    if k not in ("id", "pack", "platforms", "enabled", "requires", "signal",
                                 "summary", "triage", "metric", "denominator", "exporter",
                                 "quantile")}
            base["_metric"] = REGISTRY.get(d.get("metric")) if d.get("metric") else None
            rule_level = dict(base, **level)
            rule_level["filters"] = _merge_filters(base.get("filters"), level.get("filters"))
            for req in d.get("requires", []):
                if not rule_level.get(req) and not all((svc_ov.get(s) or {}).get(req)
                                                       for s in active):
                    problems.append(f"{rid}: enabled but required parameter `{req}` is not set "
                                    f"(add it under overrides.{rid})")
            if problems:
                continue
            # A key that does not apply to the rule's kind would be silently ignored, which
            # reads as a change the policy never got.
            svc_keys = set()
            for sov in (ov.get("services") or {}).values():
                svc_keys |= set(sov or {})
            for k in sorted((set(level) | svc_keys) - {"enabled"}):
                if k not in _applies(d["kind"]):
                    problems.append(f"overrides.{rid}: `{k}` does not apply to a {d['kind']} rule "
                                    f"(it takes: {', '.join(sorted(_applies(d['kind'])))})")
            if problems:
                continue
            if all(rule_level.get(req) for req in d.get("requires", [])):
                ref = _resolve_params(rid, rule_level, f"overrides.{rid}" if level else rid,
                                      problems, warnings)
                if ref is None:
                    continue
            else:
                ref = None      # the required parameter is set per service only
            groups = {}
            for s in active:
                sov = {k: v for k, v in (svc_ov.get(s) or {}).items() if k != "enabled"}
                if sov or ref is None:
                    raw = dict(rule_level, **{k: v for k, v in sov.items() if k != "enabled"})
                    raw["filters"] = _merge_filters(rule_level["filters"], sov.get("filters"))
                    params = _resolve_params(rid, raw, f"overrides.{rid}.services.{s}",
                                             problems, warnings)
                    if params is None:
                        continue
                else:
                    params = ref
                groups.setdefault(_canon(params), (params, []))[1].append(s)
            for canon, (params, svcs) in groups.items():
                # `_` joins: service names cannot contain it, so `a-b` and `a`+`b` differ.
                key = (rid if ref is not None and canon == _canon(ref)
                       else f"{rid}.{'_'.join(sorted(svcs))}")
                rules.append(_make(rid, key, d, params, sorted(svcs), catalog=True))
    return rules


def _make(rid, key, d, params, services, catalog):
    return Rule(
        id=rid, key=key, kind=d["kind"], services=services,
        severity=params["severity"], summary=d["summary"].strip(), triage=d["triage"].strip(),
        signal=d.get("signal", ""), pack=d.get("pack"),
        window=params.get("window", 0), for_=params.get("for", 0), op=params.get("op", ">"),
        threshold=params.get("threshold"), threshold_text=params.get("threshold_text", ""),
        min_requests=params.get("min_requests"), quantile=d.get("quantile"),
        agg=d.get("agg"),
        metric=d.get("_metric_obj") or (REGISTRY.get(d.get("metric")) if catalog else None),
        denominator=REGISTRY.get(d.get("denominator")) if d.get("denominator") else None,
        exporter=REGISTRY.get(d.get("exporter")) if d.get("exporter") else None,
        filters=params.get("filters") or {}, bad=params.get("bad") or {},
        log_filter=params.get("log_filter"), rate_limit=params.get("rate_limit"),
        may_be_absent=bool(d.get("may_be_absent", False)),
        platforms=d.get("platforms") or frozenset({"gmp", "prometheus"}),
    )


def _custom_rules(spec, catalog, problems, warnings):
    rules, seen = [], set()
    services = spec["services"]
    for i, c in enumerate(spec.get("custom") or []):
        where = f"custom[{i}]"
        if not isinstance(c, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        rid = c.get("id")
        where = f"custom[{i}] ({rid})"
        n0 = len(problems)
        if "promql" in c:
            problems.append(f"{where}: raw `promql:` is not supported in alertspec/v1 — it cannot "
                            "be ported to a backend without PromQL (e.g. Dynatrace); describe the "
                            "rule with a kind instead")
        kind = c.get("kind")
        allowed = CUSTOM_KEYS | CUSTOM_KIND_KEYS.get(kind, set())
        for k in sorted(set(c) - allowed - {"promql"}):
            used_by = sorted(kn for kn, ks in CUSTOM_KIND_KEYS.items() if k in ks)
            if used_by:
                problems.append(f"{where}: `{k}` does not apply to a {kind} rule "
                                f"(only to {', '.join(used_by)}) — it would be silently ignored")
            else:
                problems.append(f"{where}: unknown key {k!r}")
        if isinstance(rid, str) and rid.lower().replace(".", "-") in {
                c_id.replace(".", "-") for c_id in catalog}:
            problems.append(f"{where}: id {rid!r} collides with a catalog rule's rule_id label")
        if not isinstance(rid, str) or not CUSTOM_ID_RE.match(rid):
            problems.append(f"{where}: id must match {CUSTOM_ID_RE.pattern}")
        elif rid in catalog:
            problems.append(f"{where}: id {rid!r} collides with a catalog rule id")
        elif rid in seen:
            problems.append(f"{where}: duplicate custom id {rid!r}")
        seen.add(rid)
        if kind not in CUSTOM_KINDS:
            problems.append(f"{where}: kind {kind!r} is not one of {sorted(CUSTOM_KINDS)}")
        m = c.get("metric")
        metric = None
        if not isinstance(m, dict) or not isinstance(m.get("name"), str):
            problems.append(f"{where}: metric must be {{name, type, unit?}}")
        else:
            for k in sorted(set(m) - {"name", "type", "unit", "service_label"}):
                problems.append(f"{where}: metric has unknown key {k!r}")
            if not METRIC_NAME_RE.match(m["name"]):
                problems.append(f"{where}: {m['name']!r} is not a valid Prometheus metric name")
            mtype = m.get("type")
            if mtype not in ("counter", "histogram", "gauge"):
                problems.append(f"{where}: metric.type must be counter, histogram or gauge")
            unit = m.get("unit")
            if kind == "latency_quantile":
                if mtype != "histogram":
                    problems.append(f"{where}: latency_quantile needs a histogram metric, "
                                    f"got {mtype!r}")
                if unit not in ("s", "ms", "us", "ratio", "1"):
                    problems.append(f"{where}: a latency histogram needs metric.unit "
                                    "(s, ms, us — or ratio / 1 for non-time histograms)")
            elif kind in ("rate", "error_ratio") and mtype not in ("counter", "histogram"):
                problems.append(f"{where}: {kind} needs a counter or histogram metric")
            elif kind == "value" and mtype != "gauge":
                problems.append(f"{where}: value needs a gauge metric")
            sl = m.get("service_label", "job")
            if not LABEL_NAME_RE.match(str(sl)):
                problems.append(f"{where}: metric.service_label is not a valid label name")
            metric = Metric(m["name"], mtype or "counter", unit or "1", sl)
        if kind == "error_ratio" and not c.get("bad"):
            problems.append(f"{where}: error_ratio needs `bad:` filters selecting failing series")
        for fld in ("summary", "triage"):
            if not isinstance(c.get(fld), str) or not c[fld].strip():
                problems.append(f"{where}: {fld} is required")
        if isinstance(c.get("triage"), str) and len(c["triage"].strip()) < TRIAGE_MIN:
            problems.append(f"{where}: triage is {len(c['triage'].strip())} chars; at least "
                            f"{TRIAGE_MIN} — say what broke and what to check first")
        svcs = c.get("services", services)
        if not isinstance(svcs, list) or not svcs:
            problems.append(f"{where}: services must be a non-empty list")
            svcs = []
        for s in svcs:
            if s not in services:
                problems.append(f"{where}: service {s!r} is not in the top-level services")
        if c.get("quantile") is not None and not (isinstance(c["quantile"], (int, float))
                                                  and 0 < c["quantile"] < 1):
            problems.append(f"{where}: quantile must be between 0 and 1")
        if c.get("agg") is not None and c["agg"] not in AGGS:
            problems.append(f"{where}: agg must be one of {sorted(AGGS)}")
        if c.get("may_be_absent") is not None and not isinstance(c["may_be_absent"], bool):
            problems.append(f"{where}: may_be_absent must be true or false")
        if len(problems) != n0:
            continue
        raw = dict(c, _metric=metric)
        raw.setdefault("for", "10m")
        params = _resolve_params(rid, raw, where, problems, warnings)
        if params is None:
            continue
        d = dict(c, summary=c["summary"], triage=c["triage"], signal=c["summary"],
                 _metric_obj=metric, quantile=c.get("quantile", 0.95 if kind == "latency_quantile" else None),
                 agg=c.get("agg", "max" if kind == "value" else None),
                 platforms=frozenset({"gmp", "prometheus"}))
        rules.append(_make(rid, rid, d, params, sorted(svcs), catalog=False))
    return rules


def resolve(spec, *, warnings=None):
    """spec dict -> list[Rule] with expressions built. Raises SpecError listing every problem."""
    warnings = [] if warnings is None else warnings
    problems = check_top(spec)
    if problems:
        raise SpecError(problems)
    packs, catalog = load_catalog()
    rules = _catalog_rules(spec, packs, catalog, problems, warnings)
    rules += _custom_rules(spec, catalog, problems, warnings)
    if problems:
        raise SpecError(problems)
    for r in rules:
        if not r.is_log:
            r.expr, r.probe = promql.build(r)
    rules.sort(key=lambda r: r.key)
    return rules
