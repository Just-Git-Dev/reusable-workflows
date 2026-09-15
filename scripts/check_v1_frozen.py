#!/usr/bin/env python3
"""Assert the `v1` legacy alias has NOT moved off its original commit.

`v1` is a **frozen** legacy alias, on purpose — it is not a moving pointer to
"the latest v1 release" the way GitHub Actions marketplace `v1` tags usually
work here. See README.md:137 ("frozen legacy alias ... does not track new
releases") and DECISIONS-ARCHIVE.md ("`v1` is frozen, not moved. Releases are
immutable.") — moving it onto a newer release was considered and rejected:
`deploy-cloudflare-pages.yml` didn't exist at `v1`, and a Cloud Run rollout
behaviour only warned instead of failing back then, so re-pointing `v1` would
silently hand all of its callers a breaking change they never asked for.

So the invariant worth protecting is the OPPOSITE of the usual "alias tracks
latest": **`v1` must never move.** The failure mode this guards against is
someone "helpfully" re-pointing `v1` at a newer tag to fix perceived drift —
that is a supply-chain-shaped change to consumers this repo does not control.

    python3 scripts/check_v1_frozen.py              # CI: v1 == FROZEN_COMMIT
    python3 scripts/check_v1_frozen.py --self-test  # proves the check can fail

Fails loudly, never skips. If `v1` is missing or cannot be resolved, that is a
failure too — not a clean bill of health — because the check could not
actually run. A gate that goes green vacuously is the companion failure to a
gate that fires and is ignored (see TODO.md).
"""
from __future__ import annotations

import subprocess
import sys

ALIAS = "v1"

# The commit `v1` has pointed at since the very first release, and must keep
# pointing at forever. Authority: DECISIONS-ARCHIVE.md ("v1 is frozen, not
# moved... So v1 stays pinned at the first release as a legacy caller") and
# DECISIONS.md ("v1 resolves to b96d0e3, the original 5-workflow commit").
# Do NOT "fix" this constant to match wherever `v1` currently resolves —
# if this check is failing, `v1` moved and THAT is the bug, not this line.
FROZEN_COMMIT = "b96d0e38e866946ac42d2a5e1fc2c885c058544c"


# ---------------------------------------------------------------------------
# pure logic (no subprocess) — this is what --self-test exercises directly


def verdict(alias_exists: bool, alias_commit: str | None) -> list[str]:
    """Problems found, if any. Empty list means `v1` is still frozen where it
    should be.

    Every failure path is an explicit, named problem — there is no branch
    that silently returns [] because a precondition could not be checked.
    """
    problems = []
    if not alias_exists:
        problems.append(f"`{ALIAS}` tag does not exist in this repo")
    elif alias_commit is None:
        problems.append(f"`{ALIAS}` exists but could not be resolved to a commit")
    elif alias_commit != FROZEN_COMMIT:
        problems.append(
            f"`{ALIAS}` now resolves to `{alias_commit}`, but it must stay frozen "
            f"at `{FROZEN_COMMIT}` — this is almost certainly someone re-pointing "
            f"`{ALIAS}` onto a newer release. `{ALIAS}` is frozen ON PURPOSE "
            "(see README.md#versioning and DECISIONS-ARCHIVE.md): moving it would "
            "silently hand every legacy `@v1` caller a different, unreviewed input "
            "contract. The fix is to re-point the tag BACK to the frozen commit "
            f"(`{FROZEN_COMMIT}`), not to update this check."
        )
    return problems


# ---------------------------------------------------------------------------
# git plumbing seam — thin enough that the logic above never has to touch it


class Git:
    def tag_exists(self, tag: str) -> bool:
        proc = subprocess.run(
            ["git", "tag", "-l", tag], capture_output=True, text=True, check=True
        )
        return proc.stdout.strip() == tag

    def resolve(self, ref: str) -> str | None:
        """Commit SHA a tag points at, peeling annotated tags. None if absent."""
        proc = subprocess.run(
            ["git", "rev-list", "-n", "1", ref],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None


# ---------------------------------------------------------------------------
# entry points


def check(git: Git) -> int:
    alias_exists = git.tag_exists(ALIAS)
    alias_commit = git.resolve(ALIAS) if alias_exists else None

    problems = verdict(alias_exists, alias_commit)
    if problems:
        print(f"::error::`{ALIAS}` frozen-alias check failed")
        for p in problems:
            print(f"  {p}")
        return 1

    print(f"`{ALIAS}` is still frozen at `{FROZEN_COMMIT}`, as intended.")
    return 0


def self_test() -> int:
    """Construct the moved case in-process and assert the checker rejects it.

    No real git repo, no real tags — `verdict()` is pure, so every branch of
    the checker's decision is asserted directly against fabricated inputs.
    This is what proves the gate can actually fail, not just pass.
    """
    failures = []

    def expect(name: str, problems: list[str], *, should_fail: bool) -> None:
        got_fail = bool(problems)
        if got_fail != should_fail:
            failures.append(
                f"{name}: expected {'a failure' if should_fail else 'no failure'}, "
                f"got {problems!r}"
            )

    # Frozen where it should be: no complaint.
    expect(
        "frozen alias",
        verdict(True, FROZEN_COMMIT),
        should_fail=False,
    )

    # Moved: v1 exists but now points somewhere else — the exact scenario
    # ("helpfully fixing the drift") this script exists to catch.
    expect(
        "moved alias",
        verdict(True, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
        should_fail=True,
    )

    # Missing alias entirely.
    expect(
        "missing v1 tag",
        verdict(False, None),
        should_fail=True,
    )

    # Exists but unresolvable (e.g. a broken/dangling ref) — must fail, not
    # pass vacuously, per the "fail loudly, never skip" rule.
    expect(
        "unresolvable v1 tag",
        verdict(True, None),
        should_fail=True,
    )

    if failures:
        print("::error::--self-test FAILED — the checker is not trustworthy")
        for f in failures:
            print(f"  {f}")
        return 1

    print("--self-test passed: the checker correctly rejects a moved alias.")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args == ["--self-test"]:
        return self_test()
    if args:
        raise SystemExit(f"usage: {argv[0]} [--self-test]")
    return check(Git())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
