#!/usr/bin/env python3
"""Fixture tests for the F9 environments planner, scripts/repos_env_plan.py.

Contract: docs/repos-register.md §3 (the `environments:` key), §7.1 (F9 live state), §8 (action
list) and docs/repos-environments.md. Invocation:

    python3 scripts/repos_env_plan.py --feature environments --register <repos.yaml> --state <state.json>

(env REPOS_ENV_PLANNER overrides the script path.) The register fixture is JSON in a .yaml file.

State JSON: {"repos": {"<repo>": {"exists": bool, "environments": {"<env>":
  {"custom_branch_policies": bool, "policies": [{"name": str, "type": "branch"|"tag"}]}}}}}

Pinned here (the doc leaves them to the fixtures):
  * verbs: create-environment, add-branch-policy, remove-branch-policy, in-sync,
    unmanaged-environment, drift (report mode); NO other verb, and never one that deletes an
    environment or writes a secret/variable/reviewer;
  * a missing environment yields create-environment first, then one add-branch-policy per listed
    pattern; a policy is the pair (name, type), so the right name with the wrong type is one
    remove plus one add;
  * a repo with no `environments:` key is not examined: no action at all;
  * an error (repo `exists: false`, malformed register) prints nothing to stdout, one
    `error: <repo>: ...` line to stderr, exit 1.

Usage:  python3 tests/run_repos_env_plan_tests.py
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANNER = Path(os.environ.get("REPOS_ENV_PLANNER", ROOT / "scripts" / "repos_env_plan.py"))
FIX = Path(__file__).resolve().parent / "fixtures-repos-env"

ALLOWED = {"create-environment", "add-branch-policy", "remove-branch-policy", "in-sync",
           "unmanaged-environment", "drift", "skip", "unsupported"}
WRITE = {"create-environment", "add-branch-policy", "remove-branch-policy"}


def load_register():
    return json.loads((FIX / "repos.yaml").read_text())


def load_state():
    return json.loads((FIX / "state-base.json").read_text())


def repo(reg, name):
    return next(r for r in reg["repos"] if r["name"] == name)


def run(reg, state, feature="environments", extra=()):
    assert PLANNER.is_file(), "planner %s does not exist" % PLANNER.name
    with tempfile.TemporaryDirectory(dir=str(ROOT / ".scratch") if (ROOT / ".scratch").is_dir() else None) as d:
        rp, sp = Path(d) / "repos.yaml", Path(d) / "state.json"
        rp.write_text(json.dumps(reg))
        sp.write_text(json.dumps(state))
        p = subprocess.run([sys.executable, str(PLANNER), "--feature", feature,
                            "--register", str(rp), "--state", str(sp)] + list(extra),
                           capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def plan(reg, state):
    rc, out, err = run(reg, state)
    assert rc == 0, "rc=%d stderr=%s" % (rc, err.strip()[:300])
    try:
        acts = json.loads(out)
    except ValueError:
        raise AssertionError("stdout is not JSON: %r" % out[:200])
    assert isinstance(acts, list), "stdout is not an array"
    for a in acts:
        assert list(a.keys()) == ["feature", "repo", "action", "details"], "bad keys %s" % list(a)
        assert a["feature"] == "environments", "feature %r" % a["feature"]
        assert a["action"] in ALLOWED, "verb outside the contract: %s" % a["action"]
    return acts


def of(acts, name):
    return [a for a in acts if a["repo"] == name]


def shape(acts):
    return [(a["action"], a["details"]) for a in acts]


def pol(env, name, typ="branch"):
    return {"environment": env, "name": name, "type": typ}


def refused(reg, state, who):
    rc, out, err = run(reg, state)
    assert rc == 1, "rc=%s (want 1) stderr=%s" % (rc, err.strip()[:200])
    assert out.strip() == "", "stdout must be empty on error: %r" % out[:100]
    assert err.startswith("error: ") or "\nerror: " in err, err[:200]
    assert who in err, "error does not name %r: %s" % (who, err[:200])


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def everything_as_listed_is_in_sync_and_unlisted_repo_is_not_examined():
    acts = plan(load_register(), load_state())
    for name in ("svc-a", "svc-b"):
        mine = of(acts, name)
        assert mine and all(a["action"] == "in-sync" for a in mine), shape(mine)
    assert of(acts, "web") == [], "a repo with no environments: key must yield no action"


@case
def missing_environment_is_created_then_each_pattern_added():
    st = load_state()
    del st["repos"]["svc-a"]["environments"]["stage"]
    mine = of(plan(load_register(), st), "svc-a")
    s = shape([a for a in mine if a["action"] != "in-sync"])
    assert s[0] == ("create-environment", {"environment": "stage"}), s
    assert sorted(map(json.dumps, s[1:])) == sorted(map(json.dumps, [
        ("add-branch-policy", pol("stage", "main")),
        ("add-branch-policy", pol("stage", "v*", "tag"))])), s
    assert len(s) == 3, s


@case
def missing_pattern_on_existing_environment_is_added():
    st = load_state()
    st["repos"]["svc-b"]["environments"]["prod"]["policies"] = []
    mine = of(plan(load_register(), st), "svc-b")
    assert shape(mine) == [("add-branch-policy", pol("prod", "main"))], shape(mine)


@case
def custom_policies_off_still_adds_the_missing_pattern_with_no_extra_verb():
    st = load_state()
    e = st["repos"]["svc-b"]["environments"]["prod"]
    e["custom_branch_policies"] = False
    e["policies"] = []
    mine = of(plan(load_register(), st), "svc-b")
    assert ("add-branch-policy", pol("prod", "main")) in shape(mine), shape(mine)
    assert not any(a["action"] == "in-sync" for a in mine), shape(mine)


@case
def tag_policy_is_added_with_type_tag():
    reg = load_register()
    repo(reg, "svc-b")["environments"] = [{"name": "rel", "tags": ["v*"]}]
    mine = of(plan(reg, load_state()), "svc-b")
    s = shape(mine)
    assert s[0] == ("create-environment", {"environment": "rel"}), s
    assert ("add-branch-policy", pol("rel", "v*", "tag")) in s, s
    assert not any(d.get("type") == "branch" for a, d in s if a == "add-branch-policy"), s


@case
def extra_policy_on_a_listed_environment_is_removed():
    st = load_state()
    st["repos"]["svc-b"]["environments"]["prod"]["policies"].append({"name": "dev", "type": "branch"})
    mine = of(plan(load_register(), st), "svc-b")
    assert shape(mine) == [("remove-branch-policy", pol("prod", "dev"))], shape(mine)


@case
def right_name_wrong_type_is_one_remove_and_one_add():
    st = load_state()
    st["repos"]["svc-b"]["environments"]["prod"]["policies"] = [{"name": "main", "type": "tag"}]
    s = shape(of(plan(load_register(), st), "svc-b"))
    assert sorted(map(json.dumps, s)) == sorted(map(json.dumps, [
        ("remove-branch-policy", pol("prod", "main", "tag")),
        ("add-branch-policy", pol("prod", "main", "branch"))])), s


@case
def unmanaged_environment_is_reported_and_left_alone():
    st = load_state()
    st["repos"]["svc-b"]["environments"]["scratch"] = {"custom_branch_policies": False, "policies": []}
    mine = of(plan(load_register(), st), "svc-b")
    un = [a for a in mine if a["action"] == "unmanaged-environment"]
    assert len(un) == 1 and un[0]["details"] == {"environment": "scratch"}, shape(mine)
    assert not [a for a in mine if a["details"].get("environment") == "scratch"
                and a["action"] != "unmanaged-environment"], "an unmanaged environment was acted on"


@case
def unmanaged_environment_is_reported_in_report_mode_too():
    reg = load_register()
    repo(reg, "svc-b")["mode"] = "report"
    st = load_state()
    st["repos"]["svc-b"]["environments"]["scratch"] = {"custom_branch_policies": False, "policies": []}
    mine = of(plan(reg, st), "svc-b")
    assert ("unmanaged-environment", {"environment": "scratch"}) in shape(mine), shape(mine)


@case
def report_mode_yields_only_non_write_verbs_with_drift():
    reg = load_register()
    repo(reg, "svc-a")["mode"] = "report"
    st = load_state()
    del st["repos"]["svc-a"]["environments"]["stage"]
    st["repos"]["svc-a"]["environments"]["prod"]["policies"].append({"name": "dev", "type": "branch"})
    mine = of(plan(reg, st), "svc-a")
    assert not [a for a in mine if a["action"] in WRITE], "write verb in report mode: %s" % shape(mine)
    drifts = [a["details"] for a in mine if a["action"] == "drift"]
    assert {"would": "create-environment", "environment": "stage"} in drifts, drifts
    assert dict(would="remove-branch-policy", **pol("prod", "dev")) in drifts, drifts
    assert dict(would="add-branch-policy", **pol("stage", "main")) in drifts, drifts


@case
def mode_falls_back_to_defaults_then_report():
    reg = load_register()
    del reg["defaults"]
    st = load_state()
    del st["repos"]["svc-b"]["environments"]["prod"]
    mine = of(plan(reg, st), "svc-b")
    assert mine and not [a for a in mine if a["action"] in WRITE], shape(mine)
    assert any(a["action"] == "drift" for a in mine), shape(mine)


@case
def no_delete_verb_ever_even_when_register_drops_every_environment():
    reg = load_register()
    for r in reg["repos"]:
        r["environments"] = [{"name": "keep-one", "branches": ["main"]}] if r["name"] == "svc-b" else r.get("environments", [])
    repo(reg, "svc-a")["environments"] = [{"name": "only", "branches": ["main"]}]
    for mode in ("enforce", "report"):
        for r in reg["repos"]:
            r["mode"] = mode
        acts = plan(reg, load_state())
        for a in acts:
            blob = json.dumps(a).lower()
            for bad in ("delete", "secret", "variable", "reviewer", "wait"):
                assert bad not in a["action"].lower(), "forbidden verb %s" % a["action"]
        un = {(a["repo"], a["details"]["environment"]) for a in acts if a["action"] == "unmanaged-environment"}
        assert ("svc-a", "prod") in un and ("svc-a", "stage") in un, un


@case
def repo_that_does_not_exist_refuses_the_whole_run():
    st = load_state()
    st["repos"]["svc-b"] = {"exists": False}
    refused(load_register(), st, "svc-b")


@case
def repo_not_in_the_register_yields_no_action():
    st = load_state()
    st["repos"]["stranger"] = {"exists": True, "environments": {
        "prod": {"custom_branch_policies": False, "policies": []}}}
    acts = plan(load_register(), st)
    assert of(acts, "stranger") == [], shape(of(acts, "stranger"))


@case
def malformed_register_environment_with_neither_branches_nor_tags_is_refused():
    reg = load_register()
    repo(reg, "svc-b")["environments"] = [{"name": "prod"}]
    refused(reg, load_state(), "svc-b")


@case
def malformed_register_duplicate_environment_name_in_a_repo_is_refused():
    reg = load_register()
    repo(reg, "svc-b")["environments"] = [{"name": "prod", "branches": ["main"]},
                                        {"name": "prod", "branches": ["dev"]}]
    refused(reg, load_state(), "svc-b")


@case
def malformed_register_environment_without_name_is_refused():
    reg = load_register()
    repo(reg, "svc-b")["environments"] = [{"branches": ["main"]}]
    refused(reg, load_state(), "svc-b")


@case
def malformed_register_empty_pattern_is_refused():
    reg = load_register()
    repo(reg, "svc-b")["environments"] = [{"name": "prod", "branches": [""]}]
    refused(reg, load_state(), "svc-b")


@case
def malformed_register_bad_environment_name_is_refused():
    reg = load_register()
    repo(reg, "svc-b")["environments"] = [{"name": "-rf prod", "branches": ["main"]}]
    refused(reg, load_state(), "svc-b")


@case
def one_bad_repo_means_no_partial_plan():
    reg = load_register()
    repo(reg, "svc-b")["environments"] = [{"name": "prod"}]
    st = load_state()
    del st["repos"]["svc-a"]["environments"]["stage"]      # svc-a alone would plan writes
    refused(reg, st, "svc-b")


@case
def required_reviewers_and_secrets_are_not_register_keys():
    reg = load_register()
    repo(reg, "svc-b")["environments"][0].update(
        {"reviewers": ["someone"], "wait_timer": 30, "secrets": {"X": "y"}})
    acts = plan(reg, load_state())
    assert shape(of(acts, "svc-b")) == [("in-sync", {})], shape(of(acts, "svc-b"))


@case
def unknown_feature_exits_nonzero_with_nothing_on_stdout():
    rc, out, err = run(load_register(), load_state(), feature="no-such-feature")
    assert rc != 0 and out.strip() == "", (rc, out[:100])


@case
def same_input_same_output():
    st = load_state()
    del st["repos"]["svc-a"]["environments"]["stage"]
    a = run(load_register(), copy.deepcopy(st))
    b = run(load_register(), copy.deepcopy(st))
    assert a[0] == 0 and a == b, (a[0], b[0])


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
            print("ok   %s" % fn.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (fn.__name__, str(e)[:300]))
        except Exception as e:
            failed += 1
            print("FAIL %s: %s: %s" % (fn.__name__, type(e).__name__, str(e)[:300]))
    print("%d cases run, %d failed" % (len(CASES), failed))
    return 1 if failed or not CASES else 0


if __name__ == "__main__":
    sys.exit(main())
