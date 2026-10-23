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

import repos_plan

FEATURE = "deploy-scope"
RUN_DEV = "roles/run.developer"
SA_USER = "roles/iam.serviceAccountUser"
GAR_WRITER = "roles/artifactregistry.writer"
RUN_INVOKER = "roles/run.invoker"
ALL_USERS = "allUsers"
MIN_SA_LEN = 6
MAX_SA_LEN = 30


def act(repo, action, details):
    return {"feature": FEATURE, "repo": repo, "action": action, "details": details}


def held(policy_entries, role, member):
    for e in policy_entries or []:
        if e.get("role") == role and member in (e.get("members") or []):
            return True
    return False


def plan_repo(repo, mode, state, errors, admin_email):
    name = repo["name"]
    project = state.get("project_id")
    writes = []  # (verb, details) in apply order; needs-jgd/unsupported/drift pass through in any mode
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
        runtime = "%s-run" % deployable
        # both derived account ids must be valid GCP ids (6-30 chars): a one-char deployable gives
        # `a-run` (5), which the access-provisioning side could never declare
        bad_id = next(((k, i) for k, i in (("deployer", deployer), ("runtime", runtime))
                       if not MIN_SA_LEN <= len(i) <= MAX_SA_LEN), None)
        if bad_id:
            errors.append("error: %s: %s SA name '%s' is %d chars, must be %d-%d"
                          % (name, bad_id[0], bad_id[1], len(bad_id[1]), MIN_SA_LEN, MAX_SA_LEN))
            continue
        member = "serviceAccount:%s@%s.iam.gserviceaccount.com" % (deployer, project)

        def bind(rtype, res, role, iam, region=None, mem=member):
            if not held(iam, role, mem):
                det = {"resource_type": rtype, "resource": res, "role": role, "member": mem}
                if region:
                    det["region"] = region      # from the register: no live lookup is ever needed
                writes.append(("add-resource-binding", det))

        region = d.get("region")
        if not region:
            errors.append("error: %s: cloud_run '%s' needs region" % (name, deployable))
            continue
        # ruling 21: the runtime SA is DERIVED (`<d>-run`), never chosen, so a repo cannot point its
        # service at another identity. The key is optional; when present it must equal the derived name.
        given = d.get("runtime_service_account")
        if given is not None and given != runtime:
            errors.append("error: %s: runtime_service_account '%s' must be '%s' (derived from the "
                          "deployable; omit the key)" % (name, given, runtime))
            continue
        services = state.get("cloud_run_services") or {}
        svc = services.get(deployable)
        # F7 never removes a grant (owner Q1, 2026-10-23): a public service whose entry is not
        # `public: true` is reported in every mode, and a person removes the grant
        if svc is not None and d.get("public") is not True and held(svc.get("iam"), RUN_INVOKER, ALL_USERS):
            writes.append(("drift", {
                "would": "remove-public-invoker", "resource_type": "run.service",
                "resource": deployable, "region": region, "role": RUN_INVOKER, "member": ALL_USERS,
                "reason": "the service is public but its register entry has no `public: true`; "
                          "F7 never removes a grant: remove allUsers roles/run.invoker by hand "
                          "or add `public: true`"}))
        sa = (state.get("service_accounts") or {}).get(runtime) or {}
        runtime_email = "%s@%s.iam.gserviceaccount.com" % (runtime, project)
        admin_member = "serviceAccount:%s" % admin_email
        # `gcloud run deploy --service-account=<d>-run` needs repo-admin's act_as on that account, and
        # F7 cannot grant it (ruling 21). While a NEW service's act_as line is not live (or the
        # account is absent) nothing is created or bound for the deployable: only needs-jgd is
        # planned, so no run ever reaches a doomed deploy and half-applies a register.
        ready = svc is not None or held(sa.get("iam"), SA_USER, admin_member)
        if ready:
            if svc is None:
                writes.append(("create-service", {
                    "service": deployable, "region": region,
                    "runtime_service_account": runtime, "image": "placeholder"}))
            bind("run.service", deployable, RUN_DEV, (svc or {}).get("iam"), region)
            # `public: true`: F7 is the one writer of who may CALL a service; the deployer's
            # run.developer cannot set a service policy, so `--allow-unauthenticated` on deploy is inert
            if d.get("public") is True:
                bind("run.service", deployable, RUN_INVOKER, (svc or {}).get("iam"), region, ALL_USERS)
            gar = d.get("image_repository")
            if gar:
                bind("artifactregistry.repository", gar, GAR_WRITER,
                     ((state.get("gar_repositories") or {}).get(gar) or {}).get("iam"))
        # F7 writes NO service-account policy (ruling 21: one writer, the access-provisioning side).
        # It only READS the runtime SA's policy and reports each line that is not live yet.
        lines = []
        if svc is None:
            lines.append(("act_as: repo-admin", admin_member))
        lines.append(("deployed_by: %s" % deployer, member))
        for need, mem in lines:
            if not held(sa.get("iam"), SA_USER, mem):
                writes.append(("needs-jgd", {
                    "resource_type": "iam.serviceAccount", "resource": runtime_email,
                    "role": SA_USER, "member": mem, "needs": need}))

    out = []
    for verb, details in writes:
        if verb in ("unsupported", "needs-jgd", "drift") or mode == "enforce":
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
    args = ap.parse_args(argv)
    if args.feature != FEATURE:
        print("error: register: unknown feature %r" % args.feature, file=sys.stderr)
        return 2
    with open(args.register) as f:
        reg = yaml.safe_load(f)
    # F1-style validation first: a name that is not a valid service/region/SA/repo name (or that
    # starts with '-') must never reach a command line, so nothing is planned for a bad register.
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
        mode = repo.get("mode") or default_mode
        actions.extend(plan_repo(repo, mode, state, errors, args.repo_admin_sa_email))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(json.dumps(actions, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
