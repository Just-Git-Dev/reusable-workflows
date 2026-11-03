"""Tests for `release-flow ci-verdict` (docs/ci-verdict.md): is the code at a sha already tested?"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ci_verdict  # noqa: E402
import gh  # noqa: E402
import release_flow  # noqa: E402
from fake_github import OWNER, SHA_A, SHA_B, SHA_C, FakeGitHub, ci_run  # noqa: E402

TMP_ROOT = HERE.parents[2] / ".scratch" / "test-tmp"
REPO = f"{OWNER}/core"
TREE = "7" * 40
OTHER_TREE = "8" * 40
ENV = {"RELEASE_FLOW_READ_TOKEN": "t"}


def runs(fake, wf, sha, *rs):
    """Runs default to event `push` (the shared ci_run helper carries none)."""
    fake.repo("core").ci_runs[(wf, sha)] = [{"event": "push", **r} for r in rs]


def pr(fake, sha, head, number=12, tree=TREE, sha_tree=TREE):
    """A PR associated with `sha` whose head commit `head` has `tree`; `sha` has `sha_tree`."""
    r = fake.repo("core")
    r.pulls.setdefault(sha, []).append({"number": number, "head": {"sha": head}})
    r.git_trees[head] = tree
    r.git_trees[sha] = sha_tree


def cli(fake, *extra, sha=SHA_A, workflows="ci.yml", env=ENV):
    argv = ["ci-verdict", "--repo", REPO, "--sha", sha, "--workflows", workflows, *extra]
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = release_flow.main(argv, env=env, deps={"transport": fake})
    return rc, out.getvalue(), err.getvalue()


def verdict_of(out):
    lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    assert len(lines) == 1, out
    return json.loads(lines[0])


class SameShaTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub()
        self.fake.repo("core")

    def test_green_reuses_with_the_runs_url(self):
        run = ci_run(n=5)
        runs(self.fake, "ci.yml", SHA_A, run)
        rc, out, err = cli(self.fake, "--match", "sha")
        v = verdict_of(out)
        self.assertEqual(rc, 0)
        self.assertTrue(v["reuse"])
        self.assertEqual(v["run_url"], run["html_url"])
        self.assertEqual(v["examined"], 1)
        self.assertIn("same sha", v["why"])
        self.assertIn("examined 1 workflow(s): reuse=true", out + err)

    def test_red_in_progress_and_cancelled_do_not_reuse(self):
        for kw in ({"conclusion": "failure"}, {"conclusion": "cancelled"},
                   {"status": "in_progress", "conclusion": None},
                   {"status": "queued", "conclusion": None}):
            with self.subTest(kw=kw):
                runs(self.fake, "ci.yml", SHA_A, ci_run(**kw))
                rc, out, _ = cli(self.fake, "--match", "sha")
                v = verdict_of(out)
                self.assertEqual(rc, 0)
                self.assertFalse(v["reuse"])
                self.assertEqual(v["run_url"], "")
                self.assertIn("ci.yml", v["why"])

    def test_no_run_with_match_sha_does_not_reuse(self):
        rc, out, err = cli(self.fake, "--match", "sha")
        v = verdict_of(out)
        self.assertEqual(rc, 0)
        self.assertFalse(v["reuse"])
        self.assertIn("no run", v["why"])
        self.assertIn("reuse=false", out + err)
        self.assertEqual([r for r in self.fake.requests if "pulls" in r[1]], [])

    def test_newest_run_wins(self):
        old_green = ci_run(created="2026-10-01T00:00:00Z", n=1)
        new_red = ci_run(created="2026-10-02T00:00:00Z", conclusion="failure", n=2)
        runs(self.fake, "ci.yml", SHA_A, old_green, new_red)
        self.assertFalse(verdict_of(cli(self.fake, "--match", "sha")[1])["reuse"])
        old_red = ci_run(created="2026-10-01T00:00:00Z", conclusion="failure", n=1)
        new_green = ci_run(created="2026-10-02T00:00:00Z", n=2)
        runs(self.fake, "ci.yml", SHA_A, new_green, old_red)
        v = verdict_of(cli(self.fake, "--match", "sha")[1])
        self.assertTrue(v["reuse"])
        self.assertEqual(v["run_url"], new_green["html_url"])

    def test_tie_on_created_at_goes_to_the_higher_id(self):
        green = ci_run(n=9)
        red = ci_run(conclusion="failure", n=3)
        runs(self.fake, "ci.yml", SHA_A, red, green)
        self.assertTrue(verdict_of(cli(self.fake, "--match", "sha")[1])["reuse"])
        green = ci_run(n=3)
        red = ci_run(conclusion="failure", n=9)
        runs(self.fake, "ci.yml", SHA_A, green, red)
        self.assertFalse(verdict_of(cli(self.fake, "--match", "sha")[1])["reuse"])

    def test_event_is_not_filtered(self):
        runs(self.fake, "ci.yml", SHA_A, ci_run())
        cli(self.fake, "--match", "sha")
        paths = [r[1] for r in self.fake.requests if "/runs" in r[1]]
        self.assertTrue(paths)
        self.assertFalse(any("event=" in p for p in paths), paths)

    def test_only_testing_events_count(self):
        for ev in ("pull_request_target", "workflow_dispatch", "schedule", "release"):
            with self.subTest(event=ev):
                runs(self.fake, "ci.yml", SHA_A, {**ci_run(n=4), "event": ev})
                v = verdict_of(cli(self.fake, "--match", "sha")[1])
                self.assertFalse(v["reuse"])
                self.assertIn("no run", v["why"])
        for ev in ("push", "pull_request", "merge_group"):
            with self.subTest(event=ev):
                runs(self.fake, "ci.yml", SHA_A, {**ci_run(n=4), "event": ev})
                self.assertTrue(verdict_of(cli(self.fake, "--match", "sha")[1])["reuse"])

    def test_green_push_run_beside_an_ignored_newer_run_reuses(self):
        newer_ignored = {**ci_run(created="2026-10-09T00:00:00Z", conclusion="failure", n=9),
                         "event": "workflow_dispatch"}
        push = ci_run(n=2)
        runs(self.fake, "ci.yml", SHA_A, newer_ignored, push)
        v = verdict_of(cli(self.fake, "--match", "sha")[1])
        self.assertTrue(v["reuse"])
        self.assertEqual(v["run_url"], push["html_url"])

    def test_two_workflows_one_misses(self):
        runs(self.fake, "ci.yml", SHA_A, ci_run(n=1))
        rc, out, err = cli(self.fake, "--match", "sha", workflows="ci.yml,lint.yml")
        v = verdict_of(out)
        self.assertEqual(rc, 0)
        self.assertFalse(v["reuse"])
        self.assertEqual(v["examined"], 2)
        self.assertIn("lint.yml", v["why"])
        self.assertIn("examined 2 workflow(s): reuse=false", out + err)

    def test_two_workflows_both_green(self):
        a, b = ci_run(n=1), ci_run(n=2)
        runs(self.fake, "ci.yml", SHA_A, a)
        runs(self.fake, "lint.yml", SHA_A, b)
        v = verdict_of(cli(self.fake, "--match", "sha", workflows="ci.yml, lint.yml")[1])
        self.assertTrue(v["reuse"])
        self.assertEqual(v["run_url"].split(), [a["html_url"], b["html_url"]])
        self.assertEqual(v["examined"], 2)


class TreeTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub()
        self.fake.repo("core")

    def test_tree_equal_pr_head_green_reuses(self):
        pr(self.fake, SHA_A, SHA_B)
        run = ci_run(n=7)
        runs(self.fake, "ci.yml", SHA_B, run)
        rc, out, _ = cli(self.fake)  # default match is tree
        v = verdict_of(out)
        self.assertEqual(rc, 0)
        self.assertTrue(v["reuse"])
        self.assertEqual(v["run_url"], run["html_url"])
        self.assertIn("PR #12", v["why"])
        self.assertIn(SHA_B[:8], v["why"])

    def test_tree_differs_does_not_reuse(self):
        pr(self.fake, SHA_A, SHA_B, sha_tree=OTHER_TREE)
        runs(self.fake, "ci.yml", SHA_B, ci_run())
        v = verdict_of(cli(self.fake)[1])
        self.assertFalse(v["reuse"])
        self.assertIn("tree", v["why"])

    def test_pr_head_red_or_missing_does_not_reuse(self):
        pr(self.fake, SHA_A, SHA_B)
        self.assertFalse(verdict_of(cli(self.fake)[1])["reuse"])
        runs(self.fake, "ci.yml", SHA_B, ci_run(conclusion="failure"))
        self.assertFalse(verdict_of(cli(self.fake)[1])["reuse"])

    def test_malformed_pr_head_is_skipped_not_fatal(self):
        r = self.fake.repo("core")
        r.git_trees[SHA_A] = TREE
        r.pulls[SHA_A] = [{"number": 1, "head": None}, {"number": 2, "head": "x"},
                          {"number": 3}]
        rc, out, _ = cli(self.fake)
        v = verdict_of(out)
        self.assertEqual(rc, 0)
        self.assertFalse(v["reuse"])
        self.assertIn("PR #1: no usable head sha", v["why"])
        self.assertIn("PR #2: no usable head sha", v["why"])
        self.assertIn("PR #3: no usable head sha", v["why"])

    def test_second_pr_may_qualify(self):
        pr(self.fake, SHA_A, SHA_B, number=3, sha_tree=TREE, tree=OTHER_TREE)
        pr(self.fake, SHA_A, SHA_C, number=4)
        runs(self.fake, "ci.yml", SHA_C, ci_run())
        v = verdict_of(cli(self.fake)[1])
        self.assertTrue(v["reuse"])
        self.assertIn("PR #4", v["why"])

    def test_same_sha_wins_without_reading_pulls(self):
        runs(self.fake, "ci.yml", SHA_A, ci_run())
        self.assertTrue(verdict_of(cli(self.fake)[1])["reuse"])
        self.assertEqual([r for r in self.fake.requests if "pulls" in r[1]], [])

    def test_no_pr_does_not_reuse(self):
        v = verdict_of(cli(self.fake)[1])
        self.assertFalse(v["reuse"])
        self.assertIn("no run", v["why"])

    def test_finished_red_at_the_sha_blocks_the_tree_rule(self):
        # docs/ci-verdict.md "A red run at the sha itself is final": the exact code failed CI,
        # so a green run on a tree-equal PR head must not override it.
        pr(self.fake, SHA_A, SHA_B)
        runs(self.fake, "ci.yml", SHA_B, ci_run(n=1))
        for kw in ({"conclusion": "failure"}, {"conclusion": "cancelled"}):
            with self.subTest(kw=kw):
                runs(self.fake, "ci.yml", SHA_A, ci_run(n=2, **kw))
                v = verdict_of(cli(self.fake)[1])
                self.assertFalse(v["reuse"])
                self.assertIn("concluded", v["why"])

    def test_unfinished_run_at_the_sha_still_allows_the_tree_rule(self):
        pr(self.fake, SHA_A, SHA_B)
        green = ci_run(n=1)
        runs(self.fake, "ci.yml", SHA_B, green)
        runs(self.fake, "ci.yml", SHA_A, ci_run(n=2, status="in_progress", conclusion=None))
        v = verdict_of(cli(self.fake)[1])
        self.assertTrue(v["reuse"])
        self.assertEqual(v["run_url"], green["html_url"])

    def test_each_workflow_needs_its_own_qualification(self):
        pr(self.fake, SHA_A, SHA_B)
        runs(self.fake, "ci.yml", SHA_B, ci_run(n=1))
        v = verdict_of(cli(self.fake, workflows="ci.yml,lint.yml")[1])
        self.assertFalse(v["reuse"])
        self.assertEqual(v["examined"], 2)


class ErrorTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub()
        self.fake.repo("core")
        runs(self.fake, "ci.yml", SHA_A, ci_run())
        pr(self.fake, SHA_A, SHA_B)
        runs(self.fake, "ci.yml", SHA_B, ci_run())

    def test_api_errors_never_reuse_and_exit_0(self):
        for rx in (r"actions/workflows/ci.yml/runs\?head_sha=a", r"commits/a+/pulls",
                   r"git/commits/"):
            for status in (500, 403, 404, 0):
                with self.subTest(rx=rx, status=status):
                    self.fake.fail.append(("GET", rx, status))
                    # same-sha run must not satisfy the tree-path probes: drop it for those
                    if "pulls" in rx or "git/commits" in rx:
                        self.fake.repo("core").ci_runs.pop(("ci.yml", SHA_A))
                    rc, out, _ = cli(self.fake)
                    self.fake.repo("core").ci_runs[("ci.yml", SHA_A)] = [ci_run()]
                    v = verdict_of(out)
                    self.assertEqual(rc, 0)
                    self.assertFalse(v["reuse"], v)
                    self.assertEqual(v["run_url"], "")
                    want = "network" if status == 0 else str(status)
                    self.assertIn(want, v["why"])

    def test_usage_errors_exit_2(self):
        cases = [
            dict(workflows=""), dict(workflows=" , "), dict(sha="A" * 40), dict(sha="a" * 39),
            dict(sha="g" * 40),
        ]
        for kw in cases:
            with self.subTest(kw=kw):
                self.assertEqual(cli(self.fake, **kw)[0], 2)
        argv = ["ci-verdict", "--repo", "noslash", "--sha", SHA_A, "--workflows", "ci.yml"]
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(release_flow.main(argv, env=ENV, deps={"transport": self.fake}), 2)
        self.assertEqual(cli(self.fake, "--match", "bogus")[0], 2)
        self.assertEqual(cli(self.fake, env={})[0], 2)
        self.assertEqual(self.fake.requests, [])

    def test_unit_decide_returns_reason_on_github_error(self):
        def boom(method, path, body=None):
            raise gh.GitHubError("GET x: network error: timed out")
        v = ci_verdict.decide(gh.Reader(boom), REPO, SHA_A, ["ci.yml"], "tree")
        self.assertFalse(v["reuse"])
        self.assertEqual(v["examined"], 1)
        self.assertIn("network", v["why"])


class GithubOutputTests(unittest.TestCase):
    def test_writes_three_single_line_values(self):
        fake = FakeGitHub()
        fake.repo("core")
        run = ci_run(n=5)
        runs(fake, "ci.yml", SHA_A, run)
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as d:
            f = Path(d) / "out"
            f.write_text("pre=1\n")
            rc, out, _ = cli(fake, "--match", "sha", "--github-output", str(f))
            self.assertEqual(rc, 0)
            lines = f.read_text().splitlines()
            self.assertEqual(lines[0], "pre=1")
            self.assertEqual(lines[1:], ["reuse=true", f"run_url={run['html_url']}",
                                         f"why={verdict_of(out)['why']}"])

    def test_false_verdict_output_and_newlines_stripped(self):
        fake = FakeGitHub()
        fake.repo("core")
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as d:
            f = Path(d) / "out"
            cli(fake, "--match", "sha", "--github-output", str(f))
            lines = f.read_text().splitlines()
            self.assertEqual(lines[0], "reuse=false")
            self.assertEqual(lines[1], "run_url=")
            self.assertTrue(lines[2].startswith("why="))
            self.assertEqual(len(lines), 3)
        self.assertNotIn("\n", ci_verdict.one_line("a\r\nb\nc"))


if __name__ == "__main__":
    unittest.main()
