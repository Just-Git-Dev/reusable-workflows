#!/usr/bin/env python3
"""Red tests for the F5 planner `scripts/repos_wif_plan.py` (docs/repos-register.md §6 F5, §8).

IMPLEMENTER'S CONTRACT (the parts docs §7/§8 leave to the feature's fixtures):

  python3 scripts/repos_wif_plan.py --feature wif-link --register <repos.yaml> --state <state.json>

  state.json = {
    "project_number": "123456789",          # GCP project NUMBER (string), for the principalSet
    "pool": "example-pool",                 # workload identity pool id
    "service_accounts": {                   # keyed by SA account-id (the register's SA name)
      "<sa-name>": {"exists": true|false,
                    "policy": {"etag": "...", "bindings": [{"role": "...", "members": ["..."]}]}}
    }
  }
  A name absent from `service_accounts`, or with exists=false, is a missing SA -> error.

  Output / error / exit code: exactly docs §8 (stdout JSON array; on error empty stdout,
  `error: <sa-or-repo>: <reason>` lines on stderr, exit 1). Mode per repo = repo.mode, else
  defaults.mode, else `report`. A repo with >=1 write/drift action emits no `in-sync`; a repo whose
  SAs are all linked emits exactly one `in-sync`.

NOT COVERED (docs §8 is silent): what to do with a binding that is on the SA but not in the
register. §5.8 forbids removing it, §8 has no verb to report it. Raised to the owner as a question.

Test env: PLANNER=<path> overrides the planner script (used to prove the suite fails vs a `[]` stub).
Registers are written as JSON (valid YAML 1.2).

Usage:  python3 tests/run_repos_wif_plan_tests.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures-repos-wif"
PLANNER = Path(os.environ.get("PLANNER") or ROOT / "scripts" / "repos_wif_plan.py")

ROLE = "roles/iam.workloadIdentityUser"
POOL = "example-pool"
NUM = "123456789"
ALLOWED_VERBS = {"add-wif-binding", "in-sync", "skip", "drift", "unregistered-binding"}


def member(repo, org="Example-Org", pool=POOL, num=NUM):
    return ("principalSet://iam.googleapis.com/projects/%s/locations/global/"
            "workloadIdentityPools/%s/attribute.repository/%s/%s" % (num, pool, org, repo))


def register(repos, mode="enforce", **extra):
    reg = {"version": 1, "org": "Example-Org", "defaults": {"mode": mode}, "repos": repos}
    reg.update(extra)
    return reg


def repo(name, sas, **extra):
    r = {"name": name, "gcp": {"service_accounts": sas}}
    r.update(extra)
    return r


def sa(bindings=None, exists=True):
    return {"exists": exists, "policy": {"etag": "BwXXXX", "bindings": bindings or []}}


def state(sas, number=NUM, pool=POOL):
    return {"project_number": number, "pool": pool, "service_accounts": sas}


def add(r, s, mem=None):
    return {"feature": "wif-link", "repo": r, "action": "add-wif-binding",
            "details": {"service_account": s, "role": ROLE, "member": mem or member(r)}}


def drift(r, s, mem=None):
    return {"feature": "wif-link", "repo": r, "action": "drift",
            "details": {"would": "add-wif-binding", "service_account": s, "role": ROLE,
                        "member": mem or member(r)}}


def insync(r):
    return {"feature": "wif-link", "repo": r, "action": "in-sync", "details": {}}


def unreg(r, s, role, m):
    return {"feature": "wif-link", "repo": r, "action": "unregistered-binding",
            "details": {"service_account": s, "role": role, "member": m}}


def run(reg, st, tmp, reg_is_path=False, extra=()):
    d = Path(tmp)
    rp, sp = d / "repos.yaml", d / "state.json"
    if reg_is_path:
        rp, sp = reg, st
    else:
        rp.write_text(json.dumps(reg))
        sp.write_text(json.dumps(st))
    p = subprocess.run(
        [sys.executable, str(PLANNER), "--feature", "wif-link", "--register", str(rp),
         "--state", str(sp), *extra], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


FAILURES = []
COUNT = [0]


def check(name, ok, detail=""):
    COUNT[0] += 1
    if not ok:
        FAILURES.append("%s: %s" % (name, detail))


def plan(name, reg, st):
    """Run expecting success; return the parsed action list or None."""
    with tempfile.TemporaryDirectory() as t:
        rc, out, err = run(reg, st, t)
    if rc != 0:
        check(name, False, "exit %d, stderr=%r" % (rc, err[:200]))
        return None
    try:
        acts = json.loads(out)
    except ValueError:
        check(name, False, "stdout is not JSON: %r" % out[:200])
        return None
    return acts


def expect(name, reg, st, want):
    acts = plan(name, reg, st)
    if acts is not None:
        check(name, acts == want, "got %s" % json.dumps(acts))
    return acts


def expect_error(name, reg, st, needle, extra=()):
    with tempfile.TemporaryDirectory() as t:
        rc, out, err = run(reg, st, t, extra=extra)
    lines = [ln for ln in err.splitlines() if ln.strip()]
    check(name + " (exit 1)", rc == 1, "exit %d" % rc)
    check(name + " (no stdout)", out.strip() == "", "stdout=%r" % out[:100])
    check(name + " (stderr format)", bool(lines) and all(ln.startswith("error: ") for ln in lines),
          "stderr=%r" % err[:200])
    check(name + " (names culprit)", needle in err, "stderr=%r" % err[:200])


def main():
    D = "payments-api-deployer"

    # 1. golden static fixture (the doc example)
    with tempfile.TemporaryDirectory() as t:
        rc, out, err = run(FIXTURES / "register.yaml", FIXTURES / "state-missing.json", t, True)
    want = json.loads((FIXTURES / "expected-missing.json").read_text())
    check("golden fixture", rc == 0 and json.loads(out or "null") == want,
          "rc=%d out=%r err=%r" % (rc, out[:200], err[:200]))

    # 2. missing pair -> add; pool and number come from the state
    expect("missing pair -> add", register([repo("payments-api", [D])]),
           state({D: sa()}), [add("payments-api", D)])
    expect("pool/number are inputs", register([repo("payments-api", [D])]),
           state({D: sa()}, number="987654321", pool="other-pool"),
           [add("payments-api", D, member("payments-api", num="987654321", pool="other-pool"))])

    # 3. already linked -> in-sync (only one in-sync per repo even with two SAs)
    linked = [{"role": ROLE, "members": [member("payments-api")]}]
    expect("linked -> in-sync", register([repo("payments-api", [D])]),
           state({D: sa(linked)}), [insync("payments-api")])
    expect("two linked SAs -> one in-sync", register([repo("payments-api", [D, "ledger-run-sa"])]),
           state({D: sa(linked), "ledger-run-sa": sa(linked)}), [insync("payments-api")])

    # 4. linked among several members of the role
    many = [{"role": ROLE, "members": [member("other-repo"), member("payments-api")]}]
    expect("linked among many members", register([repo("payments-api", [D])]),
           state({D: sa(many)}), [unreg("payments-api", D, ROLE, member("other-repo"))])
    only = [{"role": ROLE, "members": [member("payments-api")]}]
    expect("linked, nothing else -> in-sync", register([repo("payments-api", [D])]),
           state({D: sa(only)}), [insync("payments-api")])

    # 5. partial: one SA linked, one not -> only the missing pair, no in-sync
    expect("partial link", register([repo("payments-api", [D, "ledger-run-sa"])]),
           state({D: sa(linked), "ledger-run-sa": sa()}), [add("payments-api", "ledger-run-sa")])

    # 6. near-misses are NOT linked: other role, other repo, other org, other pool
    for label, b in [
        ("other role", [{"role": "roles/iam.serviceAccountTokenCreator",
                         "members": [member("payments-api")]}]),
        ("other repo", [{"role": ROLE, "members": [member("payments-api2")]}]),
        ("other org", [{"role": ROLE, "members": [member("payments-api", org="Other-Org")]}]),
        ("other pool", [{"role": ROLE, "members": [member("payments-api", pool="p2")]}]),
    ]:
        # the near-miss binding is itself unregistered: reported after the repo's add
        expect("near-miss: " + label, register([repo("payments-api", [D])]),
               state({D: sa(b)}),
               [add("payments-api", D),
                unreg("payments-api", D, b[0]["role"], b[0]["members"][0])])

    # 7. same SA for two repos; register order across repos and SAs
    reg = register([repo("repo-b", ["sa-two-x", D]), repo("repo-a", [D])])
    expect("order = register order", reg, state({D: sa(), "sa-two-x": sa()}),
           [add("repo-b", "sa-two-x"), add("repo-b", D), add("repo-a", D)])

    # 8. missing SA -> error, whole run refused (no partial plan), exists=false and absent
    expect_error("SA exists=false", register([repo("payments-api", [D])]),
                 state({D: sa(exists=False)}), D)
    expect_error("SA absent from state", register([repo("payments-api", [D])]), state({}), D)
    expect_error("no partial plan", register([repo("repo-a", [D]), repo("repo-b", ["ghost-sa"])]),
                 state({D: sa()}), "ghost-sa")

    # 9. report mode -> drift only; per-repo mode override; default mode is report
    expect("report -> drift", register([repo("payments-api", [D])], mode="report"),
           state({D: sa()}), [drift("payments-api", D)])
    expect("repo mode overrides default",
           register([repo("repo-a", [D], mode="enforce"), repo("repo-b", [D])], mode="report"),
           state({D: sa()}), [add("repo-a", D), drift("repo-b", D)])
    reg = register([repo("payments-api", [D])])
    del reg["defaults"]
    expect("mode defaults to report", reg, state({D: sa()}), [drift("payments-api", D)])
    expect("report + linked -> in-sync", register([repo("payments-api", [D])], mode="report"),
           state({D: sa(linked)}), [insync("payments-api")])

    # 10. NEVER list: no removal, no other role, nothing for repos not in the register
    stale = [
        {"role": ROLE, "members": [member("old-repo"), member("payments-api")]},
        {"role": "roles/iam.serviceAccountUser", "members": ["user:someone@example.com"]},
    ]
    for mode in ("enforce", "report"):
        acts = plan("never-list " + mode,
                    register([repo("payments-api", [D]), repo("ledger-worker", [D])], mode=mode),
                    state({D: sa(stale)}))
        if acts is None:
            continue
        check("never-list verbs " + mode, all(a.get("action") in ALLOWED_VERBS for a in acts),
              json.dumps(acts))
        check("never-list no remove " + mode,
              not any("remove" in json.dumps(a).lower() or "delete" in json.dumps(a).lower()
                      for a in acts), json.dumps(acts))
        check("never-list role " + mode,
              all(a["details"].get("role", ROLE) == ROLE for a in acts
                  if a["action"] in ("add-wif-binding", "drift")), json.dumps(acts))
        check("never-list no project grant " + mode,
              not any(a["details"].get("scope") == "project" or
                      a["details"].get("resource_type") == "project" for a in acts),
              json.dumps(acts))
        check("never-list unlisted repo " + mode,
              {a["repo"] for a in acts} <= {"payments-api", "ledger-worker"}, json.dumps(acts))
        check("never-list exact keys " + mode,
              all(list(a) == ["feature", "repo", "action", "details"] for a in acts),
              json.dumps(acts))
    expect("repo removed from register -> no action for it",
           register([repo("payments-api", [D])]), state({D: sa(linked)}), [insync("payments-api")])

    # 10b. unregistered-binding (docs 7.2): any binding on a registered SA that the register does
    # not list is reported (both modes), never removed. Attached to the first repo listing the SA,
    # after that repo's other actions, in policy order; it suppresses that repo's in-sync.
    def ub(r, role, m):
        return unreg(r, D, role, m)
    UB = [ub("payments-api", ROLE, member("old-repo")),
          ub("payments-api", "roles/iam.serviceAccountUser", "user:someone@example.com")]
    expect("unregistered bindings (enforce)",
           register([repo("payments-api", [D]), repo("ledger-worker", [D])]), state({D: sa(stale)}),
           UB + [add("ledger-worker", D)])
    expect("unregistered bindings (report)",
           register([repo("payments-api", [D]), repo("ledger-worker", [D])], mode="report"),
           state({D: sa(stale)}), UB + [drift("ledger-worker", D)])
    expect("unregistered binding on an SA no repo lists is not examined",
           register([repo("payments-api", [D])]), state({D: sa(linked), "other-sa-xx": sa(stale)}),
           [insync("payments-api")])

    # 11. unknown keys ignored at every level, and repos without our key are not our business
    reg = register([repo("payments-api", [D], future_key={"x": 1}, kind="go-service")],
                   something_new=[1, 2])
    reg["defaults"]["future_default"] = True
    expect("unknown keys ignored", reg, state({D: sa()}), [add("payments-api", D)])

    # 12. determinism
    reg, st = register([repo("repo-a", [D, "sa-two-x"])]), state({D: sa(), "sa-two-x": sa()})
    a1, a2 = plan("determinism 1", reg, st), plan("determinism 2", reg, st)
    check("determinism", a1 is not None and a1 == a2)

    # 13. bad register -> error naming the register
    bad = register([repo("payments-api", [D])])
    bad["version"] = 2
    expect_error("version != 1", bad, state({D: sa()}), "register")

    # 14. B1: a protected SA is never linked. repo-admin is hard-coded (no input needed), the
    # input adds more; the error is total (no partial plan) in report and enforce mode alike.
    for mode in ("enforce", "report"):
        ok_repo, bad_repo = repo("payments-api", [D]), repo("project", ["repo-admin"])
        st = state({D: sa(), "repo-admin": sa()})
        expect_error("B1 repo-admin refused (" + mode + ")",
                     register([ok_repo, bad_repo], mode=mode), st, "repo-admin")
        expect_error("B1 repo-admin refused when it does not exist live (" + mode + ")",
                     register([bad_repo], mode=mode), state({}), "protected")
        expect_error("B1 input list adds a protected SA (" + mode + ")",
                     register([repo("payments-api", ["github-releaser"])], mode=mode),
                     state({"github-releaser": sa()}), "github-releaser",
                     extra=["--protected-service-accounts", "ci-deployer-x,github-releaser"])
    expect_error("B1 newline list", register([repo("a-repo", ["ci-deployer-x"])]),
                 state({"ci-deployer-x": sa()}), "ci-deployer-x",
                 extra=["--protected-service-accounts", "foo-bar-baz\nci-deployer-x\n"])
    # a lookalike is not protected; an empty list still leaves repo-admin protected
    expect("B1 unprotected SA still linked with a list given",
           register([repo("payments-api", [D])]), state({D: sa()}), [add("payments-api", D)])
    expect_error("B1 empty list keeps repo-admin protected", register([repo("p", ["repo-admin"])]),
                 state({"repo-admin": sa()}), "repo-admin", extra=["--protected-service-accounts", ""])

    print("repos_wif_plan: %d checks, %d failed" % (COUNT[0], len(FAILURES)))
    for f in FAILURES:
        print("  FAIL " + f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
