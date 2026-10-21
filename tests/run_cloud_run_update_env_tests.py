#!/usr/bin/env python3
"""Red tests for the v4 env-file contract of `cloud-run-update` (docs/cloud-run-update.md,
"Env file, labels and manifest (v4.x)"). Mirrors run_deploy_env_tests.py: a named step's `run:`
body is extracted from the workflow YAML and run under `bash -eo pipefail` against stubbed gcloud.

Step and env-var names are the ones deploy-cloud-run already uses (same bodies, copied):

  Render env file        ENV_FILE GENERATED_ENV            -> env_sha, path
  Pin env bundle         ENV_SECRET ENV_MOUNT_PATH PIN_ENV -> env_version, update_secrets
  Write config manifest  COMMIT REVISION ENV_VERSION RENDERED GENERATED_ENV BUNDLE_KEYS
  Apply the configuration (existing) plus ENV_RENDERED ENV_SHA ENV_VERSION UPDATE_SECRETS RUN_ID
  Validate the inputs    (existing) plus ENV_FILE ENV_VARS

Rule for the doc's open point (env_file AND env_vars both given): the run is REFUSED.

Usage:  python3 tests/run_cloud_run_update_env_tests.py
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_deploy_env_tests as D  # noqa: E402  (reuse run_body / svc_json only)

ROOT = Path(__file__).resolve().parent.parent
UPDATE = ROOT / ".github" / "workflows" / "cloud-run-update.yml"
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
    return yaml.safe_load(UPDATE.read_text())


def step_body(name):
    for s in load()["jobs"]["update"]["steps"]:
        if s.get("name") == name and "run" in s:
            return s["run"]
    check(f"step '{name}' exists in {UPDATE.name}", False, "(not implemented yet)")
    return None


APPLY_BASE = {"RUNTIME_SA": "", "ENV_VARS": "", "ENV_MODE": "update", "CLEAR_ENV": "false",
              "SECRETS": "", "SEC_MODE": "update", "LABELS": "", "PORT": "", "CPU": "",
              "MEMORY": "", "CONCURRENCY": "", "MIN_INST": "", "MAX_INST": "", "BOOST": "",
              "REQ_TIMEOUT": "", "PROBE": "", "EXTRA": "", "DRY": "false"}


def input_cases():
    print("\ncloud-run-update v4 · inputs")
    doc = load()
    inputs = (doc.get("on") or doc.get(True))["workflow_call"]["inputs"]
    want = {"env_file": "", "generated_env": "", "env_secret": "", "env_mount_path": "",
            "pin_env": True, "manifest_retention_days": 400}
    for k, v in want.items():
        check(f"input {k} exists with default {v!r}",
              k in inputs and inputs[k].get("default") == v, f"got {inputs.get(k)}")


def validate_cases():
    print("\ncloud-run-update v4 · env_file vs env_vars")
    body = step_body("Validate the inputs")
    if body is None:
        return
    base = {"ENV_MODE": "update", "SEC_MODE": "update", "BOOST": "", "ENV_FILE": "", "ENV_VARS": ""}
    r = D.run_body(body, {**base, "ENV_FILE": "deploy/env.yaml", "ENV_VARS": "A=1"})
    check("both env_file and env_vars: refused, naming both inputs",
          r["rc"] != 0 and "env_file" in r["out"] and "env_vars" in r["out"], r["out"])
    r = D.run_body(body, {**base, "ENV_FILE": "deploy/env.yaml"})
    check("env_file alone is accepted", r["rc"] == 0, r["out"])
    r = D.run_body(body, {**base, "ENV_VARS": "A=1"})
    check("env_vars alone is accepted", r["rc"] == 0, r["out"])


def render_cases():
    print("\ncloud-run-update v4 · render")
    body = step_body("Render env file")
    if body is None:
        return
    files = {"deploy/env.stage.yaml": "LOG_LEVEL: info\n"}

    def go(gen="APP_VERSION=1.2.3\n", f=files):
        return D.run_body(body, {"ENV_FILE": "deploy/env.stage.yaml", "GENERATED_ENV": gen, "_files": f})

    r = go()
    doc = yaml.safe_load(r["rendered"]) if r["rendered"] else None
    check("render merges the file and generated_env", r["rc"] == 0
          and doc == {"LOG_LEVEL": "info", "APP_VERSION": "1.2.3"}, f"{r['out']} {r['rendered']!r}")
    check("render emits env_sha (8 hex)", len(r["outputs"].get("env_sha", "")) == 8, str(r["outputs"]))
    r = go(gen="LOG_LEVEL=debug\n")
    check("a key in both is refused, naming the key", r["rc"] != 0 and "LOG_LEVEL" in r["out"], r["out"])
    r = go(f={"deploy/env.stage.yaml": "DB_PASSWORD: x\n"})
    check("a secret-looking key is refused", r["rc"] != 0 and "DB_PASSWORD" in r["out"], r["out"])


def pin_cases():
    print("\ncloud-run-update v4 · pin")
    body = step_body("Pin env bundle")
    if body is None:
        return
    env = {"ENV_SECRET": "svc-env", "ENV_MOUNT_PATH": "/secrets/app.env", "PIN_ENV": "true"}
    gcloud = ('if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n'
              f"  cat <<'J'\n{D.svc_json('latest')}\nJ\n  exit 0\nfi\n"
              'if [ "$2" = "versions" ] && [ "$3" = "list" ]; then\n  echo projects/1/secrets/svc-env/versions/9; echo projects/1/secrets/svc-env/versions/8; exit 0\nfi')
    r = D.run_body(body, env, gcloud=gcloud)
    check("a mounted :latest resolves to the newest ENABLED version",
          r["rc"] == 0 and r["outputs"].get("env_version") == "9"
          and r["outputs"].get("update_secrets") == "/secrets/app.env=svc-env:9", f"{r['out']} {r['outputs']}")
    check("describe puts the global --project flag first (stub-matchable)",
          "gcloud --project=p run services describe" in r["calls"], r["calls"])
    r = D.run_body(body, {**env, "PIN_ENV": "false"}, gcloud=gcloud)
    check("pin_env: false warns", "::warning::" in r["out"], r["out"])
    r = D.run_body(body, {**env, "SECRETS": "/secrets/app.env=svc-env:latest"}, gcloud=gcloud)
    check("M5: a caller-supplied *-env:latest mount in `secrets` is refused",
          r["rc"] != 0 and ":latest" in r["out"], r["out"])
    r = D.run_body(body, {**env, "PIN_ENV": "false", "SECRETS": "/secrets/app.env=svc-env:latest"}, gcloud=gcloud)
    check("M5: pin_env: false lets it through", r["rc"] == 0, r["out"])
    r = D.run_body(body, {**env, "SECRETS": "/secrets/app.env=svc-env:3"}, gcloud=gcloud)
    check("M5: a numeric mount is not refused", r["rc"] == 0, r["out"])


def apply_cases():
    print("\ncloud-run-update v4 · apply")
    body = step_body("Apply the configuration")
    if body is None:
        return

    def go(**extra):
        r = D.run_body(body, {**APPLY_BASE, **extra})
        r["call"] = next((c for c in r["calls"].splitlines() if "run services update" in c), "")
        return r

    r = go()
    check("a bare run sends no env file, no labels, no secrets (empty = do not touch)",
          r["rc"] == 0 and not any(f in r["call"] for f in ("--env-vars-file", "--update-labels", "--update-secrets")),
          r["call"] or r["out"])
    r = go(ENV_RENDERED="/r/env.rendered.yaml", ENV_SHA="0a1b2c3d", ENV_VERSION="9", RUN_ID="77",
           UPDATE_SECRETS="/secrets/app.env=svc-env:9", LABELS="team=core\n")
    c = r["call"]
    check("passes --env-vars-file=<rendered>", "--env-vars-file=/r/env.rendered.yaml" in c, c or r["out"])
    check("stamps jgd_env_version / jgd_env_sha / jgd_run",
          all(x in c for x in ("jgd_env_version=9", "jgd_env_sha=0a1b2c3d", "jgd_run=77")), c or r["out"])
    check("caller labels survive, in ONE --update-labels (a second flag would replace the first)",
          "team=core" in c and c.count("--update-labels") == 1, c)
    check("pinned bundle mount is passed, in ONE --update-secrets", "/secrets/app.env=svc-env:9" in c
          and c.count("--update-secrets") == 1, c)
    r = go(ENV_RENDERED="/r/e.yaml", ENV_SHA="0a1b2c3d", RUN_ID="77", SECRETS="/c/.env=other:2\n",
           UPDATE_SECRETS="/secrets/app.env=svc-env:9")
    check("caller secrets and the bundle mount coexist in one flag",
          "other:2" in r["call"] and "svc-env:9" in r["call"] and r["call"].count("--update-secrets") == 1,
          r["call"] or r["out"])
    r = go(ENV_RENDERED="/r/e.yaml", ENV_SHA="0a1b2c3d", RUN_ID="77", DRY="true")
    check("dry_run prints the env-file flag without applying",
          r["rc"] == 0 and "--env-vars-file" in r["out"] and not r["call"], r["out"])


def manifest_cases():
    print("\ncloud-run-update v4 · manifest")
    body = step_body("Write config manifest")
    if body is None:
        return
    import json
    r = D.run_body(body, {"COMMIT": "deadbeef", "REVISION": "svc-00042", "ENV_VERSION": "9",
                          "BUNDLE_KEYS": "DB_PASSWORD", "GENERATED_ENV": "APP_VERSION=1.2.3\n",
                          "RENDERED": "LOG_LEVEL: info\nAPP_VERSION: 1.2.3\n"})
    try:
        m = json.loads(r["manifest"])
    except ValueError:
        m = None
    check("manifest is valid JSON with revision and env version",
          r["rc"] == 0 and m is not None and m.get("revision") == "svc-00042"
          and m.get("env_secret_version") == 9, f"{r['out']} {r['manifest'][:100]!r}")
    keys = {k["name"]: k for k in (m or {}).get("keys", [])}
    check("keys carry source; bundle values never appear",
          keys.get("LOG_LEVEL", {}).get("source") == "file"
          and keys.get("APP_VERSION", {}).get("source") == "generated"
          and "value" not in keys.get("DB_PASSWORD", {"value": 1}), str(keys))
    steps = load()["jobs"]["update"]["steps"]
    check("a step uploads the config-manifest artifact",
          any(s.get("with", {}).get("name") == "config-manifest" for s in steps))


def main():
    for fn in (input_cases, validate_cases, render_cases, pin_cases, apply_cases, manifest_cases):
        fn()
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
