"""Tests for the configurable parts of services.json: release_dir, base_branch, changelog,
deploy_run_name, per-service health, and the `download` kind; and the places that read them
(manifest path rule, validate, guard.check_merge, resolve)."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import gh  # noqa: E402
import guard  # noqa: E402
import manifest  # noqa: E402
import resolve  # noqa: E402
import validate  # noqa: E402
from fake_github import CFG_DICT, FakeGitHub, SHA_A, SHA_B, make_live, run  # noqa: E402


def cfg_dict(**top):
    d = copy.deepcopy(CFG_DICT)
    d.update(top)
    return d


def svc(d, repo):
    return next(s for s in d["services"] if s["repo"] == repo)


DOWNLOAD = {"repo": "desktop", "kind": "download", "order": 9, "deploy_workflow": "release.yml",
            "assets": ["Setup.msi", "app.exe"], "ci": [{"workflow": "gate.yml"}]}


def bad(test, d, *needles):
    with test.assertRaises(config.ConfigError) as cm:
        config.from_dict(d)
    for n in needles:
        test.assertIn(n, str(cm.exception))


class ConfigDefaultsTests(unittest.TestCase):
    def test_defaults(self):
        cfg = config.from_dict(cfg_dict())
        self.assertEqual(cfg.release_dir, "releases")
        self.assertEqual(cfg.base_branch, "main")
        self.assertEqual((cfg.changelog.path, cfg.changelog.heading),
                         ("CHANGELOG.md", "## {version}"))
        self.assertEqual(cfg.deploy_run_name, "Deploy {tag}")
        self.assertEqual(tuple(cfg.service("issuer").health), ("data.status", "UP"))
        self.assertEqual(cfg.service("issuer").assets, ())

    def test_overrides(self):
        d = cfg_dict(release_dir="ops/rel", base_branch="release/prod", deploy_run_name="Ship {tag}!",
                     changelog={"path": "docs/CHANGES.md", "heading": "## [{version}]"})
        svc(d, "issuer")["health"] = {"path": "a.b", "expect": "ok"}
        cfg = config.from_dict(d)
        self.assertEqual((cfg.release_dir, cfg.base_branch, cfg.deploy_run_name),
                         ("ops/rel", "release/prod", "Ship {tag}!"))
        self.assertEqual((cfg.changelog.path, cfg.changelog.heading),
                         ("docs/CHANGES.md", "## [{version}]"))
        self.assertEqual(tuple(cfg.service("issuer").health), ("a.b", "ok"))

    def test_changelog_null_disables(self):
        self.assertIsNone(config.from_dict(cfg_dict(changelog=None)).changelog)

    def test_release_dir_rejected(self):
        for v in ("", "/abs", "a/../b", "..", "a//b", "./x", 5, None, "a b", "a\\b", "a..b"):
            bad(self, cfg_dict(release_dir=v), "release_dir")

    def test_base_branch_rejected(self):
        for v in ("", 5, None, "a b", "x..y", "/main", "main/"):
            bad(self, cfg_dict(base_branch=v), "base_branch")

    def test_changelog_rejected(self):
        for v in ("CHANGELOG.md", [], {"path": "C.md", "heading": "## x"},
                  {"path": "../C.md"}, {"path": "/C.md"}, {"path": ""}, {"path": 3},
                  {"heading": 3}, {"colour": "red"}):
            bad(self, cfg_dict(changelog=v), "changelog")

    def test_deploy_run_name_rejected(self):
        for v in ("Deploy", "Deploy {tag} {tag}", "", 5, None):
            bad(self, cfg_dict(deploy_run_name=v), "deploy_run_name")

    def test_health_rejected_with_service_and_key(self):
        for v in ({"path": "a"}, {"expect": "UP"}, {"path": "", "expect": "UP"},
                  {"path": "a..b", "expect": "UP"}, {"path": ".a", "expect": "UP"},
                  {"path": "a", "expect": ""}, {"path": 3, "expect": "UP"}, "UP",
                  {"path": "a", "expect": "UP", "extra": 1}):
            d = cfg_dict()
            svc(d, "issuer")["health"] = v
            bad(self, d, "service issuer", "health")

    def test_health_forbidden_on_other_kinds(self):
        d = cfg_dict()
        svc(d, "ui")["health"] = {"path": "a", "expect": "UP"}
        bad(self, d, "service ui", "health")
        d = cfg_dict()
        d["services"].append({**DOWNLOAD, "health": {"path": "a", "expect": "UP"}})
        bad(self, d, "service desktop", "health")


class DownloadKindTests(unittest.TestCase):
    def test_download_accepted(self):
        d = cfg_dict()
        d["services"].append(copy.deepcopy(DOWNLOAD))
        s = config.from_dict(d).service("desktop")
        self.assertEqual((s.kind, s.assets, s.health, s.health_url, s.image),
                         ("download", ("Setup.msi", "app.exe"), None, None, None))

    def test_assets_required_and_shaped(self):
        for v in (None, [], "Setup.msi", ["a", "a"], ["a", ""], ["a", 3]):
            d = cfg_dict()
            s = copy.deepcopy(DOWNLOAD)
            if v is None:
                del s["assets"]
            else:
                s["assets"] = v
            d["services"].append(s)
            bad(self, d, "service desktop", "assets")

    def test_assets_forbidden_on_other_kinds(self):
        for repo in ("issuer", "ui"):
            d = cfg_dict()
            svc(d, repo)["assets"] = ["a.zip"]
            bad(self, d, f"service {repo}", "assets")

    def test_download_takes_no_health_url_or_image(self):
        for key, val in (("health_url", "https://x.test/h"), ("image", "a/b")):
            d = cfg_dict()
            d["services"].append({**copy.deepcopy(DOWNLOAD), key: val})
            bad(self, d, "service desktop", key)

    def test_unknown_kind_names_all_three(self):
        d = cfg_dict()
        svc(d, "ui")["kind"] = "zip"
        bad(self, d, "service ui", "download")


class GarRegistryTests(unittest.TestCase):
    def test_not_required_without_image_services(self):
        d = cfg_dict()
        del d["gar_registry"]
        d["services"] = [svc(d, "ui"), copy.deepcopy(DOWNLOAD)]
        d["contracts"] = []
        d["consumers_only"] = []
        cfg = config.from_dict(d)
        self.assertEqual([s.repo for s in cfg.services], ["ui", "desktop"])

    def test_required_with_an_image_service(self):
        d = cfg_dict()
        del d["gar_registry"]
        bad(self, d, "gar_registry")


class ManifestPathRuleTests(unittest.TestCase):
    P = "ops/rel/2026-10-09-fix.yaml"

    def test_release_dir_drives_the_rule(self):
        self.assertEqual(manifest.find_added([f"A\t{self.P}"], release_dir="ops/rel"), self.P)
        self.assertEqual(manifest.find_added([f"A\t{self.P}"], whole_tree=True,
                                             release_dir="ops/rel"), self.P)

    def test_default_dir_is_releases_and_other_dir_is_not_a_manifest(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.find_added([f"A\t{self.P}"])  # default releases/
        with self.assertRaises(manifest.ManifestError):
            manifest.find_added(["A\treleases/2026-10-09-fix.yaml"], release_dir="ops/rel")

    def test_release_dir_is_regex_escaped(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.find_added(["A\topsXrel/2026-10-09-fix.yaml"], release_dir="ops.rel")
        self.assertEqual(manifest.find_added(["A\tops.rel/2026-10-09-fix.yaml"],
                                             release_dir="ops.rel"),
                         "ops.rel/2026-10-09-fix.yaml")

    def test_name_shape_enforced_in_custom_dir(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.find_added(["A\tops/rel/Foo.yaml"], release_dir="ops/rel")

    def test_existing_manifest_in_custom_dir_is_immutable(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.find_added([f"A\t{self.P}", "M\tops/rel/2026-01-01-old.yaml"],
                                release_dir="ops/rel")

    def test_manifest_path_ok(self):
        self.assertTrue(manifest.path_ok(self.P, "ops/rel"))
        self.assertFalse(manifest.path_ok("releases/2026-10-09-fix.yaml", "ops/rel"))
        self.assertFalse(manifest.path_ok("ops/rel/../x/2026-10-09-fix.yaml", "ops/rel"))


def v_world(branch="main", changelog_path="CHANGELOG.md"):
    f = FakeGitHub()
    i = f.repo("issuer")
    i.add_release("v0.131.0")
    i.good_commit(SHA_A, "v0.132.0")
    i.add_tag("v0.132.0", SHA_A)
    i.base_branch = branch
    i.changelog_path = changelog_path
    return f, i, [manifest.Entry("issuer", "v0.132.0", SHA_A)]


def check(f, es, **top):
    return validate.validate_manifest(gh.Reader(f), config.from_dict(cfg_dict(**top)), es)


class ValidateOptionsTests(unittest.TestCase):
    def test_base_branch_is_the_compare_base(self):
        f, i, es = v_world(branch="release/prod")
        self.assertEqual(check(f, es, base_branch="release/prod"), [])
        self.assertTrue(any("compare/release/prod..." in r[1] for r in f.requests))
        i.compare[SHA_A] = "diverged"
        out = check(f, es, base_branch="release/prod")
        self.assertEqual(len(out), 1)
        self.assertIn("release/prod", out[0])
        # the default (main) is not silently used: the fake answers only for release/prod
        self.assertTrue(any("not on main" in x or "not found" in x or "cannot compare" in x
                            for x in check(f, es)))

    def test_changelog_path_and_heading(self):
        f, i, es = v_world(changelog_path="docs/CHANGES.md")
        i.changelog[SHA_A] = "# Changes\n\n## [v0.132.0]\n- x\n"
        top = {"changelog": {"path": "docs/CHANGES.md", "heading": "## [{version}]"}}
        self.assertEqual(check(f, es, **top), [])
        i.changelog[SHA_A] = "# Changes\n\n## [v0.132.0]x\n"
        out = check(f, es, **top)
        self.assertEqual(len(out), 1)
        self.assertIn("docs/CHANGES.md", out[0])
        self.assertIn("## [v0.132.0]", out[0])
        i.changelog[SHA_A] = "# Changes\n\n## [v0.132.0] - 2026-10-09\n"
        self.assertEqual(check(f, es, **top), [])  # followed by whitespace: fine
        i.changelog[SHA_A] = "# Changes\n\n## v0.132.0\n"  # the OLD default heading: now wrong
        self.assertEqual(len(check(f, es, **top)), 1)

    def test_changelog_null_skips_the_check_entirely(self):
        f, i, es = v_world()
        del i.changelog[SHA_A]  # unreadable: would fail if the check ran
        self.assertEqual(check(f, es, changelog=None), [])
        self.assertFalse(any("contents/" in r[1] for r in f.requests))
        self.assertEqual(len(check(f, es)), 1)  # default config: the file is required


class GuardOptionsTests(unittest.TestCase):
    ROOT = "consumer-a-org/project"

    def good(self, base="main", path=".github/workflows/release-pr.yml"):
        f = FakeGitHub()
        p = f.repo("project")
        p.pulls[SHA_A] = [{"number": 7, "merged_at": "2026-10-09T00:00:00Z",
                           "base": {"ref": base}, "head": {"sha": SHA_B}}]
        p.check_runs[SHA_B] = [{"name": "release-pr", "status": "completed",
                                "conclusion": "success", "app": {"slug": "github-actions"},
                                "check_suite": {"id": 55}}]
        p.suite_runs = {55: [{"path": path}]}
        return f

    def merge(self, f, **kw):
        return guard.check_merge(gh.Reader(f), self.ROOT, SHA_A, "release-pr", **kw)

    def test_base_branch(self):
        f = self.good(base="develop")
        self.assertEqual(self.merge(f, base_branch="develop"), 7)
        with self.assertRaises(guard.GuardError) as cm:
            self.merge(f, base_branch="main")
        self.assertIn("main", str(cm.exception))
        with self.assertRaises(guard.GuardError):
            self.merge(self.good(base="main"), base_branch="develop")

    def test_workflow_path(self):
        f = self.good(path=".github/workflows/pr-gate.yml")
        self.assertEqual(self.merge(f, workflow_path=".github/workflows/pr-gate.yml"), 7)
        with self.assertRaises(guard.GuardError) as cm:
            self.merge(f)  # default release-pr.yml
        self.assertIn("release-pr.yml", str(cm.exception))
        with self.assertRaises(guard.GuardError):
            self.merge(self.good(), workflow_path=".github/workflows/pr-gate.yml")


def r_world():
    f = FakeGitHub()
    for n in ("issuer", "api", "ui", "website", "cli"):
        f.repo(n)
    make_live(f)
    f.repo("cli").add_release("v0.3.7")
    return f


def res(f, entries, **top):
    return resolve.resolve(gh.Reader(f), config.from_dict(cfg_dict(**top)), entries)


class ResolveOptionsTests(unittest.TestCase):
    def test_title_regex_and_dryrun_marker_follow_the_template(self):
        f = r_world()
        f.repo("api").live_runs = [
            run("v0.99.0", "2026-09-03T00:00:00Z", title="Ship DRYRUN now"),  # newest: skipped
            run("v0.37.0", "2026-09-02T00:00:00Z", title="Ship v0.37.0 now"),
            run("v0.36.0", "2026-09-01T00:00:00Z", title="Ship v0.36.0 now")]
        out = res(f, [manifest.Entry("issuer", "v0.132.0", SHA_A)], deploy_run_name="Ship {tag} now")
        self.assertEqual(out["api"]["live_ref"], "v0.37.0")

    def test_default_dryrun_marker_is_not_the_custom_one(self):
        f = r_world()
        f.repo("api").live_runs = [run("v0.37.0", "2026-09-02T00:00:00Z",
                                       title="Deploy DRYRUN v0.37.0")]
        # under the custom template this title is not a dry run and not a version title either
        with self.assertRaises(resolve.ResolveError):
            f.repo("api").live_runs[0]["event"] = "workflow_dispatch"
            res(f, [manifest.Entry("issuer", "v0.132.0", SHA_A)], deploy_run_name="Ship {tag} now")

    def test_template_is_regex_escaped(self):
        f = r_world()
        f.repo("api").live_runs = [run("main", "2026-09-02T00:00:00Z", title="Deploy [v0.37.0]",
                                       event="workflow_dispatch")]
        out = res(f, [manifest.Entry("issuer", "v0.132.0", SHA_A)], deploy_run_name="Deploy [{tag}]")
        self.assertEqual(out["api"]["live_ref"], "v0.37.0")
        f.repo("api").live_runs = [run("main", "2026-09-02T00:00:00Z", title="Deploy Xv0.37.0Y",
                                       event="workflow_dispatch")]
        with self.assertRaises(resolve.ResolveError):  # '[' must not act as a character class
            res(f, [manifest.Entry("issuer", "v0.132.0", SHA_A)], deploy_run_name="Deploy [{tag}]")

    def test_suffix_must_match(self):
        f = r_world()
        f.repo("api").live_runs = [run("main", "2026-09-02T00:00:00Z", title="Ship v0.37.0 later",
                                       event="workflow_dispatch")]
        with self.assertRaises(resolve.ResolveError):
            res(f, [manifest.Entry("issuer", "v0.132.0", SHA_A)], deploy_run_name="Ship {tag} now")

    def test_every_emitted_ref_is_a_sha_or_a_version(self):
        out = res(r_world(), [manifest.Entry("issuer", "v0.132.0", SHA_A)])
        import re
        for name, e in out.items():
            self.assertRegex(e["ref"], r"^([0-9a-f]{40}|v[0-9]+\.[0-9]+\.[0-9]+)$", name)

    def test_a_bad_ref_is_refused(self):
        for bad_sha in ("main", "A" * 40, "abc123", SHA_A[:-1], "v1.2", "-x"):
            with self.assertRaises(resolve.ResolveError, msg=bad_sha):
                res(r_world(), [manifest.Entry("issuer", "v0.132.0", bad_sha)])


if __name__ == "__main__":
    unittest.main()
