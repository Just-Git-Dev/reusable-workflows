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


def svc_env_json(version):
    """Live template whose bundle pin is an env-var secretKeyRef (key == version), no volume."""
    return json.dumps({"spec": {"template": {"spec": {"containers": [{"env": [{"name": "E",
            "valueFrom": {"secretKeyRef": {"name": "svc-env", "key": version}}}]}]}}}})


def _desc(js, rc=0, err=""):
    return ('if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n'
            + (f"  echo '{err}' >&2\n  exit {rc}\n" if rc else f"  cat <<'J'\n{js}\nJ\n  exit 0\n") + 'fi')


def guard_cases(body, run, check_fn, flag_envs, label):
    """Critic round 2 (4): with `env_secret` EMPTY the step still refuses a `*-env` bundle at
    :latest -- mounted by the live template or named by the caller's flags/secrets -- unless
    pin_env: false. Matches a MOUNT (the secret ref of a secrets flag), not a loose substring."""
    print(f"\n{label} . refuse a *-env bundle at :latest even without env_secret")
    env = {"ENV_SECRET": "", "ENV_MOUNT_PATH": "", "PIN_ENV": "true"}
    r = run(body, env, gcloud=_desc(svc_json("latest")))
    check_fn(f"{label}: live template mounts svc-env at :latest, env_secret empty -> refused",
             r["rc"] != 0 and "latest" in r["out"] and "::error::" in r["out"], r["out"])
    r = run(body, env, gcloud=_desc(svc_env_json("latest")))
    check_fn(f"{label}: the live :latest mount via an env secretKeyRef is refused too",
             r["rc"] != 0 and "::error::" in r["out"], r["out"])
    r = run(body, {**env, "PIN_ENV": "false"}, gcloud=_desc(svc_json("latest")))
    check_fn(f"{label}: pin_env: false lets the live :latest mount through, with a warning",
             r["rc"] == 0 and "::warning::" in r["out"], r["out"])
    r = run(body, env, gcloud=_desc(svc_json("7")))
    check_fn(f"{label}: a numeric live pin is not refused", r["rc"] == 0, r["out"])
    r = run(body, env, gcloud=_desc(svc_json("latest").replace("svc-env", "db-pass")))
    check_fn(f"{label}: a non-*-env secret at :latest is not this guard's business", r["rc"] == 0, r["out"])
    r = run(body, env, gcloud=_desc("", 1, "ERROR: (gcloud.run.services.describe) NOT_FOUND: Cannot find service [svc]"))
    check_fn(f"{label}: no service yet (NOT_FOUND) is not a refusal", r["rc"] == 0, r["out"])
    r = run(body, env, gcloud=_desc("", 1, "ERROR: (gcloud.run.services.describe) PERMISSION_DENIED 403"))
    check_fn(f"{label}: a describe error that is not NOT_FOUND refuses (fail closed)",
             r["rc"] != 0 and "::error::" in r["out"], r["out"])
    for k in flag_envs:
        r = run(body, {**env, k: "--set-secrets=/x/app.env=other-env:latest"}, gcloud=_desc(svc_json("7")))
        check_fn(f"{label}: {k} naming other-env:latest is refused", r["rc"] != 0 and "latest" in r["out"], r["out"])
        r = run(body, {**env, k: "--update-secrets /x/app.env=other-env:latest,/y=db:3"}, gcloud=_desc(svc_json("7")))
        check_fn(f"{label}: {k} with a space-separated --update-secrets list is refused", r["rc"] != 0, r["out"])
        r = run(body, {**env, k: "--set-secrets=/x/app.env=other-env:7"}, gcloud=_desc(svc_json("7")))
        check_fn(f"{label}: {k} naming other-env:7 is not refused", r["rc"] == 0, r["out"])
        if k != "SECRETS":
            # Critic round 3 (V3/V5): the flag and its value on separate lines are one flag.
            r = run(body, {**env, k: "--update-secrets\n/app/.env=svc-env:latest"}, gcloud=_desc(svc_json("7")))
            check_fn(f"{label}: {k} with --update-secrets and its value on the next line is refused",
                     r["rc"] != 0 and "latest" in r["out"], r["out"])
        if k == "SECRETS":
            continue          # the `secrets` list is mounts only; no other flag's value lives in it
        r = run(body, {**env, k: "--set-env-vars=NOTE=a-env:latest"}, gcloud=_desc(svc_json("7")))
        check_fn(f"{label}: {k} with an env-var VALUE ending -env:latest is not a mount (not refused)",
                 r["rc"] == 0, r["out"])


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
    # Critic round 3 (V6): a CUR describe error that is not NOT_FOUND refuses (fail closed).
    g403 = ('if [ "$3" = "services" ] && [ "$4" = "describe" ]; then echo "PERMISSION_DENIED 403" >&2; exit 1; fi\n'
            'if [ "$2" = "versions" ] && [ "$3" = "list" ]; then echo projects/1/secrets/svc-env/versions/9; exit 0; fi')
    r = run_body(body, env, gcloud=g403)
    check("V6: a CUR describe 403 with env_secret refuses (fail closed), no pin output",
          r["rc"] != 0 and "env_version" not in r["outputs"], f"{r['out']} {r['outputs']}")
    gnf = g403.replace("PERMISSION_DENIED 403", "NOT_FOUND: Cannot find service")
    r = run_body(body, env, gcloud=gnf)
    check("V6: a CUR describe NOT_FOUND (no service yet) pins the newest ENABLED version",
          r["rc"] == 0 and r["outputs"].get("env_version") == "9", f"{r['out']} {r['outputs']}")
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
    # P1: the live pin may be an env-var secretKeyRef instead of a volume item.
    r = run_body(body, env, gcloud=gcloud("latest").replace(svc_json("latest"), svc_env_json("5")))
    check("P1: a live numeric pin held via env[].valueFrom.secretKeyRef (5) is kept, not moved to 9",
          r["rc"] == 0 and r["outputs"].get("env_version") == "5", f"{r['out']} {r['outputs']}")
    # 7c: only a bundle MOUNT is refused, not any '-env:latest' text.
    r = run_body(body, {**env, "DEPLOY_FLAGS": "--set-env-vars=NOTE=a-env:latest"}, gcloud=gcloud("5"))
    check("7c: an env-var value ending -env:latest is not a mount (not refused)", r["rc"] == 0, r["out"])


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
    # Critic round 2 (5): the describe fallback fails CLOSED. Only a definite "no label" (a
    # successful describe, or the service not existing yet) is "no baseline".
    for why, err in (("403", "ERROR: (gcloud.run.services.describe) PERMISSION_DENIED: 403"),
                     ("transient", "ERROR: (gcloud.run.services.describe) UNAVAILABLE: try again")):
        g = f'if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n  echo \'{err}\' >&2\n  exit 1\nfi'
        r = run_body(body, env, gh=gh, gcloud=g)
        check(f"a describe error ({why}) in the label fallback refuses (fail closed), never 'no baseline'",
              r["rc"] != 0 and "::error::" in r["out"], r["out"])
    g = ('if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n'
         "  echo 'ERROR: (gcloud.run.services.describe) NOT_FOUND: Cannot find service [svc]' >&2\n  exit 1\nfi")
    r = run_body(body, env, gh=gh, gcloud=g)
    check("a service that does not exist yet (NOT_FOUND) is a definite 'no baseline': allowed",
          r["rc"] == 0 and "::notice::" in r["out"], r["out"])


REF = "Resolve tag + image ref"
VERIFY = "Verify prebuilt image"
DIGEST = "r-docker.pkg.dev/p/repo/img@sha256:" + "a" * 64
REF_ENV = {"IN_TAG": "v1.2.3", "FALLBACK_TAG": "", "REQUIRE_SEMVER": "true", "REGION": "r",
           "PROJECT": "p", "GAR_REPO": "repo", "IMAGE_NAME": "img", "ALSO_LATEST": "false",
           "BUILD_ONLY": "false", "IMAGE": "", "DOCKER_TARGET": "", "BUILD_ARGS": ""}


def image_cases():
    print("\ndeploy-cloud-run v4.1 · prebuilt image input")
    doc = yaml.safe_load(DEPLOY.read_text())
    inputs = (doc.get("on") or doc.get(True))["workflow_call"]["inputs"]
    check("input image exists, default ''", inputs.get("image", {}).get("default") == "",
          f"got {inputs.get('image')}")
    steps = doc["jobs"]["deploy"]["steps"]
    by = {s.get("name"): s for s in steps}
    for n in ("Configure docker for Artifact Registry", "Build & push image"):
        check(f"'{n}' is skipped when image is set", "inputs.image == ''" in str(by.get(n, {}).get("if")),
              str(by.get(n, {}).get("if")))
    bx = [s for s in steps if "setup-buildx-action" in str(s.get("uses"))]
    check("setup-buildx is skipped when image is set",
          bool(bx) and "inputs.image == ''" in str(bx[0].get("if")), str(bx[:1]))
    v = by.get(VERIFY, {})
    check("Verify prebuilt image runs only when image is set, id verify",
          "inputs.image != ''" in str(v.get("if")) and v.get("id") == "verify", str(v))
    man = by.get(MANIFEST, {})
    check("manifest IMAGE_DIGEST falls back to verify output",
          man.get("env", {}).get("IMAGE_DIGEST") ==
          "${{ steps.build.outputs.digest || steps.verify.outputs.digest }}", str(man.get("env")))
    body = step_or_red("image", REF)
    if body is None:
        return
    r = run_body(body, {**REF_ENV, "IMAGE": DIGEST})
    check("digest ref accepted; image output is the input; tag still resolved",
          r["rc"] == 0 and r["outputs"].get("image") == DIGEST and r["outputs"].get("tag") == "v1.2.3",
          f"{r['out']} {r['outputs']}")
    r = run_body(body, REF_ENV)
    check("default image '' still builds the tag ref",
          r["rc"] == 0 and r["outputs"].get("image") == "r-docker.pkg.dev/p/repo/img:v1.2.3", str(r["outputs"]))
    for label, ref in (("tag ref", "r-docker.pkg.dev/p/repo/img:v1.2.3"),
                       ("short digest", "r-docker.pkg.dev/p/repo/img@sha256:abc"),
                       ("uppercase hex", "r-docker.pkg.dev/p/repo/img@sha256:" + "A" * 64),
                       ("non-GAR host", "ghcr.io/x/img@sha256:" + "a" * 64),
                       ("F8 one path segment", "r-docker.pkg.dev/img@sha256:" + "a" * 64),
                       ("F8 two path segments", "r-docker.pkg.dev/p/img@sha256:" + "a" * 64),
                       ("F8 empty segment", "r-docker.pkg.dev/p//img@sha256:" + "a" * 64),
                       ("F8 name:tag@sha256", "r-docker.pkg.dev/p/repo/img:v1@sha256:" + "a" * 64)):
        r = run_body(body, {**REF_ENV, "IMAGE": ref})
        check(f"{label} refused, error names image",
              r["rc"] != 0 and "::error::" in r["out"] and "image" in r["out"], r["out"])
    r = run_body(body, {**REF_ENV, "IMAGE": DIGEST, "BUILD_ONLY": "true"})
    check("image + build_only refused", r["rc"] != 0 and "build_only" in r["out"], r["out"])
    r = run_body(body, {**REF_ENV, "IMAGE": DIGEST, "ALSO_LATEST": "true", "BUILD_ARGS": "A=1"})
    check("build-only inputs ignored with a notice listing them",
          r["rc"] == 0 and "::notice::" in r["out"] and "also_tag_latest" in r["out"]
          and "build_args" in r["out"] and "docker_target" not in r["out"], r["out"])
    vb = step_or_red("verify", VERIFY)
    if vb is None:
        return
    r = run_body(vb, {"IMAGE": DIGEST}, gcloud='echo "sha256:' + "a" * 64 + '"')
    check("verify describes the digest and emits it",
          r["rc"] == 0 and "artifacts docker images describe" in r["calls"] and DIGEST in r["calls"]
          and r["outputs"].get("digest") == "sha256:" + "a" * 64, f"{r['out']} {r['calls']} {r['outputs']}")
    r = run_body(vb, {"IMAGE": DIGEST}, gcloud='echo "NOT_FOUND" >&2; exit 1')
    check("verify fails the run when the digest is not in Artifact Registry",
          r["rc"] != 0 and not r["outputs"].get("digest"), r["out"])
    r = run_body(vb, {"IMAGE": DIGEST}, gcloud='true')
    check("verify fails on an empty digest answer", r["rc"] != 0, r["out"])


PUBLIC_STEP = "Check public access"


def _policy_stub(policy=None, fail=False):
    if fail:
        return ('if [ "$1 $2 $3" = "run services get-iam-policy" ]; then '
                'echo "ERROR: (gcloud.run.services.get-iam-policy) PERMISSION_DENIED" >&2; exit 1; fi')
    return ('if [ "$1 $2 $3" = "run services get-iam-policy" ]; then cat <<\'JSON\'\n'
            + json.dumps(policy) + '\nJSON\nfi')


def public_cases():
    # v5.1.0 (owner Q2, 2026-10-23): `--allow-unauthenticated` is checked against the real policy
    # after the deploy; gcloud's warning wording is never grepped
    print("\ndeploy-cloud-run v5.1 · read-back of --allow-unauthenticated")
    doc = yaml.safe_load(DEPLOY.read_text())
    names = [s.get("name") for s in doc["jobs"]["deploy"]["steps"]]
    step = next((s for s in doc["jobs"]["deploy"]["steps"] if s.get("name") == PUBLIC_STEP), None)
    check(f"step '{PUBLIC_STEP}' exists", step is not None, "(not implemented yet)")
    if step is None:
        return
    # critic: a failing check must not skip the Deployment marker / manifest / URL after the deploy
    check("it is the job's last step", names[-1] == PUBLIC_STEP, names)
    cond = str(step.get("if", ""))
    check("it is skipped on dry_run and build_only",
          "!inputs.dry_run" in cond and "!inputs.build_only" in cond, cond)
    body = step["run"]
    public = {"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]},
                           {"role": "roles/run.developer", "members": ["serviceAccount:d@p.iam"]}]}
    private = {"bindings": [{"role": "roles/run.developer", "members": ["serviceAccount:d@p.iam"]}]}
    wrong_role = {"bindings": [{"role": "roles/run.viewer", "members": ["allUsers"]}]}
    flags = "--memory=512Mi\n--allow-unauthenticated\n"

    def go(policy=None, fail=False, mode="deploy", deploy_flags=flags, extra=""):
        return run_body(body, {"MODE": mode, "DEPLOY_FLAGS": deploy_flags, "EXTRA": extra},
                        gcloud=_policy_stub(policy, fail))

    r = go(public)
    check("flag + allUsers invoker held: passes", r["rc"] == 0, r["out"])
    check("flag + held: reads the policy of THIS service once",
          r["calls"].splitlines() == ["gcloud run services get-iam-policy svc --project=p --region=r "
                                      "--format=json"], r["calls"])
    r = go(private)
    check("flag + invoker missing: fails", r["rc"] != 0, r["out"])
    check("flag + invoker missing: message names F7 `public: true`",
          "public: true" in r["out"] and "repos-deploy-scope" in r["out"], r["out"])
    r = go(wrong_role)
    check("flag + allUsers with another role only: fails", r["rc"] != 0, r["out"])
    r = go(fail=True)
    check("flag + unreadable policy: fails (never passes on an unread policy)", r["rc"] != 0, r["out"])
    r = go(public, deploy_flags="", extra="--allow-unauthenticated --cpu=1")
    check("legacy extra_deploy_flags carrying the flag: policy read", "get-iam-policy" in r["calls"],
          r["calls"] or r["out"])
    r = go(private, deploy_flags="", extra="--cpu=1 --allow-unauthenticated")
    check("legacy flag + invoker missing: fails", r["rc"] != 0, r["out"])
    r = go(private, deploy_flags="--no-allow-unauthenticated\n--allow-unauthenticated\n")
    check("--no-… then --allow-…: the last one wins, policy read, fails", r["rc"] != 0
          and "get-iam-policy" in r["calls"], (r["rc"], r["calls"]))
    for label, kw in (("flag absent", {"deploy_flags": "--memory=512Mi\n"}),
                      ("--allow-… then --no-…: the last one wins",
                       {"deploy_flags": "--allow-unauthenticated\n--no-allow-unauthenticated\n"}),
                      ("--allow-… in deploy_flags, --no-… in the legacy string after it",
                       {"extra": "--no-allow-unauthenticated"}),
                      ("only --no-allow-unauthenticated", {"deploy_flags": "--no-allow-unauthenticated\n"}),
                      ("update-image ignores deploy flags", {"mode": "update-image"})):
        r = go(private, **kw)
        check(f"{label}: passes with no policy read", r["rc"] == 0 and r["calls"] == "",
              (r["rc"], r["calls"], r["out"][:200]))


def main():
    for fn in (input_cases, image_cases, render_cases, pin_cases, label_cases, manifest_cases, forward_cases,
               public_cases):
        fn()
    pin = extract_step(PIN)
    if pin is not None:
        guard_cases(pin, run_body, check, ("DEPLOY_FLAGS", "EXTRA"), "deploy-cloud-run")
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
