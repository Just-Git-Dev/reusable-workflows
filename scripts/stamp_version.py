#!/usr/bin/env python3
"""Sweep the repo to a release version: doc example pins AND in-workflow stamps.

Two chores used to be manual, and both are the kind that get skipped:

1. **Doc example pins.** Every release since v1.20.0 needed a hand-rolled
   `perl -pi` over `docs/` + `README.md`. Skipping it is how 39 example pins
   ended up spread across twelve different tags.
2. **The version stamp.** A called workflow cannot discover which version of
   *itself* is running — a probe on 2026-08-11 confirmed `GITHUB_WORKFLOW_REF`
   and `GITHUB_WORKFLOW_SHA` describe the *caller*, and the `github` context has
   no `job_workflow_sha` key at all. So the version has to be baked in at
   release time; `WORKFLOW_VERSION` in each reusable's top-level `env:` is that
   bake. It is what lets a workflow tell its caller it is out of date.

Both are now one sweep, verified two ways so neither can be forgotten:

    python3 scripts/stamp_version.py v1.24.0   # sweep pins + stamps to a tag
    python3 scripts/stamp_version.py --check   # CI: everything agrees (any version)
    python3 scripts/stamp_version.py --check --expect v1.24.0   # tag push: agrees WITH the tag

`--check` runs on every PR and only asserts *internal* agreement, so an unrelated
PR never fails just because a release happened. `--expect` runs on tag push, where
a disagreement means the sweep was skipped before cutting the tag — the exact
failure this script exists to prevent, caught at the only moment it matters.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# `v1` (no minor/patch) is a frozen legacy alias — a doc that mentions it means it,
# so the sweep must not drag it forward. Only full vX.Y.Z pins are swept.
PIN_RE = re.compile(
    r"(Just-Git-Dev/reusable-workflows/\.github/workflows/[A-Za-z0-9._-]+\.yml@)"
    r"(v\d+\.\d+\.\d+)\b"
)
VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
STAMP_RE = re.compile(r"^(?P<indent>[ \t]+)WORKFLOW_VERSION:[ \t]*(?P<version>\S+)[ \t]*$", re.M)

STAMP_COMMENT = (
    "  # Stamped by scripts/stamp_version.py at release time; CI asserts it matches\n"
    "  # the tag. A called workflow cannot discover its own ref at runtime.\n"
)


def parse_version(raw: str) -> str:
    """Accept only a full release tag — the thing consumers are told to pin."""
    if not VERSION_RE.match(raw):
        raise SystemExit(
            f"::error::'{raw}' is not a release tag. Expected vMAJOR.MINOR.PATCH (e.g. v1.24.0)."
        )
    return raw


# ---------------------------------------------------------------------------
# text-level rewrites (pure, so the tests can drive them without touching disk)


def find_pins(text: str) -> list[str]:
    return [m.group(2) for m in PIN_RE.finditer(text)]


def bump_pins(text: str, version: str) -> tuple[str, int]:
    """Rewrite every full-version pin of OUR reusables to `version`."""
    changed = 0

    def sub(m: re.Match) -> str:
        nonlocal changed
        if m.group(2) != version:
            changed += 1
        return m.group(1) + version

    return PIN_RE.sub(sub, text), changed


def find_stamp(text: str) -> str | None:
    m = STAMP_RE.search(text)
    return m.group("version") if m else None


def stamp_workflow(text: str, version: str) -> tuple[str, bool]:
    """Set `WORKFLOW_VERSION` in the workflow's top-level `env:`, adding it if absent."""
    current = find_stamp(text)
    if current == version:
        return text, False
    if current is not None:
        return STAMP_RE.sub(lambda m: f"{m.group('indent')}WORKFLOW_VERSION: {version}", text, count=1), True

    # No stamp yet. Prefer an existing top-level `env:`; otherwise open one
    # immediately before `jobs:`, which every workflow here has exactly once.
    env_line = re.search(r"^env:[ \t]*$", text, re.M)
    if env_line:
        at = env_line.end() + 1
        return text[:at] + f"  WORKFLOW_VERSION: {version}\n" + text[at:], True

    jobs_line = re.search(r"^jobs:[ \t]*$", text, re.M)
    if not jobs_line:
        raise SystemExit("::error::workflow has neither a top-level `env:` nor a `jobs:` block")
    at = jobs_line.start()
    block = f"env:\n{STAMP_COMMENT}  WORKFLOW_VERSION: {version}\n\n"
    return text[:at] + block + text[at:], True


# ---------------------------------------------------------------------------
# repo-wide scan


def reusables() -> list[Path]:
    """Workflows this repo publishes — `ci.yml` is our own CI, not a product."""
    return [p for p in sorted(WORKFLOWS.glob("*.yml")) if "workflow_call:" in p.read_text()]


def doc_files(root: Path) -> list[Path]:
    docs = sorted((root / "docs").glob("*.md"))
    for extra in ("README.md", "AGENTS.md"):
        p = root / extra
        if p.exists():
            docs.append(p)
    return docs


@dataclass
class Report:
    stamps: dict[str, str | None] = field(default_factory=dict)
    pins: dict[str, list[str]] = field(default_factory=dict)
    version: str | None = None
    versions: set[str] = field(default_factory=set)
    unstamped: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def consensus(stamps: dict[str, str | None], pins: dict[str, list[str]]) -> str | None:
    """The version the repo is *supposed* to be at: the most common stamp, then pin."""
    counts = Counter(v for v in stamps.values() if v) or Counter(
        v for vs in pins.values() for v in vs
    )
    return counts.most_common(1)[0][0] if counts else None


def reconcile(stamps: dict[str, str | None], pins: dict[str, list[str]]) -> list[str]:
    """Every stamp and every doc pin must name the same version. Report those that don't."""
    want = consensus(stamps, pins)
    problems = []
    if want is None:
        return ["nothing to check — no stamps and no pins found (the scan is broken)"]
    for name, got in sorted(stamps.items()):
        if got is None:
            problems.append(f"{name}: no WORKFLOW_VERSION stamp")
        elif got != want:
            problems.append(f"{name}: stamped {got}, expected {want}")
    for name, got in sorted(pins.items()):
        for stale in sorted({v for v in got if v != want}):
            problems.append(f"{name}: example pinned to {stale}, expected {want}")
    return problems


def scan(root: Path) -> Report:
    report = Report()
    for path in reusables():
        report.stamps[_rel(path, root)] = find_stamp(path.read_text())
    for path in doc_files(root):
        found = find_pins(path.read_text())
        if found:
            report.pins[_rel(path, root)] = found

    report.version = consensus(report.stamps, report.pins)
    report.versions = {v for v in report.stamps.values() if v} | {
        v for vs in report.pins.values() for v in vs
    }
    report.unstamped = [n for n, v in sorted(report.stamps.items()) if v is None]
    report.problems = reconcile(report.stamps, report.pins)
    return report


# ---------------------------------------------------------------------------
# entry points


def sweep(version: str) -> int:
    touched = 0
    for path in reusables():
        text = path.read_text()
        new, changed = stamp_workflow(text, version)
        if changed:
            path.write_text(new)
            touched += 1
            print(f"  stamped {_rel(path, ROOT)}")
    pins = 0
    for path in doc_files(ROOT):
        text = path.read_text()
        new, n = bump_pins(text, version)
        if n:
            path.write_text(new)
            pins += n
            print(f"  bumped  {_rel(path, ROOT)} ({n} pin{'s' if n > 1 else ''})")
    print(f"\nswept to {version}: {touched} workflow stamp(s), {pins} doc pin(s)")
    return 0


def check(expect: str | None) -> int:
    report = scan(ROOT)
    if report.problems:
        print(f"::error::version sweep is stale — run: python3 scripts/stamp_version.py {report.version}")
        for p in report.problems:
            print(f"  {p}")
        return 1
    if expect and report.version != expect:
        print(
            f"::error::repo is swept to {report.version} but the tag being released is {expect}. "
            f"Run `python3 scripts/stamp_version.py {expect}` and merge that before tagging."
        )
        return 1
    print(
        f"version sweep is consistent at {report.version} "
        f"({len(report.stamps)} workflows, {sum(len(v) for v in report.pins.values())} doc pins)"
    )
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    expect = None
    if "--expect" in args:
        i = args.index("--expect")
        if i + 1 >= len(args):
            raise SystemExit("::error::--expect needs a version")
        expect = parse_version(args[i + 1])
        del args[i : i + 2]
    if "--check" in args:
        args.remove("--check")
        if args:
            raise SystemExit(f"::error::unexpected argument(s) with --check: {' '.join(args)}")
        return check(expect)
    if len(args) != 1:
        raise SystemExit("usage: stamp_version.py <vX.Y.Z> | --check [--expect <vX.Y.Z>]")
    return sweep(parse_version(args[0]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
