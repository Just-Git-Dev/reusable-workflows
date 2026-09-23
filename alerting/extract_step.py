#!/usr/bin/env python3
"""Print the `run:` body of a named step in a workflow file, for another workflow to execute.

service-alerts.yml reuses validate-alerts' lint and PromQL bodies and bootstrap-alerts' channel
and apply bodies by running them verbatim, from the same commit it was itself called at — one
parser and one applier, not a copy that drifts (TESTING-STANDARD Principle 11). It cannot call
those workflows directly: a `./` reference inside a called workflow resolves in the CALLER's
repository (DECISIONS 2026-09-15), and a pinned `owner/repo/...@tag` would pin the wrong commit
on a PR branch.

A body containing a `${{ }}` expression is refused: GitHub would have evaluated it before the
shell saw it, and here nothing will, so the body would run with a literal `${{ ... }}` in it.

    python3 extract_step.py WORKFLOW JOB "Step name" > body.sh
"""
import sys

import yaml


def main(argv):
    if len(argv) != 4:
        print("usage: extract_step.py WORKFLOW JOB STEP_NAME", file=sys.stderr)
        return 2
    path, job, name = argv[1:]
    doc = yaml.safe_load(open(path))
    steps = ((doc.get("jobs") or {}).get(job) or {}).get("steps") or []
    matches = [s for s in steps if s.get("name") == name]
    if len(matches) != 1:
        print(f"{path}: expected exactly one step {name!r} in job {job!r}, found {len(matches)}",
              file=sys.stderr)
        return 1
    body = matches[0].get("run")
    if not body:
        print(f"{path}: step {name!r} has no run: body", file=sys.stderr)
        return 1
    if "${{" in body:
        print(f"{path}: step {name!r} contains a ${{{{ }}}} expression; it can only run inside "
              "its own workflow", file=sys.stderr)
        return 1
    sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
