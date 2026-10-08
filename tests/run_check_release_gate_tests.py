#!/usr/bin/env python3
"""Self-test for actions/check-release-gate/check.sh — the release-gate reader.

The action decides whether a release may be drafted, so its failure mode is a
release that ships a service whose own gate never passed. Every case here runs
the SHIPPED script (no copy) against a `gh` stub that serves fixture JSON, so the
verdict logic is asserted, not assumed. The stub answers 404 for any path it has
no fixture for, the same as the real API for a missing ref.

The live positive control (real API shapes, annotated-tag peeling) is not here —
it needs a token; see docs/check-release-gate.md "Verification".

Usage:  python3 tests/run_check_release_gate_tests.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "actions" / "check-release-gate" / "check.sh"

FAILURES = []

# A `gh` stand-in. Only `gh api [flags] <path>` is supported. The path (query
# string dropped) is looked up in $GH_FIXTURES: {path: {"status": int, "body": ...}}.
# Every call's full argv is appended to $GH_LOG so a test can assert what was
# asked (or that nothing was).
GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
if not args or args[0] != "api":
    sys.stderr.write("stub: only `gh api` is supported\n"); sys.exit(2)
path = [a for a in args[1:] if not a.startswith("-")][-1]
key = path.split("?", 1)[0]
fx = json.load(open(os.environ["GH_FIXTURES"])).get(key)
if fx is None:
    print(json.dumps({"message": "Not Found"}))
    sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
status = fx.get("status", 200)
print(json.dumps(fx.get("body", {})))
if status >= 400:
    sys.stderr.write(f"gh: Server Error (HTTP {status})\n"); sys.exit(1)
'''

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_T = "c" * 40  # an annotated tag object's own sha


def svc(repo="org/api", tag="v1.0.0", sha=SHA_A):
    return {"repo": repo, "tag": tag, "sha": sha}


def light_tag(repo, tag, sha):
    """Fixture: a lightweight tag pointing straight at a commit."""
    return {f"repos/{repo}/git/ref/tags/{tag}":
            {"body": {"ref": f"refs/tags/{tag}", "object": {"type": "commit", "sha": sha}}}}


def annotated_tag(repo, tag, tag_sha, commit_sha):
    return {
        f"repos/{repo}/git/ref/tags/{tag}":
            {"body": {"ref": f"refs/tags/{tag}", "object": {"type": "tag", "sha": tag_sha}}},
        f"repos/{repo}/git/tags/{tag_sha}":
            {"body": {"sha": tag_sha, "object": {"type": "commit", "sha": commit_sha}}},
    }


def run_(id_, status="completed", conclusion="success", started="2026-10-08T10:00:00Z",
         app="github-actions", name="release-gate"):
    return {"id": id_, "name": name, "status": status, "conclusion": conclusion,
            "started_at": started, "app": {"slug": app}}


def checks(repo, sha, runs):
    return {f"repos/{repo}/commits/{sha}/check-runs":
            {"body": {"total_count": len(runs), "check_runs": runs}}}


def green(repo="org/api", tag="v1.0.0", sha=SHA_A):
    return {**light_tag(repo, tag, sha), **checks(repo, sha, [run_(1)])}


def run(services, fixtures, *, check_name=None, raw_services=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bin_ = tmp / "bin"
        bin_.mkdir()
        (bin_ / "gh").write_text(GH_STUB)
        (bin_ / "gh").chmod(0o755)
        (tmp / "fx.json").write_text(json.dumps(fixtures))
        env = dict(os.environ)
        env.update({
            "PATH": f"{bin_}:{env['PATH']}",
            "GH_FIXTURES": str(tmp / "fx.json"),
            "GH_LOG": str(tmp / "gh.log"),
            "GH_TOKEN": "stub-token",
            "SERVICES": raw_services if raw_services is not None else json.dumps(services),
            "GITHUB_OUTPUT": str(tmp / "out.txt"),
            "GITHUB_STEP_SUMMARY": str(tmp / "summary.md"),
        })
        if check_name is not None:
            env["CHECK_NAME"] = check_name
        proc = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                              env=env, cwd=tmp)
        out = tmp / "out.txt"
        outputs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l) \
            if out.exists() else {}
        log = tmp / "gh.log"
        calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        summary = (tmp / "summary.md").read_text() if (tmp / "summary.md").exists() else ""
        result = json.loads(outputs["result"]) if "result" in outputs else None
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr, "result": result,
                "calls": calls, "summary": summary}


def check(label, got, want, ctx=None):
    if got != want:
        extra = f"\n    output:\n{ctx['out']}" if ctx else ""
        FAILURES.append(f"{label}\n     got: {got!r}\n    want: {want!r}{extra}")
        print(f"  FAIL {label}")
    else:
        print(f"  ok   {label}")


def verdicts(r):
    return [(x["repo"], x["verdict"]) for x in (r["result"] or [])]


def reason_of(r, repo):
    for x in r["result"] or []:
        if x["repo"] == repo:
            return x["reason"]
    return None


# --------------------------------------------------------------------------
# verdicts


def test_all_pass():
    fx = {**green("org/api"), **green("org/ui", sha=SHA_B)}
    r = run([svc("org/api"), svc("org/ui", sha=SHA_B)], fx)
    check("all pass: exit 0", r["rc"], 0, r)
    check("all pass: both pass", verdicts(r), [("org/api", "pass"), ("org/ui", "pass")], r)
    check("all pass: count line", "examined 2 services, 2 passed" in r["out"], True, r)
    check("all pass: summary has a row per service",
          ("| org/api |" in r["summary"], "| org/ui |" in r["summary"]), (True, True), r)


def test_one_red_others_still_reported():
    fx = {**light_tag("org/api", "v1.0.0", SHA_A),
          **checks("org/api", SHA_A, [run_(1, conclusion="failure")]),
          **green("org/ui", sha=SHA_B)}
    r = run([svc("org/api"), svc("org/ui", sha=SHA_B)], fx)
    check("one red: exit 1", r["rc"], 1, r)
    check("one red: every service reported",
          verdicts(r), [("org/api", "fail"), ("org/ui", "pass")], r)
    check("one red: reason names the conclusion", reason_of(r, "org/api"), "conclusion=failure", r)
    check("one red: count line", "examined 2 services, 1 passed" in r["out"], True, r)


def test_check_missing():
    fx = {**light_tag("org/api", "v1.0.0", SHA_A), **checks("org/api", SHA_A, [])}
    r = run([svc()], fx)
    check("missing: exit 1", r["rc"], 1, r)
    check("missing: reason", reason_of(r, "org/api"), "no release-gate run", r)


def test_not_finished_is_never_waited_on():
    for status in ("queued", "in_progress"):
        fx = {**light_tag("org/api", "v1.0.0", SHA_A),
              **checks("org/api", SHA_A, [run_(1, status=status, conclusion=None)])}
        r = run([svc()], fx)
        check(f"{status}: exit 1", r["rc"], 1, r)
        check(f"{status}: reason", reason_of(r, "org/api"),
              f"not finished: status={status} (never waited on)", r)
        check(f"{status}: one check-runs read, no polling",
              sum("check-runs" in c[-1] for c in r["calls"]), 1, r)


def test_neutral_and_skipped_fail():
    for conclusion in ("neutral", "skipped", "cancelled"):
        fx = {**light_tag("org/api", "v1.0.0", SHA_A),
              **checks("org/api", SHA_A, [run_(1, conclusion=conclusion)])}
        r = run([svc()], fx)
        check(f"{conclusion}: exit 1", r["rc"], 1, r)
        check(f"{conclusion}: reason", reason_of(r, "org/api"), f"conclusion={conclusion}", r)


def test_newest_run_wins():
    older_green_newer_red = [run_(1, started="2026-10-08T10:00:00Z"),
                             run_(2, conclusion="failure", started="2026-10-08T11:00:00Z")]
    fx = {**light_tag("org/api", "v1.0.0", SHA_A), **checks("org/api", SHA_A, older_green_newer_red)}
    r = run([svc()], fx)
    check("older green, newer red: fail", (r["rc"], verdicts(r)), (1, [("org/api", "fail")]), r)

    # Listed newest-first, as the API does — order of the array must not decide.
    older_red_newer_green = [run_(4, started="2026-10-08T11:00:00Z"),
                             run_(3, conclusion="failure", started="2026-10-08T10:00:00Z")]
    fx = {**light_tag("org/api", "v1.0.0", SHA_A), **checks("org/api", SHA_A, older_red_newer_green)}
    r = run([svc()], fx)
    check("older red, newer green: pass", (r["rc"], verdicts(r)), (0, [("org/api", "pass")]), r)

    # Same started_at: the higher id (created later) is the newer run.
    tie = [run_(6, conclusion="failure", started="2026-10-08T10:00:00Z"),
           run_(5, started="2026-10-08T10:00:00Z")]
    fx = {**light_tag("org/api", "v1.0.0", SHA_A), **checks("org/api", SHA_A, tie)}
    r = run([svc()], fx)
    check("tie on started_at: higher id wins", verdicts(r), [("org/api", "fail")], r)


def test_other_app_same_name_ignored():
    fx = {**light_tag("org/api", "v1.0.0", SHA_A),
          **checks("org/api", SHA_A, [run_(1, app="some-other-app")])}
    r = run([svc()], fx)
    check("other app: exit 1", r["rc"], 1, r)
    check("other app: treated as missing", reason_of(r, "org/api"), "no release-gate run", r)


def test_check_name_override_is_sent():
    fx = {**light_tag("org/api", "v1.0.0", SHA_A),
          **checks("org/api", SHA_A, [run_(1, name="actionlint + shellcheck")])}
    r = run([svc()], fx, check_name="actionlint + shellcheck")
    check("check_name override: pass", r["rc"], 0, r)
    sent = [c[-1] for c in r["calls"] if "check-runs" in c[-1]]
    check("check_name override: url-encoded in the query",
          ["repos/org/api/commits/" + SHA_A
           + "/check-runs?check_name=actionlint%20%2B%20shellcheck&filter=all&per_page=100"],
          sent, r)


# --------------------------------------------------------------------------
# the tag


def test_annotated_tag_peeled():
    fx = {**annotated_tag("org/api", "v1.0.0", SHA_T, SHA_A), **checks("org/api", SHA_A, [run_(1)])}
    r = run([svc()], fx)
    check("annotated tag: pass", (r["rc"], verdicts(r)), (0, [("org/api", "pass")]), r)


def test_lightweight_tag():
    r = run([svc()], green())
    check("lightweight tag: pass", (r["rc"], verdicts(r)), (0, [("org/api", "pass")]), r)


def test_tag_moved():
    fx = {**light_tag("org/api", "v1.0.0", SHA_B), **checks("org/api", SHA_A, [run_(1)])}
    r = run([svc()], fx)
    check("tag moved: exit 1", r["rc"], 1, r)
    check("tag moved: reason names where it points", reason_of(r, "org/api"),
          f"tag moved: points at {SHA_B}", r)


def test_tag_missing():
    fx = checks("org/api", SHA_A, [run_(1)])
    r = run([svc()], fx)
    check("tag missing: exit 1", r["rc"], 1, r)
    check("tag missing: reason", reason_of(r, "org/api"), "tag missing", r)


def test_tag_peel_loop_is_bounded():
    # A tag object that points at itself must not spin forever.
    fx = {f"repos/org/api/git/ref/tags/v1.0.0":
          {"body": {"object": {"type": "tag", "sha": SHA_T}}},
          f"repos/org/api/git/tags/{SHA_T}":
          {"body": {"object": {"type": "tag", "sha": SHA_T}}},
          **checks("org/api", SHA_A, [run_(1)])}
    r = run([svc()], fx)
    check("peel loop: exit 1", r["rc"], 1, r)
    check("peel loop: at most 5 hops", sum("git/tags/" in c[-1] for c in r["calls"]) <= 5, True, r)


# --------------------------------------------------------------------------
# input validation — fails before any API call


def test_bad_input_fails_before_any_call():
    cases = {
        "empty array": "[]",
        "malformed JSON": "[{",
        "not an array": json.dumps(svc()),
        "bad sha": json.dumps([svc(sha="abc")]),
        "uppercase sha": json.dumps([svc(sha="A" * 40)]),
        "empty tag": json.dumps([svc(tag="")]),
        "bad repo": json.dumps([svc(repo="no-slash")]),
        "repo with path traversal": json.dumps([svc(repo="org/../x")]),
        "missing field": json.dumps([{"repo": "org/api", "tag": "v1.0.0"}]),
        "empty string": "",
    }
    for label, raw in cases.items():
        r = run(None, green(), raw_services=raw)
        check(f"invalid ({label}): exit 1", r["rc"], 1, r)
        check(f"invalid ({label}): no API call made", r["calls"], [], r)
        check(f"invalid ({label}): count line states 0 examined",
              "examined 0 services, 0 passed" in r["out"], True, r)


# --------------------------------------------------------------------------
# API errors fail closed


def test_api_500_fails_closed():
    fx = {**light_tag("org/api", "v1.0.0", SHA_A),
          f"repos/org/api/commits/{SHA_A}/check-runs": {"status": 500, "body": {"message": "boom"}},
          **green("org/ui", sha=SHA_B)}
    r = run([svc("org/api"), svc("org/ui", sha=SHA_B)], fx)
    check("API 500: exit 1", r["rc"], 1, r)
    check("API 500: other service still reported",
          verdicts(r), [("org/api", "fail"), ("org/ui", "pass")], r)
    check("API 500: reason names the HTTP status",
          "HTTP 500" in (reason_of(r, "org/api") or ""), True, r)


def test_tag_lookup_500_is_not_tag_missing():
    fx = {f"repos/org/api/git/ref/tags/v1.0.0": {"status": 502, "body": {}},
          **checks("org/api", SHA_A, [run_(1)])}
    r = run([svc()], fx)
    check("tag 502: exit 1", r["rc"], 1, r)
    check("tag 502: reason names the HTTP status, not 'missing'",
          "HTTP 502" in (reason_of(r, "org/api") or ""), True, r)


def main():
    if not SCRIPT.is_file():
        print(f"::error::{SCRIPT.relative_to(ROOT)} does not exist")
        return 1
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        print(t.__name__)
        t()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"All {len(tests)} check-release-gate test groups passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
