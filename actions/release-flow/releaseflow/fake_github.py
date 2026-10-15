"""In-memory GitHub REST fake for the release-flow tests (not a test module: discovery skips it).

It is a TRANSPORT, i.e. a callable `(method, path, body) -> (status, data)` with the same
shape as gh.urllib_transport, so Reader/Writer run unmodified against it. It records every
request, which is how the tests prove "zero writes" and "writes in this order".
"""

from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, urlsplit

OWNER = "consumer-a-org"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


class Repo:
    def __init__(self, name):
        self.name = name
        self.compare = {}        # sha -> "identical" | "behind" | "ahead" | "diverged"
        self.changelog = {}      # sha -> text
        self.releases = []       # dicts as GitHub returns them
        self.refs = {}           # tag -> {"type": "tag"|"commit", "sha": ...}
        self.tag_objects = {}    # tag object sha -> commit sha
        self.deploy_script = None  # list of (status, conclusion) consumed per poll; None = no run
        self.deploy_polls = 0
        self.published_tag = None
        self.can_push = True     # False = the token cannot see draft releases
        self.suite_runs = {}     # check_suite id -> [workflow runs with `path`]
        self.published_sha = None
        self.reruns = 0          # rerun-failed-jobs calls received (run_attempt = 1 + reruns)
        self.stale_after_rerun = 0   # polls that still show the old failed attempt after a rerun
        self.stale_polls = 0
        self.extra_runs = []     # additional deploy runs returned by the runs listing
        self.ci_runs = {}        # (workflow file, head sha) -> [runs]
        self.parents = {}        # commit sha -> [parent shas]
        self.compare_files = {}  # (ancestor, sha) -> [changed file names]
        self.live_runs = None   # deploy-workflow runs for status=success queries (None = none)
        self.pulls = {}          # commit sha -> [PR dicts]   (root repo)
        self.check_runs = {}     # head sha -> [check-run dicts]
        self.pr_objects = {}     # PR number -> PR dict (pulls/{n}; open ones also by head ref)
        self.issue_events = {}   # PR number -> [issue events] (issues/{n}/events)
        self.wf_runs = []        # workflow runs of the root repo (release.yml)
        self.after_patch = None  # callable(repo, release) to mutate state post-PATCH
        self.base_branch = "main"          # the branch compare/<base>...<sha> is answered for
        self.changelog_path = "CHANGELOG.md"
        self.run_name = "Deploy {tag}"     # the run-name the fake deploy run carries
        self._next_id = 100

    def add_release(self, tag, draft=False):
        self._next_id += 1
        rel = {"id": self._next_id, "tag_name": tag, "draft": draft, "name": tag}
        self.releases.append(rel)
        if not draft:  # a published release has its tag; a draft's tag is added via add_tag
            self.refs.setdefault(tag, {"type": "commit", "sha": "e" * 40})
        return rel

    def good_commit(self, sha, version):
        self.compare[sha] = "behind"
        self.changelog[sha] = f"# Changelog\n\n## {version} — 2026-10-09\n\n- thing\n"

    def add_tag(self, tag, sha):
        """An ANNOTATED tag (ref -> tag object -> commit `sha`), as the owner pushes it."""
        obj = f"{len(self.tag_objects) + 1:040x}"
        self.tag_objects[obj] = sha
        self.refs[tag] = {"type": "tag", "sha": obj}

    def stage_draft(self, tag, sha):
        """The annotated tag + the draft Release drafts.py leaves."""
        self.add_tag(tag, sha)
        return self.add_release(tag, draft=True)


class FakeGitHub:
    def __init__(self, page_size=100):
        self.repos = {}
        self.requests = []
        self.page_size = page_size
        self.fail = []  # (method, regex, status): next matching request returns status

    def repo(self, name):
        return self.repos.setdefault(name, Repo(name))

    def writes(self):
        return [r for r in self.requests if r[0] != "GET"]

    def __call__(self, method, path, body=None):
        self.requests.append((method, path, body))
        for i, (m, rx, status) in enumerate(self.fail):
            if m == method and re.search(rx, path):
                del self.fail[i]
                if status == 0:  # a transport failure: the request left, no response came back
                    import gh
                    raise gh.GitHubError(f"{method} {path}: network error: timed out")
                return status, {"message": "injected"}
        u = urlsplit(path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        mt = re.match(rf"^repos/{OWNER}/([^/]+)(?:/(.*))?$", u.path)
        if not mt or mt.group(1) not in self.repos:
            return 404, {"message": "Not Found"}
        return self._route(self.repos[mt.group(1)], method, mt.group(2) or "", q, body)

    def _route(self, repo, method, rest, q, body):
        nf = (404, {"message": "Not Found"})
        if method == "GET":
            if rest == "":
                return 200, {"name": repo.name, "permissions": {"push": repo.can_push}}
            if rest == "git/matching-refs/tags/v":
                # Like real GitHub: matching-refs is NOT paginated -- every page returns every
                # matching ref (measured 2026-10-09: core pages 1, 2, 50 each returned 152).
                return 200, [{"ref": f"refs/tags/{t}", "object": dict(o)}
                             for t, o in repo.refs.items()]
            if rest == "releases":
                size = min(int(q.get("per_page", 30)), self.page_size)
                page = int(q.get("page", 1))
                return 200, repo.releases[(page - 1) * size: page * size]
            m = re.match(r"^releases/(\d+)$", rest)
            if m:
                for r in repo.releases:
                    if r["id"] == int(m.group(1)):
                        return 200, r
                return nf
            # base=main head=sha: "behind" = sha is an ancestor of main (GitHub's semantics)
            m = re.match(rf"^compare/{re.escape(repo.base_branch)}\.\.\.([0-9a-f]+)$", rest)
            if m:
                st = repo.compare.get(m.group(1))
                return (200, {"status": st}) if st else nf
            m = re.match(r"^git/ref/tags/(.+)$", rest)
            if m:
                ref = repo.refs.get(m.group(1))
                if not ref:
                    return nf
                return 200, {"ref": f"refs/tags/{m.group(1)}", "object": dict(ref)}
            m = re.match(r"^git/tags/([0-9a-f]+)$", rest)
            if m:
                c = repo.tag_objects.get(m.group(1))
                if not c:
                    return nf
                return 200, {"sha": m.group(1), "object": {"type": "commit", "sha": c}}
            if rest == f"contents/{repo.changelog_path}":
                text = repo.changelog.get(q.get("ref"))
                if text is None:
                    return nf
                # GitHub wraps base64 at 60 columns; encodebytes does the same
                return 200, {"content": base64.encodebytes(text.encode()).decode(),
                             "encoding": "base64"}
            if q.get("head_sha") and re.match(r"^actions/workflows/([^/]+)/runs$", rest):
                wf = rest.split("/")[2]
                return 200, {"workflow_runs": repo.ci_runs.get((wf, q["head_sha"]), [])}
            m = re.match(r"^commits/([0-9a-f]+)$", rest)
            if m:
                par = repo.parents.get(m.group(1))
                if par is None:
                    return nf
                return 200, {"sha": m.group(1), "parents": [{"sha": p} for p in par]}
            m = re.match(r"^compare/([0-9a-f]+)\.\.\.([0-9a-f]+)$", rest)
            if m and (m.group(1), m.group(2)) in repo.compare_files:
                files = repo.compare_files[(m.group(1), m.group(2))]
                return 200, {"status": "ahead", "files": [{"filename": x} for x in files]}
            if q.get("status") == "success" and re.match(r"^actions/workflows/[^/]+/runs$", rest):
                size = min(int(q.get("per_page", 30)), self.page_size)
                page = int(q.get("page", 1))
                runs = repo.live_runs or []
                return 200, {"workflow_runs": runs[(page - 1) * size: page * size]}
            if rest == "actions/runs" and q.get("check_suite_id"):
                return 200, {"workflow_runs": repo.suite_runs.get(int(q["check_suite_id"]), [])}
            m = re.match(r"^commits/([0-9a-f]+)/pulls$", rest)
            if m:
                return 200, repo.pulls.get(m.group(1), [])
            m = re.match(r"^pulls/(\d+)$", rest)
            if m:
                pr = repo.pr_objects.get(int(m.group(1)))
                return (200, pr) if pr else nf
            if rest == "pulls" and q.get("head"):
                return 200, [pr for pr in repo.pr_objects.values()
                             if pr.get("state") == q.get("state", "open")
                             and f"{OWNER}:{(pr.get('head') or {}).get('ref')}" == q["head"]]
            m = re.match(r"^issues/(\d+)/events$", rest)
            if m:
                size = min(int(q.get("per_page", 30)), self.page_size)
                page = int(q.get("page", 1))
                evs = repo.issue_events.get(int(m.group(1)), [])
                return 200, evs[(page - 1) * size: page * size]
            m = re.match(r"^commits/([0-9a-f]+)/check-runs$", rest)
            if m:
                return 200, {"check_runs": repo.check_runs.get(m.group(1), [])}
            if repo.wf_runs and re.match(r"^actions/workflows/[^/]+/runs$", rest):
                runs = [r for r in repo.wf_runs if r["status"] == q.get("status", r["status"])]
                return 200, {"workflow_runs": runs}
            if re.match(r"^actions/workflows/[^/]+/runs$", rest):
                if repo.deploy_script is None or repo.published_tag is None:
                    return 200, {"workflow_runs": list(repo.extra_runs)}
                i = min(repo.deploy_polls, len(repo.deploy_script) - 1)
                repo.deploy_polls += 1
                st, concl = repo.deploy_script[i]
                attempt = 1 + repo.reruns
                if repo.stale_polls > 0:  # GitHub still showing the previous attempt
                    repo.stale_polls -= 1
                    st, concl, attempt = "completed", "failure", repo.reruns
                tag = repo.published_tag
                mine = {"id": 2, "head_branch": tag, "head_sha": repo.published_sha,
                        "event": "release", "display_title": repo.run_name.replace("{tag}", tag),
                        "run_attempt": attempt, "status": st, "conclusion": concl}
                decoy = {"id": 1, "head_branch": "main", "head_sha": SHA_C, "event": "release",
                         "display_title": "Deploy main", "run_attempt": 1,
                         "status": "completed", "conclusion": "failure"}
                return 200, {"workflow_runs": [decoy, mine, *repo.extra_runs]}
        if method == "POST" and rest == "releases":
            return 201, repo.add_release(body["tag_name"], draft=body["draft"])
        m = re.match(r"^actions/runs/(\d+)/rerun-failed-jobs$", rest)
        if method == "POST" and m:
            if int(m.group(1)) != 2 or repo.published_tag is None:
                return nf
            repo.reruns += 1
            repo.stale_polls = repo.stale_after_rerun
            return 201, None
        m = re.match(r"^releases/(\d+)$", rest)
        if method == "PATCH" and m:
            for r in repo.releases:
                if r["id"] == int(m.group(1)):
                    r["draft"] = body["draft"]
                    repo.published_tag = r["tag_name"]
                    obj = repo.refs.get(r["tag_name"], {}).get("sha")
                    repo.published_sha = repo.tag_objects.get(obj)
                    if repo.after_patch:
                        repo.after_patch(repo, r)
                    return 200, r
        return nf


CFG_DICT = {
    "owner": OWNER,
    "gar_registry": "asia-southeast1-docker.pkg.dev/consumer-a-project",
    "services": [
        {"repo": "core", "kind": "image", "order": 1, "deploy_workflow": "deploy.yml",
         "health_url": "https://auth.example/health", "image": "backend/core",
         "ci": [{"workflow": "tests.yml", "paths_ignore": ["**.md", "docs/**"]},
                {"workflow": "changelog-hygiene.yml"}]},
        {"repo": "gateway", "kind": "image", "order": 2, "deploy_workflow": "deploy.yml",
         "health_url": "https://gateway.example/health", "image": "backend/gateway",
         "ci": [{"workflow": "ci.yml"}]},
        {"repo": "web", "kind": "pages", "order": 3, "deploy_workflow": "deploy.yml",
         "ci": [{"workflow": "test.yml"}]},
        {"repo": "site", "kind": "pages", "order": 4, "deploy_workflow": "deploy.yml",
         "ci": [{"workflow": "workflow-hygiene.yml"}]},
    ],
    "consumers_only": ["tool"],
    "contracts": [{"consumer": "gateway", "provider": "core"},
                  {"consumer": "tool", "provider": "core"},
                  {"consumer": "web", "provider": "gateway"},
                  {"consumer": "web", "provider": "core"}],
}
ALLOWED = ["core", "gateway", "web", "site"]


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


LIVE = {"core": "v0.131.0", "gateway": "v0.37.0", "web": "v0.54.0", "site": "v0.3.8"}


def run(branch, created, event="release", conclusion="success", title=None):
    """title = the run-name (API field display_title); None models a legacy run (no run-name),
    whose display_title GitHub fills with the commit message / workflow name."""
    n = abs(hash((branch, created, event))) % 10**9
    return {"id": n, "head_branch": branch, "event": event, "conclusion": conclusion,
            "status": "completed", "created_at": created,
            "display_title": title if title is not None else "Some commit message",
            "html_url": f"https://github.com/consumer-a-org/x/actions/runs/{n}"}


def make_live(fake, **override):
    """Give every deployable repo a successful release-event deploy of its LIVE version."""
    for name, tag in {**LIVE, **override}.items():
        fake.repo(name).live_runs = [run(tag, "2026-09-01T00:00:00Z")]


def ci_run(created="2026-10-08T00:00:00Z", status="completed", conclusion="success", n=1):
    return {"id": n, "status": status, "conclusion": conclusion, "created_at": created,
            "html_url": f"https://github.com/consumer-a-org/x/actions/runs/{n}"}


def green_ci(fake, repo, sha, cfg_dict=None):
    """A successful push run of every CI workflow cfg lists for `repo`, at `sha`."""
    for s in (cfg_dict or CFG_DICT)["services"]:
        if s["repo"] == repo:
            for w in s.get("ci", []):
                fake.repo(repo).ci_runs[(w["workflow"], sha)] = [ci_run()]
