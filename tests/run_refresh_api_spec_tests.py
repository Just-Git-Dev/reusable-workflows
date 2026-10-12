#!/usr/bin/env python3
"""Self-test for actions/refresh-api-spec/refresh.sh — the scheduled spec refresher.

The action can MERGE into a consumer's default branch on its own, so its failure
modes are a merged non-spec (an HTML page served with a 200), a merge whose checks
failed, or a leaked access header. Every case runs the SHIPPED script (no copy)
with real `curl` against a local HTTP server serving fixtures, a temporary git repo
pushing to a bare remote, and a `gh` stub that logs every call — so what was
pushed, opened and merged is asserted, not assumed.

The live positive control (real GitHub PR + merge) is not here — see
docs/refresh-api-spec.md "Verification".

Usage:  python3 tests/run_refresh_api_spec_tests.py
Needs:  bash, curl, git, yq (mikefarah v4; preinstalled on GitHub's Ubuntu runners).
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "actions" / "refresh-api-spec" / "refresh.sh"

FAILURES = []
PR_URL = "https://github.com/org/consumer/pull/7"
BRANCH = "spec-refresh/api"

# --------------------------------------------------------------------------
# Local provider: ROUTES maps a path to (status, body, content-type); anything
# else is a 404. Every request's headers are recorded in REQUESTS.

ROUTES = {}
REQUESTS = []


class Provider(BaseHTTPRequestHandler):
    def do_GET(self):
        REQUESTS.append({"path": self.path, "headers": dict(self.headers)})
        status, body, ctype = ROUTES.get(self.path, (404, "not found", "text/plain"))
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


SERVER = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
BASE_URL = f"http://127.0.0.1:{SERVER.server_address[1]}"

# A `gh` stand-in. Every call's argv is appended to $GH_LOG as JSON; a
# `--body-file` is read at call time and logged too. `pr list` prints the
# contents of $GH_PR_LIST (an open PR's URL, or nothing).
GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
entry = {"argv": args}
if "--body-file" in args:
    entry["body"] = open(args[args.index("--body-file") + 1]).read()
with open(os.environ["GH_LOG"], "a") as f:
    f.write(json.dumps(entry) + "\n")
sub = args[:2]
if sub == ["repo", "view"]:
    print("main")
elif sub == ["pr", "list"]:
    print(open(os.environ["GH_PR_LIST"]).read().strip())
elif sub == ["pr", "create"]:
    print("https://github.com/org/consumer/pull/7")
elif sub in (["pr", "merge"], ["pr", "comment"]):
    pass
else:
    sys.stderr.write(f"stub: unsupported gh {args}\n"); sys.exit(2)
'''

V1 = {"openapi": "3.0.3", "info": {"title": "api", "version": "1.0.0"},
      "paths": {"/a": {"get": {"responses": {"200": {"description": "ok"}}}}}}
V2 = {"openapi": "3.0.3", "info": {"title": "api", "version": "1.1.0"},
      "paths": {"/a": {"get": {"responses": {"200": {"description": "ok"}}}},
                "/b": {"post": {"responses": {"201": {"description": "made"}}}}}}

# V1 as YAML, keys in a different order from the JSON — same meaning.
V1_YAML = """\
info:
  version: 1.0.0
  title: api
openapi: 3.0.3
paths:
  /a:
    get:
      responses:
        "200":
          description: ok
"""

HTML = "<!DOCTYPE html>\n<html><head><title>Swagger UI</title></head><body></body></html>\n"


def git_env(extra=None):
    """A git env with every hook-inherited GIT_* var scrubbed, no global/system
    config (no global hooks, no url rewrites), and a fixed identity."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})
    if extra:
        env.update(extra)
    return env


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=git_env(), check=True,
                          capture_output=True, text=True).stdout


def make_repo(tmp, copy_path, copy_body, *, remote_branch_junk=False):
    remote = tmp / "remote.git"
    work = tmp / "work"
    git(tmp, "init", "-q", "--bare", "-b", "main", str(remote))
    git(tmp, "init", "-q", "-b", "main", str(work))
    git(work, "remote", "add", "origin", str(remote))
    (work / "README.md").write_text("consumer\n")
    if copy_body is not None:
        p = work / copy_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(copy_body)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "init")
    git(work, "push", "-q", "origin", "main")
    if remote_branch_junk:
        git(work, "checkout", "-q", "-b", BRANCH)
        (work / "junk.txt").write_text("stale attempt\n")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "stale")
        git(work, "push", "-q", "origin", BRANCH)
        git(work, "checkout", "-q", "main")
        git(work, "branch", "-q", "-D", BRANCH)
    return remote, work


def run(served, *, copy_path="spec/openapi.json", copy_body=None, check_command="true",
        update_command="", request_headers="", merge_method=None, open_pr="",
        remote_branch_junk=False, dirty=False, path="/.well-known/openapi.json",
        name="api"):
    """served: (status, body, ctype) for `path`, or None for no route (404)."""
    ROUTES.clear()
    REQUESTS.clear()
    if served is not None:
        ROUTES[path] = served
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        remote, work = make_repo(tmp, copy_path, copy_body,
                                 remote_branch_junk=remote_branch_junk)
        if dirty:
            (work / "stray.txt").write_text("left by a setup step\n")
        bin_ = tmp / "bin"
        bin_.mkdir()
        (bin_ / "gh").write_text(GH_STUB)
        (bin_ / "gh").chmod(0o755)
        (tmp / "prlist").write_text(open_pr)
        (tmp / "rt").mkdir()
        env = git_env({
            "PATH": f"{bin_}:{os.environ['PATH']}",
            "GH_LOG": str(tmp / "gh.log"),
            "GH_PR_LIST": str(tmp / "prlist"),
            "GH_TOKEN": "stub-token",
            "GITHUB_OUTPUT": str(tmp / "out.txt"),
            "GITHUB_STEP_SUMMARY": str(tmp / "summary.md"),
            "GITHUB_REPOSITORY": "org/consumer",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_RUN_ID": "42",
            "RUNNER_TEMP": str(tmp / "rt"),
            "SPEC_NAME": name,
            "SPEC_URL": f"{BASE_URL}{path}",
            "COPY_PATH": copy_path,
            "CHECK_COMMAND": check_command,
            "UPDATE_COMMAND": update_command,
            "REQUEST_HEADERS": request_headers,
        })
        if merge_method is not None:
            env["MERGE_METHOD"] = merge_method
        proc = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                              env=env, cwd=work)
        out = tmp / "out.txt"
        outputs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l) \
            if out.exists() else {}
        log = tmp / "gh.log"
        calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        heads = git(tmp, "--git-dir", str(remote), "for-each-ref", "--format=%(refname)",
                    "refs/heads/")
        branch_files = {}
        if f"refs/heads/{BRANCH}" in heads.split():
            files = git(tmp, "--git-dir", str(remote), "ls-tree", "-r", "--name-only", BRANCH)
            for f in files.split():
                branch_files[f] = git(tmp, "--git-dir", str(remote), "show", f"{BRANCH}:{f}")
            branch_log = git(tmp, "--git-dir", str(remote), "log", "--format=%an|%s",
                             f"main..{BRANCH}")
        else:
            branch_log = ""
        main_log = git(tmp, "--git-dir", str(remote), "log", "--format=%s", "main")
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "outputs": outputs, "calls": calls, "heads": heads.split(),
                "branch_files": branch_files, "branch_log": branch_log.splitlines(),
                "main_log": main_log.splitlines(), "ran_check": (work / ".check-ran").exists(),
                "requests": list(REQUESTS)}


def check(label, got, want, ctx=None):
    if got != want:
        extra = f"\n    output:\n{ctx['out']}" if ctx else ""
        FAILURES.append(f"{label}\n     got: {got!r}\n    want: {want!r}{extra}")
        print(f"  FAIL {label}")
    else:
        print(f"  ok   {label}")


def gh_subs(r):
    return [" ".join(c["argv"][:2]) for c in r["calls"]]


def call(r, sub):
    for c in r["calls"]:
        if " ".join(c["argv"][:2]) == sub:
            return c
    return None


def jsn(o, indent=2):
    return json.dumps(o, indent=indent) + "\n"


CHECK_OK = "touch .check-ran"
PUSHED = f"refs/heads/{BRANCH}"


# --------------------------------------------------------------------------
# Unchanged — nothing pushed, nothing opened, checks not run


def test_unchanged_json():
    served = (200, json.dumps(V1, separators=(",", ":"), sort_keys=True), "application/json")
    r = run(served, copy_body=jsn(V1), check_command=CHECK_OK)
    check("unchanged: exit 0", r["rc"], 0, r)
    check("unchanged: changed=false", r["outputs"].get("changed"), "false", r)
    check("unchanged: checks=skipped", r["outputs"].get("checks"), "skipped", r)
    check("unchanged: no branch pushed", PUSHED in r["heads"], False, r)
    check("unchanged: no PR created or merged",
          [s for s in gh_subs(r) if s in ("pr create", "pr merge")], [], r)
    check("unchanged: check_command not run", r["ran_check"], False, r)


def test_json_served_yaml_copy_same_meaning():
    served = (200, json.dumps(V1), "application/json")
    r = run(served, copy_path="spec/openapi.yaml", copy_body=V1_YAML, check_command=CHECK_OK)
    check("json vs yaml same meaning: exit 0", r["rc"], 0, r)
    check("json vs yaml same meaning: changed=false", r["outputs"].get("changed"), "false", r)
    check("json vs yaml same meaning: no branch pushed", PUSHED in r["heads"], False, r)


def test_unchanged_with_open_pr_left_alone():
    served = (200, json.dumps(V1), "application/json")
    r = run(served, copy_body=jsn(V1), open_pr=PR_URL)
    check("unchanged + open PR: exit 0", r["rc"], 0, r)
    check("unchanged + open PR: not merged or closed",
          [s for s in gh_subs(r) if s in ("pr merge", "pr close")], [], r)
    check("unchanged + open PR: notice names the PR", PR_URL in r["out"], True, r)


# --------------------------------------------------------------------------
# Changed


def test_changed_checks_pass_merges():
    served = (200, json.dumps(V2), "application/json")
    r = run(served, copy_body=jsn(V1), check_command=CHECK_OK)
    check("changed+pass: exit 0", r["rc"], 0, r)
    check("changed+pass: changed=true", r["outputs"].get("changed"), "true", r)
    check("changed+pass: checks=passed", r["outputs"].get("checks"), "passed", r)
    check("changed+pass: pr_url output", r["outputs"].get("pr_url"), PR_URL, r)
    check("changed+pass: branch pushed", PUSHED in r["heads"], True, r)
    body = r["branch_files"].get("spec/openapi.json", "")
    check("changed+pass: copy on branch is the new spec",
          json.loads(body) if body else None, V2, r)
    check("changed+pass: copy written as pretty JSON", body.startswith("{\n"), True, r)
    check("changed+pass: one commit, by github-actions[bot]",
          [l.split("|")[0] for l in r["branch_log"]], ["github-actions[bot]"], r)
    check("changed+pass: main untouched by the action", r["main_log"], ["init"], r)
    create = call(r, "pr create")
    argv = create["argv"] if create else []
    check("changed+pass: PR created against main from the fixed branch",
          ("--base" in argv and argv[argv.index("--base") + 1] == "main"
           and "--head" in argv and argv[argv.index("--head") + 1] == BRANCH), True, r)
    check("changed+pass: PR title",
          "--title" in argv and argv[argv.index("--title") + 1] == "chore: refresh api API spec",
          True, r)
    merge = call(r, "pr merge")
    margv = merge["argv"] if merge else []
    check("changed+pass: merged with --squash --delete-branch",
          ("--squash" in margv and "--delete-branch" in margv and PR_URL in margv), True, r)
    check("changed+pass: merge pinned to the pushed head",
          "--match-head-commit" in margv, True, r)
    check("changed+pass: check_command ran", r["ran_check"], True, r)


def test_changed_checks_fail_not_merged():
    served = (200, json.dumps(V2), "application/json")
    r = run(served, copy_body=jsn(V1),
            check_command="echo contract-mismatch-detail; exit 3")
    check("changed+fail: exit 1", r["rc"], 1, r)
    check("changed+fail: checks=failed", r["outputs"].get("checks"), "failed", r)
    check("changed+fail: PR created", "pr create" in gh_subs(r), True, r)
    check("changed+fail: NOT merged", "pr merge" in gh_subs(r), False, r)
    comment = call(r, "pr comment")
    check("changed+fail: PR comment carries the check output",
          "contract-mismatch-detail" in (comment or {}).get("body", ""), True, r)
    check("changed+fail: branch pushed for the human to look at", PUSHED in r["heads"], True, r)


def test_existing_pr_updated_not_duplicated():
    served = (200, json.dumps(V2), "application/json")
    r = run(served, copy_body=jsn(V1), open_pr=PR_URL, remote_branch_junk=True)
    check("existing PR: exit 0", r["rc"], 0, r)
    check("existing PR: no second PR created", "pr create" in gh_subs(r), False, r)
    merge = call(r, "pr merge")
    check("existing PR: the open PR is merged", PR_URL in (merge or {}).get("argv", []), True, r)
    check("existing PR: branch force-pushed from main (stale commit gone)",
          "junk.txt" in r["branch_files"], False, r)
    check("existing PR: branch has exactly one commit on top of main",
          len(r["branch_log"]), 1, r)


def test_yaml_copy_written_as_yaml():
    served = (200, json.dumps(V2), "application/json")
    r = run(served, copy_path="spec/openapi.yml", copy_body=V1_YAML)
    check("yaml copy changed: exit 0", r["rc"], 0, r)
    body = r["branch_files"].get("spec/openapi.yml", "")
    check("yaml copy changed: written as YAML, not JSON",
          (not body.lstrip().startswith("{")) and "openapi:" in body and "/b:" in body, True, r)


def test_first_adoption_copy_absent():
    served = (200, json.dumps(V1), "application/json")
    r = run(served, copy_body=None)
    check("copy absent: exit 0", r["rc"], 0, r)
    check("copy absent: changed=true", r["outputs"].get("changed"), "true", r)
    check("copy absent: copy created on branch",
          "spec/openapi.json" in r["branch_files"], True, r)


def test_update_command_runs_before_checks():
    served = (200, json.dumps(V2), "application/json")
    r = run(served, copy_body=jsn(V1),
            update_command="grep -q '/b' spec/openapi.json && printf generated > gen.txt",
            check_command="grep -q generated gen.txt")
    check("update_command: exit 0 (checks saw its output)", r["rc"], 0, r)
    check("update_command: its file committed with the copy",
          r["branch_files"].get("gen.txt"), "generated", r)


def test_update_command_fails_no_push():
    served = (200, json.dumps(V2), "application/json")
    r = run(served, copy_body=jsn(V1), update_command="exit 4")
    check("update_command fails: exit 1", r["rc"], 1, r)
    check("update_command fails: nothing pushed", PUSHED in r["heads"], False, r)
    check("update_command fails: no PR", "pr create" in gh_subs(r), False, r)


# --------------------------------------------------------------------------
# Refusals — a wrong URL is a red run, never a merged non-spec


def test_http_404_fails():
    r = run(None, copy_body=jsn(V1))
    check("404: exit 1", r["rc"], 1, r)
    check("404: error names the status", "HTTP 404" in r["out"], True, r)
    check("404: nothing pushed", PUSHED in r["heads"], False, r)
    check("404: no gh pr call", [s for s in gh_subs(r) if s.startswith("pr ")], [], r)


def test_html_200_fails():
    r = run((200, HTML, "text/html"), copy_body=jsn(V1))
    check("HTML 200: exit 1", r["rc"], 1, r)
    check("HTML 200: 'not an OpenAPI document'", "not an OpenAPI document" in r["out"], True, r)
    check("HTML 200: nothing pushed", PUSHED in r["heads"], False, r)


def test_json_without_openapi_key_fails():
    r = run((200, json.dumps({"status": "ok"}), "application/json"), copy_body=jsn(V1))
    check("JSON non-spec: exit 1", r["rc"], 1, r)
    check("JSON non-spec: 'not an OpenAPI document'",
          "not an OpenAPI document" in r["out"], True, r)


def test_swagger2_accepted():
    sw = {"swagger": "2.0", "info": {"title": "x", "version": "1"}, "paths": {}}
    r = run((200, json.dumps(sw), "application/json"), copy_body=jsn(V1))
    check("swagger 2.0: accepted and refreshed", (r["rc"], r["outputs"].get("changed")),
          (0, "true"), r)


def test_empty_body_fails():
    r = run((200, "", "application/json"), copy_body=jsn(V1))
    check("empty body: exit 1", r["rc"], 1, r)
    check("empty body: error says empty", "empty" in r["out"].lower(), True, r)
    check("empty body: nothing pushed", PUSHED in r["heads"], False, r)


# --------------------------------------------------------------------------
# Headers and log hygiene


def test_headers_sent_and_masked():
    secret = "s3cr3t-tok-9f8e"
    served = (200, json.dumps(V1), "application/json")
    r = run(served, copy_body=jsn(V1),
            request_headers=f"Authorization: Bearer {secret}\nX-Env: staging\n")
    check("headers: exit 0", r["rc"], 0, r)
    got = r["requests"][0]["headers"] if r["requests"] else {}
    check("headers: Authorization reached the server",
          got.get("Authorization"), f"Bearer {secret}", r)
    check("headers: second header reached the server", got.get("X-Env"), "staging", r)
    leaks = [l for l in r["out"].splitlines()
             if secret in l and not l.startswith("::add-mask::")]
    check("headers: secret only ever printed inside ::add-mask::", leaks, [], r)
    check("headers: secret was masked", f"::add-mask::Bearer {secret}" in r["out"], True, r)


def test_log_prints_host_not_path_query():
    served = (200, json.dumps(V1), "application/json")
    r = run(served, copy_body=jsn(V1), path="/.well-known/openapi.json?key=qsecret")
    check("url log: exit 0", r["rc"], 0, r)
    check("url log: query string never printed", "qsecret" in r["out"], False, r)


# --------------------------------------------------------------------------
# Input validation — fail before fetching


def test_invalid_inputs_fail_before_fetch():
    cases = {
        "bad extension": dict(copy_path="spec/openapi.txt"),
        "bad merge_method": dict(merge_method="fast-forward"),
        "bad name": dict(name="../x"),
        "empty check_command": dict(check_command=""),
    }
    for label, kw in cases.items():
        r = run((200, json.dumps(V2), "application/json"), copy_body=jsn(V1), **kw)
        check(f"invalid ({label}): exit 1", r["rc"], 1, r)
        check(f"invalid ({label}): no request made", r["requests"], [], r)


def test_dirty_tree_refused():
    r = run((200, json.dumps(V2), "application/json"), copy_body=jsn(V1), dirty=True)
    check("dirty tree: exit 1", r["rc"], 1, r)
    check("dirty tree: names the stray file", "stray.txt" in r["out"], True, r)
    check("dirty tree: nothing pushed", PUSHED in r["heads"], False, r)


def main():
    if not SCRIPT.is_file():
        print(f"::error::{SCRIPT.relative_to(ROOT)} does not exist")
        return 1
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        print(t.__name__)
        t()
    SERVER.shutdown()
    print()
    if not tests:
        print("::error::0 test groups ran")
        return 1
    if FAILURES:
        print(f"{len(FAILURES)} failure(s) across {len(tests)} test groups:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"All {len(tests)} refresh-api-spec test groups passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
