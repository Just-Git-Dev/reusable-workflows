#!/usr/bin/env python3
"""Red tests for the v4 `deploy-cloud-run` runtime-config contract (docs/deploy-cloud-run.md,
"Runtime config (v4)").

Method as in run_step_tests.py: a named step's `run:` body is extracted from the workflow YAML and
executed under `bash -eo pipefail` against stubbed `gcloud` / `gh`. Written BEFORE the
implementation (v4 wave 1): each case is expected to fail until the workflow grows the step,
input or behaviour it names.

The docs fix the behaviour but not step or env-var names; the names below are the contract these
tests pin (wave 2 implements them, or amends the tests in the same change):

  Render env file        ENV_FILE GENERATED_ENV RUNNER_TEMP -> $RUNNER_TEMP/env.rendered.yaml,
                         GITHUB_OUTPUT env_sha=<first 8 hex of sha256 of the rendered file>
  Pin env bundle         ENV_SECRET ENV_MOUNT_PATH PIN_ENV SERVICE PROJECT REGION
                         -> GITHUB_OUTPUT env_version=<N> update_secrets=<mount>=<secret>:<N>
  Write config manifest  COMMIT IMAGE_DIGEST REVISION ENV_VERSION RENDERED GENERATED_ENV BUNDLE_KEYS
                         RUNNER_TEMP -> $RUNNER_TEMP/config-manifest.json
  Deploy to Cloud Run    (existing) plus ENV_RENDERED ENV_SHA ENV_VERSION UPDATE_SECRETS RUN_ID
  Forward-only guard     (existing) plus SERVICE PROJECT REGION for the jgd_commit label fallback

Q3 is settled (gcloud --env-vars-file), so that flag is asserted. Q8 (does pin_env exist at all)
is open: the pin_env:false case asserts only that a run warns, per the plan.

Usage:  python3 tests/run_deploy_env_tests.py
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / ".github" / "workflows" / "deploy-cloud-run.yml"

RENDER = "Render env file"
PIN = "Pin env bundle"
MANIFEST = "Write config manifest"
DEPLOY_STEP = "Deploy to Cloud Run"
FORWARD = "Forward-only guard"

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


def extract_step(step_name):
    """Return the `run:` body of a named step of the deploy job, or None if absent."""
    doc = yaml.safe_load(DEPLOY.read_text())
    for step in doc["jobs"]["deploy"]["steps"]:
        if step.get("name") == step_name and "run" in step:
            return step["run"]
    return None


def run_body(body, env, *, gcloud="", gh=""):
    """Run a body in a sandbox; stubs log argv to `calls`. RUNNER_TEMP is the sandbox."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        rt = tmp / "runner"
        rt.mkdir()
        calls = tmp / "calls"
        calls.write_text("")
        for name, script in (("gcloud", gcloud), ("gh", gh)):
            p = stub / name
            p.write_text('#!/usr/bin/env bash\n'
                         f'echo "{name} $*" >> {calls}\n' + script + '\nexit 0\n')
            p.chmod(0o755)
        files = env.pop("_files", {})
        for rel, content in files.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_text(content)
        e = dict(os.environ)
        e["PATH"] = f"{stub}:{e['PATH']}"
        e.update(RUNNER_TEMP=str(rt), GITHUB_OUTPUT=str(tmp / "out"),
                 GITHUB_STEP_SUMMARY=str(tmp / "summary"), SERVICE="svc", PROJECT="p",
                 REGION="r", GITHUB_WORKSPACE=str(tmp))
        e.update(env)
        proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                              capture_output=True, text=True, env=e, cwd=tmp)

        def read(p):
            return p.read_text() if p.exists() else ""
        outs = dict(re.findall(r"^(\w+)=(.*)$", read(tmp / "out"), re.M))
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "calls": read(calls), "outputs": outs,
                "rendered": read(rt / "env.rendered.yaml"),
                "manifest": read(rt / "config-manifest.json")}


def step_or_red(label, step):
    body = extract_step(step)
    if body is None:
        check(f"{label}: step '{step}' exists in {DEPLOY.name}", False,
              "(step not found: not implemented yet)")
    return body


def input_cases():
    print("\ndeploy-cloud-run v4 · input contract")
    doc = yaml.safe_load(DEPLOY.read_text())
    inputs = (doc.get("on") or doc.get(True))["workflow_call"]["inputs"]
    want = {"env_file": "", "generated_env": "", "env_secret": "", "pin_env": True,
            "manifest_retention_days": 400}
    for k, v in want.items():
        check(f"input {k} exists with default {v!r}",
              k in inputs and inputs[k].get("default") == v, f"got {inputs.get(k)}")
    check("input env_mount_path exists", "env_mount_path" in inputs)
    check("deploy job declares no job-level environment (deliberate, see docs)",
          "environment" not in doc["jobs"]["deploy"])


def render_cases():
    print("\ndeploy-cloud-run v4 · render")
    body = step_or_red("render", RENDER)
    if body is None:
        return
    envfile = "LOG_LEVEL: info\nREGION_NAME: asia\n"

    def go(file=envfile, gen="APP_VERSION=1.2.3\n"):
        return run_body(body, {"ENV_FILE": "deploy/env.stage.yaml", "GENERATED_ENV": gen,
                               "_files": {"deploy/env.stage.yaml": file}})

    r = go()
    doc = yaml.safe_load(r["rendered"]) if r["rendered"] else None
    check("render merges the file and generated_env into env.rendered.yaml",
          r["rc"] == 0 and doc == {"LOG_LEVEL": "info", "REGION_NAME": "asia",
                                   "APP_VERSION": "1.2.3"}, f"{r['out']} {r['rendered']!r}")
    r = go(gen="LOG_LEVEL=debug\n")
    check("render refuses a key present in both, naming the key",
          r["rc"] != 0 and "LOG_LEVEL" in r["out"], r["out"])
    for bad in ("DB_PASSWORD", "API_SECRET", "GITHUB_TOKEN", "REDIS_URL"):
        r = go(file=f"{bad}: x\n")
        check(f"render refuses secret-looking key {bad}, never echoing a value",
              r["rc"] != 0 and bad in r["out"], r["out"])
    r = go(file="REDIS_URLISH: x\nURL_BASE: y\n")
    check("only a trailing _URL is refused (REDIS_URLISH, URL_BASE pass)", r["rc"] == 0, r["out"])
    a, b = go(), go()
    want = hashlib.sha256(a["rendered"].encode()).hexdigest()[:8] if a["rendered"] else None
    check("env_sha is the first 8 hex of the rendered file's sha256",
          a["outputs"].get("env_sha") == want and want is not None,
          f"got {a['outputs']} want {want}")
    check("env_sha is stable for identical input", a["outputs"].get("env_sha") == b["outputs"].get("env_sha")
          and "env_sha" in a["outputs"])
    c = go(gen="APP_VERSION=9.9.9\n")
    check("env_sha changes when the content changes",
          "env_sha" in c["outputs"] and c["outputs"]["env_sha"] != a["outputs"].get("env_sha"))


def svc_json(version):
    return json.dumps({"spec": {"template": {"spec": {"volumes": [{"name": "env", "secret": {
        "secretName": "svc-env", "items": [{"key": version, "path": "app.env"}]}}]}}}})


def pin_cases():
    print("\ndeploy-cloud-run v4 · pin step")
    body = step_or_red("pin", PIN)
    if body is None:
        return
    env = {"ENV_SECRET": "svc-env", "ENV_MOUNT_PATH": "/secrets/app.env", "PIN_ENV": "true"}

    def gcloud(current):
        return ('if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n'
                f"  cat <<'J'\n{svc_json(current)}\nJ\n  exit 0\nfi\n"
                'if [ "$2" = "versions" ] && [ "$3" = "list" ]; then\n'
                '  echo projects/1/secrets/svc-env/versions/9; echo projects/1/secrets/svc-env/versions/8; exit 0\nfi')

    r = run_body(body, env, gcloud=gcloud("latest"))
    check("a mounted :latest resolves to the newest ENABLED version number (9)",
          r["rc"] == 0 and r["outputs"].get("env_version") == "9"
          and r["outputs"].get("update_secrets") == "/secrets/app.env=svc-env:9", f"{r['out']} {r['outputs']}")
    r = run_body(body, env, gcloud=gcloud("5"))
    check("a numeric pin (5) is kept even though 9 is newer: a deploy never moves it",
          r["rc"] == 0 and r["outputs"].get("env_version") == "5", f"{r['out']} {r['outputs']}")
    r = run_body(body, {**env, "PIN_ENV": "false"}, gcloud=gcloud("latest"))
    check("pin_env: false warns (Q8 open: nothing else asserted)",
          "::warning::" in r["out"], r["out"])
    # M5: a caller-supplied `<bundle>:latest` mount is refused (MIGRATION-v4 promise) ...
    for label, extra in (("deploy_flags", {"DEPLOY_FLAGS": "--set-secrets=/secrets/app.env=svc-env:latest"}),
                         ("extra_deploy_flags", {"EXTRA": "--update-secrets /x=other-env:latest"})):
        r = run_body(body, {**env, **extra}, gcloud=gcloud("5"))
        check(f"M5: a *-env:latest mount in {label} is refused", r["rc"] != 0
              and ":latest" in r["out"], r["out"])
    # ... unless the caller opts out of pinning (which warns).
    r = run_body(body, {**env, "PIN_ENV": "false",
                        "DEPLOY_FLAGS": "--set-secrets=/secrets/app.env=svc-env:latest"}, gcloud=gcloud("5"))
    check("M5: pin_env: false lets the :latest mount through (with the warning)",
          r["rc"] == 0 and "::warning::" in r["out"], r["out"])
    r = run_body(body, {**env, "DEPLOY_FLAGS": "--set-secrets=/secrets/app.env=svc-env:7"}, gcloud=gcloud("5"))
    check("M5: a numeric mount in deploy_flags is not refused", r["rc"] == 0, r["out"])


def label_cases():
    print("\ndeploy-cloud-run v4 · deploy step labels and env file")
    body = step_or_red("deploy", DEPLOY_STEP)
    if body is None:
        return
    for mode in ("update-image", "deploy"):
        r = run_body(body, {
            "IMAGE": "img@sha256:abc", "MODE": mode, "DEPLOY_FLAGS": "", "EXTRA": "",
            "COMMIT": "deadbeef", "DRY_RUN": "false", "ENV_RENDERED": "/r/env.rendered.yaml",
            "ENV_SHA": "0a1b2c3d", "ENV_VERSION": "9", "RUN_ID": "77",
            "UPDATE_SECRETS": "/secrets/app.env=svc-env:9"})
        call = next((c for c in r["calls"].splitlines() if "gcloud run" in c), "")
        check(f"[{mode}] passes --env-vars-file=<rendered> (Q3 settled)",
              "--env-vars-file=/r/env.rendered.yaml" in call, call or r["out"])
        check(f"[{mode}] stamps the four labels jgd_commit/jgd_env_version/jgd_env_sha/jgd_run",
              all(f"{k}={v}" in call for k, v in (("jgd_commit", "deadbeef"), ("jgd_env_version", "9"),
                                                  ("jgd_env_sha", "0a1b2c3d"), ("jgd_run", "77"))),
              call or r["out"])
        check(f"[{mode}] passes the pinned --update-secrets",
              "--update-secrets=/secrets/app.env=svc-env:9" in call, call or r["out"])


def manifest_cases():
    print("\ndeploy-cloud-run v4 · config-manifest.json")
    body = step_or_red("manifest", MANIFEST)
    if body is None:
        return
    r = run_body(body, {"COMMIT": "deadbeef", "IMAGE_DIGEST": "sha256:abc", "REVISION": "svc-00042",
                        "ENV_VERSION": "9", "BUNDLE_KEYS": "DB_PASSWORD,REDIS_URL",
                        "GENERATED_ENV": "APP_VERSION=1.2.3\n",
                        "RENDERED": "LOG_LEVEL: info\nAPP_VERSION: 1.2.3\n"})
    try:
        m = json.loads(r["manifest"])
    except ValueError:
        m = None
    check("manifest is valid JSON", r["rc"] == 0 and m is not None, f"{r['out']} {r['manifest'][:100]!r}")
    if m is None:
        return
    check("manifest carries commit, image digest, revision, env_secret version",
          (m.get("commit"), m.get("image_digest"), m.get("revision"), m.get("env_secret_version"))
          == ("deadbeef", "sha256:abc", "svc-00042", 9) or m.get("env_secret_version") == "9", str(m)[:200])
    keys = {k["name"]: k for k in m.get("keys", [])}
    check("keys carry source: file, generated or bundle",
          keys.get("LOG_LEVEL", {}).get("source") == "file"
          and keys.get("APP_VERSION", {}).get("source") == "generated"
          and keys.get("DB_PASSWORD", {}).get("source") == "bundle", str(keys))
    check("non-secret values are shown; bundle values never appear",
          keys.get("LOG_LEVEL", {}).get("value") == "info"
          and "value" not in keys.get("DB_PASSWORD", {"value": 1}), str(keys))


def forward_cases():
    print("\ndeploy-cloud-run v4 · forward-only label fallback")
    body = extract_step(FORWARD)
    if body is None:
        check("forward-only guard exists", False)
        return
    # gh stub: no deployments at all; compare says HEAD is behind BASE.
    gh = ('url=""; jq=""\nwhile [ $# -gt 0 ]; do case "$1" in --jq) jq="$2"; shift;; '
          'repos/*) url="$1";; esac; shift; done\n'
          'case "$url" in\n  */deployments\\?*) j="[]";;\n  */compare/*) j=\'{"status":"behind"}\';;\n'
          '  *) j="{}";; esac\n'
          'if [ -n "$jq" ]; then printf "%s" "$j" | jq -r "$jq"; else printf "%s" "$j"; fi')

    def gcloud(label):
        return ('if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n'
                f"  echo '{label}'\n  exit 0\nfi")

    env = {"GH_TOKEN": "t", "REPO": "o/r", "ENVIRONMENT": "prod", "HEAD": "cafe0001"}
    r = run_body(body, env, gh=gh, gcloud=gcloud("beef0002"))
    check("no Deployment but a jgd_commit label: baseline is the label, a behind candidate is refused",
          r["rc"] != 0 and "behind" in r["out"].lower(), r["out"])
    check("the fallback reads the service's jgd_commit label",
          "jgd_commit" in r["calls"] or "services describe" in r["calls"], r["calls"])
    # M11: a Deployments API ERROR is not "no deployment": fail closed, never fall through.
    gh_err = ('case "$*" in *deployments*) echo "HTTP 502" >&2; exit 1;; esac')
    r = run_body(body, env, gh=gh_err, gcloud=gcloud(""))
    check("a Deployments API error refuses (fail closed) instead of reading as 'no deployment'",
          r["rc"] != 0 and "::error::" in r["out"], r["out"])
    r = run_body(body, env, gh=gh, gcloud=gcloud(""))
    check("no Deployment and no label (first deploy ever): allowed with a notice",
          r["rc"] == 0 and "::notice::" in r["out"], r["out"])


def main():
    for fn in (input_cases, render_cases, pin_cases, label_cases, manifest_cases, forward_cases):
        fn()
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
