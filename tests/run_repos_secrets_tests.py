#!/usr/bin/env python3
"""Fixture tests for the F8 secrets planner, scripts/repos_secrets_plan.py (owner ruling 24).

Contract: docs/repos-secrets.md and docs/repos-register.md (sections 6, 7, 8).

  Invocation   python3 scripts/repos_secrets_plan.py --feature secrets --register <repos.yaml>
                   --state <state.json> [--prune]
               (env REPOS_SECRETS_PLANNER overrides the script path, to prove the suite is not
               vacuous against a stub). The register fixture is JSON in a .yaml file.
  State JSON   {"project_id": "example-proj",
                "service_accounts": {"<sa name>": {}},          # present key = the account exists
                "secrets": {"<secret>": {"iam": [POLICY]}}}      # absent key = the secret is missing
               POLICY = {"role": "roles/..", "members": ["serviceAccount:..", ..]}
  Register     a Cloud Run deploys entry with `env_secret: true` owns the secret `<d>-env`. Any other
               value of the key is an error (the name is derived, never chosen).
  Desired      policy of `<d>-env` is EXACTLY {`<d>-run`: secretAccessor, `<d>-deployer`:
               secretAccessor + secretVersionManager + viewer}.
  Actions      create-secret{secret, labels}, adopt{secret}, add-secret-binding{secret, role, member},
               remove-secret-binding{same}, needs-jgd, drift{would, ...}, in-sync.
               Order per deployable: create-secret | adopt, then bindings (run accessor first, then the
               deployer's accessor, versionManager, viewer), then removals.
  Modes        repo.mode, else defaults.mode, else report. Report: only non-write verbs. A removal is a
               write only in enforce WITH --prune; otherwise drift{would: remove-secret-binding}.
  Errors       missing <d>-deployer -> `error: <repo>: ... run F6 first`, empty stdout, rc 1 (no plan
               for any repo). Missing <d>-run -> needs-jgd, nothing else for that deployable.

Usage:  python3 tests/run_repos_secrets_tests.py
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANNER = Path(os.environ.get("REPOS_SECRETS_PLANNER", ROOT / "scripts" / "repos_secrets_plan.py"))
FIX = Path(__file__).resolve().parent / "fixtures" / "repos_secrets"

ACC = "roles/secretmanager.secretAccessor"
MGR = "roles/secretmanager.secretVersionManager"
VIEW = "roles/secretmanager.viewer"
SFX = "@example-proj.iam.gserviceaccount.com"
WRITE_VERBS = {"create-secret", "add-secret-binding", "remove-secret-binding"}
NON_WRITE = {"in-sync", "drift", "adopt", "needs-jgd"}

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def m(sa):
    return "serviceAccount:" + sa + SFX


def load_register():
    return json.loads((FIX / "repos.yaml").read_text())


def load_state():
    return json.loads((FIX / "state-base.json").read_text())


def repo(reg, name):
    return next(r for r in reg["repos"] if r["name"] == name)


def run(reg, state, extra=(), feature="secrets"):
    with tempfile.TemporaryDirectory(dir=str(ROOT / ".scratch") if (ROOT / ".scratch").is_dir() else None) as d:
        rp, sp = Path(d) / "repos.yaml", Path(d) / "state.json"
        rp.write_text(json.dumps(reg))
        sp.write_text(json.dumps(state))
        p = subprocess.run([sys.executable, str(PLANNER), "--feature", feature,
                            "--register", str(rp), "--state", str(sp)] + list(extra),
                           capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def plan(reg, state, extra=()):
    rc, out, err = run(reg, state, extra)
    assert rc == 0, "rc=%d stderr=%s" % (rc, err.strip()[:300])
    acts = json.loads(out)
    assert isinstance(acts, list)
    for a in acts:
        assert list(a.keys()) == ["feature", "repo", "action", "details"], "bad keys %s" % list(a)
        assert a["feature"] == "secrets", a["feature"]
        assert a["action"] in WRITE_VERBS | NON_WRITE, "verb outside the vocabulary: %s" % a["action"]
    return acts


def of(acts, name):
    return [(a["action"], a["details"]) for a in acts if a["repo"] == name]


def bind(secret, role, mem, verb="add-secret-binding"):
    return (verb, {"secret": secret, "role": role, "member": mem})


def full_policy(d):
    """The four lines F8 writes for deployable d, in plan order."""
    s = d + "-env"
    return [bind(s, ACC, m(d + "-run")), bind(s, ACC, m(d + "-deployer")),
            bind(s, MGR, m(d + "-deployer")), bind(s, VIEW, m(d + "-deployer"))]


def refused(reg, state, who=None, extra=()):
    rc, out, err = run(reg, state, extra)
    assert rc == 1 and out.strip() == "", "rc=%d stdout=%r" % (rc, out[:100])
    if who:
        assert any(l.startswith("error: %s:" % who) for l in err.splitlines()), err[:300]
    return err


def apply_policy(acts, state):
    """Simulate the writes on the state's policies; return {secret: {(role, member)}}."""
    pol = {s: {(e["role"], mem) for e in v["iam"] for mem in e["members"]}
           for s, v in state["secrets"].items()}
    for verb, d in [(a["action"], a["details"]) for a in acts]:
        if verb == "create-secret":
            pol.setdefault(d["secret"], set())
        elif verb == "add-secret-binding":
            pol[d["secret"]].add((d["role"], d["member"]))
        elif verb == "remove-secret-binding":
            pol[d["secret"]].discard((d["role"], d["member"]))
    return pol


# ------------------------------------------------------------------ cases

@case
def create_a_missing_secret_then_both_policy_lines_enforce():
    acts = plan(load_register(), load_state())
    assert of(acts, "ledger-worker") == [
        ("create-secret", {"secret": "ledger-worker-env",
                           "labels": {"managed-by": "repos-secrets", "deployable": "ledger-worker"}}),
    ] + full_policy("ledger-worker"), of(acts, "ledger-worker")


@case
def a_converged_secret_is_in_sync_and_unregistered_repos_get_nothing():
    acts = plan(load_register(), load_state())
    assert of(acts, "payments-api") == [("in-sync", {})], of(acts, "payments-api")
    # no env_secret (billing-web) or a gke entry (batch-runner): no action at all, even though a
    # foreign secret exists for billing-web
    assert of(acts, "billing-web") == [] and of(acts, "batch-runner") == []


@case
def adopt_an_existing_secret_in_place_never_recreate():
    st = load_state()
    st["secrets"]["ledger-worker-env"] = {"iam": []}
    acts = plan(load_register(), st)
    got = of(acts, "ledger-worker")
    assert got == [("adopt", {"secret": "ledger-worker-env"})] + full_policy("ledger-worker"), got
    assert not any(a["action"] == "create-secret" and a["details"]["secret"] == "ledger-worker-env"
                   for a in acts)


@case
def report_mode_plans_the_same_as_drift_and_writes_nothing():
    reg = load_register()
    repo(reg, "ledger-worker")["mode"] = "report"
    acts = plan(reg, load_state())
    got = of(acts, "ledger-worker")
    assert got[0] == ("drift", {"would": "create-secret", "secret": "ledger-worker-env",
                                "labels": {"managed-by": "repos-secrets", "deployable": "ledger-worker"}})
    assert got[1:] == [("drift", dict({"would": v}, **d)) for v, d in full_policy("ledger-worker")], got
    assert not any(a["action"] in WRITE_VERBS for a in acts if a["repo"] == "ledger-worker")
    # the other repo is still enforced
    reg2 = load_register()
    reg2["defaults"]["mode"] = "report"
    assert not any(a["action"] in WRITE_VERBS for a in plan(reg2, load_state()))


@case
def missing_deployer_is_an_error_naming_f6_and_plans_nothing():
    st = load_state()
    del st["service_accounts"]["ledger-worker-deployer"]
    err = refused(load_register(), st, who="ledger-worker")
    assert "F6" in err and "ledger-worker-deployer" in err, err[:300]


@case
def missing_runtime_sa_is_needs_jgd_and_nothing_else_for_that_deployable():
    st = load_state()
    del st["service_accounts"]["ledger-worker-run"]
    acts = plan(load_register(), st)
    got = of(acts, "ledger-worker")
    assert [v for v, _ in got] == ["needs-jgd"], got
    d = got[0][1]
    assert d["resource_type"] == "iam.serviceAccount" and d["resource"] == "ledger-worker-run" + SFX, d
    assert "ledger-worker-run" in d["needs"], d
    assert of(acts, "payments-api") == [("in-sync", {})]


@case
def extra_member_is_reported_and_removed_only_under_prune_in_enforce():
    st = load_state()
    st["secrets"]["payments-api-env"]["iam"][0]["members"].append(m("github-rotator"))
    st["secrets"]["payments-api-env"]["iam"].append(
        {"role": "roles/secretmanager.admin", "members": [m("payments-api-deployer")]})
    extra_a = ("remove-secret-binding", {"secret": "payments-api-env", "role": ACC, "member": m("github-rotator")})
    extra_b = ("remove-secret-binding", {"secret": "payments-api-env",
                                         "role": "roles/secretmanager.admin", "member": m("payments-api-deployer")})
    as_drift = [("drift", dict({"would": v}, **d)) for v, d in (extra_a, extra_b)]
    # enforce, no prune: reported, not written
    assert of(plan(load_register(), st), "payments-api") == as_drift
    # enforce + prune: removed
    assert of(plan(load_register(), st, ("--prune",)), "payments-api") == [extra_a, extra_b]
    # report + prune: still only drift
    reg = load_register()
    repo(reg, "payments-api")["mode"] = "report"
    assert of(plan(reg, st, ("--prune",)), "payments-api") == as_drift
    # prune never removes a wanted line
    pol = apply_policy(plan(load_register(), st, ("--prune",)), st)["payments-api-env"]
    assert pol == {(a, b) for _, d in full_policy("payments-api") for a, b in [(d["role"], d["member"])]}, pol


@case
def policy_written_is_exactly_run_accessor_and_deployer_sync_roles():
    st = load_state()
    st["secrets"]["payments-api-env"] = {"iam": [
        {"role": ACC, "members": [m("github-rotator")]},
        {"role": MGR, "members": [m("github-rotator")]}]}
    pol = apply_policy(plan(load_register(), st, ("--prune",)), st)
    want = {(ACC, m("payments-api-run")), (ACC, m("payments-api-deployer")),
            (MGR, m("payments-api-deployer")), (VIEW, m("payments-api-deployer"))}
    assert pol["payments-api-env"] == want, pol["payments-api-env"]
    assert pol["ledger-worker-env"] == {(r, mem) for _, d in full_policy("ledger-worker")
                                        for r, mem in [(d["role"], d["member"])]}
    # nothing else is touched: the foreign secrets keep their policy
    assert pol["web-env"] == {("roles/secretmanager.admin", "user:a@example.com")}
    assert pol["billing-web-env"] == {(ACC, m("someone-else"))}


@case
def a_secret_name_is_derived_never_chosen():
    # a repo cannot name another service's secret, in any spelling
    for bad in ("web-env", "payments-api-env", "true", "yes", 1, 0, "", None, [], {"name": "web-env"}):
        reg = load_register()
        repo(reg, "payments-api")["deploys"][0]["env_secret"] = bad
        err = refused(reg, load_state())
        assert "env_secret" in err, (bad, err[:300])


@case
def env_secret_false_or_absent_means_no_secret():
    reg = load_register()
    repo(reg, "ledger-worker")["deploys"][0]["env_secret"] = False
    rc, out, err = run(reg, load_state())
    # `false` is not the opt-in value: the schema allows only true (or the key absent)
    assert rc == 1 and "env_secret" in err, (rc, err[:200])
    del repo(reg, "ledger-worker")["deploys"][0]["env_secret"]
    assert of(plan(reg, load_state()), "ledger-worker") == []


@case
def only_derived_names_are_ever_touched_and_only_the_four_roles_are_bound():
    st = load_state()
    st["secrets"]["app-secrets"] = {"iam": [{"role": ACC, "members": [m("payments-api-run")]}]}
    acts = plan(load_register(), st, ("--prune",))
    derived = {"payments-api-env", "ledger-worker-env"}
    for a in acts:
        d = a["details"]
        s = d.get("secret")
        if a["action"] in WRITE_VERBS:
            assert s in derived, a
            if a["action"] != "create-secret":
                assert d["role"] in (ACC, MGR, VIEW), a
                assert d["member"].startswith("serviceAccount:"), a
                assert d["member"].split(":")[1].split("@")[0] in (a["repo"] + "-run", a["repo"] + "-deployer"), a
    assert not any("app-secrets" in json.dumps(a) or "web-env" in json.dumps(a) for a in acts)


@case
def no_verb_to_delete_a_secret_or_touch_a_version_exists():
    acts = plan(load_register(), load_state(), ("--prune",))
    blob = " ".join(a["action"] for a in acts)
    for banned in ("delete", "destroy", "version", "disable", "access", "key", "project"):
        assert banned not in blob, banned
    src = PLANNER.read_text()
    for banned in ("delete-secret", "add-secret-version", "destroy-version", "disable-version"):
        assert banned not in src, banned


@case
def invalid_register_plans_nothing():
    reg = load_register()
    repo(reg, "payments-api")["deploys"][0]["region"] = "--region=x"
    refused(reg, load_state())
    reg = load_register()
    repo(reg, "ledger-worker")["deploys"][0]["cloud_run"] = "payments-api"      # a deployable under two repos
    refused(reg, load_state())


@case
def a_deployable_whose_runtime_name_is_not_a_valid_account_id_is_an_error():
    reg = load_register()
    repo(reg, "ledger-worker")["deploys"][0]["cloud_run"] = "a"                  # a-run is 5 chars
    st = load_state()
    st["service_accounts"].update({"a-deployer": {}, "a-run": {}})
    refused(reg, st, who="ledger-worker")


@case
def unknown_feature_and_unknown_flag_are_rejected_and_output_is_deterministic():
    rc, out, err = run(load_register(), load_state(), feature="deploy-scope")
    assert rc != 0 and out.strip() == "", (rc, out[:100])
    rc, out, err = run(load_register(), load_state(), extra=("--protected-service-accounts", "x"))
    assert rc == 2 and out.strip() == "", (rc, out[:100])
    a = run(load_register(), load_state(), ("--prune",))
    b = run(load_register(), load_state(), ("--prune",))
    assert a == b


@case
def a_secret_whose_policy_has_an_unknown_member_type_is_pruned_too():
    st = load_state()
    st["secrets"]["payments-api-env"]["iam"].append({"role": VIEW, "members": ["user:a@example.com"]})
    got = of(plan(load_register(), st, ("--prune",)), "payments-api")
    assert got == [("remove-secret-binding", {"secret": "payments-api-env", "role": VIEW,
                                              "member": "user:a@example.com"})], got


@case
def the_workflow_is_thin_and_has_no_version_or_delete_call():
    wf = (ROOT / ".github" / "workflows" / "repos-secrets.yml").read_text()
    for banned in ("versions add", "versions access", "versions destroy", "versions disable",
                   "secrets delete", "secrets versions"):
        assert banned not in wf, banned
    assert "repos_secrets_plan.py" in wf and "prune" in wf


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
