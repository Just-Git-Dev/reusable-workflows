"""service-alerts.yml step bodies, executed as shipped against stubbed curl.

Imported by run_alertgen_tests.py (which owns the check() / extract_step helpers).

Two bodies carry real logic:
  - "Resolve this workflow's own commit": decodes the job's OIDC token for job_workflow_sha,
    the exact commit of the called workflow, which is what the render checks out. A token
    without the claim must FAIL, never fall back to a branch or tag that could have moved.
  - "Check every rule has live data": a rule over a metric that does not exist passes every
    lint and can never fire. Zero series is CANNOT-VERIFY (fatal) unless the rule is
    may_be_absent, and zero series on EVERY probe means we looked in the wrong place.
"""
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SHA = "0123456789abcdef0123456789abcdef01234567"
REF = "Just-Git-Dev/reusable-workflows/.github/workflows/service-alerts.yml@refs/tags/v2.10.0"


def _b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")


def _jwt(claims):
    return f"{_b64({'alg': 'RS256'})}.{_b64(claims)}.sig"


def _run(body, env_extra, tmp, stub_py=None):
    stub = tmp / "bin"
    stub.mkdir(exist_ok=True)
    if stub_py is not None:
        (stub / "curl").write_text("#!/usr/bin/env python3\n" + stub_py)
        (stub / "curl").chmod(0o755)
    out = tmp / "gh_output"
    out.write_text("")
    env = dict(os.environ)
    env["PATH"] = f"{stub}:{env['PATH']}"
    env.update(RUNNER_TEMP=str(tmp), GITHUB_OUTPUT=str(out))
    env.update({k: str(v) for k, v in env_extra.items()})
    proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                          capture_output=True, text=True, env=env, cwd=tmp)
    outs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)
    return {"rc": proc.returncode, "out": proc.stdout + proc.stderr, "outputs": outs}


def run_resolve(body, claims=None, *, request_env=True, raw_response=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        resp = raw_response if raw_response is not None else json.dumps({"value": _jwt(claims or {})})
        (tmp / "resp.json").write_text(resp)
        stub = (f"import sys\n"
                f"open({str(tmp / 'argv.txt')!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                f"sys.stdout.write(open({str(tmp / 'resp.json')!r}).read())\n")
        env = {}
        if request_env:
            env = {"ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.example/x?api-version=2.0",
                   "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "reqtok"}
        r = _run(body, env, tmp, stub)
        argv = tmp / "argv.txt"
        r["argv"] = argv.read_text() if argv.exists() else ""
        return r


# curl stub for the data check: answers by matching a marker in the query.
DATA_STUB = r"""
import json, sys
args = sys.argv[1:]
out = args[args.index("-o") + 1]
query = next(a[len("query="):] for a in args if a.startswith("query="))
table = json.load(open(__TABLE__))
for marker, (code, body) in table.items():
    if marker in query:
        open(out, "w").write(json.dumps(body))
        sys.stdout.write(code)
        sys.exit(0)
open(out, "w").write(json.dumps({"status": "success", "data": {"result": []}}))
sys.stdout.write("200")
"""


def _series(label, *values):
    return {"status": "success", "data": {"resultType": "vector",
                                          "result": [{"metric": {label: v}, "value": [0, "1"]}
                                                     for v in values]}}


def run_datacheck(body, probes, table, *, token="tok"):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rd = tmp / "rendered"
        rd.mkdir()
        (rd / "probes.json").write_text(json.dumps(probes))
        (tmp / "table.json").write_text(json.dumps(table))
        stub = DATA_STUB.replace("__TABLE__", repr(str(tmp / "table.json")))
        return _run(body, {"RENDER_DIR": str(rd), "ACCESS_TOKEN": token, "GCP_PROJECT": "p"},
                    tmp, stub)


def _probe(rule, expr, *, may=False, services=("api",), label="job"):
    return {"rule_id": rule, "expr": expr, "may_be_absent": may, "services": list(services),
            "service_label": label, "policy_file": f"policy-{rule}.yaml"}


# gcloud stub for the end-to-end apply: live policies come from a JSON file.
GCLOUD_STUB = r"""
import json, re, sys
args = sys.argv[1:]
open(__ARGV__, "a").write(" ".join(args) + "\n")
live = json.load(open(__LIVE__))
if args[:4] == ["alpha", "monitoring", "policies", "list"]:
    flt = next((a[len("--filter="):] for a in args if a.startswith("--filter=")), "")
    m = re.search(r'userLabels\.rule_id="([^"]+)"', flt)
    if m:
        print(json.dumps([p for p in live if p["userLabels"].get("rule_id") == m.group(1)]))
    else:
        d = re.search(r'displayName="(.*)"$', flt)
        for p in live:
            if d and p["displayName"] == d.group(1):
                print(p["name"]); break
    sys.exit(0)
if args[:4] == ["alpha", "monitoring", "policies", "create"]:
    print("projects/p/alertPolicies/new"); sys.exit(0)
sys.exit(0)
"""


def run_e2e_apply(apply_body, rendered_dir, live, *, dry_run):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        (tmp / "live.json").write_text(json.dumps(live))
        (stub / "gcloud").write_text("#!/usr/bin/env python3\n" + GCLOUD_STUB
                                     .replace("__ARGV__", repr(str(tmp / "argv.txt")))
                                     .replace("__LIVE__", repr(str(tmp / "live.json"))))
        (stub / "gcloud").chmod(0o755)
        r = _run(apply_body, {"ALERTS_DIR": str(rendered_dir), "POLICY_GLOB": "policy-*.yaml",
                              "GCP_PROJECT": "p", "FORCE_UPDATE": "false",
                              "DRY_RUN": "true" if dry_run else "false",
                              "APPLIER_SA": "applier@p.iam.gserviceaccount.com",
                              "CHANNEL_NAME": "projects/p/notificationChannels/9"}, tmp)
        argv = tmp / "argv.txt"
        r["argv"] = argv.read_text() if argv.exists() else ""
        return r


def test_e2e(check):
    """alertgen's real output through bootstrap-alerts' real apply body."""
    import sys
    sys.path.insert(0, str(ROOT / "alerting"))
    from alertgen.compile import resolve
    from alertgen.render_gmp import render
    print("service-alerts · rendered policies through the shipped apply body")
    proc = subprocess.run(["python3", str(ROOT / "alerting" / "extract_step.py"),
                           str(ROOT / ".github" / "workflows" / "bootstrap-alerts.yml"),
                           "apply", "Apply alert policies"], capture_output=True, text=True)
    body = proc.stdout
    spec = yaml.safe_load((ROOT / "tests" / "alertgen" / "spec-full.yaml").read_text())
    out = render(resolve(spec), owner="acme_app")
    n = len(out.policies)
    with tempfile.TemporaryDirectory() as rd:
        rd = Path(rd)
        for fname, p in out.policies:
            (rd / fname).write_text(yaml.safe_dump(p, sort_keys=True, allow_unicode=True))
        r = run_e2e_apply(body, rd, [], dry_run=True)
        check("dry run over a fresh project plans a create for every policy",
              r["rc"] == 0 and r["out"].count("would create:") == n
              and " create " not in r["argv"].replace("list", ""), r["out"][-1500:])
        r = run_e2e_apply(body, rd, [], dry_run=False)
        check("apply over a fresh project creates every policy",
              r["rc"] == 0 and r["argv"].count("policies create") == n, r["out"][-1500:])

        # Live = what the API would hand back after that create: channel substituted, plus
        # server-filled fields the render never has. Must read as unchanged, with NO drift.
        live = []
        for i, (_, p) in enumerate(out.policies):
            lp = json.loads(json.dumps(p).replace("NOTIFICATION_CHANNEL_PLACEHOLDER",
                                                  "projects/p/notificationChannels/9"))
            lp["name"] = f"projects/p/alertPolicies/{i}"
            lp["creationRecord"] = {"mutateTime": "2026-09-23T00:00:00Z",
                                    "mutatedBy": "applier@p.iam.gserviceaccount.com"}
            lp["mutationRecord"] = dict(lp["creationRecord"])
            for j, c in enumerate(lp["conditions"]):
                c["name"] = f"{lp['name']}/conditions/{j}"
            live.append(lp)
        r = run_e2e_apply(body, rd, live, dry_run=False)
        check("re-apply of an unchanged spec updates nothing",
              r["rc"] == 0 and r["out"].count("unchanged:") == n
              and "policies update" not in r["argv"], r["out"][-1500:])
        check("server-filled fields do not read as drift",
              r["outputs"].get("drifted") == "0" and "hand-edited" not in r["out"],
              r["out"][-1500:])

        edited = json.loads(json.dumps(live))
        edited[0]["documentation"]["content"] += "\nhand note"
        r = run_e2e_apply(body, rd, edited, dry_run=True)
        check("a hand edit to a managed policy is reported as drift",
              r["outputs"].get("drifted") == "1", r["out"][-1500:])

        moved = json.loads(json.dumps(live))
        moved[1]["userLabels"]["spec_hash"] = "ffffffffffffffff"
        r = run_e2e_apply(body, rd, moved, dry_run=False)
        check("a changed spec_hash updates exactly that policy",
              r["argv"].count("policies update") == 1 and moved[1]["name"] in r["argv"],
              r["out"][-1500:])


def run(check, extract_step, service_yml):
    test_e2e(check)
    print("service-alerts · resolve own commit from the OIDC token")
    body = extract_step(service_yml, "alerts", "Resolve this workflow's own commit")
    r = run_resolve(body, {"job_workflow_ref": REF, "job_workflow_sha": SHA})
    check("resolves repo and sha from the token", r["rc"] == 0
          and r["outputs"].get("repo") == "Just-Git-Dev/reusable-workflows"
          and r["outputs"].get("sha") == SHA, r)
    check("requests the token with an explicit audience", "audience=" in r["argv"], r["argv"])
    r = run_resolve(body, {"job_workflow_ref": REF})
    check("a token without job_workflow_sha fails (no fallback to a movable ref)",
          r["rc"] != 0 and "job_workflow_sha" in r["out"], r)
    r = run_resolve(body, {"job_workflow_ref": REF, "job_workflow_sha": "main"})
    check("a non-40-hex sha fails", r["rc"] != 0, r)
    r = run_resolve(body, {"job_workflow_ref": "garbage", "job_workflow_sha": SHA})
    check("an unparseable job_workflow_ref fails", r["rc"] != 0, r)
    r = run_resolve(body, request_env=False)
    check("missing id-token permission fails with the fix named",
          r["rc"] != 0 and "id-token: write" in r["out"], r)
    r = run_resolve(body, raw_response='{"message":"denied"}')
    check("a token endpoint error fails", r["rc"] != 0, r)

    print("service-alerts · live data check")
    body = extract_step(service_yml, "alerts", "Check every rule has live data")
    probes = [_probe("a", "MARK_A"), _probe("b", "MARK_B")]
    r = run_datacheck(body, probes, {"MARK_A": ["200", _series("job", "api")],
                                     "MARK_B": ["200", _series("job", "api")]})
    check("all probes with data passes", r["rc"] == 0 and r["outputs"].get("probes_checked") == "2"
          and r["outputs"].get("probes_with_data") == "2", r)
    r = run_datacheck(body, probes, {"MARK_A": ["200", _series("job", "api")]})
    check("a probe with zero series is CANNOT VERIFY (fatal)",
          r["rc"] != 0 and "CANNOT VERIFY" in r["out"] and "b" in r["out"], r)
    probes_m = [_probe("a", "MARK_A"), _probe("b", "MARK_B", may=True)]
    r = run_datacheck(body, probes_m, {"MARK_A": ["200", _series("job", "api")]})
    check("zero series on a may_be_absent rule only warns",
          r["rc"] == 0 and "::warning::" in r["out"], r)
    r = run_datacheck(body, probes_m, {})
    check("zero series on EVERY probe is CANNOT VERIFY even if may_be_absent (wrong place?)",
          r["rc"] != 0 and "wrong project" in r["out"], r)
    r = run_datacheck(body, probes, {"MARK_A": ["403", {"error": {"message": "denied"}}]})
    check("HTTP 403 is CANNOT VERIFY, not zero-and-fine", r["rc"] != 0 and "403" in r["out"], r)
    r = run_datacheck(body, probes, {"MARK_A": ["200", {"status": "error", "error": "bad"}],
                                     "MARK_B": ["200", _series("job", "api")]})
    check("a 200 with an error envelope fails", r["rc"] != 0, r)
    two = [_probe("a", "MARK_A", services=("api", "issuer"))]
    r = run_datacheck(body, two, {"MARK_A": ["200", _series("job", "api")]})
    check("a service with no data in the lookback is named in a warning",
          r["rc"] == 0 and "issuer" in r["out"] and "::warning::" in r["out"], r)
    r = run_datacheck(body, probes, {}, token="")
    check("no access token is CANNOT VERIFY", r["rc"] != 0, r)

    print("service-alerts · shared bodies and workflow shape")
    doc = yaml.safe_load(service_yml.read_text())
    steps = doc["jobs"]["alerts"]["steps"]
    text = service_yml.read_text()
    for u in re.findall(r"uses:\s*(\S+)", text):
        check(f"{u} is SHA-pinned", re.search(r"@[0-9a-f]{40}$", u) is not None, u)
    perms = doc.get("permissions") or {}
    check("permissions declared explicitly", perms == {"contents": "read", "id-token": "write"},
          perms)
    self_co = [s for s in steps if s.get("with", {}).get("path") == ".alertgen-src"]
    check("checks itself out at the resolved sha",
          len(self_co) == 1 and "steps.self.outputs.sha" in str(self_co[0]["with"].get("ref"))
          and "steps.self.outputs.repo" in str(self_co[0]["with"].get("repository")), self_co)
    shared = re.findall(r'extract_step\.py"\s+"\S+/([a-z-]+\.yml)"\s+(\S+)\s+"([^"]+)"', text)
    check("runs the four shared bodies", len(shared) == 4, shared)
    wf = ROOT / ".github" / "workflows"
    for f, job, name in shared:
        proc = subprocess.run(["python3", str(ROOT / "alerting" / "extract_step.py"),
                               str(wf / f), job, name], capture_output=True, text=True)
        check(f"shared body {f}:{name} extracts cleanly (exists, no ${{{{ }}}})",
              proc.returncode == 0 and proc.stdout.strip(), proc.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "w.yml"
        p.write_text(yaml.safe_dump({"jobs": {"j": {"steps": [
            {"name": "s", "run": "echo ${{ inputs.x }}"}]}}}))
        proc = subprocess.run(["python3", str(ROOT / "alerting" / "extract_step.py"),
                               str(p), "j", "s"], capture_output=True, text=True)
        check("extract_step refuses a body with an expression it cannot evaluate",
              proc.returncode != 0 and "${{" in proc.stderr, proc)
