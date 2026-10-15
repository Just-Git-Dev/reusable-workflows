"""Tests for publish.py and guard.py (merge guard, concurrency)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import gh  # noqa: E402
import guard  # noqa: E402
import manifest  # noqa: E402
import publish  # noqa: E402
from fake_github import CFG_DICT, FakeClock, FakeGitHub, SHA_A, SHA_B, SHA_C  # noqa: E402

CFG = config.from_dict(CFG_DICT)
OK = [("in_progress", None), ("completed", "success")]


def world(deploys=OK):
    f = FakeGitHub()
    ents = {}
    for repo, ver, sha in (("core", "v0.132.0", SHA_A), ("gateway", "v0.38.0", SHA_B),
                           ("web", "v0.55.0", SHA_C)):
        r = f.repo(repo)
        r.stage_draft(ver, sha)
        r.deploy_script = deploys
        ents[repo] = manifest.Entry(repo, ver, sha)
    return f, ents


class Health:
    def __init__(self, *bodies):
        self.bodies, self.calls = list(bodies), []

    def __call__(self, url):
        self.calls.append(url)
        b = self.bodies[min(len(self.calls) - 1, len(self.bodies) - 1)]
        return 200, b


UP = {"data": {"status": "UP"}}
DEGRADED = {"data": {"status": "DEGRADED"}}


def run(f, ent, health=None, clock=None):
    clock = clock or FakeClock()
    res = publish.publish_repo(gh.Reader(f), gh.Writer(f), CFG, ent,
                               health or Health(UP), clock, clock.sleep)
    return res, clock


class PublishRepoTests(unittest.TestCase):
    def test_happy_image(self):
        f, e = world()
        h = Health(UP)
        res, _ = run(f, e["core"], h)
        self.assertEqual(res.status, publish.LIVE, res.detail)
        patches = [w for w in f.writes() if w[0] == "PATCH"]
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0][2], {"draft": False})
        self.assertEqual(h.calls, ["https://auth.example/health"])
        self.assertFalse(f.repo("core").releases[0]["draft"])

    def test_pages_has_no_health_check(self):
        f, e = world()
        h = Health(DEGRADED)
        res, _ = run(f, e["web"], h)
        self.assertEqual(res.status, publish.LIVE)
        self.assertEqual(h.calls, [])

    def test_tag_moved_refuses_before_patch(self):
        f, e = world()
        r = f.repo("core")
        r.tag_objects[r.refs["v0.132.0"]["sha"]] = "d" * 40
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.NOT_PUBLISHED)
        self.assertIn("sha", res.detail)
        self.assertEqual(f.writes(), [])

    def test_lightweight_tag_refused(self):
        f, e = world()
        f.repo("core").refs["v0.132.0"] = {"type": "commit", "sha": SHA_A}
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.NOT_PUBLISHED)
        self.assertEqual(f.writes(), [])

    def test_already_published_refused(self):
        f, e = world()
        f.repo("core").releases[0]["draft"] = False
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.NOT_PUBLISHED)
        self.assertEqual(f.writes(), [])

    def test_no_release_or_two_releases_refused(self):
        f, e = world()
        f.repo("core").releases.clear()
        self.assertEqual(run(f, e["core"])[0].status, publish.NOT_PUBLISHED)
        f, e = world()
        f.repo("core").add_release("v0.132.0", draft=True)
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.NOT_PUBLISHED)
        self.assertEqual(f.writes(), [])

    def test_missing_tag_ref_refused(self):
        f, e = world()
        del f.repo("core").refs["v0.132.0"]
        self.assertEqual(run(f, e["core"])[0].status, publish.NOT_PUBLISHED)
        self.assertEqual(f.writes(), [])

    def test_tag_name_changed_after_patch(self):
        f, e = world()
        f.repo("core").after_patch = lambda repo, rel: rel.update(tag_name="v9.9.9")
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.POSTCHECK_FAILED)
        self.assertIn("investigate", res.detail)
        self.assertEqual([w[0] for w in f.writes()], ["PATCH"])  # never PATCHes back

    def test_tag_moved_after_patch(self):
        f, e = world()

        def move(repo, rel):
            repo.tag_objects[repo.refs["v0.132.0"]["sha"]] = "d" * 40
        f.repo("core").after_patch = move
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.POSTCHECK_FAILED)
        self.assertEqual([w[0] for w in f.writes()], ["PATCH"])

    def test_still_draft_after_patch(self):
        f, e = world()
        f.repo("core").after_patch = lambda repo, rel: rel.update(draft=True)
        self.assertEqual(run(f, e["core"])[0].status, publish.POSTCHECK_FAILED)

    def test_patch_http_error_is_not_published(self):
        f, e = world()
        f.fail.append(("PATCH", "releases/", 422))
        self.assertEqual(run(f, e["core"])[0].status, publish.NOT_PUBLISHED)

    def test_deploy_failure(self):
        f, e = world(deploys=[("completed", "failure")])
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("failure", res.detail)

    def test_deploy_timeout(self):
        f, e = world(deploys=[("in_progress", None)])
        res, clock = run(f, e["core"])
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("timed out", res.detail)
        self.assertGreaterEqual(clock.now, 15 * 60)
        self.assertLess(clock.now, 16 * 60 + 60)

    def test_deploy_run_never_appears_times_out(self):
        f, e = world(deploys=None)
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("timed out", res.detail)

    def test_other_branch_run_not_matched(self):
        # the fake always includes a failed main-branch run; it must be ignored
        f, e = world()
        self.assertEqual(run(f, e["web"])[0].status, publish.LIVE)

    def reruns(self, f):
        return [w for w in f.writes() if "rerun-failed-jobs" in w[1]]

    def test_max_retries_constant(self):
        self.assertEqual(publish.MAX_DEPLOY_RETRIES, 2)

    def test_failed_deploy_is_rerun_once_then_live(self):
        f, e = world(deploys=[("completed", "failure"), ("in_progress", None),
                              ("completed", "success")])
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.LIVE, res.detail)
        rr = self.reruns(f)
        self.assertEqual(len(rr), 1)
        self.assertTrue(rr[0][1].endswith("/actions/runs/2/rerun-failed-jobs"))  # THAT run id
        self.assertIsNone(rr[0][2])

    def test_cancelled_and_timed_out_are_retried(self):
        for concl in ("cancelled", "timed_out"):
            f, e = world(deploys=[("completed", concl), ("completed", "success")])
            self.assertEqual(run(f, e["core"])[0].status, publish.LIVE, concl)
            self.assertEqual(len(self.reruns(f)), 1)

    def test_other_conclusions_are_not_retried(self):
        f, e = world(deploys=[("completed", "skipped")])
        self.assertEqual(run(f, e["core"])[0].status, publish.DEPLOY_FAILED)
        self.assertEqual(self.reruns(f), [])

    def test_exactly_three_attempts_then_failed_with_count(self):
        f, e = world(deploys=[("completed", "failure")])
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertEqual(len(self.reruns(f)), 2)
        self.assertIn("3 attempts", res.detail)

    def test_stale_attempt_after_rerun_is_not_rerun_again(self):
        f, e = world(deploys=[("completed", "failure"), ("completed", "success")])
        f.repo("core").stale_after_rerun = 3  # old failed attempt still listed for 3 polls
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.LIVE, res.detail)
        self.assertEqual(len(self.reruns(f)), 1)

    def test_rerun_http_error_fails(self):
        f, e = world(deploys=[("completed", "failure")])
        f.fail.append(("POST", "rerun-failed-jobs", 403))
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("403", res.detail)

    def test_strict_run_match(self):
        base = {"id": 7, "head_branch": "v0.132.0", "head_sha": SHA_A, "event": "release",
                "display_title": "Deploy v0.132.0", "run_attempt": 1,
                "status": "completed", "conclusion": "success"}
        for change in ({"head_sha": SHA_B}, {"display_title": "Deploy v0.132.0 hotfix"},
                       {"event": "workflow_dispatch"}, {"head_branch": "main"},
                       {"display_title": "Deploy DRYRUN v0.132.0"}):
            f, e = world(deploys=None)
            # only a non-matching run exists: must time out, not accept it
            f.repo("core").extra_runs = [{**base, **change}]
            res, _ = run(f, e["core"])
            self.assertEqual(res.status, publish.DEPLOY_FAILED, change)
            self.assertIn("timed out", res.detail, change)

    def test_two_matching_runs_are_ambiguous(self):
        f, e = world()
        f.repo("core").extra_runs = [{
            "id": 9, "head_branch": "v0.132.0", "head_sha": SHA_A, "event": "release",
            "display_title": "Deploy v0.132.0", "run_attempt": 1, "status": "completed",
            "conclusion": "success"}]
        res, _ = run(f, e["core"])
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("ambiguous", res.detail)
        self.assertEqual(self.reruns(f), [])

    def test_worst_case_duration_fits_a_75_minute_job(self):
        f, e = world(deploys=[("in_progress", None)])
        # worst case: every attempt runs until its own timeout... but a timeout is not retried,
        # so the real worst case is two failures then a hang on the third attempt
        f.repo("core").deploy_script = (
            [("completed", "failure")] + [("in_progress", None)] * 10**4)
        res, clock = run(f, e["core"], Health(DEGRADED))
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertLess(clock.now, 55 * 60)
        self.assertLess(publish.WORST_CASE_S, 55 * 60)

    def test_health_degraded_fails_after_retries(self):
        f, e = world()
        h = Health(DEGRADED)
        res, _ = run(f, e["core"], h)
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("DEGRADED", res.detail)
        self.assertGreater(len(h.calls), 1)

    def test_health_recovers_within_retries(self):
        f, e = world()
        res, _ = run(f, e["core"], Health(DEGRADED, DEGRADED, UP))
        self.assertEqual(res.status, publish.LIVE)

    def test_health_malformed_body_fails(self):
        f, e = world()
        res, _ = run(f, e["core"], Health({"status": "UP"}))  # no data.status
        self.assertEqual(res.status, publish.DEPLOY_FAILED)


class OrderTests(unittest.TestCase):
    def test_config_order_listed_only(self):
        es = [manifest.Entry("web", "v1.0.0", SHA_A), manifest.Entry("core", "v1.0.0", SHA_B)]
        self.assertEqual(publish.order(CFG, es), ["core", "web"])


class GuardTests(unittest.TestCase):
    ROOT = "consumer-a-org/project"

    def fake(self):
        f = FakeGitHub()
        f.repos["project"] = f.repo("project")
        return f, f.repo("project")

    def pr(self, **kw):
        base = {"number": 7, "merged_at": "2026-10-09T00:00:00Z", "base": {"ref": "main"},
                "head": {"sha": SHA_B}}
        base.update(kw)
        return base

    def good(self):
        f, p = self.fake()
        p.pulls[SHA_A] = [self.pr()]
        p.check_runs[SHA_B] = [self.check(55)]
        p.suite_runs = {55: [{"path": ".github/workflows/release-pr.yml"}]}
        return f, p

    def check(self, suite, slug="github-actions", name="release-pr", conclusion="success"):
        return {"name": name, "status": "completed", "conclusion": conclusion,
                "app": {"slug": slug}, "check_suite": {"id": suite}}

    def test_same_named_check_from_another_app_or_workflow_is_refused(self):
        f, p = self.good()
        p.check_runs[SHA_B] = [self.check(55, slug="some-other-app")]
        with self.assertRaises(guard.GuardError) as cm:
            self.merge(f)
        self.assertIn("github-actions", str(cm.exception))
        # a genuine one alongside a spoofed one is still refused
        p.check_runs[SHA_B] = [self.check(55), self.check(55, slug="evil")]
        with self.assertRaises(guard.GuardError):
            self.merge(f)
        # same app, same name, but produced by a different workflow file
        f, p = self.good()
        p.suite_runs = {55: [{"path": ".github/workflows/evil.yml"}]}
        with self.assertRaises(guard.GuardError) as cm:
            self.merge(f)
        self.assertIn("release-pr.yml", str(cm.exception))
        # suite that maps to no workflow run at all
        p.suite_runs = {55: []}
        with self.assertRaises(guard.GuardError):
            self.merge(f)
        # check run without app / suite fields
        p.check_runs[SHA_B] = [{"name": "release-pr", "conclusion": "success"}]
        with self.assertRaises(guard.GuardError):
            self.merge(f)

    def merge(self, f):
        return guard.check_merge(gh.Reader(f), self.ROOT, SHA_A, "release-pr")

    def test_ok(self):
        f, _ = self.good()
        self.assertEqual(self.merge(f), 7)

    def test_failures(self):
        f, p = self.good()
        p.pulls[SHA_A] = []
        with self.assertRaises(guard.GuardError):
            self.merge(f)
        p.pulls[SHA_A] = [self.pr(), self.pr(number=8)]
        with self.assertRaises(guard.GuardError):
            self.merge(f)
        p.pulls[SHA_A] = [self.pr(merged_at=None)]
        with self.assertRaises(guard.GuardError):
            self.merge(f)
        p.pulls[SHA_A] = [self.pr(base={"ref": "dev"})]
        with self.assertRaises(guard.GuardError):
            self.merge(f)

    def test_check_not_success(self):
        for runs in ([], [self.check(55, name="other")],
                     [self.check(55, conclusion="failure")],
                     [self.check(55, conclusion=None)],
                     [self.check(55), self.check(55, conclusion="failure")]):
            f, p = self.good()
            p.check_runs[SHA_B] = runs
            with self.assertRaises(guard.GuardError, msg=str(runs)):
                self.merge(f)

    def test_concurrent(self):
        f, p = self.fake()
        p.wf_runs = [{"id": 5, "status": "in_progress"}, {"id": 6, "status": "completed"}]
        guard.concurrent(gh.Reader(f), self.ROOT, "release.yml", 5)  # only itself: fine
        for st in ("queued", "in_progress", "waiting", "pending"):
            p.wf_runs = [{"id": 5, "status": "in_progress"}, {"id": 9, "status": st}]
            with self.assertRaises(guard.GuardError, msg=st):
                guard.concurrent(gh.Reader(f), self.ROOT, "release.yml", 5)


if __name__ == "__main__":
    unittest.main()
