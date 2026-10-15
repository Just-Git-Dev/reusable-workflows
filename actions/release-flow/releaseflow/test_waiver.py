"""Tests for waiver.py: the `breaking-approved` label + ```breaking block (docs/release-flow.md
§ Contract checks, rules R1-R6)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import waiver  # noqa: E402

CONTRACTS = {("api", "issuer"), ("ui", "api")}
F1 = "POST /login: body/custom_claims: property removed in candidate"
F2 = "GET /me: 200/role: enum narrowed"


def body(*lines, fence="```breaking", text_before="Release notes.\n\n"):
    return text_before + fence + "\n" + "\n".join(lines) + "\n```\n"


class ParseTests(unittest.TestCase):
    def test_no_block_is_none(self):
        self.assertIsNone(waiver.parse_block("just notes"))
        self.assertIsNone(waiver.parse_block(""))
        self.assertIsNone(waiver.parse_block(None))
        self.assertIsNone(waiver.parse_block("```yaml\na: b\n```"))

    def test_one_line_per_break_pair_first(self):
        got = waiver.parse_block(body(f"api -> issuer | {F1}", f"ui -> api | {F2}"))
        self.assertEqual(got, [waiver.Entry("api", "issuer", F1), waiver.Entry("ui", "api", F2)])
        self.assertEqual(got[0].pair, "api -> issuer")
        self.assertEqual(got[0].line, f"api -> issuer | {F1}")

    def test_crlf_and_blank_lines_and_outer_whitespace(self):
        got = waiver.parse_block(body("", f"  api -> issuer | {F1}  ", "").replace("\n", "\r\n"))
        self.assertEqual(got, [waiver.Entry("api", "issuer", F1)])

    def test_finding_may_contain_pipes_and_arrows(self):
        f = "GET /x: 200/a: type changed 'string' -> 'integer' | odd"
        self.assertEqual(waiver.parse_block(body(f"api -> issuer | {f}"))[0].finding, f)

    def test_malformed_lines_fail(self):
        for bad in ("api issuer | x", "api -> issuer", "api -> issuer |", "API -> issuer | x",
                    "api->issuer | x", "-> issuer | x"):
            with self.assertRaises(waiver.WaiverError, msg=bad):
                waiver.parse_block(body(bad))

    def test_duplicate_line_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.parse_block(body(f"api -> issuer | {F1}", f"api -> issuer | {F1}"))
        self.assertIn("duplicate", str(cm.exception))

    def test_empty_block_fails(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.parse_block(body(""))

    def test_two_blocks_fail(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.parse_block(body(f"api -> issuer | {F1}") + body(f"ui -> api | {F2}"))

    def test_unclosed_block_fails(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.parse_block(f"```breaking\napi -> issuer | {F1}\n")


class ShapeTests(unittest.TestCase):
    """R1 + R2."""

    def test_neither_label_nor_block_is_an_empty_list(self):
        self.assertEqual(waiver.check_shape(["other"], "notes", CONTRACTS), [])

    def test_label_and_block_together(self):
        got = waiver.check_shape([waiver.LABEL], body(f"api -> issuer | {F1}"), CONTRACTS)
        self.assertEqual(got, [waiver.Entry("api", "issuer", F1)])

    def test_label_without_block_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_shape([waiver.LABEL], "notes", CONTRACTS)
        self.assertIn("breaking", str(cm.exception))

    def test_block_without_label_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_shape(["bug"], body(f"api -> issuer | {F1}"), CONTRACTS)
        self.assertIn(waiver.LABEL, str(cm.exception))

    def test_pair_must_be_a_configured_contract(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_shape([waiver.LABEL], body(f"issuer -> api | {F1}"), CONTRACTS)
        self.assertIn("issuer -> api", str(cm.exception))


class LabelBeforeMergeTests(unittest.TestCase):
    """R5."""
    MERGED = "2026-10-15T12:00:00Z"

    def ev(self, kind, at, name=waiver.LABEL):
        return {"event": kind, "label": {"name": name}, "created_at": at}

    def test_labeled_before_merge(self):
        self.assertTrue(waiver.label_before_merge(
            [self.ev("labeled", "2026-10-15T11:00:00Z")], self.MERGED))

    def test_labeled_after_merge_does_not_count(self):
        self.assertFalse(waiver.label_before_merge(
            [self.ev("labeled", "2026-10-15T12:00:01Z")], self.MERGED))

    def test_labeled_at_the_merge_second_does_not_count(self):
        self.assertFalse(waiver.label_before_merge(
            [self.ev("labeled", self.MERGED)], self.MERGED))

    def test_removed_before_merge(self):
        self.assertFalse(waiver.label_before_merge(
            [self.ev("labeled", "2026-10-15T10:00:00Z"),
             self.ev("unlabeled", "2026-10-15T11:00:00Z")], self.MERGED))

    def test_re_added_before_merge_and_order_independent(self):
        evs = [self.ev("labeled", "2026-10-15T11:30:00Z"),
               self.ev("unlabeled", "2026-10-15T11:00:00Z"),
               self.ev("labeled", "2026-10-15T10:00:00Z")]
        self.assertTrue(waiver.label_before_merge(evs, self.MERGED))

    def test_other_labels_and_events_are_ignored(self):
        evs = [self.ev("labeled", "2026-10-15T10:00:00Z", name="bug"),
               {"event": "closed", "created_at": "2026-10-15T10:00:00Z"}]
        self.assertFalse(waiver.label_before_merge(evs, self.MERGED))

    def test_no_merge_time_fails(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.label_before_merge([self.ev("labeled", "2026-10-15T10:00:00Z")], None)


class MatrixTests(unittest.TestCase):
    """R3."""

    def check(self, consumer, provider, side):
        return {"consumer": consumer, "consumer_ref": "v1.0.0", "provider": provider,
                "provider_ref": "a" * 40, "states": ["s"], "consumer_side": side}

    def test_pair_with_a_live_consumer_check_passes(self):
        entries = [waiver.Entry("api", "issuer", F1)]
        waiver.check_matrix(entries, [self.check("api", "issuer", "live"),
                                      self.check("api", "issuer", "candidate")])

    def test_pair_not_in_the_matrix_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_matrix([waiver.Entry("ui", "api", F2)], [self.check("api", "issuer", "live")])
        self.assertIn("ui -> api", str(cm.exception))

    def test_pair_with_only_a_candidate_consumer_check_fails(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.check_matrix([waiver.Entry("api", "issuer", F1)],
                                [self.check("api", "issuer", "candidate")])

    def test_empty_list_passes_any_matrix(self):
        waiver.check_matrix([], [])


class JsonTests(unittest.TestCase):
    def test_round_trip(self):
        entries = [waiver.Entry("api", "issuer", F1)]
        text = waiver.to_json(entries)
        self.assertEqual(json.loads(text), [{"consumer": "api", "provider": "issuer", "finding": F1}])
        self.assertEqual(waiver.from_json(text), entries)

    def test_empty_values(self):
        self.assertEqual(waiver.from_json(""), [])
        self.assertEqual(waiver.from_json("  "), [])
        self.assertEqual(waiver.from_json("[]"), [])

    def test_bad_json_fails(self):
        for bad in ("{", "{}", '[{"consumer": "api"}]', '["x"]', '[{"consumer": "api", '
                    '"provider": "issuer", "finding": ""}]'):
            with self.assertRaises(waiver.WaiverError, msg=bad):
                waiver.from_json(bad)


class SplitTests(unittest.TestCase):
    """R4's matching, per pair."""
    E = [waiver.Entry("api", "issuer", F1), waiver.Entry("ui", "api", F2)]

    def test_listed_finding_is_waived(self):
        self.assertEqual(waiver.split([F1], "api -> issuer", self.E), ([F1], [], []))

    def test_unlisted_finding(self):
        self.assertEqual(waiver.split([F1, "X: y"], "api -> issuer", self.E), ([F1], ["X: y"], []))

    def test_listed_entry_that_did_not_occur_is_stale(self):
        self.assertEqual(waiver.split([], "api -> issuer", self.E), ([], [], [F1]))

    def test_another_pairs_entry_never_waives_here(self):
        self.assertEqual(waiver.split([F2], "api -> issuer", self.E), ([], [F2], [F1]))

    def test_a_finding_printed_twice_is_waived_once(self):
        self.assertEqual(waiver.split([F1, F1], "api -> issuer", self.E), ([F1], [], []))


class PairAndPasteTests(unittest.TestCase):
    def test_parse_pair(self):
        self.assertEqual(waiver.parse_pair("api -> issuer"), ("api", "issuer"))
        for bad in ("api->issuer", "api -> ", "api", "Api -> issuer"):
            with self.assertRaises(waiver.WaiverError, msg=bad):
                waiver.parse_pair(bad)

    def test_paste_block_round_trips_through_the_parser(self):
        text = waiver.paste_block("api -> issuer", [F1, F2, F1])
        self.assertTrue(text.startswith("```breaking\n"))
        self.assertEqual(waiver.parse_block(text), [waiver.Entry("api", "issuer", F1),
                                                    waiver.Entry("api", "issuer", F2)])


if __name__ == "__main__":
    unittest.main()
