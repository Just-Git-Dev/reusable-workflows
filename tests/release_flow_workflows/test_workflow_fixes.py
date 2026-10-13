"""Review fixes to the release-flow workflows: each test RUNS or pins what the finding was about.

  1. every `release-flow config-check` in the four workflows is executed against the CLI;
  2. the publish report's bash is executed (a slot that never ran is not a publish);
  3. the manifest is staged by plan as an artifact and every later reader checks its sha256;
  4. the self-test cannot import code from the caller's checkout;
  5. no write-mint `if:` fails open on `!= 'true'`.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import wf

CLI_DIR = wf.ROOT / "actions" / "release-flow" / "releaseflow"
STAGED = "release-manifest/manifest.yaml"


def run_steps():
    return [(n, jn, job, st) for n, jn, job, st in wf.all_steps() if "run" in st]


class ConfigCheckInvocationTests(unittest.TestCase):
    """The CLI's own tests pass --read-only by hand; this runs what the YAML really says."""

    def commands(self):
        out = []
        for n, jn, _, st in run_steps():
            for m in re.finditer(r"\$\((release-flow config-check[^)]*)\)", st["run"]):
                out.append((n, jn, m.group(1)))
        return out

    def test_every_invocation_is_accepted_for_a_config_with_consumers_only(self):
        cfg = CLI_DIR / "testdata" / "services.json"
        self.assertIn("consumers_only", cfg.read_text())
        cmds = self.commands()
        self.assertGreaterEqual(len(cmds), 9, "pr-check + plan + drafts + 6 publish slots")
        with tempfile.TemporaryDirectory(dir=wf.ROOT / ".scratch" if (wf.ROOT / ".scratch").is_dir() else None) as d:
            exe = Path(d) / "release-flow"
            exe.write_text(f'#!/bin/sh\nexec python3 -B "{wf.ROOT}/actions/release-flow/release-flow" "$@"\n')
            exe.chmod(0o755)
            env = {**os.environ, "PATH": f"{d}:{os.environ['PATH']}", "PYTHONDONTWRITEBYTECODE": "1",
                   "GITHUB_REPOSITORY_OWNER": "consumer-a-org", "ALLOWED": "issuer,api,ui,website",
                   "READ_ONLY": "cli", "CONFIG": str(cfg)}
            for n, jn, cmd in cmds:
                p = subprocess.run(["bash", "-c", cmd], env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, f"{n}:{jn}: {cmd}\n{p.stderr}")
                self.assertIn('"owner"', p.stdout)

    def test_plan_always_passes_read_only(self):
        plan = [c for n, _, c in self.commands() if n == "release-plan.yml"]
        self.assertEqual(len(plan), 1)
        self.assertIn('--read-only "$READ_ONLY"', plan[0])
        self.assertNotIn("args+=", wf.text("release-plan.yml").split("Config is valid")[1].split("Guard and find")[0])

    def test_no_other_workflow_passes_read_only_to_config_check(self):
        for n, _, c in self.commands():
            if n != "release-plan.yml":
                self.assertNotIn("--read-only", c, n)


class ReportTests(unittest.TestCase):
    def run_report(self, ok="true", rehearsal="false", slots=()):
        """slots: [(repo, 'result:output')] for slots 1..6; missing ones are empty and skipped."""
        job = wf.jobs(wf.load("release-publish.yml"))["report"]
        st = job["steps"][-1]
        with tempfile.TemporaryDirectory(dir=wf.ROOT / ".scratch" if (wf.ROOT / ".scratch").is_dir() else None) as d:
            d = Path(d)
            (d / "release-flow").write_text('#!/bin/bash\nwhile [ $# -gt 0 ]; do [ "$1" != --result ] || echo "RESULT=$2"; shift; done\n')
            (d / "gh").write_text("#!/bin/bash\nexit 0\n")
            for s in ("release-flow", "gh"):
                (d / s).chmod(0o755)
            env = {"PATH": f"{d}:{os.environ['PATH']}", "RUNNER_TEMP": str(d), "GITHUB_STEP_SUMMARY": str(d / "sum"),
                   "GITHUB_REPOSITORY": "o/r", "NEEDS": "{}", "RUN_URL": "u", "GH_TOKEN": "t", "V_RESULT": "success",
                   "V_OK": ok, "V_REHEARSAL": rehearsal, "V_PR": "", "V_STAGE": "", "V_FAILURES": ""}
            for i in range(1, wf.SLOTS + 1):
                repo, p = slots[i - 1] if i <= len(slots) else ("", "skipped:")
                env[f"REPO_{i}"], env[f"P_{i}"] = repo, p
            p = subprocess.run(["bash", "-c", st["run"]], env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            return re.search(r"RESULT=(\w+)", (d / "sum").read_text()).group(1)

    def test_a_listed_slot_that_was_skipped_is_a_failed_publish(self):
        # Cancelled after publish-1: slots 2..n end `skipped`, and nothing was published for them.
        self.assertEqual(self.run_report(slots=[("a", "success:{}"), ("b", "skipped:")]), "failure")

    def test_every_listed_slot_succeeding_is_success(self):
        self.assertEqual(self.run_report(slots=[("a", "success:{}"), ("b", "success:{}")]), "success")

    def test_an_empty_slot_may_be_skipped(self):
        self.assertEqual(self.run_report(slots=[("a", "success:{}")]), "success")

    def test_a_rehearsal_may_skip_every_slot(self):
        self.assertEqual(self.run_report(rehearsal="true", slots=[("a", "skipped:"), ("b", "skipped:")]), "success")

    def test_a_failed_or_cancelled_slot_fails_and_a_not_ok_verdict_fails(self):
        for p in ("failure:{}", "cancelled:"):
            self.assertEqual(self.run_report(slots=[("a", p)]), "failure", p)
        self.assertEqual(self.run_report(ok="false"), "failure")


class ManifestStagingTests(unittest.TestCase):
    def test_manifest_ref_input_and_sha_output(self):
        call = wf.on_block(wf.load("release-plan.yml"))["workflow_call"]
        self.assertEqual(call["inputs"]["manifest-ref"]["default"], "")
        self.assertIn("manifest-sha256", call["outputs"])

    def test_manifest_ref_is_refused_outside_a_rehearsal_and_validated(self):
        plan = wf.jobs(wf.load("release-plan.yml"))["plan"]
        _, st = wf.step_by_id(plan, "in")
        self.assertEqual(st["env"]["MANIFEST_REF"], "${{ inputs.manifest-ref }}")
        run = st["run"]
        self.assertRegex(run, r'(?s)false\).*?-z "\$MANIFEST_REF"')
        self.assertIn("^[A-Za-z0-9._/-]+$", run.split("MANIFEST_REF", 1)[1])
        self.assertRegex(run, r'MANIFEST_REF" != \*\.\.\*')

    def test_rehearsal_fetches_the_ref_as_data_and_reads_with_git_show(self):
        plan = wf.jobs(wf.load("release-plan.yml"))["plan"]
        _, m = wf.step_by_id(plan, "m")
        run = m["run"]
        self.assertEqual(m["env"]["MANIFEST_REF"], "${{ inputs.manifest-ref }}")
        self.assertIn('fetch --no-tags origin "+refs/heads/$MANIFEST_REF:refs/remotes/rehearsal/head"', run)
        self.assertIn('git show "refs/remotes/rehearsal/head:$path" > ' + STAGED, run)
        self.assertNotRegex(run, r"git (checkout|merge|switch|cherry-pick)")

    def test_plan_uploads_the_manifest_and_outputs_its_sha(self):
        plan = wf.jobs(wf.load("release-plan.yml"))["plan"]
        ups = [s for s in plan["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact@")]
        self.assertEqual(len(ups), 1)
        self.assertEqual(ups[0]["with"]["name"], "release-manifest")
        self.assertEqual(ups[0]["with"]["path"], STAGED)
        self.assertEqual(plan["outputs"]["manifest_sha256"], "${{ steps.m.outputs.sha256 }}")
        self.assertIn("sha256sum " + STAGED, wf.step_by_id(plan, "m")[1]["run"])
        # Uploaded for a real release too: the artifact is what later stages read, in every run.
        self.assertNotIn("if", ups[0])
        # plan's own `order` reads the staged copy.
        self.assertEqual(wf.step_by_id(plan, "o")[1]["env"]["MANIFEST"], STAGED)

    def test_every_manifest_reader_downloads_then_checks_the_sha_first(self):
        readers = re.compile(r"release-flow (validate|ci-green|resolve|contract-states|gate-services|drafts|publish)\b")
        examined = 0
        for n in wf.NAMES:
            for jn, job in wf.jobs(wf.load(n)).items():
                steps = job["steps"]
                for i, st in enumerate(steps):
                    if not readers.search(st.get("run", "")):
                        continue
                    examined += 1
                    self.assertEqual(st["env"]["MANIFEST"], STAGED, f"{n}:{jn}")
                    dl = [k for k, s in enumerate(steps[:i]) if str(s.get("uses", "")).startswith("actions/download-artifact@")]
                    self.assertEqual(len(dl), 1, f"{n}:{jn}: want one download before use")
                    d = steps[dl[0]]
                    self.assertEqual(d["with"], {"name": "release-manifest", "path": "release-manifest"})
                    chk = [s for s in steps[dl[0] + 1:i] if "sha256sum" in s.get("run", "")]
                    self.assertEqual(len(chk), 1, f"{n}:{jn}: want one sha256 check between download and use")
                    self.assertIn('[ "$got" = "$WANT" ]', chk[0]["run"])
                    self.assertRegex(chk[0]["env"]["WANT"], r"manifest_sha256 }}$")
                    self.assertEqual(chk[0]["run"].count("exit 1"), 1)
        # resolve: 3, service-gates: 1, drafts: 2 (rehearsal + real), publish: 6 slots.
        self.assertEqual(examined, 3 + 1 + 2 + 6)

    def test_verdict_jobs_download_and_pass_the_staged_file_to_the_cli(self):
        for n in ("release-drafts.yml", "release-publish.yml"):
            job = wf.jobs(wf.load(n))["verdict"]
            _, v = wf.step_by_id(job, "v")
            self.assertIn(f"--manifest-file {STAGED}", v["run"], n)
            self.assertIn("manifest_sha256", job["outputs"], n)
            dl = [s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/download-artifact@")]
            self.assertEqual(len(dl), 1, n)
            self.assertEqual(dl[0]["with"], {"name": "release-manifest", "path": "release-manifest"})

    def test_artifact_actions_are_the_repos_existing_pins(self):
        up = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
        down = "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
        uses = {s["uses"] for _, _, _, s in wf.all_steps() if "artifact" in str(s.get("uses", ""))}
        self.assertEqual(uses, {up, down})


class SelfTestIsolationTests(unittest.TestCase):
    def test_self_test_cannot_import_from_the_caller_checkout(self):
        plan = wf.jobs(wf.load("release-plan.yml"))["plan"]
        run = [s for s in plan["steps"] if "unittest discover" in s.get("run", "")][0]["run"]
        # -P: neither the cwd (the caller's tree) nor the script dir goes on sys.path, so a
        # root-level yaml.py cannot shadow PyYAML and run caller code inside the release.
        self.assertIn("python3 -P -m unittest discover", run)
        self.assertIn("python3 -P -m pip install", run)
        self.assertNotRegex(run, r"python3 (?!-P)")


class WriteMintFailsClosedTests(unittest.TestCase):
    def test_no_write_step_is_gated_on_not_equal_true(self):
        examined = 0
        for n, jn, _, st in wf.all_steps():
            writes = (str(st.get("uses", "")).startswith(wf.MINT)
                      and any(v == "write" for v in wf.perms(st).values())) \
                or "RELEASE_FLOW_WRITE_TOKEN" in (st.get("env") or {})
            if writes:
                examined += 1
                self.assertNotIn("!= 'true'", str(st.get("if", "")), f"{n}:{jn}:{st.get('name')}")
        self.assertGreaterEqual(examined, 1 + 1 + 12)

    def test_drafts_write_steps_require_rehearsal_false(self):
        drafts = wf.jobs(wf.load("release-drafts.yml"))["drafts"]
        for sid in ("app", "d"):
            self.assertIn("needs.verdict.outputs.rehearsal == 'false'", wf.step_by_id(drafts, sid)[1]["if"])


if __name__ == "__main__":
    unittest.main()
