"""Tests for ci.py (H8: each listed commit's own CI must be green) and the ci-green command."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci  # noqa: E402
import config  # noqa: E402
import release_flow  # noqa: E402
import gh  # noqa: E402
import manifest  # noqa: E402
from fake_github import (ALLOWED, CFG_DICT, FakeGitHub, SHA_A, SHA_B, SHA_C, ci_run,  # noqa: E402
                         green_ci)

CFG = config.from_dict(CFG_DICT)
E = manifest.Entry
P1, P2, P3 = "1" * 40, "2" * 40, "3" * 40


def check(f, entries):
    return ci.check(gh.Reader(f), CFG, entries)


class GlobTests(unittest.TestCase):
    def test_semantics(self):
        yes = [("**.md", "README.md"), ("**.md", "a/b/README.md"), ("*.md", "README.md"),
               ("docs/**", "docs/a/b.txt"), ("docs/**", "docs/x"), ("**/*.md", "a/b.md"),
               ("**/*.md", "b.md"), (".github/workflows/x.yml", ".github/workflows/x.yml"),
               ("src/?.go", "src/a.go")]
        no = [("**.md", "a.mdx"), ("*.md", "a/README.md"), ("docs/**", "docsx/a"),
              ("docs/**", "other/docs/a"), ("src/?.go", "src/ab.go"), ("src/?.go", "src/a/b.go"),
              ("a.b", "aXb"), ("*.md", "README.md\n.go")]
        for pat, path in yes:
            self.assertTrue(ci.glob_match(pat, path), (pat, path))
        for pat, path in no:
            self.assertFalse(ci.glob_match(pat, path), (pat, path))


class CheckTests(unittest.TestCase):
    def test_green_counts_examined(self):
        f = FakeGitHub()
        green_ci(f, "core", SHA_A)
        green_ci(f, "gateway", SHA_B)
        failures, examined = check(f, [E("core", "v1.0.0", SHA_A), E("gateway", "v1.0.0", SHA_B)])
        self.assertEqual((failures, examined), ([], 3))  # tests.yml, changelog-hygiene, ci.yml
        runs = [r[1] for r in f.requests if "/runs" in r[1]]
        self.assertEqual(len(runs), 3)
        for path in runs:
            self.assertIn("head_sha=", path)
            self.assertIn("event=push", path)

    def test_newest_run_decides(self):
        f = FakeGitHub()
        green_ci(f, "gateway", SHA_B)
        f.repo("gateway").ci_runs[("ci.yml", SHA_B)] = [
            ci_run("2026-10-01T00:00:00Z", conclusion="failure", n=5),
            ci_run("2026-10-02T00:00:00Z", conclusion="success", n=6)]  # re-run went green
        self.assertEqual(check(f, [E("gateway", "v1.0.0", SHA_B)])[0], [])
        f.repo("gateway").ci_runs[("ci.yml", SHA_B)].append(
            ci_run("2026-10-03T00:00:00Z", conclusion="failure", n=7))
        out = check(f, [E("gateway", "v1.0.0", SHA_B)])[0]
        self.assertTrue(out and "actions/runs/7" in out[0])

    def test_in_progress_not_finished_failed_names_url(self):
        f = FakeGitHub()
        green_ci(f, "gateway", SHA_B)
        f.repo("gateway").ci_runs[("ci.yml", SHA_B)] = [
            ci_run(status="in_progress", conclusion=None, n=8)]
        out = check(f, [E("gateway", "v1.0.0", SHA_B)])[0]
        self.assertTrue(any("not finished yet" in m for m in out))
        for concl in ("failure", "cancelled", None):
            f.repo("gateway").ci_runs[("ci.yml", SHA_B)] = [ci_run(conclusion=concl, n=9)]
            out = check(f, [E("gateway", "v1.0.0", SHA_B)])[0]
            self.assertTrue(out and "actions/runs/9" in out[0], concl)

    def test_missing_run_without_paths_ignore(self):
        f = FakeGitHub()
        f.repo("gateway")
        out = check(f, [E("gateway", "v1.0.0", SHA_B)])[0]
        self.assertTrue(any("missing" in m and "ci.yml" in m for m in out))

    def docs_only_commit(self):
        """P3's tests.yml never ran (docs-only push); P3 -> P2 -> P1 -> root."""
        f = FakeGitHub()
        green_ci(f, "core", P3)
        r = f.repo("core")
        del r.ci_runs[("tests.yml", P3)]
        r.parents = {P3: [P2], P2: [P1], P1: ["0" * 40]}
        return f, r

    def test_paths_ignore_walks_to_ancestor_and_checks_files(self):
        f, r = self.docs_only_commit()
        r.ci_runs[("tests.yml", P1)] = [ci_run(n=11)]     # two back
        r.compare_files[(P1, P3)] = ["README.md", "docs/a/b.txt", "x/CHANGELOG.md"]
        self.assertEqual(check(f, [E("core", "v1.0.0", P3)])[0], [])

    def test_ancestor_walk_rejects_non_ignored_file_or_bad_ancestor(self):
        f, r = self.docs_only_commit()
        r.ci_runs[("tests.yml", P2)] = [ci_run(n=12)]
        r.compare_files[(P2, P3)] = ["README.md", "internal/x.go"]
        out = check(f, [E("core", "v1.0.0", P3)])[0]
        self.assertTrue(out and "internal/x.go" in out[0], out)
        r.compare_files[(P2, P3)] = ["README.md"]
        r.ci_runs[("tests.yml", P2)] = [ci_run(conclusion="failure", n=13)]
        out = check(f, [E("core", "v1.0.0", P3)])[0]
        self.assertTrue(out and "actions/runs/13" in out[0])

    def test_ancestor_walk_limit_and_no_parent(self):
        f, r = self.docs_only_commit()
        chain = [f"{i:040x}" for i in range(1, 40)]
        r.parents = {chain[i]: [chain[i + 1]] for i in range(len(chain) - 1)}
        r.parents[P3] = [chain[0]]
        r.ci_runs[("tests.yml", chain[25])] = [ci_run(n=14)]  # 26 back: out of range
        r.compare_files[(chain[25], P3)] = []
        out = check(f, [E("core", "v1.0.0", P3)])[0]
        self.assertTrue(out and "within 20" in out[0], out)
        r.parents = {P3: []}  # root commit
        self.assertTrue(check(f, [E("core", "v1.0.0", P3)])[0])

    def test_compare_truncated_or_unreadable_fails(self):
        f, r = self.docs_only_commit()
        r.ci_runs[("tests.yml", P2)] = [ci_run(n=15)]
        r.compare_files[(P2, P3)] = ["a.md"] * 300  # GitHub caps the file list at 300
        self.assertTrue(check(f, [E("core", "v1.0.0", P3)])[0])
        del r.compare_files[(P2, P3)]
        self.assertTrue(check(f, [E("core", "v1.0.0", P3)])[0])

    def test_collects_all_failures(self):
        f = FakeGitHub()
        f.repo("core"), f.repo("gateway")
        failures, examined = check(f, [E("core", "v1.0.0", SHA_A), E("gateway", "v1.0.0", SHA_B)])
        self.assertEqual(examined, 3)
        self.assertGreaterEqual(len(failures), 3)

    def test_repo_without_ci_configured_fails(self):
        d = json.loads(json.dumps(CFG_DICT))
        d["services"][3].pop("ci")
        failures, examined = ci.check(gh.Reader(FakeGitHub()), config.from_dict(d),
                                      [E("site", "v1.0.0", SHA_C)])
        self.assertEqual(examined, 0)
        self.assertTrue(any("no CI workflows" in m for m in failures))

    def test_api_error_is_a_failure(self):
        f = FakeGitHub()
        green_ci(f, "gateway", SHA_B)
        f.fail.append(("GET", "workflows/ci.yml/runs", 500))
        self.assertTrue(any("500" in m for m in check(f, [E("gateway", "v1.0.0", SHA_B)])[0]))


class CommandTests(unittest.TestCase):
    def call(self, argv, f):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = release_flow.main(argv, env={"RELEASE_FLOW_READ_TOKEN": "t"}, deps={"transport": f})
        return rc, err.getvalue()

    def test_ci_green_command(self):
        root = Path(__file__).resolve().parents[3] / ".scratch" / "test-tmp"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as d:
            (Path(d) / "c.json").write_text(json.dumps(CFG_DICT))
            (Path(d) / "m.yaml").write_text(
                f"services:\n  - {{repo: gateway, version: v0.38.0, sha: {SHA_B}}}\n")
            argv = ["ci-green", str(Path(d) / "m.yaml"), "--config", str(Path(d) / "c.json"),
                    "--allowed", ",".join(ALLOWED)]
            f = FakeGitHub()
            green_ci(f, "gateway", SHA_B)
            rc, err = self.call(argv, f)
            self.assertEqual(rc, 0, err)
            self.assertIn("examined 1", err)
            f.repo("gateway").ci_runs.clear()
            rc, err = self.call(argv, f)
            self.assertEqual(rc, 1)
            self.assertIn("missing", err)


class ConfigCiTests(unittest.TestCase):
    def test_real_file_ci(self):
        cfg = config.load(Path(__file__).resolve().parent / "testdata" / "services.json")
        got = {s.repo: [(w, tuple(p)) for w, p in s.ci] for s in cfg.services}
        self.assertEqual(got["core"], [("tests.yml", ("**.md", "docs/**")),
                                         ("deploy.yml", ()),
                                         ("changelog-hygiene.yml", ()),
                                         ("workflow-hygiene.yml", ())])
        self.assertEqual([w for w, _ in cfg.service("gateway").ci],
                         ["ci.yml", "deploy.yml", "changelog-hygiene.yml"])
        self.assertEqual([w for w, _ in cfg.service("web").ci],
                         ["test.yml", "changelog-hygiene.yml", "workflow-hygiene.yml"])
        self.assertEqual([w for w, _ in cfg.service("site").ci],
                         ["changelog-hygiene.yml", "workflow-hygiene.yml"])

    def test_bad_ci_entry(self):
        d = json.loads(json.dumps(CFG_DICT))
        d["services"][0]["ci"] = [{"workflow": "t.yml", "paths_ignore": "**.md"}]
        with self.assertRaises(config.ConfigError):
            config.from_dict(d)
        d["services"][0]["ci"] = [{"paths_ignore": []}]
        with self.assertRaises(config.ConfigError):
            config.from_dict(d)


if __name__ == "__main__":
    unittest.main()
