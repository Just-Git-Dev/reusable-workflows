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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from action_steps import ACTIONS, action_steps, extract_action_step, job_steps  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
SYNC = WF / "sync-bundle-key.yml"
ACTION = ACTIONS / "sync-bundle-key"             # the single source of truth; SYNC is a thin wrapper
KEYPAIR = WF / "rotate-signing-keypair.yml"
WORKER = WF / "rotate-worker-signing-secret.yml"

# CONTRACT (invented names; docs describe behaviour only).
S0_STEP = "Guard environment branch policy"      # env: ENVIRONMENT REQUIRE_BRANCH_POLICY GH_TOKEN REPO
COMPUTE_STEP = "Compute new bundle"              # env: REMOVE_KEYS DRY_RUN
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
    """Return the `run:` body of a named step, or None when the step does not exist.

    A wrapper job (sync-bundle-key.yml) resolves to its action's steps, and a step that runs a
    script beside action.yml yields the script body (tests/action_steps.py).
    """
    for step in job_steps(workflow, job):
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
    want = {"strict_values": True, "pin_versions": True,
            "secret_keys_file": "deploy/secret-keys.txt", "remove_keys": "",
            "require_branch_policy": True, "environment": "", "payload_source": "caller"}
    for k, v in want.items():
        check(f"input {k} exists with default {v!r}",
              k in inputs and inputs[k].get("default") == v, f"got {inputs.get(k)}")
    for gone in ("mode", "confirm_removed"):
        check(f"v5: input {gone} no longer exists on the wrapper workflow", gone not in inputs)
    check("pin_versions default is the boolean true", inputs.get("pin_versions", {}).get("type") == "boolean")
    check("job sets environment from the input",
          doc["jobs"]["sync"].get("environment") == "${{ inputs.environment }}",
          f"got {doc['jobs']['sync'].get('environment')!r}")
    # P1-dependent: payload_json is only required for payload_source: caller.
    check("P1: payload_json is not required (payload_source: environment omits it)",
          secrets.get("payload_json", {}).get("required") is False,
          f"got {secrets.get('payload_json')}")


# --- m11: an unknown payload_source fails instead of falling back to caller ---------------------

def source_cases():
    print("\nsync-bundle-key v4 . payload_source validation")
    body = step_or_red("source check", SYNC, "sync", "Validate payload_source")
    if body is None:
        return
    for v, ok in (("caller", True), ("environment", True), ("enviroment", False), ("", False)):
        r = run_body(body, {"PAYLOAD_SOURCE": v})
        check(f"payload_source {v!r} -> {'accepted' if ok else 'refused'}",
              (r["rc"] == 0) == ok, r["out"])


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
    # v5.0.0: the sync is merge-only. The v4 replace-mode cases (limit to the listed keys, refuse an
    # unconfirmed drop, confirm_removed must equal the dropped set) are DELETED: the behaviour and
    # both inputs are gone. The merge case is kept and extended.
    print("\nsync-bundle-key v5 · merge-only, explicit remove_keys")
    body = step_or_red("merge", SYNC, "sync", COMPUTE_STEP)
    if body is None:
        return
    base = {"DRY_RUN": "false", "REMOVE_KEYS": ""}
    bundle = "A=old-a\nSTALE=gone-soon\nB=old-b\n"
    payload = json.dumps({"B": "value-b-1", "C": "value-c-1"})

    def go(**kw):
        env = {**base, "PAYLOAD_JSON": kw.pop("payload", payload), **kw}
        return run_body(body, env, files={"bundle.env": kw.pop("bundle", bundle)})

    r = go()
    check("an unlisted key in the current bundle survives byte-for-byte; payload updates/adds",
          r["rc"] == 0 and r["bundle"].splitlines() == ["A=old-a", "STALE=gone-soon", "B=value-b-1", "C=value-c-1"],
          f"rc={r['rc']} bundle={r['bundle']!r} {r['out']}")
    r = go(REMOVE_KEYS="STALE")
    check("remove_keys removes exactly that key",
          r["rc"] == 0 and r["bundle"].splitlines() == ["A=old-a", "B=value-b-1", "C=value-c-1"],
          f"rc={r['rc']} bundle={r['bundle']!r} {r['out']}")
    r = go(REMOVE_KEYS=" STALE , ,A ")
    check("remove_keys: names trimmed, empties ignored, several allowed",
          r["rc"] == 0 and r["bundle"].splitlines() == ["B=value-b-1", "C=value-c-1"], r["bundle"] + r["out"])
    r = go(REMOVE_KEYS="stale")
    check("remove_keys is case-sensitive (stale does not remove STALE; warns it is absent)",
          r["rc"] == 0 and "STALE=gone-soon" in r["bundle"] and "::warning::" in r["out"] and "stale" in r["out"],
          r["out"])
    r = go(REMOVE_KEYS="B")
    check("remove_keys naming a payload key is refused, nothing written",
          r["rc"] != 0 and "B" in r["out"] and r["bundle"] == bundle, r["out"])
    r = go(REMOVE_KEYS="GONE_ALREADY")
    check("an absent remove key warns naming it and is a no-op",
          r["rc"] == 0 and "::warning::" in r["out"] and "GONE_ALREADY" in r["out"]
          and r["bundle"].startswith("A=old-a\nSTALE=gone-soon\n"), r["out"])
    for bad in ("A.*", "A B", "$(id)", "A;B"):
        r = go(REMOVE_KEYS=bad)
        check(f"injection-shaped remove_keys {bad!r} is refused by the pattern check, bundle untouched",
              r["rc"] != 0 and r["bundle"] == bundle, r["out"])
    r = go(REMOVE_KEYS="A\nSTALE")
    check("remove_keys also accepts newline separators",
          r["rc"] == 0 and r["bundle"].splitlines() == ["B=value-b-1", "C=value-c-1"], r["bundle"] + r["out"])
    r = go(bundle="  A=indented\nexport STALE=x\n", REMOVE_KEYS="A,STALE")
    check("a key only matching after spaces/export gets an accurate warning, matching not widened",
          r["rc"] == 0 and "no line starting" in r["out"] and "A=indented" in r["bundle"], r["out"] + r["bundle"])
    r = go(REMOVE_KEYS="BAD-KEY")
    check("an invalid remove key name is refused", r["rc"] != 0 and "BAD-KEY" in r["out"], r["out"])
    r = go(bundle="# note\nA=old-a\n\nSTALE=x=y\n")
    check("comments, blank lines and values holding = are kept as they were",
          r["rc"] == 0 and r["bundle"].startswith("# note\nA=old-a\n\nSTALE=x=y\n"), r["bundle"])
    r = go(DRY_RUN="true", payload=json.dumps({"B": "SECRETVALUE99", "NEW": "SECRETVALUE98"}), REMOVE_KEYS="STALE")
    check("dry run prints +added ~updated -removed by NAME only, kept as a count",
          r["rc"] == 0 and "SECRETVALUE9" not in r["out"] and "old-a" not in r["out"]
          and re.search(r"\+\s*NEW", r["out"]) and re.search(r"~\s*B", r["out"])
          and re.search(r"-\s*STALE", r["out"]) and re.search(r"kept.*\b1\b|\b1\b.*kept", r["out"]), r["out"])
    r = go(payload=json.dumps({"A": "old-a"}))
    check("an identical payload with no removals leaves the bundle unchanged",
          r["rc"] == 0 and r["bundle"] == bundle, r["bundle"])


def strict_cases():
    print("\nsync-bundle-key v4 · strict_values by default")
    inputs, _, _ = workflow_inputs()
    check("strict_values defaults true", inputs.get("strict_values", {}).get("default") is True)
    body = extract_step(SYNC, "sync", VALIDATE_STEP)
    if body is None:
        check("Validate step exists", False)
        return
    # The step must read the default from the workflow env, not hard-code false.
    doc_text = (ACTION / "action.yml").read_text() if (ACTION / "action.yml").exists() else ""
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
    # v3 keypair-rotator parity: bootstrap tolerates a service that does not exist yet.
    fail = 'if [ "$1 $2" = "run services" ]; then exit 1; fi'
    r = run_body(body, {**env, "BOOTSTRAP": "true"}, gcloud=fail)
    check("bootstrap=true: a failed roll warns and exits 0",
          r["rc"] == 0 and "::warning::" in r["out"], r["out"])
    r = run_body(body, {**env, "BOOTSTRAP": "true", "SERVICES_CSV": " , "})
    check("bootstrap=true: zero services warns and exits 0",
          r["rc"] == 0 and "::warning::" in r["out"], r["out"])
    r = run_body(body, {**env, "BOOTSTRAP": "false"}, gcloud=fail)
    check("bootstrap=false: a failed roll exits 1", r["rc"] == 1, r["out"])
    r = run_body(body, {**env, "BOOTSTRAP": "false", "SERVICES_CSV": " , "})
    check("bootstrap=false: zero services exits 1", r["rc"] == 1, r["out"])
    r = run_body(body, {**env, "SERVICES_CSV": "svc-a"}, gcloud=fail)
    check("BOOTSTRAP unset (sync-bundle-key) behaves as false: failed roll exits 1",
          r["rc"] == 1, r["out"])


# --- S6 keep-set --------------------------------------------------------------------------------

def revision(name, volume, version, mounted=True):
    """A Cloud Run v1 revision JSON: one secret volume pinning `version`."""
    mounts = [{"name": volume}] if mounted else []
    return {"metadata": {"name": name},
            "spec": {"volumes": [{"name": volume, "secret": {
                "secretName": "app-secrets", "items": [{"key": version, "path": "app.env"}]}}],
                "containers": [{"volumeMounts": mounts}]}}


def keep_cases():
    print("\nsync-bundle-key v4 · S6 keep-set")
    body = step_or_red("keep", SYNC, "sync", KEEP_STEP)
    if body is None:
        return

    def go(revs, enabled=("8", "7", "6", "5", "4"), keep="1", traffic=None, others=None):
        """`traffic`: the service's status.traffic (default 100% on the newest revision).
        `others`: {service: [revisions]} the project holds beyond services_csv."""
        others = others or {}
        top = revs[0]["metadata"]["name"]
        svc_json = json.dumps({"status": {"latestReadyRevisionName": top, "traffic": traffic
                               or [{"revisionName": top, "percent": 100}]}})
        # REAL shape: `secrets versions list --format=value(name)` prints FULL resource paths.
        gcloud = (
            'if [ "$1" = "secrets" ] && [ "$2" = "versions" ] && [ "$3" = "list" ]; then\n'
            + "".join(f'  echo projects/1/secrets/app-secrets/versions/{v}\n' for v in enabled)
            + '  exit 0\nfi\n'
            'if [ "$3" = "services" ] && [ "$4" = "list" ]; then\n'
            + "".join(f'  echo {n}\n' for n in others) + '  exit 0\nfi\n'
            'if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n'
            f"  cat <<'J'\n{svc_json}\nJ\n  exit 0\nfi\n"
            'if [ "$3" = "revisions" ] && [ "$4" = "list" ]; then\n'
            + "".join(f"  if [ \"$5\" = \"--service={n}\" ]; then cat <<'J'\n{json.dumps(rv)}\nJ\n"
                      "  exit 0; fi\n" for n, rv in others.items())
            + f"  cat <<'J'\n{json.dumps(revs)}\nJ\n  exit 0\nfi")
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
                                               "items": [{"key": "6", "path": "x"}]}}],
              "containers": [{"volumeMounts": []}]}}]
    r, d = go(revs2, enabled=("8", "7", "6"))
    check("an orphan declared volume (no volumeMount) pins nothing: 6 is disabled",
          d == ["6"], f"disabled={d} {r['out']}")
    # M4(a): a revision still taking traffic keeps its pin however old it is (post-rollback state).
    r, d = go(revs, traffic=[{"revisionName": "r0", "percent": 100}])
    check("a revision with traffic > 0 keeps its pin even when 4th newest (4 kept)",
          r["rc"] == 0 and d == ["6"], f"disabled={d} {r['out']}")
    r, d = go(revs, traffic=[{"revisionName": "r3", "percent": 50}, {"revisionName": "r0", "percent": 0}])
    check("a 0% traffic entry pins nothing", d == ["4", "6"], f"disabled={d}")
    # M4(c): consumers are scanned project-wide, not only services_csv.
    other = [{"metadata": {"name": "o1"}, "spec": {"volumes": [{"name": "v", "secret": {
        "secretName": "app-secrets", "items": [{"key": "6", "path": "x"}]}}],
        "containers": [{"volumeMounts": [{"name": "v"}]}]}}]
    r, d = go(revs, others={"other-svc": other})
    check("a bundle consumer NOT in services_csv keeps its pin (6 kept)",
          r["rc"] == 0 and d == ["4"], f"disabled={d} {r['out']}")
    r, d = go(revs, keep="3")
    check("keep_enabled_count is a floor: the 3 newest (8,7,6) stay too -> only 4 disabled",
          d == ["4"], f"disabled={d}")


# --- M3: a rotator's rollback never disables a version a live revision pins ----------------------

ROLLBACK_STEP = "Roll back the new SM version on failure"


def rollback_cases():
    print("\nrotators . M3 roll-back-on-failure refuses to disable a pinned version")
    for wf in (KEYPAIR, WORKER):
        body = extract_step(wf, "rotate", ROLLBACK_STEP)
        if body is None:
            check(f"{wf.name}: rollback step exists", False)
            continue

        def go(pin):
            rv = [{"metadata": {"name": "r2"}, "spec": {"volumes": [{"name": "v", "secret": {
                "secretName": "app-secrets", "items": [{"key": pin, "path": "x"}]}}],
                "containers": [{"volumeMounts": [{"name": "v"}]}]}}]
            svc = {"status": {"latestReadyRevisionName": "r2",
                              "traffic": [{"revisionName": "r2", "percent": 100}]}}
            gcloud = (
                'if [ "$2" = "versions" ] && [ "$3" = "access" ]; then echo content; exit 0; fi\n'
                'if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n'
                f"  cat <<'J'\n{json.dumps(svc)}\nJ\n  exit 0\nfi\n"
                'if [ "$3" = "revisions" ] && [ "$4" = "list" ]; then\n'
                f"  cat <<'J'\n{json.dumps(rv)}\nJ\n  exit 0\nfi")
            return run_body(body, {"NEW_VERSION": "8", "CUR_VERSION": "7"}, gcloud=gcloud)

        r = go("8")
        check(f"{wf.name}: N+1 pinned by a live revision -> NOT disabled, loud failure",
              "versions disable" not in r["calls"] and r["rc"] != 0, r["calls"] + r["out"])
        r = go("7")
        check(f"{wf.name}: nothing pins N+1 -> disabled as before",
              r["rc"] == 0 and "versions disable 8" in r["calls"], r["calls"] + r["out"])


# --- critic round 2: template pin, secretKeyRef pins, named traffic revisions, all regions ---------

def env_revision(name, version, secret="app-secrets"):
    """A revision whose only pin is an env-var secretKeyRef (key == the version)."""
    return {"metadata": {"name": name}, "spec": {"containers": [{"env": [{"name": "ENVF",
            "valueFrom": {"secretKeyRef": {"name": secret, "key": version}}}]}]}}


def round2_stub(svc, revs=None, named=None, others=None, jobs=None, versions=("8", "7", "6", "5", "4")):
    """gcloud stub. `svc` = service describe JSON for every service; `revs` = {service: revision
    list}; `named` = {revision name: describe JSON}; `others` = [(service, region)] the list prints
    tab-separated beyond services_csv; `jobs` = [(job, region, describe JSON)]."""
    revs, named, others = revs or {}, named or {}, others or []
    g = ('if [ "$1" = "secrets" ] && [ "$2" = "versions" ] && [ "$3" = "list" ]; then\n'
         + "".join(f"  echo projects/1/secrets/app-secrets/versions/{v}\n" for v in versions)
         + '  exit 0\nfi\n'
         'if [ "$2" = "versions" ] && [ "$3" = "access" ]; then echo content; exit 0; fi\n'
         'if [ "$3" = "services" ] && [ "$4" = "list" ]; then\n'
         + "".join(f'  printf "%s\\t%s\\n" {n} {rg}\n' for n, rg in others) + '  exit 0\nfi\n'
         'if [ "$3" = "services" ] && [ "$4" = "describe" ]; then\n'
         f"  cat <<'J'\n{json.dumps(svc)}\nJ\n  exit 0\nfi\n")
    for rn, doc in named.items():
        g += (f'if [ "$3" = "revisions" ] && [ "$4" = "describe" ] && [ "$5" = "{rn}" ]; then '
              f"cat <<'J'\n{json.dumps(doc)}\nJ\n exit 0; fi\n")
    for s, rv in revs.items():
        g += (f'if [ "$3" = "revisions" ] && [ "$4" = "list" ] && [ "$5" = "--service={s}" ]; then '
              f"cat <<'J'\n{json.dumps(rv)}\nJ\n exit 0; fi\n")
    if revs:
        first = next(iter(revs.values()))
        g += (f'if [ "$3" = "revisions" ] && [ "$4" = "list" ]; then cat <<\'J\'\n'
              f'{json.dumps(first)}\nJ\n exit 0; fi\n')
    if jobs:
        g += 'if [ "$3" = "jobs" ] && [ "$4" = "list" ]; then\n' + "".join(
            f'  printf "%s\\t%s\\n" {n} {rg}\n' for n, rg, _ in jobs) + '  exit 0\nfi\n'
        for n, rg, doc in jobs:
            g += (f'if [ "$3" = "jobs" ] && [ "$4" = "describe" ] && [ "$5" = "{n}" ]; then '
                  f"cat <<'J'\n{json.dumps(doc)}\nJ\n exit 0; fi\n")
    return g


def round2_keep_cases():
    print("\nrotators + sync . critic round 2 keep-set (secretKeyRef pins, named traffic, regions)")
    svc = {"status": {"latestReadyRevisionName": "r3", "traffic": [{"revisionName": "r3", "percent": 100}]}}
    newest = [revision("r3", "v", "8"), revision("r2", "v", "7"), revision("r1", "v", "6")]
    for wf, job in ((SYNC, "sync"), (KEYPAIR, "rotate"), (WORKER, "rotate")):
        body = extract_step(wf, job, KEEP_STEP)
        if body is None:
            check(f"{wf.name}: keep step exists", False)
            continue
        tag = wf.name

        def go(g, keep="1"):
            r = run_body(body, {"NEW_VERSION": "8", "KEEP_ENABLED_COUNT": keep}, gcloud=g)
            return r, sorted(re.findall(r"versions disable (\S+)", r["calls"]))

        r, d = go(round2_stub(svc, {"svc": newest, "other": [env_revision("o1", "5")]}, others=[("other", "r")]))
        check(f"{tag}: a pin held only via env[].valueFrom.secretKeyRef is kept (5 stays, only 4 disabled)",
              r["rc"] == 0 and d == ["4"], f"disabled={d} {r['out']}")
        # A traffic-holding revision beyond the newest-50 list is read BY NAME.
        old = {"status": {"latestReadyRevisionName": "r3", "traffic": [{"revisionName": "ancient", "percent": 100}]}}
        r, d = go(round2_stub(old, {"svc": newest}, named={"ancient": revision("ancient", "v", "5")}))
        check(f"{tag}: a traffic-holding revision missing from the newest-50 list is described by name (5 kept)",
              r["rc"] == 0 and d == ["4"] and "revisions describe ancient" in r["calls"], f"disabled={d} {r['calls']}")
        # A 0% entry with a tag is served at its tag URL: live.
        tagged = {"status": {"latestReadyRevisionName": "r3", "traffic": [
            {"revisionName": "r3", "percent": 100}, {"revisionName": "canary", "percent": 0, "tag": "canary"}]}}
        r, d = go(round2_stub(tagged, {"svc": newest}, named={"canary": revision("canary", "v", "4")}))
        check(f"{tag}: a 0% traffic entry with a tag keeps its pin (4 kept, only 5 disabled)",
              r["rc"] == 0 and d == ["5"], f"disabled={d} {r['out']}")
        # Consumers in every region the project uses, described in THEIR region.
        job_doc = {"spec": {"template": {"spec": {"template": {"spec": {
            "volumes": [{"name": "v", "secret": {"secretName": "app-secrets",
                                                 "items": [{"key": "4", "path": "x"}]}}],
            "containers": [{"volumeMounts": [{"name": "v"}]}]}}}}}}
        r, d = go(round2_stub(svc, {"svc": newest, "eu-svc": [revision("e1", "v", "5")]},
                              others=[("eu-svc", "europe-west1")], jobs=[("eu-job", "europe-west1", job_doc)]))
        check(f"{tag}: a service and a job in another region keep their pins (5 and 4 stay)",
              r["rc"] == 0 and d == [], f"disabled={d} {r['out']}")
        check(f"{tag}: the other-region service is described with --region=europe-west1",
              re.search(r"services describe eu-svc .*--region=europe-west1", r["calls"]) is not None, r["calls"])
        check(f"{tag}: services/jobs are listed across all regions (no --region on the list call)",
              not re.search(r"(services|jobs) list .*--region", r["calls"]), r["calls"])


def unresponsive_cases():
    print("\nrotators + sync . critic round 3: an all-region list that skipped regions refuses")
    svc = {"status": {"latestReadyRevisionName": "r3", "traffic": [{"revisionName": "r3", "percent": 100}]}}
    newest = [revision("r3", "v", "8"), revision("r2", "v", "7"), revision("r1", "v", "6")]
    warn = ('  echo "WARNING: The following regions did not respond: europe-west9. '
            'List results may be incomplete." >&2\n')
    for wf, job in ((SYNC, "sync"), (KEYPAIR, "rotate"), (WORKER, "rotate")):
        body = extract_step(wf, job, KEEP_STEP)
        if body is None:
            check(f"{wf.name}: keep step exists", False)
            continue
        for kind in ("services", "jobs"):
            g = (f'if [ "$3" = "{kind}" ] && [ "$4" = "list" ]; then\n' + warn + '  exit 0\nfi\n'
                 + round2_stub(svc, {"svc": newest}, jobs=[("j1", "r", {})]))
            r = run_body(body, {"NEW_VERSION": "8", "KEEP_ENABLED_COUNT": "1"}, gcloud=g)
            check(f"{wf.name}: a {kind} list that skipped a region refuses and disables nothing",
                  r["rc"] != 0 and "versions disable" not in r["calls"] and "::error::" in r["out"],
                  f"rc={r['rc']} {r['out'][-300:]} {r['calls']}")


def round2_undo_cases():
    print("\nrotators . critic round 2 M3 undo (template pin, secretKeyRef, named traffic revisions)")
    for wf in (KEYPAIR, WORKER):
        body = extract_step(wf, "rotate", ROLLBACK_STEP)
        if body is None:
            check(f"{wf.name}: rollback step exists", False)
            continue
        tag = wf.name

        def go(svc, revs, named=None):
            return run_body(body, {"NEW_VERSION": "8", "CUR_VERSION": "7"},
                            gcloud=round2_stub(svc, {"svc": revs}, named=named))

        def refused(r):
            return "versions disable" not in r["calls"] and r["rc"] != 0

        # probe P2: traffic on r1 (pins 7), but the latest ready revision r2 (0% traffic) pins 8.
        s2 = {"status": {"latestReadyRevisionName": "r2", "traffic": [{"revisionName": "r1", "percent": 100}]}}
        r = go(s2, [revision("r2", "v", "8"), revision("r1", "v", "7")])
        check(f"{tag}: the latest ready revision at 0% traffic still counts as live (8 not disabled)",
              refused(r), r["calls"] + r["out"])
        s3 = {"status": {"latestReadyRevisionName": "r1", "latestCreatedRevisionName": "r2",
                         "traffic": [{"revisionName": "r1", "percent": 100}]}}
        r = go(s3, [revision("r2", "v", "8"), revision("r1", "v", "7")])
        check(f"{tag}: the latest CREATED revision counts as live (8 not disabled)", refused(r),
              r["calls"] + r["out"])
        s4 = {"spec": {"template": revision("tpl", "v", "8")},
              "status": {"latestReadyRevisionName": "r1", "traffic": [{"revisionName": "r1", "percent": 100}]}}
        r = go(s4, [revision("r1", "v", "7")])
        check(f"{tag}: the service TEMPLATE pin counts as live (8 not disabled)", refused(r),
              r["calls"] + r["out"])
        s5 = {"status": {"latestReadyRevisionName": "r1", "traffic": [{"revisionName": "r1", "percent": 100}]}}
        r = go(s5, [env_revision("r1", "8")])
        check(f"{tag}: a live pin via env[].valueFrom.secretKeyRef is refused too", refused(r),
              r["calls"] + r["out"])
        s6 = {"status": {"latestReadyRevisionName": "r2", "traffic": [{"revisionName": "ancient", "percent": 100}]}}
        r = go(s6, [revision("r2", "v", "7")], named={"ancient": revision("ancient", "v", "8")})
        check(f"{tag}: a traffic-holding revision outside the newest-50 list is described by name",
              refused(r) and "revisions describe ancient" in r["calls"], r["calls"] + r["out"])
        r = go(s5, [revision("r1", "v", "7")])
        check(f"{tag}: nothing live pins 8 -> still disabled", r["rc"] == 0 and "versions disable 8" in r["calls"],
              r["calls"] + r["out"])
        check(f"{tag}: the retained revision list is sorted newest-first",
              "--sort-by" in r["calls"], r["calls"])


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


# --- the composite action (single source of truth) and the thin wrapper -------------------------

READ_PAYLOAD_STEP = "Read payload_json from secrets_json"  # env: SECRETS_JSON
WARN_STEP = "Warn about the caller's concurrency group"    # env: GCP_PROJECT BUNDLE_SECRET
WRAPPER_USES = re.compile(r"^Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@v\d+\.\d+\.\d+$")


def action_doc():
    p = ACTION / "action.yml"
    return yaml.safe_load(p.read_text()) if p.exists() else None


def action_cases():
    print("\nsync-bundle-key action · secrets_json, concurrency warning, no interpolation")
    doc = action_doc()
    check("actions/sync-bundle-key/action.yml exists", doc is not None)
    if doc is None:
        return
    inp = doc.get("inputs", {})
    check("secrets_json is a required action input",
          inp.get("secrets_json", {}).get("required") is True, inp.get("secrets_json"))
    steps = doc["runs"]["steps"]
    # (1) environment secrets reach the action as the secrets_json input.
    build = next((s for s in steps if s.get("name") == ENVPAYLOAD_STEP), {})
    check("the env-payload step reads ALL_SECRETS_JSON from inputs.secrets_json",
          "inputs.secrets_json" in str(build.get("env", {}).get("ALL_SECRETS_JSON", "")), build.get("env"))
    body = extract_action_step(ACTION, READ_PAYLOAD_STEP)
    check(f"step '{READ_PAYLOAD_STEP}' exists", body is not None, "(not implemented yet)")
    if body is not None:
        payload = {"DB_PASSWORD": "pw-one-1", "REDIS_PASSWORD": "pw-two-2"}
        secrets = {"payload_json": json.dumps(payload), "OTHER": "must-not-leak-9", "github_token": "x"}
        r = run_body(body, {"SECRETS_JSON": json.dumps(secrets)})
        out = r["outputs"]
        check("caller source: payload_json is read out of secrets_json",
              r["rc"] == 0 and "DB_PASSWORD" in out and "pw-two-2" in out, r["out"] + out)
        check("caller source: nothing else in secrets_json reaches the output",
              "must-not-leak-9" not in out and "github_token" not in out, out)
        check("caller source: every payload value is registered with ::add-mask::",
              "::add-mask::pw-one-1" in r["out"] and "::add-mask::pw-two-2" in r["out"], r["out"])
        r = run_body(body, {"SECRETS_JSON": json.dumps({"PAYLOAD_JSON": json.dumps(payload), "OTHER": "must-not-leak-9"})})
        check("F2: an UPPERCASE PAYLOAD_JSON key is found (secret names are case-insensitive)",
              r["rc"] == 0 and "DB_PASSWORD" in r["outputs"] and "must-not-leak-9" not in r["outputs"], r["out"] + r["outputs"])
        r = run_body(body, {"SECRETS_JSON": json.dumps({"OTHER": "y"})})
        check("caller source: no payload_json secret leaves an empty payload for Validate to refuse",
              r["rc"] == 0 and '"y"' not in r["outputs"] and "OTHER" not in r["outputs"], r["out"] + r["outputs"])
    # (2) a composite action cannot see or declare concurrency: it always warns, naming the block.
    body = extract_action_step(ACTION, WARN_STEP)
    check(f"step '{WARN_STEP}' exists", body is not None, "(not implemented yet)")
    if body is not None:
        r = run_body(body, {"GCP_PROJECT": "proj-x", "BUNDLE_SECRET": "app-secrets"})
        check("the warning is a ::warning:: naming the exact concurrency group",
              r["rc"] == 0 and "::warning::" in r["out"]
              and "group: bundle-write-proj-x-app-secrets" in r["out"], r["out"])
        check("the warning says cancel-in-progress: false", "cancel-in-progress: false" in r["out"], r["out"])
        r = run_body(body, {"GCP_PROJECT": "proj-x", "BUNDLE_SECRET": "app-secrets", "CONCURRENCY_DECLARED": "false"})
        check("a direct caller (concurrency_declared false) still gets the ::warning::",
              "::warning::" in r["out"] and "::notice::" not in r["out"], r["out"])
        r = run_body(body, {"GCP_PROJECT": "proj-x", "BUNDLE_SECRET": "app-secrets", "CONCURRENCY_DECLARED": "true"})
        check("the wrapper (concurrency_declared true) gets a ::notice::, not a ::warning::",
              r["rc"] == 0 and "::notice::" in r["out"] and "::warning::" not in r["out"]
              and "group: bundle-write-proj-x-app-secrets" in r["out"], r["out"])
    cd = inp.get("concurrency_declared", {})
    check("concurrency_declared is an optional action input defaulting to 'false'",
          cd.get("default") == "false" and cd.get("required") is not True, cd)
    warn = next((s for s in steps if s.get("name") == WARN_STEP), {})
    check("the warn step reads concurrency_declared through env:",
          "inputs.concurrency_declared" in str(warn.get("env", {}).get("CONCURRENCY_DECLARED", "")), warn.get("env"))
    # Hygiene: no `${{ }}` inside a run body; every step that runs shell declares shell: bash.
    runs = [s for s in steps if "run" in s]
    check("every run step names shell: bash", runs and all(s.get("shell") == "bash" for s in runs))
    check("no run step interpolates ${{ }} (env: then \"$VAR\")",
          runs and not any("${{" in s["run"] for s in runs), [s.get("name") for s in runs if "${{" in s["run"]])
    check("every run step is a script beside action.yml",
          runs and all(re.fullmatch(r'"\$GITHUB_ACTION_PATH/[\w.-]+\.sh"', s["run"].strip()) for s in runs))


BOOL_STEP = "Validate boolean inputs"


def boolean_cases():
    print("\nF7 · boolean inputs are exactly 'true' or 'false' (an if: and a bash [ = ] must agree)")
    doc = yaml.safe_load((ACTION / "action.yml").read_text())
    steps = action_steps(ACTION)
    bools = sorted(k.upper() for k, v in doc["inputs"].items() if v.get("default") in ("true", "false"))
    check("the boolean validation step runs FIRST", steps[0].get("name") == BOOL_STEP, steps[0].get("name"))
    check("it covers every boolean-typed input of the action",
          sorted(steps[0].get("env", {})) == bools, f"{sorted(steps[0].get('env', {}))} vs {bools}")
    body = extract_action_step(ACTION, BOOL_STEP)
    if body is None:
        check(f"step '{BOOL_STEP}' exists", False)
        return
    good = {b: "true" for b in bools}
    check("all 'true' is accepted", run_body(body, good)["rc"] == 0)
    check("all 'false' is accepted", run_body(body, {b: "false" for b in bools})["rc"] == 0)
    for bad in ("yes", "1", "True", "FALSE", "", " true"):
        for b in bools:
            r = run_body(body, {**good, b: bad})
            check(f"{b}={bad!r} is refused and named", r["rc"] != 0 and b.lower() in r["out"].lower(), r["out"])


TOMB_STEP = "Refuse removed v4 inputs"


def tombstone_cases():
    print("\nv5 · mode / confirm_removed survive on the ACTION only as refusing tombstones")
    ad = action_doc() or {"inputs": {}}
    for k in ("mode", "confirm_removed"):
        i = ad["inputs"].get(k, {})
        check(f"action input {k} is declared with default '' and a REMOVED description",
              i.get("default") == "" and "REMOVED in v5" in str(i.get("description")), i)
    body = extract_action_step(ACTION, TOMB_STEP)
    check(f"step '{TOMB_STEP}' exists", body is not None)
    if body is None:
        return
    names = [st.get("name") for st in action_steps(ACTION)]
    check("it runs right after the boolean validation, before any other step", names[:2] == [BOOL_STEP, TOMB_STEP], names[:3])
    check("empty tombstones pass", run_body(body, {"MODE": "", "CONFIRM_REMOVED": ""})["rc"] == 0)
    for env in ({"MODE": "replace", "CONFIRM_REMOVED": ""}, {"MODE": "", "CONFIRM_REMOVED": "OLD_API_KEY"}):
        r = run_body(body, env)
        check(f"{env} is refused, telling the caller to use remove_keys",
              r["rc"] != 0 and "remove_keys" in r["out"] and "mode" in r["out"], r["out"])
    wf_inputs, _, _ = workflow_inputs()
    check("the wrapper workflow_call does NOT carry the tombstones", "mode" not in wf_inputs and "confirm_removed" not in wf_inputs)


def checkout_cases():
    print("\nF6 · the key-list checkout must not touch the caller's workspace root")
    steps = action_steps(ACTION)
    co = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    check("the action has exactly one checkout step", len(co) == 1, len(co))
    if len(co) != 1:
        return
    path = str(co[0].get("with", {}).get("path", ""))
    check("the checkout has a non-empty relative path: (a clean checkout in the root wipes the caller's tree)",
          path not in ("", ".") and not path.startswith("/") and ".." not in path.split("/"), path)
    check("the checkout runs only for payload_source: environment",
          str(co[0].get("if", "")).strip() == "inputs.payload_source == 'environment'", co[0].get("if"))
    readers = [s for s in steps if "SECRET_KEYS_FILE" in s.get("env", {})]
    check("the env-payload step reads the key list", len(readers) >= 1, [s.get("name") for s in readers])
    check("every reader points SECRET_KEYS_FILE into the checkout path",
          all(path in str(s["env"]["SECRET_KEYS_FILE"]) and "github.workspace" in str(s["env"]["SECRET_KEYS_FILE"])
              for s in readers), [s["env"]["SECRET_KEYS_FILE"] for s in readers])


def wrapper_cases():
    print("\nsync-bundle-key wrapper · calls the action, contract unchanged")
    inputs, secrets, doc = workflow_inputs()
    steps = doc["jobs"]["sync"]["steps"]
    calls = [s for s in steps if WRAPPER_USES.match(s.get("uses", ""))]
    check("the wrapper job calls the action by its REMOTE vX.Y.Z ref (a ./ ref resolves to the caller)",
          len(calls) == 1, [s.get("uses") for s in steps])
    check("the wrapper job has no inline run: steps", not any("run" in s for s in steps))
    if len(calls) != 1:
        return
    call = calls[0]
    with_ = call.get("with", {})
    missing = sorted(set(inputs) - set(with_))
    check("every workflow_call input is forwarded to the action's with:", not missing, f"missing {missing}")
    ad = action_doc() or {"inputs": {}}
    unknown = sorted(set(with_) - set(ad.get("inputs", {})))
    check("every with: key is an input of the action", not unknown, f"unknown {unknown}")
    same = [k for k in inputs if k in with_ and with_[k] != "${{ inputs.%s }}" % k]
    check("each input is passed through unchanged (${{ inputs.<name> }})", not same, same)
    check("remove_keys is passed through by the wrapper", with_.get("remove_keys") == "${{ inputs.remove_keys }}",
          with_.get("remove_keys"))
    for gone in ("mode", "confirm_removed"):
        check(f"v5: {gone} is not forwarded by the wrapper", gone not in with_)
    check("v5: remove_keys is an action input defaulting to ''", ad.get("inputs", {}).get("remove_keys", {}).get("default") == "")
    check("the wrapper sets concurrency_declared: 'true' (it declares the group itself)",
          str(with_.get("concurrency_declared")).lower() == "true", with_.get("concurrency_declared"))
    check("secrets_json is the caller's toJSON(secrets)",
          with_.get("secrets_json") == "${{ toJSON(secrets) }}", with_.get("secrets_json"))
    check("the wrapper keeps the payload_json secret", "payload_json" in secrets)
    outs = (doc.get("on") or doc[True])["workflow_call"].get("outputs", {})
    check("the three outputs are unchanged",
          sorted(outs) == ["new_version", "old_version", "services_rolled"], sorted(outs))
    job_outs = doc["jobs"]["sync"].get("outputs", {})
    check("each job output comes from the action step",
          len(job_outs) == 3 and all(f"steps.{call.get('id')}.outputs." in str(v) for v in job_outs.values()),
          job_outs)
    check("the wrapper keeps permissions, concurrency and timeout",
          doc.get("permissions", {}).get("id-token") == "write"
          and doc.get("permissions", {}).get("actions") == "read"
          and doc.get("concurrency", {}).get("cancel-in-progress") is False
          and doc["jobs"]["sync"].get("timeout-minutes") == 10, doc.get("permissions"))


def main():
    for fn in (input_cases, source_cases, s0_cases, mode_cases, strict_cases, roll_cases, keep_cases, rollback_cases,
               round2_keep_cases, unresponsive_cases, round2_undo_cases, identical_cases, env_source_cases,
               action_cases, boolean_cases, checkout_cases, wrapper_cases, tombstone_cases):
        fn()
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
