#!/usr/bin/env python3
"""Report caller repos pinned to stale or mutable refs of these reusable workflows.

Why: nothing detects a caller falling behind. The 2026-07-27 sweep found 18 of 27 caller
lines stranded six-plus releases back, and only because someone read check-run annotations
by hand. On 2026-08-11, five separate problems — a broken example, an EOL Node default, a
false retention invariant — were all found by a human noticing. This closes that loop.

Two failure modes are reported:
  * STALE   — pinned to a release older than the newest by more than `--max-minors-behind`
  * MUTABLE — pinned to a branch or a moving alias (`@main`, `@v1`), so the caller is
              running whatever that ref points at today

The org list comes from `fleet.json`, deliberately committed rather than typed at the call
site: the first manual sweep silently omitted an entire org.

    python3 scripts/fleet_drift.py                 # human table
    python3 scripts/fleet_drift.py --format md     # job-summary markdown
    python3 scripts/fleet_drift.py --json          # machine-readable
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLEET = ROOT / "fleet.json"
SELF = "Just-Git-Dev/reusable-workflows"

USES = re.compile(
    r"Just-Git-Dev/reusable-workflows/\.github/workflows/([a-z0-9-]+)\.yml@([A-Za-z0-9._/-]+)"
)
SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class GH:
    """Thin `gh api` seam so tests can substitute canned responses."""

    def api(self, path: str, jq: str | None = None, raw: bool = False) -> str:
        cmd = ["gh", "api", path]
        if raw:
            # Without this the contents API returns JSON with base64 content and the
            # `uses:` regex silently matches nothing — which once made this tool report
            # "all clear" after scanning zero bytes. See the zero-findings guard below.
            cmd += ["-H", "Accept: application/vnd.github.raw"]
        if jq:
            cmd += ["--jq", jq]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            # A repo with no .github/workflows 404s; that is a normal answer, not a fault.
            if "Not Found" in proc.stderr:
                return ""
            raise RuntimeError(f"gh api {path} failed: {proc.stderr.strip()}")
        return proc.stdout


def latest_release(gh: GH) -> str:
    return gh.api(f"repos/{SELF}/releases/latest", ".tag_name").strip()


def minors_behind(pin: str, latest: str) -> int | None:
    a, b = SEMVER.match(pin), SEMVER.match(latest)
    if not a or not b:
        return None
    pa, pb = (int(a.group(1)), int(a.group(2))), (int(b.group(1)), int(b.group(2)))
    if pa[0] != pb[0]:
        return 99  # a major behind is as bad as it gets
    return max(0, pb[1] - pa[1])


def scan(gh: GH, orgs: list[str]) -> list[dict]:
    findings = []
    for org in orgs:
        repos = gh.api(f"orgs/{org}/repos?per_page=100", ".[].name").split()
        for repo in repos:
            full = f"{org}/{repo}"
            listing = gh.api(f"repos/{full}/contents/.github/workflows", ".[].name")
            for wf in listing.split():
                if not wf.endswith((".yml", ".yaml")):
                    continue
                body = gh.api(f"repos/{full}/contents/.github/workflows/{wf}", raw=True)
                for name, ref in USES.findall(body):
                    findings.append(
                        {"repo": full, "file": wf, "workflow": name, "ref": ref}
                    )
    return findings


def classify(findings: list[dict], latest: str, max_behind: int) -> list[dict]:
    out = []
    for f in findings:
        behind = minors_behind(f["ref"], latest)
        if behind is None:
            f["status"], f["detail"] = "MUTABLE", f"`{f['ref']}` is not a release tag"
        elif behind > max_behind:
            f["status"], f["detail"] = "STALE", f"{behind} minor(s) behind {latest}"
        else:
            f["status"], f["detail"] = "OK", ""
        out.append(f)
    return out


def render_md(rows: list[dict], latest: str) -> str:
    bad = [r for r in rows if r["status"] != "OK"]
    lines = [f"## Caller pin drift — latest release `{latest}`", ""]
    if not bad:
        lines += [f"All {len(rows)} caller pin(s) are current. ✅"]
        return "\n".join(lines) + "\n"
    lines += [
        f"**{len(bad)} of {len(rows)} caller pin(s) need attention.**",
        "",
        "| Status | Repo | File | Workflow | Pin | Detail |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(bad, key=lambda r: (r["status"], r["repo"])):
        lines.append(
            f"| {r['status']} | `{r['repo']}` | `{r['file']}` | `{r['workflow']}` "
            f"| `{r['ref']}` | {r['detail']} |"
        )
    lines += [
        "",
        "**MUTABLE** pins run whatever the ref points at today — a moved tag is a "
        "supply-chain event for workflows that mint cloud credentials.",
        "",
        "Before repinning, diff the contract you depend on "
        "(`git diff <pin>..<latest> -- .github/workflows/<workflow>.yml`) and, for a "
        "destructive workflow, dry-run both pins and diff the plans. See AGENTS.md §5.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["text", "md"], default="text")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-minors-behind", type=int, default=1)
    ap.add_argument("--fail-on-drift", action="store_true")
    args = ap.parse_args(argv)

    orgs = json.loads(FLEET.read_text())["orgs"]
    if not orgs:
        print("::error::fleet.json lists no orgs — nothing would be scanned")
        return 1

    gh = GH()
    latest = latest_release(gh)
    found = scan(gh, orgs)

    # A fleet-wide zero is not "all current" — it means the scan broke (a bad Accept
    # header did exactly this once) and a silent all-clear is the worst possible output
    # for a tool whose entire job is noticing what nobody is watching.
    if not found:
        print(
            "::error::scanned "
            f"{len(orgs)} org(s) and found no reusable-workflow callers at all. "
            "That is almost certainly a broken scan, not a clean fleet — check token "
            "scope and the contents API response format."
        )
        return 1

    rows = classify(found, latest, args.max_minors_behind)
    bad = [r for r in rows if r["status"] != "OK"]

    if args.json:
        print(json.dumps({"latest": latest, "findings": rows}, indent=2))
    elif args.format == "md":
        print(render_md(rows, latest), end="")
    else:
        for r in bad:
            print(f"{r['status']:8} {r['repo']:28} {r['file']:22} {r['workflow']:26} {r['ref']}")
        print(f"\n{len(bad)}/{len(rows)} caller pin(s) need attention (latest {latest})")

    return 1 if (bad and args.fail_on_drift) else 0


if __name__ == "__main__":
    sys.exit(main())
