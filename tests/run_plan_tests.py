#!/usr/bin/env python3
"""Self-test for the delete-plan logic inside cleanup-gar-images.yml.

The logic has to stay INLINE in the workflow: every `actions/checkout` in a
reusable workflow checks out the *caller's* repo, so a `scripts/*.py` shipped
here would simply not exist at runtime (same trap as the local-composite-action
note in TODO.md). So this runner does not re-implement anything — it extracts
the `python3 <<'PY' ... PY` block straight out of the workflow file and runs
that exact source against synthetic registries via the PLAN_FIXTURE seam.

If the workflow's algorithm changes, this tests the change. There is no copy to
drift.

Usage:  python3 tests/run_plan_tests.py
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "cleanup-gar-images.yml"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

# Mirrors the workflow's own `env:` defaults, which are the `inputs.*` defaults.
DEFAULT_ENV = {
    "REPO_PATH": "fixture-docker.pkg.dev/fixture-project/fixture-repo",
    "KEEP_SEMVER_COUNT": "5",
    "RELEASE_TAG_PATTERN": r"^v\d+\.\d+\.\d+$",
    "BUILD_RETENTION_RELEASES": "2",
    "GRACE_PERIOD_DAYS": "0",
    "KEEP_TAGS": "latest,buildcache",
    "KEEP_TAG_PREFIXES": "hotfix-,rc-,debug-",
}


def extract_plan_source() -> str:
    """Pull the heredoc body out of the 'Compute delete-set' step."""
    lines = WORKFLOW.read_text().splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.rstrip().endswith("<<'PY' | tee /tmp/delete-plan.json"):
            start = i + 1
            break
    if start is None:
        raise SystemExit("could not find the `python3 <<'PY'` block in %s" % WORKFLOW)
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


def materialise_images(spec, now):
    """Turn the fixture's relative `days_ago` into the timestamp fields GAR emits."""
    out = []
    for img in spec:
        rec = {
            "package": img["package"],
            "version": img["version"],
            "tags": img.get("tags", []),
        }
        if "days_ago" in img:
            stamp = (now - timedelta(days=img["days_ago"])).isoformat().replace("+00:00", "Z")
            for field in ("createTime", "uploadTime", "updateTime"):
                rec[field] = stamp
        # Per-field ages, for exercising the newest()/oldest() asymmetry.
        for field, days in img.get("days_ago_fields", {}).items():
            rec[field] = (now - timedelta(days=days)).isoformat().replace("+00:00", "Z")
        for field in img.get("omit", []):
            rec.pop(field, None)
        rec.update(img.get("override", {}))
        out.append(rec)
    return out


def run_plan(source, fixture, env_overrides, tmp):
    """Execute the extracted workflow source; return (exit_code, plan_or_None, stderr)."""
    now = datetime.now(timezone.utc)
    images = materialise_images(fixture["images"], now)

    images_path = tmp / "images.json"
    images_path.write_text(json.dumps(images))
    live_path = tmp / "live-digests.txt"
    live_path.write_text("\n".join(fixture.get("live_digests", [])) + "\n")
    # Always written, even when empty: otherwise the plan would fall through to the
    # real /tmp/manifest-children.json and the suite would stop being hermetic.
    child_path = tmp / "manifest-children.json"
    child_path.write_text(json.dumps(fixture.get("child_map", {})))
    src_path = tmp / "plan.py"
    src_path.write_text(source)

    env = dict(os.environ)
    env.update(DEFAULT_ENV)
    env.update(fixture.get("env", {}))
    env.update(env_overrides)
    env["PLAN_FIXTURE"] = str(images_path)
    env["LIVE_DIGESTS_FILE"] = str(live_path)
    env["CHILD_MAP_FILE"] = str(child_path)

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


def delete_set(plan):
    return sorted(item["image"] for item in plan["to_delete"])


def main():
    source = extract_plan_source()
    fixtures = sorted(FIXTURE_DIR.glob("*.json"))
    if not fixtures:
        raise SystemExit("no fixtures found in %s" % FIXTURE_DIR)

    failures = []
    for path in fixtures:
        fixture = json.loads(path.read_text())
        name = fixture.get("name", path.stem)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rc, plan, stderr = run_plan(source, fixture, {}, tmp)

            want_rc = fixture.get("expect_exit", 0)
            if rc != want_rc:
                failures.append(
                    "%s: exit %d, want %d\n    stderr: %s" % (name, rc, want_rc, stderr.strip())
                )
                continue
            if want_rc != 0:
                # A failing step must not leave a usable plan behind.
                if plan is not None:
                    failures.append("%s: exited %d but still produced a plan" % (name, rc))
                else:
                    print("ok   %s (exit %d, no plan produced)" % (name, rc))
                continue
            if plan is None:
                failures.append("%s: exit 0 but stdout was not valid JSON" % name)
                continue

            got = delete_set(plan)
            want = sorted(fixture.get("expect_delete", []))
            if got != want:
                failures.append(
                    "%s: delete-set mismatch\n    want: %s\n    got:  %s" % (name, want, got)
                )
                continue

            if "expect_blocked" in fixture:
                got_blocked = sorted(i["image"] for i in plan.get("blocked_by_parent", []))
                want_blocked = sorted(fixture["expect_blocked"])
                if got_blocked != want_blocked:
                    failures.append(
                        "%s: blocked-set mismatch\n    want: %s\n    got:  %s"
                        % (name, want_blocked, got_blocked)
                    )
                    continue

            # Structural invariants, checked on EVERY fixture. Both are monotonicity
            # claims the policy makes, and a fixture that violates either has found a
            # real defect even if its own expect_delete still matches.
            #
            #   1. A LONGER build window keeps more. Moving the boundary further back
            #      can only add builds to the keep-set.
            #   2. A LONGER grace period keeps more. The cutoff moves backwards in
            #      time, so nothing new can fall outside it.
            #
            # v1 asserted keep-only by disabling the window (SHA_RETENTION_RELEASES=0);
            # v2 has no "off" switch, so the probes vary the knob instead.
            if not fixture.get("skip_monotonic"):
                keep_n = int(fixture.get("env", {}).get(
                    "KEEP_SEMVER_COUNT", DEFAULT_ENV["KEEP_SEMVER_COUNT"]))
                for label, override in (
                    ("longer window", {"BUILD_RETENTION_RELEASES": str(keep_n)}),
                    ("longer grace", {"GRACE_PERIOD_DAYS": "3650"}),
                ):
                    _, probe, probe_err = run_plan(source, fixture, override, tmp)
                    if probe is None:
                        failures.append(
                            "%s: %s probe produced no plan\n    stderr: %s"
                            % (name, label, probe_err.strip()))
                        break
                    extra = set(delete_set(probe)) - set(got)
                    if extra:
                        failures.append(
                            "%s: NOT monotonic — with a %s the plan deletes %s that the "
                            "default does not" % (name, label, sorted(extra)))
                        break
                else:
                    print("ok   %s (%d delete candidate(s))" % (name, len(got)))
                continue

            print("ok   %s (%d delete candidate(s))" % (name, len(got)))

    if failures:
        print("\n%d FAILURE(S):\n" % len(failures), file=sys.stderr)
        for f in failures:
            print("FAIL %s\n" % f, file=sys.stderr)
        raise SystemExit(1)
    print("\nAll %d fixture(s) passed." % len(fixtures))


if __name__ == "__main__":
    main()
