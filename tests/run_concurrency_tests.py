#!/usr/bin/env python3
"""Assert that workflows mutating the same resource share a concurrency group.

Why this exists: `sync-bundle-key`, `rotate-signing-keypair` and
`rotate-worker-signing-secret` all read-modify-write the SAME `app-secrets`
bundle — read the latest version, patch one or two keys, add a new version.
They shipped with three different `concurrency:` group prefixes, so two of them
could run at once, both read version N, and the second write would silently drop
the first one's keys. Nothing fails; the lost key is discovered later by whatever
stops verifying signatures.

A group key is a string, so the only mechanical check that means anything is that
the three strings are IDENTICAL — a prefix that "looks the same" is a different
lock. Hence a string equality assertion, not a regex.

Scope of the guarantee: GitHub scopes a concurrency group to the repository that
declares it, which for a `workflow_call` reusable is the CALLER's repo. Two
different caller repos writing the same bundle are still not serialised — that
is a property of the platform, not something this test can assert away.

Usage:  python3 tests/run_concurrency_tests.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# The three writers of the app-secrets bundle. Add a workflow here the moment it
# grows a write path into the same blob.
BUNDLE_WRITERS = [
    "sync-bundle-key.yml",
    "rotate-signing-keypair.yml",
    "rotate-worker-signing-secret.yml",
]

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}\n     got: {got!r}\n    want: {want!r}")
        print(f"  FAIL {label}")
    else:
        print(f"  ok   {label}")


def _concurrency_block(name):
    """The top-level `concurrency:` mapping as {key: verbatim value}.

    Hand-parsed rather than via PyYAML so the tests keep running on a bare
    python3 (CI installs nothing), and comment lines inside the block are
    skipped — the block carries a long explanatory comment on purpose.
    """
    out = {}
    inside = False
    for line in (WORKFLOWS / name).read_text().splitlines():
        if line == "concurrency:":
            inside = True
            continue
        if not inside:
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):  # dedented back to a top-level key
            break
        k, _, v = line.strip().partition(":")
        out[k] = v.strip()
    return out


def group_of(name):
    """The top-level `concurrency: group:` expression, verbatim."""
    return _concurrency_block(name).get("group")


def cancel_in_progress_of(name):
    return _concurrency_block(name).get("cancel-in-progress")


def test_every_bundle_writer_declares_a_group():
    for name in BUNDLE_WRITERS:
        check(f"{name}: declares concurrency.group", group_of(name) is not None, True)


def test_bundle_writers_share_one_group():
    groups = {name: group_of(name) for name in BUNDLE_WRITERS}
    # Guard against the assertion passing vacuously if every parse returned None.
    check("every writer parsed a group", all(groups.values()), True)
    distinct = sorted(set(groups.values()))
    check(
        "the three bundle writers hold ONE lock",
        distinct,
        [groups[BUNDLE_WRITERS[0]]],
    )


def test_the_group_is_keyed_on_the_blob_not_the_key():
    # `bundle_key` names one entry inside the bundle; two runs patching different
    # keys still collide on the whole-blob read-modify-write, so the key must not
    # appear in the lock or the lock is per-key and useless.
    group = group_of(BUNDLE_WRITERS[0])
    check("group is keyed on gcp_project", "inputs.gcp_project" in (group or ""), True)
    check("group is keyed on bundle_secret", "inputs.bundle_secret" in (group or ""), True)
    check("group is NOT keyed on bundle_key", "inputs.bundle_key" in (group or ""), False)


def test_writers_never_cancel_each_other():
    # A cancelled writer can have already added a version; cancellation mid-write
    # is a worse outcome than queueing behind one.
    for name in BUNDLE_WRITERS:
        check(f"{name}: cancel-in-progress false", cancel_in_progress_of(name), "false")


def main():
    for fn in [
        test_every_bundle_writer_declares_a_group,
        test_bundle_writers_share_one_group,
        test_the_group_is_keyed_on_the_blob_not_the_key,
        test_writers_never_cancel_each_other,
    ]:
        print(f"{fn.__name__}:")
        fn()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nall concurrency tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
