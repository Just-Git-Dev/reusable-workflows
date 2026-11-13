"""Workflow shape of the `breaking-approved` waiver (docs/release-flow.md § Contract checks):
release-pr-check checks the shape from the event payload with no token; plan reads the PR with
the GITHUB_TOKEN (R1, R2, R5); resolve checks every approved pair against `checks` (R3) and
exposes the list as the `breaking` output."""
import unittest

import wf

DOC = wf.ROOT / "docs" / "release-flow.md"


class PrCheckTests(unittest.TestCase):
    def setUp(self):
        self.job = wf.jobs(wf.load("release-pr-check.yml"))["release-pr"]

    def shape_step(self):
        st = [s for s in self.job["steps"] if "release-flow breaking-shape" in s.get("run", "")]
        self.assertEqual(len(st), 1)
        return st[0]

    def test_shape_reads_the_event_payload_and_holds_no_token(self):
        st = self.shape_step()
        self.assertIn('--event-file "$GITHUB_EVENT_PATH"', st["run"])
        self.assertIn('--config "$CONFIG"', st["run"])
        for v in (st.get("env") or {}).values():
            self.assertNotIn("token", str(v).lower())
            self.assertNotIn("secrets.", str(v))
        self.assertIn("GITHUB_STEP_SUMMARY", st["run"])

    def test_waiver_pairs_input_reaches_the_cli_by_env(self):
        inp = wf.on_block(wf.load("release-pr-check.yml"))["workflow_call"]["inputs"]["waiver_pairs"]
        self.assertEqual((inp["type"], inp["required"], inp["default"]), ("string", False, ""))
        st = self.shape_step()
        self.assertEqual(st["env"]["WAIVER_PAIRS"], "${{ inputs.waiver_pairs }}")
        self.assertIn('--waiver-pairs "$WAIVER_PAIRS"', st["run"])
        self.assertNotIn("inputs.waiver_pairs", st["run"])

    def test_shape_runs_after_the_cli_is_pinned(self):
        steps = self.job["steps"]
        pin = next(i for i, s in enumerate(steps) if "RELEASE_FLOW_TREE" in s.get("run", ""))
        self.assertGreater(steps.index(self.shape_step()), pin)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.w = wf.load("release-plan.yml")
        self.jobs = wf.jobs(self.w)

    def test_plan_reads_the_approval_with_the_github_token(self):
        _, st = wf.step_by_id(self.jobs["plan"], "brk")
        env = st["env"]
        self.assertEqual(env["RELEASE_FLOW_READ_TOKEN"], "${{ github.token }}")
        self.assertEqual(env["PR"], "${{ steps.m.outputs.pr }}")
        self.assertEqual(env["MANIFEST_REF"], "${{ inputs.manifest-ref }}")
        self.assertEqual(env["REHEARSAL"], "${{ inputs.rehearsal }}")
        run = st["run"]
        self.assertIn('release-flow breaking-approval --pr "$PR"', run)
        self.assertIn('release-flow breaking-approval --head-branch "$MANIFEST_REF"', run)
        self.assertIn('"$GITHUB_OUTPUT"', run)
        self.assertIn('"$GITHUB_STEP_SUMMARY"', run)
        self.assertEqual(self.jobs["plan"]["outputs"]["breaking"],
                         "${{ steps.brk.outputs.breaking }}")

    def test_waiver_pairs_input_and_labels_output(self):
        inp = wf.on_block(self.w)["workflow_call"]["inputs"]["waiver_pairs"]
        self.assertEqual((inp["type"], inp["required"], inp["default"]), ("string", False, ""))
        _, st = wf.step_by_id(self.jobs["plan"], "brk")
        self.assertEqual(st["env"]["WAIVER_PAIRS"], "${{ inputs.waiver_pairs }}")
        self.assertIn('--waiver-pairs "$WAIVER_PAIRS"', st["run"])
        self.assertIn('--labels-out "$RUNNER_TEMP/labels.json"', st["run"])
        self.assertIn("labels=", st["run"])
        self.assertIn("labels=[]", st["run"])   # a rehearsal without manifest-ref has no PR
        self.assertNotIn("inputs.waiver_pairs", st["run"])
        self.assertEqual(self.jobs["plan"]["outputs"]["labels"], "${{ steps.brk.outputs.labels }}")
        outs = wf.on_block(self.w)["workflow_call"]["outputs"]
        self.assertEqual(outs["labels"]["value"], "${{ jobs.plan.outputs.labels }}")

    def test_resolve_passes_the_pairs_and_the_config_to_the_matrix_check(self):
        _, st = wf.step_by_id(self.jobs["resolve"], "brk")
        self.assertEqual(st["env"]["WAIVER_PAIRS"], "${{ inputs.waiver_pairs }}")
        self.assertIn("CONFIG", st["env"])
        self.assertIn('--waiver-pairs "$WAIVER_PAIRS"', st["run"])
        self.assertIn('--config "$CONFIG"', st["run"])
        self.assertNotIn("inputs.waiver_pairs", st["run"])

    def test_approval_runs_after_the_guard(self):
        m, _ = wf.step_by_id(self.jobs["plan"], "m")
        b, _ = wf.step_by_id(self.jobs["plan"], "brk")
        self.assertGreater(b, m)

    def test_resolve_checks_the_pairs_against_the_matrix_and_outputs_the_list(self):
        res = self.jobs["resolve"]
        _, st = wf.step_by_id(res, "brk")
        self.assertEqual(st["env"]["BREAKING"], "${{ needs.plan.outputs.breaking }}")
        self.assertEqual(st["env"]["CHECKS"], "${{ steps.r.outputs.checks }}")
        self.assertIn('release-flow breaking-matrix --breaking "$BREAKING" --checks "$CHECKS"',
                      st["run"])
        self.assertEqual(res["outputs"]["breaking"], "${{ steps.brk.outputs.breaking }}")
        r, _ = wf.step_by_id(res, "r")
        b, _ = wf.step_by_id(res, "brk")
        self.assertGreater(b, r)

    def test_workflow_output(self):
        outs = wf.on_block(self.w)["workflow_call"]["outputs"]
        self.assertEqual(outs["breaking"]["value"], "${{ jobs.resolve.outputs.breaking }}")


class CallerExampleTests(unittest.TestCase):
    def test_doc_caller_example_wires_the_waiver(self):
        text = DOC.read_text()
        self.assertIn("types: [opened, synchronize, reopened, edited, labeled, unlabeled]", text)
        self.assertIn("RELEASE_BREAKING: ${{ needs.plan.outputs.breaking }}", text)
        self.assertIn('--pair "$PAIR" --consumer-side "$SIDE"', text)
        self.assertIn("SIDE: ${{ matrix.consumer_side }}", text)
        self.assertIn("## Contract checks", text)

    def test_doc_caller_example_declares_a_pair_on_both_calls(self):
        text = DOC.read_text()
        self.assertEqual(text.count("waiver_pairs: sdk-oldest -> backend"), 2)
        start = text.index("  sdk-compat:")
        stage = text[start:text.index("  drafts:", start)]
        self.assertIn("--consumer-side live", stage)
        self.assertIn("--pair", stage)
        self.assertIn("RELEASE_BREAKING: ${{ needs.plan.outputs.breaking }}", stage)
        self.assertNotIn("if:", stage)   # verdict.py: a needs job that is skipped fails drafts
        self.assertIn("needs: [plan, contracts, sdk-compat]", text)
        self.assertIn("fromJSON(needs.plan.outputs.labels)", text)


if __name__ == "__main__":
    unittest.main()
