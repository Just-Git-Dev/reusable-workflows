#!/usr/bin/env python3
"""`ci.yml` and `make ci` must be the same set of checks, by construction.

Local checks used to be retyped by hand and drifted from `ci.yml` (in the sibling provisioning
repo four PR runs went red on 2026-10-19 for checks the local run skipped). The fix is one
definition per check: a make target. So every `run:` step in ci.yml must be `make <target>`
(CI-only plumbing, the pinned tool installers named `install pinned ...`, is the one named
exception), every such target must be listed in the Makefile's `CHECKS` (exactly what `make ci`
runs), and every CHECK must be called by ci.yml. The pinned tool versions in the installer steps
must equal the Makefile's, because `make tools` refuses a local tool of a different version.

Usage:  python3 tests/run_ci_make_tests.py     (PyYAML needed)
"""
import os
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CI_YML = os.path.join(ROOT, ".github", "workflows", "ci.yml")
MAKEFILE = os.path.join(ROOT, "Makefile")
PLUMBING_PREFIX = "install pinned "
MAKE_STEP = re.compile(r"make ([\w-]+)")


def run_steps():
    with open(CI_YML, encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    steps = [s for job in wf["jobs"].values() for s in job["steps"] if "run" in s]
    assert steps, "ci.yml has no run: steps; the parser is looking in the wrong place"
    return steps


def makefile_text():
    assert os.path.exists(MAKEFILE), "no Makefile: `make ci` does not exist yet"
    with open(MAKEFILE, encoding="utf-8") as fh:
        return fh.read()


def make_var(text, name):
    m = re.search(rf"^{name}\s*[:?]?=\s*(\S+)", text, re.M)
    assert m, f"Makefile does not define {name}"
    return m.group(1)


def checks(text):
    m = re.search(r"^CHECKS\s*:?=\s*((?:.*\\\n)*.*)$", text, re.M)
    assert m, "Makefile has no CHECKS list (the targets `make ci` runs)"
    return m.group(1).replace("\\\n", " ").split()


def targets_called():
    called = []
    for step in run_steps():
        name = step.get("name", "")
        body = step["run"].strip()
        m = MAKE_STEP.fullmatch(body)
        if m:
            called.append(m.group(1))
        elif not name.startswith(PLUMBING_PREFIX):
            raise AssertionError(
                f"ci.yml step {name or body.splitlines()[0]!r} is not `make <target>`; "
                "move the check into the Makefile (or name it 'install pinned ...' if it is "
                "only a pinned-tool installer)")
    return called


def test_every_check_step_is_a_make_target_listed_in_make_ci():
    text = makefile_text()
    listed = checks(text)
    called = targets_called()
    assert called, "no make steps found in ci.yml"
    missing = [t for t in called if t not in listed]
    assert not missing, f"ci.yml calls {missing}, which `make ci` does not run (CHECKS={listed})"
    for t in called:
        assert re.search(rf"^{re.escape(t)}\s*:", text, re.M), f"no Makefile target {t!r}"


def test_make_ci_runs_nothing_ci_does_not():
    extra = [t for t in checks(makefile_text()) if t not in targets_called()]
    assert not extra, f"`make ci` runs {extra}, which ci.yml never calls"


def test_pinned_tool_versions_match_the_makefile():
    text = makefile_text()
    with open(CI_YML, encoding="utf-8") as fh:
        raw = fh.read()
    for var, pat in (("SHELLCHECK_VERSION", r"SC_VERSION:\s*v{v}\b"),
                     ("ACTIONLINT_VERSION", r"AL_VERSION:\s*{v}\b"),
                     ("PROMTOOL_VERSION", r"PROM_VERSION:\s*{v}\b")):
        v = make_var(text, var)
        assert re.search(pat.format(v=re.escape(v)), raw), \
            f"ci.yml pin differs from Makefile {var}={v}"


def test_checker_catches_a_retyped_step():
    """Self-test: a raw command step is not a make step, and CHECKS parses continuations."""
    assert MAKE_STEP.fullmatch("python3 -m pytest tests/ -q") is None
    assert checks("CHECKS := a b \\\n  c\nfoo:\n") == ["a", "b", "c"]


def test_pinned_check_flags_a_mutable_ref_and_a_sha_passes():
    """The check ran as `grep -rnP`, which BSD grep lacks: locally it errored and passed."""
    script = os.path.join(ROOT, "scripts", "check_pinned_actions.py")
    with tempfile.TemporaryDirectory() as d:
        wf = os.path.join(d, "a.yml")

        def run(line):
            with open(wf, "w", encoding="utf-8") as fh:
                fh.write(f"jobs:\n  a:\n    steps:\n      {line}\n")
            return subprocess.run([sys.executable, script, d], capture_output=True, text=True)

        assert run("- uses: actions/checkout@v4").returncode == 1
        assert run("- uses: actions/checkout@" + "a" * 40 + " # v5").returncode == 0
        assert run("- uses: ./local-action").returncode == 1   # examined nothing third-party


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests, "no tests collected"
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
    print(f"ci make targets: {len(tests) - failed} of {len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
