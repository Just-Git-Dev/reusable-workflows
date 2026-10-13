"""H8: each listed commit's own CI must be green before the run writes anything.

Per listed repo and per workflow in services.json `ci`, the newest push run for that exact sha
(`actions/workflows/{file}/runs?head_sha=SHA&event=push`) must be completed/success. In
progress is a failure ("not finished yet"), not a wait. A workflow with `paths_ignore` (a
push touching only ignored paths never starts it) may have NO run at the sha: then walk the
first-parent ancestors (up to MAX_WALK) to the nearest commit that has a run, require that
run to be green, and require every file changed between it and the sha to match the
paths_ignore globs. No run and no paths_ignore is "missing". All failures are collected, and
the number of (repo, workflow) pairs examined is returned: a check that examined nothing
proves nothing, so the caller treats 0 as a failure.
"""

from __future__ import annotations

import re

import gh

MAX_WALK = 20
COMPARE_FILE_CAP = 300  # GitHub truncates compare's file list here; beyond it we cannot verify


def glob_match(pattern, path):
    """GitHub path-filter globs: `*` and `?` stay inside one path segment, `**` crosses `/`."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.fullmatch("".join(out), path, re.S) is not None


def _newest_run(reader, base, wf, sha):
    data = reader.get_ok(f"{base}/actions/workflows/{wf}/runs?head_sha={sha}&event=push")
    runs = sorted(data.get("workflow_runs", []), key=lambda r: r.get("created_at", ""),
                  reverse=True)
    return runs[0] if runs else None


def _verdict(run, label):
    """None if green, else the failure text."""
    if run.get("status") != "completed":
        return f"{label}: not finished yet: {run.get('html_url')}"
    if run.get("conclusion") != "success":
        return f"{label}: {run.get('conclusion')}: {run.get('html_url')}"
    return None


def _check_one(reader, base, repo, sha, wf, ignore):
    label = f"{repo}@{sha[:8]} {wf}"
    run = _newest_run(reader, base, wf, sha)
    if run:
        return _verdict(run, label)
    if not ignore:
        return f"{label}: missing (no push run at this commit)"
    cur = sha
    for _ in range(MAX_WALK):
        parents = reader.get_ok(f"{base}/commits/{cur}").get("parents") or []
        if not parents:
            return f"{label}: no run found and the history ends (root commit)"
        cur = parents[0]["sha"]
        run = _newest_run(reader, base, wf, cur)
        if not run:
            continue
        bad = _verdict(run, f"{label} (ancestor {cur[:8]})")
        if bad:
            return bad
        files = [f["filename"] for f in
                 reader.get_ok(f"{base}/compare/{cur}...{sha}").get("files", [])]
        if len(files) >= COMPARE_FILE_CAP:
            return f"{label}: {len(files)}+ changed files since ancestor {cur[:8]}; cannot verify"
        for name in files:
            if not any(glob_match(g, name) for g in ignore):
                return (f"{label}: no run at the commit and {name} (changed since green ancestor "
                        f"{cur[:8]}) is not covered by paths_ignore {list(ignore)}")
        return None
    return f"{label}: no run found within {MAX_WALK} first-parent ancestors"


def check(reader, cfg, entries):
    """-> (failures, examined)."""
    failures, examined = [], 0
    for e in entries:
        svc = cfg.service(e.repo)
        if svc is None or not svc.ci:
            failures.append(f"{e.repo}: no CI workflows configured in services.json")
            continue
        base = f"repos/{cfg.owner}/{e.repo}"
        for wf, ignore in svc.ci:
            examined += 1
            try:
                bad = _check_one(reader, base, e.repo, e.sha, wf, ignore)
            except gh.GitHubError as ex:
                bad = f"{e.repo}@{e.sha[:8]} {wf}: cannot read CI state: {ex}"
            if bad:
                failures.append(bad)
    return failures, examined
