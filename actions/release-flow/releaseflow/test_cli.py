"""Tests for ops_subset.py, report.py and the release_flow.py entry point."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ops_subset  # noqa: E402
import release_flow  # noqa: E402
import report  # noqa: E402
from fake_github import ALLOWED, CFG_DICT, FakeClock, FakeGitHub, SHA_A, SHA_B, green_ci, make_live  # noqa: E402

TMP_ROOT = HERE.parents[2] / ".scratch" / "test-tmp"


def tmpdir():
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TMP_ROOT)


def spec(*ops):
    paths = {}
    for m, p in ops:
        paths.setdefault(p, {})[m.lower()] = {"summary": "x"}
    paths_param = {"parameters": []}
    return json.dumps({"openapi": "3.0.0", "paths": {p: {**v, **paths_param}
                                                     for p, v in paths.items()}})


class CliOpsTests(unittest.TestCase):
    def run_check(self, tool, core, *extra):
        with tmpdir() as d:
            a, b = Path(d) / "tool.json", Path(d) / "core.json"
            a.write_text(tool)
            b.write_text(core)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                rc = ops_subset.main([str(a), str(b), *extra])
            return rc, out.getvalue()

    def test_subset_ok_and_counts(self):
        rc, out = self.run_check(spec(("GET", "/a"), ("POST", "/a")),
                                 spec(("GET", "/a"), ("POST", "/a"), ("GET", "/b")))
        self.assertEqual(rc, 0)
        self.assertIn("examined 2", out)

    def test_parameters_key_is_not_an_operation(self):
        rc, out = self.run_check(spec(("GET", "/a")), spec(("GET", "/a")))
        self.assertIn("examined 1", out)

    def test_missing_operation(self):
        rc, out = self.run_check(spec(("GET", "/a"), ("DELETE", "/gone")), spec(("GET", "/a")))
        self.assertEqual(rc, 1)
        self.assertIn("DELETE /gone", out)

    def test_method_missing_on_existing_path(self):
        rc, out = self.run_check(spec(("POST", "/a")), spec(("GET", "/a")))
        self.assertEqual(rc, 1)

    def test_label_in_output_and_web_gateway_direction(self):
        # "web@live vs gateway@new": web's vendored copy of gateway's spec must be a SUBSET of the
        # candidate -- byte identity could never pass once gateway adds an operation
        rc, out = self.run_check(spec(("GET", "/a")), spec(("GET", "/a"), ("GET", "/new")),
                                 "--label", "web@live vs gateway@new")
        self.assertEqual(rc, 0)
        self.assertIn("web@live vs gateway@new", out)

    def test_zero_examined_fails(self):
        rc, out = self.run_check(json.dumps({"paths": {}}), spec(("GET", "/a")))
        self.assertEqual(rc, 1)
        self.assertIn("examined 0", out)

    def test_yaml_input(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML missing")  # the CI workflow installs it; see make check
        with tmpdir() as d:
            a = Path(d) / "tool.yaml"
            a.write_text("paths:\n  /a:\n    get: {}\n")
            b = Path(d) / "i.yaml"
            b.write_text("paths:\n  /a:\n    get: {}\n    post: {}\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ops_subset.main([str(a), str(b)]), 0)


class ReportTests(unittest.TestCase):
    def test_failure_report(self):
        md = report.render(stage="publish", result="failure", detail="deploy failed for gateway",
                           drafts={"core": 1, "gateway": 2},
                           statuses={"core": "published+live", "gateway": "published-deploy-failed",
                                     "web": "not published"})
        for needle in ("publish", "FAILED", "deploy failed for gateway", "core", "gateway", "web",
                       "published+live", "published-deploy-failed", "not published",
                       "burned"):
            self.assertIn(needle, md)

    def test_success_report(self):
        md = report.render(stage="publish", result="success", detail="",
                           drafts={"core": 1}, statuses={"core": "published+live"})
        self.assertIn("succeeded", md)
        self.assertNotIn("burned", md)


def call(argv, env=None, deps=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = release_flow.main(argv, env=env or {}, deps=deps or {})
    return rc, out.getvalue(), err.getvalue()


def manifest_file(d, text=None):
    p = Path(d) / "m.yaml"
    p.write_text(text or f"services:\n  - {{repo: core, version: v0.132.0, sha: {SHA_A}}}\n")
    return str(p)


def cfg_file(d):
    p = Path(d) / "services.json"
    p.write_text(json.dumps(CFG_DICT))
    return str(p)


AL = ",".join(ALLOWED)


class ReleaseFlowTests(unittest.TestCase):
    def base(self, d):
        return ["--config", cfg_file(d), "--allowed", AL]

    def fake(self):
        f = FakeGitHub()
        i = f.repo("core")
        i.add_release("v0.131.0")
        i.good_commit(SHA_A, "v0.132.0")
        i.add_tag("v0.132.0", SHA_A)
        green_ci(f, "core", SHA_A)
        return f

    def test_validate_ok_and_fail(self):
        with tmpdir() as d:
            f = self.fake()
            rc, out, err = call(["validate", manifest_file(d), *self.base(d)],
                                {"RELEASE_FLOW_READ_TOKEN": "t"}, {"transport": f})
            self.assertEqual(rc, 0, err)
            f.repo("core").compare[SHA_A] = "diverged"
            rc, out, err = call(["validate", manifest_file(d), *self.base(d)],
                                {"RELEASE_FLOW_READ_TOKEN": "t"}, {"transport": f})
            self.assertEqual(rc, 1)
            self.assertIn("main", err + out)

    def test_validate_requires_token_and_allowed(self):
        with tmpdir() as d:
            rc, _, err = call(["validate", manifest_file(d), *self.base(d)], {}, {})
            self.assertEqual(rc, 2)
            self.assertIn("RELEASE_FLOW_READ_TOKEN", err)
            with self.assertRaises(SystemExit) as cm:
                call(["validate", manifest_file(d), "--config", cfg_file(d)],
                     {"RELEASE_FLOW_READ_TOKEN": "t"}, {"transport": self.fake()})
            self.assertEqual(cm.exception.code, 2)

    def test_manifest_repo_outside_allowed(self):
        with tmpdir() as d:
            rc, _, err = call(["validate", manifest_file(d), "--config", cfg_file(d),
                               "--allowed", "gateway,web,site"], {"RELEASE_FLOW_READ_TOKEN": "t"},
                              {"transport": self.fake()})
            self.assertEqual(rc, 2)

    def test_services_json_wider_than_allowed(self):
        with tmpdir() as d:
            rc, _, err = call(["validate", manifest_file(d), "--config", cfg_file(d),
                               "--allowed", "core"], {"RELEASE_FLOW_READ_TOKEN": "t"},
                              {"transport": self.fake()})
            self.assertEqual(rc, 2)

    def test_bad_manifest_exit_2(self):
        with tmpdir() as d:
            rc, _, err = call(["validate", manifest_file(d, "services:\n"), *self.base(d)],
                              {"RELEASE_FLOW_READ_TOKEN": "t"}, {"transport": self.fake()})
            self.assertEqual(rc, 2)

    def test_drafts_requires_write_token(self):
        with tmpdir() as d:
            f = self.fake()
            rc, _, err = call(["drafts", manifest_file(d), *self.base(d)],
                              {"RELEASE_FLOW_READ_TOKEN": "t"}, {"transport": f})
            self.assertEqual(rc, 2)
            self.assertIn("RELEASE_FLOW_WRITE_TOKEN", err)
            self.assertEqual(f.requests, [])

    def test_drafts_ok_prints_json(self):
        with tmpdir() as d:
            f = self.fake()
            rc, out, err = call(["drafts", manifest_file(d), *self.base(d)],
                                {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w"},
                                {"transport": f})
            self.assertEqual(rc, 0, err)
            self.assertEqual(set(json.loads(out)), {"core"})

    def test_drafts_failure_still_prints_created_json(self):
        with tmpdir() as d:
            f = self.fake()
            f.repo("core").compare[SHA_A] = "diverged"
            rc, out, err = call(["drafts", manifest_file(d), *self.base(d)],
                                {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w"},
                                {"transport": f})
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads(out), {})
            self.assertEqual(f.writes(), [])

    def test_drafts_creates_no_tag_and_no_ref(self):
        with tmpdir() as d:
            f = self.fake()
            rc, _, err = call(["drafts", manifest_file(d), *self.base(d)],
                              {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w"}, {"transport": f})
            self.assertEqual(rc, 0, err)
            self.assertEqual([(m, p.split("/", 2)[2]) for m, p, _ in f.writes()],
                             [("POST", "core/releases")])

    def test_drafts_missing_tag_exit_1_zero_writes(self):
        with tmpdir() as d:
            f = self.fake()
            del f.repo("core").refs["v0.132.0"]
            rc, out, err = call(["drafts", manifest_file(d), *self.base(d)],
                                {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w"}, {"transport": f})
            self.assertEqual(rc, 1)
            self.assertIn("does not exist", err)
            self.assertEqual((json.loads(out), f.writes()), ({}, []))

    def test_drafts_midway_failure_prints_partial_json_then_exit_1(self):
        with tmpdir() as d:
            f = self.fake()
            f.fail.append(("POST", "core/releases", 0))  # response lost: the draft may exist
            rc, out, err = call(["drafts", manifest_file(d), *self.base(d)],
                                {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w"},
                                {"transport": f})
            self.assertEqual(rc, 1)
            self.assertIn("unknown", json.loads(out)["core"])

    def test_resolve_never_needs_write_token(self):
        with tmpdir() as d:
            f = self.fake()
            make_live(f)
            f.repo("tool").add_release("v1.0.0")
            rc, out, err = call(["resolve", manifest_file(d), *self.base(d)],
                                {"RELEASE_FLOW_READ_TOKEN": "r"}, {"transport": f})
            self.assertEqual(rc, 0, err)
            self.assertTrue(json.loads(out)["core"]["listed"])

    def test_resolve_drafts_proof_flag(self):
        with tmpdir() as d:
            f = self.fake()
            make_live(f)
            f.repo("tool").add_release("v1.0.0")
            f.repo("tool").can_push = False
            f.repo("core").add_release("v0.132.0", draft=True)
            env = {"RELEASE_FLOW_READ_TOKEN": "r"}
            m = manifest_file(d)
            rc, out, err = call(["resolve", m, *self.base(d), "--drafts-proof",
                                 "core:v0.132.0"], env, {"transport": f})
            self.assertEqual(rc, 0, err)
            rc, _, err = call(["resolve", m, *self.base(d), "--drafts-proof",
                               "core:v0.999.0"], env, {"transport": f})
            self.assertEqual(rc, 1)
            self.assertIn("cannot see the draft", err)
            for bad in ("core", "core:0.1.0", "web;x:v1.0.0", "tool:v1.0.0", "ghost:v1.0.0"):
                rc, _, err = call(["resolve", m, *self.base(d), "--drafts-proof", bad], env,
                                  {"transport": f})
                self.assertEqual(rc, 2, bad)  # bad shape, or repo outside --allowed

    def test_contract_states_subcommand(self):
        with tmpdir() as d:
            f = self.fake()
            make_live(f)
            f.repo("tool").add_release("v0.3.7")
            env = {"RELEASE_FLOW_READ_TOKEN": "r"}
            rc, out, err = call(["contract-states", manifest_file(d), *self.base(d)], env,
                                {"transport": f})
            self.assertEqual(rc, 0, err)
            self.assertEqual({(c["consumer"], c["provider"]) for c in json.loads(out)},
                             {("gateway", "core"), ("tool", "core"), ("web", "core")})
            web = f"services:\n  - {{repo: site, version: v0.4.0, sha: {SHA_B}}}\n"
            rc, out, err = call(["contract-states", manifest_file(d, web), *self.base(d)], env,
                                {"transport": f})
            self.assertEqual((rc, json.loads(out)), (0, []))
            self.assertIn("no contract", err)

    def test_order(self):
        with tmpdir() as d:
            m = manifest_file(d, f"services:\n  - {{repo: web, version: v1.0.0, sha: {SHA_A}}}\n"
                                 f"  - {{repo: core, version: v1.0.0, sha: {SHA_B}}}\n")
            rc, out, _ = call(["order", m, *self.base(d)])
            self.assertEqual((rc, out.split()), (0, ["core", "web"]))

    def test_gate_services_lists_only_the_listed_services_in_publish_order(self):
        with tmpdir() as d:
            m = manifest_file(d, f"services:\n  - {{repo: web, version: v1.2.3, sha: {SHA_A}}}\n"
                                 f"  - {{repo: core, version: v0.132.0, sha: {SHA_B}}}\n")
            rc, out, err = call(["gate-services", m, *self.base(d)])
            self.assertEqual(rc, 0, err)
            self.assertEqual(json.loads(out), [
                {"repo": "consumer-a-org/core", "tag": "v0.132.0", "sha": SHA_B},
                {"repo": "consumer-a-org/web", "tag": "v1.2.3", "sha": SHA_A}])
            self.assertEqual(out.count("\n"), 1, "one compact line, fit for $GITHUB_OUTPUT")

    def test_gate_services_empty_manifest_is_an_error_never_a_pass(self):
        with tmpdir() as d:
            rc, out, err = call(["gate-services", manifest_file(d, "services:\n"),
                                 *self.base(d)])
            self.assertNotEqual(rc, 0)
            self.assertEqual(out.strip(), "")
            self.assertIn("error", err)

    def test_gate_services_refuses_a_repo_outside_allowed(self):
        with tmpdir() as d:
            rc, out, _ = call(["gate-services", manifest_file(d), "--config", cfg_file(d),
                               "--allowed", "gateway"])
            self.assertEqual(rc, 2)
            self.assertEqual(out.strip(), "")

    def test_gate_services_function_rejects_zero_entries(self):
        import config
        with self.assertRaises(release_flow.Usage):
            release_flow.gate_services(config.from_dict(CFG_DICT), [])

    def publish_world(self):
        f = FakeGitHub()
        r = f.repo("core")
        r.stage_draft("v0.132.0", SHA_A)
        r.deploy_script = [("completed", "success")]
        return f

    def pub(self, d, env, repo="core", f=None):
        f = f or self.publish_world()
        clock = FakeClock()
        deps = {"transport": f, "health_get": lambda url: (200, {"data": {"status": "UP"}}),
                "clock": clock, "sleep": clock.sleep}
        return f, call(["publish", manifest_file(d), "--repo", repo, *self.base(d)], env, deps)

    def test_publish_ok(self):
        with tmpdir() as d:
            f, (rc, out, err) = self.pub(d, {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w",
                                             "GITHUB_RUN_ATTEMPT": "1"})
            self.assertEqual(rc, 0, err)
            self.assertEqual(json.loads(out)["status"], "published+live")

    def test_publish_refuses_rerun(self):
        with tmpdir() as d:
            f, (rc, _, err) = self.pub(d, {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w",
                                           "GITHUB_RUN_ATTEMPT": "2"})
            self.assertEqual(rc, 2)
            self.assertIn("GITHUB_RUN_ATTEMPT", err)
            self.assertEqual(f.requests, [])
            f, (rc, _, _) = self.pub(d, {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w"})
            self.assertEqual(rc, 2)  # unset is not "1"

    def test_publish_needs_write_token_and_listed_repo(self):
        with tmpdir() as d:
            f, (rc, _, _) = self.pub(d, {"RELEASE_FLOW_READ_TOKEN": "r", "GITHUB_RUN_ATTEMPT": "1"})
            self.assertEqual(rc, 2)
            f, (rc, _, _) = self.pub(d, {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w",
                                         "GITHUB_RUN_ATTEMPT": "1"}, repo="gateway")
            self.assertEqual(rc, 2)  # gateway is not in the manifest

    def test_publish_failure_exit_1(self):
        with tmpdir() as d:
            f = self.publish_world()
            f.repo("core").deploy_script = [("completed", "failure")]
            f, (rc, out, _) = self.pub(d, {"RELEASE_FLOW_READ_TOKEN": "r", "RELEASE_FLOW_WRITE_TOKEN": "w",
                                           "GITHUB_RUN_ATTEMPT": "1"}, f=f)
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads(out)["status"], "published-deploy-failed")

    def test_find_manifest(self):
        with tmpdir() as d:
            cfg = ["--config", cfg_file(d)]
            diff = lambda base, head: ["A\treleases/2026-10-09-x.yaml"]  # noqa: E731
            rc, out, _ = call(["find-manifest", "--base", "b", "--head", "h", "--pr", *cfg], {},
                              {"git_diff": diff})
            self.assertEqual((rc, out.strip()), (0, "releases/2026-10-09-x.yaml"))
            diff2 = lambda base, head: ["A\treleases/2026-10-09-x.yaml", "M\tMakefile"]  # noqa: E731
            rc, _, err = call(["find-manifest", "--base", "b", "--head", "h", *cfg], {},
                              {"git_diff": diff2})
            self.assertEqual(rc, 1)

    def test_check_merge_and_concurrent(self):
        f = FakeGitHub()
        p = f.repo("project")
        env = {"RELEASE_FLOW_READ_TOKEN": "r", "GITHUB_REPOSITORY": "consumer-a-org/project"}
        with tmpdir() as d:
            cfg = ["--config", cfg_file(d)]
            rc, _, err = call(["check-merge", "--sha", SHA_A, "--check-name", "release-pr", *cfg],
                              env, {"transport": f})
        self.assertEqual(rc, 1)  # direct push: no PR
        p.wf_runs = [{"id": 1, "status": "in_progress"}, {"id": 2, "status": "queued"}]
        rc, _, _ = call(["concurrent", "--workflow", "release.yml", "--run-id", "1"], env,
                        {"transport": f})
        self.assertEqual(rc, 1)
        rc, _, _ = call(["concurrent", "--workflow", "release.yml", "--run-id", "1"],
                        {"RELEASE_FLOW_READ_TOKEN": "r"}, {"transport": f})
        self.assertEqual(rc, 2)  # no GITHUB_REPOSITORY

    def test_ops_subset_and_report_subcommands(self):
        with tmpdir() as d:
            a = Path(d) / "a.json"
            a.write_text(spec(("GET", "/a")))
            rc, out, _ = call(["ops-subset", str(a), str(a), "--label", "web->gateway"])
            self.assertEqual(rc, 0)
            self.assertIn("web->gateway", out)
            b = Path(d) / "b.json"
            b.write_text(spec(("POST", "/z")))
            rc, out, _ = call(["ops-subset", str(a), str(b), "--label", "web->gateway"])
            self.assertEqual(rc, 1)
            self.assertIn("GET /a", out)
            self.assertIn("web->gateway", out)
            rc, out, _ = call(["report", "--stage", "drafts", "--result", "failure",
                               "--detail", "boom"])
            self.assertEqual(rc, 0)
            self.assertIn("boom", out)

    def test_spec_compat_subcommand(self):
        with tmpdir() as d:
            a, b = Path(d) / "a.json", Path(d) / "b.json"
            a.write_text(spec(("GET", "/a")))
            b.write_text(spec(("POST", "/z")))
            rc, out, _ = call(["spec-compat", str(a), str(a), "--label", "gateway@live → core"])
            self.assertEqual(rc, 0, out)
            self.assertIn("gateway@live → core", out)
            rc, out, _ = call(["spec-compat", str(a), str(b)])
            self.assertEqual(rc, 1)
            self.assertIn("GET /a", out)


if __name__ == "__main__":
    unittest.main()
