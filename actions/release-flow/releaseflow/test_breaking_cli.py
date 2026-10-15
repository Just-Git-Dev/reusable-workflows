"""The `breaking-approved` waiver through the CLI: breaking-shape (release-pr-check, no token),
breaking-approval (plan: real release and rehearsal), breaking-matrix (resolve), and the merge
guard judging the NEWEST release-pr run (docs/release-flow.md § Contract checks)."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gh  # noqa: E402
import guard  # noqa: E402
import release_flow  # noqa: E402
import waiver  # noqa: E402
from fake_github import CFG_DICT, FakeGitHub, SHA_A, SHA_B  # noqa: E402

TMP_ROOT = HERE.parents[2] / ".scratch" / "test-tmp"
F1 = "POST /login: body/extra_fields: property removed in candidate"
BLOCK = f"Notes.\n\n```breaking\ngateway -> core | {F1}\n```\n"
ENV = {"RELEASE_FLOW_READ_TOKEN": "r", "GITHUB_REPOSITORY": "consumer-a-org/project"}
MERGED = "2026-10-15T12:00:00Z"


def tmpdir():
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TMP_ROOT)


def call(argv, env=None, deps=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = release_flow.main(argv, env=env or {}, deps=deps or {})
    return rc, out.getvalue(), err.getvalue()


def write(d, name, obj):
    p = Path(d) / name
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))
    return str(p)


def labels(*names):
    return [{"name": n} for n in names]


class ShapeCommandTests(unittest.TestCase):
    def shape(self, event):
        with tmpdir() as d:
            return call(["breaking-shape", "--event-file", write(d, "event.json", event),
                         "--config", write(d, "c.json", CFG_DICT)])

    def ev(self, body, *names):
        return {"pull_request": {"number": 7, "body": body, "labels": labels(*names)}}

    def test_label_and_block_print_the_list(self):
        rc, out, err = self.shape(self.ev(BLOCK, waiver.LABEL))
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), [{"consumer": "gateway", "provider": "core", "finding": F1}])

    def test_neither_prints_an_empty_list(self):
        rc, out, err = self.shape(self.ev(None))
        self.assertEqual((rc, json.loads(out)), (0, []), err)

    def test_r1_and_r2_failures_are_exit_1(self):
        for ev in (self.ev(BLOCK), self.ev("notes", waiver.LABEL),
                   self.ev(BLOCK.replace("gateway -> core", "site -> gateway"), waiver.LABEL)):
            rc, _, err = self.shape(ev)
            self.assertEqual(rc, 1, ev)
            self.assertIn("FAIL", err)

    def test_not_a_pull_request_event_is_exit_2(self):
        rc, _, _ = self.shape({"push": {}})
        self.assertEqual(rc, 2)

    def test_unreadable_event_file_is_exit_2(self):
        with tmpdir() as d:
            rc, _, _ = call(["breaking-shape", "--event-file", str(Path(d) / "absent.json"),
                             "--config", write(d, "c.json", CFG_DICT)])
        self.assertEqual(rc, 2)


class ApprovalCommandTests(unittest.TestCase):
    def world(self, body=BLOCK, names=(waiver.LABEL,), events=None, merged_at=MERGED,
              state="closed"):
        f = FakeGitHub()
        f.repos["project"] = p = f.repo("project")
        p.pr_objects[7] = {"number": 7, "state": state, "merged_at": merged_at, "body": body,
                           "labels": labels(*names), "head": {"ref": "release/x", "sha": SHA_B}}
        p.issue_events[7] = events if events is not None else [
            {"event": "labeled", "label": {"name": waiver.LABEL},
             "created_at": "2026-10-15T11:00:00Z"}]
        return f, p

    def approve(self, f, *args):
        with tmpdir() as d:
            return call(["breaking-approval", *args, "--config", write(d, "c.json", CFG_DICT)],
                        ENV, {"transport": f})

    def test_real_release_label_before_merge(self):
        f, _ = self.world()
        rc, out, err = self.approve(f, "--pr", "7")
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out)[0]["finding"], F1)
        self.assertFalse(f.writes())

    def test_real_release_label_added_after_merge_fails(self):
        f, _ = self.world(events=[{"event": "labeled", "label": {"name": waiver.LABEL},
                                   "created_at": "2026-10-15T12:05:00Z"}])
        rc, _, err = self.approve(f, "--pr", "7")
        self.assertEqual(rc, 1)
        self.assertIn("merge", err)

    def test_real_release_without_label_or_block_is_empty(self):
        f, _ = self.world(body="notes", names=(), events=[])
        rc, out, err = self.approve(f, "--pr", "7")
        self.assertEqual((rc, json.loads(out)), (0, []), err)

    def test_real_release_block_without_label_fails(self):
        f, _ = self.world(names=())
        self.assertEqual(self.approve(f, "--pr", "7")[0], 1)

    def test_real_release_pr_must_be_merged(self):
        f, _ = self.world(merged_at=None)
        self.assertEqual(self.approve(f, "--pr", "7")[0], 1)

    def test_rehearsal_reads_the_open_pr_of_the_branch(self):
        f, _ = self.world(merged_at=None, state="open", events=[])
        rc, out, err = self.approve(f, "--head-branch", "release/x")
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out)[0]["finding"], F1)
        self.assertTrue(any("head=consumer-a-org:release/x" in r[1] for r in f.requests))

    def test_rehearsal_with_no_or_two_open_prs_fails(self):
        f, _ = self.world(state="closed")
        self.assertEqual(self.approve(f, "--head-branch", "release/x")[0], 1)
        f, p = self.world(merged_at=None, state="open")
        p.pr_objects[8] = dict(p.pr_objects[7], number=8)
        self.assertEqual(self.approve(f, "--head-branch", "release/x")[0], 1)

    def test_exactly_one_of_pr_or_head_branch(self):
        f, _ = self.world()
        self.assertEqual(self.approve(f)[0], 2)
        self.assertEqual(self.approve(f, "--pr", "7", "--head-branch", "x")[0], 2)

    def test_token_is_required(self):
        f, _ = self.world()
        with tmpdir() as d:
            rc, _, _ = call(["breaking-approval", "--pr", "7", "--config",
                             write(d, "c.json", CFG_DICT)],
                            {"GITHUB_REPOSITORY": "consumer-a-org/project"}, {"transport": f})
        self.assertEqual(rc, 2)


class MatrixCommandTests(unittest.TestCase):
    LIVE = {"consumer": "gateway", "consumer_ref": "v1.0.0", "provider": "core",
            "provider_ref": "a" * 40, "states": ["s"], "consumer_side": "live"}
    ENTRY = [{"consumer": "gateway", "provider": "core", "finding": F1}]

    def test_ok_prints_the_list(self):
        rc, out, err = call(["breaking-matrix", "--breaking", json.dumps(self.ENTRY),
                             "--checks", json.dumps([self.LIVE])])
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), self.ENTRY)

    def test_no_live_check_for_the_pair_is_exit_1(self):
        cand = dict(self.LIVE, consumer_side="candidate")
        rc, _, err = call(["breaking-matrix", "--breaking", json.dumps(self.ENTRY),
                           "--checks", json.dumps([cand])])
        self.assertEqual(rc, 1, err)

    def test_empty_breaking_with_empty_checks(self):
        rc, out, _ = call(["breaking-matrix", "--breaking", "[]", "--checks", "[]"])
        self.assertEqual((rc, json.loads(out)), (0, []))

    def test_bad_json_is_exit_2(self):
        self.assertEqual(call(["breaking-matrix", "--breaking", "{", "--checks", "[]"])[0], 2)
        self.assertEqual(call(["breaking-matrix", "--breaking", "[]", "--checks", "{"])[0], 2)


class NewestRunMergeGuardTests(unittest.TestCase):
    ROOT = "consumer-a-org/project"

    def world(self, runs):
        f = FakeGitHub()
        f.repos["project"] = p = f.repo("project")
        p.pulls[SHA_A] = [{"number": 7, "merged_at": MERGED, "base": {"ref": "main"},
                           "head": {"sha": SHA_B}}]
        p.check_runs[SHA_B] = runs
        p.suite_runs = {55: [{"path": ".github/workflows/release-pr.yml"}],
                        56: [{"path": ".github/workflows/release-pr.yml"}]}
        return f

    def run_(self, id_, conclusion, suite=55, status="completed"):
        return {"id": id_, "name": "release-pr", "status": status, "conclusion": conclusion,
                "app": {"slug": "github-actions"}, "check_suite": {"id": suite}}

    def merge(self, f):
        return guard.check_merge(gh.Reader(f), self.ROOT, SHA_A, "release-pr")

    def test_an_older_red_run_does_not_block_a_newer_green_one(self):
        f = self.world([self.run_(10, "failure"), self.run_(11, "success", suite=56)])
        self.assertEqual(self.merge(f), 7)

    def test_a_newer_red_run_blocks(self):
        f = self.world([self.run_(10, "success"), self.run_(11, "failure", suite=56)])
        with self.assertRaises(guard.GuardError):
            self.merge(f)

    def test_a_newer_unfinished_run_blocks(self):
        f = self.world([self.run_(10, "success"),
                        self.run_(11, None, suite=56, status="in_progress")])
        with self.assertRaises(guard.GuardError):
            self.merge(f)

    def test_provenance_is_still_checked_on_every_run(self):
        f = self.world([self.run_(10, "failure"), self.run_(11, "success", suite=56)])
        f.repo("project").suite_runs[55] = [{"path": ".github/workflows/evil.yml"}]
        with self.assertRaises(guard.GuardError):
            self.merge(f)
        f = self.world([dict(self.run_(10, "failure"), app={"slug": "evil"}),
                        self.run_(11, "success", suite=56)])
        with self.assertRaises(guard.GuardError):
            self.merge(f)

    def test_without_ids_every_run_must_succeed(self):
        a, b = self.run_(10, "failure"), self.run_(11, "success", suite=56)
        del a["id"]
        f = self.world([a, b])
        with self.assertRaises(guard.GuardError):
            self.merge(f)


if __name__ == "__main__":
    unittest.main()
