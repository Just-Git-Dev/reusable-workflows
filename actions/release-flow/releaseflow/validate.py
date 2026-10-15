"""The release-PR / merge-time checks, read-only (a Reader, never a Writer).

Every failure is COLLECTED, not raised at the first, so a PR author sees the whole list in
one run. The same function runs on the PR and again at merge (state may have moved).

"sha is on the base branch" (config base_branch, default main): GitHub's compare API
describes HEAD relative to BASE. We compare `{base_branch}...{sha}`; `behind`/`identical`
means {sha} is an ancestor of (or equal to) the base branch.
(The spec text writes the base the other way round with the same two statuses; the
statuses it names are only right for this direction. Verified against the API's docs, not
against a live repo -- see the porting notes.)
"""

from __future__ import annotations

import base64
import re

import gh

_SEMVER = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)\Z")


def semver(tag):
    m = _SEMVER.match(tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def semver_tags(reader, base):
    """All vX.Y.Z tags of a repo as [(tuple, tag)] ascending; non-semver tags ignored.

    Tags, not Releases: before release-flow these repos released by tag push, so their GitHub Releases
    are stale (releases/latest said v0.5.0 while v0.131.0 was live). Burned tags from failed
    release-flow runs and legacy tags with no Release both count -- a version is spent once tagged.
    """
    out = []
    # ONE GET: matching-refs is not paginated -- every page returns every matching ref, so
    # paginate() would never see an empty page (2026-10-09, 152 core refs on pages 1/2/50).
    refs = reader.get_ok(f"{base}/git/matching-refs/tags/v")
    if not isinstance(refs, list):
        raise gh.GitHubError(f"GET {base}/git/matching-refs/tags/v: expected a list")
    for ref in refs:
        tag = str(ref.get("ref", "")).removeprefix("refs/tags/")
        v = semver(tag)
        if v:
            out.append((v, tag))
    return sorted(out)


def tag_problem(reader, base, tag, sha):
    """None if `tag` exists, is an ANNOTATED tag object, and peels to commit `sha`; else the
    one distinct, named reason it does not. The owner pushes the tag; this flow never does."""
    status, ref = reader.get(f"{base}/git/ref/tags/{tag}")
    if status == 404:
        return f"tag {tag} does not exist (push the annotated tag first)"
    if status != 200 or not isinstance(ref, dict):
        return f"cannot read tag {tag}: HTTP {status}"
    obj = ref.get("object") or {}
    if obj.get("type") != "tag":
        return (f"tag {tag} is not annotated (its ref points at a {obj.get('type')!r}, not a "
                f"tag object); re-push it with git tag -a")
    status, tobj = reader.get(f"{base}/git/tags/{obj.get('sha')}")
    target = tobj.get("object") if status == 200 and isinstance(tobj, dict) else None
    if not target:
        return f"cannot peel tag {tag}: tag object {obj.get('sha')} unreadable (HTTP {status})"
    if target.get("type") != "commit":
        return f"tag {tag} peels to a {target.get('type')!r}, not a commit"
    if target.get("sha") != sha:
        return f"tag {tag} peels to {target.get('sha')}, not the listed sha {sha}"
    return None


def validate_entry(reader, cfg, e):
    o, r = cfg.owner, e.repo
    out = []

    def fail(msg):
        out.append(f"{r}: {msg}")

    if cfg.service(r) is None:
        fail("not in releases/services.json")
        return out
    ver = semver(e.version)
    if ver is None:
        fail(f"version {e.version!r} is not vX.Y.Z")
        return out
    base = f"repos/{o}/{r}"

    try:
        releases = reader.paginate(f"{base}/releases")
    except gh.GitHubError as ex:
        releases = []
        fail(f"cannot list releases: {ex}")
    else:
        # Releases (draft or not), not tags and not releases/latest: the tag of THIS version
        # exists by design now, and legacy repos carry stale "latest" (v0.5.0 while v0.131.0
        # was live). A burned draft keeps its version spent.
        spent = sorted((v, r["tag_name"]) for r in releases
                       if (v := semver(r.get("tag_name"))))
        if spent and ver <= spent[-1][0]:
            fail(f"version {e.version} is not greater than the highest release "
                 f"{spent[-1][1]}")
        if any(r.get("tag_name") == e.version for r in releases):
            drafted = any(r.get("tag_name") == e.version and r.get("draft") for r in releases)
            fail(f"a release for {e.version} already exists{' (draft)' if drafted else ''}")

    bb = cfg.base_branch
    status, data = reader.get(f"{base}/compare/{bb}...{e.sha}")
    if status == 404:
        fail(f"sha {e.sha} not found in the repo, so it is not on {bb}")
    elif status != 200:
        fail(f"cannot compare sha to {bb}: HTTP {status}")
    elif data.get("status") not in ("identical", "behind"):
        fail(f"sha {e.sha} is not on {bb} (compare status {data.get('status')!r})")

    # Legacy repos carry stale Releases, so the Release bar alone lets a typo'd lower tag
    # through: the listed tag must also be the newest version tag (burned and legacy included).
    try:
        tags = semver_tags(reader, base)
        if tags and tags[-1][1] != e.version and ver < tags[-1][0]:
            fail(f"tag {e.version} is not the newest version tag (newest is {tags[-1][1]})")
    except gh.GitHubError as ex:
        fail(f"cannot list tags: {ex}")

    problem = tag_problem(reader, base, e.version, e.sha)
    if problem:
        fail(problem)

    if cfg.changelog is not None:  # `changelog: null` in services.json turns the check off
        cl_path = cfg.changelog.path
        heading = cfg.changelog.heading.replace("{version}", e.version)
        status, data = reader.get(f"{base}/contents/{cl_path}?ref={e.sha}")
        if status != 200 or not isinstance(data, dict) or data.get("encoding") != "base64":
            fail(f"{cl_path} not readable at {e.sha} (HTTP {status})")
        else:
            text = base64.b64decode(data["content"]).decode("utf-8", "replace")
            if not re.search(rf"^{re.escape(heading)}(?:[ \t]|$)", text, re.M):
                fail(f"{cl_path} at {e.sha} has no '{heading}' heading")
    return out


def validate_manifest(reader, cfg, entries):
    out = []
    for e in entries:
        out.extend(validate_entry(reader, cfg, e))
    return out
