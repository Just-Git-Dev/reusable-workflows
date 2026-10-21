#!/usr/bin/env python3
"""Reject `uses: owner/repo@ref` where ref is not a 40-char hex SHA, under the given dirs.

This was an inline `grep -rnP` in ci.yml. BSD grep (macOS) has no -P, so the same line run
locally errored and the step still reported success; a regex in Python behaves identically
on every machine. Local (`./...`) refs are excluded by `[^./]`. Prints how many files and
`uses:` lines it examined and fails when it examined none.

Usage: check_pinned_actions.py [DIR ...]   (default: .github/workflows actions)
"""
import pathlib
import re
import sys

USES = re.compile(r'^\s*(-\s*)?uses:\s*(?P<target>[^./][^@]+)@(?P<ref>\S*)')
SHA = re.compile(r'[0-9a-f]{40}\s*($|#)')
# This repo's own composite actions may be pinned to an exact release tag (owner ruling,
# 2026-10-21): a wrapper workflow cannot SHA-pin an action that first exists in its own release
# commit, and stamp_version.py sweeps this exact form at release. Nothing looser is exempt.
OWN_ACTION = re.compile(r'Just-Git-Dev/reusable-workflows/actions/[A-Za-z0-9][A-Za-z0-9._-]*$')
OWN_TAG = re.compile(r'v\d+\.\d+\.\d+\s*($|#)')


def main(argv):
    roots = [pathlib.Path(a) for a in (argv[1:] or [".github/workflows", "actions"])]
    missing = [str(r) for r in roots if not r.exists()]
    if missing:
        print(f"::error::path(s) not found: {', '.join(missing)}; a missing root must not pass silently")
        return 1
    files = []
    for root in roots:
        files += list(root.rglob("*.yml")) + list(root.rglob("*.yaml"))
    files.sort()
    bad, uses = [], 0
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            m = USES.match(line)
            if not m:
                continue
            uses += 1
            ref = line[m.start("ref"):]
            if OWN_ACTION.match(m.group("target")) and OWN_TAG.match(ref):
                continue
            if not SHA.match(ref):
                bad.append(f"{f}:{n}:{line.strip()}")
    if not files or not uses:
        print(f"::error::examined {len(files)} files / {uses} uses: lines under "
              f"{', '.join(map(str, roots))}; expected some")
        return 1
    if bad:
        print("\n".join(bad))
        print("::error::Third-party actions must be pinned to a full commit SHA.")
        return 1
    print(f"All third-party action references are SHA-pinned "
          f"(examined {uses} uses: lines in {len(files)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
