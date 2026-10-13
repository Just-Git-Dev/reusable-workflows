"""Tests for the publish-time options (run-name template, health path, download assets) and the
subcommands config-check, drafts --check-only, order's slot cap, verdict, plus find-manifest /
check-merge reading the config."""

import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402
import gh  # noqa: E402
import manifest  # noqa: E402
import publish  # noqa: E402
import release_flow  # noqa: E402
from fake_github import (ALLOWED, CFG_DICT, FakeClock, FakeGitHub, SHA_A, SHA_B,  # noqa: E402
                         SHA_C, green_ci)

TMP_ROOT = HERE.parents[2] / ".scratch" / "test-tmp"
AL = ",".join(ALLOWED)
OK = [("in_progress", None), ("completed", "success")]


def tmpdir():
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TMP_ROOT)


def cfg_dict(**top):
    d = copy.deepcopy(CFG_DICT)
    d.update(top)
    return d


def svc(d, repo):
    return next(s for s in d["services"] if s["repo"] == repo)


def call(argv, env=None, deps=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = release_flow.main(argv, env=env or {}, deps=deps or {})
    return rc, out.getvalue(), err.getvalue()


def write(d, name, obj):
    p = Path(d) / name
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))
    return str(p)


# ---------------------------------------------------------------------------- publish


def pub_world(cfg_d, repo, ver, sha, run_name=None):
    f = FakeGitHub()
    r = f.repo(repo)
    r.stage_draft(ver, sha)
    r.deploy_script = OK
    if run_name:
        r.run_name = run_name
    return f, r, manifest.Entry(repo, ver, sha)


class Health:
    def __init__(self, *bodies, status=200):
        self.bodies, self.status, self.calls = list(bodies), status, []

    def __call__(self, url):
        self.calls.append(url)
        return self.status, self.bodies[min(len(self.calls) - 1, len(self.bodies) - 1)]


def do_publish(f, cfg_d, ent, health=None, transport=None):
    clock = FakeClock()
    cfg = config.from_dict(cfg_d)
    t = transport or f
    res = publish.publish_repo(gh.Reader(t), gh.Writer(t), cfg, ent,
                               health or Health({"data": {"status": "UP"}}),
                               clock, clock.sleep)
    return res, clock


class RunNameTemplateTests(unittest.TestCase):
    def test_deploy_run_is_matched_by_the_template(self):
        d = cfg_dict(deploy_run_name="Ship {tag} now")
        f, _, e = pub_world(d, "ui", "v0.55.0", SHA_C, run_name="Ship {tag} now")
        res, _ = do_publish(f, d, e)
        self.assertEqual(res.status, publish.LIVE, res.detail)

    def test_a_run_titled_by_another_template_is_not_ours(self):
        d = cfg_dict(deploy_run_name="Ship {tag} now")
        f, _, e = pub_world(d, "ui", "v0.55.0", SHA_C)  # the fake titles it "Deploy v0.55.0"
        res, _ = do_publish(f, d, e)
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("timed out", res.detail)


class HealthTests(unittest.TestCase):
    def test_dotted_path_and_expect(self):
        d = cfg_dict()
        svc(d, "issuer")["health"] = {"path": "a.b.state", "expect": "ok"}
        f, _, e = pub_world(d, "issuer", "v0.132.0", SHA_A)
        h = Health({"a": {"b": {"state": "ok"}}})
        res, _ = do_publish(f, d, e, h)
        self.assertEqual(res.status, publish.LIVE, res.detail)
        self.assertEqual(len(h.calls), 1)

    def test_default_path_is_data_status_UP(self):
        d = cfg_dict()
        f, _, e = pub_world(d, "issuer", "v0.132.0", SHA_A)
        res, _ = do_publish(f, d, e, Health({"data": {"status": "UP"}}))
        self.assertEqual(res.status, publish.LIVE)
        f, _, e = pub_world(d, "issuer", "v0.132.0", SHA_A)
        res, _ = do_publish(f, d, e, Health({"status": "UP"}))  # custom path not in force
        self.assertEqual(res.status, publish.DEPLOY_FAILED)

    def test_wrong_value_or_missing_path_never_passes_and_retries(self):
        d = cfg_dict()
        svc(d, "issuer")["health"] = {"path": "a.b", "expect": "ok"}
        for body in ({"a": {"b": "bad"}}, {"a": "ok"}, {"b": "ok"}, {"a": {"b": ["ok"]}}, [],
                     {"a": {"b": {"c": "ok"}}}):
            f, _, e = pub_world(d, "issuer", "v0.132.0", SHA_A)
            h = Health(body)
            res, clock = do_publish(f, d, e, h)
            self.assertEqual(res.status, publish.DEPLOY_FAILED, body)
            self.assertEqual(len(h.calls), publish.HEALTH_TRIES)
            self.assertEqual(clock.sleeps[-(publish.HEALTH_TRIES - 1):],
                             [publish.HEALTH_WAIT_S] * (publish.HEALTH_TRIES - 1))

    def test_http_200_is_still_required(self):
        d = cfg_dict()
        f, _, e = pub_world(d, "issuer", "v0.132.0", SHA_A)
        res, _ = do_publish(f, d, e, Health({"data": {"status": "UP"}}, status=503))
        self.assertEqual(res.status, publish.DEPLOY_FAILED)

    def test_recovers_on_a_later_try(self):
        d = cfg_dict()
        f, _, e = pub_world(d, "issuer", "v0.132.0", SHA_A)
        h = Health({"data": {"status": "DOWN"}}, {"data": {"status": "UP"}})
        res, _ = do_publish(f, d, e, h)
        self.assertEqual(res.status, publish.LIVE)
        self.assertEqual(len(h.calls), 2)


def download_cfg():
    d = cfg_dict()
    d["services"].append({"repo": "desktop", "kind": "download", "order": 9,
                          "deploy_workflow": "release.yml", "assets": ["Setup.msi", "app.exe"],
                          "ci": [{"workflow": "gate.yml"}]})
    return d


def assets(*pairs):
    return [{"name": n, "state": s} for n, s in pairs]


class DownloadTests(unittest.TestCase):
    def world(self, present):
        d = download_cfg()
        f, r, e = pub_world(d, "desktop", "v1.0.0", SHA_C)
        r.after_patch = lambda repo, rel: rel.__setitem__("assets", present)
        return d, f, r, e

    def test_all_assets_uploaded_is_live_and_no_health_check(self):
        d, f, r, e = self.world(assets(("Setup.msi", "uploaded"), ("app.exe", "uploaded"),
                                       ("extra.txt", "uploaded")))
        h = Health({"data": {"status": "DOWN"}})
        res, _ = do_publish(f, d, e, h)
        self.assertEqual(res.status, publish.LIVE, res.detail)
        self.assertEqual(h.calls, [])

    def test_missing_asset_is_deploy_failed_and_named(self):
        d, f, r, e = self.world(assets(("Setup.msi", "uploaded")))
        res, clock = do_publish(f, d, e)
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("app.exe", res.detail)
        self.assertNotIn("Setup.msi", res.detail)
        reads = [x for x in f.requests if x[0] == "GET" and x[1].endswith(f"/releases/{r.releases[0]['id']}")]
        self.assertGreaterEqual(len(reads), publish.HEALTH_TRIES)
        self.assertEqual(clock.sleeps.count(publish.HEALTH_WAIT_S), publish.HEALTH_TRIES - 1)

    def test_asset_not_in_state_uploaded_counts_as_missing(self):
        d, f, r, e = self.world(assets(("Setup.msi", "uploaded"), ("app.exe", "starter")))
        res, _ = do_publish(f, d, e)
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("app.exe", res.detail)

    def test_no_assets_at_all_names_both(self):
        d, f, r, e = self.world([])
        res, _ = do_publish(f, d, e)
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertIn("Setup.msi", res.detail)
        self.assertIn("app.exe", res.detail)

    def test_assets_that_arrive_late_are_waited_for(self):
        d, f, r, e = self.world([])
        rid = r.releases[0]["id"]
        gets = []

        def transport(method, path, body=None):
            status, data = f(method, path, body)
            if method == "GET" and path == f"repos/consumer-a-org/desktop/releases/{rid}":
                gets.append(1)
                if len(gets) >= 4 and data.get("draft") is False:
                    data["assets"] = assets(("Setup.msi", "uploaded"), ("app.exe", "uploaded"))
            return status, data

        res, clock = do_publish(f, d, e, transport=transport)
        self.assertEqual(res.status, publish.LIVE, res.detail)

    def test_assets_are_not_looked_at_when_the_deploy_failed(self):
        d, f, r, e = self.world([])
        r.deploy_script = [("completed", "success")]
        r.deploy_script = [("completed", "failure")]
        res, _ = do_publish(f, d, e)
        self.assertEqual(res.status, publish.DEPLOY_FAILED)
        self.assertNotIn("Setup.msi", res.detail)

    def test_worst_case_covers_the_asset_wait_and_stays_under_the_token_lifetime(self):
        deploy = (publish.MAX_DEPLOY_RETRIES + 1) * (publish.DEPLOY_TIMEOUT_S + publish.POLL_S
                                                     + publish.API_TIMEOUT_S)
        assets_wait = (publish.HEALTH_TRIES * publish.API_TIMEOUT_S
                       + (publish.HEALTH_TRIES - 1) * publish.HEALTH_WAIT_S)
        health_wait = (publish.HEALTH_TRIES * publish.HEALTH_TIMEOUT_S
                       + (publish.HEALTH_TRIES - 1) * publish.HEALTH_WAIT_S)
        self.assertGreaterEqual(publish.WORST_CASE_S, deploy + assets_wait)
        self.assertGreaterEqual(publish.WORST_CASE_S, deploy + health_wait)
        self.assertLess(publish.WORST_CASE_S, 55 * 60)


# ---------------------------------------------------------------------------- commands


def mfile(d, *entries, name="m.yaml"):
    lines = "".join(f"  - {{repo: {r}, version: {v}, sha: {s}}}\n" for r, v, s in entries)
    return write(d, name, "services:\n" + lines)


class FindManifestCliTests(unittest.TestCase):
    def diff(self, *lines):
        return {"git_diff": lambda b, h: list(lines)}

    def test_release_dir_from_config(self):
        with tmpdir() as d:
            cfg = write(d, "c.json", cfg_dict(release_dir="ops/rel"))
            rc, out, _ = call(["find-manifest", "--base", "b", "--head", "h", "--config", cfg],
                              deps=self.diff("A\tops/rel/2026-10-09-x.yaml"))
            self.assertEqual((rc, out.strip()), (0, "ops/rel/2026-10-09-x.yaml"))
            rc, _, _ = call(["find-manifest", "--base", "b", "--head", "h", "--config", cfg],
                            deps=self.diff("A\treleases/2026-10-09-x.yaml"))
            self.assertEqual(rc, 1)

    def test_unreadable_config_is_exit_2_never_a_silent_default(self):
        with tmpdir() as d:
            for cfg in (str(Path(d) / "absent.json"), write(d, "bad.json", "{not json"),
                        write(d, "bad2.json", cfg_dict(release_dir="/abs"))):
                rc, out, err = call(["find-manifest", "--base", "b", "--head", "h",
                                     "--config", cfg],
                                    deps=self.diff("A\treleases/2026-10-09-x.yaml"))
                self.assertEqual(rc, 2, cfg)
                self.assertEqual(out, "")

    def test_default_config_is_relative_to_the_current_directory(self):
        with tmpdir() as d:
            os.makedirs(Path(d) / "releases")
            write(Path(d) / "releases", "services.json", cfg_dict(release_dir="ops/rel"))
            old = os.getcwd()
            os.chdir(d)
            try:
                rc, out, _ = call(["find-manifest", "--base", "b", "--head", "h"],
                                  deps=self.diff("A\tops/rel/2026-10-09-x.yaml"))
            finally:
                os.chdir(old)
            self.assertEqual((rc, out.strip()), (0, "ops/rel/2026-10-09-x.yaml"))


class CheckMergeCliTests(unittest.TestCase):
    def world(self, base, path):
        f = FakeGitHub()
        p = f.repo("project")
        p.pulls[SHA_A] = [{"number": 7, "merged_at": "2026-10-09T00:00:00Z",
                           "base": {"ref": base}, "head": {"sha": SHA_B}}]
        p.check_runs[SHA_B] = [{"name": "release-pr", "status": "completed",
                                "conclusion": "success", "app": {"slug": "github-actions"},
                                "check_suite": {"id": 55}}]
        p.suite_runs = {55: [{"path": path}]}
        return f

    ENV = {"RELEASE_FLOW_READ_TOKEN": "r", "GITHUB_REPOSITORY": "consumer-a-org/project"}

    def merge(self, f, cfg, *extra):
        return call(["check-merge", "--sha", SHA_A, "--check-name", "release-pr",
                     "--config", cfg, *extra], self.ENV, {"transport": f})

    def test_base_branch_and_workflow_path(self):
        with tmpdir() as d:
            cfg = write(d, "c.json", cfg_dict(base_branch="develop"))
            f = self.world("develop", ".github/workflows/release-pr.yml")
            rc, out, err = self.merge(f, cfg)
            self.assertEqual((rc, out.strip()), (0, "7"), err)
            rc, _, _ = self.merge(self.world("main", ".github/workflows/release-pr.yml"), cfg)
            self.assertEqual(rc, 1)
            f = self.world("develop", ".github/workflows/gate.yml")
            self.assertEqual(self.merge(f, cfg)[0], 1)
            rc, out, err = self.merge(f, cfg, "--workflow-path", ".github/workflows/gate.yml")
            self.assertEqual((rc, out.strip()), (0, "7"), err)

    def test_unreadable_config_is_exit_2(self):
        with tmpdir() as d:
            f = self.world("main", ".github/workflows/release-pr.yml")
            self.assertEqual(self.merge(f, str(Path(d) / "absent.json"))[0], 2)

    def test_check_name_stays_required(self):
        with tmpdir() as d, self.assertRaises(SystemExit):
            call(["check-merge", "--sha", SHA_A, "--config", write(d, "c.json", cfg_dict())],
                 self.ENV)


class ConfigCheckTests(unittest.TestCase):
    def cc(self, d, *extra, env=None, **top):
        cfg = write(d, "c.json", cfg_dict(**top))
        env = {"GITHUB_REPOSITORY_OWNER": "consumer-a-org"} if env is None else env
        return call(["config-check", "--config", cfg, *extra], env)

    def test_prints_the_three_values_compactly(self):
        with tmpdir() as d:
            rc, out, err = self.cc(d, "--allowed", AL, "--read-only", "cli", release_dir="ops/rel")
            self.assertEqual(rc, 0, err)
            self.assertEqual(out.strip(), '{"owner":"consumer-a-org","release_dir":"ops/rel",'
                                          '"base_branch":"main"}')

    def test_consumers_only_must_be_read_only(self):
        with tmpdir() as d:
            for extra in (("--read-only", ""), ("--read-only", "other")):
                rc, out, err = self.cc(d, "--allowed", AL, *extra)
                self.assertEqual(rc, 2, extra)
                self.assertIn("cli", err)
                self.assertEqual(out, "")

    def test_absent_read_only_skips_the_rule_given_enforces_it(self):
        # Only the job that mints a token covering the consumers_only repos (plan) passes
        # --read-only; every other config-check caller omits it and must not be refused.
        with tmpdir() as d:
            rc, out, err = self.cc(d, "--allowed", AL)
            self.assertEqual(rc, 0, err)
            self.assertIn('"owner"', out)
            rc, _, err = self.cc(d, "--allowed", AL, "--read-only", "")
            self.assertEqual(rc, 2)
            self.assertIn("cli", err)

    def test_no_consumers_only_needs_no_read_only(self):
        with tmpdir() as d:
            rc, _, err = self.cc(d, "--allowed", AL, consumers_only=[], contracts=[])
            self.assertEqual(rc, 0, err)

    def test_owner_must_match_the_running_org(self):
        with tmpdir() as d:
            rc, _, err = self.cc(d, "--allowed", AL, "--read-only", "cli",
                                 env={"GITHUB_REPOSITORY_OWNER": "someone-else"})
            self.assertEqual(rc, 2)
            self.assertIn("owner", err)
            rc, _, err = self.cc(d, "--allowed", AL, "--read-only", "cli", env={})
            self.assertEqual(rc, 2)
            self.assertIn("GITHUB_REPOSITORY_OWNER", err)

    def test_repo_outside_allowed_and_bad_config(self):
        with tmpdir() as d:
            rc, _, err = self.cc(d, "--allowed", "issuer,api,ui", "--read-only", "cli")
            self.assertEqual(rc, 2)
            self.assertIn("website", err)
            rc, _, _ = call(["config-check", "--allowed", AL, "--config", str(Path(d) / "no.json")],
                            {"GITHUB_REPOSITORY_OWNER": "consumer-a-org"})
            self.assertEqual(rc, 2)

    def test_allowed_is_required(self):
        with tmpdir() as d, self.assertRaises(SystemExit):
            self.cc(d)


class DraftsCheckOnlyTests(unittest.TestCase):
    def world(self):
        f = FakeGitHub()
        i = f.repo("issuer")
        i.add_release("v0.131.0")
        i.good_commit(SHA_A, "v0.132.0")
        i.add_tag("v0.132.0", SHA_A)
        green_ci(f, "issuer", SHA_A)
        return f

    def go(self, d, f, env=None, *extra):
        env = {"RELEASE_FLOW_READ_TOKEN": "r"} if env is None else env
        argv = ["drafts", mfile(d, ("issuer", "v0.132.0", SHA_A)), "--check-only",
                "--config", write(d, "c.json", cfg_dict()), "--allowed", AL, *extra]
        with mock.patch.object(release_flow.gh, "Writer",
                               side_effect=AssertionError("a Writer was built")):
            return call(argv, env, {"transport": f})

    def test_prints_rehearsal_and_writes_nothing(self):
        with tmpdir() as d:
            f = self.world()
            rc, out, err = self.go(d, f)
            self.assertEqual(rc, 0, err)
            self.assertEqual(json.loads(out), {"issuer": "rehearsal"})
            self.assertEqual(f.writes(), [])
            self.assertTrue(f.requests)  # it did read

    def test_uses_only_the_read_token(self):
        with tmpdir() as d:
            f = self.world()
            rc, _, err = self.go(d, f, {"RELEASE_FLOW_WRITE_TOKEN": "w"})
            self.assertEqual(rc, 2)
            self.assertIn("RELEASE_FLOW_READ_TOKEN", err)
            self.assertEqual(f.requests, [])
            rc, _, _ = self.go(d, self.world(), {"RELEASE_FLOW_READ_TOKEN": "r",
                                                 "RELEASE_FLOW_WRITE_TOKEN": "w"})
            self.assertEqual(rc, 0)

    def test_every_precheck_still_runs(self):
        cases = {
            "validate (sha not on base)": lambda f: f.repo("issuer").compare.update({SHA_A: "diverged"}),
            "ci-green": lambda f: f.repo("issuer").ci_runs.clear(),
            "tag moved": lambda f: f.repo("issuer").tag_objects.update(
                {f.repo("issuer").refs["v0.132.0"]["sha"]: SHA_B}),
            "tag missing": lambda f: f.repo("issuer").refs.pop("v0.132.0"),
        }
        for label, breaker in cases.items():
            with tmpdir() as d:
                f = self.world()
                breaker(f)
                rc, out, err = self.go(d, f)
                self.assertEqual(rc, 1, label)
                self.assertEqual(f.writes(), [], label)

    def test_without_check_only_the_write_path_is_unchanged(self):
        with tmpdir() as d:
            f = self.world()
            argv = ["drafts", mfile(d, ("issuer", "v0.132.0", SHA_A)),
                    "--config", write(d, "c.json", cfg_dict()), "--allowed", AL]
            rc, out, err = call(argv, {"RELEASE_FLOW_READ_TOKEN": "r",
                                       "RELEASE_FLOW_WRITE_TOKEN": "w"}, {"transport": f})
            self.assertEqual(rc, 0, err)
            self.assertEqual(len(f.writes()), 1)


class OrderSlotCapTests(unittest.TestCase):
    def go(self, n):
        d = cfg_dict(consumers_only=[], contracts=[])
        d["services"] = [{"repo": f"svc{i}", "kind": "pages", "order": i,
                          "deploy_workflow": "deploy.yml"} for i in range(1, n + 1)]
        with tmpdir() as t:
            m = mfile(t, *[(f"svc{i}", "v1.0.0", SHA_A) for i in range(1, n + 1)])
            return call(["order", m, "--config", write(t, "c.json", d), "--allowed",
                         ",".join(f"svc{i}" for i in range(1, n + 1))])

    def test_constant(self):
        self.assertEqual(publish.MAX_PUBLISH_SLOTS, 6)

    def test_six_are_fine(self):
        rc, out, err = self.go(6)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.split(), [f"svc{i}" for i in range(1, 7)])

    def test_seven_are_refused(self):
        rc, out, err = self.go(7)
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("6", err)


# ---------------------------------------------------------------------------- verdict

MANIFEST = "releases/2026-10-09-x.yaml"


def needs(plan="success", manifest_path=MANIFEST, checks="[]", rehearsal="false", pr="7",
          **jobs):
    out = {}
    if plan is not None:
        out["plan"] = {"result": plan, "outputs": {"manifest": manifest_path, "checks": checks,
                                                   "rehearsal": rehearsal, "pr": pr}}
    for k, v in jobs.items():
        if v is not None:
            out[k] = {"result": v, "outputs": {}}
    return out


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self._d = tmpdir()
        self.d = self._d.name
        self.addCleanup(self._d.cleanup)
        self.old = os.getcwd()
        os.chdir(self.d)
        self.addCleanup(os.chdir, self.old)
        os.makedirs("releases")
        # api listed before issuer in the file; the verdict must give services.json order
        self.mpath = mfile(self.d, ("api", "v0.38.0", SHA_B), ("issuer", "v0.132.0", SHA_A),
                           name="releases/2026-10-09-x.yaml")
        self.cfg = write(self.d, "c.json", cfg_dict())

    def v(self, nd, *extra, stage="drafts", contracts="contracts", cfg=None, raw=None,
          needs_path=None):
        nf = needs_path or write(self.d, "needs.json", raw if raw is not None else nd)
        rc, out, err = call(["verdict", "--stage", stage, "--needs-file", nf,
                             "--contracts-job", contracts, "--config", cfg or self.cfg,
                             "--allowed", AL, *extra])
        return rc, (json.loads(out) if out.strip() else None), out, err

    def test_ok(self):
        rc, j, out, err = self.v(needs())
        self.assertEqual(rc, 0, err)
        self.assertEqual(j, {"ok": True, "rehearsal": False, "manifest": MANIFEST, "pr": "7",
                             "manifest_sha256": "", "order": ["issuer", "api"],
                             "failed_stage": "", "failures": []})
        self.assertEqual(out.strip(), json.dumps(j, separators=(",", ":")))
        self.assertEqual(len(out.strip().splitlines()), 1)

    def with_sha(self, sha, **kw):
        nd = needs(**kw)
        nd["plan"]["outputs"]["manifest-sha256"] = sha
        return nd

    def test_manifest_file_is_read_instead_of_the_path_and_its_sha_is_asserted(self):
        # The artifact the plan stage staged is the only manifest the later stages may read
        # (a rehearsal's manifest is not on the base branch at all).
        import hashlib
        staged = mfile(self.d, ("api", "v0.38.0", SHA_B), ("issuer", "v0.132.0", SHA_A),
                       name="staged.yaml")
        sha = hashlib.sha256(Path(staged).read_bytes()).hexdigest()
        os.remove(self.mpath)
        rc, j, _, err = self.v(self.with_sha(sha), "--manifest-file", staged)
        self.assertEqual(rc, 0, err)
        self.assertEqual(j["manifest_sha256"], sha)
        self.assertEqual(j["order"], ["issuer", "api"])
        for bad in ("0" * 64, "", "xyz"):
            rc, j, _, err = self.v(self.with_sha(bad), "--manifest-file", staged)
            self.assertEqual(rc, 2, bad)
            self.assertIn("sha256", err)
        rc, _, _, err = self.v(needs(), "--manifest-file", staged)   # plan gave no sha at all
        self.assertEqual(rc, 2)

    def test_rehearsal_flag(self):
        rc, j, _, _ = self.v(needs(rehearsal="true", pr=""))
        self.assertEqual(rc, 0)
        self.assertTrue(j["rehearsal"])
        self.assertEqual(j["pr"], "")
        rc, j, _, _ = self.v(needs(rehearsal="True"))
        self.assertFalse(j["rehearsal"])

    def test_contracts_job_skipped_or_absent_only_when_checks_is_empty(self):
        for state in ("skipped", None):
            rc, j, _, err = self.v(needs(checks="[]", contracts=state))
            self.assertEqual((rc, j["ok"]), (0, True), (state, err))
            rc, j, _, _ = self.v(needs(checks='[{"consumer":"ui"}]', contracts=state))
            self.assertEqual((rc, j["ok"], j["failed_stage"], j["order"]),
                             (1, False, "contracts", []), state)
        rc, j, _, _ = self.v(needs(checks='[{"x":1}]', contracts="success"))
        self.assertEqual((rc, j["ok"]), (0, True))

    def test_contracts_job_failure_is_a_failure_even_with_no_checks(self):
        for state in ("failure", "cancelled"):
            rc, j, _, _ = self.v(needs(checks="[]", contracts=state))
            self.assertEqual((rc, j["failed_stage"]), (1, "contracts"), state)

    def test_contracts_job_id_is_a_parameter(self):
        rc, j, _, _ = self.v(needs(checks='[{"x":1}]', ck="success"), contracts="ck")
        self.assertEqual((rc, j["ok"]), (0, True))
        rc, j, _, _ = self.v(needs(checks='[{"x":1}]', ck="skipped"), contracts="ck")
        self.assertEqual((rc, j["failed_stage"]), (1, "ck"))

    def test_plan_must_be_present_and_successful(self):
        rc, j, _, _ = self.v(needs(plan=None, drafts="success"), "--required", "plan,drafts")
        self.assertEqual((rc, j["ok"], j["failed_stage"], j["order"]), (1, False, "plan", []))
        for state in ("failure", "skipped", "cancelled"):
            rc, j, _, _ = self.v(needs(plan=state))
            self.assertEqual((rc, j["failed_stage"]), (1, "plan"), state)

    def test_plan_manifest_must_exist_and_match_the_release_dir_rule(self):
        for m in ("", "releases/foo.yaml", "other/2026-10-09-x.yaml", "/releases/2026-10-09-x.yaml",
                  "releases/../2026-10-09-x.yaml", "releases/2026-10-09-x.yml",
                  "releases/2026-10-09-X.yaml", "releases/2026-10-09-x.yaml\n", None):
            nd = needs(manifest_path=m)
            if m is None:
                del nd["plan"]["outputs"]["manifest"]
            rc, j, _, _ = self.v(nd)
            self.assertEqual((rc, j["ok"], j["failed_stage"]), (1, False, "plan"), repr(m))

    def test_release_dir_comes_from_the_config(self):
        os.makedirs("ops/rel")
        mfile(self.d, ("issuer", "v0.132.0", SHA_A), name="ops/rel/2026-10-09-x.yaml")
        cfg = write(self.d, "c2.json", cfg_dict(release_dir="ops/rel"))
        rc, j, _, err = self.v(needs(manifest_path="ops/rel/2026-10-09-x.yaml"), cfg=cfg)
        self.assertEqual((rc, j["order"]), (0, ["issuer"]), err)
        rc, j, _, _ = self.v(needs(manifest_path=MANIFEST), cfg=cfg)
        self.assertEqual((rc, j["failed_stage"]), (1, "plan"))

    def test_required_jobs_must_be_present(self):
        rc, j, _, _ = self.v(needs(), "--required", "plan,drafts")
        self.assertEqual((rc, j["ok"], j["failed_stage"]), (1, False, "drafts"))
        self.assertTrue(any("drafts" in x for x in j["failures"]))
        rc, j, _, _ = self.v(needs(drafts="success"), "--required", "plan,drafts")
        self.assertEqual((rc, j["ok"]), (0, True))

    def test_every_present_job_must_succeed(self):
        for state in ("failure", "cancelled", "skipped", "weird"):
            rc, j, _, _ = self.v(needs(drafts=state), "--required", "plan,drafts")
            self.assertEqual((rc, j["failed_stage"]), (1, "drafts"), state)
            rc, j, _, _ = self.v(needs(extra=state))  # present but not required: still counts
            self.assertEqual((rc, j["failed_stage"]), (1, "extra"), state)

    def test_failed_stage_is_the_first_in_required_order_then_alphabetical(self):
        nd = needs(drafts="failure", publish_1="failure", zeta="failure", alpha="cancelled")
        rc, j, _, _ = self.v(nd, "--required", "plan,publish_1,drafts")
        self.assertEqual(j["failed_stage"], "publish_1")
        rc, j, _, _ = self.v(nd, "--required", "plan,drafts,publish_1")
        self.assertEqual(j["failed_stage"], "drafts")
        rc, j, _, _ = self.v(needs(zeta="failure", alpha="cancelled"), "--required", "plan")
        self.assertEqual(j["failed_stage"], "alpha")
        rc, j, _, _ = self.v(needs(zeta="failure", alpha="cancelled"), "--required", "plan,zeta")
        self.assertEqual(j["failed_stage"], "zeta")
        self.assertEqual(len(j["failures"]), 2)

    def test_unparseable_needs_file_is_not_ok_at_plan(self):
        for raw in ("{not json", "", "[]", '"x"', "null"):
            rc, j, _, _ = self.v(None, raw=raw)
            self.assertEqual((rc, j["ok"], j["failed_stage"], j["order"]),
                             (1, False, "plan", []), raw)

    def test_unreadable_needs_file_and_bad_config_are_exit_2(self):
        rc, j, out, err = self.v(None, needs_path=str(Path(self.d) / "absent.json"))
        self.assertEqual((rc, out), (2, ""))
        rc, _, out, _ = self.v(needs(), cfg=str(Path(self.d) / "absent.json"))
        self.assertEqual((rc, out), (2, ""))
        rc, _, out, _ = self.v(needs(), cfg=write(self.d, "bad.json", cfg_dict(release_dir="/x")))
        self.assertEqual((rc, out), (2, ""))
        rc, out, _ = call(["verdict", "--stage", "drafts", "--needs-file",
                           write(self.d, "n.json", needs()), "--contracts-job", "contracts",
                           "--config", self.cfg, "--allowed", "issuer,api"])
        self.assertEqual((rc, out), (2, ""))  # website is in services.json, outside --allowed

    def test_ok_but_unreadable_manifest_is_exit_2(self):
        os.remove(self.mpath)
        rc, _, out, _ = self.v(needs())
        self.assertEqual((rc, out), (2, ""))
        Path(self.mpath).write_text("services:\n  garbage\n")
        rc, _, out, _ = self.v(needs())
        self.assertEqual((rc, out), (2, ""))

    def test_order_is_computed_only_when_ok(self):
        rc, j, _, _ = self.v(needs(drafts="failure"), "--required", "plan,drafts")
        self.assertEqual((rc, j["order"], j["manifest"]), (1, [], MANIFEST))

    def test_malformed_job_entry_is_a_failure_of_that_job(self):
        nd = needs()
        nd["drafts"] = "success"
        rc, j, _, _ = self.v(nd, "--required", "plan,drafts")
        self.assertEqual((rc, j["failed_stage"]), (1, "drafts"))

    def test_stage_is_validated(self):
        with self.assertRaises(SystemExit):
            self.v(needs(), stage="deploy")
        rc, j, _, _ = self.v(needs(drafts="success"), "--required", "plan,drafts",
                             stage="publish")
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
