#!/usr/bin/env python3
"""Red tests for the F6 planner `scripts/repos_sa_plan.py` (docs/repos-register.md §6 F6, §3, §8).

IMPLEMENTER'S CONTRACT (the parts docs §7/§8 leave to the feature's fixtures):

  python3 scripts/repos_sa_plan.py --feature service-accounts --register <repos.yaml> --state <state.json>

  state.json = {"service_accounts": [{"name": "<account-id>", "description": "...",
                                      "display_name": "..."}]}      # SAs that exist live

  Output / error / exit code: exactly docs §8 (stdout JSON array; on error empty stdout,
  `error: <sa>: <reason>` lines on stderr, exit 1, no partial plan). Every action has repo null.
  Mode per SA = the SA entry's `mode`, else defaults.mode, else `report`. A register with no
  `service_accounts` (or an empty list) yields `[]`.
  Fields are compared only when the register states them; an SA with no `display_name` in the
  register is never reported as drifting on display_name (these tests avoid depending on any
  default for a create without display_name beyond `description` being present).

Test env: PLANNER=<path> overrides the planner script (used to prove the suite fails vs a `[]` stub).
Registers are written as JSON (valid YAML 1.2).

Usage:  python3 tests/run_repos_sa_plan_tests.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures-repos-sa"
PLANNER = Path(os.environ.get("PLANNER") or ROOT / "scripts" / "repos_sa_plan.py")

ALLOWED_VERBS = {"create-service-account", "update-service-account", "in-sync", "skip", "drift"}
DESC = "CI deployer for payments-api only (owner: payments team)"


def register(sas, mode="enforce", **extra):
    reg = {"version": 1, "org": "Example-Org", "defaults": {"mode": mode},
           "service_accounts": sas, "repos": []}
    reg.update(extra)
    return reg


def entry(name, description=DESC, display_name="Payments deployer", **extra):
    e = {"name": name, "description": description}
    if display_name is not None:
        e["display_name"] = display_name
    e.update(extra)
    return e


def live(name, description=DESC, display_name="Payments deployer"):
    return {"name": name, "description": description, "display_name": display_name}


def state(*sas):
    return {"service_accounts": list(sas)}


def act(action, **details):
    return {"feature": "service-accounts", "repo": None, "action": action, "details": details}


def create(name, description=DESC, display_name="Payments deployer"):
    return act("create-service-account", name=name, display_name=display_name,
               description=description)


def update(name, field, old, new):
    return act("update-service-account", name=name, field=field, **{"from": old, "to": new})


def drift(would, **details):
    return act("drift", would=would, **details)


def insync(name=None):
    return act("in-sync")


def run(reg, st, tmp, paths=False, extra=()):
    d = Path(tmp)
    rp, sp = d / "repos.yaml", d / "state.json"
    if paths:
        rp, sp = reg, st
    else:
        rp.write_text(json.dumps(reg))
        sp.write_text(json.dumps(st))
    p = subprocess.run(
        [sys.executable, str(PLANNER), "--feature", "service-accounts", "--register", str(rp),
         "--state", str(sp), *extra], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


FAILURES = []
COUNT = [0]


def check(name, ok, detail=""):
    COUNT[0] += 1
    if not ok:
        FAILURES.append("%s: %s" % (name, detail))


def plan(name, reg, st, extra=()):
    with tempfile.TemporaryDirectory() as t:
        rc, out, err = run(reg, st, t, extra=extra)
    if rc != 0:
        check(name, False, "exit %d, stderr=%r" % (rc, err[:200]))
        return None
    try:
        return json.loads(out)
    except ValueError:
        check(name, False, "stdout is not JSON: %r" % out[:200])
        return None


def key(a):
    return json.dumps(a, sort_keys=True)


def expect(name, reg, st, want, ordered=True, extra=()):
    acts = plan(name, reg, st, extra)
    if acts is not None:
        ok = acts == want if ordered else sorted(map(key, acts)) == sorted(map(key, want))
        check(name, ok, "got %s" % json.dumps(acts))
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
    N = "payments-api-deployer"

    # 1. golden static fixture
    with tempfile.TemporaryDirectory() as t:
        rc, out, err = run(FIXTURES / "register.yaml", FIXTURES / "state-empty.json", t, True)
    want = json.loads((FIXTURES / "expected-create.json").read_text())
    check("golden fixture", rc == 0 and json.loads(out or "null") == want,
          "rc=%d out=%r err=%r" % (rc, out[:200], err[:200]))

    # 2. create only the missing ones, in register order
    expect("create missing", register([entry(N)]), state(), [create(N)])
    expect("create only the missing",
           register([entry("one-aa-deployer"), entry("two-bb-deployer"), entry("three-cc-deployer")]),
           state(live("two-bb-deployer")),
           [create("one-aa-deployer"), insync(), create("three-cc-deployer")])

    # 2b. display_name defaults to the SA name on create only (docs 7.2); compared only when stated
    expect("create: display_name defaults to name", register([entry(N, display_name=None)]),
           state(), [create(N, display_name=N)])
    expect("no display_name in register -> never drift on it", register([entry(N, display_name=None)]),
           state(live(N, display_name="whatever")), [insync()])

    # 3. in-sync
    expect("existing in sync", register([entry(N)]), state(live(N)), [insync()])

    # 4. description / display_name differ -> update (enforce)
    expect("description differs", register([entry(N)]), state(live(N, description="old")),
           [update(N, "description", "old", DESC)])
    expect("display_name differs", register([entry(N)]), state(live(N, display_name="old")),
           [update(N, "display_name", "old", "Payments deployer")])
    expect("both differ", register([entry(N)]),
           state(live(N, description="old d", display_name="old n")),
           [update(N, "description", "old d", DESC),
            update(N, "display_name", "old n", "Payments deployer")], ordered=False)

    # 5. report mode -> drift only, never a write
    expect("report: missing -> drift", register([entry(N)], mode="report"), state(),
           [drift("create-service-account", name=N, display_name="Payments deployer",
                  description=DESC)])
    expect("report: differs -> drift", register([entry(N)], mode="report"),
           state(live(N, description="old")),
           [drift("update-service-account", name=N, field="description", **{"from": "old", "to": DESC})])
    expect("report: in sync", register([entry(N)], mode="report"), state(live(N)), [insync()])
    expect("entry mode overrides default", register(
        [entry("one-aa-deployer", mode="enforce"), entry("two-bb-deployer")], mode="report"), state(),
        [create("one-aa-deployer"),
         drift("create-service-account", name="two-bb-deployer", display_name="Payments deployer",
               description=DESC)])
    reg = register([entry(N)])
    del reg["defaults"]
    expect("mode defaults to report", reg, state(),
           [drift("create-service-account", name=N, display_name="Payments deployer",
                  description=DESC)])

    # 6. name validation (6-30 chars, ^[a-z][a-z0-9-]*$, no trailing hyphen) -> error
    for label, name in [
        ("5 chars", "abcde"), ("31 chars", "a" * 31), ("uppercase", "Payments-deployer"),
        ("leading digit", "1payments-deployer"), ("underscore", "payments_deployer"),
        ("trailing hyphen", "payments-deployer-"), ("empty", ""), ("dot", "payments.deployer"),
    ]:
        expect_error("bad name: " + label, register([entry(name)]), state(), name or "service_accounts")
    # boundaries are accepted
    expect("10 chars ok", register([entry("a-deployer")]), state(), [create("a-deployer")])
    expect("30 chars ok", register([entry("a" * 21 + "-deployer")]), state(), [create("a" * 21 + "-deployer")])

    # 7. description required (missing, empty) and bounded
    e = entry(N)
    del e["description"]
    expect_error("missing description", register([e]), state(), N)
    expect_error("empty description", register([entry(N, description="")]), state(), N)
    expect_error("description > 256", register([entry(N, description="x" * 257)]), state(), N)
    expect_error("display_name > 100", register([entry(N, display_name="x" * 101)]), state(), N)

    # 8. no partial plan: one bad entry refuses the whole run
    expect_error("no partial plan", register([entry("one-aa-deployer"), entry("BAD")]), state(), "BAD")

    # 9. an SA that exists live but is not in the register -> no action at all
    expect("unlisted live SA untouched", register([entry(N)]),
           state(live(N), live("legacy-zz-deployer", description="who knows")), [insync()])
    expect("empty register list", register([]), state(live("legacy-zz-deployer")), [])
    reg = register([])
    del reg["service_accounts"]
    expect("no service_accounts key", reg, state(live("legacy-zz-deployer")), [])
    expect("removed from register -> no action", register([entry("one-aa-deployer")]),
           state(live("one-aa-deployer"), live(N)), [insync()])

    # 10. NEVER list: no delete / key / role verbs, repo is always null, exact keys
    for mode in ("enforce", "report"):
        acts = plan("never-list " + mode,
                    register([entry("one-aa-deployer"), entry("two-bb-deployer"), entry("three-cc-deployer")],
                             mode=mode),
                    state(live("two-bb-deployer", description="old"), live("legacy-zz-deployer")))
        if acts is None:
            continue
        check("never verbs " + mode, all(a["action"] in ALLOWED_VERBS for a in acts), json.dumps(acts))
        blob = json.dumps(acts).lower()
        check("never delete/key/role " + mode,
              not any(w in blob for w in ("delete", "key", "role", "iam", "binding", "member")), blob)
        check("never legacy touched " + mode, "legacy-zz-deployer" not in blob, blob)
        check("repo null + feature " + mode,
              all(a["repo"] is None and a["feature"] == "service-accounts" for a in acts), blob)
        check("exact keys " + mode,
              all(list(a) == ["feature", "repo", "action", "details"] for a in acts), blob)
        if mode == "report":
            check("report only non-write", all(a["action"] in {"drift", "in-sync", "skip"}
                                               for a in acts), blob)

    # 11. unknown keys are ignored (at every level), repos are not this feature's business
    e = entry(N, future_key={"x": 1})
    reg = register([e], something_new=[1], repos=[{"name": "payments-api", "gcp": {"service_accounts": ["nope-nope"]}}])
    expect("unknown keys ignored", reg, state(live(N)), [insync()])

    # 12. determinism, bad version
    reg = register([entry("one-aa-deployer"), entry("two-bb-deployer")])
    a1, a2 = plan("determinism 1", reg, state()), plan("determinism 2", reg, state())
    check("determinism", a1 is not None and a1 == a2)
    bad = register([entry(N)])
    bad["version"] = 2
    expect_error("version != 1", bad, state(), "register")

    # 13. ruling 21: F6 creates/updates only `<d>-deployer` SAs and never adopts any other name
    # (so repo-admin, github-releaser and every JGD-declared SA are refused by name, in both modes).
    for mode in ("enforce", "report"):
        expect_error("not a project SA: repo-admin create (" + mode + ")",
                     register([entry("one-aa-deployer"), entry("repo-admin")], mode=mode), state(),
                     "repo-admin is not a project SA")
        expect_error("not a project SA: repo-admin update (" + mode + ")",
                     register([entry("repo-admin", description="changed")], mode=mode),
                     state(live("repo-admin")), "repo-admin is not a project SA")
        expect_error("never adopt an existing non-deployer SA (" + mode + ")",
                     register([entry("github-releaser")], mode=mode), state(live("github-releaser")),
                     "github-releaser is not a project SA")
        expect_error("a runtime SA is JGD's (" + mode + ")",
                     register([entry("payments-api-run")], mode=mode), state(),
                     "payments-api-run is not a project SA")
    # the deprecated input is accepted and ignored
    expect("deprecated input is a no-op", register([entry("one-aa-deployer")]),
           state(live("one-aa-deployer")), [insync()],
           extra=["--protected-service-accounts", "one-aa-deployer,x"])
    expect_error("deprecated input cannot lift the rule", register([entry("github-releaser")]), state(),
                 "github-releaser is not a project SA", extra=["--protected-service-accounts", ""])

    print("repos_sa_plan: %d checks, %d failed" % (COUNT[0], len(FAILURES)))
    for f in FAILURES:
        print("  FAIL " + f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
