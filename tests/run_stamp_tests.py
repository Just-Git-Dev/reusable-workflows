#!/usr/bin/env python3
"""Self-test for scripts/stamp_version.py — the release-time version sweeper.

Why this exists: every release since v1.20.0 needed a manual `perl -pi` pass over
docs/ + README.md, which is exactly the chore that gets skipped — 39 example pins
once sat on twelve different tags. The sweep is now a script, so the script itself
needs the tests: a bad rewrite would silently corrupt 22 shipped workflows.

The text-level functions are pure (str -> str), so these run against fixtures in
memory; only the repo-wide scan touches disk, and it asserts against the real tree.

Usage:  python3 tests/run_stamp_tests.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import stamp_version as S  # noqa: E402

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}\n     got: {got!r}\n    want: {want!r}")
        print(f"  FAIL {label}")
    else:
        print(f"  ok   {label}")


# --------------------------------------------------------------------------
# stamping a workflow

UNSTAMPED = """\
name: Deploy (reusable)

on:
  workflow_call:
    inputs:
      service:
        type: string

jobs:
  deploy:
    runs-on: ubuntu-latest
"""

STAMPED = """\
name: Deploy (reusable)

on:
  workflow_call:
    inputs:
      service:
        type: string

env:
  # Stamped by scripts/stamp_version.py at release time; CI asserts it matches
  # the tag. A called workflow cannot discover its own ref at runtime.
  WORKFLOW_VERSION: v1.24.0

jobs:
  deploy:
    runs-on: ubuntu-latest
"""


def test_stamp_inserts_env_block():
    out, changed = S.stamp_workflow(UNSTAMPED, "v1.24.0")
    check("insert: produces the expected block", out, STAMPED)
    check("insert: reports a change", changed, True)
    check("insert: stamp is readable back", S.find_stamp(out), "v1.24.0")


def test_stamp_is_idempotent():
    out, changed = S.stamp_workflow(STAMPED, "v1.24.0")
    check("idempotent: text unchanged", out, STAMPED)
    check("idempotent: reports no change", changed, False)


def test_restamp_replaces_value_only():
    out, changed = S.stamp_workflow(STAMPED, "v1.25.0")
    check("restamp: reports a change", changed, True)
    check("restamp: new value", S.find_stamp(out), "v1.25.0")
    check("restamp: no duplicate env block", out.count("\nenv:\n"), 1)
    check("restamp: comment preserved", "Stamped by scripts/stamp_version.py" in out, True)


def test_stamp_uses_existing_env_block():
    text = "on:\n  workflow_call:\n\nenv:\n  FOO: bar\n\njobs:\n  a:\n    runs-on: x\n"
    out, changed = S.stamp_workflow(text, "v1.24.0")
    check("existing env: no second block", out.count("\nenv:\n"), 1)
    check("existing env: keeps FOO", "  FOO: bar\n" in out, True)
    check("existing env: stamped", S.find_stamp(out), "v1.24.0")
    check("existing env: reports a change", changed, True)


# --------------------------------------------------------------------------
# rewriting doc pins

DOC = """\
Pin an exact release:

```yaml
jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloud-run.yml@v1.22.0
    secrets: inherit
  ci:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-node.yml@v1.23.0
```

Third-party actions stay pinned to SHAs:
`uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`
and another org's reusable is not ours:
`uses: other-org/reusable-workflows/.github/workflows/ci-node.yml@v1.0.0`
"""


def test_bump_pins_rewrites_only_our_pins():
    out, n = S.bump_pins(DOC, "v1.24.0")
    check("pins: two rewritten", n, 2)
    check("pins: all ours now current", sorted(set(S.find_pins(out))), ["v1.24.0"])
    check(
        "pins: third-party SHA untouched",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in out,
        True,
    )
    check(
        "pins: another org untouched",
        "other-org/reusable-workflows/.github/workflows/ci-node.yml@v1.0.0" in out,
        True,
    )


def test_bump_pins_idempotent():
    once, _ = S.bump_pins(DOC, "v1.24.0")
    twice, n = S.bump_pins(once, "v1.24.0")
    check("pins: second pass is a no-op", twice, once)
    check("pins: second pass reports zero", n, 0)


def test_find_pins_ignores_v1_alias():
    # `v1` is a frozen legacy alias (CLAUDE.md); the sweep must not drag it forward,
    # or a doc that deliberately documents the alias would be rewritten every release.
    text = "uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v1\n"
    out, n = S.bump_pins(text, "v1.24.0")
    check("alias: v1 not rewritten", out, text)
    check("alias: reported as unchanged", n, 0)
    check("alias: not collected as a pin", S.find_pins(text), [])


# --------------------------------------------------------------------------
# version parsing / validation


def test_version_must_be_a_release_tag():
    for bad in ["1.24.0", "v1.24", "v1.24.0-rc1", "main"]:
        try:
            S.parse_version(bad)
            FAILURES.append(f"version: {bad!r} should have been rejected")
            print(f"  FAIL version: {bad!r} accepted")
        except SystemExit:
            print(f"  ok   version: {bad!r} rejected")
    check("version: v1.24.0 accepted", S.parse_version("v1.24.0"), "v1.24.0")


# --------------------------------------------------------------------------
# repo-wide consistency (the CI check, run against the real tree)


def test_repo_is_internally_consistent():
    report = S.scan(ROOT)
    check("repo: no disagreement", report.problems, [])
    check("repo: every reusable is stamped", report.unstamped, [])
    check("repo: one version across the tree", sorted(report.versions), [report.version])
    # Hand-maintained on purpose: deriving it from the same scan would make the
    # assertion a tautology. Bump it when a reusable is ADDED (22 as of
    # cleanup-secret-versions, 2026-08-16) — if it fails without one being added,
    # a workflow has silently stopped being stamped, which is the point.
    check("repo: stamped 22 reusables", len(report.stamps), 22)


def test_scan_flags_a_stale_pin(tmp_check=True):
    report = S.scan(ROOT)
    # Simulate a forgotten sweep: one doc left behind at the previous tag.
    stale = {**report.stamps}
    pins = {**report.pins, "docs/forgotten.md": ["v1.22.0"]}
    problems = S.reconcile(stamps=stale, pins=pins)
    check("stale pin: reported", any("forgotten.md" in p for p in problems), True)


def test_scan_flags_a_missing_stamp():
    report = S.scan(ROOT)
    stamps = {k: v for k, v in report.stamps.items()}
    stamps["\u200bmissing.yml"] = None
    problems = S.reconcile(stamps=stamps, pins=report.pins)
    check("missing stamp: reported", any("missing.yml" in p for p in problems), True)


def main():
    for fn in [
        test_stamp_inserts_env_block,
        test_stamp_is_idempotent,
        test_restamp_replaces_value_only,
        test_stamp_uses_existing_env_block,
        test_bump_pins_rewrites_only_our_pins,
        test_bump_pins_idempotent,
        test_find_pins_ignores_v1_alias,
        test_version_must_be_a_release_tag,
        test_repo_is_internally_consistent,
        test_scan_flags_a_stale_pin,
        test_scan_flags_a_missing_stamp,
    ]:
        print(f"{fn.__name__}:")
        fn()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nall stamp tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
