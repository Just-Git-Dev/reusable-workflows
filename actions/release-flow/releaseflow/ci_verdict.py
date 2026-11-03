"""`release-flow ci-verdict`: did CI already pass for this exact code? (docs/ci-verdict.md)

For EVERY listed workflow, the newest run (by created_at, a tie goes to the higher id) on
head_sha == sha must be completed/success (rule 1); or, with match=tree, a pull request of
`commits/{sha}/pulls` whose head commit has the same git tree as `sha` must have a newest run of
that workflow on its head commit that is completed/success (rule 2). Any event counts (unlike
ci.py, which reads push runs only). Everything else, including ANY API error, is reuse=false with
the reason in `why`: a wrong "yes" ships untested code, a miss costs a few minutes of CI. Reads
only; never waits.
"""

from __future__ import annotations

import json
import re
import sys

import gh

MATCHES = ("sha", "tree")


class UsageError(Exception):
    """A bad input: the CLI exits 2."""


def one_line(text):
    return " ".join(str(text).replace("\r", " ").replace("\n", " ").split())


def validate(repo, sha, workflows, match):
    """-> the list of workflow file names. Raises UsageError."""
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repo or ""):
        raise UsageError(f"--repo must be owner/name, got {repo!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
        raise UsageError(f"--sha must be 40 lowercase hex characters, got {sha!r}")
    if match not in MATCHES:
        raise UsageError(f"--match must be one of {', '.join(MATCHES)}, got {match!r}")
    wfs = [w.strip() for w in (workflows or "").split(",") if w.strip()]
    if not wfs:
        raise UsageError("--workflows lists no workflow file")
    return wfs


# Events whose run tests the commit it names; others (pull_request_target, workflow_dispatch...)
# are ignored as if absent (docs/ci-verdict.md).
TESTING_EVENTS = ("push", "pull_request", "merge_group")


def _run_key(run):
    rid = run.get("id")
    return (run.get("created_at") or "", rid if isinstance(rid, int) else 0)


def _newest_run(reader, base, wf, sha):
    data = reader.get_ok(f"{base}/actions/workflows/{wf}/runs?head_sha={sha}")
    runs = data.get("workflow_runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        raise gh.GitHubError(f"runs of {wf} at {sha[:8]}: unexpected response shape")
    runs = [r for r in runs if isinstance(r, dict) and r.get("event") in TESTING_EVENTS]
    return max(runs, key=_run_key) if runs else None


def _green(run):
    """None if green, else why not."""
    if run.get("status") != "completed":
        return f"run {run.get('html_url')} is {run.get('status')}, not finished"
    if run.get("conclusion") != "success":
        return f"run {run.get('html_url')} concluded {run.get('conclusion')}"
    return None


def _tree(reader, base, sha):
    data = reader.get_ok(f"{base}/git/commits/{sha}")
    tree = ((data or {}).get("tree") or {}).get("sha") if isinstance(data, dict) else None
    if not tree:
        raise gh.GitHubError(f"git/commits/{sha[:8]}: no tree in the response")
    return tree


class _Prs:
    """The PRs associated with sha and sha's tree, read once and only if rule 2 is needed."""

    def __init__(self, reader, base, sha):
        self.reader, self.base, self.sha = reader, base, sha
        self._loaded = None

    def get(self):
        if self._loaded is None:
            prs = self.reader.get_ok(f"{self.base}/commits/{self.sha}/pulls")
            if not isinstance(prs, list):
                raise gh.GitHubError(f"commits/{self.sha[:8]}/pulls: unexpected response shape")
            self._loaded = (prs, _tree(self.reader, self.base, self.sha) if prs else None)
        return self._loaded


def _by_sha(reader, base, wf, sha):
    """-> (url, why, final). url is None when rule 1 does not hold; final is True when the
    newest run at the sha itself FINISHED red, which no tree-equal PR head may override."""
    run = _newest_run(reader, base, wf, sha)
    if run is None:
        return None, f"{wf}: no run on {sha[:8]}", False
    bad = _green(run)
    if bad:
        return None, f"{wf}: {bad}", run.get("status") == "completed"
    return run.get("html_url") or "", f"{wf}: same sha, run {run.get('html_url')}", False


def _by_tree(reader, base, wf, sha, prs, rule1_why):
    candidates, tree = prs.get()
    if not candidates:
        return None, f"{rule1_why}; no pull request is associated with {sha[:8]}"
    notes = []
    for pr in candidates:
        number = pr.get("number") if isinstance(pr, dict) else None
        head_obj = pr.get("head") if isinstance(pr, dict) else None
        head = head_obj.get("sha") if isinstance(head_obj, dict) else None
        if not head or not re.fullmatch(r"[0-9a-f]{40}", str(head)):
            notes.append(f"PR #{number}: no usable head sha")
            continue
        if _tree(reader, base, head) != tree:
            notes.append(f"PR #{number} head {head[:8]} has a different tree")
            continue
        run = _newest_run(reader, base, wf, head)
        if run is None:
            notes.append(f"PR #{number} head {head[:8]} has the same tree but no run")
            continue
        bad = _green(run)
        if bad:
            notes.append(f"PR #{number} head {head[:8]} has the same tree but {bad}")
            continue
        return (run.get("html_url") or "",
                f"{wf}: PR #{number} head {head[:8]} has the same tree, run {run.get('html_url')}")
    return None, f"{rule1_why}; {'; '.join(notes)}"


def decide(reader, repo, sha, workflows, match):
    """-> {"reuse", "run_url", "why", "examined"}. Never raises on a GitHub error."""
    base = f"repos/{repo}"
    prs = _Prs(reader, base, sha)
    urls, whys, first_bad = [], [], None
    for wf in workflows:
        try:
            url, why, final = _by_sha(reader, base, wf, sha)
            if url is None and match == "tree" and not final:
                url, why = _by_tree(reader, base, wf, sha, prs, why)
        except gh.GitHubError as ex:
            url, why = None, f"{wf}: cannot read CI state: {ex}"
        if url is None:
            first_bad = first_bad or why
        else:
            urls.append(url)
            whys.append(why)
    if first_bad:
        return {"reuse": False, "run_url": "", "why": one_line(first_bad),
                "examined": len(workflows)}
    return {"reuse": True, "run_url": " ".join(urls), "why": one_line("; ".join(whys)),
            "examined": len(workflows)}


def write_github_output(path, verdict):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"reuse={'true' if verdict['reuse'] else 'false'}\n")
        fh.write(f"run_url={one_line(verdict['run_url'])}\n")
        fh.write(f"why={one_line(verdict['why'])}\n")


def run_cli(reader, repo, sha, workflows, match, github_output=""):
    """Prints the one JSON line; always 0 (usage errors are raised by validate before)."""
    v = decide(reader, repo, sha, workflows, match)
    print(json.dumps(v, separators=(",", ":")))
    print(f"examined {v['examined']} workflow(s): reuse={'true' if v['reuse'] else 'false'}",
          file=sys.stderr)
    if github_output:
        write_github_output(github_output, v)
    return 0
