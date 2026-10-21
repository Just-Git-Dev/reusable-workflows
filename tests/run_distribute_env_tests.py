#!/usr/bin/env python3
"""Red tests for .github/workflows/distribute-env-secrets.yml (docs/distribute-env-secrets.md).

Same idiom as run_step_tests.py: a named step's `run:` body is extracted from the workflow YAML
and executed under `bash -eo pipefail` against a stubbed `gh`. The stub records every call (argv)
and the stdin of `secret set`, and answers `GET .../environments/<env>` from a list of existing
environments (anything else -> HTTP 404), so the suite proves:

  * an EMPTY source value is refused before anything is written;
  * a missing environment (404) fails the run and nothing is ever PUT/POSTed (never creates one);
  * `dry_run: true` writes nothing and prints names, never values;
  * the value reaches `gh secret set` on stdin only, never in argv or in output;
  * zero targets examined fails the run.

NAMES THIS FILE INVENTS (not fixed by the doc; the implementer matches them or edits the
constants below): job `distribute`; steps "Validate mapping" and "Distribute secrets"; the env
vars the bodies read: MAPPING_FILE, DRY_RUN, ONLY, SOURCES_JSON, ORG, GH_TOKEN.

Usage:  python3 tests/run_distribute_env_tests.py
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "distribute-env-secrets.yml"
JOB = "distribute"
STEPS = ["Validate mapping", "Distribute secrets"]
ORG = "Example-Org"

SECRET_VALUE = "s3cr3t-VALUE-0123456789"
OTHER_VALUE = "an0ther-VALUE-9876543210"

MAPPING = {"distribute": [
    {"source": "R2_ACCESS_KEY_ID", "repo": "api", "environment": "prod", "name": "R2_ACCESS_KEY_ID"},
    {"source": "R2_SECRET_ACCESS_KEY", "repo": "api", "environment": "prod", "name": "R2_SECRET_ACCESS_KEY"},
]}
SOURCES = {"R2_ACCESS_KEY_ID": SECRET_VALUE, "R2_SECRET_ACCESS_KEY": OTHER_VALUE, "UNRELATED": "x"}

GH_STUB = r"""#!/usr/bin/env bash
# records argv (one line per call); `secret set` stdin goes to stdin.log; GET environment answered
# from existing-envs.txt ("<repo>/<env>" per line), otherwise HTTP 404.
echo "$*" >> "$STUB_DIR/calls.log"
if [ "$1" = "secret" ] && [ "$2" = "set" ]; then
  if [ -n "$FAIL_ON" ] && [ "$3" = "$FAIL_ON" ]; then cat > /dev/null; echo "gh: HTTP 500" >&2; exit 1; fi
  cat >> "$STUB_DIR/stdin.log"; echo >> "$STUB_DIR/stdin.log"
  exit 0
fi
if [ "$1" = "api" ]; then
  for a in "$@"; do
    case "$a" in
      repos/*/environments/*)
        rest="${a#repos/*/}"; repo="${rest%%/environments/*}"; env="${rest##*/environments/}"
        env="${env%%\?*}"
        if grep -qx "$repo/$env" "$STUB_DIR/existing-envs.txt"; then echo '{}'; exit 0; fi
        echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
    esac
  done
fi
exit 0
"""


def step_body(name):
    assert WORKFLOW.is_file(), "%s does not exist" % WORKFLOW.name
    doc = yaml.safe_load(WORKFLOW.read_text())
    for step in doc["jobs"][JOB]["steps"]:
        if step.get("name") == name:
            assert "run" in step, "step %r has no run: body" % name
            return step["run"]
    raise AssertionError("step %r not found in %s:%s" % (name, WORKFLOW.name, JOB))


def run_steps(mapping=MAPPING, sources=SOURCES, existing=("api/prod",), dry_run="false", only="", fail_on=""):
    """Run the steps in order in one temp dir; return (rc, output, calls, stdin_log)."""
    bodies = [step_body(n) for n in STEPS]
    with tempfile.TemporaryDirectory(dir=str(ROOT / ".scratch") if (ROOT / ".scratch").is_dir() else None) as d:
        d = Path(d)
        stub = d / "bin"
        stub.mkdir()
        gh = stub / "gh"
        gh.write_text(GH_STUB)
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        (d / "existing-envs.txt").write_text("".join(e + "\n" for e in existing))
        (stub / "calls.log").write_text("")
        (stub / "stdin.log").write_text("")
        (stub / "existing-envs.txt").write_text("".join(e + "\n" for e in existing))
        (d / "mapping.yaml").write_text(json.dumps(mapping))
        env = dict(os.environ)
        env.update({
            "PATH": "%s:%s" % (stub, env["PATH"]), "STUB_DIR": str(stub),
            "FAIL_ON": fail_on, "MAPPING_FILE": "mapping.yaml", "DRY_RUN": dry_run, "ONLY": only,
            "SOURCES_JSON": json.dumps(sources), "ORG": ORG, "GH_TOKEN": "tok-not-a-real-token",
            "GITHUB_REPOSITORY_OWNER": ORG, "GITHUB_OUTPUT": str(d / "out"), "GITHUB_STEP_SUMMARY": str(d / "summary"),
        })
        out, rc = "", 0
        for body in bodies:
            p = subprocess.run(["bash", "-eo", "pipefail", "-c", body], cwd=str(d), env=env,
                               capture_output=True, text=True)
            out += p.stdout + p.stderr
            if p.returncode != 0:
                rc = p.returncode
                break
        summary = d / "summary"
        if summary.exists():
            out += summary.read_text()
        calls = (stub / "calls.log").read_text().splitlines()
        stdin = (stub / "stdin.log").read_text()
    return rc, out, calls, stdin


def secret_sets(calls):
    return [c for c in calls if c.startswith("secret set")]


def writes_to_envs(calls):
    """Any API call that is not a plain GET (create/modify an environment, branch policy...)."""
    bad = []
    for c in calls:
        if c.startswith("api") and any(m in c.split() for m in ("PUT", "POST", "DELETE", "PATCH")):
            bad.append(c)
    return bad


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def workflow_declares_the_documented_inputs_and_secrets():
    assert WORKFLOW.is_file(), "%s does not exist" % WORKFLOW.name
    doc = yaml.safe_load(WORKFLOW.read_text())
    on = doc.get("on", doc.get(True))
    call = on["workflow_call"]
    ins, secs = call["inputs"], call["secrets"]
    for k in ("mapping_file", "environment", "app_id", "dry_run", "only"):
        assert k in ins, "missing input %s" % k
    assert ins["dry_run"]["default"] is True, "dry_run must default to true"
    assert ins["mapping_file"]["default"] == ".github/distribute-env-secrets.yaml"
    assert ins["environment"]["default"] == "repo-admin"
    assert ins["app_id"].get("required") is True
    for k in ("app_key", "sources_json"):
        assert k in secs and secs[k].get("required") is True, "secret %s missing/not required" % k
    assert doc["jobs"][JOB]["environment"] == "${{ inputs.environment }}"


@case
def happy_path_writes_each_secret_with_value_on_stdin_only():
    rc, out, calls, stdin = run_steps()
    assert rc == 0, "rc=%d out=%s" % (rc, out[-300:])
    sets = secret_sets(calls)
    assert len(sets) == 2, sets
    for c in sets:
        assert "--env prod" in c and "--repo %s/api" % ORG in c, c
        assert SECRET_VALUE not in c and OTHER_VALUE not in c, "value in argv: %s" % c
    assert any("secret set R2_ACCESS_KEY_ID" in c for c in sets), sets
    assert SECRET_VALUE in stdin and OTHER_VALUE in stdin, "values did not arrive on stdin"
    assert SECRET_VALUE not in out and OTHER_VALUE not in out, "value leaked into output"


@case
def empty_source_value_is_refused_and_nothing_is_written():
    src = dict(SOURCES, R2_SECRET_ACCESS_KEY="")
    rc, out, calls, _ = run_steps(sources=src)
    assert rc != 0, "an empty source must fail the run"
    assert secret_sets(calls) == [], "secrets written despite an empty source: %s" % secret_sets(calls)
    assert "R2_SECRET_ACCESS_KEY" in out, "the empty source is not named: %s" % out[-300:]


@case
def m9_placeholder_source_values_are_refused_and_nothing_is_written():
    for bad in ("changeme", "-", "TODO", "xxxx", "<your-key>", "${KEY}", "  Change_Me "):
        src = dict(SOURCES, R2_SECRET_ACCESS_KEY=bad)
        rc, out, calls, _ = run_steps(sources=src)
        assert rc != 0 and secret_sets(calls) == [], "placeholder %r accepted: %s" % (bad, out[-200:])
        assert "R2_SECRET_ACCESS_KEY" in out and (len(bad.strip()) < 4 or bad.strip() not in out.replace("R2_SECRET_ACCESS_KEY", "")), \
            "source not named / value echoed for %r: %s" % (bad, out[-300:])


@case
def m9_a_failed_write_reports_which_targets_were_already_written():
    rc, out, calls, _ = run_steps(sources=SOURCES, existing=("api/prod",), dry_run="false",
                                  fail_on="R2_SECRET_ACCESS_KEY")
    assert rc != 0, "a failing second write must fail the run"
    assert "R2_ACCESS_KEY_ID" in out and "already written" in out, out[-400:]


@case
def missing_environment_fails_and_is_never_created():
    rc, out, calls, _ = run_steps(existing=())
    assert rc != 0, "a 404 environment must fail the run"
    assert "missing environment api/prod" in out, out[-300:]
    assert secret_sets(calls) == [], secret_sets(calls)
    assert writes_to_envs(calls) == [], "environment write attempted: %s" % writes_to_envs(calls)


@case
def one_missing_environment_among_several_writes_no_secret():
    m = {"distribute": MAPPING["distribute"] + [
        {"source": "R2_ACCESS_KEY_ID", "repo": "api", "environment": "stage", "name": "R2_ACCESS_KEY_ID"}]}
    rc, out, calls, _ = run_steps(mapping=m, existing=("api/prod",))
    assert rc != 0 and "missing environment api/stage" in out, out[-300:]
    assert secret_sets(calls) == [], "partial distribution: %s" % secret_sets(calls)


@case
def dry_run_writes_nothing_and_prints_names_not_values():
    rc, out, calls, stdin = run_steps(dry_run="true")
    assert rc == 0, "rc=%d out=%s" % (rc, out[-300:])
    assert secret_sets(calls) == [], secret_sets(calls)
    assert writes_to_envs(calls) == [], writes_to_envs(calls)
    assert stdin.strip() == "", "stdin was written in dry run"
    assert "R2_ACCESS_KEY_ID" in out, "dry run does not print the planned names"
    assert SECRET_VALUE not in out and OTHER_VALUE not in out, "value leaked into output"


@case
def dry_run_still_fails_on_a_missing_environment():
    rc, out, calls, _ = run_steps(dry_run="true", existing=())
    assert rc != 0 and "missing environment api/prod" in out, out[-300:]


@case
def zero_targets_in_the_mapping_fails():
    rc, out, calls, _ = run_steps(mapping={"distribute": []})
    assert rc != 0, "zero targets must fail, not pass"
    assert secret_sets(calls) == []


@case
def only_filter_matching_nothing_fails_as_zero_targets():
    rc, out, calls, _ = run_steps(only="NO_SUCH_SOURCE")
    assert rc != 0, "a filter that leaves zero targets must fail"
    assert secret_sets(calls) == []


@case
def only_filter_distributes_just_that_source():
    rc, out, calls, _ = run_steps(only="R2_ACCESS_KEY_ID")
    assert rc == 0, "rc=%d out=%s" % (rc, out[-300:])
    sets = secret_sets(calls)
    assert len(sets) == 1 and "R2_ACCESS_KEY_ID" in sets[0], sets


@case
def duplicate_repo_environment_name_triple_refuses_the_whole_run():
    m = {"distribute": MAPPING["distribute"] + [
        {"source": "UNRELATED", "repo": "api", "environment": "prod", "name": "R2_ACCESS_KEY_ID"}]}
    rc, out, calls, _ = run_steps(mapping=m)
    assert rc != 0, "a duplicate repo/environment/name must refuse the run"
    assert secret_sets(calls) == [], secret_sets(calls)


@case
def source_absent_from_sources_json_is_refused_like_an_empty_one():
    src = {k: v for k, v in SOURCES.items() if k != "R2_SECRET_ACCESS_KEY"}
    rc, out, calls, _ = run_steps(sources=src)
    assert rc != 0, "a source the caller did not pass must fail"
    assert secret_sets(calls) == []


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
            print("ok   %s" % fn.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (fn.__name__, str(e)[:300]))
        except Exception as e:
            failed += 1
            print("FAIL %s: %s: %s" % (fn.__name__, type(e).__name__, str(e)[:300]))
    print("%d cases run, %d failed" % (len(CASES), failed))
    return 1 if failed or not CASES else 0


if __name__ == "__main__":
    sys.exit(main())
