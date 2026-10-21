#!/usr/bin/env python3
"""Structural check: every variable a v4-touched step body reads is wired into that step.

run_body() in the other runners injects env straight into a body and never sees the YAML `env:`
block, so a body reading a variable its step never wires stays green there (v4 critic round 2,
finding 3: the refusal loop read DEPLOY_FLAGS / EXTRA that the Pin step never set). This runner
reads the YAML instead: for each run step of each v4 workflow, every `$VAR` / `${VAR}` the body
reads that the body itself does not assign must be in the step's, job's or workflow's `env:`, or
be a GitHub-provided default. Prints how many steps and reads it examined; fails on 0.

Usage:  python3 tests/run_step_env_wiring_tests.py
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
V4 = ["sync-bundle-key.yml", "rotate-signing-keypair.yml", "rotate-worker-signing-secret.yml",
      "deploy-cloud-run.yml", "cloud-run-update.yml", "rollback-service.yml",
      "distribute-env-secrets.yml", "deploy-env-lint.yml", "repos-environments.yml"]

SHELL_SPECIAL = {"HOME", "PATH", "PWD", "IFS", "RANDOM", "LINENO", "BASH_REMATCH", "BASH_SOURCE",
                 "OPTARG", "OPTIND", "REPLY", "TMPDIR", "USER", "SHELL", "CI", "UID"}
GH_PREFIX = ("GITHUB_", "RUNNER_")
# (workflow, step name) -> variables read on purpose without being wired, each with its reason.
OPTIONAL = {
    # `${BOOTSTRAP:-false}`: parity with the v3 keypair rotator; unset == false is asserted by
    # run_sync_v4_tests.py ("BOOTSTRAP unset (sync-bundle-key) behaves as false").
    ("sync-bundle-key.yml", "Force new Cloud Run revision(s)"): {"BOOTSTRAP"},
}

READ = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")


def strip_literals(body: str, keep_dq: bool = True) -> str:
    """Drop comments, quoted heredoc bodies and single-quoted strings: `$x` there is not shell.
    keep_dq=False also drops double-quoted text (but not $( ) code inside it): used to find
    assignments, so `echo "EXTRA=$EXTRA"` does not read as assigning EXTRA."""
    body = re.sub(r"(?ms)<<-?\s*'(\w+)'.*?^\s*\1\s*$", "", body)
    # Quote-state scanner. stack top: None (code) | "'" | '"' | "(" ($( ) command substitution,
    # which is code again, so quotes inside it nest properly).
    out, i, n, stack = [], 0, len(body), [None]
    while i < n:
        c, mode = body[i], stack[-1]
        if mode == "'":
            if c == "'":
                stack.pop(); out.append(" ")
        elif c == "\\":
            i += 1            # an escaped char (`\$x` is not a read) is dropped
        elif c == "$" and body[i + 1:i + 2] == "'" and mode is None:
            pass              # `$'...'` ANSI-C quote: drop the `$` so it does not glue to what follows
        elif c == "$" and body[i + 1:i + 2] == "(":
            stack.append("(")
            i += 1
        elif mode == '"':
            if c == '"':
                stack.pop(); out.append(" ")
            elif keep_dq:
                out.append(c)
        elif c in "'\"":
            stack.append(c)
        elif c == ")" and mode == "(":
            stack.pop()
        elif c == "#" and mode is None and (i == 0 or body[i - 1] in " \t\n"):
            while i < n and body[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def assigned(body: str) -> set:
    names = set(re.findall(r"(?<![\w$])([A-Za-z_]\w*)\+?=", body))
    names |= set(re.findall(r"\bfor\s+([A-Za-z_]\w*)\s+in\b", body))
    names |= set(re.findall(r"\b(?:local|declare|export)\s+(?:-\w+\s+)*([A-Za-z_]\w*)", body))
    for m in re.finditer(r"\bread\s+(?:-\w+\s+)*([A-Za-z_][\w ]*)", body):
        names |= set(m.group(1).split())
    return names


def unwired(body: str, wired: set) -> list:
    clean = strip_literals(body)
    ok = assigned(strip_literals(body, keep_dq=False)) | wired | SHELL_SPECIAL
    return sorted({v for v in READ.findall(clean)
                   if v not in ok and not v.startswith(GH_PREFIX)})


def selfcheck():
    """The reader must not be fooled by text that merely looks like an assignment (critic 3, V7)."""
    cases = [('echo "EXTRA=$EXTRA" >> "$GITHUB_OUTPUT"\n', ["EXTRA"]),
             ("echo 'X=1'; echo \"$X\"\n", ["X"]),
             ('X=1\necho "$X"\n', []),
             ('export Y="a"\necho "$Y"\n', []),
             ('FOO=$(echo "A=b")\necho "$FOO $A"\n', ["A"])]
    return [f"selfcheck {body!r}: got {unwired(body, set())}, want {want}"
            for body, want in cases if unwired(body, set()) != want]


def main():
    steps = reads = 0
    bad = selfcheck()
    per = {}
    for name in V4:
        per[name] = 0
        doc = yaml.safe_load((WF / name).read_text())
        top = set((doc.get("env") or {}))
        for jid, job in (doc.get("jobs") or {}).items():
            jenv = top | set((job.get("env") or {}))
            for i, st in enumerate(job.get("steps") or []):
                body = st.get("run")
                if not body:
                    continue
                steps += 1
                per[name] += 1
                wired = jenv | set((st.get("env") or {}))
                reads += len(READ.findall(strip_literals(body)))
                miss = [v for v in unwired(body, wired)
                        if v not in OPTIONAL.get((name, st.get("name")), ())]
                if miss:
                    bad.append(f"{name}:{jid}:'{st.get('name', i)}' reads unwired {miss}")
    print(f"examined {steps} run steps, {reads} variable reads in {len(V4)} workflows")
    if steps == 0:
        print("FAIL examined 0 steps")
        sys.exit(1)
    for name, n in per.items():
        if n == 0:
            bad.append(f"{name}: examined 0 run steps (a vacuous pass)")
    for b in bad:
        print("  FAIL", b)
    if bad:
        sys.exit(1)
    print("ok: every variable read is wired")


if __name__ == "__main__":
    main()
