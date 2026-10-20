#!/usr/bin/env python3
"""Pure planner for the repos-as-code features F1-F4 (docs/repos-register.md, sections 7-8).

    python3 scripts/repos_plan.py --feature <register|create|settings|variables>
                                  --register repos.yaml [--state state.json]

Reads the register and the live-state JSON the workflow fetched, prints the action list (a JSON
array of {feature, repo, action, details}) and exits 0. On any error it prints nothing to stdout,
one `error: <repo|register>: <reason>` line per error to stderr, and exits 1: there is no partial
plan. No network, no clock, no environment. The never-do list is enforced by the vocabulary: this
file has no verb for delete, archive, make-public, or anything outside section 8's tables.

Dependencies: PyYAML; `jsonschema` only for `--feature register` (F1).
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "repos.v1.json"
FEATURES = ("register", "create", "settings", "variables")
MODES = ("report", "enforce")
VISIBILITIES = ("private", "internal")
NAME_RE = re.compile(r"^(?!-)(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$")   # never `-`-led, never . or ..
ORG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
SERVICE_RE = re.compile(r"[a-z]([-a-z0-9]{0,61}[a-z0-9])?")
REGION_RE = re.compile(r"[a-z]+-[a-z]+[0-9]")
VAR_RE =re.compile(r"^(?!GITHUB_)[A-Z_][A-Z0-9_]*$")
BOOL_SETTINGS = ("delete_branch_on_merge", "allow_auto_merge", "allow_squash_merge",
                 "allow_merge_commit", "allow_rebase_merge", "has_issues", "has_wiki",
                 "has_projects")
# Keys each feature reads, besides `name`; used only to scope validation (7.2).
FEATURE_KEYS = {
    "create": ("status", "rename_from", "mode", "visibility", "default_branch", "description"),
    "settings": ("mode", "description", "visibility", "default_branch", "settings"),
    "variables": ("mode", "variables"),
}


class PlanError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def load_register(path):
    import yaml
    try:
        data = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as e:
        raise PlanError([err("register", f"cannot read {path}: {e}")])
    return data


def err(who, reason):
    return f"error: {who}: {reason}"


# ------------------------------------------------------------------ validation

def validate_core(reg):
    """Shape every feature needs: version, org, repos, unique well-formed names."""
    errs = []
    if not isinstance(reg, dict):
        raise PlanError([err("register", "top level must be a mapping")])
    if reg.get("version") != 1 or isinstance(reg.get("version"), bool):
        errs.append(err("register", "version must be 1"))
    if not isinstance(reg.get("org"), str) or not ORG_RE.match(reg["org"]):
        errs.append(err("register", "org must be a GitHub login"))
    repos = reg.get("repos")
    if not isinstance(repos, list):
        errs.append(err("register", "repos must be a list"))
        raise PlanError(errs)
    seen = set()
    for i, r in enumerate(repos):
        if not isinstance(r, dict) or not isinstance(r.get("name"), str) \
                or not NAME_RE.match(r["name"]):
            errs.append(err("register", f"repos[{i}] needs a valid name"))
            continue
        if r["name"] in seen:
            errs.append(err(r["name"], "duplicate repo name"))
        seen.add(r["name"])
    # ruling 21: a deployable belongs to exactly one repo (its `<d>-deployer` / `<d>-run` are derived
    # from the name, so two repos naming `d` would share one identity). Malformed deploys are the
    # schema's business; only well-formed cloud_run names are compared here.
    owners = {}
    for r in repos:
        if not isinstance(r, dict) or not isinstance(r.get("name"), str) \
                or not isinstance(r.get("deploys"), list):
            continue
        for dep in r["deploys"]:
            svc = dep.get("cloud_run") if isinstance(dep, dict) else None
            region = dep.get("region") if isinstance(dep, dict) else None
            # `$` (the schema's pattern, jq's too) accepts a trailing "\n", which would then reach a
            # command line. Other malformed values stay the schema's business; here only the value
            # that the schema lets through but fullmatch refuses.
            if isinstance(svc, str) and re.fullmatch(SERVICE_RE.pattern + r"\n", svc):
                errs.append(err(r["name"], "cloud_run must be a Cloud Run service name"))
            if isinstance(region, str) and re.fullmatch(REGION_RE.pattern + r"\n", region):
                errs.append(err(r["name"], "region must look like europe-west1"))
            if isinstance(svc, str) and svc and r["name"] not in owners.setdefault(svc, []):
                owners[svc].append(r["name"])
    for svc, names in sorted(owners.items()):
        if len(names) > 1:
            errs.append(err(names[1], f"cloud_run {svc} is also deployed by {names[0]}: a deployable "
                                      "belongs to exactly one repo"))
    d = reg.get("defaults")
    if d is not None and not isinstance(d, dict):
        errs.append(err("register", "defaults must be a mapping"))
    if errs:
        raise PlanError(errs)
    return errs


def check_keys(who, node, keys, errs):
    """Validate the listed keys of a repo entry or of `defaults`."""
    if "mode" in keys and "mode" in node and node["mode"] not in MODES:
        errs.append(err(who, "mode must be report or enforce"))
    if "visibility" in keys and "visibility" in node and node["visibility"] not in VISIBILITIES:
        errs.append(err(who, f"visibility {node['visibility']!r} is not allowed "
                             "(private or internal; never public)"))
    if "default_branch" in keys and "default_branch" in node:
        db = node["default_branch"]
        if not isinstance(db, str) or not db or db.startswith("-") or any(c.isspace() for c in db):
            errs.append(err(who, "default_branch must be a non-empty string that does not start "
                                 "with '-' and holds no whitespace"))
    if "description" in keys and "description" in node:
        if not isinstance(node["description"], str) or len(node["description"]) > 350:
            errs.append(err(who, "description must be a string of at most 350 chars"))
    if "status" in keys and "status" in node and node["status"] not in ("new", "existing"):
        errs.append(err(who, "status must be new or existing"))
    if "rename_from" in keys and "rename_from" in node:
        rf = node["rename_from"]
        if not isinstance(rf, str) or not NAME_RE.match(rf):
            errs.append(err(who, "rename_from must be a repo name"))
        elif rf == node.get("name"):
            errs.append(err(who, "rename_from must differ from name"))
    if "settings" in keys and "settings" in node:
        s = node["settings"]
        if not isinstance(s, dict):
            errs.append(err(who, "settings must be a mapping"))
        else:
            for k in BOOL_SETTINGS:
                if k in s and not isinstance(s[k], bool):
                    errs.append(err(who, f"settings.{k} must be a boolean"))
    if "variables" in keys and "variables" in node:
        v = node["variables"]
        if not isinstance(v, dict):
            errs.append(err(who, "variables must be a mapping"))
        else:
            for k, val in v.items():
                if not isinstance(k, str) or not VAR_RE.match(k):
                    errs.append(err(who, f"variable name {k!r} is not allowed"))
                if not isinstance(val, str):
                    errs.append(err(who, f"variable {k} must be a string value"))


def validate_feature(feature, reg):
    validate_core(reg)
    keys = FEATURE_KEYS[feature]
    errs = []
    check_keys("register", reg.get("defaults") or {}, keys, errs)
    names = {r["name"] for r in reg["repos"]}
    for r in reg["repos"]:
        check_keys(r["name"], r, keys, errs)
        if "rename_from" in keys and r.get("rename_from") in names - {r["name"]}:
            errs.append(err(r["name"], f"rename_from {r['rename_from']} is another entry"))
    if errs:
        raise PlanError(errs)


def schema_error_who(reg, error):
    path = list(error.absolute_path)
    try:
        if len(path) >= 2 and path[0] == "repos":
            return reg["repos"][path[1]]["name"]
        if len(path) >= 2 and path[0] == "service_accounts":
            return reg["service_accounts"][path[1]]["name"]
    except (KeyError, IndexError, TypeError):
        pass
    return "register"


def validate_register_feature(reg):
    """F1: the whole file against the JSON schema, plus cross-entry rules."""
    import jsonschema
    schema = json.loads(SCHEMA.read_text())
    errs = []
    for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(reg),
                    key=lambda e: [str(p) for p in e.absolute_path]):
        where = ".".join(str(p) for p in e.absolute_path) or "(top level)"
        errs.append(err(schema_error_who(reg, e), f"{where}: {e.message}"))
    if errs:
        raise PlanError(errs)
    names = [r["name"] for r in reg["repos"]]
    for n in sorted({n for n in names if names.count(n) > 1}):
        errs.append(err(n, "duplicate repo name"))
    for r in reg["repos"]:
        rf = r.get("rename_from")
        if rf is not None and (rf == r["name"] or rf in names):
            errs.append(err(r["name"], f"rename_from {rf} must differ from every repo name"))
    sa_names = [s["name"] for s in reg.get("service_accounts") or []]
    for n in sorted({n for n in sa_names if sa_names.count(n) > 1}):
        errs.append(err(n, "duplicate service account name"))
    if errs:
        raise PlanError(errs)


# ------------------------------------------------------------------ planning

def action(feature, repo, verb, details=None):
    return {"feature": feature, "repo": repo, "action": verb, "details": details or {}}


def effective(reg, repo, key):
    if key in repo:
        return repo[key]
    return (reg.get("defaults") or {}).get(key)


def mode_of(reg, repo):
    return effective(reg, repo, "mode") or "report"


def write_or_drift(mode, feature, name, verb, details):
    if mode == "enforce":
        return action(feature, name, verb, details)
    return action(feature, name, "drift", dict({"would": verb}, **details))


def live_repo(state, name):
    r = (state.get("repos") or {}).get(name) or {}
    return r if r.get("exists") else None


def plan_register(reg, _state):
    return [action("register", r["name"], "in-sync") for r in reg["repos"]]


def plan_create(reg, state):
    out = []
    errs = []
    for r in reg["repos"]:
        name, mode = r["name"], mode_of(reg, r)
        old = r.get("rename_from")
        here = live_repo(state, name) is not None
        if old is not None:
            there = live_repo(state, old) is not None
            if there and here:
                errs.append(err(name, f"both {old} and {name} exist; rename refused"))
                continue
            if there:
                out.append(write_or_drift(mode, "create", name, "rename-repo",
                                          {"from": old, "to": name}))
                continue
            if here:
                out.append(action("create", name, "skip", {"reason": "rename already done"}))
                continue
        if r.get("status") == "new":
            if here:
                out.append(action("create", name, "skip", {"reason": "exists"}))
            else:
                out.append(write_or_drift(mode, "create", name, "create-repo", {
                    "visibility": effective(reg, r, "visibility") or "private",
                    "default_branch": effective(reg, r, "default_branch") or "main",
                    "description": r.get("description")}))
        elif here:
            out.append(action("create", name, "in-sync"))
        else:
            out.append(action("create", name, "skip",
                              {"reason": "missing, but status is not new"}))
    if errs:
        raise PlanError(errs)
    return out


def plan_settings(reg, state):
    out = []
    for r in reg["repos"]:
        name, mode = r["name"], mode_of(reg, r)
        live = live_repo(state, name)
        if live is None:
            out.append(action("settings", name, "skip", {"reason": "repo does not exist"}))
            continue
        diffs = []
        for field in ("description", "visibility", "default_branch"):
            want = effective(reg, r, field)
            if want is not None and live.get(field) != want:
                diffs.append((field, live.get(field), want))
        want_s = dict((reg.get("defaults") or {}).get("settings") or {})
        want_s.update(r.get("settings") or {})
        live_s = live.get("settings") or {}
        for k in BOOL_SETTINGS:
            if k in want_s and live_s.get(k) != want_s[k]:
                diffs.append((k, live_s.get(k), want_s[k]))
        if not diffs:
            out.append(action("settings", name, "in-sync"))
        for field, frm, to in diffs:
            if field == "visibility":
                # never written, in either direction and in either mode (a public -> private flip
                # cannot be undone): always a reported difference for a human to act on
                out.append(action("settings", name, "drift", {
                    "would": "update-repo", "field": field, "from": frm, "to": to}))
                continue
            out.append(write_or_drift(mode, "settings", name, "update-repo",
                                      {"field": field, "from": frm, "to": to}))
    return out


def plan_variables(reg, state):
    out = []
    for r in reg["repos"]:
        name, mode = r["name"], mode_of(reg, r)
        live = live_repo(state, name)
        if live is None:
            out.append(action("variables", name, "skip", {"reason": "repo does not exist"}))
            continue
        live_v = live.get("variables") or {}
        diffs = [(k, live_v.get(k), v) for k, v in (r.get("variables") or {}).items()
                 if live_v.get(k) != v]
        if not diffs:
            out.append(action("variables", name, "in-sync"))
        for k, frm, to in diffs:
            out.append(write_or_drift(mode, "variables", name, "set-variable",
                                      {"name": k, "from": frm, "to": to}))
    return out


PLANNERS = {"register": plan_register, "create": plan_create,
            "settings": plan_settings, "variables": plan_variables}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--feature", required=True)
    ap.add_argument("--register", required=True)
    ap.add_argument("--state")
    args = ap.parse_args(argv)
    try:
        if args.feature not in FEATURES:
            raise PlanError([err("register", f"unknown feature {args.feature!r}")])
        reg = load_register(args.register)
        if args.feature == "register":
            validate_core(reg)
            validate_register_feature(reg)
            state = {}
        else:
            validate_feature(args.feature, reg)
            if not args.state:
                raise PlanError([err("register", "--state is required for this feature")])
            try:
                state = json.loads(Path(args.state).read_text())
            except (OSError, ValueError) as e:
                raise PlanError([err("register", f"cannot read state {args.state}: {e}")])
            if not isinstance(state, dict):
                raise PlanError([err("register", "state must be a JSON object")])
        plan = PLANNERS[args.feature](reg, state)
    except PlanError as e:
        for line in e.errors:
            print(line, file=sys.stderr)
        return 1
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
