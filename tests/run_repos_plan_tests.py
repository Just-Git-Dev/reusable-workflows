#!/usr/bin/env python3
"""Self-test for the repos planner, scripts/repos_plan.py (features F1-F4).

Contract under test: docs/repos-register.md sections 2-8. The planner is a pure program run as a
subprocess, and this file is the IMPLEMENTER'S CONTRACT for its command line and live-state shape:

    python3 scripts/repos_plan.py --feature <register|create|settings|variables>
                                  --register <repos.yaml> --state <state.json>

  * stdout: one JSON array of {feature, repo, action, details} (keys in that order), exit 0.
  * on any error: NOTHING on stdout, `error: <repo|sa|register>: <reason>` lines on stderr, exit 1.
  * `--feature register` (F1) needs no live state: --state may be omitted for it. It emits one
    `in-sync` entry (feature `register`) per repo in the register when the register is valid.
  * an unknown --feature exits non-zero with nothing on stdout.

Live-state JSON (what the workflow fetches from GitHub; one entry per repo it looked up):

    {"repos": {"<name>": {"exists": true|false,
                          "description": str, "visibility": "private"|"internal"|"public",
                          "default_branch": str, "settings": {<bool settings>},
                          "variables": {<NAME>: <value>}}}}

  A repo with `exists: false`, or absent from `repos`, does not exist. Live repos that the register
  does not list must produce no action at all.

Every run is checked against the section 8 invariants (no verb outside the two tables, report mode
never writes, rename only via rename_from, never visibility -> public, key order).

Set REPOS_PLANNER=<path> to run the suite against a stand-in planner (used to prove the tests are
not vacuous). Usage:  python3 tests/run_repos_plan_tests.py
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANNER = Path(os.environ.get("REPOS_PLANNER") or ROOT / "scripts" / "repos_plan.py")
SCHEMA = ROOT / "schemas" / "repos.v1.json"
FIX = Path(__file__).resolve().parent / "fixtures-repos"
WORK = FIX / ".work"

NON_WRITE = {"in-sync", "skip", "drift", "unsupported"}
WRITE = {"create-repo", "rename-repo", "update-repo", "set-variable"}  # F1-F4 share of section 8
ALL_VERBS = NON_WRITE | WRITE | {
    "add-wif-binding", "create-service-account", "update-service-account",
    "create-service", "add-resource-binding"}
FEATURES = ["register", "create", "settings", "variables"]

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# ---------------------------------------------------------------- helpers

_n = 0


def _write(obj_or_path, suffix):
    """A dict becomes a file (JSON is valid YAML); a Path is used as-is."""
    global _n
    if isinstance(obj_or_path, Path):
        return obj_or_path
    WORK.mkdir(parents=True, exist_ok=True)
    _n += 1
    p = WORK / f"in{_n}{suffix}"
    p.write_text(json.dumps(obj_or_path))
    return p


def run(feature, register, state=None, planner=None):
    """Return (rc, stdout, stderr)."""
    cmd = [sys.executable, str(planner or PLANNER), "--feature", feature,
           "--register", str(_write(register, ".yaml"))]
    if state is not None:
        cmd += ["--state", str(_write(state, ".json"))]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout, p.stderr


def reg(repos, defaults=None, **top):
    d = {"mode": "report", "visibility": "private", "default_branch": "main"}
    d.update(defaults or {})
    r = {"version": 1, "org": "Example-Org", "defaults": d, "repos": repos}
    r.update(top)
    return r


def st(**repos):
    return {"repos": repos}


def live(**kw):
    kw.setdefault("exists", True)
    return kw


def plan(feature, register, state=None):
    """Run, require success, return parsed actions after invariant checks."""
    rc, out, err = run(feature, register, state)
    assert rc == 0, f"expected exit 0, got {rc}; stderr={err!r}"
    actions = json.loads(out)
    check_invariants(feature, register, actions)
    return actions


def refused(feature, register, state=None, who=None):
    rc, out, err = run(feature, register, state)
    assert rc == 1, f"expected exit 1, got {rc}; stdout={out!r} stderr={err!r}"
    assert out == "", f"error run must print nothing to stdout, got {out!r}"
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert lines and all(ln.startswith("error: ") for ln in lines), f"bad stderr: {err!r}"
    if who:
        assert any(ln.startswith(f"error: {who}:") for ln in lines), f"no error for {who}: {err!r}"
    return err


def load_register(reg_or_path):
    if isinstance(reg_or_path, Path):
        import yaml  # PyYAML, as the planner itself needs for repos.yaml
        return yaml.safe_load(reg_or_path.read_text())
    return reg_or_path


def effective_mode(register, name):
    repo = next(r for r in register["repos"] if r["name"] == name)
    return repo.get("mode") or (register.get("defaults") or {}).get("mode") or "report"


def check_invariants(feature, register, actions):
    register = load_register(register)
    assert isinstance(actions, list), "stdout must be a JSON array"
    listed = {r["name"]: r for r in register["repos"]}
    for a in actions:
        assert list(a.keys()) == ["feature", "repo", "action", "details"], f"keys/order: {a}"
        assert a["feature"] == feature, f"feature {feature} emitted {a['feature']} entry: {a}"
        assert a["action"] in ALL_VERBS, f"verb outside the section 8 tables: {a}"
        assert isinstance(a["details"], dict), a
        assert a["repo"] in listed, f"action for a repo absent from the register: {a}"
        mode = effective_mode(register, a["repo"])
        if mode == "report":
            assert a["action"] in NON_WRITE, f"report-mode repo got a write verb: {a}"
        if a["action"] == "drift":
            assert a["details"].get("would") in WRITE, f"drift.would must be a write verb: {a}"
        if a["action"] == "rename-repo":
            assert listed[a["repo"]].get("rename_from") == a["details"]["from"], \
                f"rename without rename_from: {a}"
        if a["action"] == "update-repo":
            assert a["details"].get("field") != "visibility", f"visibility is never written: {a}"
        if a["action"] == "create-repo":
            assert a["details"]["visibility"] in ("private", "internal"), a
    return actions


def verbs(actions, repo=None):
    return [a["action"] for a in actions if repo is None or a["repo"] == repo]


def for_repo(actions, repo):
    return [a for a in actions if a["repo"] == repo]


def by_field(actions):
    return {a["details"]["field"]: a["details"] for a in actions if a["action"] == "update-repo"}


# ---------------------------------------------------------------- schema (data file)

def _schema():
    return json.loads(SCHEMA.read_text())


@case
def schema_is_draft_2020_12_and_requires_top_level_keys():
    s = _schema()
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(s["required"]) == {"version", "org", "repos"}
    assert s["properties"]["version"]["const"] == 1


@case
def schema_visibility_is_private_or_internal_never_public():
    s = _schema()
    enums = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "enum":
                    enums.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(s)
    assert any(set(e) == {"private", "internal"} for e in enums), enums
    assert not any("public" in e for e in enums), "public must not be an allowed value"
    assert any(set(e) == {"report", "enforce"} for e in enums), "mode enum missing"


@case
def schema_sa_name_pattern_and_required_description():
    d = _schema()["$defs"]
    assert d["saName"]["pattern"] == "^[a-z][a-z0-9-]{4,28}[a-z0-9]$"
    assert set(d["serviceAccount"]["required"]) == {"name", "description"}


@case
def schema_allows_unknown_keys_everywhere_the_doc_says():
    s = _schema()
    for node in (s, s["$defs"]["defaults"], s["$defs"]["repo"], s["$defs"]["serviceAccount"]):
        assert node.get("additionalProperties", True) is not False, node


@case
def schema_validates_fixtures():
    # docs/repos-register.md 7.2: a missing dependency FAILS the suite, never skips it
    try:
        import jsonschema
        import yaml
    except ImportError as e:
        raise AssertionError(f"required dependency missing ({e}); run via `make venv`'s python")
    v = jsonschema.Draft202012Validator(_schema())
    ok = yaml.safe_load((FIX / "valid-register.yaml").read_text())
    assert not list(v.iter_errors(ok)), "valid-register.yaml must validate"
    for name in sorted(FIX.glob("invalid-*.yaml")):
        bad = yaml.safe_load(name.read_text())
        assert list(v.iter_errors(bad)), f"{name.name} must NOT validate"


# ---------------------------------------------------------------- F1 register

@case
def register_valid_fixture_is_accepted_one_in_sync_per_repo():
    a = plan("register", FIX / "valid-register.yaml")
    assert [(x["repo"], x["action"]) for x in a] == [
        ("payments-api", "in-sync"), ("ledger-worker", "in-sync"), ("billing-web", "in-sync")]


@case
def register_empty_repos_list_yields_empty_array():
    assert plan("register", reg([])) == []


@case
def register_public_visibility_is_an_error_exit_1_no_stdout():
    refused("register", FIX / "invalid-public-visibility.yaml", who="payments-api")


@case
def register_public_in_defaults_is_an_error_too():
    refused("register", reg([{"name": "payments-api"}], defaults={"visibility": "public"}))


@case
def register_each_invalid_fixture_is_refused():
    for f in ("invalid-sa-name-too-short.yaml", "invalid-sa-no-description.yaml",
              "invalid-version.yaml", "invalid-bad-mode.yaml"):
        refused("register", FIX / f)


@case
def register_sa_name_length_bounds_6_to_30():
    def sa(n):
        return reg([], service_accounts=[{"name": n, "description": "d"}])
    assert plan("register", sa("a" * 6)) == []
    assert plan("register", sa("a" * 30)) == []
    refused("register", sa("a" * 5))
    refused("register", sa("a" * 31))
    refused("register", sa("Abcdef"))
    refused("register", sa("abcdef-"))


@case
def register_duplicate_repo_names_refused():
    refused("register", reg([{"name": "payments-api"}, {"name": "payments-api"}]))


@case
def register_rename_from_must_differ_and_not_collide_with_another_entry():
    refused("register", reg([{"name": "a-repo", "rename_from": "a-repo"}]))
    refused("register", reg([{"name": "a-repo", "rename_from": "b-repo"}, {"name": "b-repo"}]))


@case
def register_missing_org_or_repos_refused():
    r = reg([])
    del r["org"]
    refused("register", r)
    r = reg([])
    del r["repos"]
    refused("register", r)


@case
def register_invalid_variable_and_settings_values_refused():
    refused("register", reg([{"name": "payments-api", "variables": {"lower": "x"}}]))
    refused("register", reg([{"name": "payments-api", "variables": {"GITHUB_X": "x"}}]))
    refused("register", reg([{"name": "payments-api", "variables": {"A": 1}}]))
    refused("register", reg([{"name": "payments-api", "settings": {"has_wiki": "yes"}}]))


def _deploy(**kw):
    d = {"cloud_run": "payments-api", "region": "europe-west1",
         "runtime_service_account": "payments-api-run", "image_repository": "europe-west1/services"}
    d.update(kw)
    return {"name": "payments-api", "deploys": [d]}


@case
def m3_name_patterns_and_no_leading_dash_in_the_register():
    # controls first: the unmodified values are accepted, so each refusal below is the pattern's doing
    for ok in (_deploy(), {"name": ".hidden"}, {"name": "a.b_c-d"}, {"name": "x", "default_branch": "release/1.x"}):
        rc, out, err = run("register", reg([ok]))
        assert rc == 0, f"control {ok} refused: {err!r}"
    bad = [
        {"name": "-evil"}, {"name": "--ingress=all"}, {"name": "."}, {"name": ".."},
        {"name": "ok-name", "rename_from": "--x"}, {"name": "ok-name", "rename_from": ".."},
        {"name": "ok-name", "default_branch": "--delete"},
        _deploy(cloud_run="--ingress=all"), _deploy(cloud_run="-x"), _deploy(cloud_run="Upper"),
        _deploy(cloud_run="a" * 64), _deploy(cloud_run="trailing-"),
        _deploy(region="--region=x"), _deploy(region="europe_west1"), _deploy(region="europe-west"),
        _deploy(region="Europe-west1"), _deploy(region="europe-west1\n"),
        _deploy(cloud_run="payments-api\n"),
        _deploy(runtime_service_account="--x-run"),
        _deploy(image_repository="--x/services"), _deploy(image_repository="loc/--x"),
        {"name": "g", "deploys": [{"gke": {"cluster": "--c/main", "namespace": "ns", "workload": "w"}}]},
        {"name": "g", "deploys": [{"gke": {"cluster": "l/main", "namespace": "-ns", "workload": "w"}}]},
        {"name": "g", "deploys": [{"gke": {"cluster": "l/main", "namespace": "ns", "workload": "--w"}}]},
    ]
    for b in bad:
        refused("register", reg([b]))


@case
def m3_leading_dash_and_dot_names_are_refused_by_the_f2_f3_planners_too():
    for feature in ("create", "settings"):
        for b in ({"name": "-evil"}, {"name": ".."}, {"name": "ok-name", "default_branch": "--x"}):
            refused(feature, reg([b]), st())
    # rename_from is read by F2 only (7.2: each planner validates only the keys it reads)
    for b in ({"name": "ok-name", "rename_from": "--x"}, {"name": "ok-name", "rename_from": ".."}):
        refused("create", reg([b]), st())


@case
def register_unknown_keys_anywhere_are_accepted():
    r = reg([{"name": "payments-api", "future_key": {"a": 1}, "settings": {"new_setting": 3}}],
            future_top="x")
    r["defaults"]["future_default"] = 1
    assert [x["action"] for x in plan("register", r)] == ["in-sync"]


@case
def schema_env_secret_is_the_boolean_true_only_on_a_cloud_run_entry():
    # F8 (ruling 24): the secret name is derived (`<cloud_run>-env`), so the opt-in is `true`, never a name
    rc, out, err = run("register", reg([_deploy(env_secret=True)]))
    assert rc == 0, f"env_secret: true refused: {err!r}"
    for bad in ("web-env", "payments-api-env", "true", False, 1, None, [], {}):
        rc, out, err = run("register", reg([_deploy(env_secret=bad)]))
        assert rc == 1 and out.strip() == "" and "env_secret" in err, (bad, rc, err[:200])
    s = json.dumps(_schema())
    assert "env_secret" in s, "schemas/repos.v1.json does not know env_secret"


# ---------------------------------------------------------------- F2 create

@case
def create_status_new_missing_enforce_emits_create_repo():
    r = reg([{"name": "ledger-worker", "status": "new", "mode": "enforce",
              "description": "Ledger worker"}])
    a = plan("create", r, st(**{"ledger-worker": {"exists": False}}))
    assert a == [{"feature": "create", "repo": "ledger-worker", "action": "create-repo",
                  "details": {"visibility": "private", "default_branch": "main",
                              "description": "Ledger worker"}}]


@case
def create_description_absent_is_null_and_visibility_is_the_registers():
    r = reg([{"name": "ledger-worker", "status": "new", "mode": "enforce",
              "visibility": "internal", "default_branch": "trunk"}])
    a = plan("create", r, st())  # absent from live state == missing
    assert a[0]["details"] == {"visibility": "internal", "default_branch": "trunk",
                               "description": None}


@case
def create_status_new_missing_report_is_drift_would_create():
    r = reg([{"name": "ledger-worker", "status": "new"}])  # inherits report
    a = plan("create", r, st(**{"ledger-worker": {"exists": False}}))
    assert len(a) == 1 and a[0]["action"] == "drift"
    assert a[0]["details"]["would"] == "create-repo"
    assert a[0]["details"]["visibility"] == "private"
    assert a[0]["details"]["default_branch"] == "main"


@case
def create_status_new_but_repo_exists_is_skip_never_create():
    for mode in ("report", "enforce"):
        r = reg([{"name": "payments-api", "status": "new", "mode": mode}])
        a = plan("create", r, st(**{"payments-api": live()}))
        assert [(x["action"]) for x in a] == ["skip"], a
        assert "exists" in a[0]["details"]["reason"]


@case
def create_missing_repo_without_status_new_is_never_created():
    for status in ({}, {"status": "existing"}):
        r = reg([dict({"name": "ghost-repo", "mode": "enforce"}, **status)])
        a = plan("create", r, st(**{"ghost-repo": {"exists": False}}))
        assert "create-repo" not in verbs(a), a
        assert all(x["details"].get("would") != "create-repo" for x in a), a


@case
def create_rename_via_rename_from_enforce():
    r = reg([{"name": "billing-web", "rename_from": "legacy-billing", "mode": "enforce"}])
    a = plan("create", r, st(**{"legacy-billing": live(), "billing-web": {"exists": False}}))
    assert a == [{"feature": "create", "repo": "billing-web", "action": "rename-repo",
                  "details": {"from": "legacy-billing", "to": "billing-web"}}]


@case
def create_rename_report_mode_is_drift_would_rename():
    r = reg([{"name": "billing-web", "rename_from": "legacy-billing"}])
    a = plan("create", r, st(**{"legacy-billing": live()}))
    assert len(a) == 1 and a[0]["action"] == "drift"
    assert a[0]["details"] == {"would": "rename-repo", "from": "legacy-billing", "to": "billing-web"}


@case
def create_rename_target_exists_and_old_gone_is_skip():
    r = reg([{"name": "billing-web", "rename_from": "legacy-billing", "mode": "enforce"}])
    a = plan("create", r, st(**{"billing-web": live(), "legacy-billing": {"exists": False}}))
    assert verbs(a) == ["skip"] and "rename" in a[0]["details"]["reason"], a


@case
def create_rename_refused_when_both_old_and_new_exist():
    r = reg([{"name": "billing-web", "rename_from": "legacy-billing", "mode": "enforce"}])
    refused("create", r, st(**{"billing-web": live(), "legacy-billing": live()}),
            who="billing-web")


@case
def create_never_renames_without_rename_from():
    # a live repo with a plausible old name exists, but the register does not name it
    r = reg([{"name": "billing-web", "status": "new", "mode": "enforce"}])
    a = plan("create", r, st(**{"legacy-billing": live(), "billing-web": {"exists": False}}))
    assert verbs(a) == ["create-repo"], a


@case
def create_ignores_repos_absent_from_register_and_never_deletes():
    r = reg([{"name": "payments-api"}])
    a = plan("create", r, st(**{"payments-api": live(), "stray-repo": live()}))
    assert all(x["repo"] == "payments-api" for x in a)
    assert not any(v.startswith(("delete", "archive")) for v in verbs(a))


@case
def create_public_visibility_refused():
    refused("create", reg([{"name": "ledger-worker", "status": "new", "visibility": "public"}]),
            st())


# ---------------------------------------------------------------- F3 settings

@case
def settings_enforce_emits_exact_update_repo_diffs():
    r = reg([{"name": "payments-api", "mode": "enforce", "description": "Payments HTTP API v2",
              "visibility": "internal", "default_branch": "trunk",
              "settings": {"delete_branch_on_merge": True, "allow_auto_merge": False}}])
    s = st(**{"payments-api": live(description="Payments HTTP API", visibility="private",
                                   default_branch="main",
                                   settings={"delete_branch_on_merge": False,
                                             "allow_auto_merge": False})})
    a = plan("settings", r, s)
    assert sorted(verbs(a)) == ["drift", "update-repo", "update-repo", "update-repo"], a
    assert by_field(a) == {
        "description": {"field": "description", "from": "Payments HTTP API",
                        "to": "Payments HTTP API v2"},
        "default_branch": {"field": "default_branch", "from": "main", "to": "trunk"},
        "delete_branch_on_merge": {"field": "delete_branch_on_merge", "from": False, "to": True},
    }
    assert [x["details"] for x in a if x["action"] == "drift"] == [
        {"would": "update-repo", "field": "visibility", "from": "private", "to": "internal"}], a


@case
def settings_report_emits_only_drift_would_update_repo():
    r = reg([{"name": "payments-api", "settings": {"delete_branch_on_merge": True}}])
    s = st(**{"payments-api": live(default_branch="main", visibility="private",
                                   settings={"delete_branch_on_merge": False})})
    a = plan("settings", r, s)
    assert a == [{"feature": "settings", "repo": "payments-api", "action": "drift",
                  "details": {"would": "update-repo", "field": "delete_branch_on_merge",
                              "from": False, "to": True}}]


@case
def settings_in_sync_yields_one_in_sync_per_repo():
    for mode in ("report", "enforce"):
        r = reg([{"name": "payments-api", "mode": mode, "description": "d",
                  "settings": {"has_wiki": False}}])
        s = st(**{"payments-api": live(description="d", visibility="private",
                                       default_branch="main", settings={"has_wiki": False})})
        a = plan("settings", r, s)
        assert [(x["repo"], x["action"], x["details"]) for x in a] == \
            [("payments-api", "in-sync", {})], a


@case
def settings_defaults_apply_and_repo_key_wins():
    r = reg([{"name": "a-repo", "mode": "enforce", "default_branch": "trunk"},
             {"name": "b-repo", "mode": "enforce"}],
            defaults={"default_branch": "main", "visibility": "internal"})
    s = st(**{"a-repo": live(visibility="internal", default_branch="main"),
              "b-repo": live(visibility="internal", default_branch="develop")})
    a = plan("settings", r, s)
    assert by_field(for_repo(a, "a-repo")) == {
        "default_branch": {"field": "default_branch", "from": "main", "to": "trunk"}}
    assert by_field(for_repo(a, "b-repo")) == {
        "default_branch": {"field": "default_branch", "from": "develop", "to": "main"}}


@case
def settings_mode_is_per_repo_and_defaults_to_report():
    r = reg([{"name": "a-repo", "mode": "enforce", "default_branch": "trunk"},
             {"name": "b-repo", "default_branch": "trunk"}])
    del r["defaults"]["mode"]  # nothing says enforce: must behave as report
    s = st(**{"a-repo": live(visibility="private", default_branch="main"),
              "b-repo": live(visibility="private", default_branch="main")})
    a = plan("settings", r, s)
    assert verbs(a, "a-repo") == ["update-repo"]
    assert verbs(a, "b-repo") == ["drift"]


@case
def r20_visibility_difference_is_drift_in_every_mode_and_never_a_write():
    for mode in ("enforce", "report"):
        for frm, to in (("private", "internal"), ("internal", "private"), ("public", "private"),
                        ("public", "internal")):
            r = reg([{"name": "payments-api", "mode": mode, "visibility": to}])
            a = plan("settings", r, st(**{"payments-api": live(visibility=frm, default_branch="main")}))
            assert a == [{"feature": "settings", "repo": "payments-api", "action": "drift",
                          "details": {"would": "update-repo", "field": "visibility", "from": frm,
                                      "to": to}}], (mode, frm, to, a)
    # defaults.visibility behaves the same, and a matching visibility stays in-sync
    r = reg([{"name": "payments-api", "mode": "enforce"}], defaults={"visibility": "private"})
    a = plan("settings", r, st(**{"payments-api": live(visibility="public", default_branch="main")}))
    assert verbs(a) == ["drift"] and a[0]["details"]["field"] == "visibility", a
    a = plan("settings", r, st(**{"payments-api": live(visibility="private", default_branch="main")}))
    assert verbs(a) == ["in-sync"], a


@case
def settings_public_visibility_refused_in_every_position():
    s = st(**{"payments-api": live(visibility="private", default_branch="main")})
    refused("settings", reg([{"name": "payments-api", "mode": "enforce",
                              "visibility": "public"}]), s, who="payments-api")
    refused("settings", reg([{"name": "payments-api"}], defaults={"visibility": "public"}), s)
    refused("settings", FIX / "invalid-public-visibility.yaml", s)


@case
def settings_a_live_public_repo_never_yields_to_public():
    r = reg([{"name": "payments-api", "mode": "enforce", "visibility": "private"}])
    a = plan("settings", r, st(**{"payments-api": live(visibility="public",
                                                       default_branch="main")}))
    assert all(x["details"].get("to") != "public" for x in a)


@case
def settings_unknown_setting_keys_are_ignored():
    r = reg([{"name": "payments-api", "mode": "enforce", "settings": {"brand_new_flag": True}}])
    a = plan("settings", r, st(**{"payments-api": live(visibility="private",
                                                       default_branch="main", settings={})}))
    assert verbs(a) == ["in-sync"], a


@case
def settings_repo_absent_from_register_gets_no_action():
    r = reg([{"name": "payments-api", "mode": "enforce"}])
    a = plan("settings", r, st(**{
        "payments-api": live(visibility="private", default_branch="main"),
        "stray-repo": live(description="x", visibility="internal", default_branch="trunk")}))
    assert {x["repo"] for x in a} == {"payments-api"}


@case
def settings_empty_register_yields_no_actions_even_with_live_repos():
    assert plan("settings", reg([]), st(**{"stray-repo": live()})) == []


@case
def settings_output_follows_register_order_and_is_deterministic():
    r = reg([{"name": n, "mode": "enforce", "default_branch": "trunk"}
             for n in ("zeta-repo", "alpha-repo", "mid-repo")])
    s = st(**{n: live(visibility="private", default_branch="main")
              for n in ("zeta-repo", "alpha-repo", "mid-repo")})
    a = plan("settings", r, s)
    assert [x["repo"] for x in a] == ["zeta-repo", "alpha-repo", "mid-repo"]
    assert plan("settings", r, s) == a


# ---------------------------------------------------------------- F4 variables

@case
def variables_enforce_sets_changed_and_missing_variables():
    r = reg([{"name": "payments-api", "mode": "enforce",
              "variables": {"REGION": "europe-west1", "NEW_ONE": "v"}}])
    a = plan("variables", r, st(**{"payments-api": live(variables={"REGION": "us-east1"})}))
    got = {x["details"]["name"]: x for x in a}
    assert set(verbs(a)) == {"set-variable"} and len(a) == 2, a
    assert got["REGION"]["details"] == {"name": "REGION", "from": "us-east1", "to": "europe-west1"}
    assert got["NEW_ONE"]["details"] == {"name": "NEW_ONE", "from": None, "to": "v"}


@case
def variables_report_emits_drift_would_set_variable():
    r = reg([{"name": "payments-api", "variables": {"REGION": "europe-west1"}}])
    a = plan("variables", r, st(**{"payments-api": live(variables={"REGION": "us-east1"})}))
    assert a == [{"feature": "variables", "repo": "payments-api", "action": "drift",
                  "details": {"would": "set-variable", "name": "REGION",
                              "from": "us-east1", "to": "europe-west1"}}]


@case
def variables_matching_values_are_in_sync():
    for mode in ("report", "enforce"):
        r = reg([{"name": "payments-api", "mode": mode, "variables": {"REGION": "x"}}])
        a = plan("variables", r, st(**{"payments-api": live(variables={"REGION": "x"})}))
        assert [(x["action"], x["details"]) for x in a] == [("in-sync", {})], a


@case
def variables_live_but_unlisted_variables_produce_no_action():
    for mode in ("report", "enforce"):
        r = reg([{"name": "payments-api", "mode": mode, "variables": {"REGION": "x"}}])
        a = plan("variables", r, st(**{"payments-api": live(
            variables={"REGION": "x", "UNLISTED_VAR": "keep", "OTHER": "y"})}))
        blob = json.dumps(a)
        assert "UNLISTED_VAR" not in blob and "OTHER" not in blob, a
        assert verbs(a) == ["in-sync"]


@case
def variables_never_delete_even_when_register_lists_none():
    r = reg([{"name": "payments-api", "mode": "enforce", "variables": {}}])
    a = plan("variables", r, st(**{"payments-api": live(variables={"OLD_VAR": "1"})}))
    assert not any("delete" in v for v in verbs(a)) and "OLD_VAR" not in json.dumps(a)


@case
def variables_repo_without_variables_key_is_not_examined_for_changes():
    r = reg([{"name": "payments-api", "mode": "enforce"}])
    a = plan("variables", r, st(**{"payments-api": live(variables={"A": "1"})}))
    assert "set-variable" not in verbs(a)


@case
def variables_repo_absent_from_register_gets_no_action():
    r = reg([{"name": "payments-api", "mode": "enforce", "variables": {"A": "1"}}])
    a = plan("variables", r, st(**{"payments-api": live(variables={"A": "1"}),
                                   "stray-repo": live(variables={"B": "2"})}))
    assert {x["repo"] for x in a} == {"payments-api"}


@case
def variables_invalid_names_or_values_refused():
    for bad in ({"lower": "x"}, {"GITHUB_TOKEN": "x"}, {"A": 5}):
        refused("variables", reg([{"name": "payments-api", "mode": "enforce", "variables": bad}]),
                st(**{"payments-api": live()}))


# ---------------------------------------------------------------- cross-cutting

@case
def report_mode_never_emits_a_write_verb_across_all_features():
    r = reg([
        {"name": "payments-api", "description": "new", "default_branch": "trunk",
         "variables": {"REGION": "z"}, "settings": {"has_wiki": True}},
        {"name": "ledger-worker", "status": "new"},
        {"name": "billing-web", "rename_from": "legacy-billing"}])
    s = st(**{"payments-api": live(description="old", visibility="private",
                                   default_branch="main", settings={"has_wiki": False},
                                   variables={"REGION": "a"}),
              "ledger-worker": {"exists": False}, "legacy-billing": live()})
    seen = 0
    for f in FEATURES:
        a = plan(f, r, s)  # invariants assert report => non-write
        seen += len(a)
        assert not (set(verbs(a)) & WRITE), (f, a)
    assert seen > 0


@case
def feature_selection_each_feature_reads_only_its_own_keys():
    # only `settings` is broken -> variables/create succeed; only `variables` broken -> settings ok
    s = st(**{"payments-api": live(visibility="private", default_branch="main")})
    broken_settings = reg([{"name": "payments-api", "settings": {"has_wiki": "yes"},
                            "variables": {"A": "1"}}])
    refused("settings", broken_settings, s)
    plan("variables", broken_settings, s)
    plan("create", broken_settings, s)
    broken_vars = reg([{"name": "payments-api", "settings": {"has_wiki": True},
                        "variables": {"bad": "1"}}])
    refused("variables", broken_vars, s)
    plan("settings", broken_vars, s)
    plan("create", broken_vars, s)


@case
def feature_selection_actions_never_leak_into_another_feature():
    s = FIX / "state-basic.json"
    r = FIX / "valid-register.yaml"
    for f in FEATURES:
        for x in plan(f, r, None if f == "register" else s):
            assert x["feature"] == f, x


@case
def feature_selection_unknown_feature_is_rejected_with_no_stdout():
    rc, out, _ = run("wif-link", reg([]), st())
    assert rc != 0 and out == "", (rc, out)
    rc, out, _ = run("delete-everything", reg([]), st())
    assert rc != 0 and out == "", (rc, out)


@case
def r21_a_deployable_belongs_to_exactly_one_repo():
    # M2: two repos naming the same cloud_run is refused (validate_core) by F1-F4 here; F5, F6 and F7
    # call the same validate_core and pin it in their own suites
    a = {"name": "api", "deploys": [{"cloud_run": "payments-api", "region": "europe-west1"}]}
    b = {"name": "web", "deploys": [{"cloud_run": "payments-api", "region": "europe-west1"}]}
    for feature in ("register", "create", "settings"):
        err = refused(feature, reg([a, b]), st())
        assert "payments-api" in err and "api" in err and "web" in err, (feature, err)
    # controls: distinct deployables, and gke entries (no cloud_run name), are accepted
    c = {"name": "web", "deploys": [{"cloud_run": "web", "region": "europe-west1"}]}
    rc, out, err = run("register", reg([a, c]))
    assert rc == 0, err
    g1 = {"name": "g1", "deploys": [{"gke": {"cluster": "l/main", "namespace": "ns", "workload": "w"}}]}
    g2 = {"name": "g2", "deploys": [{"gke": {"cluster": "l/main", "namespace": "ns", "workload": "w"}}]}
    rc, out, err = run("register", reg([g1, g2]))
    assert rc == 0, err


@case
def r21_runtime_service_account_is_optional_in_the_schema():
    d = {"cloud_run": "payments-api", "region": "europe-west1"}
    rc, out, err = run("register", reg([{"name": "payments-api", "deploys": [d]}]))
    assert rc == 0, err
    # still pattern-checked when present (M3), and region stays required
    refused("register", reg([{"name": "payments-api", "deploys": [dict(d, runtime_service_account="--x-run")]}]))
    refused("register", reg([{"name": "payments-api", "deploys": [{"cloud_run": "payments-api"}]}]))


@case
def feature_selection_f5_to_f7_keys_are_ignored_by_f1_to_f4():
    r = reg([{"name": "payments-api", "mode": "enforce",
              "gcp": {"service_accounts": ["payments-api-deployer"]},
              "deploys": [{"cloud_run": "payments-api", "region": "europe-west1",
                           "runtime_service_account": "payments-api-run"}]}],
            service_accounts=[{"name": "payments-api-deployer", "description": "d"}])
    s = st(**{"payments-api": live(visibility="private", default_branch="main")})
    for f in ("create", "settings", "variables"):
        assert verbs(plan(f, r, s)) == ["in-sync"], f


@case
def unknown_keys_do_not_change_the_plan():
    base = [{"name": "payments-api", "mode": "enforce", "default_branch": "trunk"}]
    noisy = [{"name": "payments-api", "mode": "enforce", "default_branch": "trunk",
              "kind": "go-service", "future": {"x": [1, 2]}, "labels": ["a"]}]
    s = st(**{"payments-api": live(visibility="private", default_branch="main")})
    for f in ("create", "settings", "variables"):
        assert plan(f, reg(noisy, future_top=1), s) == plan(f, reg(base), s), f


@case
def repo_removed_from_register_is_unmanaged_no_delete_archive_or_reset():
    s = st(**{"payments-api": live(visibility="private", default_branch="main"),
              "removed-repo": live(description="still there", visibility="internal",
                                   default_branch="trunk", variables={"A": "1"})})
    r = reg([{"name": "payments-api", "mode": "enforce"}])
    for f in FEATURES:
        a = plan(f, r, None if f == "register" else s)
        assert "removed-repo" not in json.dumps(a), (f, a)


@case
def error_runs_print_nothing_even_when_other_repos_are_fine():
    # one bad repo among good ones: no partial plan
    r = reg([{"name": "good-repo", "mode": "enforce", "default_branch": "trunk"},
             {"name": "bad-repo", "visibility": "public"}])
    s = st(**{"good-repo": live(visibility="private", default_branch="main"),
              "bad-repo": live(visibility="private", default_branch="main")})
    refused("settings", r, s, who="bad-repo")


@case
def planner_script_exists_and_is_python():
    assert PLANNER.is_file(), f"{PLANNER} does not exist yet"


# ---------------------------------------------------------------- runner

def main():
    shutil.rmtree(WORK, ignore_errors=True)
    failed = []
    try:
        for fn in CASES:
            try:
                fn()
            except AssertionError as e:
                failed.append((fn.__name__, str(e)[:300]))
            except Exception as e:  # missing planner, bad JSON, timeouts
                failed.append((fn.__name__, f"{type(e).__name__}: {str(e)[:300]}"))
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    for name, why in failed:
        print(f"FAIL {name}: {why}")
    print(f"examined {len(CASES)} cases against {PLANNER}: "
          f"{len(CASES) - len(failed)} passed, {len(failed)} failed")
    if not CASES:
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
