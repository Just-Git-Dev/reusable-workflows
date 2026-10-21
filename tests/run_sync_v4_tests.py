#!/usr/bin/env python3
"""Red tests for the v4 `sync-bundle-key` contract (docs/sync-bundle-key.md).

Same method as run_step_tests.py: a named step's `run:` body is extracted from the workflow YAML
and executed under `bash -eo pipefail` against stubbed `gcloud` / `gh`. Written BEFORE the
implementation (v4 wave 1): every case here is expected to fail until the workflow grows the
step, input or behaviour it names.

Step names and the env-var names a step reads are the contract these tests pin; the docs fix the
behaviour but not those names, so they are listed in CONTRACT below and are what wave 2 must
implement (or the tests are amended in the same change).

Cases marked P1 depend on the unproven premise that an environment-scoped secret reaches a
cross-org reusable callee (plan premise P1); they encode the documented design only.

Usage:  python3 tests/run_sync_v4_tests.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
SYNC = WF / "sync-bundle-key.yml"
KEYPAIR = WF / "rotate-signing-keypair.yml"
WORKER = WF / "rotate-worker-signing-secret.yml"

# CONTRACT (invented names; docs describe behaviour only).
S0_STEP = "Guard environment branch policy"      # env: ENVIRONMENT REQUIRE_BRANCH_POLICY GH_TOKEN REPO
COMPUTE_STEP = "Compute new bundle"              # env: MODE SECRET_KEYS_FILE CONFIRM_REMOVED DRY_RUN
                                                 #      PAYLOAD_JSON STRICT_VALUES MIN_VALUE_LEN; /tmp/bundle.env
VALIDATE_STEP = "Validate payload"
ROLL_STEP = "Force new Cloud Run revision(s)"    # env: NEW_VERSION PIN_VERSIONS GITHUB_RUN_ID
KEEP_STEP = "Disable superseded bundle version(s)"  # env: NEW_VERSION KEEP_ENABLED_COUNT SERVICES_CSV
ENVPAYLOAD_STEP = "Build payload from environment secrets"  # P1; env: ALL_SECRETS_JSON SECRET_KEYS_FILE

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


def extract_step(workflow: Path, job: str, step_name: str):
    """Return the `run:` body of a named step, or None when the step does not exist."""
    doc = yaml.safe_load(workflow.read_text())
    for step in doc["jobs"][job]["steps"]:
        if step.get("name") == step_name and "run" in step:
            return step["run"]
    return None


def workflow_inputs():
    doc = yaml.safe_load(SYNC.read_text())
    on = doc.get("on") or doc.get(True)
    return on["workflow_call"]["inputs"], on["workflow_call"].get("secrets", {}), doc


def run_body(body, env, *, gcloud="", gh="", files=None):
    """Run a step body in a sandbox. /tmp is redirected; stubs log argv to `calls`."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        calls = tmp / "calls"
        calls.write_text("")
        for name, script in (("gcloud", gcloud), ("gh", gh)):
            p = stub / name
            p.write_text('#!/usr/bin/env bash\n'
                         f'echo "{name} $*" >> {calls}\n' + script + '\nexit 0\n')
            p.chmod(0o755)
        for rel, content in (files or {}).items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_text(content)
        e = dict(os.environ)
        e["PATH"] = f"{stub}:{e['PATH']}"
        e.update(GITHUB_STEP_SUMMARY=str(tmp / "summary"), GITHUB_OUTPUT=str(tmp / "out"),
                 BUNDLE_SECRET="app-secrets", GCP_PROJECT="p", GCP_REGION="r",
                 MOUNT_PATH="/secrets/app.env", SERVICES_CSV="svc")
        e.update(env)
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
             body.replace("/tmp/", f"{tmp}/")],
            capture_output=True, text=True, env=e, cwd=tmp)
        out = tmp / "out"
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "calls": calls.read_text(),
                "bundle": (tmp / "bundle.env").read_text() if (tmp / "bundle.env").exists() else "",
                "outputs": out.read_text() if out.exists() else ""}


def step_or_red(name, workflow, job, step):
    body = extract_step(workflow, job, step)
    if body is None:
        check(f"{name}: step '{step}' exists in {workflow.name}", False,
              "(step not found: not implemented yet)")
    return body


# --- inputs and defaults ------------------------------------------------------------------------

def input_cases():
    print("\nsync-bundle-key v4 · input contract")
    inputs, secrets, doc = workflow_inputs()
    want = {"mode": "replace", "strict_values": True, "pin_versions": True,
            "secret_keys_file": "deploy/secret-keys.txt", "confirm_removed": "",
            "require_branch_policy": True, "environment": "", "payload_source": "caller"}
    for k, v in want.items():
        check(f"input {k} exists with default {v!r}",
              k in inputs and inputs[k].get("default") == v, f"got {inputs.get(k)}")
    check("pin_versions default is the boolean true", inputs.get("pin_versions", {}).get("type") == "boolean")
    check("job sets environment from the input",
          doc["jobs"]["sync"].get("environment") == "${{ inputs.environment }}",
          f"got {doc['jobs']['sync'].get('environment')!r}")
    # P1-dependent: payload_json is only required for payload_source: caller.
    check("P1: payload_json is not required (payload_source: environment omits it)",
          secrets.get("payload_json", {}).get("required") is False,
          f"got {secrets.get('payload_json')}")


# --- S0 -----------------------------------------------------------------------------------------

def s0_cases():
    print("\nsync-bundle-key v4 · S0 environment guard")
    body = step_or_red("S0", SYNC, "sync", S0_STEP)
    if body is None:
        return
    env = {"ENVIRONMENT": "stage", "REQUIRE_BRANCH_POLICY": "true", "GH_TOKEN": "t",
           "REPO": "o/r"}

    def gh_env(policy):
        doc = json.dumps({"name": "stage", "deployment_branch_policy": policy})
        return f"cat <<'J'\n{doc}\nJ"

    r = run_body(body, env, gh=gh_env(None))
    check("S0 refuses an environment with a null branch policy", r["rc"] != 0, r["out"])
    r = run_body(body, env, gh=gh_env({"protected_branches": False, "custom_branch_policies": True}))
    check("S0 passes an environment with a branch policy", r["rc"] == 0, r["out"])
    check("S0 reads /environments/<env> of the repo",
          "repos/o/r/environments/stage" in r["calls"], r["calls"])
    r = run_body(body, {**env, "ENVIRONMENT": ""}, gh=gh_env(None))
    check("S0 is a no-op without an environment", r["rc"] == 0 and r["calls"] == "", r["out"])


# --- replace / merge ----------------------------------------------------------------------------

def mode_cases():
    print("\nsync-bundle-key v4 · mode: replace")
    body = step_or_red("replace", SYNC, "sync", COMPUTE_STEP)
    if body is None:
        return
    base = {"MODE": "replace", "SECRET_KEYS_FILE": "deploy/secret-keys.txt", "DRY_RUN": "false",
            "STRICT_VALUES": "true", "MIN_VALUE_LEN": "8", "CONFIRM_REMOVED": ""}
    keys = {"deploy/secret-keys.txt": "A\nB\n"}
    bundle = "A=old-a\nSTALE=gone-soon\n"
    payload = json.dumps({"B": "value-b-1"})

    def go(**kw):
        files = {**keys, **kw.pop("files", {})}
        env = {**base, "PAYLOAD_JSON": kw.pop("payload", payload), **kw}
        return run_body(body, env, files=files | {"bundle.env": bundle})

    r = go(CONFIRM_REMOVED="STALE")
    check("replace keeps listed current keys, overlays payload, drops unlisted",
          r["rc"] == 0 and r["bundle"].splitlines() == ["A=old-a", "B=value-b-1"],
          f"rc={r['rc']} bundle={r['bundle']!r} {r['out']}")
    r = go(payload=json.dumps({"A": "value-a-2"}))
    check("replace refuses a listed key absent from payload and bundle (B)",
          r["rc"] != 0 and "B" in r["out"], r["out"])
    r = go()
    check("replace refuses a live run that drops STALE without confirm_removed",
          r["rc"] != 0 and "STALE" in r["out"], r["out"])
    r = go(CONFIRM_REMOVED="STALE,A")
    check("confirm_removed must equal the dropped set EXACTLY (superset refused)",
          r["rc"] != 0, r["out"])
    r = go(CONFIRM_REMOVED="STALE")
    check("exact confirm_removed lets the drop through", r["rc"] == 0, r["out"])
    r = go(DRY_RUN="true", payload=json.dumps({"B": "SECRETVALUE99"}))
    check("dry run prints +added -removed =kept by NAME only",
          r["rc"] == 0 and "SECRETVALUE99" not in r["out"] and "old-a" not in r["out"]
          and re.search(r"\+\s*B", r["out"]) and re.search(r"-\s*STALE", r["out"])
          and re.search(r"=\s*A", r["out"]), r["out"])
    r = go(DRY_RUN="true")
    check("dry run needs no confirm_removed (it only reports)", r["rc"] == 0, r["out"])

    print("\nsync-bundle-key v4 · mode: merge (v3 behaviour)")
    r = go(MODE="merge")
    check("merge keeps unlisted keys and needs no list or confirm",
          r["rc"] == 0 and "STALE=gone-soon" in r["bundle"] and "B=value-b-1" in r["bundle"],
          r["out"])


def strict_cases():
    print("\nsync-bundle-key v4 · strict_values by default")
    inputs, _, _ = workflow_inputs()
    check("strict_values defaults true", inputs.get("strict_values", {}).get("default") is True)
    body = extract_step(SYNC, "sync", VALIDATE_STEP)
    if body is None:
        check("Validate step exists", False)
        return
    # The step must read the default from the workflow env, not hard-code false.
    doc_text = SYNC.read_text()
    check("Validate step is fed STRICT_VALUES from inputs.strict_values",
          re.search(r"STRICT_VALUES:\s*\$\{\{\s*inputs\.strict_values", doc_text) is not None)
    r = run_body(body, {"PAYLOAD_JSON": json.dumps({"K": ""}), "MIN_VALUE_LEN": "0",
                        "STRICT_VALUES": "true"})
    check("an empty value is refused under the strict default", r["rc"] != 0, r["out"])


# --- S5 roll, pinned ----------------------------------------------------------------------------

def roll_cases():
    print("\nsync-bundle-key v4 · S5 pinned roll")
    body = step_or_red("roll", SYNC, "sync", ROLL_STEP)
    if body is None:
        return
    env = {"NEW_VERSION": "8", "PIN_VERSIONS": "true", "GITHUB_RUN_ID": "4242",
           "SERVICES_CSV": "svc-a, svc-b"}
    r = run_body(body, env)
    check("roll succeeds", r["rc"] == 0, r["out"])
    updates = [c for c in r["calls"].splitlines() if "run services update" in c]
    check("one update per service", len(updates) == 2, r["calls"])
    check("roll pins the bundle to :N+1 (version number from NEW_VERSION), never :latest",
          all("--update-secrets=/secrets/app.env=app-secrets:8" in c for c in updates)
          and ":latest" not in r["calls"], r["calls"])
    check("roll stamps jgd_env_version and jgd_run labels",
          all("jgd_env_version=8" in c and "jgd_run=4242" in c for c in updates), r["calls"])
    r = run_body(body, {**env, "PIN_VERSIONS": "false"})
    check("pin_versions: false keeps the v3 :latest roll",
          "app-secrets:latest" in r["calls"], r["calls"])


# --- S6 keep-set --------------------------------------------------------------------------------

def revision(name, volume, version, mounted=True):
    """A Cloud Run v1 revision JSON: one secret volume pinning `version`."""
    mounts = [{"name": volume}] if mounted else []
    return {"metadata": {"name": name},
            "spec": {"volumes": [{"name": volume, "secret": {
                "secretName": "app-secrets", "items": [{"version": version, "path": "app.env"}]}}],
                "containers": [{"volumeMounts": mounts}]}}


def keep_cases():
    print("\nsync-bundle-key v4 · S6 keep-set")
    body = step_or_red("keep", SYNC, "sync", KEEP_STEP)
    if body is None:
        return

    def go(revs, enabled=("8", "7", "6", "5", "4"), keep="1"):
        rj = json.dumps(revs)
        gcloud = (
            'if [ "$2" = "versions" ] && [ "$3" = "list" ]; then\n'
            + "".join(f'  echo {v}\n' for v in enabled) + '  exit 0\nfi\n'
            'if [ "$2" = "revisions" ] && [ "$3" = "list" ]; then\n'
            f"  cat <<'J'\n{rj}\nJ\n  exit 0\nfi")
        # older gcloud arg layout is `gcloud secrets versions ...` ($2=versions);
        # `gcloud run revisions list` has revisions at $3: cover both.
        gcloud = gcloud.replace('[ "$2" = "revisions" ] && [ "$3" = "list" ]',
                                '[ "$3" = "revisions" ] && [ "$4" = "list" ]')
        r = run_body(body, {"NEW_VERSION": "8", "KEEP_ENABLED_COUNT": keep,
                            "SERVICES_CSV": "svc"}, gcloud=gcloud)
        disabled = sorted(re.findall(r"versions disable (\S+)", r["calls"]))
        return r, disabled

    # newest-first revisions: r3 -> 8 (just rolled), r2 pins 7, r1 pins 5, r0 pins 4 (3rd newest).
    revs = [revision("r3", "v", "8"), revision("r2", "v", "7"),
            revision("r1", "v", "5"), revision("r0", "v", "4")]
    r, d = go(revs)
    check("keeps N+1 and the pins of the two newest revisions; disables the rest (6, 4)",
          r["rc"] == 0 and d == ["4", "6"], f"disabled={d} {r['out']}")
    check("never destroys", "versions destroy" not in r["calls"], r["calls"])
    revs2 = [revision("r2", "v", "8"), revision("r1", "v", "7", mounted=True),
             {"metadata": {"name": "r1b"}, "spec": {"volumes": [
                 {"name": "orphan", "secret": {"secretName": "app-secrets",
                                               "items": [{"version": "6", "path": "x"}]}}],
              "containers": [{"volumeMounts": []}]}}]
    r, d = go(revs2, enabled=("8", "7", "6"))
    check("an orphan declared volume (no volumeMount) pins nothing: 6 is disabled",
          d == ["6"], f"disabled={d} {r['out']}")
    r, d = go(revs, keep="3")
    check("keep_enabled_count is a floor: the 3 newest (8,7,6) stay too -> only 4 disabled",
          d == ["4"], f"disabled={d}")


# --- three writers identical --------------------------------------------------------------------

def identical_cases():
    print("\nsync-bundle-key v4 · the three bundle writers share roll + keep-set bodies")
    for step in (ROLL_STEP, KEEP_STEP):
        bodies = {wf.name: extract_step(wf, job, step)
                  for wf, job in ((SYNC, "sync"), (KEYPAIR, "rotate"), (WORKER, "rotate"))}
        missing = [n for n, b in bodies.items() if b is None]
        check(f"'{step}' exists in all three writers", not missing, f"missing in {missing}")
        distinct = {b for b in bodies.values() if b is not None}
        check(f"'{step}' bodies are byte-identical across the three writers",
              len(distinct) == 1 and not missing, f"{len(distinct)} distinct bodies")


# --- P1: payload_source: environment ------------------------------------------------------------

def env_source_cases():
    # P1-DEPENDENT: encodes the documented design for payload_source: environment, which stays
    # UNPROVEN until a real dry run shows environment secrets reach a cross-org callee.
    print("\nsync-bundle-key v4 · payload_source: environment (P1-dependent, UNPROVEN premise)")
    body = step_or_red("P1 env payload", SYNC, "sync", ENVPAYLOAD_STEP)
    if body is None:
        return
    files = {"deploy/secret-keys.txt": "DB_PASSWORD\nREDIS_PASSWORD\n"}
    env = {"SECRET_KEYS_FILE": "deploy/secret-keys.txt"}
    r = run_body(body, {**env, "ALL_SECRETS_JSON": json.dumps(
        {"DB_PASSWORD": "pw-one-1", "REDIS_PASSWORD": "pw-two-2", "github_token": "x", "OTHER": "y"})},
        files=files)
    check("P1: builds a payload of exactly the listed keys (github_token, OTHER excluded)",
          r["rc"] == 0 and "github_token" not in r["outputs"] and "OTHER" not in r["outputs"]
          and "DB_PASSWORD" in r["outputs"], r["out"] + r["outputs"])
    r = run_body(body, {**env, "ALL_SECRETS_JSON": json.dumps({"DB_PASSWORD": "pw-one-1"})},
                 files=files)
    check("P1: a listed key with no environment secret is refused, naming the key only",
          r["rc"] != 0 and "REDIS_PASSWORD" in r["out"] and "pw-one-1" not in r["out"], r["out"])


def main():
    for fn in (input_cases, s0_cases, mode_cases, strict_cases, roll_cases, keep_cases,
               identical_cases, env_source_cases):
        fn()
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
