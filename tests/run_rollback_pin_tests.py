#!/usr/bin/env python3
"""Red tests for the v4 `rollback-service` pin refusal and `to_revision` mode (docs/rollback-service.md).

Same method as run_step_tests.py: a named step's `run:` body is extracted from the workflow YAML
and executed under `bash -eo pipefail` against a stubbed `gcloud`. Written BEFORE the
implementation: every case fails until the workflow grows the step, input or behaviour it names.

CONTRACT (names the docs do not fix; wave 2 implements them, or amends them in the same change):
  GUARD_STEP  "Guard revision bundle pin"   env: RUN_PROJECT RUN_REGION RUN_SERVICE REVISION
                                                 BUNDLE_SECRET ; output `image` (the revision's image)
  SHIFT_STEP  "Shift traffic to revision"   env: RUN_PROJECT RUN_REGION RUN_SERVICE REVISION DRY_RUN
  RESOLVE     "Resolve rollback target"     env adds MODE TO_REVISION
  The stub gcloud answers `run revisions describe` with JSON and `secrets versions describe` with
  a state; any `run services update` / `update-traffic` is logged so the tests can assert on it.

Usage:  python3 tests/run_rollback_pin_tests.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows" / "rollback-service.yml"

RESOLVE_STEP = "Resolve rollback target"
GUARD_STEP = "Guard revision bundle pin"
SHIFT_STEP = "Shift traffic to revision"
JOB = "rollback"

FAILURES = []
CASES = 0


def check(name, cond, detail=""):
    global CASES
    CASES += 1
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}"[:400])
        FAILURES.append(name)


def load():
    return yaml.safe_load(WF.read_text())


def find_step(step_name):
    for step in load()["jobs"][JOB]["steps"]:
        if step.get("name") == step_name:
            return step
    return None


def extract_step(step_name):
    s = find_step(step_name)
    return s.get("run") if s else None


def revision_json(version, secret="app-env"):
    return json.dumps({"spec": {
        "containers": [{"image": "gar/app@sha256:old"}],
        "volumes": [{"name": "env", "secret": {"secretName": secret,
                     "items": [{"version": version, "path": "app.env"}]}}]}})


def run_body(body, env, *, state="ENABLED", rev=None, rev_rc=0):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        calls = tmp / "calls"
        calls.write_text("")
        (tmp / "rev.json").write_text(rev if rev is not None else revision_json("3"))
        g = stub / "gcloud"
        g.write_text(f'''#!/usr/bin/env bash
echo "gcloud $*" >> {calls}
case "$*" in
  *"run revisions describe"*) [ {rev_rc} -ne 0 ] && exit {rev_rc}; cat {tmp}/rev.json ;;
  *"secrets versions describe"*) echo "{state}" ;;
esac
exit 0
''')
        g.chmod(0o755)
        e = dict(os.environ)
        e["PATH"] = f"{stub}:{e['PATH']}"
        e.update(GITHUB_STEP_SUMMARY=str(tmp / "summary"), GITHUB_OUTPUT=str(tmp / "out"),
                 RUN_PROJECT="p", RUN_REGION="r", RUN_SERVICE="svc", REVISION="svc-00005-abc",
                 BUNDLE_SECRET="app-env", DRY_RUN="false")
        e.update(env)
        proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                              capture_output=True, text=True, env=e, cwd=tmp)
        out = tmp / "out"
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "calls": calls.read_text(), "outputs": out.read_text() if out.exists() else ""}


def mutating(calls):
    return "update-traffic" in calls or "services update" in calls


def input_cases():
    print("\nrollback-service · input contract")
    doc = load()
    on = doc.get("on") or doc.get(True)
    inputs = on["workflow_call"]["inputs"]
    for k, v in {"mode": "image", "to_revision": "", "bundle_secret": ""}.items():
        check(f"input {k} exists with default {v!r}",
              k in inputs and inputs[k].get("default") == v, f"got {inputs.get(k)}")
    check("input mode is a string", inputs.get("mode", {}).get("type") == "string")


def guard_cases():
    print("\nrollback-service · pin guard")
    body = extract_step(GUARD_STEP)
    if body is None:
        check(f"step '{GUARD_STEP}' exists", False, "(not implemented yet)")
        return
    r = run_body(body, {}, state="DISABLED")
    check("disabled pin: exits non-zero", r["rc"] != 0, r["out"])
    check("disabled pin: error names the revision", "svc-00005-abc" in r["out"], r["out"])
    check("disabled pin: error names app-env:3", "app-env:3" in r["out"], r["out"])
    check("disabled pin: error says refused and DISABLED",
          "rollback refused" in r["out"] and "DISABLED" in r["out"], r["out"])
    check("disabled pin: no gcloud update/traffic call", not mutating(r["calls"]), r["calls"])

    r = run_body(body, {}, state="ENABLED")
    check("enabled pin: proceeds (rc 0)", r["rc"] == 0, r["out"])
    check("enabled pin: exports the revision's image",
          "image=gar/app@sha256:old" in r["outputs"], r["outputs"])
    check("enabled pin: checks the version it read (3)",
          "versions describe 3" in r["calls"], r["calls"])

    r = run_body(body, {}, state="DESTROYED")
    check("destroyed pin: refused too (state != ENABLED)", r["rc"] != 0 and "app-env:3" in r["out"], r["out"])

    r = run_body(body, {}, rev=revision_json("3", secret="other-secret"), state="DISABLED")
    check("revision mounting a different secret: no refusal for the bundle", r["rc"] == 0, r["out"])

    r = run_body(body, {"BUNDLE_SECRET": ""}, state="DISABLED")
    check("empty bundle_secret: check skipped with a notice, rc 0",
          r["rc"] == 0 and "versions describe" not in r["calls"], r["out"] + r["calls"])

    r = run_body(body, {}, rev_rc=1)
    check("unknown revision: fails, no mutation", r["rc"] != 0 and not mutating(r["calls"]), r["out"])

    r = run_body(body, {}, rev=revision_json("latest"), state="ENABLED")
    check("version 'latest' is resolved, not mis-reported", r["rc"] == 0, r["out"])


def shift_cases():
    print("\nrollback-service · to_revision shift")
    body = extract_step(SHIFT_STEP)
    if body is None:
        check(f"step '{SHIFT_STEP}' exists", False, "(not implemented yet)")
        return
    r = run_body(body, {})
    check("shift: update-traffic to the revision at 100",
          r["rc"] == 0 and "update-traffic svc" in r["calls"]
          and "--to-revisions svc-00005-abc=100" in r["calls"], r["out"] + r["calls"])
    r = run_body(body, {"DRY_RUN": "true"})
    check("shift dry run: prints, calls nothing", r["rc"] == 0 and not mutating(r["calls"]), r["calls"])

    step = find_step(SHIFT_STEP)
    check("shift runs only in to_revision mode and after the guard",
          "to_revision" in str(step.get("if", "")), str(step.get("if")))
    steps = [s.get("name") for s in load()["jobs"][JOB]["steps"]]
    check("guard precedes the shift", steps.index(GUARD_STEP) < steps.index(SHIFT_STEP), steps)


def mode_cases():
    print("\nrollback-service · mode validation and image mode")
    body = extract_step(RESOLVE_STEP)
    base = {"MODE": "image", "TO_REVISION": "", "ROLLBACK_TAG": "v1", "ROLLBACK_DIGEST": "",
            "DEPLOY_TARGET": "cloud-run", "REGION": "r", "IN_REGISTRY": "", "GAR_PROJECT": "p",
            "GAR_REPO": "r", "IMAGE_NAME": "i"}
    r = run_body(body, base)
    check("image mode (default) still resolves the image", r["rc"] == 0 and "image=" in r["outputs"], r["out"])
    r = run_body(body, {**base, "MODE": "to_revision", "ROLLBACK_TAG": "", "TO_REVISION": "svc-1"})
    check("to_revision mode needs no tag/digest", r["rc"] == 0, r["out"])
    r = run_body(body, {**base, "MODE": "to_revision", "ROLLBACK_TAG": "", "TO_REVISION": ""})
    check("to_revision mode without to_revision is refused", r["rc"] != 0, r["out"])
    r = run_body(body, {**base, "MODE": "to_revision", "TO_REVISION": "svc-1"})
    check("to_revision with a tag as well is refused", r["rc"] != 0, r["out"])
    r = run_body(body, {**base, "MODE": "to_revision", "ROLLBACK_TAG": "", "TO_REVISION": "svc-1",
                        "DEPLOY_TARGET": "gke"})
    check("to_revision on gke is refused", r["rc"] != 0, r["out"])
    r = run_body(body, {**base, "TO_REVISION": "svc-1"})
    check("image mode with to_revision set is refused", r["rc"] != 0, r["out"])
    r = run_body(body, {**base, "MODE": "bogus"})
    check("unknown mode is refused", r["rc"] != 0, r["out"])

    for n in ("Verify rollback image exists", "Roll Cloud Run"):
        s = find_step(n)
        check(f"'{n}' is image-mode only", s is not None and "image" in str(s.get("if", "")),
              str(s and s.get("if")))
    summ = extract_step("Summary")
    check("summary warns image mode runs old code on the current secrets",
          summ is not None and "current" in summ and "secrets" in summ, "")


def main():
    for fn in (input_cases, guard_cases, shift_cases, mode_cases):
        fn()
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
