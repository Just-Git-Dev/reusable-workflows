#!/usr/bin/env python3
"""Extract every complete example workflow from the docs into OUT_DIR, for actionlint.

Every ```yaml block in docs/ and README.md that looks like a complete workflow (has a top-level
`jobs:` and `on:`) is written to OUT_DIR/.github/workflows/<doc>-<n>.yml. This was an inline
heredoc in ci.yml; it lives here so `make doc-examples` runs the same code on a laptop.
Fails when it extracts none, so a broken extractor cannot go green.

Usage: extract_doc_examples.py OUT_DIR
"""
import pathlib
import re
import sys


def main(argv):
    out = pathlib.Path(argv[1]) / ".github" / "workflows"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for md in sorted(pathlib.Path("docs").glob("*.md")) + [pathlib.Path("README.md")]:
        for i, block in enumerate(re.findall(r"```yaml\n(.*?)```", md.read_text(), re.S)):
            # A complete workflow has jobs and a trigger; fragments ("with:" only) do not.
            if re.search(r"^jobs:", block, re.M) and re.search(r"^on:", block, re.M):
                (out / f"{md.stem}-{i}.yml").write_text(block)
                n += 1
    print(f"extracted {n} complete example workflow(s)")
    if n == 0:
        print("::error::no complete examples found — the extractor is broken")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
