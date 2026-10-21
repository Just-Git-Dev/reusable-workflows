"""Structural + behaviour tests for the rotate-worker-signing-secret composite action and its
thin wrapper (.github/workflows/rotate-worker-signing-secret.yml).

What this pins:
  * the secret (new_secret, old_secret, the Cloudflare token) is NEVER interpolated into a `run:`
    body. `${{ steps.gen.outputs.new_secret }}` used to be substituted into the script TEXT before
    bash ran, so the secret was part of the script source and a value with shell metacharacters
    would execute. It now reaches a script only through `env:` and is read as "$VAR".
  * the action shape (shell: bash, script per step, no ${{ }} in a run), the wrapper contract, the
    concurrency reminder (warning for a direct caller, notice from the wrapper).
  * the Worker payload is valid JSON for any secret value, and nothing leaks into it twice.

Run: .venv/bin/python tests/run_rotator_action_tests.py
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
WRAPPER = ROOT / ".github" / "workflows" / "rotate-worker-signing-secret.yml"
ACTION = ACTIONS / "rotate-worker-signing-secret"
WRAPPER_USES = re.compile(r"^Just-Git-Dev/reusable-workflows/actions/rotate-worker-signing-secret@v\d+\.\d+\.\d+$")
EXPR = re.compile(r"\$\{\{.*?\}\}", re.S)

CASES = 0
FAILURES = []


def check(name, cond, detail=""):
    global CASES
    CASES += 1
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}"[:400])
        FAILURES.append(name)


def run_body(body, env, files=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for rel, content in (files or {}).items():
            (tmp / rel).write_text(content)
        e = dict(os.environ)
        e.update(GITHUB_OUTPUT=str(tmp / "out"), GITHUB_STEP_SUMMARY=str(tmp / "summary"))
        e.update(env)
        p = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
                            body.replace("/tmp/", f"{tmp}/")],
                           capture_output=True, text=True, env=e, cwd=tmp)
        read = lambda n: (tmp / n).read_text() if (tmp / n).exists() else ""  # noqa: E731
        return {"rc": p.returncode, "out": p.stdout + p.stderr, "outputs": read("out"),
                "cf": read("cf_secret.json"), "tmp": tmp}


def structural_cases():
    print("\nrotate-worker-signing-secret · no step output / secret interpolated into a run: body")
    check("actions/rotate-worker-signing-secret/action.yml exists", (ACTION / "action.yml").exists())
    wrapper = yaml.safe_load(WRAPPER.read_text())
    # The wrapper's own run: bodies (it should have none) and, via job_steps, the action's.
    sets = [("wrapper", wrapper["jobs"]["rotate"]["steps"])]
    if (ACTION / "action.yml").exists():
        sets.append(("action", yaml.safe_load((ACTION / "action.yml").read_text())["runs"]["steps"]))
    for label, steps in sets:
        bad = [s.get("name") for s in steps if "run" in s and EXPR.search(s["run"])]
        check(f"{label}: no ${{{{ ... }}}} expression inside any run: body", not bad, bad)
        bad = [s.get("name") for s in steps if "run" in s
               and re.search(r"\$\{\{[^}]*(new_secret|old_secret|steps\.[\w-]+\.outputs\.)", s["run"])]
        check(f"{label}: no new_secret / old_secret / steps.*.outputs.* in a run: body", not bad, bad)
    # The scripts themselves (the text bash executes) must not carry an expression either.
    texts = {p.name: p.read_text() for p in ACTION.glob("*.sh")} if ACTION.exists() else {}
    bad = [n for n, t in texts.items() if "${{" in t]
    check(f"no script under the action contains ${{{{ }}}} ({len(texts)} scripts examined)", texts and not bad, bad)


def action_cases():
    print("\nrotate-worker-signing-secret action · shape")
    if not (ACTION / "action.yml").exists():
        check("action.yml exists", False)
        return
    doc = yaml.safe_load((ACTION / "action.yml").read_text())
    steps = doc["runs"]["steps"]
    runs = [s for s in steps if "run" in s]
    check("every run step names shell: bash", runs and all(s.get("shell") == "bash" for s in runs))
    check("every run step is a script beside action.yml",
          runs and all(re.fullmatch(r'"\$GITHUB_ACTION_PATH/[\w.-]+\.sh"', s["run"].strip()) for s in runs))
    check("secrets_json is a required input", doc["inputs"].get("secrets_json", {}).get("required") is True)
    cd = doc["inputs"].get("concurrency_declared", {})
    check("concurrency_declared is optional and defaults to 'false'",
          cd.get("default") == "false" and cd.get("required") is not True, cd)
    check("outputs old_version / new_version exist",
          {"old_version", "new_version"} <= set(doc.get("outputs", {})), list(doc.get("outputs", {})))
    check("no input description embeds a secrets expression",
          "${{" not in json.dumps(doc["inputs"]), "")
    first = steps[1] if len(steps) > 1 else {}
    check("the concurrency reminder follows the boolean validation (F7)",
          "warn-concurrency" in first.get("run", ""), first)
    # Every secret-carrying env var is fed from a step output or secrets_json, never from a literal.
    token = next((s for s in steps if s.get("name") == "Read the Cloudflare token"), {})
    check("the Cloudflare token is read out of secrets_json", "inputs.secrets_json" in str(token.get("env")), token)
    for name, var, src in (("Set Worker PRIMARY slot = new secret", "NEW_SECRET", "steps.gen.outputs.new_secret"),
                           ("Set Worker PREVIOUS slot = old secret", "OLD_SECRET", "steps.cur.outputs.old_secret"),
                           ("Replace the key in the bundle", "NEW_SECRET", "steps.gen.outputs.new_secret")):
        st = next((s for s in steps if s.get("name") == name), {})
        check(f"'{name}': {var} arrives through env:", src in str(st.get("env", {}).get(var, "")), st.get("env"))

    print("\nrotate-worker-signing-secret action · behaviour")
    body = extract_action_step(ACTION, "Warn about the caller's concurrency group")
    check("concurrency reminder step exists", body is not None)
    if body is not None:
        env = {"GCP_PROJECT": "proj-x", "BUNDLE_SECRET": "app-secrets"}
        r = run_body(body, {**env, "CONCURRENCY_DECLARED": "false"})
        check("a direct caller gets the ::warning:: naming the exact group",
              r["rc"] == 0 and "::warning::" in r["out"] and "group: bundle-write-proj-x-app-secrets" in r["out"], r["out"])
        r = run_body(body, {**env, "CONCURRENCY_DECLARED": "true"})
        check("the wrapper (concurrency_declared true) gets a ::notice::, not a ::warning::",
              r["rc"] == 0 and "::notice::" in r["out"] and "::warning::" not in r["out"], r["out"])

    body = extract_action_step(ACTION, "Read the Cloudflare token")
    if body is not None:
        r = run_body(body, {"SECRETS_JSON": json.dumps({"cloudflare_api_token": "cf-tok-1", "OTHER": "leak-me"})})
        check("token step masks the token and emits it as an output",
              r["rc"] == 0 and "::add-mask::cf-tok-1" in r["out"] and "cf-tok-1" in r["outputs"], r["out"] + r["outputs"])
        check("token step emits nothing else from secrets_json", "leak-me" not in r["outputs"] + r["out"])
        r = run_body(body, {"SECRETS_JSON": json.dumps({"OTHER": "x"})})
        check("a missing cloudflare_api_token fails the step", r["rc"] != 0, r["out"])
        r = run_body(body, {"SECRETS_JSON": json.dumps({"CLOUDFLARE_API_TOKEN": "cf-tok-UP", "OTHER": "leak-me"})})
        check("F2: an UPPERCASE CLOUDFLARE_API_TOKEN key is found (secret names are case-insensitive)",
              r["rc"] == 0 and "cf-tok-UP" in r["outputs"] and "leak-me" not in r["outputs"], r["out"] + r["outputs"])

    body = extract_action_step(ACTION, "Generate new signing secret")
    if body is not None:
        r = run_body(body, {"SECRET_BYTES": "16"})
        m = re.search(r"new_secret<<(\S+)\n([0-9a-f]{32})\n\1\n", r["outputs"])
        check("generated secret is 2x secret_bytes hex, masked, heredoc output",
              r["rc"] == 0 and m and f"::add-mask::{m.group(2)}" in r["out"], r["out"] + r["outputs"])

    # A hostile value must reach the Worker payload as DATA, never as shell or broken JSON.
    hostile = 'a"b$(touch pwned)`id`\\'
    for name, var, slot, key in (("Set Worker PRIMARY slot = new secret", "NEW_SECRET", "CF_PRIMARY", "PRIM"),
                                 ("Set Worker PREVIOUS slot = old secret", "OLD_SECRET", "CF_PREVIOUS", "PREV")):
        body = extract_action_step(ACTION, name)
        if body is None:
            check(f"'{name}' exists", False)
            continue
        # curl is shadowed by a function that keeps the --data @file payload; the script then runs
        # in a sandbox cwd, and a trailing `ls` shows whether the hostile value created a file.
        stub = 'curl() { for a in "$@"; do case "$a" in @*) cp "${a#@}" /tmp/sent;; esac; done; printf 200; }\n'
        r = run_body(stub + body + '\necho "PAYLOAD:$(cat /tmp/sent)"\necho "FILES:$(ls)"\n',
                     {var: hostile, "CF_PRIMARY": "PRIM", "CF_PREVIOUS": "PREV", "CF_ACCOUNT_ID": "acc",
                      "CF_WORKER_SCRIPT": "w", "CF_API_TOKEN": "t"})
        m = re.search(r"PAYLOAD:(\{.*\})\s*FILES:", r["out"], re.S)
        try:
            parsed = json.loads(m.group(1)) if m else None
        except ValueError:
            parsed = None
        check(f"'{name}': a hostile secret value arrives as valid JSON data",
              parsed is not None and parsed.get("text") == hostile and parsed.get("name") == key, r["out"])
        check(f"'{name}': nothing in the value was executed", "pwned" not in r["out"].split("FILES:")[-1], r["out"])


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


def wrapper_cases():
    print("\nrotate-worker-signing-secret wrapper · calls the action, contract unchanged")
    doc = yaml.safe_load(WRAPPER.read_text())
    on = doc.get("on") or doc[True]
    inputs = on["workflow_call"]["inputs"]
    steps = doc["jobs"]["rotate"]["steps"]
    calls = [s for s in steps if WRAPPER_USES.match(s.get("uses", ""))]
    check("the wrapper calls the action by its REMOTE vX.Y.Z ref", len(calls) == 1, [s.get("uses") for s in steps])
    check("the wrapper job has no inline run: steps", not any("run" in s for s in steps))
    if len(calls) != 1:
        return
    with_ = calls[0].get("with", {})
    missing = sorted(set(inputs) - set(with_))
    check("every workflow_call input is forwarded", not missing, missing)
    ad = yaml.safe_load((ACTION / "action.yml").read_text()) if (ACTION / "action.yml").exists() else {"inputs": {}}
    unknown = sorted(set(with_) - set(ad.get("inputs", {})))
    check("every with: key is an input of the action", not unknown, unknown)
    same = [k for k in inputs if k in with_ and with_[k] != "${{ inputs.%s }}" % k]
    check("each input is passed through unchanged", not same, same)
    check("secrets_json is the caller's toJSON(secrets)", with_.get("secrets_json") == "${{ toJSON(secrets) }}", with_.get("secrets_json"))
    check("the wrapper sets concurrency_declared: 'true'", str(with_.get("concurrency_declared")).lower() == "true")
    check("the secret cloudflare_api_token is still declared", "cloudflare_api_token" in on["workflow_call"]["secrets"])
    check("outputs keep their names", sorted(on["workflow_call"]["outputs"]) == ["new_version", "old_version"])
    job = doc["jobs"]["rotate"]
    check("job outputs come from the action step",
          all(f"steps.{calls[0].get('id')}.outputs." in str(v) for v in job.get("outputs", {}).values()) and job.get("outputs"))
    check("the wrapper keeps permissions, concurrency, timeout and WORKFLOW_VERSION",
          doc["permissions"].get("id-token") == "write" and doc["concurrency"].get("cancel-in-progress") is False
          and job.get("timeout-minutes") == 30 and "WORKFLOW_VERSION" in doc.get("env", {}), doc.get("permissions"))


def main():
    for fn in (structural_cases, action_cases, boolean_cases, wrapper_cases):
        fn()
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
