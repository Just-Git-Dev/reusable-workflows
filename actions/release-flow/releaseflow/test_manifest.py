"""Tests for manifest.py and config.py: the strict parser and the diff rule."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import manifest  # noqa: E402
from fake_github import ALLOWED, CFG_DICT, SHA_A, SHA_B  # noqa: E402

GOOD = f"""# a comment

services:
  - {{repo: core, version: v0.132.0, sha: {SHA_A}}}
  - {{repo: gateway,    version: v0.38.0,  sha: {SHA_B}}}
"""


def entry(repo="core", ver="v0.1.0", sha=SHA_A):
    return f"  - {{repo: {repo}, version: {ver}, sha: {sha}}}\n"


class ParseTests(unittest.TestCase):
    def test_good(self):
        es = manifest.parse(GOOD)
        self.assertEqual([(e.repo, e.version, e.sha) for e in es],
                         [("core", "v0.132.0", SHA_A), ("gateway", "v0.38.0", SHA_B)])

    def bad(self, text, line, fragment=""):
        with self.assertRaises(manifest.ManifestError) as cm:
            manifest.parse(text)
        self.assertIn(f"line {line}", str(cm.exception))
        self.assertIn(fragment, str(cm.exception))

    def test_empty_list(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.parse("services:\n")
        with self.assertRaises(manifest.ManifestError):
            manifest.parse("# nothing\n")

    def test_duplicate_repo(self):
        self.bad("services:\n" + entry() + entry(ver="v0.2.0"), 3, "duplicate")

    def test_bad_version(self):
        for v in ("0.1.0", "v1.2", "v1.2.3-rc1", "v01.2.3x"):
            self.bad("services:\n" + entry(ver=v), 2)

    def test_bad_sha(self):
        for s in ("abc", SHA_A.upper(), "g" * 40, SHA_A + "0"):
            self.bad("services:\n" + entry(sha=s), 2)

    def test_uppercase_sha_message_says_lowercase(self):
        with self.assertRaises(manifest.ManifestError) as cm:
            manifest.parse("services:\n" + entry(sha=SHA_A.upper()))
        self.assertIn("40 lowercase hex", str(cm.exception))

    def test_extra_key_or_order(self):
        self.bad(f"services:\n  - {{repo: a, version: v1.0.0, sha: {SHA_A}, x: 1}}\n", 2)
        self.bad(f"services:\n  - {{version: v1.0.0, repo: a, sha: {SHA_A}}}\n", 2)

    def test_entry_before_services_and_unknown_lines(self):
        self.bad(entry() + "services:\n", 1)
        self.bad("services:\n" + entry() + "other: 1\n", 3)
        self.bad("services:\n" + entry() + "services:\n", 3)

    def test_tabs_and_indentation(self):
        self.bad("services:\n" + entry().replace("  - ", "\t- "), 2)
        self.bad("services:\n" + entry().replace("  - ", "- "), 2)

    def test_trailing_comment_refused(self):
        self.bad("services:\n" + entry().rstrip("\n") + " # hi\n", 2)


class FindAddedTests(unittest.TestCase):
    P = "releases/2026-10-09-pw.yaml"

    def test_one_added(self):
        self.assertEqual(manifest.find_added([f"A\t{self.P}", "A\treleases/README.md"]), self.P)

    def test_modified_deleted_renamed_existing(self):
        for line in (f"M\t{self.P}", f"D\t{self.P}", f"R100\t{self.P}\treleases/x.yaml",
                     f"C100\treleases/old.yaml\t{self.P}"):
            with self.assertRaises(manifest.ManifestError, msg=line):
                manifest.find_added([f"A\treleases/2026-01-01-a.yaml", line])

    def test_zero_or_many(self):
        for lines in ([], ["A\treleases/README.md"],
                      [f"A\t{self.P}", "A\treleases/2026-10-10-b.yaml"]):
            with self.assertRaises(manifest.ManifestError):
                manifest.find_added(lines)

    def test_bad_name_refused(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.find_added(["A\treleases/Foo.yaml"])

    def test_whole_tree_rule(self):
        self.assertEqual(manifest.find_added([f"A\t{self.P}"], whole_tree=True), self.P)
        for extra in ("M\tMakefile", "A\t.github/workflows/release.yml",
                      "A\treleases/services.json", "D\tREADME.md"):
            with self.assertRaises(manifest.ManifestError, msg=extra):
                manifest.find_added([f"A\t{self.P}", extra], whole_tree=True)


class ConfigTests(unittest.TestCase):
    def test_load_real_file(self):
        cfg = config.load(Path(__file__).resolve().parent / "testdata" / "services.json")
        self.assertEqual([s.repo for s in cfg.services], ["core", "gateway", "web", "site"])
        self.assertEqual(cfg.consumers_only, ["tool"])
        self.assertEqual(cfg.owner, "consumer-a-org")
        self.assertEqual(cfg.service("core").image, "backend/core")
        self.assertEqual(cfg.service("gateway").image, "backend/gateway")
        self.assertEqual(cfg.service("web").kind, "pages")
        for s in cfg.services:
            self.assertEqual(s.deploy_workflow, "deploy.yml")

    def test_order_sorted(self):
        d = json.loads(json.dumps(CFG_DICT))
        d["services"].reverse()
        self.assertEqual([s.repo for s in config.from_dict(d).services],
                         ["core", "gateway", "web", "site"])

    def test_invalid(self):
        def mut(f):
            d = json.loads(json.dumps(CFG_DICT))
            f(d)
            return d
        cases = [
            mut(lambda d: d["services"][0].pop("health_url")),
            mut(lambda d: d["services"][0].pop("image")),
            mut(lambda d: d["services"][0].update(kind="vm")),
            mut(lambda d: d["services"][2].update(health_url="https://x")),
            mut(lambda d: d["services"][1].update(order=1)),
            mut(lambda d: d["services"][1].update(repo="core")),
            mut(lambda d: d.pop("owner")),
            mut(lambda d: d["services"][0].pop("deploy_workflow")),
            mut(lambda d: d.update(consumers_only=["gateway"])),
        ]
        for d in cases:
            with self.assertRaises(config.ConfigError, msg=str(d)):
                config.from_dict(d)

    def test_consumers_only_are_unique_nonempty_names(self):
        for bad in ([""], ["tool", "tool"], [3]):
            d = json.loads(json.dumps(CFG_DICT))
            d["consumers_only"] = bad
            with self.assertRaises(config.ConfigError, msg=str(bad)):
                config.from_dict(d)
        self.assertIn("non-flow", config.__doc__)

    def test_restrict_allowed(self):
        cfg = config.from_dict(CFG_DICT)
        cfg.restrict(ALLOWED)  # ok
        with self.assertRaises(config.ConfigError):
            cfg.restrict(["core", "gateway"])  # services.json lists web/site too
        self.assertEqual(config.parse_allowed("core, gateway"), ["core", "gateway"])
        with self.assertRaises(config.ConfigError):
            config.parse_allowed("")

    def test_manifest_outside_allowed(self):
        es = manifest.parse(GOOD)
        manifest.check_allowed(es, ["core", "gateway"])
        with self.assertRaises(manifest.ManifestError):
            manifest.check_allowed(es, ["core"])


if __name__ == "__main__":
    unittest.main()
