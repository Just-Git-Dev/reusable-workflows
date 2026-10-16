"""Which ref/image each service runs in the contract and smoke stages.

Listed in the manifest -> ref is the candidate sha (image: <registry>/<image>:<sha>).
Unlisted -> ref is the LIVE version. Every entry also carries `live_ref`.

"Live" (owner ruling H7) comes from DEPLOYS THAT SUCCEEDED, not from tags or Releases (the
service repos released by tag push before this flow, so their Releases are stale; core's latest
Release said v0.5.0 while v0.131.0 was live). Walk the deploy workflow's successful runs
(events release, push, workflow_dispatch), newest CREATED first; the first decisive run wins:
  - run-name (API display_title) `Deploy DRYRUN ...`: skipped, a dry run deploys nothing;
  - `Deploy vX.Y.Z`: that version is live (a hand deploy of an older tag DOES make it live);
  - no parseable title (legacy, before run-name), any of the three events: head_branch if it
    is vX.Y.Z, since such a workflow deploys the ref it runs on;
  - otherwise release/push is skipped (a build on push to main is not a deploy), and
    workflow_dispatch FAILS naming the run URL, since prod then runs a branch or sha with no
    version and nothing may guess.
No qualifying run at all also fails loudly. This relies on each deploy.yml's `run-name`.

tool (consumers_only) is non-flow: it releases by tag push and never gets drafts or deploy runs
from this flow, so its live_ref is simply the highest vX.Y.Z tag; no draft visibility needed.
Ordering of deploy runs uses run_started_at (see _started), so a re-run rollback wins.
"""

from __future__ import annotations

import re

import gh
import validate


_REF = re.compile(r"^([0-9a-f]{40}|v[0-9]+\.[0-9]+\.[0-9]+)\Z", re.ASCII)


def title_patterns(template):
    """(dry-run marker, version title) regexes for a deploy_run_name template such as
    `Deploy {tag}`. The marker is the template with {tag} -> DRYRUN, matched as a prefix."""
    head, tail = template.split("{tag}")
    dry = re.compile("^" + re.escape(template.replace("{tag}", "DRYRUN")))
    title = re.compile("^" + re.escape(head) + r"(v[0-9]+\.[0-9]+\.[0-9]+)" + re.escape(tail)
                       + r"\Z", re.ASCII)
    return dry, title


class ResolveError(Exception):
    pass


def prove_drafts_visible(reader, owner, repo, tag):
    """The token can see drafts iff it can see the draft this run just created.

    One App installation carries the same permissions on every repo, so one proof covers all.
    """
    try:
        rels = reader.paginate(f"repos/{owner}/{repo}/releases")
    except gh.GitHubError as ex:
        raise ResolveError(f"{repo}: cannot list releases to prove draft visibility ({ex})") from ex
    if not any(r.get("tag_name") == tag and r.get("draft") is True for r in rels):
        raise ResolveError(f"token cannot see the draft {repo}:{tag} this run just created, "
                           "so burned draft tags cannot be told from released ones")


def _live_from_deploys(reader, owner, svc, template):
    dryrun, title_re = title_patterns(template)
    path = (f"repos/{owner}/{svc.repo}/actions/workflows/{svc.deploy_workflow}/runs"
            "?status=success")
    try:
        runs = reader.paginate(path, key="workflow_runs")
    except gh.GitHubError as ex:
        raise ResolveError(f"{svc.repo}: cannot list successful deploys ({ex})") from ex
    runs = [r for r in runs if r.get("conclusion") == "success"
            and r.get("event") in ("release", "push", "workflow_dispatch")]
    for r in sorted(runs, key=_started, reverse=True):
        title = r.get("display_title") or ""
        if dryrun.match(title):
            continue  # a dry run deploys nothing
        m = title_re.match(title)
        if m:
            return m.group(1)
        if validate.semver(r.get("head_branch")) is not None:
            return r["head_branch"]  # legacy tag push / release / dispatch, before run-name
        if r["event"] == "workflow_dispatch":
            raise ResolveError(
                f"{svc.repo}: a successful hand-dispatched deploy ({title!r}) has no version "
                f"in its title, so what prod runs is unknowable: {r.get('html_url')}")
        # push to a branch (core/gateway build on main): not a deploy
    raise ResolveError(f"{svc.repo}: no successful {svc.deploy_workflow} run found that "
                       "deployed a vX.Y.Z, so its live version is unknown")


def _started(run):
    """Ordering key: run_started_at, NOT created_at. A re-run of an old Deploy (a rollback)
    keeps its original created_at but gets a new run_started_at, and that re-run is what
    prod now runs. created_at only as a fallback when the field is absent."""
    return run.get("run_started_at") or run.get("created_at", "")


def _live_from_tags(reader, owner, name):
    """consumers_only = non-flow (tag-released, no drafts ever): the highest vX.Y.Z tag."""
    try:
        tags = validate.semver_tags(reader, f"repos/{owner}/{name}")
    except gh.GitHubError as ex:
        raise ResolveError(f"{name}: cannot determine the released version ({ex})") from ex
    if not tags:
        raise ResolveError(f"{name}: no vX.Y.Z tag found")
    return tags[-1][1]


def resolve(reader, cfg, entries, drafts_proof=None):
    """drafts_proof: optional (repo, tag); when given, that draft must be visible to the token.
    Nothing requires it now (deployable repos use deploy runs, tool uses plain tags); it is
    kept for a deployable repo that ever needs tag-vs-draft resolution again."""
    if drafts_proof:
        prove_drafts_visible(reader, cfg.owner, *drafts_proof)
    listed = {e.repo: e for e in entries}
    out = {}
    for svc in cfg.services:
        live = _live_from_deploys(reader, cfg.owner, svc, cfg.deploy_run_name)
        out[svc.repo] = _entry(cfg, svc.repo, svc.image, listed.get(svc.repo), live)
    for name in cfg.consumers_only:
        out[name] = _entry(cfg, name, None, None, _live_from_tags(reader, cfg.owner, name))
    return out


def _entry(cfg, name, image, listed, live):
    if listed:
        ref, version = listed.sha, listed.version
    else:
        ref = version = live
    if not isinstance(ref, str) or not _REF.match(ref):
        raise ResolveError(f"{name}: ref {ref!r} is neither a 40-hex sha nor vX.Y.Z")
    return {"ref": ref, "version": version, "listed": listed is not None,
            "image": f"{cfg.gar_registry}/{image}:{ref}" if image else None,
            "live_ref": live}
