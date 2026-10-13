"""Markdown summary of a release run, for $GITHUB_STEP_SUMMARY and the PR comment."""

from __future__ import annotations


def render(stage, result, detail="", drafts=None, statuses=None):
    ok = result == "success"
    lines = [f"## Release run: {'succeeded' if ok else 'FAILED'}", ""]
    lines.append(f"- Stage: **{stage}**")
    if detail:
        lines.append(f"- Detail: {detail}")
    if drafts:
        lines += ["", "### Draft releases that exist", ""]
        lines += [f"- `{repo}` ({'release id ' + str(rid) if isinstance(rid, int) else rid})"
                  for repo, rid in drafts.items()]
    if statuses:
        lines += ["", "### Repos", "", "| repo | status |", "|---|---|"]
        lines += [f"| {repo} | {st} |" for repo, st in statuses.items()]
        live = [r for r, s in statuses.items() if s == "published+live"]
        lines += ["", f"Live: {', '.join(live) if live else 'none'}"]
    if not ok:
        lines += ["", "The versions in this run are burned: nothing was deleted. Fix the cause "
                  "and open a NEW release PR with bumped versions (docs/release-flow.md "
                  "\"After a failure\")."]
    return "\n".join(lines) + "\n"
