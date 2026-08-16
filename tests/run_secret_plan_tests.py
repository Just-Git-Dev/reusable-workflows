#!/usr/bin/env python3
"""Self-test for the sweep-plan logic inside cleanup-secret-versions.yml.

Same shape, and the same reason, as run_plan_tests.py: the logic has to stay
INLINE in the workflow, because every `actions/checkout` in a reusable workflow
checks out the *caller's* repo, so a `scripts/*.py` shipped here would not exist
at runtime. So this runner does not re-implement anything — it extracts the
`python3 <<'PY'` block straight out of the workflow and runs that exact source
against synthetic projects via the PLAN_FIXTURE seam.

What makes this suite worth more than the GAR one: `DESTROYED` has no undelete.
Every fixture therefore asserts the plan's two hard invariants as well as its
own expectations —

  1. the version `latest` resolves to is NEVER in the disable or destroy set;
  2. no secret is ever left with zero ENABLED versions.

Usage:  python3 tests/run_secret_plan_tests.py
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "cleanup-secret-versions.yml"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures-secrets"

# Mirrors the workflow's own `env:` defaults, which are the `inputs.*` defaults.
DEFAULT_ENV = {
    "KEEP_ENABLED_COUNT": "3",
    "MIN_AGE_DAYS": "7",
    "QUARANTINE_DAYS": "30",
    "REQUIRE_CONSUMERS": "true",
    "KEEP_VERSIONS": "",
}


def extract_plan_source() -> str:
    """Pull the heredoc body out of the 'Compute plan' step."""
    lines = WORKFLOW.read_text().splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.rstrip().endswith("<<'PY' | tee /tmp/secret-plan.json"):
            start = i + 1
            break
    if start is None:
        raise SystemExit("could not find the `python3 <<'PY'` plan block in %s" % WORKFLOW)
    end = None
    for j in range(start, len(lines)):
        if lines[j].strip() == "PY":
            end = j
            break
    if end is None:
        raise SystemExit("unterminated `PY` heredoc in %s" % WORKFLOW)

    body = lines[start:end]
    indents = [len(ln) - len(ln.lstrip()) for ln in body if ln.strip()]
    pad = min(indents)
    return "\n".join(ln[pad:] if ln.strip() else "" for ln in body) + "\n"


def stamp(now, days_ago):
    return (now - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def materialise(fixture, now):
    """Turn the fixture's relative `days_ago` into the state the collect steps emit."""
    versions = []
    for secret, spec in fixture["secrets"].items():
        for v in spec["versions"]:
            versions.append({
                "secret": secret,
                "version": v["version"],
                "state": v.get("state", "ENABLED"),
                "createTime": stamp(now, v.get("days_ago", 100)),
                "etag": v.get("etag", "etag-%s-%d" % (secret, v["version"])),
                "latest": spec["latest"],
            })
    disabled_at = [
        {"secret": d["secret"], "version": d["version"], "disabledAt": stamp(now, d["days_ago"])}
        for d in fixture.get("disabled_at", [])
    ]
    return {
        "versions": versions,
        "consumers": fixture.get("consumers", []),
        "disabledAt": disabled_at,
        "now": now.isoformat().replace("+00:00", "Z"),
    }


def run_plan(source, fixture, env_overrides, tmp, now):
    """Execute the extracted workflow source; return (exit_code, plan_or_None, stderr)."""
    state_path = tmp / "state.json"
    state_path.write_text(json.dumps(materialise(fixture, now)))
    src_path = tmp / "plan.py"
    src_path.write_text(source)

    env = dict(os.environ)
    env.update(DEFAULT_ENV)
    env.update(fixture.get("env", {}))
    env.update(env_overrides)
    env["PLAN_FIXTURE"] = str(state_path)
    env.pop("GITHUB_OUTPUT", None)

    proc = subprocess.run(
        [sys.executable, str(src_path)], env=env, capture_output=True, text=True
    )
    plan = None
    if proc.returncode == 0:
        try:
            plan = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    return proc.returncode, plan, proc.stderr


def refs(plan, key):
    return sorted("%s:%d" % (v["secret"], v["version"]) for v in plan[key])


def check_invariants(name, fixture, plan):
    """The two claims that make an irreversible operation safe. Checked everywhere."""
    problems = []
    actionable = {(v["secret"], v["version"]) for v in plan["disable"] + plan["destroy"]}
    for secret, spec in fixture["secrets"].items():
        latest = spec["latest"]
        if (secret, latest) in actionable:
            problems.append(
                "%s: plan acts on %s:%d, the version `latest` resolves to" % (name, secret, latest))
        enabled = {v["version"] for v in spec["versions"] if v.get("state", "ENABLED") == "ENABLED"}
        disabling = {v["version"] for v in plan["disable"] if v["secret"] == secret}
        if enabled and not (enabled - disabling):
            problems.append("%s: plan leaves %s with no ENABLED version" % (name, secret))
    return problems


def main():
    source = extract_plan_source()
    fixtures = sorted(FIXTURE_DIR.glob("*.json"))
    if not fixtures:
        raise SystemExit("no fixtures found in %s" % FIXTURE_DIR)

    now = datetime.now(timezone.utc)
    failures = []
    for path in fixtures:
        fixture = json.loads(path.read_text())
        name = fixture.get("name", path.stem)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rc, plan, stderr = run_plan(source, fixture, {}, tmp, now)

            want_rc = fixture.get("expect_exit", 0)
            if rc != want_rc:
                failures.append(
                    "%s: exit %d, want %d\n    stderr: %s" % (name, rc, want_rc, stderr.strip()))
                continue
            if want_rc != 0:
                # A failing plan must not leave a usable plan behind.
                if plan is not None:
                    failures.append("%s: exited %d but still produced a plan" % (name, rc))
                else:
                    want_msg = fixture.get("expect_error", "")
                    if want_msg and want_msg.lower() not in stderr.lower():
                        failures.append(
                            "%s: wrong error\n    want substring: %s\n    got: %s"
                            % (name, want_msg, stderr.strip()))
                    else:
                        print("ok   %s (exit %d, no plan produced)" % (name, rc))
                continue
            if plan is None:
                failures.append("%s: exit 0 but stdout was not valid JSON" % name)
                continue

            bad = check_invariants(name, fixture, plan)
            if bad:
                failures.extend(bad)
                continue

            mismatched = False
            for key, want_key in (("disable", "expect_disable"),
                                  ("destroy", "expect_destroy"),
                                  ("held", "expect_held")):
                if want_key not in fixture:
                    continue
                got, want = refs(plan, key), sorted(fixture[want_key])
                if got != want:
                    failures.append(
                        "%s: %s-set mismatch\n    want: %s\n    got:  %s"
                        % (name, key, want, got))
                    mismatched = True
                    break
            if mismatched:
                continue

            # Structural monotonicity, checked on EVERY fixture. Each is a claim
            # the policy makes, and a fixture that violates one has found a real
            # defect even if its own expectations still match. All three say the
            # same thing: loosening a knob can only ever act on FEWER versions.
            if not fixture.get("skip_monotonic"):
                keep_n = int(fixture.get("env", {}).get(
                    "KEEP_ENABLED_COUNT", DEFAULT_ENV["KEEP_ENABLED_COUNT"]))
                probes = (
                    ("larger keep_enabled_count", {"KEEP_ENABLED_COUNT": str(keep_n + 5)}, "disable"),
                    ("larger min_age_days", {"MIN_AGE_DAYS": "3650"}, "disable"),
                    ("longer quarantine", {"QUARANTINE_DAYS": "3650"}, "destroy"),
                )
                broke = False
                for label, override, key in probes:
                    prc, probe, probe_err = run_plan(source, fixture, override, tmp, now)
                    if probe is None:
                        failures.append(
                            "%s: %s probe produced no plan (exit %d)\n    stderr: %s"
                            % (name, label, prc, probe_err.strip()))
                        broke = True
                        break
                    extra = set(refs(probe, key)) - set(refs(plan, key))
                    if extra:
                        failures.append(
                            "%s: NOT monotonic — with a %s the plan %ss %s that the "
                            "default does not" % (name, label, key, sorted(extra)))
                        broke = True
                        break
                if broke:
                    continue

            print("ok   %s (disable %d, destroy %d, held %d)"
                  % (name, len(plan["disable"]), len(plan["destroy"]), len(plan["held"])))

    if failures:
        print("\n%d FAILURE(S):\n" % len(failures), file=sys.stderr)
        for f in failures:
            print("FAIL %s\n" % f, file=sys.stderr)
        raise SystemExit(1)
    print("\nAll %d fixture(s) passed." % len(fixtures))


if __name__ == "__main__":
    main()
