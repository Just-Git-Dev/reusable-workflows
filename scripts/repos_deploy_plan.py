#!/usr/bin/env python3
"""F7 planner: per-deployable deploy scope (docs/repos-register.md §6, §7, §8).

Pure: reads a register (YAML) and a live-state JSON, prints the action list. No network, no
subprocess. The action vocabulary has no verb to delete, archive, create a key or grant a
project-level role, so the NEVER list cannot be violated from here.

Usage: repos_deploy_plan.py --feature deploy-scope --register repos.yaml --state state.json
"""

import argparse
import json
import sys

import yaml

import repos_protected

FEATURE = "deploy-scope"
RUN_DEV = "roles/run.developer"
SA_USER = "roles/iam.serviceAccountUser"
GAR_WRITER = "roles/artifactregistry.writer"
MAX_SA_LEN = 30


def act(repo, action, details):
    return {"feature": FEATURE, "repo": repo, "action": action, "details": details}


def held(policy_entries, role, member):
    for e in policy_entries or []:
        if e.get("role") == role and member in (e.get("members") or []):
            return True
    return False


def plan_repo(repo, mode, state, errors, protected, admin_email):
    name = repo["name"]
    project = state.get("project_id")
    writes = []  # (verb, details) in apply order
    admin_done = set()          # runtime SAs whose repo-admin binding is already planned for this repo
    for d in repo.get("deploys") or []:
        if "gke" in d:
            # ruling 19: GKE is deferred; no kubectl path exists, so the entry is only reported
            writes.append(("unsupported", {
                "key": "gke",
                "reason": "GKE deploy scope is not supported yet: F7 acts on cloud_run entries only"}))
            continue
        if "cloud_run" not in d:
            continue
        deployable = d["cloud_run"]
        if not deployable:
            errors.append("error: %s: deploys entry without a deployable name" % name)
            continue
        deployer = "%s-deployer" % deployable
        if len(deployer) > MAX_SA_LEN:
            errors.append("error: %s: deployer SA name '%s' is %d chars, max %d"
                          % (name, deployer, len(deployer), MAX_SA_LEN))
            continue
        if deployer in protected:
            errors.append("error: %s: deployer SA name '%s' is a protected service account"
                          % (name, deployer))
            continue
        member = "serviceAccount:%s@%s.iam.gserviceaccount.com" % (deployer, project)

        def bind(rtype, res, role, iam, region=None):
            if not held(iam, role, member):
                det = {"resource_type": rtype, "resource": res, "role": role, "member": member}
                if region:
                    det["region"] = region      # from the register: no live lookup is ever needed
                writes.append(("add-resource-binding", det))

        if "cloud_run" in d:
            region, runtime = d.get("region"), d.get("runtime_service_account")
            if not region or not runtime:
                errors.append("error: %s: cloud_run '%s' needs region and runtime_service_account"
                              % (name, deployable))
                continue
            if runtime in protected:
                errors.append("error: %s: runtime_service_account '%s' is a protected service account"
                              % (name, runtime))
                continue
            services = state.get("cloud_run_services") or {}
            svc = services.get(deployable)
            sa = (state.get("service_accounts") or {}).get(runtime) or {}
            runtime_email = "%s@%s.iam.gserviceaccount.com" % (runtime, project)
            # repo-admin has no project-wide act-as: it grants itself serviceAccountUser on THIS
            # runtime SA first, so the right is a visible line in that SA's own policy.
            admin_member = "serviceAccount:%s" % admin_email
            if runtime not in admin_done and not held(sa.get("iam"), SA_USER, admin_member):
                writes.append(("add-resource-binding", {
                    "resource_type": "iam.serviceAccount", "resource": runtime_email,
                    "role": SA_USER, "member": admin_member}))
            admin_done.add(runtime)
            if svc is None:
                writes.append(("create-service", {
                    "service": deployable, "region": region,
                    "runtime_service_account": runtime, "image": "placeholder"}))
            bind("run.service", deployable, RUN_DEV, (svc or {}).get("iam"), region)
            bind("iam.serviceAccount", runtime_email, SA_USER, sa.get("iam"))
            gar = d.get("image_repository")
            if gar:
                bind("artifactregistry.repository", gar, GAR_WRITER,
                     ((state.get("gar_repositories") or {}).get(gar) or {}).get("iam"))

    out = []
    for verb, details in writes:
        if verb == "unsupported" or mode == "enforce":
            out.append(act(name, verb, details))
        else:
            out.append(act(name, "drift", dict(would=verb, **details)))
    if not out:
        out.append(act(name, "in-sync", {}))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature", required=True)
    ap.add_argument("--register", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--repo-admin-sa-email", required=True)
    repos_protected.add_argument(ap)
    args = ap.parse_args(argv)
    if args.feature != FEATURE:
        print("error: register: unknown feature %r" % args.feature, file=sys.stderr)
        return 2
    with open(args.register) as f:
        reg = yaml.safe_load(f)
    with open(args.state) as f:
        state = json.load(f)
    default_mode = ((reg.get("defaults") or {}).get("mode")) or "report"
    errors, actions = [], []
    for repo in reg.get("repos") or []:
        mode = repo.get("mode") or default_mode
        actions.extend(plan_repo(repo, mode, state, errors,
                                 repos_protected.parse(args.protected_service_accounts),
                                 args.repo_admin_sa_email))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(json.dumps(actions, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
