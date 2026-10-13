#!/usr/bin/env python3
"""Runs the release-flow CLI's unit tests and, when present, the workflow-shape tests.

Stdlib unittest discovery over actions/release-flow/releaseflow (test_*.py) and over
tests/release_flow_workflows/ (if that directory exists). Prints the count and exits
non-zero on any failure, any skip, or zero tests run.

Usage:  python3 tests/run_release_flow_tests.py
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
DIRS = [ROOT / "actions" / "release-flow" / "releaseflow",
        ROOT / "tests" / "release_flow_workflows"]


def main():
    suite = unittest.TestSuite()
    examined = []
    for d in DIRS:
        if d.is_dir():
            # top_level_dir = d so the modules import each other as plain names.
            suite.addTests(unittest.defaultTestLoader.discover(
                str(d), pattern="test_*.py", top_level_dir=str(d)))
            examined.append(str(d.relative_to(ROOT)))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    n = result.testsRun
    print(f"release-flow tests: ran {n} in {', '.join(examined) or 'no directory'}; "
          f"{len(result.failures)} failure(s), {len(result.errors)} error(s), "
          f"{len(result.skipped)} skipped")
    if n == 0:
        print("::error::0 tests ran")
        return 1
    if result.failures or result.errors or result.skipped:
        return 1
    print(f"All {n} release-flow tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
