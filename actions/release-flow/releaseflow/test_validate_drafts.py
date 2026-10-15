"""Tests for validate.py, drafts.py, resolve.py."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import drafts  # noqa: E402
import gh  # noqa: E402
import manifest  # noqa: E402
import resolve  # noqa: E402
import validate  # noqa: E402
from fake_github import (CFG_DICT, FakeGitHub, OWNER, SHA_A, SHA_B, SHA_C,  # noqa: E402
                         green_ci)

CFG = config.from_dict(CFG_DICT)


def E(repo, ver, sha):
    return manifest.Entry(repo, ver, sha)


def world():
    """core latest v0.131.0, gateway latest v0.37.0; both candidate commits good, and the
    owner has already pushed the annotated tags v0.132.0 / v0.38.0 on them."""
    f = FakeGitHub()
    i, a = f.repo("core"), f.repo("gateway")
    i.add_release("v0.131.0")
    a.add_release("v0.37.0")
    i.good_commit(SHA_A, "v0.132.0")
    a.good_commit(SHA_B, "v0.38.0")
    i.add_tag("v0.132.0", SHA_A)
    a.add_tag("v0.38.0", SHA_B)
    green_ci(f, "core", SHA_A)
    green_ci(f, "gateway", SHA_B)
    return f, [E("core", "v0.132.0", SHA_A), E("gateway", "v0.38.0", SHA_B)]


def check(f, entries):
    return validate.validate_manifest(gh.Reader(f), CFG, entries)


class ValidateTests(unittest.TestCase):
    def test_happy(self):
        f, es = world()
        self.assertEqual(check(f, es), [])
        self.assertEqual([r for r in f.requests if r[0] != "GET"], [])

    def test_no_previous_release_is_ok(self):
        f, es = world()
        i = f.repo("core")
        i.releases.clear()
        del i.refs["v0.131.0"]
        self.assertEqual(check(f, es), [])

    def test_greater_than_highest_release_even_with_stale_releases(self):
        # live bug: releases/latest said v0.5.0 while the real version was v0.131.0; the
        # highest RELEASE (not "latest", not the newest by date) is the bar
        f, es = world()
        i = f.repo("core")
        i.releases.clear()
        i.add_release("v0.5.0")
        i.add_release("v0.131.0")
        i.add_release("v0.20.0")
        i.good_commit(SHA_A, "v0.130.0")
        i.add_tag("v0.130.0", SHA_A)
        out = check(f, [E("core", "v0.130.0", SHA_A)])
        self.assertTrue(any("not greater" in m and "v0.131.0" in m for m in out), out)
        i.good_commit(SHA_A, "v0.132.0")
        self.assertEqual(check(f, es), [])

    def test_burned_draft_release_counts_and_non_semver_releases_ignored(self):
        f, es = world()
        i = f.repo("core")
        i.add_release("v0.140.0", draft=True)
        i.add_release("vnext")
        i.add_release("v1.2")
        self.assertTrue(any("not greater" in m and "v0.140.0" in m for m in check(f, es)))
        i.releases[:] = [r for r in i.releases if r["tag_name"] != "v0.140.0"]
        self.assertEqual(check(f, es), [])

    def test_listed_version_must_be_the_newest_version_tag(self):
        # stale Releases: a typo'd v0.13.2 is "greater" than the highest Release (v0.5.0)
        f, _ = world()
        i = f.repo("core")
        i.releases.clear()
        del i.refs["v0.132.0"]  # world()'s tag for the normal case
        i.add_release("v0.5.0")
        i.refs["v0.131.0"] = {"type": "commit", "sha": SHA_A}  # legacy tag, no Release
        i.good_commit(SHA_A, "v0.13.2")
        i.add_tag("v0.13.2", SHA_A)
        out = check(f, [E("core", "v0.13.2", SHA_A)])
        self.assertTrue(any("not the newest version tag (newest is v0.131.0)" in m
                            for m in out), out)

    def test_newest_version_tag_rule_counts_burned_tags_and_passes_when_newest(self):
        f, es = world()
        f.repo("core").refs["v0.140.0"] = {"type": "tag", "sha": SHA_A}  # burned
        out = check(f, es)
        self.assertTrue(any("newest is v0.140.0" in m for m in out), out)
        del f.repo("core").refs["v0.140.0"]
        self.assertEqual(check(f, es), [])

    def test_releases_are_paginated_and_latest_endpoint_unused(self):
        f, es = world()
        f.page_size = 2
        i = f.repo("core")
        for n in range(6):
            i.add_release(f"v0.0.{n}")
        i.add_release("v0.500.0")  # last page
        self.assertTrue(any("not greater" in m for m in check(f, es)))
        self.assertFalse(any("releases/latest" in r[1] for r in f.requests))

    def test_release_list_error_is_a_failure(self):
        f, es = world()
        f.fail.append(("GET", "/releases", 500))
        self.assertTrue(any("500" in m for m in check(f, es)))

    def test_version_not_greater(self):
        for v in ("v0.131.0", "v0.130.9", "v0.9.0"):
            f, es = world()
            f.repo("core").good_commit(SHA_A, v)
            out = check(f, [E("core", v, SHA_A)])
            self.assertTrue(any("not greater" in m for m in out), (v, out))

    def test_numeric_not_lexical_compare(self):
        f, _ = world()
        f.repo("core").good_commit(SHA_A, "v0.200.0")
        f.repo("core").add_tag("v0.200.0", SHA_A)
        self.assertEqual(check(f, [E("core", "v0.200.0", SHA_A)]), [])  # 200 > 131

    def test_sha_not_on_main(self):
        for st in ("ahead", "diverged", None):
            f, es = world()
            r = f.repo("core")
            if st:
                r.compare[SHA_A] = st
            else:
                del r.compare[SHA_A]
            out = check(f, es)
            self.assertTrue(any("main" in m for m in out), (st, out))

    def test_identical_ok(self):
        f, es = world()
        f.repo("core").compare[SHA_A] = "identical"
        self.assertEqual(check(f, es), [])

    def test_tag_missing(self):
        f, es = world()
        del f.repo("core").refs["v0.132.0"]
        out = check(f, es)
        self.assertTrue(any("tag v0.132.0 does not exist" in m for m in out), out)

    def test_tag_lightweight_is_not_annotated(self):
        f, es = world()
        f.repo("core").refs["v0.132.0"] = {"type": "commit", "sha": SHA_A}
        out = check(f, es)
        self.assertTrue(any("not annotated" in m for m in out), out)
        self.assertFalse(any("does not exist" in m or "peels" in m for m in out), out)

    def test_tag_peels_to_another_sha(self):
        f, es = world()
        f.repo("core").add_tag("v0.132.0", SHA_C)  # tag moved / wrong commit
        out = check(f, es)
        self.assertTrue(any("peels to" in m and SHA_C in m for m in out), out)
        self.assertFalse(any("not annotated" in m or "does not exist" in m for m in out), out)

    def test_tag_object_unreadable_is_a_failure(self):
        f, es = world()
        f.repo("core").tag_objects.clear()
        self.assertTrue(any("peel" in m for m in check(f, es)))

    def test_tag_read_error_is_a_failure(self):
        f, es = world()
        f.fail.append(("GET", "git/ref/tags", 500))
        self.assertTrue(any("500" in m for m in check(f, es)))

    def test_release_with_tag_exists_including_draft_on_second_page(self):
        f, es = world()
        f.page_size = 2
        i = f.repo("core")
        for n in range(5):
            i.add_release(f"v0.0.{n}")
        i.add_release("v0.132.0", draft=True)
        self.assertTrue(any("release" in m and "exists" in m for m in check(f, es)))

    def test_published_release_of_the_listed_name_fails(self):
        f, es = world()
        f.repo("core").add_release("v0.132.0")
        out = check(f, es)
        self.assertTrue(any("release for v0.132.0 already exists" in m for m in out), out)

    def test_changelog_missing_or_wrong_heading(self):
        for text in ("## v0.132.01 — x\n", "### v0.132.0\n", " ## v0.132.0\n", "# v0.132.0\n",
                     "## v0.132.0x\n", "## v0.132.1 — x\n"):
            f, es = world()
            f.repo("core").changelog[SHA_A] = "# C\n\n" + text
            self.assertTrue(any("CHANGELOG" in m for m in check(f, es)), text)
        f, es = world()
        del f.repo("core").changelog[SHA_A]
        self.assertTrue(any("CHANGELOG" in m for m in check(f, es)))

    def test_changelog_heading_at_end_of_line_ok(self):
        f, es = world()
        f.repo("core").changelog[SHA_A] = "## v0.132.0"
        self.assertEqual(check(f, es), [])

    def test_unknown_repo(self):
        f, es = world()
        out = check(f, [E("tool", "v1.0.0", SHA_C)])
        self.assertTrue(any("tool" in m and "services.json" in m for m in out))

    def test_collects_all_failures(self):
        f, es = world()
        i, a = f.repo("core"), f.repo("gateway")
        i.compare[SHA_A] = "diverged"
        i.changelog[SHA_A] = "nothing"
        del i.refs["v0.132.0"]
        a.add_release("v0.38.0", draft=True)
        out = check(f, es)
        self.assertGreaterEqual(len(out), 4)
        self.assertTrue(any(m.startswith("core") for m in out))
        self.assertTrue(any(m.startswith("gateway") for m in out))

    def test_api_error_is_a_failure_not_a_pass(self):
        f, es = world()
        f.fail.append(("GET", "compare", 500))
        out = check(f, es)
        self.assertTrue(any("500" in m for m in out))


def make_drafts(f, es):
    return drafts.create_drafts(gh.Reader(f), gh.Writer(f), CFG, es)


def tag_writes(f):
    return [r for r in f.requests if r[0] != "GET"
            and r[1].split("?")[0].endswith(("/git/tags", "/git/refs"))]


class DraftsTests(unittest.TestCase):
    def test_happy_creates_only_draft_releases(self):
        f, es = world()
        out = make_drafts(f, es)
        self.assertEqual(set(out), {"core", "gateway"})
        kinds = [(m, p.split(OWNER + "/")[1]) for m, p, _ in f.writes()]
        self.assertEqual(kinds, [("POST", "core/releases"), ("POST", "gateway/releases")])
        self.assertEqual(tag_writes(f), [])
        rel = f.writes()[0][2]
        self.assertEqual((rel["tag_name"], rel["name"], rel["draft"],
                          rel["generate_release_notes"]), ("v0.132.0", "v0.132.0", True, True))
        self.assertEqual(out["core"], f.repo("core").releases[-1]["id"])

    def test_one_bad_repo_means_zero_writes(self):
        f, es = world()
        f.repo("gateway").compare[SHA_B] = "diverged"  # the SECOND repo is bad
        with self.assertRaises(drafts.DraftsError) as cm:
            make_drafts(f, es)
        self.assertEqual(f.writes(), [])
        self.assertEqual(cm.exception.created, {})
        self.assertTrue(cm.exception.failures)

    def test_missing_or_moved_tag_means_zero_writes(self):
        for how in ("missing", "lightweight", "moved"):
            f, es = world()
            a = f.repo("gateway")
            if how == "missing":
                del a.refs["v0.38.0"]
            elif how == "lightweight":
                a.refs["v0.38.0"] = {"type": "commit", "sha": SHA_B}
            else:
                a.add_tag("v0.38.0", SHA_C)
            with self.assertRaises(drafts.DraftsError) as cm:
                make_drafts(f, es)
            self.assertEqual(f.writes(), [], how)
            self.assertEqual(cm.exception.created, {}, how)
            self.assertTrue(any("v0.38.0" in m for m in cm.exception.failures), how)

    def test_red_ci_on_second_repo_means_zero_writes(self):
        f, es = world()
        f.repo("gateway").ci_runs.clear()  # gateway's commit has no CI result at all
        with self.assertRaises(drafts.DraftsError) as cm:
            make_drafts(f, es)
        self.assertEqual(f.writes(), [])
        self.assertTrue(any("ci.yml" in m for m in cm.exception.failures))

    def test_write_failure_midway_reports_what_exists(self):
        f, es = world()
        f.fail.append(("POST", "gateway/releases", 422))
        with self.assertRaises(drafts.DraftsError) as cm:
            make_drafts(f, es)
        self.assertIsInstance(cm.exception.created["core"], int)  # complete: release id
        self.assertNotIn("gateway", cm.exception.created)  # the rejected POST created nothing
        self.assertEqual(tag_writes(f), [])

    def test_lost_response_is_recorded_as_unknown(self):
        f, es = world()
        f.fail.append(("POST", "gateway/releases", 0))  # timeout: the POST may have landed
        with self.assertRaises(drafts.DraftsError) as cm:
            make_drafts(f, es)
        msg = cm.exception.created["gateway"]
        self.assertIn("unknown", msg)
        self.assertIn("response lost", msg)
        self.assertIsInstance(cm.exception.created["core"], int)

    def test_release_response_without_id_is_a_drafts_error(self):
        f, es = world()

        class NoId(gh.Writer):
            def create_draft(self, owner, repo, tag):
                super().create_draft(owner, repo, tag)
                return {"tag_name": tag}  # malformed: no id
        with self.assertRaises(drafts.DraftsError) as cm:
            drafts.create_drafts(gh.Reader(f), NoId(f), CFG, es)
        self.assertIn("core", cm.exception.created)
        self.assertIn("unknown", cm.exception.created["core"])  # the release may exist


if __name__ == "__main__":
    unittest.main()
