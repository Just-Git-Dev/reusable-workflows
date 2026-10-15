"""spec_compat --pair / --consumer-side with RELEASE_BREAKING: the `breaking-approved` waiver
(docs/release-flow.md § Contract checks, R4 + R6; ruling 5: exit 2 / 0 operations never waived)."""

import copy
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import spec_compat  # noqa: E402
from test_spec_compat import PINNED  # noqa: E402

PAIR = "gateway -> core"
REMOVED = "POST /b: body/y: property removed in candidate"
GONE = "GET /a: operation missing in candidate"


def cand_without_y():
    c = copy.deepcopy(PINNED)
    del c["paths"]["/b"]["post"]["requestBody"]["content"]["application/json"]["schema"][
        "properties"]["y"]
    return c


def cand_without_y_and_a():
    c = cand_without_y()
    del c["paths"]["/a"]
    return c


def listed(*findings, consumer="gateway", provider="core"):
    return json.dumps([{"consumer": consumer, "provider": provider, "finding": f}
                       for f in findings])


class Run:
    def __init__(self, pinned, cand, *extra, breaking=None, summary=True, raw_pinned=None):
        with tempfile.TemporaryDirectory() as d:
            a, b, s = Path(d, "a.json"), Path(d, "b.json"), Path(d, "summary.md")
            a.write_text(raw_pinned if raw_pinned is not None else json.dumps(pinned))
            b.write_text(json.dumps(cand))
            env = {}
            if breaking is not None:
                env["RELEASE_BREAKING"] = breaking
            if summary:
                env["GITHUB_STEP_SUMMARY"] = str(s)
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.rc = spec_compat.main([str(a), str(b), *extra], env=env)
            self.out = out.getvalue() + err.getvalue()
            self.summary = s.read_text() if s.exists() else ""


LIVE = ("--pair", PAIR, "--consumer-side", "live")
CANDIDATE = ("--pair", PAIR, "--consumer-side", "candidate")


class WaiverTests(unittest.TestCase):
    def test_listed_finding_is_waived_and_summarised(self):
        r = Run(PINNED, cand_without_y(), *LIVE, breaking=listed(REMOVED))
        self.assertEqual(r.rc, 0, r.out)
        self.assertIn(f"WAIVED {REMOVED}", r.out)
        self.assertNotIn("INCOMPATIBLE", r.out)
        self.assertIn(REMOVED, r.summary)
        self.assertIn("breaking-approved", r.summary)

    def test_unlisted_finding_fails(self):
        r = Run(PINNED, cand_without_y_and_a(), *LIVE, breaking=listed(REMOVED))
        self.assertEqual(r.rc, 1, r.out)
        self.assertIn(f"WAIVED {REMOVED}", r.out)
        self.assertIn(f"INCOMPATIBLE {GONE}", r.out)

    def test_listed_entry_that_did_not_occur_fails(self):
        r = Run(PINNED, cand_without_y(), *LIVE, breaking=listed(REMOVED, GONE))
        self.assertEqual(r.rc, 1, r.out)
        self.assertIn("STALE", r.out)
        self.assertIn(GONE, r.out)

    def test_a_clean_candidate_with_a_listed_entry_fails_stale(self):
        r = Run(PINNED, PINNED, *LIVE, breaking=listed(REMOVED))
        self.assertEqual(r.rc, 1, r.out)
        self.assertIn("STALE", r.out)

    def test_another_pairs_entries_neither_waive_nor_go_stale_here(self):
        r = Run(PINNED, cand_without_y(), *LIVE, breaking=listed(REMOVED, consumer="web",
                                                                  provider="gateway"))
        self.assertEqual(r.rc, 1, r.out)
        self.assertIn(f"INCOMPATIBLE {REMOVED}", r.out)
        self.assertNotIn("STALE", r.out)
        r = Run(PINNED, PINNED, *LIVE, breaking=listed(REMOVED, consumer="web", provider="gateway"))
        self.assertEqual(r.rc, 0, r.out)

    def test_candidate_consumer_side_waives_nothing_and_has_no_stale_rule(self):
        r = Run(PINNED, cand_without_y(), *CANDIDATE, breaking=listed(REMOVED))
        self.assertEqual(r.rc, 1, r.out)
        self.assertIn(f"INCOMPATIBLE {REMOVED}", r.out)
        self.assertNotIn("WAIVED", r.out)
        r = Run(PINNED, PINNED, *CANDIDATE, breaking=listed(REMOVED))
        self.assertEqual(r.rc, 0, r.out)

    def test_zero_operations_fails_whatever_is_listed(self):
        r = Run({"openapi": "3.0.0", "paths": {}}, PINNED, *LIVE, breaking=listed(REMOVED))
        self.assertEqual(r.rc, 1, r.out)
        self.assertIn("examined 0 operations", r.out)
        self.assertNotIn("WAIVED", r.out)

    def test_unreadable_baseline_is_exit_2_whatever_is_listed(self):
        r = Run(None, PINNED, *LIVE, breaking=listed(REMOVED), raw_pinned="{not json")
        self.assertEqual(r.rc, 2, r.out)

    def test_bad_release_breaking_is_exit_2(self):
        r = Run(PINNED, cand_without_y(), *LIVE, breaking="{nope")
        self.assertEqual(r.rc, 2, r.out)

    def test_release_breaking_without_pair_is_exit_2(self):
        r = Run(PINNED, cand_without_y(), breaking=listed(REMOVED))
        self.assertEqual(r.rc, 2, r.out)

    def test_empty_release_breaking_behaves_as_today(self):
        for empty in ("", "[]"):
            r = Run(PINNED, cand_without_y(), breaking=empty)
            self.assertEqual(r.rc, 1, r.out)
            self.assertIn(f"INCOMPATIBLE {REMOVED}", r.out)
            r = Run(PINNED, PINNED, *LIVE, breaking=empty)
            self.assertEqual(r.rc, 0, r.out)

    def test_pair_needs_a_valid_consumer_side_and_a_valid_pair(self):
        for extra in (("--pair", PAIR), ("--pair", PAIR, "--consumer-side", "both"),
                      ("--pair", "gateway->core", "--consumer-side", "live"),
                      ("--consumer-side", "live")):
            r = Run(PINNED, PINNED, *extra)
            self.assertEqual(r.rc, 2, f"{extra}: {r.out}")


class UnreadableYamlTests(unittest.TestCase):
    """A malformed YAML spec is exit 2 (unreadable), never a traceback's exit 1 that a caller
    would read as 'incompatible' (found 2026-10-15 while building the waiver)."""

    def test_ops_subset_malformed_yaml_is_exit_2(self):
        import ops_subset
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d, "a.yaml"), Path(d, "b.json")
            a.write_text("{not json")
            b.write_text(json.dumps(PINNED))
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(ops_subset.main([str(a), str(b)]), 2)

    def test_spec_compat_malformed_yaml_without_waiver_is_exit_2(self):
        self.assertEqual(Run(None, PINNED, raw_pinned="a: [b").rc, 2)


class PasteBlockTests(unittest.TestCase):
    """R6: on failure, the author gets the exact block to paste."""

    def test_failure_prints_a_paste_ready_block_for_the_pair(self):
        r = Run(PINNED, cand_without_y_and_a(), *LIVE)
        self.assertEqual(r.rc, 1, r.out)
        self.assertIn("```breaking\n", r.out)
        self.assertIn(f"{PAIR} | {REMOVED}\n", r.out)
        self.assertIn(f"{PAIR} | {GONE}\n", r.out)

    def test_without_pair_the_block_uses_a_placeholder(self):
        r = Run(PINNED, cand_without_y())
        self.assertEqual(r.rc, 1, r.out)
        self.assertIn(f"<consumer> -> <provider> | {REMOVED}", r.out)

    def test_candidate_side_failure_says_it_cannot_be_waived(self):
        r = Run(PINNED, cand_without_y(), *CANDIDATE)
        self.assertEqual(r.rc, 1, r.out)
        self.assertNotIn("```breaking", r.out)
        self.assertIn("cannot be waived", r.out)


if __name__ == "__main__":
    unittest.main()
