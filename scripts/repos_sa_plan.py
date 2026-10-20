#!/usr/bin/env python3
"""F6 planner: the project's own service accounts. Pure: no network, no clock.

    python3 scripts/repos_sa_plan.py --feature service-accounts --register repos.yaml --state state.json

Prints the docs/repos-register.md §8 action list to stdout (exit 0), or nothing to stdout and one
`error: <sa|register>: <reason>` line per error to stderr (exit 1). The NEVER list is enforced by
vocabulary: the only write verbs are `create-service-account` and `update-service-account`; there is
no verb for deleting an SA, creating a key, or granting any role. A live SA the register does not
list gets no action.
"""

import argparse
import json
import re
import sys

import yaml

FEATURE = "service-accounts"
SA_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
ORG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def act(action, details):
    return {"feature": FEATURE, "repo": None, "action": action, "details": details}


def validate(reg, errors):
    if not isinstance(reg, dict):
        errors.append(("register", "register is not a mapping"))
        return []
    if reg.get("version") != 1 or isinstance(reg.get("version"), bool):
        errors.append(("register", "version must be 1"))
    if not isinstance(reg.get("org"), str) or not ORG_RE.match(reg["org"]):
        errors.append(("register", "org must be a GitHub login"))
    sas = reg.get("service_accounts")
    if sas is None:
        return []
    if not isinstance(sas, list):
        errors.append(("register", "service_accounts must be a list"))
        return []
    defaults = reg.get("defaults") if isinstance(reg.get("defaults"), dict) else {}
    out = []
    for e in sas:
        name = e.get("name") if isinstance(e, dict) else None
        who = name if isinstance(name, str) and name else "service_accounts"
        if not isinstance(e, dict):
            errors.append((who, "entry must be a mapping"))
            continue
        ok = True
        if not isinstance(name, str) or not SA_RE.match(name):
            errors.append((who, "name must be 6-30 chars, ^[a-z][a-z0-9-]*$, no trailing hyphen"))
            ok = False
        desc = e.get("description")
        if not isinstance(desc, str) or not desc.strip():
            errors.append((who, "description is required (what it is for, who owns it)"))
            ok = False
        elif len(desc) > 256:
            errors.append((who, "description is longer than 256 chars"))
            ok = False
        dn = e.get("display_name")
        if dn is not None and (not isinstance(dn, str) or len(dn) > 100):
            errors.append((who, "display_name must be a string of at most 100 chars"))
            ok = False
        mode = e.get("mode", defaults.get("mode", "report"))
        if mode not in ("report", "enforce"):
            errors.append((who, "mode must be report or enforce"))
            ok = False
        if ok:
            out.append((name, desc, dn, mode))
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

    errors = []
    entries = validate(reg, errors)
    if errors:
        for who, why in dict.fromkeys(errors):
            print("error: %s: %s" % (who, why), file=sys.stderr)
        return 1

    live = {s.get("name"): s for s in state.get("service_accounts") or []}
    out = []
    for name, desc, dn, mode in entries:
        if name not in live:
            d = {"name": name, "display_name": dn if dn is not None else name, "description": desc}
            out.append(act("create-service-account", d) if mode == "enforce"
                       else act("drift", dict(would="create-service-account", **d)))
            continue
        cur = live[name]
        mine = []
        for field, want in (("description", desc), ("display_name", dn)):
            if want is None or cur.get(field) == want:
                continue
            d = {"name": name, "field": field, "from": cur.get(field) or "", "to": want}
            mine.append(act("update-service-account", d) if mode == "enforce"
                        else act("drift", dict(would="update-service-account", **d)))
        out.extend(mine or [act("in-sync", {})])
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
