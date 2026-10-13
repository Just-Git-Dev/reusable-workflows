"""H4: publish ONE repo's draft release and prove its deploy went live.

The workflow runs one job per repo in `order()` sequence, each with its own freshly minted
token; this module does the per-repo work. Before the only irreversible write (PATCH
draft:false) it re-asserts everything the draft stage established -- exactly one release with
the tag, still a draft, the tag is an ANNOTATED tag object peeling to the manifest sha -- so
a tag moved or a draft edited between stages is refused, not shipped. After the PATCH it
re-reads and re-asserts. If that post-check fails the deploy may already be running (the
release event fires on publish), so the status says so and nothing is ever PATCHed back.

Statuses:
  published+live             PATCHed, Deploy run succeeded, (image kind) health matched, (download kind) every asset uploaded
  published-deploy-failed    PATCHed; Deploy run failed/timed out, health never matched or an asset is missing
  published-postcheck-failed PATCHed; the re-read disagreed. Deploy MAY BE LIVE: investigate
  not published              refused or failed before/at the PATCH; the draft is untouched
"""

from __future__ import annotations

from typing import NamedTuple

import config
import gh

LIVE = "published+live"
DEPLOY_FAILED = "published-deploy-failed"
POSTCHECK_FAILED = "published-postcheck-failed"
NOT_PUBLISHED = "not published"
DEFAULT_HEALTH = config.DEFAULT_HEALTH

DEPLOY_TIMEOUT_S = 15 * 60          # per wait. Measured max release Deploy: 10 min (n=59)
POLL_S = 15
HEALTH_TRIES = 6
HEALTH_WAIT_S = 10
MAX_DEPLOY_RETRIES = 2              # H7: 3 attempts in total (docs/release-flow.md cites this)
RETRYABLE = ("failure", "cancelled", "timed_out")
API_TIMEOUT_S = 30                  # urllib_transport default
HEALTH_TIMEOUT_S = 15               # http_get_json default
# Worst case for one repo's publish step, to size the job's timeout-minutes: every attempt
# waits its full timeout (a poll can overshoot the deadline by one sleep + one API call), then
# the proof loop burns all its tries: the health loop (image: HTTP calls) or the asset loop
# (download: API calls), whichever is longer. ~51.1 min (download). It MUST stay under the
# 60 min lifetime of the App installation token minted for the job (test pins < 55 min);
# measured max deploy is 10 min, so 15 min per attempt leaves headroom without outliving it.
MAX_PUBLISH_SLOTS = 6               # the shared workflow has 6 publish jobs; `order` refuses more
_DEPLOY_WORST_S = (MAX_DEPLOY_RETRIES + 1) * (DEPLOY_TIMEOUT_S + POLL_S + API_TIMEOUT_S)
_WAITS_S = (HEALTH_TRIES - 1) * HEALTH_WAIT_S
_HEALTH_WORST_S = HEALTH_TRIES * HEALTH_TIMEOUT_S + _WAITS_S
_ASSETS_WORST_S = HEALTH_TRIES * API_TIMEOUT_S + _WAITS_S
WORST_CASE_S = _DEPLOY_WORST_S + max(_HEALTH_WORST_S, _ASSETS_WORST_S)


class PublishResult(NamedTuple):
    status: str
    detail: str


class _Stop(Exception):
    pass


def order(cfg, entries):
    listed = {e.repo for e in entries}
    return [s.repo for s in cfg.services if s.repo in listed]


def _peels_to(reader, base, tag, sha):
    """The tag ref must be an annotated tag object whose target is commit `sha`."""
    ref = reader.get_ok(f"{base}/git/ref/tags/{tag}")
    obj = ref.get("object") or {}
    if obj.get("type") != "tag":
        raise _Stop(f"tag {tag} is not an annotated tag (object type {obj.get('type')!r})")
    target = reader.get_ok(f"{base}/git/tags/{obj['sha']}").get("object") or {}
    if target.get("type") != "commit" or target.get("sha") != sha:
        raise _Stop(f"tag {tag} peels to {target.get('sha')!r}, manifest sha is {sha}")


def _find_draft(reader, base, tag):
    matches = [r for r in reader.paginate(f"{base}/releases") if r.get("tag_name") == tag]
    if len(matches) != 1:
        raise _Stop(f"expected exactly one release tagged {tag}, found {len(matches)}")
    rel = reader.get_ok(f"{base}/releases/{matches[0]['id']}")
    if rel.get("tag_name") != tag or rel.get("draft") is not True:
        raise _Stop(f"release {matches[0]['id']} is not a draft for {tag}")
    return rel


def _wait_run(reader, base, svc, entry, clock, sleep, run_id=None, after_attempt=0,
              title=None):
    """Poll until THE deploy run is completed -> that run dict. Bounded by DEPLOY_TIMEOUT_S.

    The run is matched strictly: event release, head_branch the tag, head_sha the manifest
    sha, display_title exactly the deploy_run_name template with the tag filled in (set by the
    deploy workflow's run-name; default `Deploy <tag>`). Two matches are
    ambiguous and stop the publish. After a rerun, `completed` is ignored until run_attempt
    exceeds `after_attempt` (GitHub can still list the old failed attempt for a moment).
    """
    tag = entry.version
    title = title or f"Deploy {tag}"
    deadline = clock() + DEPLOY_TIMEOUT_S
    path = f"{base}/actions/workflows/{svc.deploy_workflow}/runs?event=release&per_page=30"
    while True:
        runs = reader.get_ok(path).get("workflow_runs", [])
        mine = [r for r in runs if r.get("event") == "release" and r.get("head_branch") == tag
                and r.get("head_sha") == entry.sha and r.get("display_title") == title
                and (run_id is None or r.get("id") == run_id)]
        if len(mine) > 1:
            raise _Stop(f"ambiguous: {len(mine)} deploy runs match {tag} at {entry.sha}: "
                        f"{sorted(r.get('id') for r in mine)}")
        if mine and mine[0].get("status") == "completed" \
                and (mine[0].get("run_attempt") or 1) > after_attempt:
            return mine[0]
        if clock() >= deadline:
            raise _Stop(f"timed out after {DEPLOY_TIMEOUT_S // 60} min waiting for the "
                        f"{svc.deploy_workflow} run on {tag}")
        sleep(POLL_S)


def _deploy(reader, writer, cfg, base, svc, entry, clock, sleep):
    """Wait for the deploy run; rerun its failed jobs up to MAX_DEPLOY_RETRIES times."""
    title = cfg.deploy_run_name.replace("{tag}", entry.version)
    run = _wait_run(reader, base, svc, entry, clock, sleep, title=title)
    for retry in range(MAX_DEPLOY_RETRIES + 1):
        if run.get("conclusion") == "success":
            return
        if run.get("conclusion") not in RETRYABLE or retry == MAX_DEPLOY_RETRIES:
            why = "not retryable" if retry < MAX_DEPLOY_RETRIES else "retries exhausted"
            raise _Stop(f"Deploy run {run['id']} concluded {run.get('conclusion')!r} after "
                        f"{retry + 1} attempts ({why})" if retry else
                        f"Deploy run {run['id']} concluded {run.get('conclusion')!r} "
                        f"after 1 attempt ({why})")
        attempt = run.get("run_attempt") or 1
        try:
            writer.rerun_failed(cfg.owner, entry.repo, run["id"])
        except (gh.GitHubError, gh.Refused) as ex:
            raise _Stop(f"rerun of failed deploy run {run['id']} refused: {ex}") from ex
        run = _wait_run(reader, base, svc, entry, clock, sleep, run["id"], attempt, title)


def _dig(body, path):
    """The value at a dotted path inside nested JSON objects, or None."""
    for key in path.split("."):
        if not isinstance(body, dict):
            return None
        body = body.get(key)
    return body


def _check_health(svc, health_get, sleep):
    path, expect = svc.health or DEFAULT_HEALTH
    last = "no response"
    for i in range(HEALTH_TRIES):
        status, body = health_get(svc.health_url)
        got = _dig(body, path)
        if status == 200 and got == expect:
            return
        last = f"HTTP {status}, {path}={got!r}"
        if i < HEALTH_TRIES - 1:
            sleep(HEALTH_WAIT_S)
    raise _Stop(f"health {svc.health_url} never reported {path}={expect!r} ({last})")


def _check_assets(reader, base, release_id, svc, sleep):
    """kind download: the published Release must carry every configured asset, state uploaded."""
    missing = list(svc.assets)
    for i in range(HEALTH_TRIES):
        rel = reader.get_ok(f"{base}/releases/{release_id}")
        have = {a.get("name") for a in rel.get("assets") or []
                if isinstance(a, dict) and a.get("state") == "uploaded"}
        missing = [a for a in svc.assets if a not in have]
        if not missing:
            return
        if i < HEALTH_TRIES - 1:
            sleep(HEALTH_WAIT_S)
    raise _Stop(f"release asset(s) missing or not in state 'uploaded' after "
                f"{HEALTH_TRIES} tries: {', '.join(missing)}")


def publish_repo(reader, writer, cfg, entry, health_get, clock, sleep):
    svc = cfg.service(entry.repo)
    if svc is None:
        return PublishResult(NOT_PUBLISHED, f"{entry.repo} is not in services.json")
    base = f"repos/{cfg.owner}/{entry.repo}"
    tag = entry.version
    try:
        rel = _find_draft(reader, base, tag)
        _peels_to(reader, base, tag, entry.sha)
    except (_Stop, gh.GitHubError) as ex:
        return PublishResult(NOT_PUBLISHED, str(ex))
    try:
        writer.publish_release(cfg.owner, entry.repo, rel["id"])
    except (gh.GitHubError, gh.Refused) as ex:
        return PublishResult(NOT_PUBLISHED, f"PATCH failed: {ex} (re-check the release state)")
    try:
        again = reader.get_ok(f"{base}/releases/{rel['id']}")
        if again.get("tag_name") != tag or again.get("draft") is not False:
            raise _Stop(f"after PATCH release has tag_name={again.get('tag_name')!r} "
                        f"draft={again.get('draft')!r}")
        _peels_to(reader, base, tag, entry.sha)
    except (_Stop, gh.GitHubError) as ex:
        return PublishResult(POSTCHECK_FAILED,
                             f"{ex}. The deploy may already be live; investigate. Nothing "
                             "was reverted.")
    try:
        _deploy(reader, writer, cfg, base, svc, entry, clock, sleep)
        if svc.kind == "image":
            _check_health(svc, health_get, sleep)
        elif svc.kind == "download":
            _check_assets(reader, base, rel["id"], svc, sleep)
    except (_Stop, gh.GitHubError) as ex:
        return PublishResult(DEPLOY_FAILED, str(ex))
    return PublishResult(LIVE, "")
