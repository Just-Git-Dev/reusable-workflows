#!/usr/bin/env python3
"""F8 planner: one Secret Manager secret per service, with one writer for its policy (owner ruling 24;
docs/repos-secrets.md, docs/repos-register.md §6, §7, §8).

Pure: reads a register (YAML) and a live-state JSON, prints the action list. No network, no
subprocess. The write vocabulary is `create-secret`, `add-secret-binding` and
`remove-secret-binding`: there is no verb to delete a secret or to add, read, disable or destroy a
version, so the NEVER list cannot be violated from here.

For every `cloud_run: <d>` deploys entry with `env_secret: true` the secret is `<d>-env` (derived,
never chosen) and its whole policy is exactly:
    <d>-run       -> roles/secretmanager.secretAccessor
    <d>-deployer  -> secretAccessor, secretVersionManager, viewer   (the sync role set)

Usage: repos_secrets_plan.py --feature secrets --register repos.yaml --state state.json [--prune]
"""

import argparse
import json
import sys

import yaml

import repos_plan

FEATURE = "secrets"
ACCESSOR = "roles/secretmanager.secretAccessor"
VERSION_MANAGER = "roles/secretmanager.secretVersionManager"
VIEWER = "roles/secretmanager.viewer"
RUN_ROLES = (ACCESSOR,)
DEPLOYER_ROLES = (ACCESSOR, VERSION_MANAGER, VIEWER)
MIN_SA_LEN = 6
MAX_SA_LEN = 30


def act(repo, action, details):
    return {"feature": FEATURE, "repo": repo, "action": action, "details": details}


def live_lines(secret_state):
    """The (role, member) pairs of a live policy, in policy order, without duplicates."""
    seen, out = set(), []
    for e in (secret_state or {}).get("iam") or []:
        for mem in e.get("members") or []:
            if (e.get("role"), mem) not in seen:
                seen.add((e.get("role"), mem))
                out.append((e.get("role"), mem))
    return out


def deployables(repo):
    """The Cloud Run deployables of `repo` that opted in to a secret."""
    return [d["cloud_run"] for d in repo.get("deploys") or []
            if "cloud_run" in d and d.get("env_secret") is True]


def check_repo(repo, state, errors):
    """Accumulate errors; a missing deployer or a name that cannot be an SA id refuses the run."""
    name = repo["name"]
    accounts = state.get("service_accounts") or {}
    for d in deployables(repo):
        deployer, runtime = "%s-deployer" % d, "%s-run" % d
        bad_id = next(((k, i) for k, i in (("deployer", deployer), ("runtime", runtime))
                       if not MIN_SA_LEN <= len(i) <= MAX_SA_LEN), None)
        if bad_id:
            errors.append("error: %s: %s SA name '%s' is %d chars, must be %d-%d"
                          % (name, bad_id[0], bad_id[1], len(bad_id[1]), MIN_SA_LEN, MAX_SA_LEN))
        elif deployer not in accounts:
            errors.append("error: %s: service account %s does not exist: run F6 "
                          "(repos-service-accounts) first" % (name, deployer))


def plan_repo(repo, mode, state, prune):
    name = repo["name"]
    project = state.get("project_id")
    secrets = state.get("secrets") or {}
    accounts = state.get("service_accounts") or {}
    out = []

    def write(verb, details):
        out.append(act(name, verb, details) if mode == "enforce"
                   else act(name, "drift", dict(would=verb, **details)))

    for d in deployables(repo):
        secret, runtime, deployer = "%s-env" % d, "%s-run" % d, "%s-deployer" % d
        if runtime not in accounts:
            out.append(act(name, "needs-jgd", {
                "resource_type": "iam.serviceAccount",
                "resource": "%s@%s.iam.gserviceaccount.com" % (runtime, project),
                "needs": "service account %s" % runtime}))
            continue

        def sa(n):
            return "serviceAccount:%s@%s.iam.gserviceaccount.com" % (n, project)

        want = [(r, sa(runtime)) for r in RUN_ROLES] + [(r, sa(deployer)) for r in DEPLOYER_ROLES]
        exists = secret in secrets
        have = live_lines((secrets.get(secret)))
        add = [w for w in want if w not in have]
        extra = [h for h in have if h not in want]
        if not exists:
            write("create-secret", {"secret": secret,
                                    "labels": {"managed-by": "repos-secrets", "deployable": d}})
        elif add:
            out.append(act(name, "adopt", {"secret": secret}))
        for role, mem in add:
            write("add-secret-binding", {"secret": secret, "role": role, "member": mem})
        for role, mem in extra:
            det = {"secret": secret, "role": role, "member": mem}
            if mode == "enforce" and prune:
                out.append(act(name, "remove-secret-binding", det))
            else:
                out.append(act(name, "drift", dict(would="remove-secret-binding", **det)))
        if exists and not (add or extra):
            out.append(act(name, "in-sync", {}))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature", required=True)
    ap.add_argument("--register", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--prune", action="store_true")
    args = ap.parse_args(argv)
    if args.feature != FEATURE:
        print("error: register: unknown feature %r" % args.feature, file=sys.stderr)
        return 2
    with open(args.register) as f:
        reg = yaml.safe_load(f)
    # F1-style validation first: a name or `env_secret` of the wrong shape never reaches a command
    # line, so nothing is planned for a bad register.
    try:
        repos_plan.validate_core(reg)
        repos_plan.validate_register_feature(reg)
    except repos_plan.PlanError as e:
        print("\n".join(e.errors), file=sys.stderr)
        return 1
    with open(args.state) as f:
        state = json.load(f)
    default_mode = ((reg.get("defaults") or {}).get("mode")) or "report"
    errors, actions = [], []
    for repo in reg.get("repos") or []:
        check_repo(repo, state, errors)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    for repo in reg.get("repos") or []:
        actions.extend(plan_repo(repo, repo.get("mode") or default_mode, state, args.prune))
    print(json.dumps(actions, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
