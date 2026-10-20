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
CLUSTER_VIEWER = "roles/container.clusterViewer"
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
    legacy = []
    admin_done = set()          # runtime SAs whose repo-admin binding is already planned for this repo
    for d in repo.get("deploys") or []:
        if "cloud_run" in d:
            deployable = d["cloud_run"]
        elif isinstance(d.get("gke"), dict):
            deployable = d["gke"].get("workload")
        else:
            continue
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

        def bind(rtype, res, role, iam):
            if not held(iam, role, member):
                writes.append(("add-resource-binding", {
                    "resource_type": rtype, "resource": res, "role": role, "member": member}))

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
            bind("run.service", deployable, RUN_DEV, (svc or {}).get("iam"))
            bind("iam.serviceAccount", runtime_email, SA_USER, sa.get("iam"))
            gar = d.get("image_repository")
            if gar:
                bind("artifactregistry.repository", gar, GAR_WRITER,
                     ((state.get("gar_repositories") or {}).get(gar) or {}).get("iam"))
        else:
            g = d["gke"]
            cluster, ns = g.get("cluster"), g.get("namespace")
            if not cluster or not ns:
                errors.append("error: %s: gke '%s' needs cluster and namespace" % (name, deployable))
                continue
            cl = (state.get("gke_clusters") or {}).get(cluster) or {}
            # GKE has no cluster-resource IAM: clusterViewer exists only at project level, so it
            # is never granted here. Its absence is a report, in both modes.
            if CLUSTER_VIEWER not in ((state.get("project_roles") or {}).get(deployer) or []):
                writes.append(("unsupported", {
                    "key": "gke.cluster_viewer",
                    "reason": "%s exists only at project level (GKE has no cluster IAM); grant it "
                              "to %s in the access-provisioning config" % (CLUSTER_VIEWER, deployer)}))
            applied = any(r.get("namespace") == ns and r.get("workload") == deployable
                          and r.get("member") == member
                          and r.get("resource_names") == [deployable]
                          for r in cl.get("rbac") or [])
            if not applied:
                writes.append(("apply-k8s-rbac", {
                    "cluster": cluster, "namespace": ns, "workload": deployable,
                    "resource_names": [deployable], "member": member}))

        for role in (state.get("project_roles") or {}).get(deployer) or []:
            if role == CLUSTER_VIEWER:
                continue
            if role.startswith("roles/run.") or role.startswith("roles/container."):
                legacy.append(act(name, "legacy-grant", {
                    "service_account": deployer, "role": role, "scope": "project"}))

    out = []
    for verb, details in writes:
        if verb == "unsupported" or mode == "enforce":
            out.append(act(name, verb, details))
        else:
            out.append(act(name, "drift", dict(would=verb, **details)))
    out.extend(legacy)
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
