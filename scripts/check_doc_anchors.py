#!/usr/bin/env python3
"""Every in-page `#anchor` link in a Markdown doc must resolve to a heading in that file.

The `DECISIONS.md` index is hand-maintained, and 17 of its 58 links pointed at nothing: the
anchors collapsed the two spaces GitHub leaves behind when it strips an em dash, so
`## 2026-08-11 — Private npm…` (anchor `2026-08-11--private-npm…`) was indexed as
`#2026-08-11-private-npm…`. Both conventions coexisted in the file for a month.

Nothing caught it because a dead in-page anchor fails silently — the browser simply stays
put — and `check_docs_coverage.py` checks that pages exist, not that links into them work.

GitHub's anchor algorithm, as implemented here: render markdown links to their text,
lowercase, delete every character outside [\\w\\s-], then map each remaining space to a
hyphen. It does NOT collapse runs of whitespace; that is the whole bug.

Exits non-zero listing every unresolved link.
"""
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DOCS = ["DECISIONS.md", "DECISIONS-ARCHIVE.md", "TODO.md", "TODO-ARCHIVE.md", "README.md"]


def render(text):
    """A markdown link contributes its TEXT to the heading, never its URL."""
    return re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)


def anchor(heading):
    return re.sub(r'[^\w\s-]', '', render(heading).lower()).strip().replace(' ', '-')


def check(path):
    lines = path.read_text().splitlines()
    heads, seen = set(), {}
    for line in lines:
        m = re.match(r'^#{1,6}\s+(.*)', line)
        if not m:
            continue
        a = anchor(m.group(1).strip())
        # GitHub disambiguates a repeated anchor by appending -1, -2, ...
        n = seen.get(a, 0)
        seen[a] = n + 1
        heads.add(a if n == 0 else f"{a}-{n}")
    bad = []
    for i, line in enumerate(lines, 1):
        for m in re.finditer(r'\]\(#([^)]+)\)', line):
            if m.group(1) not in heads:
                bad.append((i, m.group(1)))
    return bad


def main():
    failures = 0
    for name in DOCS:
        path = REPO / name
        if not path.exists():
            continue
        bad = check(path)
        if bad:
            failures += len(bad)
            print(f"{name}: {len(bad)} unresolved anchor link(s)")
            for i, a in bad:
                print(f"  {name}:{i} -> #{a}")
    if failures:
        print(f"\n{failures} unresolved anchor link(s). "
              f"Regenerate each index anchor from its own heading.")
        return 1
    print("all in-page anchor links resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
