#!/usr/bin/env python3
"""Extract a named step's `run:` body out of a workflow file, verbatim.

Used by pin_gate_behaviour.sh so that the behavioural test executes the gate
THE REPO ACTUALLY SHIPS, rather than a copy of the gate pasted into the test.
A test carrying its own copy of the logic passes even when the repo's copy is
broken — which is the whole failure mode the pin gate audit was chasing.

Deliberately stdlib-only (no PyYAML): this runs on whatever python3 the laptop
has, and a missing dependency here would degrade into a skip, which is the
other way a check goes quietly inert.

  usage: pin_gate_extract.py <workflow.yml> <step name>
  stdout: the dedented run: body.  exit 2 if the step or its run: is absent.
"""
import re
import sys


def extract(text: str, step_name: str) -> str | None:
    lines = text.splitlines()
    # Find `- name: <step name>`, tolerating quoting around the value.
    name_re = re.compile(
        r"^(\s*)-\s+name:\s*['\"]?" + re.escape(step_name) + r"['\"]?\s*$"
    )
    start = None
    for i, line in enumerate(lines):
        m = name_re.match(line)
        if m:
            start, item_indent = i, len(m.group(1))
            break
    if start is None:
        return None

    # Within this list item, find `run: |` (or |- / |+ / >).
    run_re = re.compile(r"^(\s*)run:\s*[|>][-+]?\s*$")
    body_start = None
    for i in range(start + 1, len(lines)):
        line = lines[i]
        # A new list item at the same indent ends this step.
        if re.match(r"^\s{0,%d}-\s" % item_indent, line) and i != start:
            break
        m = run_re.match(line)
        if m:
            body_start, key_indent = i + 1, len(m.group(1))
            break
    if body_start is None:
        return None

    # The block scalar runs until a line that is non-blank and indented at or
    # below the `run:` key itself.
    body = []
    for line in lines[body_start:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= key_indent:
            break
        body.append(line)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        return None

    indent = min(
        (len(ln) - len(ln.lstrip())) for ln in body if ln.strip()
    )
    return "\n".join(ln[indent:] if ln.strip() else "" for ln in body) + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    path, step = sys.argv[1], sys.argv[2]
    with open(path, encoding="utf-8") as fh:
        out = extract(fh.read(), step)
    if out is None:
        print(f"no `run:` body for step {step!r} in {path}", file=sys.stderr)
        return 2
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
