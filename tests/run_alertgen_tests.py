#!/usr/bin/env python3
"""Self-test for alerting/alertgen — the AlertSpec compiler behind service-alerts.

Four layers, each catching what the one before cannot:

  1. Spec checks — the errors a spec author can make (unknown ids, a bare number on a
     latency, a ratio written as 5 instead of 5%) must be refused, loudly. A spec that is
     wrong in a way that silences an alert is the failure mode this format exists to prevent.
  2. Render checks — every GMP policy carries the labels the managed applier keys on, the
     severity mapping, a stable spec_hash, and both sides of every `and` group by the same
     label set (otherwise the guard matches nothing and the alert never fires).
  3. Golden files — the exact rendered output for a fixture spec, so a catalog change shows
     up as a reviewed diff. Regenerate with `--update-golden` and read the diff.
  4. promtool — the rendered PromQL is EXECUTED against synthetic series (0/0, 3 requests,
     100 requests with 10% 5xx, silent-while-serving with one side missing). This is the
     semantic oracle: the first three layers check shape, only this one checks behaviour.

Plus conformance (every rendered policy passes validate-alerts' shipped lint body) and the
service-alerts step bodies, executed against stubs.

Usage:  python3 tests/run_alertgen_tests.py [--update-golden]
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "alerting"))
FIX = ROOT / "tests" / "alertgen"
GOLDEN = FIX / "golden"
VALIDATE = ROOT / ".github" / "workflows" / "validate-alerts.yml"
SERVICE = ROOT / ".github" / "workflows" / "service-alerts.yml"

FAILURES = []
UPDATE = "--update-golden" in sys.argv


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


def extract_step(workflow: Path, job: str, step_name: str) -> str:
    doc = yaml.safe_load(workflow.read_text())
    for step in doc["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return step["run"]
    raise SystemExit(f"step '{step_name}' not found in {workflow.name}:{job}")


def base_spec(**kw):
    spec = {"apiVersion": "alertspec/v1", "services": ["api"], "packs": []}
    spec.update(kw)
    return spec


def errors_of(fn):
    """Run fn; return the SpecError message ('' when it did not raise)."""
    from alertgen.spec import SpecError
    try:
        fn()
    except SpecError as e:
        return str(e)
    return ""


def by_id(rules):
    out = {}
    for r in rules:
        out.setdefault(r.id, []).append(r)
    return out


# --- 1. spec ---------------------------------------------------------------------
def test_spec():
    from alertgen import units
    from alertgen.compile import resolve
    print("spec · validation, units, precedence")

    e = errors_of(lambda: resolve(base_spec(pakcs=["cloudrun"])))
    check("unknown top-level key is an error", "pakcs" in e, e)
    e = errors_of(lambda: resolve(base_spec(apiVersion="alertspec/v9")))
    check("wrong apiVersion is an error", "apiVersion" in e, e)
    e = errors_of(lambda: resolve(base_spec(services=[])))
    check("empty services is an error", "services" in e, e)
    e = errors_of(lambda: resolve(base_spec(packs=["nope"])))
    check("unknown pack is an error", "nope" in e, e)
    e = errors_of(lambda: resolve(base_spec(packs=["cloudrun"],
                                            overrides={"cloudrun.latency_p99": {"threshold": "1s"}})))
    check("unknown override id is an error", "cloudrun.latency_p99" in e, e)
    e = errors_of(lambda: resolve(base_spec(packs=["gofr-http"],
                                            overrides={"cloudrun.latency_p95": {"threshold": "1s"}})))
    check("override for a rule whose pack is off is an error", "cloudrun" in e, e)
    e = errors_of(lambda: resolve(base_spec(packs=["cloudrun"],
                                            overrides={"cloudrun.latency_p95": {"treshold": "1s"}})))
    check("unknown override key is an error", "treshold" in e, e)
    e = errors_of(lambda: resolve(base_spec(packs=["cloudrun"],
                                            overrides={"cloudrun.latency_p95": {"threshold": 5}})))
    check("bare number on a duration metric is an error", "unit" in e.lower(), e)
    e = errors_of(lambda: resolve(base_spec(packs=["cloudrun"],
                                            overrides={"cloudrun.5xx_ratio": {"threshold": 5}})))
    check("bare ratio above 1 is an error (write 5%)", "5%" in e, e)
    e = errors_of(lambda: resolve(base_spec(packs=["cloudrun"],
                                            overrides={"cloudrun.5xx_ratio": {"window": 10}})))
    check("bare-number window is an error", "window" in e, e)
    e = errors_of(lambda: resolve(base_spec(packs=["cloudrun"],
                                            overrides={"cloudrun.5xx_ratio": {"severity": "urgent"}})))
    check("unknown severity is an error", "severity" in e, e)

    # unit conversions — each metric stores a different unit
    check("5s -> 5000 for Cloud Run (ms)", units.convert("5s", "ms") == 5000)
    check("2s -> 2 for GoFr HTTP (s)", units.convert("2s", "s") == 2)
    check("500ms -> 500 for GoFr SQL (ms)", units.convert("500ms", "ms") == 500)
    check("50ms -> 50000 for GoFr Redis (us)", units.convert("50ms", "us") == 50000)
    check("250ms -> 0.25 s", units.convert("250ms", "s") == 0.25)
    check("5% -> 0.05", units.convert("5%", "ratio") == 0.05)
    check("0.05 ratio accepted", units.convert(0.05, "ratio") == 0.05)
    check("0.1/s -> 0.1", units.convert("0.1/s", "per_s") == 0.1)
    check("6/m -> 0.1", units.convert("6/m", "per_s") == 0.1)
    check("360/h -> 0.1", units.convert("360/h", "per_s") == 0.1)
    check("10m -> 600s", units.parse_duration("10m") == 600)
    check("1h30m -> 5400s", units.parse_duration("1h30m") == 5400)
    e = errors_of(lambda: units.convert(0.1, "per_s"))
    check("bare number on a rate is an error", "/s" in e, e)
    e = errors_of(lambda: units.convert("5%", "ms"))
    check("percent on a duration metric is an error", e != "", e)
    e = errors_of(lambda: units.convert("2s", "ratio"))
    check("duration on a ratio is an error", e != "", e)

    # compiled thresholds carry the converted value
    rules = by_id(resolve(base_spec(packs=["cloudrun", "gofr-http", "gofr-sql", "gofr-redis"],
                                    overrides={"cloudrun.latency_p95": {"threshold": "5s"}})))
    check("cloudrun.latency_p95 5s compiles to 5000",
          rules["cloudrun.latency_p95"][0].threshold == 5000, rules["cloudrun.latency_p95"][0].threshold)
    check("gofr http p95 default 2s compiles to 2",
          rules["gofr.http.server.latency_p95"][0].threshold == 2)
    check("gofr sql p95 default 500ms compiles to 500",
          rules["gofr.sql.latency_p95"][0].threshold == 500)
    check("gofr redis p95 default 50ms compiles to 50000",
          rules["gofr.redis.latency_p95"][0].threshold == 50000)

    # precedence + grouping
    spec = base_spec(services=["issuer", "api"], packs=["gofr-http"],
                     overrides={"gofr.http.server.latency_p95": {
                         "threshold": "3s", "services": {"issuer": {"threshold": "4s"}}}})
    rules = by_id(resolve(spec))
    lat = sorted(rules["gofr.http.server.latency_p95"], key=lambda r: r.services)
    check("per-service override splits the rule into two policies", len(lat) == 2, lat)
    check("service-level override beats rule-level",
          [(r.services, r.threshold) for r in lat] == [(["api"], 3), (["issuer"], 4)],
          [(r.services, r.threshold) for r in lat])
    check("the un-overridden group keeps the plain key",
          sorted(r.key for r in lat) == ["gofr.http.server.latency_p95",
                                        "gofr.http.server.latency_p95.issuer"],
          [r.key for r in lat])
    err = rules["gofr.http.server.error_ratio"]
    check("identical services render as ONE policy", len(err) == 1 and err[0].services == ["api", "issuer"],
          [(r.services) for r in err])
    e = errors_of(lambda: resolve(base_spec(packs=["gofr-http"], overrides={
        "gofr.http.server.latency_p95": {"services": {"ghost": {"threshold": "1s"}}}})))
    check("per-service override for an unknown service is an error", "ghost" in e, e)

    # enabled / default-off
    rules = by_id(resolve(base_spec(packs=["gofr-sql"],
                                    overrides={"gofr.sql.pool_saturation": {"enabled": False}})))
    check("enabled: false removes the rule", "gofr.sql.pool_saturation" not in rules, list(rules))
    rules = by_id(resolve(base_spec(packs=["cloudrun"])))
    check("default-off cloudrun.5xx_count is off by default", "cloudrun.5xx_count" not in rules)
    rules = by_id(resolve(base_spec(packs=["cloudrun"],
                                    overrides={"cloudrun.5xx_count": {"threshold": 5, "window": "15m"}})))
    check("configuring a default-off rule turns it on", "cloudrun.5xx_count" in rules, list(rules))
    rules = by_id(resolve(base_spec(packs=["gcp-logs"])))
    check("logs.error_match is off without a filter", "logs.error_match" not in rules)
    e = errors_of(lambda: resolve(base_spec(packs=["gcp-logs"],
                                            overrides={"logs.error_match": {"enabled": True}})))
    check("enabling logs.error_match without filter is an error", "filter" in e, e)
    rules = by_id(resolve(base_spec(packs=["gcp-logs"],
                                    overrides={"logs.error_match": {"filter": 'jsonPayload.message:"neon"'}})))
    check("logs.error_match with a filter is on", "logs.error_match" in rules)

    # custom rules
    good = {"id": "bff-upstream-errors", "metric": {"name": "bff_upstream_error", "type": "counter"},
            "kind": "rate", "filters": {"code": {"in": ["502", "503"]}}, "window": "10m", "op": ">",
            "threshold": "0.1/s", "for": "10m", "severity": "page",
            "summary": "BFF upstream 5xx rate is high",
            "triage": "x" * 80, "may_be_absent": True}
    rules = by_id(resolve(base_spec(custom=[good])))
    check("valid custom rate rule compiles", "bff-upstream-errors" in rules, list(rules))

    def bad(**kw):
        c = dict(good)
        c.update(kw)
        return errors_of(lambda: resolve(base_spec(custom=[c])))

    e = bad(triage="too short")
    check("custom triage under 80 chars is an error", "triage" in e, e)
    e = bad(promql="up == 0")
    check("raw promql: is refused", "promql" in e, e)
    e = bad(kind="latency_quantile")
    check("latency_quantile on a counter is an error", "histogram" in e, e)
    e = bad(kind="error_ratio")
    check("error_ratio without bad: is an error", "bad" in e, e)
    e = bad(kind="absence")
    check("unknown custom kind is an error", "absence" in e, e)
    e = bad(id="cloudrun.5xx_ratio")
    check("custom id colliding with a catalog id is an error", "cloudrun.5xx_ratio" in e, e)
    e = bad(metric={"name": "bad-name", "type": "counter"})
    check("invalid metric name is an error", "bad-name" in e, e)
    e = bad(threshold=0.1)
    check("custom rate with a bare number is an error", "/s" in e, e)
    e = bad(kind="latency_quantile", metric={"name": "h", "type": "histogram"}, threshold="1s")
    check("latency histogram without a unit is an error", "unit" in e, e)
    e = bad(services=["ghost"])
    check("custom rule naming an unknown service is an error", "ghost" in e, e)
    e = errors_of(lambda: resolve(base_spec(custom=[good, dict(good)])))
    check("duplicate custom ids are an error", "duplicate" in e.lower(), e)

    # --- critic findings 2026-09-23: each was a silent loss or a silently weaker alert ---
    for bad_name in ("API", 'a"b', "a_b", "-a"):
        e = errors_of(lambda: resolve(base_spec(services=[bad_name])))
        check(f"service name {bad_name!r} is refused", "service" in e, e)
    e = errors_of(lambda: resolve(base_spec(packs=["gofr-http"],
                                            custom=[dict(good, id="gofr-http-server-error_ratio")])))
    check("custom id that slugs onto a catalog rule_id is an error", "collides" in e, e)
    spec = base_spec(services=["a-b", "a", "b", "c"], packs=["gofr-http"],
                     overrides={"gofr.http.server.latency_p95": {"services": {
                         "a-b": {"threshold": "3s"}, "a": {"threshold": "4s"},
                         "b": {"threshold": "4s"}}}})
    out = render_gmp(spec)
    ids = [p["userLabels"]["rule_id"] for _, p in out.policies]
    check("group keys cannot collide ('a-b' vs 'a'+'b')", len(ids) == len(set(ids)), ids)
    rules = by_id(resolve(base_spec(packs=["cloudrun"])))
    check("cloudrun.memory_p99 has no request guard (it counts memory samples, not requests)",
          rules["cloudrun.memory_p99"][0].min_requests is None
          and " and " not in rules["cloudrun.memory_p99"][0].expr,
          rules["cloudrun.memory_p99"][0].expr)
    for key, val in (("bad", {"code": "502"}), ("quantile", 0.5), ("agg", "max"),
                     ("min_requests", 5)):
        e = bad(**{key: val})
        check(f"custom rate rule with `{key}` (unused by the kind) is an error", key in e, e)
    two = base_spec(services=["api", "issuer"], packs=["cloudrun"])
    rules = by_id(resolve(dict(two, overrides={"cloudrun.5xx_count": {
        "services": {"api": {"enabled": True}}}})))
    check("per-service enabled:true on a default-off rule enables ONLY that service",
          [r.services for r in rules.get("cloudrun.5xx_count", [])] == [["api"]],
          [r.services for r in rules.get("cloudrun.5xx_count", [])])
    rules = by_id(resolve(dict(two, overrides={"cloudrun.5xx_count": {
        "services": {"issuer": {"enabled": False}}}})))
    check("per-service enabled:false on a default-off rule enables nothing",
          "cloudrun.5xx_count" not in rules, list(rules))
    rules = by_id(resolve(dict(two, overrides={"cloudrun.5xx_ratio": {
        "services": {"issuer": {"enabled": False}}}})))
    check("per-service enabled:false removes only that service",
          [r.services for r in rules["cloudrun.5xx_ratio"]] == [["api"]])
    e = errors_of(lambda: resolve(dict(two, overrides={"cloudrun.5xx_ratio": {
        "enabled": False, "services": {"api": {"enabled": True}}}})))
    check("rule-level enabled:false + service-level enabled:true is an error", "enabled" in e, e)
    r = by_id(resolve(base_spec(packs=["gofr-http"])))["gofr.http.server.error_ratio"][0]
    check("error_ratio probe proves the `bad` label exists (a typo'd label never fires)",
          'status!=""' in r.probe, r.probe)


# --- 2. render -------------------------------------------------------------------
LABEL_RE = re.compile(r"^[a-z0-9_-]{1,63}$")


def _and_sides_by_sets(expr):
    """For every top-level ` and ` in expr, the `by (...)` sets on each side."""
    out = []
    parts = expr.split(" and ")
    for left, right in zip(parts, parts[1:]):
        lb = re.findall(r"by \(([^)]*)\)", left)
        rb = re.findall(r"by \(([^)]*)\)", right)
        # histogram_quantile keeps `le` inside; it is dropped by the quantile
        lset = {tuple(sorted(s.replace(" ", "").replace(",le", "").split(","))) for s in lb}
        rset = {tuple(sorted(s.replace(" ", "").split(","))) for s in rb}
        out.append((lset, rset))
    return out


FULL_SPEC = FIX / "spec-full.yaml"


def render_gmp(spec, owner="acme_app"):
    from alertgen.compile import resolve
    from alertgen.render_gmp import render
    return render(resolve(spec), owner=owner)


def test_render():
    from alertgen.compile import resolve
    from alertgen.spec import SpecError
    print("render · GMP policies and PrometheusRule")
    spec = yaml.safe_load(FULL_SPEC.read_text())
    out = render_gmp(spec)
    pols = out.policies
    check("full spec renders policies", len(pols) >= 10, len(pols))

    ids = [p["userLabels"]["rule_id"] for _, p in pols]
    check("rule_id labels are unique", len(ids) == len(set(ids)), ids)
    names = [p["displayName"] for _, p in pols]
    check("displayNames are unique", len(names) == len(set(names)), names)
    for fname, p in pols:
        ul = p["userLabels"]
        check(f"{fname}: labels are Cloud Monitoring-legal",
              all(LABEL_RE.match(k) and LABEL_RE.match(v) for k, v in ul.items()), ul)
        check(f"{fname}: managed labels present",
              ul.get("managed_by") == "alertgen" and ul.get("alertgen_owner") == "acme_app"
              and re.fullmatch(r"[0-9a-f]{16}", ul.get("spec_hash", "")), ul)
        check(f"{fname}: severity mapped", p["severity"] in ("CRITICAL", "WARNING"), p.get("severity"))
        check(f"{fname}: placeholder channel",
              p["notificationChannels"] == ["NOTIFICATION_CHANNEL_PLACEHOLDER"])
        check(f"{fname}: documentation >= 80 chars", len(p["documentation"]["content"]) >= 80)
        check(f"{fname}: autoClose emitted", p["alertStrategy"].get("autoClose") == "1800s")
        cond = p["conditions"][0]
        if "conditionPrometheusQueryLanguage" in cond:
            c = cond["conditionPrometheusQueryLanguage"]
            check(f"{fname}: evaluationInterval 60s", c["evaluationInterval"] == "60s")
            check(f"{fname}: no __name__ regex (GMP rejects it)", "__name__" not in c["query"])
            for lset, rset in _and_sides_by_sets(c["query"]):
                check(f"{fname}: both sides of `and` group by the same labels",
                      lset == rset and len(lset) == 1, (lset, rset, c["query"]))
            if "run_googleapis_com:" in c["query"]:
                n_sel = c["query"].count("run_googleapis_com:")
                check(f"{fname}: every Cloud Run selector has the monitored_resource matcher",
                      c["query"].count('monitored_resource="cloud_run_revision"') == n_sel, c["query"])
        else:
            check(f"{fname}: log rule has notificationRateLimit",
                  p["alertStrategy"]["notificationRateLimit"]["period"] == "300s", p["alertStrategy"])
            check(f"{fname}: log rule scoped to the spec's services",
                  'resource.labels.service_name="api"' in cond["conditionMatchedLog"]["filter"],
                  cond["conditionMatchedLog"]["filter"])

    by_rule = {p["userLabels"]["rule_id"]: p for _, p in pols}
    check("severity page -> CRITICAL",
          by_rule["cloudrun-5xx_ratio"]["severity"] == "CRITICAL", by_rule.keys())
    check("override severity ticket -> WARNING",
          by_rule["gofr-http-server-error_ratio"]["severity"] == "WARNING")
    q = by_rule["cloudrun-latency_p95"]["conditions"][0]["conditionPrometheusQueryLanguage"]["query"]
    check("cloudrun p95 threshold in ms (5s -> 5000)", "> 5000 and" in q, q)
    c = by_rule["bff-upstream-errors"]["conditions"][0]["conditionPrometheusQueryLanguage"]
    check("may_be_absent -> disableMetricValidation", c.get("disableMetricValidation") is True, c)
    check("custom `in` filter renders as an anchored regex", 'code=~"502|503"' in c["query"], c["query"])
    check("for -> condition duration", c["duration"] == "600s", c)
    c0 = by_rule["cloudrun-5xx_count"]["conditions"][0]["conditionPrometheusQueryLanguage"]
    check("for: 0s omits duration (the API drops a zero, which would read as drift)",
          "duration" not in c0, c0)

    # spec_hash: stable, and moves when a threshold moves
    again = render_gmp(spec)
    check("spec_hash is deterministic",
          [p["userLabels"]["spec_hash"] for _, p in again.policies]
          == [p["userLabels"]["spec_hash"] for _, p in pols])
    spec2 = yaml.safe_load(FULL_SPEC.read_text())
    spec2["overrides"]["cloudrun.latency_p95"]["threshold"] = "6s"
    moved = {p["userLabels"]["rule_id"]: p["userLabels"]["spec_hash"] for _, p in render_gmp(spec2).policies}
    before = {p["userLabels"]["rule_id"]: p["userLabels"]["spec_hash"] for _, p in pols}
    check("changing one threshold changes only that policy's hash",
          [k for k in before if before[k] != moved[k]] == ["cloudrun-latency_p95"],
          [k for k in before if before[k] != moved[k]])

    # probes: one un-thresholded expression per PromQL policy
    promql_pols = [p for _, p in pols if "conditionPrometheusQueryLanguage" in p["conditions"][0]]
    check("one probe per PromQL policy", len(out.probes) == len(promql_pols), len(out.probes))
    for pr in out.probes:
        check(f"probe {pr['rule_id']} carries no threshold comparison",
              not re.search(r"[<>]=?\s*[0-9]", pr["expr"]), pr["expr"])

    # targets
    from alertgen.render_prom import render as render_prom
    rules = resolve(spec)
    try:
        render_prom(rules)
        e = ""
    except SpecError as ex:
        e = str(ex)
    check("prometheus target refuses GCP-only rules", "cloudrun" in e, e)
    groups = render_prom(rules, oracle=True)
    alerts = [r["alert"] for g in groups["groups"] for r in g["rules"]]
    check("oracle render includes PromQL rules, skips log rules",
          "cloudrun_5xx_ratio" in alerts and not any(a.startswith("logs_") for a in alerts), alerts)
    portable = resolve(base_spec(packs=["gofr-http", "gofr-sql"]))
    check("prometheus target renders portable packs", len(render_prom(portable)["groups"][0]["rules"]) == 4)

    from alertgen.cli import main as cli_main
    with tempfile.TemporaryDirectory() as tmp:
        sp = Path(tmp) / "a.yaml"
        sp.write_text(yaml.safe_dump(base_spec(packs=["gofr-http"])))
        rc = cli_main(["render", "--spec", str(sp), "--target", "dynatrace", "--out", tmp])
        check("dynatrace target is refused (documented mapping only)", rc != 0, rc)
        rc = cli_main(["render", "--spec", str(sp), "--target", "gmp", "--owner", "Acme/App",
                       "--out", str(Path(tmp) / "out")])
        files = sorted(p.name for p in (Path(tmp) / "out").iterdir())
        check("cli render gmp writes policies + probes + manifest",
              rc == 0 and "probes.json" in files and "manifest.json" in files
              and any(f.startswith("policy-") for f in files), (rc, files))
        pol = yaml.safe_load((Path(tmp) / "out" / [f for f in files if f.startswith("policy-")][0]).read_text())
        check("cli sanitises the owner into a legal label",
              pol["userLabels"]["alertgen_owner"] == "acme_app", pol["userLabels"])


# --- 3. golden -------------------------------------------------------------------
def test_golden():
    from alertgen.compile import resolve
    from alertgen.render_prom import render as render_prom
    print("golden · rendered output for tests/alertgen/spec-full.yaml")
    spec = yaml.safe_load(FULL_SPEC.read_text())
    out = render_gmp(spec)
    actual = {f"gmp/{fname}": yaml.safe_dump(p, sort_keys=True, allow_unicode=True)
              for fname, p in out.policies}
    actual["gmp/probes.json"] = json.dumps(out.probes, indent=2, sort_keys=True) + "\n"
    actual["prometheus-rules.yaml"] = yaml.safe_dump(render_prom(resolve(spec), oracle=True),
                                                     sort_keys=False, allow_unicode=True)
    if UPDATE:
        shutil.rmtree(GOLDEN, ignore_errors=True)
        for rel, text in actual.items():
            (GOLDEN / rel).parent.mkdir(parents=True, exist_ok=True)
            (GOLDEN / rel).write_text(text)
        print(f"  wrote {len(actual)} golden file(s)")
        return
    existing = {str(p.relative_to(GOLDEN)) for p in GOLDEN.rglob("*") if p.is_file()}
    check("golden file set matches", existing == set(actual),
          sorted(existing ^ set(actual)))
    for rel, text in sorted(actual.items()):
        p = GOLDEN / rel
        check(f"golden {rel}", p.is_file() and p.read_text() == text)


# --- 4. promtool -----------------------------------------------------------------
def test_promtool():
    from alertgen.compile import resolve
    from alertgen.render_prom import render as render_prom
    print("promtool · rendered PromQL executed against synthetic series")
    promtool = shutil.which("promtool")
    check("promtool is installed (the semantic oracle must run, not skip)", promtool is not None)
    if not promtool:
        return
    spec = yaml.safe_load((FIX / "spec-oracle.yaml").read_text())
    rules = render_prom(resolve(spec), oracle=True)
    # promtool compares annotations too; the oracle checks expressions, not prose.
    for g in rules["groups"]:
        for r in g["rules"]:
            r.pop("annotations", None)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "rules.yaml").write_text(yaml.safe_dump(rules, sort_keys=False))
        shutil.copy(FIX / "promtool" / "tests.yaml", Path(tmp) / "tests.yaml")
        proc = subprocess.run([promtool, "test", "rules", "tests.yaml"], cwd=tmp,
                              capture_output=True, text=True)
        check("promtool test rules passes", proc.returncode == 0, proc.stdout + proc.stderr)
        # anti-vacuity: the test file must actually expect alerts, and must cover the cases
        tests = yaml.safe_load((FIX / "promtool" / "tests.yaml").read_text())["tests"]
        fired = sum(1 for t in tests for a in t.get("alert_rule_test", []) if a.get("exp_alerts"))
        quiet = sum(1 for t in tests for a in t.get("alert_rule_test", []) if not a.get("exp_alerts"))
        check("oracle has firing AND quiet expectations", fired >= 3 and quiet >= 3, (fired, quiet))
        # and a deliberately broken rule must make it fail
        broken = json.loads(json.dumps(rules))
        for g in broken["groups"]:
            for r in g["rules"]:
                r["expr"] = r["expr"].replace(" > 0.05 and", " > 0.5 and")
        (Path(tmp) / "rules.yaml").write_text(yaml.safe_dump(broken, sort_keys=False))
        proc = subprocess.run([promtool, "test", "rules", "tests.yaml"], cwd=tmp,
                              capture_output=True, text=True)
        check("promtool oracle fails when a threshold is wrong (it can fail)", proc.returncode != 0)


# --- conformance -----------------------------------------------------------------
def test_conformance():
    print("conformance · rendered policies pass validate-alerts' shipped lint")
    body = extract_step(VALIDATE, "validate", "Lint policy files (offline)")
    spec = yaml.safe_load(FULL_SPEC.read_text())
    out = render_gmp(spec)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        d = tmp / "rendered"
        d.mkdir()
        for fname, p in out.policies:
            (d / fname).write_text(yaml.safe_dump(p, sort_keys=True))
        (d / "email-channel.yaml").write_text(yaml.safe_dump(
            {"type": "email", "displayName": "Ops", "labels": {"email_address": "o@example.com"}}))
        gh_out = tmp / "gh_output"
        gh_out.write_text("")
        env = dict(os.environ, ALERTS_DIR=str(d), CHANNEL_FILE="email-channel.yaml",
                   POLICY_GLOB="policy-*.yaml", RUNNER_TEMP=str(tmp), GITHUB_OUTPUT=str(gh_out))
        proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                              capture_output=True, text=True, env=env, cwd=tmp)
        check("every rendered policy passes the shipped lint", proc.returncode == 0,
              proc.stdout[-2000:] + proc.stderr[-2000:])
        outs = dict(l.split("=", 1) for l in gh_out.read_text().splitlines() if "=" in l)
        check("lint checked every rendered policy", outs.get("checked") == str(len(out.policies)), outs)


def main():
    try:
        import alertgen  # noqa: F401
    except ImportError as e:
        print(f"  FAIL alertgen importable {e}")
        return 1
    for t in (test_spec, test_render, test_golden, test_promtool, test_conformance):
        try:
            t()
        except Exception as e:  # a crash is a failure, never a skip
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ran to completion", False, repr(e))
    if SERVICE.exists():
        import run_service_alerts_steps
        run_service_alerts_steps.run(check, extract_step, SERVICE)
    else:
        check("service-alerts.yml exists", False)
    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
