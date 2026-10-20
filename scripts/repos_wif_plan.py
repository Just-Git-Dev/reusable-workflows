#!/usr/bin/env python3
"""F5 planner: link repos to deploy identities (repo-level WIF). Pure: no network, no clock.

    python3 scripts/repos_wif_plan.py --feature wif-link --register repos.yaml --state state.json

Prints the docs/repos-register.md §8 action list to stdout (exit 0), or nothing to stdout and one
`error: <repo|sa|register>: <reason>` line per error to stderr (exit 1). The NEVER list is enforced
here by vocabulary: the only write verb this planner can emit is `add-wif-binding`, always with
`roles/iam.workloadIdentityUser`; there is no verb for removal, a key, or a project-level grant.
"""

import argparse
import json
import re
import sys

import yaml

import repos_plan
import repos_protected

ROLE = "roles/iam.workloadIdentityUser"
FEATURE = "wif-link"
SA_RE = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")   # fullmatch: `$` accepts a trailing newline
NAME_RE = re.compile(r"^(?!-)(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$")   # never `-`-led, never . or ..
ORG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def act(repo, action, details):
    return {"feature": FEATURE, "repo": repo, "action": action, "details": details}


def validate(reg, errors):
    """Validate only the keys F5 reads. Returns the usable repo list."""
    if not isinstance(reg, dict):
        errors.append(("register", "register is not a mapping"))
        return []
    if reg.get("version") != 1 or isinstance(reg.get("version"), bool):
        errors.append(("register", "version must be 1"))
    if not isinstance(reg.get("org"), str) or not ORG_RE.match(reg["org"]):
        errors.append(("register", "org must be a GitHub login"))
    repos = reg.get("repos")
    if not isinstance(repos, list):
        errors.append(("register", "repos must be a list"))
        return []
    defaults = reg.get("defaults") if isinstance(reg.get("defaults"), dict) else {}
    out, seen = [], set()
    for r in repos:
        name = r.get("name") if isinstance(r, dict) else None
        if not isinstance(name, str) or not NAME_RE.match(name):
            errors.append(("register", "repo entry without a valid name"))
            continue
        if name in seen:
            errors.append((name, "duplicate repo name"))
        seen.add(name)
        mode = r.get("mode", defaults.get("mode", "report"))
        if mode not in ("report", "enforce"):
            errors.append((name, "mode must be report or enforce"))
        sas = (r.get("gcp") or {}).get("service_accounts") if isinstance(r.get("gcp"), dict) else None
        if sas is None:
            continue
        if not isinstance(sas, list) or not all(isinstance(s, str) and SA_RE.fullmatch(s) for s in sas):
            errors.append((name, "gcp.service_accounts must be a list of valid service account names"))
            continue
        deployables = {d.get("cloud_run") for d in (r.get("deploys") or []) if isinstance(d, dict)
                       and isinstance(d.get("cloud_run"), str)}
        for s in dict.fromkeys(sas):
            if not repos_protected.is_project_sa(s):
                errors.append((name, "%s is not a project SA: ask JGD (wif_repos). F5 links only "
                                     "`<deployable>-deployer` accounts (docs/repos-register.md section 5, "
                                     "item 9)" % s))
            elif s[:-len("-deployer")] not in deployables:
                errors.append((name, "%s is not a deployer of a deployable of %s: F5 links only "
                                     "`<d>-deployer` for a `cloud_run: <d>` in this repo's own deploys"
                                     % (s, name)))
        out.append((name, mode, list(dict.fromkeys(sas))))
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

    with open(args.register) as f:
        reg = yaml.safe_load(f)
    with open(args.state) as f:
        state = json.load(f)

    # the shared register shape, incl. "a deployable belongs to exactly one repo": F5 links a repo to
    # `<d>-deployer`, so two repos naming `d` would let one of them link the other's identity
    try:
        repos_plan.validate_core(reg)
    except repos_plan.PlanError as e:
        print("\n".join(e.errors), file=sys.stderr)
        return 1
    errors = []
    repos = validate(reg, errors)
    number, pool = state.get("project_number"), state.get("pool")
    if not number or not pool:
        errors.append(("register", "state needs project_number and pool"))
    live = state.get("service_accounts") or {}
    for name, _mode, sas in repos:
        for s in sas:
            if not (live.get(s) or {}).get("exists"):
                errors.append((s, "service account does not exist (F5 never creates one; use F6)"))
    if errors:
        for who, why in dict.fromkeys(errors):
            print("error: %s: %s" % (who, why), file=sys.stderr)
        return 1

    org = reg["org"]

    def member(repo):
        return ("principalSet://iam.googleapis.com/projects/%s/locations/global/"
                "workloadIdentityPools/%s/attribute.repository/%s/%s" % (number, pool, org, repo))

    # every register-listed link per SA: these are the "listed" bindings
    listed = {}
    for name, _mode, sas in repos:
        for s in sas:
            listed.setdefault(s, set()).add(member(name))

    out, reported = [], set()
    for name, mode, sas in repos:
        mine = []
        for s in sas:
            bindings = (live[s].get("policy") or {}).get("bindings") or []
            have = {m for b in bindings if b.get("role") == ROLE for m in b.get("members") or []}
            if member(name) not in have:
                d = {"service_account": s, "role": ROLE, "member": member(name)}
                if mode == "enforce":
                    mine.append(act(name, "add-wif-binding", d))
                else:
                    mine.append(act(name, "drift", dict(would="add-wif-binding", **d)))
            if s in reported:
                continue
            reported.add(s)
            for b in bindings:
                for m in b.get("members") or []:
                    if b.get("role") == ROLE and m in listed[s]:
                        continue
                    mine.append(act(name, "unregistered-binding",
                                    {"service_account": s, "role": b.get("role"), "member": m}))
        out.extend(mine or [act(name, "in-sync", {})])
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
