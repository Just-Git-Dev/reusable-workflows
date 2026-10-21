#!/usr/bin/env python3
"""F9 planner: the GitHub environments a service repo needs, with their deployment branch/tag rule
(docs/repos-environments.md, docs/repos-register.md §3, §7.1, §8). Pure: no network, no clock.

    python3 scripts/repos_env_plan.py --feature environments --register repos.yaml --state state.json

Prints the §8 action list to stdout (exit 0), or nothing to stdout and one `error: <repo>: <reason>`
line per error to stderr (exit 1). The NEVER list is enforced by vocabulary: the write verbs are
`create-environment`, `add-branch-policy` and `remove-branch-policy`; there is no verb that deletes
an environment or writes a secret, variable, reviewer or wait timer. An environment the register
does not list gets `unmanaged-environment` and nothing else, in both modes.

State: {"repos": {"<repo>": {"exists": bool, "environments": {"<env>":
        {"custom_branch_policies": bool, "policies": [{"name": str, "type": "branch"|"tag"}]}}}}}
A policy is the pair (name, type). With custom policies off, live policies carry no meaning, so all
listed patterns are planned as additions (the apply step switches the policies on first).
"""

import argparse
import json
import re
import sys

import repos_plan

FEATURE = "environments"
MODES = ("report", "enforce")
ENV_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")   # fullmatch: `$` accepts a trailing newline


def act(repo, verb, details):
    return {"feature": FEATURE, "repo": repo, "action": verb, "details": details}


def patterns(env, key):
    return env.get(key) if isinstance(env.get(key), list) else []


def validate_repo(repo, errors):
    """Return [(env_name, [(pattern, type), ...])] for a repo with `environments:`, or None."""
    who = repo["name"]
    envs = repo.get("environments")
    if envs is None:
        return None
    if not isinstance(envs, list):
        errors.append(repos_plan.err(who, "environments must be a list"))
        return None
    out, seen, ok = [], set(), True
    for i, e in enumerate(envs):
        if not isinstance(e, dict):
            errors.append(repos_plan.err(who, "environments[%d] must be a mapping" % i))
            ok = False
            continue
        name = e.get("name")
        if not isinstance(name, str) or not ENV_RE.fullmatch(name):
            errors.append(repos_plan.err(who, "environments[%d].name is required and must match "
                                              "^[A-Za-z0-9][A-Za-z0-9._-]*$ (max 100)" % i))
            ok = False
            continue
        if name in seen:
            errors.append(repos_plan.err(who, "environment %s is listed twice" % name))
            ok = False
        seen.add(name)
        pats = []
        for key, typ in (("branches", "branch"), ("tags", "tag")):
            vals = e.get(key)
            if vals is None:
                continue
            if not isinstance(vals, list) or any(
                    not isinstance(v, str) or not v.strip() or not v.isprintable() for v in vals):
                errors.append(repos_plan.err(who, "environment %s: %s must be a list of non-empty "
                                                  "printable patterns" % (name, key)))
                ok = False
                continue
            pats.extend((v, typ) for v in vals)
        if ok and not pats:
            errors.append(repos_plan.err(who, "environment %s needs at least one of branches or tags"
                                         % name))
            ok = False
        out.append((name, list(dict.fromkeys(pats))))
    return out if ok else None


def plan_repo(repo, mode, wanted, live):
    name = repo["name"]
    out = []

    def write(verb, details):
        out.append(act(name, verb, details) if mode == "enforce"
                   else act(name, "drift", dict(would=verb, **details)))

    envs = live.get("environments") or {}
    for env, pats in wanted:
        cur = envs.get(env)
        if cur is None:
            write("create-environment", {"environment": env})
            have = set()
        else:
            on = cur.get("custom_branch_policies") is True
            have = {(p.get("name"), p.get("type")) for p in cur.get("policies") or []} if on else set()
        extra = [h for h in sorted(have, key=lambda h: (str(h[0]), str(h[1]))) if h not in pats]
        add = [p for p in pats if p not in have]
        for pname, typ in extra:
            write("remove-branch-policy", {"environment": env, "name": pname, "type": typ})
        for pname, typ in add:
            write("add-branch-policy", {"environment": env, "name": pname, "type": typ})
        if cur is not None and not (extra or add):
            out.append(act(name, "in-sync", {}))
    listed = {env for env, _ in wanted}
    for env in sorted(set(envs) - listed):
        out.append(act(name, "unmanaged-environment", {"environment": env}))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature", required=True)
    ap.add_argument("--register", required=True)
    ap.add_argument("--state", required=True)
    args = ap.parse_args(argv)
    if args.feature != FEATURE:
        print("error: register: unknown feature %r" % args.feature, file=sys.stderr)
        return 2
    try:
        reg = repos_plan.load_register(args.register)
        repos_plan.validate_core(reg)
        with open(args.state) as f:
            state = json.load(f)
    except repos_plan.PlanError as e:
        print("\n".join(e.errors), file=sys.stderr)
        return 1
    default_mode = (reg.get("defaults") or {}).get("mode") or "report"
    errors, todo = [], []
    if default_mode not in MODES:
        errors.append(repos_plan.err("register", "defaults.mode must be report or enforce"))
    live_repos = state.get("repos") or {}
    for repo in reg["repos"]:
        wanted = validate_repo(repo, errors)
        if wanted is None:
            continue
        mode = repo.get("mode", default_mode)
        if mode not in MODES:
            errors.append(repos_plan.err(repo["name"], "mode must be report or enforce"))
            continue
        live = live_repos.get(repo["name"])
        if not isinstance(live, dict) or live.get("exists") is not True:
            errors.append(repos_plan.err(repo["name"], "repo does not exist (F9 never creates a "
                                                       "repo: run repos-create first)"))
            continue
        todo.append((repo, mode, wanted, live))
    if errors:
        for line in dict.fromkeys(errors):
            print(line, file=sys.stderr)
        return 1
    out = []
    for repo, mode, wanted, live in todo:
        out.extend(plan_repo(repo, mode, wanted, live))
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
