#!/usr/bin/env python3
"""tool -> core contract: every operation the released tool vendors must still exist.

The tool generates its whole command tree from its vendored core spec at startup, so an
core release that drops (or re-methods) an operation silently breaks a command in a
binary already in users' hands. This compares (METHOD, path) pairs: every pair in the tool's
vendored spec must exist in the candidate core spec. Extra core operations are fine.

Generalised as `ops-subset`: the same subset test serves web -> gateway (web's vendored copy of
gateway's swagger must be a subset of the candidate gateway spec) where byte identity can never hold
for "web@live vs gateway@new". "tool"/"core" below read as consumer/provider.

Usage: ops_subset.py CLI_SPEC ISSUER_SPEC [--label X]     (JSON or YAML files)
Exit: 0 all present; 1 missing operation(s) or ZERO examined (a check that examined nothing
proves nothing); 2 usage / unreadable file / PyYAML missing for a YAML input.
PyYAML is imported lazily and only for YAML input (like tools/stepup-path-check/check.py).
"""

from __future__ import annotations

import json
import re
import sys

METHODS = ("get", "put", "post", "delete", "patch", "head", "options")


def _spec_loader(yaml):
    """SafeLoader with YAML 1.2 booleans: only true/false (any case), never on/off/yes/no.

    PyYAML follows YAML 1.1, where an unquoted `off` is False. JSON keeps "off" a string, so a
    JSON spec compared with a raw YAML one saw enum value "off" vanish: a false break.
    """
    class SpecLoader(yaml.SafeLoader):
        pass
    SpecLoader.yaml_implicit_resolvers = {
        first: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:bool"]
        for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    SpecLoader.add_implicit_resolver(
        "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
        list("tTfF"))
    return SpecLoader


def load(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        import yaml
    except ImportError:
        raise SystemExit(f"{path} is not JSON and PyYAML is not installed: "
                         "pip install pyyaml (needed to read YAML specs)")
    try:
        return yaml.load(text, Loader=_spec_loader(yaml))  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError as ex:  # unreadable = exit 2 at the callers, never a traceback's 1
        raise ValueError(f"{path} is neither JSON nor valid YAML: {ex}") from ex


def ops(spec):
    out = set()
    for path, item in ((spec or {}).get("paths") or {}).items():
        for m in (item or {}):
            if m.lower() in METHODS:
                out.add((m.upper(), path))
    return out


def main(argv):
    argv = list(argv)
    label = "ops-subset"
    if "--label" in argv:
        i = argv.index("--label")
        if i + 1 >= len(argv):
            print(__doc__, file=sys.stderr)
            return 2
        label = f"ops-subset[{argv[i + 1]}]"
        del argv[i:i + 2]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        consumer, provider = ops(load(argv[0])), ops(load(argv[1]))
    except (OSError, SystemExit, ValueError) as ex:
        print(f"{label}: {ex}", file=sys.stderr)
        return 2
    print(f"{label}: examined {len(consumer)} operation(s) vendored by the consumer")
    if not consumer:
        print("FAIL: examined 0 operations -- the consumer spec has no paths, nothing was checked")
        return 1
    missing = sorted(consumer - provider)
    for m, p in missing:
        print(f"MISSING in provider spec: {m} {p}")
    if missing:
        print(f"FAIL: {len(missing)} of {len(consumer)} operation(s) the consumer relies on "
              "are gone")
        return 1
    print("ok: every consumer operation exists in the candidate provider spec")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
