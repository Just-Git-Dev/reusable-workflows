"""Where GitHub credentials may appear in the four release-flow workflows.

ONE GitHub App serves every cross-repo read and every release write. Its key can mint a WRITE
token that publishes a release, and publishing deploys. So the key is confined:

  - it appears ONLY as `with.private-key` of an `actions/create-github-app-token` step, never in
    an `env:` (workflow, job or step), never passed to a workflow, never declared as a secret;
  - every job that mints runs under `environment: ${{ inputs.environment }}`;
  - only the `drafts` job (non-rehearsal mint) and the six `publish-N` jobs mint a write
    permission; every other mint is read-only; a rehearsal never gets a write token;
  - a write job runs no third-party action besides checkout and the mint, and installs nothing;
  - `release-pr-check.yml` references no secret and mints nothing;
  - `repositories` and `owner` of a mint come from a validated step output, never a raw input.
"""
import re
import unittest

import wf

KEY = "RELEASE_APP_KEY"
KEY_REF = "${{ secrets.RELEASE_APP_KEY }}"


class KeyConfinementTests(unittest.TestCase):
    def test_key_appears_only_as_private_key_of_a_mint_step(self):
        examined = 0
        for n in wf.NAMES:
            w = wf.load(n)
            self.assertNotIn(KEY, str(w.get("env", "")), f"{n}: workflow env")
            call = wf.on_block(w)["workflow_call"]
            self.assertNotIn("secrets", call, f"{n}: declares a secret")
            self.assertFalse([k for k in call["inputs"] if "key" in k.lower()], f"{n}: an input carries a key")
            for jn, job in wf.jobs(w).items():
                self.assertNotIn(KEY, str(job.get("env", "")), f"{n}:{jn}: job env")
                self.assertNotIn("secrets", job, f"{n}:{jn}: passes secrets")
                for st in job["steps"]:
                    examined += 1
                    if KEY not in str(st):
                        continue
                    self.assertTrue(str(st.get("uses", "")).startswith(wf.MINT), f"{n}:{jn}: key in {st.get('name')}")
                    self.assertEqual(st["with"]["private-key"], KEY_REF)
                    self.assertNotIn(KEY, str(st.get("env", "")))
        self.assertGreater(examined, 50, "examined suspiciously few steps")

    def test_the_number_of_mint_steps_is_pinned(self):
        # 2 (plan) + 2 (drafts, read + write) + 6 (publish slots)
        mints = wf.mint_steps()
        self.assertEqual(len(mints), 10)
        self.assertEqual(sum(1 for m in mints if m[0] == "release-plan.yml"), 2)
        self.assertEqual(sum(1 for m in mints if m[0] == "release-drafts.yml"), 2)
        self.assertEqual(sum(1 for m in mints if m[0] == "release-publish.yml"), 6)

    def test_the_mint_action_is_pinned_to_the_proven_sha(self):
        for n, jn, _, st in wf.mint_steps():
            self.assertEqual(st["uses"], "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
                             f"{n}:{jn}")

    def test_every_minting_job_runs_in_the_input_environment(self):
        for n, jn, job, _ in wf.mint_steps():
            self.assertEqual(job.get("environment"), "${{ inputs.environment }}", f"{n}:{jn}")

    def test_pr_check_has_no_secret_no_mint_no_environment(self):
        self.assertNotIn("secrets.", wf.text("release-pr-check.yml"))
        self.assertNotIn(KEY, wf.text("release-pr-check.yml"))
        self.assertFalse([m for m in wf.mint_steps() if m[0] == "release-pr-check.yml"])
        self.assertNotIn("environment", wf.jobs(wf.load("release-pr-check.yml"))["release-pr"])
        self.assertNotIn("WRITE_TOKEN", wf.text("release-pr-check.yml"))


class WriteScopeTests(unittest.TestCase):
    def test_only_drafts_and_publish_slots_mint_a_write_permission(self):
        writers = []
        for n, jn, _, st in wf.mint_steps():
            p = wf.perms(st)
            self.assertTrue(p, f"{n}:{jn}: a mint must state its permissions")
            writes = {k for k, v in p.items() if v != "read"}
            if not writes:
                continue
            writers.append((n, jn, st.get("id")))
            ok = (n == "release-drafts.yml" and jn == "drafts") or \
                 (n == "release-publish.yml" and re.fullmatch(r"publish-[1-6]", jn))
            self.assertTrue(ok, f"{n}:{jn}: a read-only job mints {writes}")
        self.assertEqual(len(writers), 1 + wf.SLOTS)

    def test_the_drafts_write_mint_is_excluded_in_a_rehearsal(self):
        job = wf.jobs(wf.load("release-drafts.yml"))["drafts"]
        for sid in ("app", "d"):
            _, st = wf.step_by_id(job, sid)
            self.assertEqual(st["if"], "${{ needs.verdict.outputs.rehearsal == 'false' }}", sid)
        for sid in ("app-ro", "dr"):
            _, st = wf.step_by_id(job, sid)
            self.assertEqual(st["if"], "${{ needs.verdict.outputs.rehearsal == 'true' }}", sid)
        _, ro = wf.step_by_id(job, "app-ro")
        self.assertEqual(set(wf.perms(ro).values()), {"read"})

    def test_publish_slot_n_is_scoped_to_its_single_repo(self):
        wf_ = wf.load("release-publish.yml")
        for n in range(1, wf.SLOTS + 1):
            job = wf.jobs(wf_)[f"publish-{n}"]
            _, app = wf.step_by_id(job, "app")
            _, slot = wf.step_by_id(job, "slot")
            self.assertEqual(app["with"]["repositories"], "${{ steps.slot.outputs.repo }}")
            self.assertNotIn(",", slot["run"].split('echo "repo=')[1].split("\n")[0])
            self.assertEqual(wf.perms(app), {"permission-contents": "write", "permission-actions": "write"})

    def test_read_mints_state_exactly_the_scopes_they_need(self):
        plan = wf.jobs(wf.load("release-plan.yml"))
        _, resolve = wf.step_by_id(plan["resolve"], "app")
        self.assertEqual(wf.perms(resolve), {"permission-contents": "read", "permission-actions": "read",
                                             "permission-checks": "read"})
        self.assertEqual(resolve["with"]["repositories"], "${{ steps.repos.outputs.list }}")
        _, gates = wf.step_by_id(plan["service-gates"], "app")
        self.assertEqual(wf.perms(gates), {"permission-checks": "read", "permission-contents": "read"})

    def test_write_jobs_run_nothing_third_party_and_install_nothing(self):
        examined = 0
        seen = set()
        for n, jn, job, st in wf.mint_steps():
            if (n, jn) in seen or all(v == "read" for v in wf.perms(st).values()):
                continue
            seen.add((n, jn))
            examined += 1
            for st in job["steps"]:
                uses = str(st.get("uses", ""))
                # download-artifact: the staged manifest, sha256-checked before any use.
                self.assertTrue(not uses or uses.startswith((wf.CHECKOUT, wf.MINT, "actions/download-artifact@")),
                                f"{n}:{jn}: {uses}")
                self.assertNotRegex(st.get("run", ""), r"pip install|npm |go (get|install|run)|curl |wget ",
                                    f"{n}:{jn}:{st.get('name')}")
        self.assertGreaterEqual(examined, 1 + wf.SLOTS)

    def test_write_token_env_name_appears_only_in_drafts_and_publish(self):
        for n, jn, job, st in wf.all_steps():
            if "RELEASE_FLOW_WRITE_TOKEN" in (st.get("env") or {}):
                ok = (n, jn) == ("release-drafts.yml", "drafts") or (n == "release-publish.yml" and jn.startswith("publish-"))
                self.assertTrue(ok, f"{n}:{jn}:{st.get('name')}")
        for n in ("release-pr-check.yml", "release-plan.yml"):
            self.assertNotIn("WRITE_TOKEN", wf.text(n))


class MintArgumentTests(unittest.TestCase):
    """`owner` and `repositories` come from a step output set by a step that validated them."""

    def test_owner_and_repositories_are_validated_step_outputs(self):
        for n, jn, job, st in wf.mint_steps():
            w = st["with"]
            owner, repos = str(w["owner"]), str(w["repositories"])
            self.assertRegex(owner, r"^\$\{\{ (needs\.plan|steps\.(cfg|slot))\.outputs\.owner \}\}$", f"{n}:{jn}")
            m = re.fullmatch(r"\$\{\{ steps\.([a-z]+)\.outputs\.(list|repo) \}\}", repos)
            self.assertIsNotNone(m, f"{n}:{jn}: repositories {repos!r} must be a validated step output")
            i, producer = wf.step_by_id(job, m.group(1))
            self.assertLess(i, job["steps"].index(st), f"{n}:{jn}: validated after the mint")
            self.assertIn("=~", producer["run"], f"{n}:{jn}: producer does not validate")
            self.assertIn("exit 1", producer["run"])
            self.assertIn("[a-z0-9]", producer["run"])

    def test_owner_comes_from_config_check_never_a_literal(self):
        for n, jn, _, st in wf.mint_steps():
            self.assertNotRegex(str(st["with"]["owner"]), r"^[A-Za-z0-9-]+$", f"{n}:{jn}: hard-coded owner")
        plan = wf.jobs(wf.load("release-plan.yml"))["plan"]
        _, cfg = wf.step_by_id(plan, "cfg")
        self.assertIn("release-flow config-check", cfg["run"])
        self.assertEqual(plan["outputs"]["owner"], "${{ steps.cfg.outputs.owner }}")

    def test_app_id_is_an_input_not_a_secret(self):
        for n, jn, _, st in wf.mint_steps():
            self.assertEqual(st["with"]["app-id"], "${{ inputs.app-id }}", f"{n}:{jn}")


class PrCheckCheckoutTests(unittest.TestCase):
    def test_no_checkout_persists_credentials(self):
        examined = 0
        for n, jn, _, st in wf.all_steps():
            if str(st.get("uses", "")).startswith(wf.CHECKOUT):
                examined += 1
                self.assertIs(st["with"].get("persist-credentials"), False, f"{n}:{jn}")
        self.assertEqual(examined, 2 * (1 + 3 + 2 + 8))


if __name__ == "__main__":
    unittest.main()
