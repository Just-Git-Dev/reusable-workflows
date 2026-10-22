"""Tests for the rotate-external-secret composite action and its thin wrapper
(.github/workflows/rotate-external-secret.yml).

What this pins:
  * decide.sh as a pure table over every branch of the state machine (pending-sync / retire /
    rotate / adopt / no-op / refuse), with an injected clock (NOW).
  * the Cloudflare calls (list / PUT / DELETE, non-2xx fails) and the gh calls (secret set on stdin,
    workflow run, run list/view, variable get/set) against stubbed `curl` / `gh` / `date` / `sleep`.
  * the sync wait: success, failure (job fails, pending stays, nothing deleted), timeout, and
    refusal of an ambiguous match.
  * dry_run makes no write call at all.
  * the generated value never reaches stdout, stderr, GITHUB_OUTPUT, the step summary or a command
    line; it travels only on stdin / a 0600 file that the shred step removes.
  * shape: every action step runs "$GITHUB_ACTION_PATH/x.sh" with shell: bash and inputs via env:;
    the wrapper's permissions, concurrency group, timeout and remote action ref.

Run: .venv/bin/python tests/run_rotate_external_tests.py
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
from action_steps import ACTIONS, action_steps, extract_action_step  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / ".github" / "workflows" / "rotate-external-secret.yml"
ACTION = ACTIONS / "rotate-external-secret"
WRAPPER_USES = re.compile(r"^Just-Git-Dev/reusable-workflows/actions/rotate-external-secret@v\d+\.\d+\.\d+$")
EXPR = re.compile(r"\$\{\{.*?\}\}", re.S)
NOW = 1_800_000_000
H, D = 3600, 86400

CASES = 0
FAILURES = []


def check(name, cond, detail=""):
    global CASES
    CASES += 1
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}"[:500])
        FAILURES.append(name)


CURL = r'''
curl() {
  local method=GET url="" out="" data=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -X) method=$2; shift;;
      -o) out=$2; shift;;
      --data) data=$2; shift;;
      -w|-H) shift;;
      https://*) url=$1;;
    esac
    shift
  done
  echo "CURL $method $url" >> /tmp/calls
  if [ "$data" = "@-" ]; then cat > /tmp/curl_body; elif [ -n "$data" ]; then echo "DATAARG $data" >> /tmp/calls; fi
  case "$method" in
    GET) body=${CF_LIST_JSON:-'{"success":true,"result":[]}'}; code=${CF_LIST_HTTP:-200};;
    *) body='{"success":true}'; code=${CF_WRITE_HTTP:-200};;
  esac
  [ -z "$out" ] || printf '%s' "$body" > "$out"
  printf '%s' "$code"
}
'''
GH = r'''
gh() {
  echo "GH $*" >> /tmp/calls
  case "$1 $2" in
    "secret set") cat > /tmp/secret_stdin;;
    "workflow run") ;;
    "run list") cat /tmp/runlist.json;;
    "run view")
      n=$(cat /tmp/viewn 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > /tmp/viewn
      if [ -f "/tmp/runview.$n.json" ]; then cat "/tmp/runview.$n.json"; else cat /tmp/runview.json; fi;;
    "variable get")
      if [ -f /tmp/var.json ]; then cat /tmp/var.json; else echo "HTTP 404: Not Found (https://api.github.com/x)" >&2; return 1; fi;;
    "variable set") ;;
  esac
}
'''
CLOCK = r'''
date() {
  if [ "$1" = "+%s" ]; then
    n=$(cat /tmp/clock 2>/dev/null || echo 1000); echo $((n + ${CLOCK_STEP:-0})) > /tmp/clock; echo "$n"
  else command date "$@"; fi
}
sleep() { :; }
'''
STUBS = CURL + GH + CLOCK


def run(body, env=None, files=None, stubs=STUBS):
    """Run a script body once in a scratch dir; returns rc, merged output and the scratch files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "rt").mkdir()
        for rel, content in (files or {}).items():
            (tmp / rel).write_text(content)
        e = dict(os.environ)
        for k in ("GITHUB_ACTION_PATH",):
            e.pop(k, None)
        e.update(GITHUB_OUTPUT=str(tmp / "out"), GITHUB_STEP_SUMMARY=str(tmp / "summary"),
                 RUNNER_TEMP=str(tmp / "rt"))
        e.update(env or {})
        p = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
                            (stubs + body).replace("/tmp/", f"{tmp}/")],
                           capture_output=True, text=True, env=e, cwd=tmp)
        rd = lambda n: (tmp / n).read_text() if (tmp / n).exists() else ""  # noqa: E731
        return {"rc": p.returncode, "out": p.stdout + p.stderr, "outputs": rd("out"), "summary": rd("summary"),
                "calls": rd("calls"), "stdin": rd("secret_stdin"), "body": rd("curl_body"), "tmp": tmp,
                "secretfile": (tmp / "rt" / "rotate-external" / "new-secret")}


def outs(text):
    d = {}
    for line in text.splitlines():
        if "=" in line and "<<" not in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


def step(name):
    b = extract_action_step(ACTION, name) if (ACTION / "action.yml").exists() else None
    if b is None:
        check(f"step '{name}' exists", False)
    return b


SLOTS = {"SLOT_A": "SIG_A", "SLOT_B": "SIG_B"}


def decide_cases():
    print("\nrotate-external-secret · decide.sh (pure state machine table)")
    body = step("Decide")
    if body is None:
        return

    def st(cur, pend="", age=0):
        return json.dumps({"current": cur, "pending": pend, "rotated_at": NOW - age})

    base = {**SLOTS, "NOW": str(NOW), "ROTATE_EVERY_DAYS": "30", "GRACE_HOURS": "24", "FORCE": "false"}
    table = [
        ("no state, no slot -> rotate into slot_a", "", "", "rotate", {"new_slot": "SIG_A"}),
        ("no state, one slot A -> adopt", "", "SIG_A", "adopt", {"current": "SIG_A"}),
        ("no state, one slot B -> adopt", "", "SIG_B", "adopt", {"current": "SIG_B"}),
        ("no state, both slots -> refuse", "", "SIG_A,SIG_B", "refuse", {}),
        ("bad JSON -> refuse", "{nope", "SIG_A", "refuse", {}),
        ("JSON array -> refuse", "[]", "SIG_A", "refuse", {}),
        ("rotated_at not a number -> refuse", '{"current":"SIG_A","pending":"","rotated_at":"x"}', "SIG_A", "refuse", {}),
        ("current names a slot that is absent -> refuse", st("SIG_A"), "SIG_B", "refuse", {}),
        ("current is not one of the slots -> refuse", st("OTHER"), "SIG_A", "refuse", {}),
        ("pending equals current -> refuse", st("SIG_A", "SIG_A"), "SIG_A", "refuse", {}),
        ("pending slot absent -> refuse", st("SIG_A", "SIG_B"), "SIG_A", "refuse", {}),
        ("pending set, both slots -> pending-sync", st("SIG_A", "SIG_B", 100), "SIG_A,SIG_B", "pending-sync", {"new_slot": "SIG_B"}),
        ("bootstrap pending (current empty) -> pending-sync", st("", "SIG_A"), "SIG_A", "pending-sync", {"new_slot": "SIG_A"}),
        ("both slots, grace reached (A current) -> retire B", st("SIG_A", "", 25 * H), "SIG_A,SIG_B", "retire", {"retire_slot": "SIG_B"}),
        ("both slots, grace reached (B current) -> retire A", st("SIG_B", "", 25 * H), "SIG_A,SIG_B", "retire", {"retire_slot": "SIG_A"}),
        ("both slots, grace exactly reached -> retire", st("SIG_A", "", 24 * H), "SIG_A,SIG_B", "retire", {"retire_slot": "SIG_B"}),
        ("both slots, grace not reached -> noop", st("SIG_A", "", H), "SIG_A,SIG_B", "noop", {}),
        ("one slot, due -> rotate into the other", st("SIG_A", "", 31 * D), "SIG_A", "rotate", {"new_slot": "SIG_B"}),
        ("one slot B, due -> rotate into A", st("SIG_B", "", 31 * D), "SIG_B", "rotate", {"new_slot": "SIG_A"}),
        ("one slot, not due -> noop", st("SIG_A", "", 5 * D), "SIG_A", "noop", {}),
    ]
    for name, state, present, want, extra in table:
        r = run(body, {**base, "STATE_JSON": state, "PRESENT": present})
        o = outs(r["outputs"])
        ok = o.get("action") == want and all(o.get(k) == v for k, v in extra.items())
        ok = ok and ((r["rc"] != 0) == (want == "refuse"))
        check(name, ok, f"rc={r['rc']} {o} {r['out']}")
    r = run(body, {**base, "STATE_JSON": st("SIG_A", "", H), "PRESENT": "SIG_A,SIG_B"})
    check("grace not reached: message says when the old slot retires", "retires at" in outs(r["outputs"]).get("message", ""), r["outputs"])
    r = run(body, {**base, "STATE_JSON": st("SIG_A", "", 5 * D), "PRESENT": "SIG_A"})
    check("rotate_every_days not reached: message says when the next rotation is due",
          "next rotation" in outs(r["outputs"]).get("message", ""), r["outputs"])
    r = run(body, {**base, "FORCE": "true", "STATE_JSON": st("SIG_A", "", 5 * D), "PRESENT": "SIG_A"})
    check("force rotates before rotate_every_days", outs(r["outputs"]).get("action") == "rotate", r["outputs"])
    r = run(body, {**base, "FORCE": "true", "STATE_JSON": st("SIG_A", "", H), "PRESENT": "SIG_A,SIG_B"})
    check("force cannot rotate while both slots exist (no empty slot)", outs(r["outputs"]).get("action") == "noop", r["outputs"])
    r = run(body, {**base, "STATE_JSON": st("SIG_A", "", 31 * D), "PRESENT": "SIG_A,SIG_B", "FORCE": "false"})
    check("both slots past rotate_every_days: retire wins, never a second rotation", outs(r["outputs"]).get("action") == "retire", r["outputs"])
    r = run(body, {**base, "STATE_JSON": "{nope", "PRESENT": ""})
    check("a refusal prints ::error:: saying what to check", "::error::" in r["out"] and "check" in r["out"].lower(), r["out"])


def cloudflare_cases():
    print("\nrotate-external-secret · Cloudflare calls")
    cf = {"CF_ACCOUNT_ID": "acc", "WORKER_SCRIPT": "w", "CF_API_TOKEN": "tok", **SLOTS}
    body = step("List Worker slots")
    if body is not None:
        lst = json.dumps({"success": True, "result": [{"name": "SIG_B", "type": "secret_text"},
                                                      {"name": "UNRELATED", "type": "secret_text"}]})
        r = run(body, {**cf, "CF_LIST_JSON": lst})
        check("list: only slot_a/slot_b names are reported, via GET .../workers/scripts/w/secrets",
              r["rc"] == 0 and outs(r["outputs"]).get("present") == "SIG_B"
              and "CURL GET https://api.cloudflare.com/client/v4/accounts/acc/workers/scripts/w/secrets" in r["calls"], r["out"] + r["outputs"] + r["calls"])
        r = run(body, {**cf, "CF_LIST_HTTP": "403"})
        check("list: a non-2xx fails the step", r["rc"] != 0, r["out"])
    body = step("Put Worker slot")
    if body is not None:
        env = {**cf, "NEW_SLOT": "SIG_B"}
        pre = 'mkdir -p "$RUNNER_TEMP/rotate-external"; printf %s "s3cr3t-value" > "$RUNNER_TEMP/rotate-external/new-secret"\n'
        r = run(pre + body, env)
        sent = json.loads(r["body"]) if r["body"] else {}
        check("put: PUT .../secrets with {name, text, type} on stdin",
              r["rc"] == 0 and "CURL PUT https://api.cloudflare.com/client/v4/accounts/acc/workers/scripts/w/secrets" in r["calls"]
              and sent == {"name": "SIG_B", "text": "s3cr3t-value", "type": "secret_text"}, r["out"] + r["calls"] + r["body"])
        check("put: the value is not on a command line", "s3cr3t-value" not in r["calls"] + r["out"], r["calls"])
        r = run(pre + body, {**env, "CF_WRITE_HTTP": "500"})
        check("put: non-2xx fails the step", r["rc"] != 0 and "500" in r["out"], r["out"])
        r = run(pre + body, {**env, "DRY_RUN": "true"})
        check("put: refuses to write in dry_run", r["rc"] != 0 and "CURL" not in r["calls"], r["out"] + r["calls"])
    body = step("Retire old slot")
    if body is not None:
        env = {**cf, "RETIRE_SLOT": "SIG_B"}
        r = run(body, env)
        check("delete: DELETE .../secrets/<slot>",
              r["rc"] == 0 and "CURL DELETE https://api.cloudflare.com/client/v4/accounts/acc/workers/scripts/w/secrets/SIG_B" in r["calls"], r["out"] + r["calls"])
        r = run(body, {**env, "CF_WRITE_HTTP": "500"})
        check("delete: non-2xx fails the step", r["rc"] != 0, r["out"])
        r = run(body, {**env, "DRY_RUN": "true"})
        check("delete: refuses to write in dry_run", r["rc"] != 0 and "CURL" not in r["calls"], r["out"] + r["calls"])


def gh_cases():
    print("\nrotate-external-secret · gh calls (state, env secret, dispatch)")
    base = {"GH_TOKEN": "t", "OWNER": "Org", "TARGET_REPO": "svc", "REPO": "Org/project", "STATE_VARIABLE": "ST"}
    body = step("Read state")
    if body is not None:
        r = run(body, base, files={"var.json": '{"current":"SIG_A","pending":"","rotated_at":5}'})
        check("read-state: returns the variable's JSON", outs(r["outputs"]).get("state_json") == '{"current":"SIG_A","pending":"","rotated_at":5}'
              and "GH variable get ST --repo Org/project" in r["calls"], r["outputs"] + r["calls"])
        r = run(body, base)
        check("read-state: a missing variable (404) is empty state, not an error", r["rc"] == 0 and outs(r["outputs"]).get("state_json") == "", r["out"] + r["outputs"])
        r = run(body, base, stubs='gh() { echo "HTTP 500: boom" >&2; return 1; }\n')
        check("read-state: any other API error fails the step", r["rc"] != 0, r["out"])
    body = step("Write environment secret")
    if body is not None:
        pre = 'mkdir -p "$RUNNER_TEMP/rotate-external"; printf %s "v4lue-xyz" > "$RUNNER_TEMP/rotate-external/new-secret"\n'
        env = {**base, "TARGET_ENVIRONMENT": "prod", "TARGET_SECRET_NAME": "FILES_SECRET"}
        r = run(pre + body, env)
        check("env secret: gh secret set <name> --env <env> --repo, value on stdin",
              r["rc"] == 0 and "GH secret set FILES_SECRET --env prod --repo Org/svc" in r["calls"] and r["stdin"] == "v4lue-xyz", r["out"] + r["calls"] + r["stdin"])
        check("env secret: the value is not on a command line", "v4lue-xyz" not in r["calls"] + r["out"])
        r = run(pre + body, {**env, "DRY_RUN": "true"})
        check("env secret: refuses to write in dry_run", r["rc"] != 0 and "GH" not in r["calls"], r["out"])
    for name, cur, pend, at, want in (
            ("Record pending", "SIG_A", "SIG_B", str(NOW - 31 * D), {"current": "SIG_A", "pending": "SIG_B", "rotated_at": NOW - 31 * D}),
            ("Promote pending", "SIG_B", "", "now", {"current": "SIG_B", "pending": "", "rotated_at": NOW}),
            ("Adopt slot", "SIG_A", "", "now", {"current": "SIG_A", "pending": "", "rotated_at": NOW})):
        body = step(name)
        if body is None:
            continue
        env = {**base, "STATE_CURRENT": cur, "STATE_PENDING": pend, "STATE_ROTATED_AT": at, "NOW": str(NOW)}
        r = run(body, env)
        m = re.search(r"GH variable set ST --repo Org/project --body (\{.*\})", r["calls"])
        got = json.loads(m.group(1)) if m else None
        check(f"'{name}': variable set with the expected JSON", r["rc"] == 0 and got == want, r["out"] + r["calls"])
        r = run(body, {**env, "DRY_RUN": "true"})
        check(f"'{name}': refuses to write in dry_run", r["rc"] != 0 and "GH" not in r["calls"], r["out"])
    body = step("Dispatch sync")
    if body is not None:
        env = {**base, "SYNC_WORKFLOW": "sync.yml", "SYNC_REF": "main", "SYNC_INPUTS_JSON": '{"dry_run":"false"}', "CORRELATION_ID": "99-1"}
        r = run(body, env)
        check("dispatch: gh workflow run with ref, the extra inputs and correlation_id",
              r["rc"] == 0 and "GH workflow run sync.yml --repo Org/svc --ref main" in r["calls"]
              and "-f dry_run=false" in r["calls"] and "-f correlation_id=99-1" in r["calls"], r["out"] + r["calls"])
        r = run(body, {**env, "DRY_RUN": "true"})
        check("dispatch: refuses in dry_run", r["rc"] != 0 and "GH" not in r["calls"], r["out"])


def wait_cases():
    print("\nrotate-external-secret · waiting for the sync run")
    body = step("Wait for sync")
    if body is None:
        return
    env = {"GH_TOKEN": "t", "OWNER": "Org", "TARGET_REPO": "svc", "SYNC_WORKFLOW": "sync.yml",
           "CORRELATION_ID": "99-1", "WAIT_MINUTES": "30", "POLL_SECONDS": "0", "CLOCK_STEP": "60"}
    run_item = lambda i, t, s="completed", c="success": {"databaseId": i, "displayTitle": t, "status": s, "conclusion": c}  # noqa: E731
    lst = json.dumps([run_item(1, "sync 98-1"), run_item(7, "sync 99-1", "queued", ""), run_item(3, "sync 99-10")])
    files = {"runlist.json": lst, "runview.json": json.dumps({"status": "completed", "conclusion": "success"})}
    r = run(body, env, files)
    check("success: matches the whole token only (not 99-10), views run 7 and passes",
          r["rc"] == 0 and "GH run view 7 --repo Org/svc" in r["calls"] and "GH run list --repo Org/svc --workflow sync.yml" in r["calls"], r["out"] + r["calls"])
    r = run(body, env, {**files, "runview.1.json": json.dumps({"status": "in_progress", "conclusion": ""})})
    check("success after an in_progress poll", r["rc"] == 0 and r["calls"].count("GH run view") == 2, r["out"] + r["calls"])
    r = run(body, env, {**files, "runview.json": json.dumps({"status": "completed", "conclusion": "failure"})})
    check("a failed sync run fails the step", r["rc"] != 0 and "failure" in r["out"], r["out"])
    check("a failed sync run deletes nothing and sets no state", "DELETE" not in r["calls"] and "variable set" not in r["calls"], r["calls"])
    r = run(body, {**env, "CLOCK_STEP": "600"}, {**files, "runview.json": json.dumps({"status": "in_progress", "conclusion": ""})})
    check("timeout: still running after wait_minutes fails the step", r["rc"] != 0 and "timed out" in r["out"].lower(), r["out"])
    r = run(body, {**env, "CLOCK_STEP": "600"}, {**files, "runlist.json": "[]"})
    check("timeout: the run never appears -> fails", r["rc"] != 0 and "timed out" in r["out"].lower(), r["out"])
    two = json.dumps([run_item(7, "sync 99-1"), run_item(8, "sync 99-1")])
    r = run(body, env, {**files, "runlist.json": two})
    check("two runs match the correlation id -> refuse (ambiguous)", r["rc"] != 0 and "ambiguous" in r["out"].lower() and "GH run view" not in r["calls"], r["out"])


def flow_cases():
    print("\nrotate-external-secret · dry run and secret hygiene")
    # dry run: the read-only steps and the planner make no write call
    calls = ""
    for name, env, files in (
            ("Read state", {"GH_TOKEN": "t", "REPO": "Org/project", "STATE_VARIABLE": "ST"}, {}),
            ("List Worker slots", {"CF_ACCOUNT_ID": "a", "WORKER_SCRIPT": "w", "CF_API_TOKEN": "t", **SLOTS}, {})):
        b = step(name)
        if b is not None:
            calls += run(b, env, files)["calls"]
    check("dry_run read-only steps made calls but no write call",
          calls and not re.search(r"CURL (PUT|DELETE)|secret set|workflow run|variable set", calls), calls)

    gen, put, envs = step("Generate secret"), step("Put Worker slot"), step("Write environment secret")
    shred = step("Shred secret")
    if None in (gen, put, envs, shred):
        return
    chain = gen + "\n" + put + "\n" + envs + '\ncp "$RUNNER_TEMP/rotate-external/new-secret" /tmp/value_copy\n'
    env = {"SECRET_BYTES": "16", "CF_ACCOUNT_ID": "a", "WORKER_SCRIPT": "w", "CF_API_TOKEN": "t", "NEW_SLOT": "SIG_B",
           "GH_TOKEN": "t", "OWNER": "Org", "TARGET_REPO": "svc", "TARGET_ENVIRONMENT": "prod", "TARGET_SECRET_NAME": "S"}
    r = run(chain, env)
    # the scratch dir is gone on return: the value is read from what `gh secret set` got on stdin
    value = r["stdin"]
    check("generated value is 32 hex chars and reached `gh secret set` on stdin", re.fullmatch(r"[0-9a-f]{32}", value or "") is not None, value)
    check("the value was masked", f"::add-mask::{value}" in r["out"], r["out"])
    json_sent = json.loads(r["body"]) if r["body"] else {}
    check("the same value reached Cloudflare in the --data @- body", json_sent.get("text") == value, r["body"])
    leaks = [n for n, t in (("stdout/stderr (besides the mask command)", r["out"].replace(f"::add-mask::{value}", "")),
                            ("GITHUB_OUTPUT", r["outputs"]), ("summary", r["summary"]), ("command lines", r["calls"])) if value and value in t]
    check("the value appears nowhere but the mask command, stdin and the request body", not leaks, leaks)
    r = run(gen + "\n" + shred + '\n[ ! -e "$RUNNER_TEMP/rotate-external/new-secret" ] && echo GONE\n', {"SECRET_BYTES": "16"})
    check("the shred step removes the secret file", "GONE" in r["out"], r["out"])
    b = step("Summary")
    if b is not None:
        r = run(b, {"ACTION": "noop", "MESSAGE": "old slot SIG_B retires at 2030-01-01T00:00:00Z", "DRY_RUN": "false",
                    "WORKER_SCRIPT": "w", "SLOT_A": "SIG_A", "SLOT_B": "SIG_B", "TARGET_REPO": "svc",
                    "TARGET_ENVIRONMENT": "prod", "TARGET_SECRET_NAME": "S", "SYNC_WORKFLOW": "sync.yml",
                    "STATE_VARIABLE": "ST", "CURRENT": "SIG_A", "NEW_SLOT": "", "RETIRE_SLOT": ""})
        check("summary names the branch and says when the old slot retires",
              r["rc"] == 0 and "noop" in r["summary"] and "retires at" in r["summary"], r["out"] + r["summary"])
        r = run(b, {"ACTION": "rotate", "MESSAGE": "m", "DRY_RUN": "true", "WORKER_SCRIPT": "w", "SLOT_A": "SIG_A", "SLOT_B": "SIG_B",
                    "TARGET_REPO": "svc", "TARGET_ENVIRONMENT": "prod", "TARGET_SECRET_NAME": "S", "SYNC_WORKFLOW": "sync.yml",
                    "STATE_VARIABLE": "ST", "CURRENT": "SIG_A", "NEW_SLOT": "SIG_B", "RETIRE_SLOT": ""})
        check("dry-run summary lists the planned calls", "would" in r["summary"].lower(), r["summary"])


def inputs_cases():
    print("\nrotate-external-secret · input validation")
    b = step("Validate inputs")
    bools = step("Validate boolean inputs")
    good = {"CF_ACCOUNT_ID": "0123abcd", "WORKER_SCRIPT": "svc-cdn", "SLOT_A": "SIG_A", "SLOT_B": "SIG_B", "TARGET_REPO": "svc",
            "TARGET_ENVIRONMENT": "prod", "TARGET_SECRET_NAME": "FILES_SECRET", "SYNC_WORKFLOW": "sync.yml", "SYNC_REF": "main",
            "SYNC_INPUTS_JSON": '{"dry_run":"false"}', "STATE_VARIABLE": "ST", "ROTATE_EVERY_DAYS": "30", "GRACE_HOURS": "24",
            "WAIT_MINUTES": "30", "SECRET_BYTES": "32", "APP_ID": "123", "GITHUB_REPOSITORY": "Org/project"}
    if b is not None:
        r = run(b, good)
        check("valid inputs pass and the token repos are target + this repo",
              r["rc"] == 0 and outs(r["outputs"]).get("token_repos") == "svc,project", r["out"] + r["outputs"])
        for k, v in (("SLOT_B", "SIG_A"), ("SLOT_A", "bad name"), ("WAIT_MINUTES", "31"), ("WAIT_MINUTES", "0"),
                     ("ROTATE_EVERY_DAYS", "x"), ("GRACE_HOURS", "-1"), ("SECRET_BYTES", "8"), ("TARGET_REPO", "a/b"),
                     ("SYNC_INPUTS_JSON", "[1]"), ("SYNC_INPUTS_JSON", '{"correlation_id":"x"}'), ("SYNC_WORKFLOW", "../x.yml"),
                     ("STATE_VARIABLE", "GITHUB_X")):
            r = run(b, {**good, k: v})
            check(f"{k}={v!r} is refused", r["rc"] != 0 and "::error::" in r["out"], r["out"])
    if bools is not None:
        check("booleans true/false accepted", run(bools, {"FORCE": "false", "DRY_RUN": "true", "CONCURRENCY_DECLARED": "true"})["rc"] == 0)
        for bad in ("yes", "True", "1", ""):
            r = run(bools, {"FORCE": "false", "DRY_RUN": bad, "CONCURRENCY_DECLARED": "true"})
            check(f"dry_run={bad!r} refused", r["rc"] != 0 and "dry_run" in r["out"], r["out"])
    w = step("Warn about the caller's concurrency group")
    if w is not None:
        r = run(w, {"WORKER_SCRIPT": "w", "SLOT_A": "SIG_A", "CONCURRENCY_DECLARED": "false"})
        check("a direct caller gets a ::warning:: naming the group", "::warning::" in r["out"] and "rotate-external-w-SIG_A" in r["out"], r["out"])
        r = run(w, {"WORKER_SCRIPT": "w", "SLOT_A": "SIG_A", "CONCURRENCY_DECLARED": "true"})
        check("the wrapper gets a ::notice::", "::notice::" in r["out"] and "::warning::" not in r["out"], r["out"])


WRITE_STEPS = ("Generate secret", "Put Worker slot", "Write environment secret", "Record pending", "Dispatch sync",
               "Promote pending", "Adopt slot", "Retire old slot")


def structural_cases():
    print("\nrotate-external-secret action · shape")
    if not (ACTION / "action.yml").exists():
        check("action.yml exists", False)
        return
    doc = yaml.safe_load((ACTION / "action.yml").read_text())
    steps = doc["runs"]["steps"]
    runs = [s for s in steps if "run" in s]
    check("every run step names shell: bash", runs and all(s.get("shell") == "bash" for s in runs))
    check("every run step is a script beside action.yml",
          runs and all(re.fullmatch(r'"\$GITHUB_ACTION_PATH/[\w.-]+\.sh"', s["run"].strip()) for s in runs))
    check("no ${{ }} inside any run: body", not any(EXPR.search(s["run"]) for s in runs))
    texts = {p.name: p.read_text() for p in ACTION.glob("*.sh")}
    check(f"no script contains ${{{{ }}}} ({len(texts)} examined)", texts and not [n for n, t in texts.items() if "${{" in t])
    check("the value is never echoed or passed through GITHUB_OUTPUT by a script",
          not [n for n, t in texts.items() if re.search(r"new_secret<<", t)])
    check("no `set -x` in any script", not [n for n, t in texts.items() if re.search(r"^\s*set\s+-\w*x|set -o xtrace", t, re.M)])
    for s in steps:
        if "uses" in s:
            check(f"third-party action pinned to a 40-hex SHA: {s['uses'].split('@')[0]}", re.search(r"@[0-9a-f]{40}$", s["uses"]) is not None, s["uses"])
    for name in WRITE_STEPS:
        st = next((s for s in steps if s.get("name") == name), None)
        check(f"write step '{name}' is skipped on dry_run", st is not None and "inputs.dry_run != 'true'" in str(st.get("if", "")), st and st.get("if"))
        check(f"write step '{name}' passes DRY_RUN to the script", st is not None and "DRY_RUN" in st.get("env", {}), st and st.get("env"))
    check("the first step validates booleans", steps[0].get("name") == "Validate boolean inputs", steps[0].get("name"))
    for var in ("dry_run",):
        check(f"{var} defaults to 'true'", doc["inputs"].get(var, {}).get("default") == "true")
    check("force defaults to 'false'", doc["inputs"].get("force", {}).get("default") == "false")
    for k in ("cloudflare_api_token", "app_key", "app_id", "cf_account_id", "worker_script", "slot_a", "slot_b", "target_repo",
              "target_secret_name", "sync_workflow", "state_variable"):
        check(f"input {k} is required", doc["inputs"].get(k, {}).get("required") is True)
    defaults = {"target_environment": "prod", "sync_ref": "main", "sync_inputs_json": '{"dry_run":"false"}', "rotate_every_days": "30",
                "grace_hours": "24", "wait_minutes": "30", "secret_bytes": "32"}
    for k, v in defaults.items():
        check(f"input {k} defaults to {v!r}", doc["inputs"].get(k, {}).get("default") == v, doc["inputs"].get(k))
    mint = next((s for s in steps if "create-github-app-token" in s.get("uses", "")), {})
    check("the App token is minted for target + this repo with environments, actions, variables write",
          mint.get("with", {}).get("permission-environments") == "write" and mint.get("with", {}).get("permission-actions") == "write"
          and mint.get("with", {}).get("permission-variables") == "write", mint)
    check("the shred step runs always", next((s for s in steps if s.get("name") == "Shred secret"), {}).get("if") == "always()")
    check("the summary step runs always", next((s for s in steps if s.get("name") == "Summary"), {}).get("if") == "always()")
    check("the secret is never a step output", "new_secret" not in (ACTION / "action.yml").read_text())


def wrapper_cases():
    print("\nrotate-external-secret wrapper")
    if not WRAPPER.exists():
        check("wrapper exists", False)
        return
    doc = yaml.safe_load(WRAPPER.read_text())
    on = doc.get("on") or doc[True]
    inputs = on["workflow_call"]["inputs"]
    job = doc["jobs"]["rotate"]
    steps = job["steps"]
    calls = [s for s in steps if WRAPPER_USES.match(s.get("uses", ""))]
    check("the wrapper calls the action by its REMOTE vX.Y.Z ref", len(calls) == 1, [s.get("uses") for s in steps])
    check("no inline run: steps", not any("run" in s for s in steps))
    check("permissions: contents read only", doc.get("permissions") == {"contents": "read"}, doc.get("permissions"))
    check("concurrency group rotate-external-<worker_script>-<slot_a>, no cancel",
          doc["concurrency"] == {"group": "rotate-external-${{ inputs.worker_script }}-${{ inputs.slot_a }}", "cancel-in-progress": False}, doc.get("concurrency"))
    check("timeout-minutes = wait_minutes default (30) + 10", job.get("timeout-minutes") == inputs["wait_minutes"]["default"] + 10 == 40, job.get("timeout-minutes"))
    check("environment comes from the environment input", job.get("environment") == "${{ inputs.environment }}", job.get("environment"))
    check("WORKFLOW_VERSION is stamped", "WORKFLOW_VERSION" in doc.get("env", {}))
    check("secrets cloudflare_api_token and app_key are required",
          all(on["workflow_call"]["secrets"].get(k, {}).get("required") is True for k in ("cloudflare_api_token", "app_key")))
    check("dry_run defaults to true; force to false", inputs["dry_run"]["default"] is True and inputs["force"]["default"] is False)
    if len(calls) != 1:
        return
    with_ = calls[0].get("with", {})
    ad = yaml.safe_load((ACTION / "action.yml").read_text()) if (ACTION / "action.yml").exists() else {"inputs": {}}
    missing = sorted(set(inputs) - set(with_) - {"environment"})  # `environment` is the job's own key
    check("every workflow_call input (but environment) is forwarded", not missing, missing)
    check("every with: key is an input of the action", not sorted(set(with_) - set(ad["inputs"])), sorted(set(with_) - set(ad["inputs"])))
    same = [k for k in inputs if k in with_ and with_[k] != "${{ inputs.%s }}" % k]
    check("each input is passed through unchanged", not same, same)
    check("secrets are forwarded by static name", with_.get("cloudflare_api_token") == "${{ secrets.cloudflare_api_token }}"
          and with_.get("app_key") == "${{ secrets.app_key }}", with_)
    check("the wrapper sets concurrency_declared: 'true'", str(with_.get("concurrency_declared")).lower() == "true")


def main():
    for fn in (decide_cases, cloudflare_cases, gh_cases, wait_cases, flow_cases, inputs_cases, structural_cases, wrapper_cases):
        fn()
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES or CASES == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
