#!/usr/bin/env python3
"""Fixture tests for the F7 deploy-scope planner, scripts/repos_deploy_plan.py.

Output contract: docs/repos-register.md §8 (action list) and §6 F7. This file pins the F7
parts the doc leaves to "the fixtures", so it is the implementer's contract:

  Invocation   python3 scripts/repos_deploy_plan.py --feature deploy-scope \
                   --register <repos.yaml> --state <state.json>
               (env REPOS_DEPLOY_PLANNER overrides the script path; used only to prove the
               suite is not vacuous against a stub.) The register fixture is JSON written to a
               .yaml file (JSON is valid YAML), so these tests need no YAML library.

  State JSON   {
                 "project_id": "example-proj",
                 "cloud_run_services": {"<service>": {"iam": [POLICY]}},   # absent key = missing
                 "service_accounts":   {"<sa name>":  {"iam": [POLICY]}},  # runtime SAs
                 "gar_repositories":   {"<location>/<repo>": {"iam": [POLICY]}},
                 "gke_clusters":       {"<location>/<name>": {"iam": [POLICY],
                                         "rbac": [{"namespace", "workload", "member",
                                                   "resource_names": [..]}]}},
                 "project_roles":      {"<deployer sa name>": ["roles/..", ..]}
               }
               POLICY = {"role": "roles/..", "members": ["serviceAccount:..", ..]}

  Names        deployer SA = "<deployable>-deployer" (deployable = Cloud Run service name, or
               GKE workload). member = "serviceAccount:<sa>@<project_id>.iam.gserviceaccount.com".
               add-resource-binding.resource: run.service -> service name;
               iam.serviceAccount -> the runtime SA's EMAIL; artifactregistry.repository ->
               "<location>/<repo>" (the register's image_repository); container.cluster ->
               "<location>/<name>".
  Order        per repo: create-service, run.developer on the service, serviceAccountUser on the
               runtime SA, artifactregistry.writer; GKE: clusterViewer binding, apply-k8s-rbac.
  Mode         repo.mode, else defaults.mode, else "report". Report mode: drift{would:<verb>,
               ...that verb's details}; legacy-grant is emitted in both modes.
  legacy-grant a deployer's project_roles entry starting "roles/run." or "roles/container."
               (reported, never removed; no verb exists to remove it).
  Errors       deployer name > 30 chars -> `error: <repo>: ...` on stderr, empty stdout, rc 1.

Usage:  python3 tests/run_repos_deploy_plan_tests.py
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANNER = Path(os.environ.get("REPOS_DEPLOY_PLANNER", ROOT / "scripts" / "repos_deploy_plan.py"))
FIX = Path(__file__).resolve().parent / "fixtures-repos-deploy"

WRITE_VERBS = {"create-service", "add-resource-binding", "apply-k8s-rbac"}
NON_WRITE = {"in-sync", "skip", "drift", "unsupported", "legacy-grant"}
RUN_DEV = "roles/run.developer"
SA_USER = "roles/iam.serviceAccountUser"
GAR_W = "roles/artifactregistry.writer"
CLUSTER_VIEWER = "roles/container.clusterViewer"
SUFFIX = ".iam.gserviceaccount.com"


def member(sa):
    return "serviceAccount:%s@example-proj%s" % (sa, SUFFIX)


def email(sa):
    return "%s@example-proj%s" % (sa, SUFFIX)


def load_register():
    return json.loads((FIX / "repos.yaml").read_text())


def load_state():
    return json.loads((FIX / "state-base.json").read_text())


def repo(reg, name):
    return next(r for r in reg["repos"] if r["name"] == name)


def run(reg, state):
    with tempfile.TemporaryDirectory(dir=str(ROOT / ".scratch") if (ROOT / ".scratch").is_dir() else None) as d:
        rp, sp = Path(d) / "repos.yaml", Path(d) / "state.json"
        rp.write_text(json.dumps(reg))
        sp.write_text(json.dumps(state))
        p = subprocess.run(
            [sys.executable, str(PLANNER), "--feature", "deploy-scope",
             "--register", str(rp), "--state", str(sp)],
            capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def plan(reg, state):
    """Return the parsed action list, or raise AssertionError with context."""
    rc, out, err = run(reg, state)
    assert rc == 0, "rc=%d stderr=%s" % (rc, err.strip()[:300])
    try:
        acts = json.loads(out)
    except ValueError:
        raise AssertionError("stdout is not JSON: %r" % out[:200])
    assert isinstance(acts, list), "stdout is not an array"
    for a in acts:
        assert list(a.keys()) == ["feature", "repo", "action", "details"], "bad keys %s" % list(a)
        assert a["feature"] == "deploy-scope", "feature %r" % a["feature"]
    return acts


def of(acts, name):
    return [a for a in acts if a["repo"] == name]


def shape(acts):
    return [(a["action"], a["details"]) for a in acts]


def binding(rtype, res, role, mem):
    return ("add-resource-binding", {"resource_type": rtype, "resource": res, "role": role, "member": mem})


def run_bindings(svc, runtime, sa, gar="europe-west1/services"):
    m = member(sa)
    return [binding("run.service", svc, RUN_DEV, m),
            binding("iam.serviceAccount", email(runtime), SA_USER, m),
            binding("artifactregistry.repository", gar, GAR_W, m)]


def create(svc, runtime, region="europe-west1"):
    return ("create-service", {"service": svc, "region": region,
                               "runtime_service_account": runtime, "image": "placeholder"})


def fully_bound_state():
    st = load_state()
    st["cloud_run_services"]["payments-api"] = {"iam": [
        {"role": RUN_DEV, "members": [member("payments-api-deployer")]}]}
    st["cloud_run_services"]["ledger-worker"] = {"iam": [
        {"role": RUN_DEV, "members": [member("ledger-worker-deployer")]}]}
    for rt, sa in (("payments-api-run", "payments-api-deployer"),
                   ("ledger-worker-run", "ledger-worker-deployer")):
        st["service_accounts"][rt] = {"iam": [{"role": SA_USER, "members": [member(sa)]}]}
    st["gar_repositories"]["europe-west1/services"] = {"iam": [{"role": GAR_W, "members": [
        member("payments-api-deployer"), member("ledger-worker-deployer")]}]}
    st["gke_clusters"]["europe-west1/main"] = {
        "iam": [{"role": CLUSTER_VIEWER, "members": [member("batch-runner-deployer")]}],
        "rbac": [{"namespace": "batch", "workload": "batch-runner",
                  "member": member("batch-runner-deployer"), "resource_names": ["batch-runner"]}]}
    return st


# --------------------------------------------------------------------------- cases
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def missing_service_is_created_then_bound():
    acts = of(plan(load_register(), load_state()), "payments-api")
    exp = [create("payments-api", "payments-api-run")] + run_bindings(
        "payments-api", "payments-api-run", "payments-api-deployer")
    assert shape(acts) == exp, "got %s" % json.dumps(shape(acts))


@case
def create_comes_before_every_binding():
    acts = of(plan(load_register(), load_state()), "payments-api")
    names = [a["action"] for a in acts]
    assert names[0] == "create-service" and names.count("create-service") == 1, names
    assert names.index("create-service") < names.index("add-resource-binding"), names


@case
def existing_service_is_not_recreated():
    acts = of(plan(load_register(), load_state()), "ledger-worker")
    assert shape(acts) == run_bindings("ledger-worker", "ledger-worker-run", "ledger-worker-deployer"), \
        json.dumps(shape(acts))


@case
def partially_bound_adds_only_the_missing_bindings():
    st = load_state()
    st["cloud_run_services"]["ledger-worker"]["iam"] = [
        {"role": RUN_DEV, "members": [member("ledger-worker-deployer")]}]
    acts = of(plan(load_register(), st), "ledger-worker")
    exp = run_bindings("ledger-worker", "ledger-worker-run", "ledger-worker-deployer")[1:]
    assert shape(acts) == exp, json.dumps(shape(acts))


@case
def run_developer_only_on_the_service_never_project_level():
    acts = plan(load_register(), load_state())
    for a in acts:
        if a["action"] != "add-resource-binding":
            continue
        d = a["details"]
        assert d["resource_type"] in {"run.service", "iam.serviceAccount",
                                      "artifactregistry.repository", "container.cluster"}, d
        if d["role"] == RUN_DEV:
            assert d["resource_type"] == "run.service", d
    devs = [a for a in acts if a["action"] == "add-resource-binding" and a["details"]["role"] == RUN_DEV]
    assert len(devs) == 2, "expected one run.developer per Cloud Run deployable, got %d" % len(devs)


@case
def service_account_user_only_on_the_runtime_sa():
    acts = of(plan(load_register(), load_state()), "payments-api")
    users = [a["details"] for a in acts
             if a["action"] == "add-resource-binding" and a["details"]["role"] == SA_USER]
    assert users == [{"resource_type": "iam.serviceAccount", "resource": email("payments-api-run"),
                      "role": SA_USER, "member": member("payments-api-deployer")}], users


@case
def artifact_registry_writer_on_the_image_repository():
    acts = of(plan(load_register(), load_state()), "payments-api")
    w = [a["details"] for a in acts if a["action"] == "add-resource-binding"
         and a["details"]["role"] == GAR_W]
    assert w == [{"resource_type": "artifactregistry.repository", "resource": "europe-west1/services",
                  "role": GAR_W, "member": member("payments-api-deployer")}], w


@case
def cross_service_isolation_each_deployer_only_its_own_service():
    st = load_state()
    # the other repo's deployer already sits on payments-api's runtime SA: still no action for it
    st["service_accounts"]["payments-api-run"]["iam"] = [
        {"role": SA_USER, "members": [member("ledger-worker-deployer")]}]
    acts = plan(load_register(), st)
    mine = [a for a in of(acts, "payments-api") if a["action"] == "add-resource-binding"]
    assert mine and all(a["details"]["member"] == member("payments-api-deployer") for a in mine), mine
    assert not any(a["details"]["resource"] == "ledger-worker" for a in mine), mine
    theirs = [a for a in of(acts, "ledger-worker") if a["action"] == "add-resource-binding"]
    assert theirs and all(a["details"]["member"] == member("ledger-worker-deployer") for a in theirs), theirs
    assert not any(a["details"]["resource"] == "payments-api" for a in theirs), theirs
    assert not any(email("payments-api-run") == a["details"]["resource"] for a in theirs), theirs


@case
def already_bound_is_in_sync():
    acts = plan(load_register(), fully_bound_state())
    for name in ("payments-api", "ledger-worker", "batch-runner"):
        assert shape(of(acts, name)) == [("in-sync", {})], (name, json.dumps(shape(of(acts, name))))


@case
def legacy_project_level_grants_are_reported_never_removed():
    st = fully_bound_state()
    st["project_roles"]["payments-api-deployer"] = [
        "roles/run.developer", "roles/container.developer", "roles/run.admin", "roles/viewer"]
    acts = plan(load_register(), st)
    leg = [a["details"] for a in of(acts, "payments-api") if a["action"] == "legacy-grant"]
    exp = [{"service_account": "payments-api-deployer", "role": r, "scope": "project"}
           for r in ("roles/run.developer", "roles/container.developer", "roles/run.admin")]
    key = lambda d: d["role"]
    assert sorted(leg, key=key) == sorted(exp, key=key), leg
    assert not [a for a in acts if a["action"] in WRITE_VERBS], "legacy grants must plan no write"


@case
def legacy_grant_also_reported_in_report_mode():
    reg, st = load_register(), fully_bound_state()
    repo(reg, "payments-api")["mode"] = "report"
    st["project_roles"]["payments-api-deployer"] = ["roles/run.developer"]
    acts = of(plan(reg, st), "payments-api")
    assert {"service_account": "payments-api-deployer", "role": RUN_DEV, "scope": "project"} in \
        [a["details"] for a in acts if a["action"] == "legacy-grant"], json.dumps(shape(acts))


@case
def gke_rbac_scoped_to_the_workload_and_cluster_viewer():
    acts = of(plan(load_register(), load_state()), "batch-runner")
    exp = [binding("container.cluster", "europe-west1/main", CLUSTER_VIEWER, member("batch-runner-deployer")),
           ("apply-k8s-rbac", {"cluster": "europe-west1/main", "namespace": "batch",
                               "workload": "batch-runner", "resource_names": ["batch-runner"],
                               "member": member("batch-runner-deployer")})]
    assert shape(acts) == exp, json.dumps(shape(acts))


@case
def gke_never_grants_container_developer_and_resource_names_never_empty():
    acts = plan(load_register(), load_state())
    assert "roles/container.developer" not in json.dumps(acts), "container.developer planned"
    rbac = [a["details"] for a in acts if a["action"] == "apply-k8s-rbac"]
    assert rbac and all(d["resource_names"] and d["resource_names"] == [d["workload"]] for d in rbac), rbac


@case
def report_mode_emits_only_drift_legacy_and_in_sync():
    reg = load_register()
    reg["defaults"]["mode"] = "report"
    acts = plan(reg, load_state())
    assert acts, "no actions"
    assert {a["action"] for a in acts} <= {"drift", "legacy-grant", "in-sync"}, {a["action"] for a in acts}
    pay = of(acts, "payments-api")
    exp = [("drift", dict(would=v, **d)) for v, d in
           [create("payments-api", "payments-api-run")] + run_bindings(
               "payments-api", "payments-api-run", "payments-api-deployer")]
    assert shape(pay) == exp, json.dumps(shape(pay))


@case
def report_mode_default_when_no_mode_set():
    reg = load_register()
    reg["defaults"].pop("mode")
    acts = plan(reg, load_state())
    assert acts and {a["action"] for a in acts} <= {"drift", "legacy-grant", "in-sync"}


@case
def report_mode_in_sync_when_bound():
    reg = load_register()
    reg["defaults"]["mode"] = "report"
    acts = plan(reg, fully_bound_state())
    assert [shape(of(acts, n)) for n in ("payments-api", "ledger-worker", "batch-runner")] == \
        [[("in-sync", {})]] * 3


@case
def per_repo_mode_overrides_default():
    reg = load_register()
    repo(reg, "ledger-worker")["mode"] = "report"
    acts = plan(reg, load_state())
    assert {a["action"] for a in of(acts, "ledger-worker")} == {"drift"}
    assert "create-service" in {a["action"] for a in of(acts, "payments-api")}


@case
def deployer_name_over_30_chars_is_an_error_with_no_partial_plan():
    reg = load_register()
    d = repo(reg, "payments-api")["deploys"][0]
    d["cloud_run"] = "payments-processing-service"      # 27 + "-deployer" = 36
    rc, out, err = run(reg, load_state())
    assert rc == 1, "rc=%d" % rc
    assert out.strip() == "", "stdout must be empty on error, got %r" % out[:100]
    assert err.startswith("error: payments-api:"), err[:200]


@case
def deployer_name_of_exactly_30_chars_is_accepted():
    reg, st = load_register(), load_state()
    svc = "a" * 21                                       # 21 + 9 = 30
    repo(reg, "payments-api")["deploys"][0]["cloud_run"] = svc
    repo(reg, "payments-api")["gcp"]["service_accounts"] = [svc + "-deployer"]
    acts = of(plan(reg, st), "payments-api")
    assert acts[0]["action"] == "create-service" and acts[0]["details"]["service"] == svc, acts[0]
    assert member(svc + "-deployer") in json.dumps(acts)


@case
def repo_absent_from_register_gets_no_action():
    reg = load_register()
    reg["repos"] = [r for r in reg["repos"] if r["name"] != "ledger-worker"]
    st = load_state()                                    # ledger-worker still live in state
    acts = plan(reg, st)
    assert of(acts, "ledger-worker") == [] and "ledger-worker" not in json.dumps(acts), acts
    assert of(acts, "payments-api"), "listed repos still planned"


@case
def removed_deploy_entry_plans_nothing_for_it_and_removes_nothing():
    reg, st = load_register(), fully_bound_state()
    repo(reg, "payments-api")["deploys"] = []
    acts = of(plan(reg, st), "payments-api")
    assert {a["action"] for a in acts} <= {"in-sync", "skip"}, json.dumps(shape(acts))
    assert acts, "an examined repo must yield at least one entry"


@case
def unknown_keys_are_ignored():
    reg = load_register()
    repo(reg, "payments-api")["frobnicate"] = {"x": 1}
    repo(reg, "payments-api")["deploys"][0]["future_key"] = "y"
    reg["something_new"] = True
    base = plan(load_register(), load_state())
    assert base and plan(reg, load_state()) == base


@case
def never_list_no_delete_key_or_project_verbs_ever():
    st = fully_bound_state()
    st["project_roles"]["payments-api-deployer"] = ["roles/run.admin"]
    for s in (load_state(), st):
        acts = plan(load_register(), s)
        assert acts, "empty plan"
        for a in acts:
            assert a["action"] in WRITE_VERBS | NON_WRITE, "verb outside the contract: %s" % a["action"]
            for bad in ("delete", "remove", "archive", "key-create", "public"):
                assert bad not in a["action"], a
            if a["action"] == "add-resource-binding":
                assert a["details"]["resource_type"] != "project", a
                assert "projects/" not in a["details"]["resource"], a


@case
def same_input_same_output():
    a = run(load_register(), load_state())
    b = run(load_register(), load_state())
    assert a == b and a[0] == 0 and json.loads(a[1]), a


@case
def every_repo_examined_yields_an_entry():
    acts = plan(load_register(), load_state())
    assert {a["repo"] for a in acts} == {"payments-api", "ledger-worker", "batch-runner"}


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
            print("ok   %s" % fn.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (fn.__name__, str(e)[:400]))
        except Exception as e:                           # planner missing, crash in test, ...
            failed += 1
            print("FAIL %s: %s: %s" % (fn.__name__, type(e).__name__, str(e)[:400]))
    print("%d cases run, %d failed" % (len(CASES), failed))
    return 1 if failed or not CASES else 0


if __name__ == "__main__":
    sys.exit(main())
