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
SA_STEP = "Apply (create/update service accounts only, in order)"

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

    r = wif_run([add("one-aa-deployer", MEMBER % "a"), act("wif-link", "r", "in-sync", {}), add("two-bb-deployer", MEMBER % "b")])
    check("F5 enforce: rc 0", r["rc"] == 0, r["out"])
    check("F5 enforce: exactly the planned calls in order", r["calls"] == [
        wif_call("one-aa-deployer", MEMBER % "a"), wif_call("two-bb-deployer", MEMBER % "b")], r["calls"])

    for bad in ("remove-wif-binding", "create-sa-key", "grant-project-role", "delete-sa"):
        r = wif_run([add("one-aa-deployer", MEMBER % "a"), act("wif-link", "r", bad, {}), add("two-bb-deployer", MEMBER % "b")])
        check(f"F5 verb {bad}: step fails", r["rc"] != 0, r["out"])
        check(f"F5 verb {bad}: no call made", r["calls"] == [], r["calls"])

    r = wif_run([add("one-aa-deployer", MEMBER % "a"), add("two-bb-deployer", MEMBER % "b", "roles/owner")])
    check("F5 foreign role: step fails", r["rc"] != 0, r["out"])
    check("F5 foreign role: no call made (even the valid action before it)", r["calls"] == [], r["calls"])

    r = wif_run([add("one-aa-deployer", MEMBER % "a"), add("two-bb-deployer", MEMBER % "b"), add("three-cc-deployer", MEMBER % "c")], fail_on=2)
    check("F5 first failure: rc != 0", r["rc"] != 0, r["out"])
    check("F5 first failure: loop stopped after the failing call", len(r["calls"]) == 2, r["calls"])

    # the member (free-form) arrives as ONE literal argument; the SA name must have the planner's shape
    for v in NASTY:
        r = wif_run([add("one-aa-deployer", v)])
        check(f"F5 metachar member {v!r}: rc 0", r["rc"] == 0, r["out"])
        check(f"F5 metachar member {v!r}: nothing executed", "pwned" not in r["files"], r["files"])
        check(f"F5 metachar member {v!r}: literal single argument",
              r["calls"] == [wif_call("one-aa-deployer", v)], r["calls"])
        r = wif_run([add(v, MEMBER % "a")])
        check(f"F5 malformed SA {v!r}: step fails, no call, nothing executed",
              r["rc"] != 0 and r["calls"] == [] and "pwned" not in r["files"], (r["rc"], r["calls"]))

    # review 9: the whole plan is re-checked for the `-deployer` suffix before any write (as F7 does)
    for label, sa_name in (("repo-admin", "repo-admin"), ("runtime SA", "payments-api-run"),
                           ("deployer-in-the-middle", "x-deployer-aa"), ("trailing newline", "aa-deployer\n")):
        r = wif_run([add("one-aa-deployer", MEMBER % "a"), add(sa_name, MEMBER % "b")])
        check(f"F5 non-deployer SA ({label}): step fails", r["rc"] != 0, r["out"])
        check(f"F5 non-deployer SA ({label}): no call made (even the valid action before it)",
              r["calls"] == [], r["calls"])


# ---------------------------------------------------------------- F6 repos-service-accounts
def sa_run(plan, **kw):
    return run_apply(extract_step("repos-service-accounts.yml", SA_STEP), plan,
                     env={"PROJECT_ID": "example-proj"}, **kw)


def sa_cases():
    mk = lambda n: act("service-accounts", None, "create-service-account",
                       {"name": n, "display_name": "D", "description": "desc"})
    r = sa_run([mk("one-aa-deployer"), act("service-accounts", None, "in-sync", {}), mk("two-bb-deployer")])
    check("F6 enforce: rc 0", r["rc"] == 0, r["out"])
    check("F6 enforce: two creates in order", [c[3] for c in r["calls"]] == ["create"] * 2
          and [c[4] for c in r["calls"]] == ["one-aa-deployer", "two-bb-deployer"], r["calls"])
    for label, n in (("repo-admin", "repo-admin"), ("github-releaser", "github-releaser"),
                     ("runtime SA", "payments-api-run"), ("trailing newline", "aa-deployer\n")):
        r = sa_run([mk("one-aa-deployer"), mk(n)])
        check(f"F6 non-deployer SA ({label}): step fails", r["rc"] != 0, r["out"])
        check(f"F6 non-deployer SA ({label}): no call made (even the valid action before it)",
              r["calls"] == [], r["calls"])
    upd = lambda n: act("service-accounts", None, "update-service-account",
                        {"name": n, "field": "description", "from": "a", "to": "b"})
    r = sa_run([upd("repo-admin")])
    check("F6 update of a non-deployer SA: step fails, no call", r["rc"] != 0 and r["calls"] == [], r["out"])
    r = sa_run([upd("one-aa-deployer")])
    check("F6 update of a deployer SA: one call", r["rc"] == 0 and len(r["calls"]) == 1, r["out"])


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

    r = deploy_run([act("deploy-scope", "r", "needs-jgd", {"needs": "deployed_by: payments-api-deployer"}),
                    act("deploy-scope", "r", "in-sync", {}), d_create(),
                    d_run(), d_gar()])
    check("F7 enforce: rc 0", r["rc"] == 0, r["out"])
    check("F7 enforce: exactly the planned calls in order", r["calls"] == [
        ["gcloud", "run", "deploy", "payments-api", "--image=img.example/hello",
         "--service-account=payments-api-run" + SUFFIX, "--region=europe-west1",
         "--no-allow-unauthenticated", "--project=example-proj", "--quiet"],
        g_bind(["run", "services", "add-iam-policy-binding"], "payments-api", DEPLOYER, RUN_DEV,
               ["--region=europe-west1"]),
        ["gcloud", "artifacts", "repositories", "add-iam-policy-binding", "services",
         "--location=europe-west1", f"--member={DEPLOYER}", f"--role={GAR_W}",
         "--project=example-proj", "--quiet"],
    ], r["calls"])

    for bad in ("apply-k8s-rbac", "delete-service", "create-sa-key", "grant-project-role", "legacy-grant"):
        r = deploy_run([d_run(), act("deploy-scope", "r", bad, {}), d_gar()])
        check(f"F7 verb {bad}: step fails", r["rc"] != 0, r["out"])
        check(f"F7 verb {bad}: no call made (even the valid action before it)", r["calls"] == [], r["calls"])

    foreign = {
        "run.service with roles/run.admin": d_run(role="roles/run.admin"),
        "run.service with roles/owner": d_run(role="roles/owner"),
        "run.service with serviceAccountUser": d_run(role=SA_USER),
        "serviceAccount with roles/iam.serviceAccountUser (ruling 21: F7 writes no SA policy)": d_sa(),
        "serviceAccount with repo-admin self-grant": d_sa(mem=ADMIN),
        "serviceAccount with roles/iam.serviceAccountTokenCreator": d_sa(role="roles/iam.serviceAccountTokenCreator"),
        "serviceAccount with roles/owner": d_sa(role="roles/owner"),
        "repository with roles/artifactregistry.admin": d_gar(role="roles/artifactregistry.admin"),
        "project resource type": d_bind("project", "example-proj", RUN_DEV, DEPLOYER),
        "user member": d_run(mem="user:someone@example.com"),
        "run.service without a region": d_bind("run.service", "payments-api", RUN_DEV, DEPLOYER),
    }
    for label, bad in foreign.items():
        r = deploy_run([d_gar(), bad, d_gar()])
        check(f"F7 foreign binding ({label}): step fails", r["rc"] != 0, r["out"])
        check(f"F7 foreign binding ({label}): no call made (even the valid actions around it)",
              r["calls"] == [], r["calls"])

    r = deploy_run([d_run(), d_gar(), d_gar(res="europe-west1/other")], fail_on=2)
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

    # M1: jq's `$` matches before a trailing newline, so a newline-suffixed name must still be refused
    for label, plan in (("service", [d_create(svc="payments-api\n")]),
                        ("region", [d_create(region="europe-west1\n")]),
                        ("runtime SA", [d_create(rt="payments-api-run\n")]),
                        ("binding service", [d_run(svc="payments-api\n")]),
                        ("binding region", [d_run(region="europe-west1\n")])):
        r = deploy_run(plan)
        check(f"F7 trailing newline {label}: step fails, no call",
              r["rc"] != 0 and r["calls"] == [], (r["rc"], r["calls"]))

    # free-form fields (member suffix, SA email, GAR path) arrive as ONE literal argument
    for v in NASTY:
        r = deploy_run([d_gar(res="loc/" + v, mem="serviceAccount:" + v)])
        check(f"F7 metachar {v!r}: rc 0", r["rc"] == 0, r["out"])
        check(f"F7 metachar {v!r}: nothing executed", "pwned" not in r["files"], r["files"])
        check(f"F7 metachar {v!r}: literal single arguments", r["calls"] == [
            ["gcloud", "artifacts", "repositories", "add-iam-policy-binding", v, "--location=loc",
             f"--member=serviceAccount:{v}", f"--role={GAR_W}", "--project=example-proj", "--quiet"],
        ], r["calls"])


SECRETS_STEP = "Apply (secrets and their policy lines only, in order)"
S_ACC = "roles/secretmanager.secretAccessor"
S_MGR = "roles/secretmanager.secretVersionManager"
S_VIEW = "roles/secretmanager.viewer"
S_RUN = "serviceAccount:payments-api-run" + SUFFIX
S_DEP = "serviceAccount:payments-api-deployer" + SUFFIX


def secrets_run(plan, prune="false", replication="automatic", **kw):
    return run_apply(extract_step("repos-secrets.yml", SECRETS_STEP), plan,
                     env={"PROJECT_ID": "example-proj", "PRUNE": prune, "REPLICATION": replication}, **kw)


def s_create(secret="payments-api-env", d="payments-api"):
    return act("secrets", "r", "create-secret", {
        "secret": secret, "labels": {"managed-by": "repos-secrets", "deployable": d}})


def s_bind(verb="add-secret-binding", secret="payments-api-env", role=S_ACC, mem=S_RUN):
    return act("secrets", "r", verb, {"secret": secret, "role": role, "member": mem})


def s_call(sub, secret, role, mem):
    return ["gcloud", "secrets", sub, secret, f"--member={mem}", f"--role={role}",
            "--project=example-proj", "--quiet"]


FETCH_STUB = """#!/bin/bash
case "$*" in
  *"secrets get-iam-policy"*) cat "$POLICY_FILE" ;;
  *) echo '{}' ;;
esac
"""


def fetch_run(policy):
    """Run the shipped 'Fetch live state' step with a gcloud stub answering describe with {} and
    get-iam-policy with `policy`; return rc, output and the files left in the working dir."""
    body = extract_step("repos-secrets.yml", "Fetch live state")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "bin").mkdir()
        (tmp / "work").mkdir()
        g = tmp / "bin" / "gcloud"
        g.write_text(FETCH_STUB)
        g.chmod(0o755)
        (tmp / "policy.json").write_text(json.dumps(policy))
        (tmp / "work" / "register.yml").write_text(
            "repos:\n- name: r\n  deploys:\n  - {cloud_run: payments-api, env_secret: true}\n")
        e = dict(os.environ)
        e.update({"PATH": f"{tmp / 'bin'}:{e['PATH']}", "PROJECT_ID": "example-proj",
                  "REGISTER": "register.yml", "POLICY_FILE": str(tmp / "policy.json")})
        p = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                           capture_output=True, text=True, env=e, cwd=tmp / "work")
        return {"rc": p.returncode, "out": p.stdout + p.stderr,
                "files": sorted(x.name for x in (tmp / "work").iterdir())}


def fetch_cases():
    plain = {"bindings": [{"role": S_ACC, "members": [S_RUN]}]}
    r = fetch_run(plain)
    check("F8 fetch positive control: unconditional policy -> state.json written",
          r["rc"] == 0 and "state.json" in r["files"], (r["rc"], r["out"]))
    cond = {"bindings": [{"role": S_ACC, "members": [S_RUN]},
                         {"role": S_ACC, "members": [S_DEP],
                          "condition": {"title": "t", "expression": "true"}}]}
    r = fetch_run(cond)
    check("F8 fetch refuses a <d>-env policy carrying an IAM condition (error, no state written)",
          r["rc"] != 0 and "state.json" not in r["files"] and "condition" in r["out"], (r["rc"], r["out"]))


def secrets_cases():
    fetch_cases()
    r = secrets_run([act("secrets", "r", "in-sync", {}), act("secrets", "r", "adopt", {"secret": "x-env"}),
                     act("secrets", "r", "needs-jgd", {}),
                     act("secrets", "r", "drift", {"would": "create-secret"})])
    check("F8 report plan: rc 0", r["rc"] == 0, r["out"])
    check("F8 report plan: no gcloud call", r["calls"] == [], r["calls"])

    r = secrets_run([s_create(), s_bind(), s_bind(role=S_ACC, mem=S_DEP), s_bind(role=S_MGR, mem=S_DEP),
                     s_bind(role=S_VIEW, mem=S_DEP)])
    check("F8 enforce: rc 0", r["rc"] == 0, r["out"])
    check("F8 enforce: exactly the planned calls in order", r["calls"] == [
        ["gcloud", "secrets", "create", "payments-api-env", "--replication-policy=automatic",
         "--labels=managed-by=repos-secrets,deployable=payments-api", "--project=example-proj", "--quiet"],
        s_call("add-iam-policy-binding", "payments-api-env", S_ACC, S_RUN),
        s_call("add-iam-policy-binding", "payments-api-env", S_ACC, S_DEP),
        s_call("add-iam-policy-binding", "payments-api-env", S_MGR, S_DEP),
        s_call("add-iam-policy-binding", "payments-api-env", S_VIEW, S_DEP),
    ], r["calls"])

    r = secrets_run([s_create()], replication="europe-west1")
    check("F8 user-managed replication: region passed as one argument", r["rc"] == 0 and r["calls"] == [
        ["gcloud", "secrets", "create", "payments-api-env", "--replication-policy=user-managed",
         "--locations=europe-west1", "--labels=managed-by=repos-secrets,deployable=payments-api",
         "--project=example-proj", "--quiet"]], r["calls"])
    for bad in ("--x", "Europe", "a;touch pwned", ""):
        r = secrets_run([s_create()], replication=bad)
        check(f"F8 malformed replication {bad!r}: fails before any call", r["rc"] != 0 and r["calls"] == [], r["calls"])

    # removal: refused unless PRUNE=true, and refused for the WHOLE plan (nothing applied)
    S_ADMIN = "roles/secretmanager.admin"
    rm = s_bind("remove-secret-binding", mem="serviceAccount:payments-api-deployer" + SUFFIX, role=S_ADMIN)
    r = secrets_run([s_bind(), rm])
    check("F8 remove without prune: step fails, no call", r["rc"] != 0 and r["calls"] == [], (r["rc"], r["calls"]))
    r = secrets_run([s_bind(), rm], prune="true")
    check("F8 remove with prune: remove call issued", r["rc"] == 0 and r["calls"] == [
        s_call("add-iam-policy-binding", "payments-api-env", S_ACC, S_RUN),
        s_call("remove-iam-policy-binding", "payments-api-env", S_ADMIN, S_DEP),
    ], (r["rc"], r["calls"]))
    # a removal may never take a WANTED line (runtime accessor, deployer's three sync roles), even
    # under prune: the planner never emits one, so this is defense in depth
    for label, role, mem in (("runtime accessor", S_ACC, S_RUN), ("deployer accessor", S_ACC, S_DEP),
                             ("deployer versionManager", S_MGR, S_DEP), ("deployer viewer", S_VIEW, S_DEP)):
        r = secrets_run([s_bind("remove-secret-binding", role=role, mem=mem)], prune="true")
        check(f"F8 prune refuses removing the wanted {label} line: step fails, no call",
              r["rc"] != 0 and r["calls"] == [], (r["rc"], r["calls"]))

    # m1: jq's `$` matches before a trailing newline, so \A..\z anchors are needed on the secret
    # name and on the member the name derives
    nl_mem = "serviceAccount:payments-api\n-run" + SUFFIX
    for label, plan in (("add secret", [s_bind(secret="payments-api-env\n")]),
                        ("add secret + newline-split member", [s_bind(secret="payments-api-env\n", mem=nl_mem)]),
                        ("add newline-split member", [s_bind(mem=nl_mem)]),
                        ("add member", [s_bind(mem=S_RUN + "\n")]),
                        ("create secret", [s_create(secret="payments-api-env\n")])):
        r = secrets_run(plan)
        check(f"F8 trailing newline ({label}): step fails, no call", r["rc"] != 0 and r["calls"] == [],
              (r["rc"], r["calls"]))
    r = secrets_run([s_bind("remove-secret-binding", secret="payments-api-env\n", role=S_ADMIN)], prune="true")
    check("F8 trailing newline (remove secret): step fails, no call", r["rc"] != 0 and r["calls"] == [],
          (r["rc"], r["calls"]))
    r = secrets_run([s_bind("remove-secret-binding", role=S_ADMIN, mem="user:a@example.com\n")], prune="true")
    check("F8 trailing newline (remove member): step fails, no call", r["rc"] != 0 and r["calls"] == [],
          (r["rc"], r["calls"]))
    # a removal may name ANY member (the extra lines are by definition not ours), but still only a
    # derived secret and a serviceAccount/user shape without metacharacters
    rm2 = s_bind("remove-secret-binding", mem="serviceAccount:github-rotator" + SUFFIX, role="roles/secretmanager.admin")
    r = secrets_run([rm2], prune="true")
    check("F8 prune removes a foreign line on the derived secret", r["rc"] == 0 and r["calls"] == [
        s_call("remove-iam-policy-binding", "payments-api-env", "roles/secretmanager.admin",
               "serviceAccount:github-rotator" + SUFFIX)], (r["rc"], r["calls"]))
    r = secrets_run([s_bind("remove-secret-binding", secret="app-secrets")], prune="true")
    check("F8 prune never touches a secret that is not -env", r["rc"] != 0 and r["calls"] == [], (r["rc"], r["calls"]))

    for bad in ("delete-secret", "add-secret-version", "destroy-version", "disable-version",
                "grant-project-role", "create-sa-key"):
        r = secrets_run([s_bind(), act("secrets", "r", bad, {}), s_bind(role=S_VIEW, mem=S_DEP)])
        check(f"F8 verb {bad}: step fails, no call (even the valid action before it)",
              r["rc"] != 0 and r["calls"] == [], (r["rc"], r["calls"]))

    foreign = {
        "secret not named -env": s_bind(secret="app-secrets"),
        "secret name with a suffix after -env": s_bind(secret="payments-api-env-old"),
        "role secretmanager.admin": s_bind(role="roles/secretmanager.admin"),
        "role owner": s_bind(role="roles/owner"),
        "role versionAdder": s_bind(role="roles/secretmanager.secretVersionAdder"),
        "runtime SA holding the manager role": s_bind(role=S_MGR, mem=S_RUN),
        "user member": s_bind(mem="user:someone@example.com"),
        "member of another service": s_bind(mem="serviceAccount:ledger-worker-run" + SUFFIX),
        "member of another project": s_bind(mem="serviceAccount:payments-api-run@other.iam.gserviceaccount.com"),
        "member that is not -run or -deployer": s_bind(mem="serviceAccount:repo-admin" + SUFFIX),
    }
    for label, bad in foreign.items():
        r = secrets_run([s_bind(), bad, s_bind(role=S_VIEW, mem=S_DEP)])
        check(f"F8 foreign binding ({label}): step fails, no call", r["rc"] != 0 and r["calls"] == [],
              (r["rc"], r["calls"]))
    r = secrets_run([s_bind(), s_create(secret="web-env", d="payments-api")])
    check("F8 create-secret whose name is not <labels.deployable>-env: step fails, no call",
          r["rc"] != 0 and r["calls"] == [], (r["rc"], r["calls"]))

    r = secrets_run([s_bind(), s_bind(role=S_VIEW, mem=S_DEP), s_bind(role=S_MGR, mem=S_DEP)], fail_on=2)
    check("F8 first failure: loop stopped after the failing call", r["rc"] != 0 and len(r["calls"]) == 2, r["calls"])

    for v in NASTY + ["--x"]:
        r = secrets_run([s_create(secret=v), s_bind(secret=v)])
        check(f"F8 malformed secret {v!r}: step fails, no call, nothing executed",
              r["rc"] != 0 and r["calls"] == [] and "pwned" not in r["files"], (r["rc"], r["calls"]))


def deploy_gated_cases():
    """Review F2, end to end: the real planner's plan for a NEW service whose runtime SA is absent
    (or lacks repo-admin's act_as) goes through the real apply step and reaches no gcloud verb."""
    fix = ROOT / "tests" / "fixtures-repos-deploy"
    reg = json.loads((fix / "repos.yaml").read_text())
    base = json.loads((fix / "state-base.json").read_text())
    absent = json.loads(json.dumps(base))
    absent["service_accounts"].pop("payments-api-run")
    no_act_as = json.loads(json.dumps(base))
    no_act_as["service_accounts"]["payments-api-run"]["iam"] = []
    for label, st in (("runtime SA absent", absent), ("act_as not live", no_act_as)):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "r.yaml").write_text(json.dumps(reg))
            (Path(t) / "s.json").write_text(json.dumps(st))
            p = subprocess.run([sys.executable, str(ROOT / "scripts" / "repos_deploy_plan.py"),
                                "--feature", "deploy-scope", "--register", str(Path(t) / "r.yaml"),
                                "--state", str(Path(t) / "s.json"), "--repo-admin-sa-email",
                                "repo-admin@example-proj.iam.gserviceaccount.com"],
                               capture_output=True, text=True)
        check(f"F7 gated ({label}): planner rc 0", p.returncode == 0, p.stderr)
        plan = json.loads(p.stdout or "[]")
        r = deploy_run(plan)
        check(f"F7 gated ({label}): apply rc 0", r["rc"] == 0, r["out"])
        check(f"F7 gated ({label}): `gcloud run deploy` never reached",
              not any(c[1:3] == ["run", "deploy"] for c in r["calls"]), r["calls"])
        check(f"F7 gated ({label}): nothing bound on the not-yet-created service",
              not any("payments-api" in " ".join(c) and "add-iam-policy-binding" in c for c in r["calls"]),
              r["calls"])
        check(f"F7 gated ({label}): the existing service is still served",
              any(c[:4] == ["gcloud", "run", "services", "add-iam-policy-binding"] and c[4] == "ledger-worker"
                  for c in r["calls"]), r["calls"])


# ------------------------------------------- F3/F4 write token is narrowed to the plan's targets
def targets_cases():
    for wf, feature, verb, mint_name in (
            ("repos-settings.yml", "settings", "update-repo", "Mint App token (administration:write)"),
            ("repos-variables.yml", "variables", "set-variable", "Mint App token (actions_variables:write)")):
        body = extract_step(wf, "Compute write targets")
        w = lambda r: act(feature, r, verb, {"field": "x", "name": "X", "from": None, "to": 1})
        env = {"GITHUB_OUTPUT": "/dev/stdout"}
        r = run_apply(body, [w("b-repo"), act(feature, "n", "in-sync", {}), w("a-repo"), w("b-repo"),
                             act(feature, "d", "drift", {"would": verb})], env=env)
        check(f"{feature} targets: rc 0", r["rc"] == 0, r["out"])
        check(f"{feature} targets: exactly the write targets, unique, in plan order",
              "targets=b-repo,a-repo" in r["out"].splitlines(), r["out"])
        r = run_apply(body, [act(feature, "n", "in-sync", {}), act(feature, "d", "drift", {"would": verb})], env=env)
        check(f"{feature} no writes: empty targets", "targets=" in r["out"].splitlines(), r["out"])
        doc = yaml.safe_load((WF / wf).read_text())
        steps = {s.get("name"): s for j in doc["jobs"].values() for s in j["steps"]}
        mint = steps[mint_name]
        check(f"{feature} write mint: repositories = the plan targets",
              mint["with"].get("repositories") == "${{ steps.targets.outputs.targets }}", mint["with"])
        check(f"{feature} write mint: never runs on an empty target list (empty = ALL repos)",
              "steps.targets.outputs.targets != ''" in mint.get("if", ""), mint.get("if"))
        ro = [s for n, s in steps.items() if n and n.startswith("Mint App token (READ-ONLY)")][0]
        check(f"{feature} read mint unchanged: no repositories input", "repositories" not in ro["with"], ro["with"])


# ---------------------------------------------------------------- F9 repos-environments
ENV_STEP = "Apply the write actions in order"
ENV_STUB = """#!/bin/bash
{ printf '%s\\x1f' "$(basename "$0")" "$@"; echo; } >> "$STUB_DIR/calls.log"
case "$*" in
  *"--input -"*) cat > "$STUB_DIR/put.json" ;;
  *"-X "*) ;;
  *"deployment-branch-policies"*) ;;
  *"/environments/"*)
    if [ -n "${ENV_GET_FILE:-}" ]; then cat "$ENV_GET_FILE"; else echo "gh: Not Found (HTTP 404)" >&2; exit 1; fi ;;
esac
exit 0
"""


def env_put(existing):
    """Run the shipped apply step for one create-environment with a gh stub whose GET answers
    `existing` (None = 404); return rc, output and the JSON body the PUT received (None if no PUT)."""
    body = extract_step("repos-environments.yml", ENV_STEP)
    plan = [act("environments", "r", "create-environment", {"environment": "prod"})]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for d in ("bin", "stub", "work"):
            (tmp / d).mkdir()
        g = tmp / "bin" / "gh"
        g.write_text(ENV_STUB)
        g.chmod(0o755)
        (tmp / "work" / "plan.json").write_text(json.dumps(plan))
        e = dict(os.environ)
        e.update({"PATH": f"{tmp / 'bin'}:{e['PATH']}", "STUB_DIR": str(tmp / "stub"),
                  "RUNNER_TEMP": str(tmp / "work"), "GITHUB_STEP_SUMMARY": str(tmp / "summary.md"),
                  "ORG": "Example-Org"})
        if existing is not None:
            (tmp / "get.json").write_text(json.dumps(existing))
            e["ENV_GET_FILE"] = str(tmp / "get.json")
        p = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                           capture_output=True, text=True, env=e, cwd=tmp / "work")
        put = tmp / "stub" / "put.json"
        return p.returncode, p.stdout + p.stderr, (json.loads(put.read_text()) if put.exists() else None)


def env_cases():
    policy = {"protected_branches": False, "custom_branch_policies": True}
    existing = {"name": "prod", "protection_rules": [
        {"id": 1, "type": "wait_timer", "wait_timer": 30},
        {"id": 2, "type": "required_reviewers", "prevent_self_review": True,
         "reviewers": [{"type": "User", "reviewer": {"id": 42, "login": "someone"}}]}]}
    rc, out, put = env_put(existing)
    check("F9 existing environment: PUT carries wait_timer, reviewers {type,id}, prevent_self_review "
          "and the branch policy",
          rc == 0 and put == {"deployment_branch_policy": policy, "wait_timer": 30,
                              "prevent_self_review": True, "reviewers": [{"type": "User", "id": 42}]},
          (rc, out, put))
    rc, out, put = env_put(None)
    check("F9 new environment (GET 404): PUT holds only deployment_branch_policy",
          rc == 0 and put == {"deployment_branch_policy": policy}, (rc, out, put))


def env_token_cases():
    doc = yaml.safe_load((WF / "repos-environments.yml").read_text())
    steps = [s for j in doc["jobs"].values() for s in j["steps"]
             if s.get("name") == "Mint App token (administration:write)"]
    w = steps[0]["with"] if steps else {}
    check("F9 M6: write token requests actions: read and administration: write",
          w.get("permission-actions") == "read" and w.get("permission-administration") == "write", w)


def main():
    env_cases()
    env_token_cases()
    targets_cases()
    create_cases()
    wif_cases()
    sa_cases()
    deploy_cases()
    deploy_gated_cases()
    secrets_cases()
    print(f"repos apply step tests: {RAN} cases run, {RAN - len(FAILURES)} passed, {len(FAILURES)} failed")
    if RAN == 0 or FAILURES:
        sys.exit(1)


main()
