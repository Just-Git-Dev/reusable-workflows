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
               }
               POLICY = {"role": "roles/..", "members": ["serviceAccount:..", ..]}
  Flags        --repo-admin-sa-email <email> is REQUIRED (the repo-admin SA; missing -> rc 2, no
               stdout). --protected-service-accounts is a DEPRECATED NO-OP (accepted, ignored).
  Ruling 21    F7 writes NO service-account policy. The runtime SA is DERIVED: `<d>-run`
               (`runtime_service_account` optional; if present it must equal `<d>-run`, else
               `error: <repo>: ...` rc 1). F7 only READS `<d>-run`'s policy and reports
               needs-jgd{resource_type, resource (runtime SA email), role serviceAccountUser,
               member, needs: "deployed_by: <d>-deployer" | "act_as: repo-admin"} in BOTH modes
               when the line is not live (act_as only while the service is still to be created).
  Names        deployer SA = "<deployable>-deployer" (deployable = Cloud Run service name, or
               GKE workload). member = "serviceAccount:<sa>@<project_id>.iam.gserviceaccount.com".
               add-resource-binding.resource: run.service -> service name;
               artifactregistry.repository ->
               "<location>/<repo>" (the register's image_repository). GKE has no cluster-level IAM,
               so there is no container.cluster resource_type.
  Order        per deployable: create-service, run.developer on the service,
               artifactregistry.writer, then needs-jgd lines. A run.service binding's details also carry
               "region" (the register's region; no live lookup is ever needed).
  GKE          ruling 19: a `gke` entry yields exactly one unsupported{"key": "gke", "reason"} in
               BOTH modes and nothing else (no apply-k8s-rbac verb exists, no cluster state is
               read).
  Mode         repo.mode, else defaults.mode, else "report". Report mode: drift{would:<verb>,
               ...that verb's details}.
  No legacy    F7 reads no project-level IAM: there is no legacy-grant verb and no project_roles.
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

WRITE_VERBS = {"create-service", "add-resource-binding"}
NON_WRITE = {"in-sync", "skip", "drift", "unsupported", "needs-jgd"}
RUN_DEV = "roles/run.developer"
SA_USER = "roles/iam.serviceAccountUser"
GAR_W = "roles/artifactregistry.writer"
SUFFIX = ".iam.gserviceaccount.com"
ADMIN_EMAIL = "repo-admin@example-proj.iam.gserviceaccount.com"


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


def run(reg, state, extra=(), admin=ADMIN_EMAIL):
    with tempfile.TemporaryDirectory(dir=str(ROOT / ".scratch") if (ROOT / ".scratch").is_dir() else None) as d:
        rp, sp = Path(d) / "repos.yaml", Path(d) / "state.json"
        rp.write_text(json.dumps(reg))
        sp.write_text(json.dumps(state))
        p = subprocess.run(
            [sys.executable, str(PLANNER), "--feature", "deploy-scope",
             "--register", str(rp), "--state", str(sp)]
            + (["--repo-admin-sa-email", admin] if admin else []) + list(extra),
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


def binding(rtype, res, role, mem, region="europe-west1"):
    d = {"resource_type": rtype, "resource": res, "role": role, "member": mem}
    if rtype == "run.service":
        d["region"] = region
    return ("add-resource-binding", d)


def run_bindings(svc, runtime, sa, gar="europe-west1/services"):
    # ruling 21: F7 writes NO service-account policy, so no iam.serviceAccount binding appears here
    m = member(sa)
    return [binding("run.service", svc, RUN_DEV, m),
            binding("artifactregistry.repository", gar, GAR_W, m)]


def needs_jgd(runtime, line, mem):
    return ("needs-jgd", {"resource_type": "iam.serviceAccount", "resource": email(runtime),
                          "role": SA_USER, "member": mem, "needs": line})


def needs_deployed_by(runtime, sa):
    return needs_jgd(runtime, "deployed_by: " + sa, member(sa))


def needs_act_as(runtime):
    return needs_jgd(runtime, "act_as: repo-admin", "serviceAccount:" + ADMIN_EMAIL)


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
        st["service_accounts"][rt] = {"iam": [{"role": SA_USER, "members": [
            member(sa), "serviceAccount:" + ADMIN_EMAIL]}]}
    st["gar_repositories"]["europe-west1/services"] = {"iam": [{"role": GAR_W, "members": [
        member("payments-api-deployer"), member("ledger-worker-deployer")]}]}
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
        "payments-api", "payments-api-run", "payments-api-deployer") + [
        needs_deployed_by("payments-api-run", "payments-api-deployer")]
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
    assert shape(acts) == run_bindings(
        "ledger-worker", "ledger-worker-run", "ledger-worker-deployer") + [
        needs_deployed_by("ledger-worker-run", "ledger-worker-deployer")], json.dumps(shape(acts))


@case
def partially_bound_adds_only_the_missing_bindings():
    st = load_state()
    st["cloud_run_services"]["ledger-worker"]["iam"] = [
        {"role": RUN_DEV, "members": [member("ledger-worker-deployer")]}]
    acts = of(plan(load_register(), st), "ledger-worker")
    exp = run_bindings("ledger-worker", "ledger-worker-run", "ledger-worker-deployer")[1:] + [
        needs_deployed_by("ledger-worker-run", "ledger-worker-deployer")]
    assert shape(acts) == exp, json.dumps(shape(acts))


@case
def run_developer_only_on_the_service_never_project_level():
    acts = plan(load_register(), load_state())
    for a in acts:
        if a["action"] != "add-resource-binding":
            continue
        d = a["details"]
        assert d["resource_type"] in {"run.service", "artifactregistry.repository"}, d
        if d["role"] == RUN_DEV:
            assert d["resource_type"] == "run.service", d
    devs = [a for a in acts if a["action"] == "add-resource-binding" and a["details"]["role"] == RUN_DEV]
    assert len(devs) == 2, "expected one run.developer per Cloud Run deployable, got %d" % len(devs)


@case
def r21_f7_writes_no_service_account_policy_in_any_state():
    # ruling 21: the runtime SA's policy has exactly one writer (JGD). F7 may only READ it.
    for st in (load_state(), fully_bound_state()):
        for mode in ("enforce", "report"):
            reg = load_register()
            reg["defaults"]["mode"] = mode
            for a in plan(reg, st):
                d = a["details"]
                assert d.get("resource_type") != "iam.serviceAccount" or a["action"] == "needs-jgd", a
                assert d.get("would") != "add-resource-binding" or d["resource_type"] != "iam.serviceAccount", a


@case
def r21_runtime_sa_deployed_by_line_missing_is_needs_jgd_in_both_modes():
    for mode in ("enforce", "report"):
        reg = load_register()
        reg["defaults"]["mode"] = mode
        got = shape(of(plan(reg, load_state()), "ledger-worker"))
        assert needs_deployed_by("ledger-worker-run", "ledger-worker-deployer") in got, got
        assert "add-resource-binding" not in [g[0] for g in got if g[1].get("resource_type") == "iam.serviceAccount"], got


@case
def r21_deployed_by_line_live_means_no_needs_jgd():
    st = load_state()
    st["service_accounts"]["ledger-worker-run"]["iam"] = [
        {"role": SA_USER, "members": [member("ledger-worker-deployer"), "serviceAccount:" + ADMIN_EMAIL]}]
    got = shape(of(plan(load_register(), st), "ledger-worker"))
    assert got == run_bindings("ledger-worker", "ledger-worker-run", "ledger-worker-deployer"), got
    # another role or another member does not count as live
    st["service_accounts"]["ledger-worker-run"]["iam"] = [
        {"role": "roles/iam.serviceAccountTokenCreator", "members": [member("ledger-worker-deployer")]},
        {"role": SA_USER, "members": [member("someone-else-aa")]}]
    got = shape(of(plan(load_register(), st), "ledger-worker"))
    assert needs_deployed_by("ledger-worker-run", "ledger-worker-deployer") in got, got


@case
def r21_runtime_sa_absent_from_state_is_needs_jgd_not_an_error():
    st = load_state()
    st["service_accounts"].pop("ledger-worker-run")
    got = shape(of(plan(load_register(), st), "ledger-worker"))
    assert needs_deployed_by("ledger-worker-run", "ledger-worker-deployer") in got, got


@case
def r21_act_as_for_repo_admin_is_reported_only_when_creating_a_service():
    # existing service (ledger-worker): repo-admin act_as is not needed, so never reported
    got = shape(of(plan(load_register(), load_state()), "ledger-worker"))
    assert needs_act_as("ledger-worker-run") not in got, got
    # new service (payments-api): reported until the line is live; then gone
    st = load_state()
    st["service_accounts"]["payments-api-run"]["iam"] = [
        {"role": SA_USER, "members": ["serviceAccount:" + ADMIN_EMAIL]}]
    got = shape(of(plan(load_register(), st), "payments-api"))
    assert needs_act_as("payments-api-run") not in got and needs_deployed_by(
        "payments-api-run", "payments-api-deployer") in got, got


@case
def r21_new_service_with_act_as_not_live_plans_only_needs_jgd_in_both_modes():
    # review F2: `gcloud run deploy --service-account=<d>-run` needs repo-admin's act_as on it. While
    # that line is not live (SA present without it, or SA absent) nothing may be created or bound.
    absent = load_state()
    absent["service_accounts"].pop("payments-api-run")
    present = load_state()
    present["service_accounts"]["payments-api-run"]["iam"] = [
        {"role": SA_USER, "members": [member("someone-else-aa")]}]
    for label, st in (("sa absent", absent), ("sa without act_as", present)):
        for mode in ("enforce", "report"):
            reg = load_register()
            reg["defaults"]["mode"] = mode
            got = shape(of(plan(reg, st), "payments-api"))
            exp = [needs_act_as("payments-api-run"),
                   needs_deployed_by("payments-api-run", "payments-api-deployer")]
            assert got == exp, "%s/%s: %s" % (label, mode, json.dumps(got))


@case
def r21_new_service_with_act_as_live_is_created_then_bound():
    st = load_state()
    st["service_accounts"]["payments-api-run"]["iam"] = [
        {"role": SA_USER, "members": ["serviceAccount:" + ADMIN_EMAIL]}]
    for mode in ("enforce", "report"):
        reg = load_register()
        reg["defaults"]["mode"] = mode
        verbs = [g[0] if mode == "enforce" else g[1].get("would", g[0])
                 for g in shape(of(plan(reg, st), "payments-api"))]
        assert verbs[0] == "create-service" and "add-resource-binding" in verbs, verbs
        assert "needs-jgd" in verbs, verbs         # deployed_by is still outstanding


def _expect_planner_error(mutate, needle):
    reg = load_register()
    mutate(repo(reg, "payments-api")["deploys"][0])
    rc, out, err = run(reg, load_state())
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert rc == 1 and out.strip() == "", (rc, out[:100], err[:200])
    assert lines and all(ln.startswith("error: ") for ln in lines) and needle in err, err[:300]


@case
def r21_derived_ids_outside_gcp_length_are_an_early_error():
    # review 5: `a-run` is 5 chars (GCP minimum 6): JGD could never declare it
    def one_char(d):
        d["cloud_run"] = "a"
        d.pop("runtime_service_account", None)
    _expect_planner_error(one_char, "a-run")
    # `<d>-deployer` over 30 chars
    _expect_planner_error(lambda d: d.update({"cloud_run": "x" * 22, "runtime_service_account": "x" * 22 + "-run"}),
                          "-deployer")


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
    # the other repo's deployer already sits on payments-api's runtime SA: it is not payments-api's line
    st["service_accounts"]["payments-api-run"]["iam"] = [
        {"role": SA_USER, "members": [member("ledger-worker-deployer"), "serviceAccount:" + ADMIN_EMAIL]}]
    acts = plan(load_register(), st)
    mine = [a for a in of(acts, "payments-api") if a["action"] == "add-resource-binding"]
    assert mine and all(a["details"]["member"] == member("payments-api-deployer") for a in mine), mine
    assert not any(a["details"]["resource"] == "ledger-worker" for a in mine), mine
    assert needs_deployed_by("payments-api-run", "payments-api-deployer") in shape(of(acts, "payments-api"))
    theirs = [a for a in of(acts, "ledger-worker") if a["action"] == "add-resource-binding"]
    assert theirs and all(a["details"]["member"] == member("ledger-worker-deployer") for a in theirs), theirs
    assert not any(a["details"]["resource"] == "payments-api" for a in theirs), theirs
    assert not any(email("payments-api-run") == a["details"]["resource"] for a in of(acts, "ledger-worker")), acts


@case
def already_bound_is_in_sync():
    acts = plan(load_register(), fully_bound_state())
    for name in ("payments-api", "ledger-worker"):
        assert shape(of(acts, name)) == [("in-sync", {})], (name, json.dumps(shape(of(acts, name))))


@case
def m3_unvalidated_values_never_reach_a_plan():
    cases = [("cloud_run", "--ingress=all"), ("cloud_run", "-x"), ("cloud_run", "Upper_Case"),
             ("region", "--region=us"), ("region", "europe_west1"),
             ("runtime_service_account", "--x-run"), ("image_repository", "--x/y")]
    for key, bad in cases:
        reg = load_register()
        repo(reg, "payments-api")["deploys"][0][key] = bad
        for mode in ("enforce", "report"):
            reg["defaults"]["mode"] = mode
            rc, out, err = run(reg, load_state())
            assert rc == 1 and out.strip() == "", (key, bad, mode, rc, out[:100])
            assert "error: " in err and ("does not match" in err or "is not valid" in err), (key, bad, err[:300])
    reg = load_register()
    reg["repos"][0]["name"] = "-evil"
    rc, out, err = run(reg, load_state())
    assert rc == 1 and out.strip() == "", (rc, out[:100])
    reg = load_register()
    reg["version"] = 2
    rc, out, err = run(reg, load_state())
    assert rc == 1 and out.strip() == "" and "error: register:" in err, (rc, err[:200])


@case
def r19_gke_entry_is_unsupported_in_both_modes_and_nothing_else():
    for mode in ("enforce", "report"):
        reg = load_register()
        reg["defaults"]["mode"] = mode
        got = shape(of(plan(reg, load_state()), "batch-runner"))
        assert len(got) == 1 and got[0][0] == "unsupported", (mode, got)
        d = got[0][1]
        assert d["key"] == "gke" and isinstance(d["reason"], str) and "GKE" in d["reason"], d
        assert set(d) == {"key", "reason"}, d
    blob = json.dumps(plan(load_register(), load_state()))
    for bad in ("apply-k8s-rbac", "container.developer", "clusterViewer", "legacy-grant"):
        assert bad not in blob, bad


@case
def r19_gke_needs_no_cluster_or_project_state():
    st = load_state()
    st.pop("gke_clusters", None)
    st.pop("project_roles", None)
    got = shape(of(plan(load_register(), st), "batch-runner"))
    assert got[0][0] == "unsupported", got


@case
def region_comes_from_the_register_for_existing_and_new_services():
    reg = load_register()
    repo(reg, "ledger-worker")["deploys"][0]["region"] = "us-central1"      # existing service
    repo(reg, "payments-api")["deploys"][0]["region"] = "asia-east1"        # missing service
    acts = plan(reg, load_state())
    got = {a["details"]["resource"]: a["details"].get("region") for a in acts
           if a["action"] == "add-resource-binding" and a["details"]["resource_type"] == "run.service"}
    assert got == {"ledger-worker": "us-central1", "payments-api": "asia-east1"}, got
    for a in acts:
        if a["action"] == "add-resource-binding" and a["details"]["resource_type"] != "run.service":
            assert "region" not in a["details"], a


@case
def report_mode_emits_only_drift_legacy_and_in_sync():
    reg = load_register()
    reg["defaults"]["mode"] = "report"
    acts = plan(reg, load_state())
    assert acts, "no actions"
    assert {a["action"] for a in acts} <= {"drift", "in-sync", "unsupported", "needs-jgd"}, {a["action"] for a in acts}
    pay = of(acts, "payments-api")
    exp = [("drift", dict(would=v, **d)) for v, d in
           [create("payments-api", "payments-api-run")] + run_bindings(
               "payments-api", "payments-api-run", "payments-api-deployer")] + [
        needs_deployed_by("payments-api-run", "payments-api-deployer")]
    assert shape(pay) == exp, json.dumps(shape(pay))


@case
def report_mode_default_when_no_mode_set():
    reg = load_register()
    reg["defaults"].pop("mode")
    acts = plan(reg, load_state())
    assert acts and {a["action"] for a in acts} <= {"drift", "in-sync", "unsupported", "needs-jgd"}


@case
def report_mode_in_sync_when_bound():
    reg = load_register()
    reg["defaults"]["mode"] = "report"
    acts = plan(reg, fully_bound_state())
    assert [shape(of(acts, n)) for n in ("payments-api", "ledger-worker")] == [[("in-sync", {})]] * 2


@case
def per_repo_mode_overrides_default():
    reg = load_register()
    repo(reg, "ledger-worker")["mode"] = "report"
    acts = plan(reg, load_state())
    assert {a["action"] for a in of(acts, "ledger-worker")} == {"drift", "needs-jgd"}
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
    st["service_accounts"][svc + "-run"] = {"iam": [{"role": SA_USER, "members": ["serviceAccount:" + ADMIN_EMAIL]}]}
    repo(reg, "payments-api")["deploys"][0]["cloud_run"] = svc
    repo(reg, "payments-api")["deploys"][0]["runtime_service_account"] = svc + "-run"
    repo(reg, "payments-api")["gcp"]["service_accounts"] = [svc + "-deployer"]
    acts = of(plan(reg, st), "payments-api")
    assert acts[0]["action"] == "create-service" and acts[0]["details"]["service"] == svc, acts[:2]
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


@case
def r21_runtime_sa_is_derived_when_the_key_is_absent():
    # runtime_service_account is optional: absent means `<d>-run`, and the plan is identical
    base = plan(load_register(), load_state())
    reg = load_register()
    for r in reg["repos"]:
        for d in r["deploys"]:
            d.pop("runtime_service_account", None)
    assert plan(reg, load_state()) == base


@case
def r21_runtime_sa_present_must_equal_the_derived_name():
    # M2: `api` can never point its service at another runtime identity, protected or not
    for rt in ("ledger-worker-run", "repo-admin", "github-releaser", "payments-api-deployer", "payments-api-runner"):
        for mode in ("enforce", "report"):
            reg = load_register()
            reg["defaults"]["mode"] = mode
            repo(reg, "payments-api")["deploys"][0]["runtime_service_account"] = rt
            rc, out, err = run(reg, load_state())
            assert rc == 1 and out.strip() == "", (rt, mode, rc, out[:100])
            assert err.startswith("error: payments-api:") and "payments-api-run" in err and rt in err, err[:300]
            assert "ledger-worker:" not in err, "no partial plan: %s" % err[:200]


@case
def r21_second_deployable_in_one_repo_gets_its_own_derived_runtime_sa():
    reg, st = load_register(), load_state()
    d = repo(reg, "payments-api")["deploys"]
    d.append({"cloud_run": "payments-batch", "region": "europe-west1"})
    repo(reg, "payments-api")["gcp"]["service_accounts"].append("payments-batch-deployer")
    st["service_accounts"]["payments-batch-run"] = {"iam": []}
    got = shape(of(plan(reg, st), "payments-api"))
    assert needs_deployed_by("payments-batch-run", "payments-batch-deployer") in got, got
    assert needs_deployed_by("payments-api-run", "payments-api-deployer") in got, got


@case
def r21_f7_refuses_a_deployable_under_two_repos():
    reg = load_register()
    repo(reg, "ledger-worker")["deploys"][0]["cloud_run"] = "payments-api"
    repo(reg, "ledger-worker")["deploys"][0]["runtime_service_account"] = "payments-api-run"
    rc, out, err = run(reg, load_state())
    assert rc == 1 and out.strip() == "", (rc, out[:100])
    assert "payments-api" in err and "ledger-worker" in err, err[:300]


@case
def r21_deprecated_protected_input_is_accepted_and_ignored():
    base = run(load_register(), load_state())
    assert base[0] == 0, base
    for val in ("", "payments-api-deployer", "x-yy-zz\nrepo-admin"):
        assert run(load_register(), load_state(), extra=("--protected-service-accounts", val)) == base, val


@case
def repo_admin_sa_email_flag_is_required():
    rc, out, err = run(load_register(), load_state(), admin="")
    assert rc != 0 and out.strip() == "", (rc, out[:100])


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
