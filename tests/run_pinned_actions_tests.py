#!/usr/bin/env python3
"""Cases for scripts/check_pinned_actions.py: third-party refs need a SHA; this repo's own
composite actions may be pinned to an exact vX.Y.Z tag (owner ruling 5, 2026-10-21), because a
wrapper workflow cannot SHA-pin an action that first exists in its own release commit."""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_pinned_actions.py"
SHA = "a" * 40

CASES = [
    # (name, uses line, expected rc)
    ("third-party SHA passes", f"uses: actions/checkout@{SHA} # v5.0.0", 0),
    ("third-party tag fails", "uses: actions/checkout@v5", 1),
    ("own action exact tag passes",
     "uses: Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@v4.1.0", 0),
    ("own action SHA passes",
     f"uses: Just-Git-Dev/reusable-workflows/actions/check-release-gate@{SHA} # v3.7.0", 0),
    ("own action partial tag fails",
     "uses: Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@v4", 1),
    ("own action branch fails",
     "uses: Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@main", 1),
    ("own action pre-release tag fails",
     "uses: Just-Git-Dev/reusable-workflows/actions/sync-bundle-key@v4.1.0-rc1", 1),
    ("own reusable WORKFLOW tag still fails (only actions/ are exempt)",
     "uses: Just-Git-Dev/reusable-workflows/.github/workflows/x.yml@v4.1.0", 1),
    ("dot-dot action name fails",
     "uses: Just-Git-Dev/reusable-workflows/actions/..@v4.1.0", 1),
    ("look-alike org fails",
     "uses: Just-Git-Dev-evil/reusable-workflows/actions/sync-bundle-key@v4.1.0", 1),
]


def run(line):
    with tempfile.TemporaryDirectory(dir=ROOT / ".scratch" if (ROOT / ".scratch").is_dir() else None) as d:
        p = pathlib.Path(d) / "w.yml"
        p.write_text(f"jobs:\n  j:\n    steps:\n      - {line}\n", encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), d], capture_output=True, text=True)


def main():
    failed = 0
    for name, line, want in CASES:
        r = run(line)
        ok = r.returncode == want
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name} (rc={r.returncode}, want {want})")
    print(f"{len(CASES)} cases ran, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
