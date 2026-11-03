"""Tests for propose.py (`release-flow propose`). Self-contained: a fake GitHub transport and
a fake runner that records every git/gh argv; no real git, gh or network."""

import argparse
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gh  # noqa: E402
import manifest  # noqa: E402
import propose  # noqa: E402

TMP_ROOT = HERE.parents[2] / ".scratch" / "test-tmp"
OWNER, ROOT = "consumer-a-org", "consumer-a-org/release"
SHA = {"backend": "a" * 40, "webapp": "b" * 40, "desktop": "d" * 40}
BASE_SHA = "e" * 40
TAGOBJ = "c" * 40
RUN_URL = "https://github.com/consumer-a-org/{r}/actions/runs/{n}"
CFG = {
    "owner": OWNER, "gar_registry": "r.example/p",
    "services": [
        {"repo": "backend", "kind": "image", "order": 1, "deploy_workflow": "deploy.yml",
         "health_url": "https://b.example/health", "image": "b/backend", "ci": []},
        {"repo": "webapp", "kind": "pages", "order": 2, "deploy_workflow": "deploy.yml", "ci": []},
        {"repo": "desktop", "kind": "pages", "order": 3, "deploy_workflow": "deploy.yml",
         "ci": []},
    ],
}
ALLOWED = "backend,webapp,desktop"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, n):
        self.now += n


def run_of(repo, state="completed", conclusion="success", n=1, app="github-actions",
           started="2026-11-03T10:00:00Z", rid=None):
    return {"id": rid or n, "status": state, "conclusion": conclusion if state == "completed"
            else None, "app": {"slug": app}, "started_at": started,
            "html_url": RUN_URL.format(r=repo, n=n), "name": "release-gate"}


class Api:
    """Fake GitHub REST transport."""

    def __init__(self, tags, gates=None, protection=None, rules=None, versions=None,
                 changelog=True):
        self.calls = []
        self.tags = tags                      # {repo: tag}
        self.gates = gates or {r: [[run_of(r)]] for r in tags}   # {repo: [poll1, poll2...]}
        self.polls = {r: 0 for r in tags}
        self.protection = protection if protection is not None else (200, {"contexts": []})
        self.rules = rules if rules is not None else (200, [])
        self.changelog = changelog
        self.light = set()
        self.err = {}                         # repo -> list of statuses to return first

    def __call__(self, method, path, body=None):
        self.calls.append((method, path))
        p = path.split("?")[0]
        if p == f"repos/{ROOT}/branches/main/protection/required_status_checks":
            return self.protection
        if p == f"repos/{ROOT}/rules/branches/main":
            return self.rules
        parts = p.split("/")
        repo = parts[2]
        tag = self.tags.get(repo)
        sha = SHA.get(repo)
        rest = "/".join(parts[3:])
        if rest == f"git/ref/tags/{tag}":
            if repo in self.light:
                return 200, {"object": {"type": "commit", "sha": sha}}
            return 200, {"object": {"type": "tag", "sha": TAGOBJ}}
        if rest == f"git/tags/{TAGOBJ}":
            return 200, {"object": {"type": "commit", "sha": sha}}
        if rest == "git/matching-refs/tags/v":
            return 200, [{"ref": f"refs/tags/{tag}"}]
        if rest == "releases":
            return 200, []
        if rest == f"compare/main...{sha}":
            return 200, {"status": "identical"}
        if rest == f"contents/CHANGELOG.md":
            text = f"## {tag}\n- x\n" if self.changelog else "## other\n"
            return 200, {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
        if rest == f"commits/{sha}/check-runs":
            if self.err.get(repo):
                e = self.err[repo].pop(0)
                if isinstance(e, Exception):
                    raise e
                return e, {}
            seq = self.gates[repo]
            i = min(self.polls[repo], len(seq) - 1)
            self.polls[repo] += 1
            return 200, {"check_runs": seq[i]}
        return 404, {}


class Runner:
    def __init__(self, existing=(), remote_branch=False, merge_rc=0, root=ROOT,
                 origin=f"https://github.com/{ROOT}.git", pr_out=f"https://github.com/{ROOT}/pull/42\n",
                 git_path_prefix=".git/"):
        self.origin = origin
        self.pr_out = pr_out
        self.git_path_prefix = git_path_prefix
        self.calls = []                       # (argv, env, input)
        self.existing = set(existing)
        self.remote_branch = remote_branch
        self.merge_rc = merge_rc
        self.root = root

    def __call__(self, argv, env=None, input=None):
        self.calls.append((list(argv), env, input))
        a = argv
        if a[:3] == ["gh", "repo", "view"]:
            return 0, json.dumps({"nameWithOwner": self.root}), ""
        if a[:4] == ["git", "remote", "get-url", "origin"]:
            return 0, self.origin + "\n", ""
        if a[:2] == ["git", "fetch"]:
            return 0, "", ""
        if a[:2] == ["git", "rev-parse"]:
            if a[2] == "--git-path":
                return 0, self.git_path_prefix + a[3] + "\n", ""
            return 0, BASE_SHA + "\n", ""
        if a[:3] == ["git", "cat-file", "-e"]:
            return (0 if a[3].split(":", 1)[1] in self.existing else 128), "", "missing"
        if a[:2] == ["git", "ls-remote"]:
            return 0, ("1234 refs/heads/x\n" if self.remote_branch else ""), ""
        if a[:2] == ["git", "hash-object"]:
            return 0, "f" * 40 + "\n", ""
        if a[:2] == ["git", "read-tree"] or a[:2] == ["git", "update-index"]:
            return 0, "", ""
        if a[:2] == ["git", "write-tree"]:
            return 0, "9" * 40 + "\n", ""
        if a[:2] == ["git", "commit-tree"]:
            return 0, "8" * 40 + "\n", ""
        if a[:2] == ["git", "push"]:
            return 0, "", ""
        if a[:3] == ["gh", "pr", "create"]:
            return 0, self.pr_out, ""
        if a[:3] == ["gh", "pr", "merge"]:
            return self.merge_rc, "", "auto-merge is not allowed" if self.merge_rc else ""
        return 1, "", f"unexpected {a}"

    def cmds(self, *prefix):
        return [c for c in self.calls if c[0][:len(prefix)] == list(prefix)]


def parse_args(*argv):
    p = argparse.ArgumentParser()
    propose.add_arguments(p)
    return p.parse_args(list(argv))


class ProposeTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=TMP_ROOT)
        self.cfg_path = Path(self._tmp.name) / "services.json"
        self.cfg_path.write_text(json.dumps(CFG))
        self.addCleanup(self._tmp.cleanup)

    def go(self, *argv, api=None, runner=None, clock=None, env=None):
        tags = {}
        for t in argv:
            if "@" in t and not t.startswith("-"):
                r, v = t.split("@", 1)
                tags[r] = v
        api = api or Api(tags)
        runner = runner or Runner()
        clock = clock or Clock()
        lines = []
        args = parse_args(*argv, "--config", str(self.cfg_path), "--allowed", ALLOWED)
        deps = {"transport": api, "runner": runner, "clock": clock, "sleep": clock.sleep,
                "today": lambda: "2026-11-03", "out": lambda s="": lines.append(str(s))}
        rc = propose.run(args, env if env is not None else {}, deps)
        self.out = "\n".join(lines)
        self.api, self.runner, self.clock = api, runner, clock
        return rc

    def assertNothingWritten(self):
        for pre in (("git", "hash-object"), ("git", "push"), ("gh", "pr", "create"),
                    ("gh", "pr", "merge")):
            self.assertEqual(self.runner.cmds(*pre), [], pre)

    # --- arguments -------------------------------------------------------------------------
    def test_dotted_slug_refused(self):
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "fix.1"), 2)
        self.assertIn("must match [a-z0-9][a-z0-9-]*", self.out)
        self.assertNothingWritten()

    def test_upper_slug_refused(self):
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "Fix"), 2)
        self.assertIn("must match [a-z0-9][a-z0-9-]*", self.out)
        self.assertNothingWritten()

    def test_repo_outside_allowed_refused(self):
        args = parse_args("backend@v1.4.0", "--slug", "x", "--config", str(self.cfg_path),
                          "--allowed", "webapp")
        r, api = Runner(), Api({"backend": "v1.4.0"})
        rc = propose.run(args, {}, {"transport": api, "runner": r, "out": lambda s="": None,
                                    "today": lambda: "2026-11-03"})
        self.assertEqual(rc, 2)
        self.assertEqual(r.cmds("git", "push"), [])

    def test_unknown_repo_refused(self):
        self.assertEqual(self.go("nope@v1.0.0", "--slug", "x"), 2)
        self.assertNothingWritten()

    def test_duplicate_repo_refused(self):
        self.assertEqual(self.go("backend@v1.4.0", "backend@v1.4.1", "--slug", "x"), 2)
        self.assertNothingWritten()

    def test_bad_tag_format_refused(self):
        self.assertEqual(self.go("backend@1.4", "--slug", "x"), 2)
        self.assertNothingWritten()

    def test_root_owner_mismatch_refused(self):
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x",
                                 runner=Runner(root="other-org/release")), 2)
        self.assertNothingWritten()

    def test_manifest_already_on_base_refused(self):
        r = Runner(existing={"releases/2026-11-03-x.yaml"})
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", runner=r), 2)
        self.assertNothingWritten()

    def test_branch_already_on_origin_refused(self):
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x",
                                 runner=Runner(remote_branch=True)), 2)
        self.assertNothingWritten()

    def test_lightweight_tag_refused(self):
        api = Api({"backend": "v1.4.0"})
        api.light.add("backend")
        rc = self.go("backend@v1.4.0", "--slug", "x", api=api)
        self.assertEqual(rc, 1)
        self.assertIn("git tag -a", self.out)
        self.assertNothingWritten()

    # --- gates -----------------------------------------------------------------------------
    def test_gate_red_exit_1(self):
        api = Api({"backend": "v1.4.0"},
                  gates={"backend": [[run_of("backend", conclusion="failure")]]})
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 1)
        self.assertIn("gate red: backend v1.4.0 release-gate failure", self.out)
        self.assertIn("nothing was written", self.out)
        self.assertNothingWritten()

    def test_gate_never_finishes(self):
        api = Api({"backend": "v1.4.0"},
                  gates={"backend": [[run_of("backend", state="in_progress")]]})
        rc = self.go("backend@v1.4.0", "--slug", "x", "--wait-min", "2", api=api)
        self.assertEqual(rc, 1)
        self.assertIn("gate not finished after 2 min: backend v1.4.0 (in_progress)", self.out)
        self.assertGreaterEqual(self.clock.now, 120)
        self.assertLess(self.clock.now, 200)
        self.assertNothingWritten()

    def test_gate_not_started_then_green_proceeds(self):
        api = Api({"backend": "v1.4.0"},
                  gates={"backend": [[], [], [run_of("backend", state="queued")],
                                     [run_of("backend")]]})
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)
        self.assertEqual(len(self.runner.cmds("git", "push")), 1)

    def test_gate_reading_ignores_other_apps_and_picks_newest(self):
        old_red = run_of("backend", conclusion="failure", n=1, started="2026-11-03T09:00:00Z")
        new_green = run_of("backend", n=2, started="2026-11-03T10:00:00Z")
        other = run_of("backend", conclusion="failure", n=3, app="evil",
                       started="2026-11-03T11:00:00Z")
        api = Api({"backend": "v1.4.0"}, gates={"backend": [[old_red, new_green, other]]})
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)

    def test_gate_tie_broken_by_higher_id(self):
        a = run_of("backend", conclusion="failure", rid=1)
        b = run_of("backend", rid=2)
        # the winner (higher id) is LAST, so a key without the id tie-break picks the red one
        api = Api({"backend": "v1.4.0"}, gates={"backend": [[a, b]]})
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)

    def test_gate_5xx_retried_then_ok(self):
        api = Api({"backend": "v1.4.0"})
        api.err["backend"] = [502, 503]
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)

    def test_gate_five_5xx_in_a_row_exit_3(self):
        api = Api({"backend": "v1.4.0"})
        api.err["backend"] = [500] * 5
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 3)
        self.assertNothingWritten()
        self.assertEqual(len([p for _, p in api.calls if "check-runs" in p]), 5)

    def test_gate_four_5xx_then_green_proceeds(self):
        api = Api({"backend": "v1.4.0"})
        api.err["backend"] = [500, 502, 503, 504]
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)
        self.assertEqual(len([p for _, p in api.calls if "check-runs" in p]), 5)

    def test_gate_network_errors_retried_then_ok(self):
        api = Api({"backend": "v1.4.0"})
        api.err["backend"] = [gh.GitHubError("network down", 0), gh.GitHubError("reset", 0)]
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)
        self.assertEqual(len([p for _, p in api.calls if "check-runs" in p]), 3)

    def test_gate_five_network_errors_in_a_row_exit_3(self):
        api = Api({"backend": "v1.4.0"})
        api.err["backend"] = [gh.GitHubError("network down", 0)] * 5
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 3)
        self.assertNothingWritten()

    def test_gate_query_names_check_and_sha(self):
        self.go("backend@v1.4.0", "--slug", "x", "--gate-check", "gate x")
        q = [p for m, p in self.api.calls if "check-runs" in p][0]
        self.assertIn(f"repos/{OWNER}/backend/commits/{SHA['backend']}/check-runs?", q)
        self.assertIn("check_name=gate%20x", q)

    # --- validate / manifest ---------------------------------------------------------------
    def test_validate_failure_exit_1(self):
        api = Api({"backend": "v1.4.0"}, changelog=False)
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 1)
        self.assertIn("FAIL: backend:", self.out)
        self.assertIn("nothing was written", self.out)
        self.assertNothingWritten()

    def test_happy_path(self):
        rc = self.go("webapp@v2.0.1", "backend@v1.4.0", "--slug", "backend-fix",
                     api=Api({"webapp": "v2.0.1", "backend": "v1.4.0"}), runner=Runner())
        self.assertEqual(rc, 0, self.out)
        blobs = self.runner.cmds("git", "hash-object")
        self.assertEqual(len(blobs), 1)
        self.assertEqual(blobs[0][0], ["git", "hash-object", "-w", "--stdin"])
        entries = manifest.parse(blobs[0][2])
        self.assertEqual([tuple(e) for e in entries],
                         [("backend", "v1.4.0", SHA["backend"]),
                          ("webapp", "v2.0.1", SHA["webapp"])])  # services.json order
        ui = self.runner.cmds("git", "update-index")[0][0]
        self.assertIn("100644,%s,releases/2026-11-03-backend-fix.yaml" % ("f" * 40), ui[-1])
        pushes = self.runner.cmds("git", "push")
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0][0], ["git", "push", "origin",
                                        "8" * 40 + ":refs/heads/release/2026-11-03-backend-fix"])
        ct = self.runner.cmds("git", "commit-tree")[0][0]
        self.assertEqual(ct[2:4], ["9" * 40, "-p"])
        self.assertEqual(ct[4], BASE_SHA)
        prs = self.runner.cmds("gh", "pr", "create")
        self.assertEqual(len(prs), 1)
        argv = prs[0][0]
        self.assertEqual(argv[argv.index("--head") + 1], "release/2026-11-03-backend-fix")
        self.assertEqual(argv[argv.index("--base") + 1], "main")
        self.assertEqual(argv[argv.index("--repo") + 1], ROOT)
        self.assertEqual(argv[argv.index("--title") + 1],
                         "release: backend v1.4.0, webapp v2.0.1")
        body = argv[argv.index("--body") + 1]
        self.assertIn(SHA["backend"], body)
        self.assertIn(RUN_URL.format(r="backend", n=1), body)
        self.assertIn("PR opened: https://github.com/consumer-a-org/release/pull/42", self.out)
        self.assertIn("validate: 2 service(s), 0 failure(s)", self.out)

    def test_temp_index_env_only_for_index_commands(self):
        self.go("backend@v1.4.0", "--slug", "x", env={"GIT_DIR": "/x", "GIT_INDEX_FILE": "/y",
                                                       "PATH": "/bin"})
        index_cmds = {"read-tree", "update-index", "write-tree"}
        seen = set()
        for argv, env, _ in self.runner.calls:
            has = bool(env) and "GIT_INDEX_FILE" in env
            if argv[0] == "git" and argv[1] in index_cmds:
                seen.add(argv[1])
                self.assertEqual(env["GIT_INDEX_FILE"],
                                 os.path.abspath(".git/release-flow-propose.index"))
            else:
                self.assertFalse(has, argv)
            if env:
                self.assertNotIn("GIT_DIR", env)
                self.assertEqual(env.get("PATH"), "/bin")
        self.assertEqual(seen, index_cmds)
        rt = self.runner.cmds("git", "read-tree")[0][0]
        self.assertEqual(rt, ["git", "read-tree", BASE_SHA])

    def test_base_is_recorded_once(self):
        self.go("backend@v1.4.0", "--slug", "x")
        argvs = [c[0] for c in self.runner.calls]
        i = argvs.index(["git", "rev-parse", "origin/main"])
        for argv in argvs[i + 1:]:
            self.assertFalse([x for x in argv if "origin/main" in x], argv)
        cat = self.runner.cmds("git", "cat-file")[0][0]
        self.assertEqual(cat[3], f"{BASE_SHA}:releases/2026-11-03-x.yaml")

    def test_git_env_scrubbed_from_every_call(self):
        env = {"PATH": "/bin", "GIT_DIR": "/x", "GIT_CONFIG_PARAMETERS": "'a.b=c'",
               "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "url.x.insteadOf",
               "GIT_CONFIG_VALUE_0": "y", "GIT_CONFIG_KEY_12": "k", "GIT_CONFIG_VALUE_12": "v",
               "GIT_CONFIG": "/c", "GIT_WORK_TREE": "/w", "GIT_NO_REPLACE_OBJECTS": "1",
               "GIT_SHALLOW_FILE": "/s", "GIT_COMMON_DIR": "/cd", "GIT_GRAFT_FILE": "/g",
               "GIT_REPLACE_REF_BASE": "r", "GIT_IMPLICIT_WORK_TREE": "0",
               "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/a", "GIT_OBJECT_DIRECTORY": "/o",
               "GIT_PREFIX": "p", "GIT_INDEX_FILE": "/i", "GIT_AUTHOR_NAME": "keep"}
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", env=env), 0)
        self.assertTrue(self.runner.calls)
        for argv, e, _ in self.runner.calls:
            bad = [k for k in e if k.startswith("GIT_") and k != "GIT_AUTHOR_NAME"
                   and not (k == "GIT_INDEX_FILE" and argv[:2] in (
                       ["git", "read-tree"], ["git", "update-index"], ["git", "write-tree"]))]
            self.assertEqual(bad, [], argv)
            self.assertEqual(e.get("PATH"), "/bin")
            self.assertEqual(e.get("GIT_AUTHOR_NAME"), "keep")

    def test_relative_git_path_index_is_made_absolute(self):
        r = Runner(git_path_prefix="rel/.git/")
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", runner=r), 0)
        idx = r.cmds("git", "read-tree")[0][1]["GIT_INDEX_FILE"]
        self.assertTrue(os.path.isabs(idx), idx)
        self.assertTrue(idx.endswith("rel/.git/release-flow-propose.index"), idx)

    # --- origin must be the root --------------------------------------------------------------
    def test_origin_forms_accepted(self):
        for url in (f"https://github.com/{ROOT}", f"https://github.com/{ROOT}.git",
                    f"git@github.com:{ROOT}.git", f"git@github.com:{ROOT}",
                    f"ssh://git@github.com/{ROOT}.git", f"ssh://git@github.com/{ROOT}",
                    f"https://github.com/{ROOT.upper()}.git"):
            with self.subTest(url=url):
                self.assertEqual(self.go("backend@v1.4.0", "--slug", "x",
                                         runner=Runner(origin=url)), 0, self.out)

    def test_fork_or_unparseable_origin_refused_before_fetch(self):
        for url in ("https://github.com/someone/release.git", "git@github.com:someone/release.git",
                    f"https://github.com/{ROOT}-fork.git", "/local/path/release",
                    f"https://evil.example/{ROOT}.git", "", f"https://github.com/{ROOT}/extra"):
            with self.subTest(url=url):
                r = Runner(origin=url)
                self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", runner=r), 2)
                self.assertEqual(r.cmds("git", "fetch"), [])
                self.assertNothingWritten()

    # --- PR url ----------------------------------------------------------------------------
    def test_pr_create_output_must_be_a_root_pull_url(self):
        def api():
            return Api({"backend": "v1.4.0"},
                       protection=(200, {"contexts": ["release-pr / release-pr"]}))
        for out in ("", "\n", "https://github.com/other/repo/pull/3\n", "created ok\n",
                    f"https://github.com/{ROOT}/pull/x\n"):
            with self.subTest(out=out):
                r = Runner(pr_out=out)
                self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api(), runner=r), 3)
                self.assertEqual(r.cmds("gh", "pr", "merge"), [])
        r = Runner(pr_out=f"warning: x\nhttps://github.com/{ROOT.upper()}/pull/7\n\n")
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api(), runner=r), 0)
        self.assertEqual(len(r.cmds("gh", "pr", "merge")), 1)

    def test_never_touches_worktree(self):
        self.go("backend@v1.4.0", "--slug", "x")
        for argv, _, _ in self.runner.calls:
            if argv[0] == "git":
                self.assertNotIn(argv[1], {"checkout", "add", "commit", "reset", "switch",
                                           "stash", "restore", "merge"})

    # --- auto-merge ------------------------------------------------------------------------
    def test_auto_merge_on_when_classic_requires_pr_check(self):
        api = Api({"backend": "v1.4.0"}, protection=(200, {"contexts": ["release-pr / release-pr"]}))
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)
        m = self.runner.cmds("gh", "pr", "merge")
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0][0], ["gh", "pr", "merge", f"https://github.com/{ROOT}/pull/42",
                                   "--auto", "--squash"])
        self.assertIn("auto-merge: on (release-pr / release-pr is required on main)", self.out)

    def test_auto_merge_on_via_checks_list(self):
        api = Api({"backend": "v1.4.0"}, protection=(200, {"contexts": [], "checks": [
            {"context": "release-pr / release-pr", "app_id": None}]}))
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)
        self.assertEqual(len(self.runner.cmds("gh", "pr", "merge")), 1)

    def test_auto_merge_on_via_ruleset(self):
        rules = (200, [{"type": "deletion"}, {"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "release-pr / release-pr"}]}}])
        api = Api({"backend": "v1.4.0"}, protection=(404, {}), rules=rules)
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)
        self.assertEqual(len(self.runner.cmds("gh", "pr", "merge")), 1)

    def test_merge_method_flag(self):
        api = Api({"backend": "v1.4.0"}, protection=(200, {"contexts": ["release-pr / release-pr"]}))
        self.go("backend@v1.4.0", "--slug", "x", "--merge-method", "rebase", api=api)
        self.assertEqual(self.runner.cmds("gh", "pr", "merge")[0][0][-2:], ["--auto", "--rebase"])

    def test_auto_merge_off_when_check_not_required(self):
        api = Api({"backend": "v1.4.0"}, protection=(200, {"contexts": ["other"]}))
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)
        self.assertEqual(self.runner.cmds("gh", "pr", "merge"), [])
        self.assertIn("auto-merge: off (release-pr / release-pr is not a required check on "
                      "main, so --auto would merge at once untested); merge by hand once it "
                      "is green", self.out)

    def test_auto_merge_off_when_protection_unreadable(self):
        for st in (404, 403):
            api = Api({"backend": "v1.4.0"}, protection=(st, {}), rules=(st, {}))
            self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", api=api), 0)
            self.assertEqual(self.runner.cmds("gh", "pr", "merge"), [])
            self.assertIn("auto-merge: off", self.out)
            self.assertIn(f"HTTP {st}", self.out)
            self.assertEqual(len(self.runner.cmds("gh", "pr", "create")), 1)

    def test_merge_failure_prints_command_exit_0(self):
        api = Api({"backend": "v1.4.0"}, protection=(200, {"contexts": ["release-pr / release-pr"]}))
        rc = self.go("backend@v1.4.0", "--slug", "x", api=api, runner=Runner(merge_rc=1))
        self.assertEqual(rc, 0)
        self.assertIn("auto-merge: off (gh pr merge failed: auto-merge is not allowed); run: "
                      f"! gh pr merge https://github.com/{ROOT}/pull/42 --auto --squash",
                      self.out)

    def test_no_auto_merge_skips_protection_read(self):
        self.assertEqual(self.go("backend@v1.4.0", "--slug", "x", "--no-auto-merge"), 0)
        self.assertEqual(self.runner.cmds("gh", "pr", "merge"), [])
        self.assertFalse([p for _, p in self.api.calls if "protection" in p or "rules/" in p])

    def test_custom_pr_check(self):
        api = Api({"backend": "v1.4.0"}, protection=(200, {"contexts": ["my check"]}))
        self.go("backend@v1.4.0", "--slug", "x", "--pr-check", "my check", api=api)
        self.assertEqual(len(self.runner.cmds("gh", "pr", "merge")), 1)

    # --- dry run ---------------------------------------------------------------------------
    def test_dry_run(self):
        api = Api({"backend": "v1.4.0"}, protection=(200, {"contexts": ["release-pr / release-pr"]}))
        rc = self.go("backend@v1.4.0", "--slug", "x", "--dry-run", api=api)
        self.assertEqual(rc, 0)
        self.assertNothingWritten()
        for pre in (("git", "read-tree"), ("git", "update-index"), ("git", "write-tree"),
                    ("git", "commit-tree")):
            self.assertEqual(self.runner.cmds(*pre), [])
        self.assertIn(f"{{repo: backend, version: v1.4.0, sha: {SHA['backend']}}}", self.out)
        self.assertIn("release/2026-11-03-x", self.out)
        self.assertTrue(self.out.rstrip().endswith("dry run: nothing was written"))
        self.assertTrue([p for _, p in self.api.calls if "protection" in p])


class CliWiringTests(unittest.TestCase):
    """`release-flow propose ...` reaches propose.run with the parsed args and its exit code."""

    def test_main_dispatches_to_propose(self):
        import release_flow
        seen = {}

        def fake_run(args, env, deps):
            seen.update(targets=args.targets, slug=args.slug, dry=args.dry_run, deps=deps)
            return 7

        orig = propose.run
        propose.run = fake_run
        try:
            rc = release_flow.main(["propose", "backend@v1.4.0", "--slug", "fix",
                                    "--allowed", "backend", "--dry-run"],
                                   env={}, deps={"marker": 1})
        finally:
            propose.run = orig
        self.assertEqual(rc, 7)
        self.assertEqual(seen["targets"], ["backend@v1.4.0"])
        self.assertEqual(seen["slug"], "fix")
        self.assertTrue(seen["dry"])
        self.assertEqual(seen["deps"], {"marker": 1})


if __name__ == "__main__":
    unittest.main()
