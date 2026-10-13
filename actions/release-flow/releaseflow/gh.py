"""GitHub REST client for the release flow, split into a Reader and a Writer.

WHY two classes: the release flow holds a write-capable App token for a few minutes. The
safety property we want is not "the code is careful" but "the code CANNOT do anything else":
no branch push, no tag delete, no release delete, no publishing with extra fields. So all
writes go through `Writer.request`, which refuses everything outside a three-entry allowlist
(draft release, publish, rerun-failed-jobs of one deploy run; never a tag or a ref;
ALLOWED_CALLS, pinned verbatim by test_gh.py). A refused call never reaches the transport.
`Reader` has no write surface at all (GET only).

A transport is a callable `(method, path, body) -> (status, data)`; `path` is relative to
https://api.github.com/ and may carry a query string. `urllib_transport` is the real one;
the tests inject fake_github.FakeGitHub. Stdlib only.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

API = "https://api.github.com/"
_SLUG = r"[A-Za-z0-9_.-]+"
# \Z, not $: "$" also matches before a trailing newline
_RELEASES = re.compile(rf"^repos/{_SLUG}/{_SLUG}/releases\Z")
_RERUN = re.compile(rf"^repos/{_SLUG}/{_SLUG}/actions/runs/[0-9]+/rerun-failed-jobs\Z")
_RELEASE = re.compile(rf"^repos/{_SLUG}/{_SLUG}/releases/\d+\Z", re.ASCII)

# The ENTIRE write surface of the flow: no tag, no ref (the owner pushes the annotated tag;
# J1). Adding a fourth entry must fail test_gh.py.
ALLOWED_CALLS = (
    "POST repos/{o}/{r}/releases  body.draft is true",
    "PATCH repos/{o}/{r}/releases/{id}  body == {\"draft\": false}",
    "POST repos/{o}/{r}/actions/runs/{id}/rerun-failed-jobs  no body",
)


class GitHubError(Exception):
    """A GitHub call failed (non-2xx where 2xx was required, or a network error)."""

    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


class Refused(Exception):
    """The Writer allowlist refused a call. Nothing was sent."""


def urllib_transport(token, timeout=30):
    def call(method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "release-flow",
            **({"Content-Type": "application/json"} if data else {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise GitHubError(f"{method} {path}: network error: {e}") from e
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, raw.decode("utf-8", "replace")
    return call


def http_get_json(url, timeout=15):
    """Unauthenticated GET of an arbitrary URL (service health). -> (status, data|text)."""
    req = urllib.request.Request(url, headers={"User-Agent": "release-flow"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, f"network error: {e}"
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode("utf-8", "replace")


class Reader:
    """GET only."""

    def __init__(self, transport):
        self._t = transport

    def get(self, path):
        return self._t("GET", path, None)

    def get_ok(self, path):
        status, data = self.get(path)
        if not 200 <= status < 300:
            raise GitHubError(f"GET {path}: HTTP {status}", status)
        return data

    def paginate(self, path, key=None):
        """All items of a list endpoint (or of `key` in an object response); stops at the
        first empty page."""
        sep = "&" if "?" in path else "?"
        out, page, prev = [], 1, None
        while True:
            items = self.get_ok(f"{path}{sep}per_page=100&page={page}")
            if key:
                items = items.get(key, [])
            if not items:
                return out
            if items == prev:
                # An endpoint that ignores `page` (e.g. git/matching-refs) repeats itself and
                # would loop to the cap; say so instead.
                raise GitHubError(f"GET {path}: page {page} repeats page {page - 1} -- "
                                  "this endpoint is not paginated; read it with one get_ok")
            prev = items
            out.extend(items)
            page += 1
            if page > 200:
                raise GitHubError(f"GET {path}: more than 200 pages")


def _allowed(method, path, body):
    """Return None if allowed, else the reason for refusal."""
    if method == "POST" and _RELEASES.match(path):
        if isinstance(body, dict) and body.get("draft") is True:
            return None
        return "release POST must carry draft: true"
    if method == "POST" and _RERUN.match(path):
        if body is None:
            return None
        return "rerun-failed-jobs takes no body"
    if method == "PATCH" and _RELEASE.match(path):
        if isinstance(body, dict) and body == {"draft": False} and body["draft"] is False:
            return None
        return 'release PATCH body must be exactly {"draft": false}'
    return "not in the allowlist"


class Writer:
    def __init__(self, transport):
        self._t = transport

    def request(self, method, path, body=None):
        why = _allowed(method, path, body)
        if why:
            raise Refused(f"{method} {path}: {why}")
        return self._t(method, path, body)

    def _ok(self, method, path, body):
        status, data = self.request(method, path, body)
        if not 200 <= status < 300:
            raise GitHubError(f"{method} {path}: HTTP {status}", status)
        return data

    def create_draft(self, owner, repo, tag):
        return self._ok("POST", f"repos/{owner}/{repo}/releases",
                        {"tag_name": tag, "name": tag, "generate_release_notes": True,
                         "draft": True})

    def rerun_failed(self, owner, repo, run_id):
        """Re-run the failed jobs of ONE deploy run (H7 retry). The only actions/* write."""
        self._ok("POST", f"repos/{owner}/{repo}/actions/runs/{int(run_id)}/rerun-failed-jobs",
                 None)

    def publish_release(self, owner, repo, release_id):
        return self._ok("PATCH", f"repos/{owner}/{repo}/releases/{release_id}",
                        {"draft": False})
