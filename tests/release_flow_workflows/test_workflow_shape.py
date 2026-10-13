"""Shape of the four release-flow reusable workflows (docs/release-flow.md).

Pins: SHA pins, `shell: bash`, no `${{ }}` inside `run:`, no concurrency group, the stamped
WORKFLOW_VERSION / RELEASE_FLOW_TREE, the CLI-load step sequence with the tree assertion, the
attempt-1 guard, the self-test's skip/zero-test refusal, rehearsal semantics, the six publish
slots and their chaining, and the report job.
"""
import re
import unittest

import wf


class EveryWorkflowTests(unittest.TestCase):
    def test_four_workflows_are_reusable_and_declare_no_secrets(self):
        for n in wf.NAMES:
            w = wf.load(n)
            call = wf.on_block(w).get("workflow_call")
            self.assertIsNotNone(call, f"{n}: not a workflow_call")
            self.assertNotIn("secrets", call, f"{n}: declares secrets; none are passed")
            self.assertEqual(set(wf.on_block(w)), {"workflow_call"}, n)

    def test_every_run_is_bash_via_default_or_explicit_shell(self):
        examined = 0
        for n in wf.NAMES:
            default = ((wf.load(n).get("defaults") or {}).get("run") or {}).get("shell")
            for _, jn, job, st in [t for t in wf.all_steps() if t[0] == n]:
                if "run" in st:
                    examined += 1
                    shell = st.get("shell") or (job.get("defaults") or {}).get("run", {}).get("shell") or default
                    self.assertEqual(shell, "bash", f"{n}:{jn}:{st.get('name')}")
        self.assertGreater(examined, 30, "examined suspiciously few run steps")

    def test_no_expression_inside_a_run_body(self):
        for n, jn, _, st in wf.all_steps():
            self.assertNotIn("${{", st.get("run", ""), f"{n}:{jn}:{st.get('name')}: inputs must go through env")

    def test_every_action_is_sha_pinned_with_a_version_comment(self):
        examined = 0
        for n in wf.NAMES:
            lines = wf.text(n).splitlines()
            for ln in lines:
                m = re.match(r"\s*(?:-\s*)?uses:\s*(\S+)(.*)$", ln)
                if not m:
                    continue
                examined += 1
                self.assertRegex(m.group(1), wf.SHA_RE, f"{n}: {ln.strip()}")
                self.assertRegex(m.group(2), r"#\s*v\d+\.\d+\.\d+", f"{n}: no version comment: {ln.strip()}")
        self.assertGreaterEqual(examined, 39)

    def test_no_concurrency_group(self):
        # A concurrency group silently REPLACES a pending release; the CLI's `concurrent`
        # guard fails loudly instead.
        for n in wf.NAMES:
            w = wf.load(n)
            self.assertNotIn("concurrency", w, n)
            for jn, job in wf.jobs(w).items():
                self.assertNotIn("concurrency", job, f"{n}:{jn}")

    def test_stamps_are_present_and_well_formed(self):
        for n in wf.NAMES:
            env = wf.load(n).get("env") or {}
            self.assertRegex(str(env.get("WORKFLOW_VERSION")), r"^v\d+\.\d+\.\d+$", n)
            # A string, not a YAML number: an all-digit hash would load as an int (and one like
            # 1e5... as a float), so the stamp is always written quoted.
            self.assertIsInstance(env.get("RELEASE_FLOW_TREE"), str, n)
            self.assertRegex(env["RELEASE_FLOW_TREE"], r"^[0-9a-f]{40}$", n)
            self.assertRegex(wf.text(n), r'(?m)^  RELEASE_FLOW_TREE: "[0-9a-f]{40}"', n)

    def test_workflow_permissions_default_to_contents_read(self):
        for n in wf.NAMES:
            self.assertEqual(wf.load(n).get("permissions"), {"contents": "read"}, n)
            for jn, job in wf.jobs(wf.load(n)).items():
                granted = {k: v for k, v in (job.get("permissions") or {}).items() if v != "read"}
                if (n, jn) == ("release-publish.yml", "report"):
                    self.assertEqual(granted, {"pull-requests": "write"})
                else:
                    self.assertEqual(granted, {}, f"{n}:{jn}: GITHUB_TOKEN write grant")


class CliLoadSequenceTests(unittest.TestCase):
    """Every job: checkout caller, checkout this repo at WORKFLOW_VERSION, assert the tree, PATH."""

    def test_every_job_loads_and_pins_the_cli_before_using_it(self):
        jobs_seen = 0
        for n in wf.NAMES:
            for jn, job in wf.jobs(wf.load(n)).items():
                jobs_seen += 1
                steps = job["steps"]
                idx = [i for i, s in enumerate(steps)
                       if str(s.get("uses", "")).startswith(wf.CHECKOUT)
                       and (s.get("with") or {}).get("path") == ".release-flow-src"]
                self.assertEqual(len(idx), 1, f"{n}:{jn}: want one CLI checkout")
                i = idx[0]
                caller, cli, pin = steps[i - 1], steps[i], steps[i + 1]
                self.assertTrue(str(caller.get("uses", "")).startswith(wf.CHECKOUT), f"{n}:{jn}")
                self.assertIs(caller["with"].get("persist-credentials"), False, f"{n}:{jn}: caller checkout")
                self.assertNotIn("repository", caller["with"], f"{n}:{jn}")
                self.assertEqual(cli["with"]["repository"], "Just-Git-Dev/reusable-workflows")
                self.assertEqual(cli["with"]["ref"], "${{ env.WORKFLOW_VERSION }}", f"{n}:{jn}")
                self.assertIs(cli["with"].get("persist-credentials"), False, f"{n}:{jn}: CLI checkout")
                run = pin["run"]
                self.assertIn('git -C .release-flow-src rev-parse HEAD:actions/release-flow', run)
                self.assertIn('[ "$got" = "$RELEASE_FLOW_TREE" ]', run)
                self.assertIn("::error::", run)
                self.assertIn("exit 1", run)
                self.assertIn('echo "$GITHUB_WORKSPACE/.release-flow-src/actions/release-flow" >> "$GITHUB_PATH"', run)
                # Nothing may run the CLI before it is pinned.
                for s in steps[: i + 1]:
                    self.assertNotRegex(s.get("run", ""), r"release-flow (?!src)[a-z-]+ ", f"{n}:{jn}")
        self.assertEqual(jobs_seen, 1 + 3 + 2 + 8)

    def test_pr_check_checks_out_the_base_commit_and_fetches_the_head_as_data(self):
        job = wf.jobs(wf.load("release-pr-check.yml"))["release-pr"]
        first = job["steps"][0]
        self.assertEqual(first["with"]["ref"], "${{ github.event.pull_request.base.sha }}")
        self.assertEqual(first["with"]["fetch-depth"], 0)
        text = wf.text("release-pr-check.yml")
        self.assertNotIn("pull_request_target", text)
        self.assertIn("refs/pull/$PR_NUMBER/head", text)
        self.assertIn("find-manifest", text)
        self.assertIn("--pr", text)
        self.assertEqual(job.get("name"), "release-pr")
        self.assertNotIn("environment", job)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.w = wf.load("release-plan.yml")
        self.jobs = wf.jobs(self.w)

    def test_inputs_and_outputs_match_the_spec(self):
        call = wf.on_block(self.w)["workflow_call"]
        ins = call["inputs"]
        required = {k for k, v in ins.items() if v.get("required")}
        self.assertEqual(required, {"allowed", "app-id"})
        self.assertEqual(set(ins), {"allowed", "read-only-repos", "app-id", "environment", "config",
                                    "release-workflow", "pr-check-name", "pr-check-workflow",
                                    "rehearsal", "manifest", "manifest-ref"})
        self.assertEqual(ins["environment"]["default"], "release")
        self.assertEqual(ins["pr-check-name"]["default"], "release-pr / release-pr")
        self.assertEqual(ins["rehearsal"]["type"], "boolean")
        self.assertEqual(set(call["outputs"]), {"manifest", "manifest-sha256", "pr", "order", "rehearsal", "resolved",
                                           "checks"})

    def test_jobs_and_needs(self):
        self.assertEqual(list(self.jobs), ["plan", "resolve", "service-gates"])
        self.assertEqual(self.jobs["resolve"]["needs"], "plan")
        self.assertEqual(self.jobs["service-gates"]["needs"], ["plan", "resolve"])

    def test_plan_job_holds_no_app_token_and_reads_with_the_github_token(self):
        plan = self.jobs["plan"]
        self.assertNotIn("environment", plan)
        self.assertFalse([s for s in plan["steps"] if str(s.get("uses", "")).startswith(wf.MINT)])
        self.assertEqual(plan["permissions"], {"contents": "read", "pull-requests": "read",
                                               "checks": "read", "actions": "read"})
        _, m = wf.step_by_id(plan, "m")
        self.assertEqual(m["env"]["RELEASE_FLOW_READ_TOKEN"], "${{ github.token }}")

    def test_attempt_one_guard(self):
        _, st = wf.step_by_id(self.jobs["plan"], "in")
        self.assertEqual(st["env"]["ATTEMPT"], "${{ github.run_attempt }}")
        self.assertIn('[ "$ATTEMPT" = "1" ]', st["run"])
        self.assertIn("exit 1", st["run"])

    def test_rehearsal_rules(self):
        _, st = wf.step_by_id(self.jobs["plan"], "in")
        run = st["run"]
        self.assertIn("true) [ -n \"$MANIFEST_IN\" ]", run)    # a rehearsal needs a manifest
        self.assertIn("false) [ -z \"$MANIFEST_IN\" ]", run)   # a real release must not have one
        _, m = wf.step_by_id(self.jobs["plan"], "m")
        body = m["run"]
        rehearsal_branch, real_branch = body.split("\nelse\n", 1)
        real_branch = real_branch.split("\nfi\n", 1)[0]
        self.assertIn('path="$MANIFEST_IN"', rehearsal_branch)
        self.assertIn('[ -f "$path" ]', body)
        self.assertNotIn("check-merge", rehearsal_branch)
        self.assertIn("check-merge", real_branch)
        self.assertIn("find-manifest", real_branch)
        self.assertIn('--base "$BEFORE" --head "$AFTER"', real_branch)
        # The concurrent guard runs for a rehearsal too.
        self.assertIn("release-flow concurrent", body.split("sha256sum", 1)[1])
        self.assertIn('--workflow-path "$PR_CHECK_WORKFLOW"', body)

    def test_self_test_fails_on_a_skip_and_on_zero_tests(self):
        st = [s for s in self.jobs["plan"]["steps"] if "unittest discover" in s.get("run", "")]
        self.assertEqual(len(st), 1)
        run = st[0]["run"]
        self.assertIn("pip install", run)
        self.assertIn("pyyaml", run)
        self.assertIn(".release-flow-src/actions/release-flow/releaseflow", run)
        self.assertIn("Ran [1-9][0-9]* test", run)
        self.assertIn("skipped=", run)
        self.assertGreaterEqual(run.count("exit 1"), 3)

    def test_step_order_in_plan(self):
        names = [s.get("id") or s.get("name", "") for s in self.jobs["plan"]["steps"]]
        order = [i for i, s in enumerate(self.jobs["plan"]["steps"])
                 if any(k in s.get("run", "") for k in ("unittest discover", "config-check", "release-flow order"))
                 or s.get("id") in ("in", "m")]
        self.assertEqual(order, sorted(order), names)
        ids = [s.get("id") for s in self.jobs["plan"]["steps"] if s.get("id")]
        self.assertEqual(ids, ["in", "cfg", "m", "o", "up"])

    def test_resolve_runs_the_read_checks_with_the_minted_token(self):
        steps = self.jobs["resolve"]["steps"]
        runs = " ".join(s.get("run", "") for s in steps)
        for sub in ("release-flow validate", "release-flow ci-green", "release-flow resolve",
                    "release-flow contract-states"):
            self.assertIn(sub, runs)
        for s in steps:
            if "release-flow validate" in s.get("run", "") or "release-flow ci-green" in s.get("run", ""):
                self.assertEqual(s["env"]["RELEASE_FLOW_READ_TOKEN"], "${{ steps.app.outputs.token }}")
        self.assertNotIn("WRITE_TOKEN", wf.text("release-plan.yml"))

    def test_service_gates_uses_the_pinned_check_release_gate(self):
        steps = self.jobs["service-gates"]["steps"]
        gate = steps[-1]
        self.assertEqual(gate["uses"], "Just-Git-Dev/reusable-workflows/actions/check-release-gate"
                                       "@08b6f7260a8e17d8bceff7744c0408bac06001f9")
        self.assertEqual(gate["with"]["services"], "${{ steps.s.outputs.services }}")
        self.assertEqual(gate["with"]["token"], "${{ steps.app.outputs.token }}")
        _, s = wf.step_by_id(self.jobs["service-gates"], "s")
        self.assertIn("release-flow gate-services", s["run"])


class DraftsTests(unittest.TestCase):
    def setUp(self):
        self.w = wf.load("release-drafts.yml")
        self.jobs = wf.jobs(self.w)

    def test_shape(self):
        self.assertEqual(list(self.jobs), ["verdict", "drafts"])
        call = wf.on_block(self.w)["workflow_call"]
        self.assertEqual({k for k, v in call["inputs"].items() if v.get("required")}, {"needs", "allowed", "app-id"})
        self.assertEqual(call["inputs"]["contracts-job"]["default"], "contracts")
        self.assertEqual(set(call["outputs"]), {"drafts"})
        self.assertEqual(self.jobs["drafts"]["needs"], "verdict")

    def test_verdict_job_uses_the_cli_and_fails_on_not_ok(self):
        _, v = wf.step_by_id(self.jobs["verdict"], "v")
        run = v["run"]
        self.assertIn("release-flow verdict --stage drafts", run)
        self.assertIn('--needs-file "$RUNNER_TEMP/needs.json"', run)
        self.assertIn('--contracts-job "$CONTRACTS_JOB"', run)
        self.assertEqual(v["env"]["NEEDS"], "${{ inputs.needs }}")
        self.assertIn('if [ "$rc" -ne 0 ]', run)
        self.assertIn("exit 1", run)
        self.assertNotIn("environment", self.jobs["verdict"])

    def test_rehearsal_gets_a_read_token_and_check_only(self):
        drafts = self.jobs["drafts"]
        _, ro = wf.step_by_id(drafts, "app-ro")
        self.assertIn("== 'true'", ro["if"])
        self.assertEqual({v for v in wf.perms(ro).values()}, {"read"})
        _, dr = wf.step_by_id(drafts, "dr")
        self.assertIn("--check-only", dr["run"])
        self.assertEqual(dr["env"]["RELEASE_FLOW_READ_TOKEN"], "${{ steps.app-ro.outputs.token }}")
        self.assertNotIn("RELEASE_FLOW_WRITE_TOKEN", dr["env"])
        self.assertIn("== 'true'", dr["if"])

    def test_write_mint_and_step_exclude_rehearsal(self):
        drafts = self.jobs["drafts"]
        _, app = wf.step_by_id(drafts, "app")
        self.assertIn("== 'false'", app["if"])
        self.assertEqual(wf.perms(app), {"permission-contents": "write", "permission-actions": "read",
                                         "permission-checks": "read"})
        _, d = wf.step_by_id(drafts, "d")
        self.assertIn("== 'false'", d["if"])
        self.assertNotIn("--check-only", d["run"])
        self.assertEqual(d["env"]["RELEASE_FLOW_WRITE_TOKEN"], "${{ steps.app.outputs.token }}")
        # Whatever was created must be reported even when the command fails partway.
        self.assertIn('exit "$rc"', d["run"])
        self.assertIn("drafts=", d["run"])


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.w = wf.load("release-publish.yml")
        self.jobs = wf.jobs(self.w)

    def test_job_list(self):
        want = ["verdict"] + [f"publish-{i}" for i in range(1, wf.SLOTS + 1)] + ["report"]
        self.assertEqual(list(self.jobs), want)

    def test_inputs(self):
        ins = wf.on_block(self.w)["workflow_call"]["inputs"]
        self.assertEqual({k for k, v in ins.items() if v.get("required")}, {"needs", "allowed", "app-id"})
        self.assertEqual(ins["required-jobs"]["default"], "plan,drafts")
        self.assertEqual(ins["contracts-job"]["default"], "contracts")
        self.assertNotIn("outputs", wf.on_block(self.w)["workflow_call"])

    def test_verdict_uses_the_cli_and_never_fails_on_not_ok(self):
        v = self.jobs["verdict"]
        _, st = wf.step_by_id(v, "v")
        self.assertIn("release-flow verdict --stage publish", st["run"])
        self.assertIn('--required "$REQUIRED_JOBS"', st["run"])
        self.assertIn("rc=$?", st["run"])
        self.assertNotIn("exit", st["run"], "a not-ok verdict must reach the report job, not fail here")
        self.assertEqual(set(v["outputs"]), {"ok", "rehearsal", "pr", "manifest", "manifest_sha256", "failed_stage", "failures",
                                             *[f"repo{i}" for i in range(1, wf.SLOTS + 1)]})

    def test_slot_chaining(self):
        for n in range(1, wf.SLOTS + 1):
            job = self.jobs[f"publish-{n}"]
            self.assertEqual(job["needs"], ["verdict"] + [f"publish-{k}" for k in range(1, n)])
            cond = job["if"]
            for part in ("!cancelled()", "needs.verdict.outputs.ok == 'true'",
                         "needs.verdict.outputs.rehearsal == 'false'",
                         f"needs.verdict.outputs.repo{n} != ''"):
                self.assertIn(part, cond, f"publish-{n}")
            self.assertNotIn("always()", cond)
            for k in range(1, n):
                self.assertIn(f"(needs.publish-{k}.result == 'success' || needs.publish-{k}.result == 'skipped')", cond)
            self.assertNotIn(f"needs.publish-{n}.", cond)
            self.assertEqual(job["timeout-minutes"], 55)
            self.assertEqual(job["outputs"], {"result": "${{ steps.p.outputs.result }}"})
            self.assertEqual(job["environment"], "${{ inputs.environment }}")

    def test_slot_asserts_allowed_before_minting_and_mints_one_repo(self):
        for n in range(1, wf.SLOTS + 1):
            job = self.jobs[f"publish-{n}"]
            si, slot = wf.step_by_id(job, "slot")
            ai, app = wf.step_by_id(job, "app")
            self.assertLess(si, ai)
            self.assertEqual(slot["env"]["REPO"], f"${{{{ needs.verdict.outputs.repo{n} }}}}")
            self.assertIn('case ",$ALLOWED," in *",$REPO,"*) ;;', slot["run"])
            self.assertIn("exit 1", slot["run"])
            self.assertEqual(app["with"]["repositories"], "${{ steps.slot.outputs.repo }}")
            self.assertEqual(wf.perms(app), {"permission-contents": "write", "permission-actions": "write"})
            _, p = wf.step_by_id(job, "p")
            self.assertIn("release-flow publish", p["run"])
            self.assertIn('--repo "$REPO"', p["run"])
            self.assertEqual(p["env"]["REPO"], "${{ steps.slot.outputs.repo }}")
            self.assertEqual(p["env"]["RELEASE_FLOW_WRITE_TOKEN"], "${{ steps.app.outputs.token }}")
            self.assertIn('exit "$rc"', p["run"])

    def test_report_job(self):
        r = self.jobs["report"]
        self.assertEqual(r["if"], "${{ always() }}")
        self.assertEqual(r["needs"], ["verdict"] + [f"publish-{i}" for i in range(1, wf.SLOTS + 1)])
        self.assertEqual(r["permissions"], {"contents": "read", "pull-requests": "write"})
        self.assertNotIn("environment", r)
        self.assertFalse([s for s in r["steps"] if str(s.get("uses", "")).startswith(wf.MINT)])
        st = r["steps"][-1]
        self.assertEqual(st["env"]["GH_TOKEN"], "${{ github.token }}")
        run = st["run"]
        self.assertIn("rehearsal: no writes", run)
        self.assertIn("release-flow report", run)
        self.assertIn(">> \"$GITHUB_STEP_SUMMARY\"", run)
        # The comment is posted only for a real release that has a PR.
        self.assertRegex(run, r'if \[ -n "\$pr" \] && \[ "\$rehearsal" != "true" \]; then\n\s+\[\[ "\$pr" =~ \^\[0-9\]\+\$ \]\].*\n\s+gh pr comment')
        self.assertEqual(run.count("gh pr comment"), 1)
        for i in range(1, wf.SLOTS + 1):
            self.assertEqual(st["env"][f"P_{i}"], f"${{{{ needs.publish-{i}.result }}}}:${{{{ needs.publish-{i}.outputs.result }}}}")
        # A cancelled or failed slot is a failed publish: only success passes; skipped only for an empty slot or a rehearsal.
        self.assertIn("success:*) ;;", run)
        self.assertIn('skipped:*) if [ -n "$listed" ]', run)


if __name__ == "__main__":
    unittest.main()
