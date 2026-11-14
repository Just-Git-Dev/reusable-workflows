"""Tests for waiver.py: the `breaking-approved` label + ```breaking block (docs/release-flow.md
§ Contract checks, rules R1-R6)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import waiver  # noqa: E402

CONTRACTS = {("gateway", "core"), ("web", "gateway")}
F1 = "POST /login: body/extra_fields: property removed in candidate"
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
        got = waiver.parse_block(body(f"gateway -> core | {F1}", f"web -> gateway | {F2}"))
        self.assertEqual(got, [waiver.Entry("gateway", "core", F1), waiver.Entry("web", "gateway", F2)])
        self.assertEqual(got[0].pair, "gateway -> core")
        self.assertEqual(got[0].line, f"gateway -> core | {F1}")

    def test_crlf_and_blank_lines_and_outer_whitespace(self):
        got = waiver.parse_block(body("", f"  gateway -> core | {F1}  ", "").replace("\n", "\r\n"))
        self.assertEqual(got, [waiver.Entry("gateway", "core", F1)])

    def test_finding_may_contain_pipes_and_arrows(self):
        f = "GET /x: 200/a: type changed 'string' -> 'integer' | odd"
        self.assertEqual(waiver.parse_block(body(f"gateway -> core | {f}"))[0].finding, f)

    def test_malformed_lines_fail(self):
        for bad in ("gateway core | x", "gateway -> core", "gateway -> core |", "GATEWAY -> core | x",
                    "gateway->core | x", "-> core | x"):
            with self.assertRaises(waiver.WaiverError, msg=bad):
                waiver.parse_block(body(bad))

    def test_duplicate_line_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.parse_block(body(f"gateway -> core | {F1}", f"gateway -> core | {F1}"))
        self.assertIn("duplicate", str(cm.exception))

    def test_empty_block_fails(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.parse_block(body(""))

    def test_two_blocks_fail(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.parse_block(body(f"gateway -> core | {F1}") + body(f"web -> gateway | {F2}"))

    def test_unclosed_block_fails(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.parse_block(f"```breaking\ngateway -> core | {F1}\n")


class ShapeTests(unittest.TestCase):
    """R1 + R2."""

    def test_neither_label_nor_block_is_an_empty_list(self):
        self.assertEqual(waiver.check_shape(["other"], "notes", CONTRACTS), [])

    def test_label_and_block_together(self):
        got = waiver.check_shape([waiver.LABEL], body(f"gateway -> core | {F1}"), CONTRACTS)
        self.assertEqual(got, [waiver.Entry("gateway", "core", F1)])

    def test_label_without_block_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_shape([waiver.LABEL], "notes", CONTRACTS)
        self.assertIn("breaking", str(cm.exception))

    def test_block_without_label_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_shape(["bug"], body(f"gateway -> core | {F1}"), CONTRACTS)
        self.assertIn(waiver.LABEL, str(cm.exception))

    def test_pair_must_be_a_configured_contract(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_shape([waiver.LABEL], body(f"core -> gateway | {F1}"), CONTRACTS)
        self.assertIn("core -> gateway", str(cm.exception))


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
        entries = [waiver.Entry("gateway", "core", F1)]
        waiver.check_matrix(entries, [self.check("gateway", "core", "live"),
                                      self.check("gateway", "core", "candidate")])

    def test_pair_not_in_the_matrix_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_matrix([waiver.Entry("web", "gateway", F2)], [self.check("gateway", "core", "live")])
        self.assertIn("web -> gateway", str(cm.exception))

    def test_pair_with_only_a_candidate_consumer_check_fails(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.check_matrix([waiver.Entry("gateway", "core", F1)],
                                [self.check("gateway", "core", "candidate")])

    def test_empty_list_passes_any_matrix(self):
        waiver.check_matrix([], [])


class JsonTests(unittest.TestCase):
    def test_round_trip(self):
        entries = [waiver.Entry("gateway", "core", F1)]
        text = waiver.to_json(entries)
        self.assertEqual(json.loads(text), [{"consumer": "gateway", "provider": "core", "finding": F1}])
        self.assertEqual(waiver.from_json(text), entries)

    def test_empty_values(self):
        self.assertEqual(waiver.from_json(""), [])
        self.assertEqual(waiver.from_json("  "), [])
        self.assertEqual(waiver.from_json("[]"), [])

    def test_bad_json_fails(self):
        for bad in ("{", "{}", '[{"consumer": "gateway"}]', '["x"]', '[{"consumer": "gateway", '
                    '"provider": "core", "finding": ""}]'):
            with self.assertRaises(waiver.WaiverError, msg=bad):
                waiver.from_json(bad)


class SplitTests(unittest.TestCase):
    """R4's matching, per pair."""
    E = [waiver.Entry("gateway", "core", F1), waiver.Entry("web", "gateway", F2)]

    def test_listed_finding_is_waived(self):
        self.assertEqual(waiver.split([F1], "gateway -> core", self.E), ([F1], [], []))

    def test_unlisted_finding(self):
        self.assertEqual(waiver.split([F1, "X: y"], "gateway -> core", self.E), ([F1], ["X: y"], []))

    def test_listed_entry_that_did_not_occur_is_stale(self):
        self.assertEqual(waiver.split([], "gateway -> core", self.E), ([], [], [F1]))

    def test_another_pairs_entry_never_waives_here(self):
        self.assertEqual(waiver.split([F2], "gateway -> core", self.E), ([], [F2], [F1]))

    def test_a_finding_printed_twice_is_waived_once(self):
        self.assertEqual(waiver.split([F1, F1], "gateway -> core", self.E), ([F1], [], []))


class PairAndPasteTests(unittest.TestCase):
    def test_parse_pair(self):
        self.assertEqual(waiver.parse_pair("gateway -> core"), ("gateway", "core"))
        for bad in ("gateway->core", "gateway -> ", "gateway", "Gateway -> core"):
            with self.assertRaises(waiver.WaiverError, msg=bad):
                waiver.parse_pair(bad)

    def test_paste_block_round_trips_through_the_parser(self):
        text = waiver.paste_block("gateway -> core", [F1, F2, F1])
        self.assertTrue(text.startswith("```breaking\n"))
        self.assertEqual(waiver.parse_block(text), [waiver.Entry("gateway", "core", F1),
                                                    waiver.Entry("gateway", "core", F2)])


SERVICES = {"core", "gateway", "web"}
SDK = ("sdk-oldest", "core")


class ParseDeclaredTests(unittest.TestCase):
    """`waiver_pairs`: caller-declared pairs that are not `contracts` pairs."""

    def parse(self, text, services=SERVICES):
        return waiver.parse_declared(text, CONTRACTS, services)

    def test_comma_and_newline_lists_with_whitespace(self):
        want = frozenset({SDK, ("sdk-newest", "gateway")})
        self.assertEqual(self.parse("sdk-oldest -> core, sdk-newest -> gateway"), want)
        self.assertEqual(self.parse("  sdk-oldest -> core\n\n sdk-newest -> gateway \n"), want)

    def test_empty_is_the_empty_set(self):
        for text in ("", "  ", None, " , \n ,"):
            self.assertEqual(self.parse(text), frozenset(), repr(text))

    def test_malformed_item_fails(self):
        for bad in ("sdk-oldest->core", "sdk-oldest", "SDK -> core", "a -> b -> c"):
            with self.assertRaises(waiver.WaiverError, msg=bad):
                self.parse(bad)

    def test_duplicate_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            self.parse("sdk-oldest -> core, sdk-oldest -> core")
        self.assertIn("sdk-oldest -> core", str(cm.exception))

    def test_a_configured_contract_cannot_be_redeclared(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            self.parse("gateway -> core")
        self.assertIn("gateway -> core", str(cm.exception))

    def test_unknown_provider_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            self.parse("sdk-oldest -> backned")
        self.assertIn("backned", str(cm.exception))

    def test_consumer_side_is_a_free_name(self):
        self.assertEqual(self.parse("never-heard-of -> web"), frozenset({("never-heard-of", "web")}))


class DeclaredShapeTests(unittest.TestCase):
    """R1 + R2 with declared pairs."""
    DECLARED = frozenset({SDK})

    def test_a_declared_pair_passes_r2(self):
        got = waiver.check_shape([waiver.LABEL], body(f"sdk-oldest -> core | {F1}"), CONTRACTS,
                                 self.DECLARED)
        self.assertEqual(got, [waiver.Entry("sdk-oldest", "core", F1)])

    def test_contract_and_declared_pairs_mix(self):
        got = waiver.check_shape([waiver.LABEL],
                                 body(f"gateway -> core | {F1}", f"sdk-oldest -> core | {F2}"),
                                 CONTRACTS, self.DECLARED)
        self.assertEqual(len(got), 2)

    def test_an_undeclared_non_contract_pair_still_fails(self):
        with self.assertRaises(waiver.WaiverError) as cm:
            waiver.check_shape([waiver.LABEL], body(f"sdk-newest -> core | {F1}"), CONTRACTS,
                               self.DECLARED)
        self.assertIn("sdk-newest -> core", str(cm.exception))
        self.assertIn("waiver_pairs", str(cm.exception))

    def test_r1_is_unchanged_for_declared_pairs(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.check_shape(["bug"], body(f"sdk-oldest -> core | {F1}"), CONTRACTS,
                               self.DECLARED)
        with self.assertRaises(waiver.WaiverError):
            waiver.check_shape([waiver.LABEL], "notes", CONTRACTS, self.DECLARED)


class DeclaredMatrixTests(unittest.TestCase):
    """R3 with declared pairs."""

    def live(self, consumer, provider):
        return {"consumer": consumer, "consumer_ref": "v1.0.0", "provider": provider,
                "provider_ref": "a" * 40, "states": ["s"], "consumer_side": "live"}

    def test_a_declared_pair_passes_with_no_checks_entry(self):
        waiver.check_matrix([waiver.Entry("sdk-oldest", "core", F1)], [],
                            frozenset({SDK}))

    def test_a_contract_pair_still_needs_a_live_consumer_check(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.check_matrix([waiver.Entry("gateway", "core", F1)], [], frozenset({SDK}))
        waiver.check_matrix([waiver.Entry("gateway", "core", F1)],
                            [self.live("gateway", "core")], frozenset({SDK}))

    def test_an_undeclared_pair_is_still_refused(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.check_matrix([waiver.Entry("sdk-newest", "core", F1)], [], frozenset({SDK}))


class LabelsAtTests(unittest.TestCase):
    """Q3-B: the PR's labels at the moment it merged (the R5 rule for every label)."""
    MERGED = "2026-10-15T12:00:00Z"

    def ev(self, kind, at, name):
        return {"event": kind, "label": {"name": name}, "created_at": at}

    def test_labeled_before_merge_is_listed_sorted(self):
        evs = [self.ev("labeled", "2026-10-15T11:00:00Z", "skip-smoke"),
               self.ev("labeled", "2026-10-15T10:00:00Z", "breaking-approved")]
        self.assertEqual(waiver.labels_at(evs, self.MERGED), ["breaking-approved", "skip-smoke"])

    def test_labeled_at_or_after_merge_is_not_listed(self):
        evs = [self.ev("labeled", self.MERGED, "a"),
               self.ev("labeled", "2026-10-15T12:00:01Z", "b")]
        self.assertEqual(waiver.labels_at(evs, self.MERGED), [])

    def test_removed_before_merge_is_not_listed(self):
        evs = [self.ev("labeled", "2026-10-15T10:00:00Z", "a"),
               self.ev("unlabeled", "2026-10-15T11:00:00Z", "a")]
        self.assertEqual(waiver.labels_at(evs, self.MERGED), [])

    def test_re_added_and_order_independent(self):
        evs = [self.ev("labeled", "2026-10-15T11:30:00Z", "a"),
               self.ev("unlabeled", "2026-10-15T11:00:00Z", "a"),
               self.ev("labeled", "2026-10-15T10:00:00Z", "a")]
        self.assertEqual(waiver.labels_at(evs, self.MERGED), ["a"])

    def test_removed_after_merge_is_still_listed(self):
        evs = [self.ev("labeled", "2026-10-15T10:00:00Z", "a"),
               self.ev("unlabeled", "2026-10-15T13:00:00Z", "a")]
        self.assertEqual(waiver.labels_at(evs, self.MERGED), ["a"])

    def test_a_post_merge_event_listed_first_does_not_hide_earlier_ones(self):
        evs = [self.ev("labeled", "2026-10-15T13:00:00Z", "late"),
               self.ev("labeled", "2026-10-15T10:00:00Z", "a")]
        self.assertEqual(waiver.labels_at(evs, self.MERGED), ["a"])

    def test_other_events_are_ignored(self):
        evs = [{"event": "closed", "created_at": "2026-10-15T10:00:00Z"}]
        self.assertEqual(waiver.labels_at(evs, self.MERGED), [])

    def test_no_merge_time_fails(self):
        with self.assertRaises(waiver.WaiverError):
            waiver.labels_at([], None)


if __name__ == "__main__":
    unittest.main()
