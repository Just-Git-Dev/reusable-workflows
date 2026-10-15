"""Run-start guards on the ROOT repo (read-only).

check_merge: a push to main starts the release run, so a direct push (no PR, an unmerged PR,
or a PR whose `release-pr` check did not pass) must never release anything.
concurrent: the `concurrency: release` group would silently REPLACE a pending run; failing
loudly instead means a queued release is never dropped without anyone noticing.
"""

from __future__ import annotations

import gh
import waiver


WORKFLOW_PATH = ".github/workflows/release-pr.yml"


class GuardError(Exception):
    pass


def check_merge(reader, root, sha, check_name, base_branch="main",
                workflow_path=WORKFLOW_PATH):
    """-> PR number. root is 'owner/repo'."""
    try:
        prs = reader.get_ok(f"repos/{root}/commits/{sha}/pulls")
    except gh.GitHubError as ex:
        raise GuardError(f"cannot list PRs for {sha}: {ex}") from ex
    if len(prs) != 1:
        raise GuardError(f"commit {sha} belongs to {len(prs)} PRs, want exactly 1 "
                         "(a direct push to the base branch must not release)")
    pr = prs[0]
    if not pr.get("merged_at"):
        raise GuardError(f"PR #{pr.get('number')} is not merged")
    if (pr.get("base") or {}).get("ref") != base_branch:
        raise GuardError(f"PR #{pr.get('number')} did not target {base_branch}")
    head = (pr.get("head") or {}).get("sha")
    try:
        data = reader.get_ok(f"repos/{root}/commits/{head}/check-runs?per_page=100")
    except gh.GitHubError as ex:
        raise GuardError(f"cannot read check runs for {head}: {ex}") from ex
    runs = [c for c in data.get("check_runs", []) if c.get("name") == check_name]
    # The NEWEST run is the verdict: an edit or a label (the breaking-approved flow) re-runs the
    # check on the same head, leaving an older red run beside the green one. Without an int id on
    # every run, "newest" is unknowable, so every run must succeed (fail closed).
    if runs and all(isinstance(c.get("id"), int) for c in runs):
        judged = [max(runs, key=lambda c: c["id"])]
    else:
        judged = runs
    if not runs or any(c.get("conclusion") != "success" for c in judged):
        raise GuardError(f"check {check_name!r} on PR head {head} did not conclude success "
                         f"(found {[c.get('conclusion') for c in runs]}, judged "
                         f"{[c.get('conclusion') for c in judged]})")
    # A check NAME proves nothing: any app can publish a check called release-pr. Every
    # same-named run must come from GitHub Actions AND from the release-pr.yml workflow.
    for c in runs:
        slug = (c.get("app") or {}).get("slug")
        if slug != "github-actions":
            raise GuardError(f"check {check_name!r} was published by app {slug!r}, "
                             "not github-actions")
        suite = (c.get("check_suite") or {}).get("id")
        if not suite:
            raise GuardError(f"check {check_name!r} has no check suite; cannot tie it to "
                             f"{workflow_path}")
        try:
            wf = reader.get_ok(f"repos/{root}/actions/runs?check_suite_id={suite}")
        except gh.GitHubError as ex:
            raise GuardError(f"cannot map check suite {suite} to a workflow run: {ex}") from ex
        paths = [r.get("path") for r in wf.get("workflow_runs", [])]
        if not paths or any(p != workflow_path for p in paths):
            raise GuardError(f"check {check_name!r} comes from workflow run(s) {paths}, "
                             f"not {workflow_path}")
    return pr["number"]


def concurrent(reader, root, workflow, run_id):
    others = []
    for status in ("queued", "in_progress", "waiting", "pending"):
        try:
            data = reader.get_ok(
                f"repos/{root}/actions/workflows/{workflow}/runs?status={status}&per_page=100")
        except gh.GitHubError as ex:
            raise GuardError(f"cannot list {status} runs: {ex}") from ex
        others += [r["id"] for r in data.get("workflow_runs", [])
                   if str(r["id"]) != str(run_id)]
    if others:
        raise GuardError(f"other {workflow} run(s) active: {sorted(set(others))}")


def breaking_approval(reader, root, contracts, pr=None, head_branch=None):
    """The `breaking-approved` list of the release PR (waiver.py) -> [Entry].

    Real release (pr): the MERGED PR's current label + body (R1, R2), and the label must have
    been on it before merged_at (R5, from issues/{n}/events). Rehearsal (head_branch): the one
    OPEN PR whose head is that branch; its current label + body (R1, R2)."""
    try:
        if pr is not None:
            obj = reader.get_ok(f"repos/{root}/pulls/{pr}")
        else:
            owner = root.split("/", 1)[0]
            found = reader.get_ok(f"repos/{root}/pulls?state=open&head={owner}:{head_branch}")
            if len(found) != 1:
                raise GuardError(f"{len(found)} open PRs have head branch {head_branch!r}, want "
                                 "exactly 1 (a rehearsal reads the release PR's approval)")
            obj = found[0]
    except gh.GitHubError as ex:
        raise GuardError(f"cannot read the release PR: {ex}") from ex
    if pr is not None and not obj.get("merged_at"):
        raise GuardError(f"PR #{pr} is not merged")
    names = [lb.get("name") for lb in obj.get("labels") or []]
    try:
        entries = waiver.check_shape(names, obj.get("body"), contracts)
        if pr is not None and entries:
            try:
                events = reader.paginate(f"repos/{root}/issues/{pr}/events")
            except gh.GitHubError as ex:
                raise GuardError(f"cannot read PR #{pr}'s label events: {ex}") from ex
            if not waiver.label_before_merge(events, obj["merged_at"]):
                raise GuardError(f"the {waiver.LABEL!r} label was not on PR #{pr} before its "
                                 f"merge at {obj['merged_at']}; a label added after the merge "
                                 "approves nothing")
    except waiver.WaiverError as ex:
        raise GuardError(str(ex)) from ex
    return entries
