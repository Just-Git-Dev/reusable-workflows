#!/usr/bin/env python3
"""Every reusable workflow must be documented and listed in the README.

The README asserts, in prose, "Each workflow has a `docs/<name>.md` page with its full
input/secret contract". That was false for three workflows — `bootstrap-dashboards`,
`cleanup-cloud-run-revisions` and `validate-alerts` shipped with no docs page and no README
row, so the only way to discover them was to list the directory.

Nothing caught it because every existing gate checks the *content* of things that are
already tracked: `gen_catalog.py --check` regenerates from the workflow files, so a new
workflow simply appears in `catalog.json` and looks fine. Absence from a hand-maintained
list is the failure mode a generator cannot see.

Exits non-zero listing every gap. `ci.yml` is this repo's own CI, not a reusable, so it is
excluded.
"""
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"
DOCS = REPO / "docs"
README = REPO / "README.md"

# Not a `workflow_call` reusable — this repo's own CI.
EXCLUDE = {"ci"}


def main():
    readme = README.read_text()
    problems = []

    names = sorted(p.stem for p in WORKFLOWS.glob("*.yml") if p.stem not in EXCLUDE)
    for name in names:
        if not (DOCS / f"{name}.md").is_file():
            problems.append(f"{name}: no docs/{name}.md")
        if f"docs/{name}.md" not in readme:
            problems.append(f"{name}: not linked from README.md")

    # And the reverse: a docs page whose workflow was deleted or renamed.
    for doc in sorted(DOCS.glob("*.md")):
        # Standalone guidance pages, not workflow references. They have no
        # corresponding .yml and never will.
        if doc.stem in {"PLATFORM", "convergence-audit", "release-process",
                        "TESTING-STANDARD"}:
            continue
        if not (WORKFLOWS / f"{doc.stem}.yml").is_file():
            problems.append(f"{doc.stem}: docs/{doc.stem}.md has no workflow")

    if problems:
        print("::error::workflow documentation is incomplete")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"All {len(names)} reusable workflows have a docs page and a README link.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
