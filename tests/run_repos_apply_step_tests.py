#!/usr/bin/env python3
"""Stubbed-command tests for the APPLY bash of repos-create.yml (F2), repos-wif-link.yml (F5) and
repos-deploy-scope.yml (F7).

The `run:` body is extracted as shipped (as tests/run_step_tests.py does) and run under
`bash -eo pipefail` with stub `gh` / `gcloud` on PATH. A stub appends one line per call (argv joined
by \\x1f) to a log; FAIL_ON=<n> makes the n-th call exit 1. Asserted per feature:
  - a report-mode plan (non-writing verbs only) calls no write endpoint / gcloud verb;
  - an enforce plan calls exactly the planned writes, in order, nothing else;
  - a verb outside the feature's allow-list fails the step before ANY call;
  - the first failing call stops the loop;
  - values holding shell metacharacters or spaces arrive as ONE literal argument and never run.

Usage:  python3 tests/run_repos_apply_step_tests.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
SEP = "\x1f"
FAILURES = []
RAN = 0

CREATE_STEP = "Apply the write actions in order"
WIF_STEP = "Apply (add-wif-binding only, in order)"
DEPLOY_STEP = "Apply (write actions, in order)"

STUB = """#!/bin/bash
n=$(( $(cat "$STUB_DIR/count" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$STUB_DIR/count"
{ printf '%s\\x1f' "$(basename "$0")" "$@"; echo; } >> "$STUB_DIR/calls.log"
[ "${FAIL_ON:-0}" = "$n" ] && { echo "stub: forced failure on call $n" >&2; exit 1; }
exit 0
"""


def extract_step(workflow, step_name):
    doc = yaml.safe_load((WF / workflow).read_text())
    for job in doc["jobs"].values():
        for step in job["steps"]:
            if step.get("name") == step_name:
                return step["run"]
    raise SystemExit(f"step '{step_name}' not found in {workflow}")


def run_apply(body, plan, *, env=None, fail_on=0):
    """Run the body in a scratch dir holding plan.json (also $RUNNER_TEMP); return rc, output,
    the stubbed calls (list of argv lists) and the files left in the working dir."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for d in ("bin", "stub", "work"):
            (tmp / d).mkdir()
        for name in ("gh", "gcloud"):
            f = tmp / "bin" / name
            f.write_text(STUB)
            f.chmod(0o755)
        (tmp / "work" / "plan.json").write_text(json.dumps(plan))
        e = dict(os.environ)
        e.update({"PATH": f"{tmp / 'bin'}:{e['PATH']}", "STUB_DIR": str(tmp / "stub"),
                  "RUNNER_TEMP": str(tmp / "work"), "GITHUB_STEP_SUMMARY": str(tmp / "summary.md"),
                  "FAIL_ON": str(fail_on)})
        e.update(env or {})
        p = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                           capture_output=True, text=True, env=e, cwd=tmp / "work")
        log = tmp / "stub" / "calls.log"
        calls = [l.split(SEP)[:-1] for l in log.read_text().splitlines()] if log.exists() else []
        return {"rc": p.returncode, "out": p.stdout + p.stderr, "calls": calls,
                "files": sorted(x.name for x in (tmp / "work").iterdir())}


def check(name, cond, detail=""):
    global RAN
    RAN += 1
    if not cond:
        FAILURES.append(name)
        print(f"FAIL {name}\n     {detail}")


def act(feature, repo, action, details):
    return {"feature": feature, "repo": repo, "action": action, "details": details}


NASTY = ["$(touch pwned)", "`touch pwned`", "a;touch pwned", "has space", "q'uote\"s", "a|b&c>d"]


# ---------------------------------------------------------------- F2 repos-create
def create_run(plan, **kw):
    return run_apply(extract_step("repos-create.yml", CREATE_STEP), plan, env={"ORG": "Example-Org"}, **kw)


def create_cases():
    cr = lambda r, d="": act("create", r, "create-repo", {"visibility": "private", "description": d})
    mv = lambda a, b: act("create", b, "rename-repo", {"from": a, "to": b})

    r = create_run([act("create", "a", "in-sync", {}), act("create", "b", "skip", {}),
                    act("create", "c", "drift", {"would": "create-repo"}),
                    act("create", "d", "unsupported", {})])
    check("F2 report plan: rc 0", r["rc"] == 0, r["out"])
    check("F2 report plan: no gh call", r["calls"] == [], r["calls"])

    r = create_run([cr("payments-api", "Pay things"), act("create", "x", "in-sync", {}),
                    mv("old-name", "new-name"), cr("ledger")])
    check("F2 enforce: rc 0", r["rc"] == 0, r["out"])
    check("F2 enforce: exactly the planned calls in order", r["calls"] == [
        ["gh", "api", "-X", "POST", "orgs/Example-Org/repos", "-f", "name=payments-api",
         "-f", "visibility=private", "-F", "auto_init=false", "-f", "description=Pay things"],
        ["gh", "api", "-X", "PATCH", "repos/Example-Org/old-name", "-f", "name=new-name"],
        ["gh", "api", "-X", "POST", "orgs/Example-Org/repos", "-f", "name=ledger",
         "-f", "visibility=private", "-F", "auto_init=false"],
    ], r["calls"])

    for bad in ("delete-repo", "archive-repo", "make-public", "transfer-repo"):
        r = create_run([cr("one"), act("create", "two", bad, {}), cr("three")])
        check(f"F2 verb {bad}: step fails", r["rc"] != 0, r["out"])
        check(f"F2 verb {bad}: no call made (even the valid action before it)", r["calls"] == [], r["calls"])

    r = create_run([cr("one"), cr("two"), cr("three")], fail_on=2)
    check("F2 first failure: rc != 0", r["rc"] != 0, r["out"])
    check("F2 first failure: loop stopped after the failing call", len(r["calls"]) == 2, r["calls"])

    for v in NASTY:
        r = create_run([cr(v, v), mv(v, v + "2")])
        check(f"F2 metachar {v!r}: rc 0", r["rc"] == 0, r["out"])
        check(f"F2 metachar {v!r}: nothing executed", "pwned" not in r["files"], r["files"])
        check(f"F2 metachar {v!r}: literal single arguments", r["calls"] == [
            ["gh", "api", "-X", "POST", "orgs/Example-Org/repos", "-f", f"name={v}",
             "-f", "visibility=private", "-F", "auto_init=false", "-f", f"description={v}"],
            ["gh", "api", "-X", "PATCH", f"repos/Example-Org/{v}", "-f", f"name={v}2"],
        ], r["calls"])


# ---------------------------------------------------------------- F5 repos-wif-link
ROLE = "roles/iam.workloadIdentityUser"
MEMBER = "principalSet://iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/attribute.repository/Example-Org/%s"


def wif_run(plan, **kw):
    return run_apply(extract_step("repos-wif-link.yml", WIF_STEP), plan,
                     env={"PROJECT_ID": "example-proj"}, **kw)


def wif_call(sa, member, role=ROLE):
    return ["gcloud", "iam", "service-accounts", "add-iam-policy-binding",
            f"{sa}@example-proj.iam.gserviceaccount.com", f"--member={member}", f"--role={role}",
            "--project=example-proj", "--quiet"]


def wif_cases():
    add = lambda sa, mem, role=ROLE: act("wif-link", "r", "add-wif-binding",
                                         {"service_account": sa, "member": mem, "role": role})

    r = wif_run([act("wif-link", "r", "in-sync", {}),
                 act("wif-link", "r", "unregistered-binding",
                     {"service_account": "s", "role": "roles/viewer", "member": "user:x"}),
                 act("wif-link", "r", "drift", {"would": "add-wif-binding"})])
    check("F5 report plan: rc 0", r["rc"] == 0, r["out"])
    check("F5 report plan: no gcloud call", r["calls"] == [], r["calls"])

    r = wif_run([add("sa-one", MEMBER % "a"), act("wif-link", "r", "in-sync", {}), add("sa-two", MEMBER % "b")])
    check("F5 enforce: rc 0", r["rc"] == 0, r["out"])
    check("F5 enforce: exactly the planned calls in order", r["calls"] == [
        wif_call("sa-one", MEMBER % "a"), wif_call("sa-two", MEMBER % "b")], r["calls"])

    for bad in ("remove-wif-binding", "create-sa-key", "grant-project-role", "delete-sa"):
        r = wif_run([add("sa-one", MEMBER % "a"), act("wif-link", "r", bad, {}), add("sa-two", MEMBER % "b")])
        check(f"F5 verb {bad}: step fails", r["rc"] != 0, r["out"])
        check(f"F5 verb {bad}: no call made", r["calls"] == [], r["calls"])

    r = wif_run([add("sa-one", MEMBER % "a"), add("sa-two", MEMBER % "b", "roles/owner")])
    check("F5 foreign role: step fails", r["rc"] != 0, r["out"])
    check("F5 foreign role: no call made (even the valid action before it)", r["calls"] == [], r["calls"])

    r = wif_run([add("sa-one", MEMBER % "a"), add("sa-two", MEMBER % "b"), add("sa-three", MEMBER % "c")], fail_on=2)
    check("F5 first failure: rc != 0", r["rc"] != 0, r["out"])
    check("F5 first failure: loop stopped after the failing call", len(r["calls"]) == 2, r["calls"])

    for v in NASTY:
        r = wif_run([add(v, v)])
        check(f"F5 metachar {v!r}: rc 0", r["rc"] == 0, r["out"])
        check(f"F5 metachar {v!r}: nothing executed", "pwned" not in r["files"], r["files"])
        check(f"F5 metachar {v!r}: literal single arguments", r["calls"] == [wif_call(v, v)], r["calls"])


# ---------------------------------------------------------------- F7 repos-deploy-scope
RUN_DEV, SA_USER, GAR_W = ("roles/run.developer", "roles/iam.serviceAccountUser",
                           "roles/artifactregistry.writer")
DEPLOYER = "serviceAccount:payments-api-deployer@example-proj.iam.gserviceaccount.com"
ADMIN = "serviceAccount:repo-admin@example-proj.iam.gserviceaccount.com"
SUFFIX = "@example-proj.iam.gserviceaccount.com"


def deploy_run(plan, **kw):
    return run_apply(extract_step("repos-deploy-scope.yml", DEPLOY_STEP), plan,
                     env={"PROJECT_ID": "example-proj", "PLACEHOLDER_IMAGE": "img.example/hello"}, **kw)


def d_create(svc="payments-api", region="europe-west1", rt="payments-api-run"):
    return act("deploy-scope", "r", "create-service", {
        "service": svc, "region": region, "runtime_service_account": rt, "image": "placeholder"})


def d_bind(rtype, res, role, mem, region=None):
    d = {"resource_type": rtype, "resource": res, "role": role, "member": mem}
    if region:
        d["region"] = region
    return act("deploy-scope", "r", "add-resource-binding", d)


def d_run(svc="payments-api", region="europe-west1", mem=DEPLOYER, role=RUN_DEV):
    return d_bind("run.service", svc, role, mem, region)


def d_sa(res="payments-api-run" + SUFFIX, mem=DEPLOYER, role=SA_USER):
    return d_bind("iam.serviceAccount", res, role, mem)


def d_gar(res="europe-west1/services", mem=DEPLOYER, role=GAR_W):
    return d_bind("artifactregistry.repository", res, role, mem)


def g_bind(kind, res, mem, role, extra=()):
    return ["gcloud", *kind, res, *extra, f"--member={mem}", f"--role={role}",
            "--project=example-proj", "--quiet"]


def deploy_cases():
    r = deploy_run([act("deploy-scope", "r", "in-sync", {}), act("deploy-scope", "r", "skip", {}),
                    act("deploy-scope", "r", "unsupported", {"key": "gke", "reason": "x"}),
                    act("deploy-scope", "r", "drift", {"would": "create-service"})])
    check("F7 report plan: rc 0", r["rc"] == 0, r["out"])
    check("F7 report plan: no gcloud call", r["calls"] == [], r["calls"])

    r = deploy_run([d_sa(mem=ADMIN), act("deploy-scope", "r", "in-sync", {}), d_create(),
                    d_run(), d_sa(), d_gar()])
    check("F7 enforce: rc 0", r["rc"] == 0, r["out"])
    check("F7 enforce: exactly the planned calls in order", r["calls"] == [
        g_bind(["iam", "service-accounts", "add-iam-policy-binding"], "payments-api-run" + SUFFIX, ADMIN, SA_USER),
        ["gcloud", "run", "deploy", "payments-api", "--image=img.example/hello",
         "--service-account=payments-api-run" + SUFFIX, "--region=europe-west1",
         "--no-allow-unauthenticated", "--project=example-proj", "--quiet"],
        g_bind(["run", "services", "add-iam-policy-binding"], "payments-api", DEPLOYER, RUN_DEV,
               ["--region=europe-west1"]),
        g_bind(["iam", "service-accounts", "add-iam-policy-binding"], "payments-api-run" + SUFFIX, DEPLOYER, SA_USER),
        ["gcloud", "artifacts", "repositories", "add-iam-policy-binding", "services",
         "--location=europe-west1", f"--member={DEPLOYER}", f"--role={GAR_W}",
         "--project=example-proj", "--quiet"],
    ], r["calls"])

    for bad in ("apply-k8s-rbac", "delete-service", "create-sa-key", "grant-project-role", "legacy-grant"):
        r = deploy_run([d_run(), act("deploy-scope", "r", bad, {}), d_sa()])
        check(f"F7 verb {bad}: step fails", r["rc"] != 0, r["out"])
        check(f"F7 verb {bad}: no call made (even the valid action before it)", r["calls"] == [], r["calls"])

    foreign = {
        "run.service with roles/run.admin": d_run(role="roles/run.admin"),
        "run.service with roles/owner": d_run(role="roles/owner"),
        "run.service with serviceAccountUser": d_run(role=SA_USER),
        "serviceAccount with roles/iam.serviceAccountTokenCreator": d_sa(role="roles/iam.serviceAccountTokenCreator"),
        "serviceAccount with roles/owner": d_sa(role="roles/owner"),
        "repository with roles/artifactregistry.admin": d_gar(role="roles/artifactregistry.admin"),
        "project resource type": d_bind("project", "example-proj", RUN_DEV, DEPLOYER),
        "user member": d_run(mem="user:someone@example.com"),
        "run.service without a region": d_bind("run.service", "payments-api", RUN_DEV, DEPLOYER),
    }
    for label, bad in foreign.items():
        r = deploy_run([d_sa(), bad, d_gar()])
        check(f"F7 foreign binding ({label}): step fails", r["rc"] != 0, r["out"])
        check(f"F7 foreign binding ({label}): no call made (even the valid actions around it)",
              r["calls"] == [], r["calls"])

    r = deploy_run([d_sa(), d_run(), d_gar()], fail_on=2)
    check("F7 first failure: rc != 0", r["rc"] != 0, r["out"])
    check("F7 first failure: loop stopped after the failing call", len(r["calls"]) == 2, r["calls"])

    # names that reach a command line must have the planner's shape; anything else never runs
    for v in NASTY + ["--ingress=all", "-x"]:
        for label, plan in (("service", [d_create(svc=v)]), ("region", [d_create(region=v)]),
                            ("runtime SA", [d_create(rt=v)]), ("binding service", [d_run(svc=v)]),
                            ("binding region", [d_run(region=v)])):
            r = deploy_run(plan)
            check(f"F7 malformed {label} {v!r}: step fails, no call, nothing executed",
                  r["rc"] != 0 and r["calls"] == [] and "pwned" not in r["files"], (r["rc"], r["calls"]))

    # free-form fields (member suffix, SA email, GAR path) arrive as ONE literal argument
    for v in NASTY:
        r = deploy_run([d_sa(res=v, mem="serviceAccount:" + v), d_gar(res="loc/" + v, mem="serviceAccount:" + v)])
        check(f"F7 metachar {v!r}: rc 0", r["rc"] == 0, r["out"])
        check(f"F7 metachar {v!r}: nothing executed", "pwned" not in r["files"], r["files"])
        check(f"F7 metachar {v!r}: literal single arguments", r["calls"] == [
            g_bind(["iam", "service-accounts", "add-iam-policy-binding"], v, "serviceAccount:" + v, SA_USER),
            ["gcloud", "artifacts", "repositories", "add-iam-policy-binding", v, "--location=loc",
             f"--member=serviceAccount:{v}", f"--role={GAR_W}", "--project=example-proj", "--quiet"],
        ], r["calls"])


def main():
    create_cases()
    wif_cases()
    deploy_cases()
    print(f"repos apply step tests: {RAN} cases run, {RAN - len(FAILURES)} passed, {len(FAILURES)} failed")
    if RAN == 0 or FAILURES:
        sys.exit(1)


main()
