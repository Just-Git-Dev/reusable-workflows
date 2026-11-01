"""v6 credential modes of the three release workflows that hold credentials (plan, drafts, publish).

Each takes EITHER the App (`client-id` input + `RELEASE_APP_KEY` secret) OR one caller token
(`github-token` secret), never both. What these tests pin, all on the YAML shape:

  - every mint passes `client-id` and is skipped in token mode (`inputs.client-id != ''`, ANDed
    with any existing `if:`); `app-id` appears nowhere;
  - every consumer of a mint's output reads `steps.<mint>.outputs.token || secrets.github-token`;
  - `secrets.github-token` appears nowhere else but there and in the guard;
  - the guard is one byte-identical step, the first step (after any refusal) of EVERY job that
    mints, each such job declaring `environment:`, and in no job without a mint; it has the four settled messages in the settled order, and no `${{ }}` inside its `run:`;
  - docs/release-flow.md states the least-privilege consequence of token mode.

Behaviour of the guard body (6 env combinations) is run by tests/run_auth_mode_tests.py.
"""
import json
import re
import unittest

import wf

MESSAGES = [
    "pass the App or github-token, not both",
    "no credentials: pass the App (client-id and its private key) or github-token",
    "App incomplete: missing client-id",
    "App incomplete: missing private key",
]
GATE = "inputs.client-id != ''"
CONSUMER = re.compile(r"^\$\{\{ steps\.[\w-]+\.outputs\.token \|\| secrets\.github-token \}\}$")


def mint_jobs(name):
    """(job name, job) for every job of the workflow that contains a mint."""
    return [(jn, j) for jn, j in wf.jobs(wf.load(name)).items()
            if any(str(st.get("uses", "")).startswith(wf.MINT) for st in j.get("steps") or [])]


def guards(name):
    """(job name, guard step) for every guard of the workflow."""
    return [(jn, wf.guard_step(j)[1]) for jn, j in wf.jobs(wf.load(name)).items() if wf.guard_step(j)[1]]


def values(step):
    """(where, value) for every env/with value of a step."""
    for where in ("env", "with"):
        for k, v in (step.get(where) or {}).items():
            yield f"{where}.{k}", str(v)


class MintTests(unittest.TestCase):
    def test_every_mint_takes_client_id_and_is_skipped_in_token_mode(self):
        mints = [m for m in wf.mint_steps() if m[0] in wf.RELEASE_NAMES]
        self.assertEqual(len(mints), 10)
        for n, jn, _, st in mints:
            self.assertEqual(st["with"].get("client-id"), "${{ inputs.client-id }}", f"{n}:{jn}")
            cond = str(st.get("if", ""))
            self.assertTrue(cond == "${{ " + GATE + " }}" or
                            (cond.startswith("${{ " + GATE + " && ") and cond.endswith(" }}")),
                            f"{n}:{jn}: if {cond!r} must be the client-id gate, ANDed with any existing if")

    def test_app_id_appears_nowhere(self):
        for n in wf.RELEASE_NAMES:
            self.assertNotIn("app-id", wf.text(n), n)
            for _, _, _, st in [t for t in wf.all_steps() if t[0] == n]:
                self.assertNotIn("app-id", st.get("with") or {}, n)


class ConsumerTests(unittest.TestCase):
    def test_every_token_consumer_falls_back_to_the_caller_token(self):
        examined = 0
        for n, jn, _, st in wf.all_steps():
            if n not in wf.RELEASE_NAMES:
                continue
            for where, v in values(st):
                if ".outputs.token" in v:
                    examined += 1
                    self.assertRegex(v, CONSUMER, f"{n}:{jn}:{st.get('name')}:{where}")
        self.assertGreaterEqual(examined, 15, "examined suspiciously few token consumers")

    def test_caller_token_appears_only_in_consumers_and_the_guard(self):
        for n in wf.RELEASE_NAMES:
            allowed = 0
            for _, jn, _, st in [t for t in wf.all_steps() if t[0] == n]:
                for _, v in values(st):
                    if "secrets.github-token" in v:
                        allowed += v.count("secrets.github-token")
                        ok = CONSUMER.match(v) or (v == "${{ secrets.github-token != '' }}" and
                                                   "TOKEN_SET" in (st.get("env") or {}))
                        self.assertTrue(ok, f"{n}:{jn}:{st.get('name')}: {v!r}")
                self.assertNotIn("secrets.github-token", st.get("run", ""), f"{n}:{jn}: in a run body")
            self.assertGreater(allowed, 1, n)
            self.assertEqual(wf.text(n).count("secrets.github-token"), allowed,
                             f"{n}: secrets.github-token outside a step env/with (comment, job env, ...)")


class GuardTests(unittest.TestCase):
    def test_guard_is_the_first_step_of_every_minting_job_and_only_there(self):
        examined = 0
        for n in wf.RELEASE_NAMES:
            minting = dict(mint_jobs(n))
            self.assertTrue(minting, n)
            for jn, job in wf.jobs(wf.load(n)).items():
                i, g = wf.guard_step(job)
                if jn not in minting:
                    self.assertIsNone(g, f"{n}:{jn}: a guard in a job without a mint")
                    continue
                examined += 1
                self.assertIsNotNone(g, f"{n}:{jn}: mints but has no credentials guard")
                for st in job["steps"][:i]:
                    self.assertTrue(str(st.get("name", "")).startswith("Refuse"),
                                    f"{n}:{jn}: {st.get('name')!r} runs before the guard")
                self.assertEqual(sum(1 for st in job["steps"] if "KEY_SET" in (st.get("env") or {})), 1, f"{n}:{jn}")
        self.assertEqual(examined, 2 + 1 + 6, "minting jobs: resolve, service-gates, drafts, publish-1..6")

    def test_every_job_with_a_mint_or_a_guard_declares_environment(self):
        examined = 0
        for n in wf.RELEASE_NAMES:
            held = {jn for jn, _ in mint_jobs(n)} | {jn for jn, _ in guards(n)}
            for jn in held:
                examined += 1
                self.assertTrue(wf.jobs(wf.load(n))[jn].get("environment"),
                                f"{n}:{jn}: mints or guards without environment: (caller-environment secrets are empty here)")
        self.assertEqual(examined, 9)

    def test_every_job_naming_the_caller_token_declares_environment(self):
        # Token mode has the same trap as the key: a job that reads secrets.github-token
        # without environment: sees an empty token, even with no mint in it.
        examined = 0
        for n in wf.RELEASE_NAMES:
            for jn, job in wf.jobs(wf.load(n)).items():
                if "secrets.github-token" not in json.dumps(job):
                    continue
                examined += 1
                self.assertTrue(job.get("environment"),
                                f"{n}:{jn}: reads secrets.github-token without environment:")
        self.assertEqual(examined, 9)

    def test_guard_env_is_booleans_and_the_input_only(self):
        for n in wf.RELEASE_NAMES:
            self.assertTrue(guards(n), n)
            for jn, g in guards(n):
                self.assertEqual(g["env"], {"CLIENT_ID": "${{ inputs.client-id }}",
                                            "KEY_SET": "${{ secrets.RELEASE_APP_KEY != '' }}",
                                            "TOKEN_SET": "${{ secrets.github-token != '' }}"}, f"{n}:{jn}")
                self.assertNotIn("${{", g["run"], f"{n}:{jn}: expression in the guard's run body")

    def test_guard_states_the_four_settled_messages_in_order(self):
        for n in wf.RELEASE_NAMES:
            self.assertTrue(guards(n), n)
            for jn, g in guards(n):
                at = [g["run"].find(m) for m in MESSAGES]
                self.assertNotIn(-1, at, f"{n}:{jn}: a settled message is missing")
                self.assertEqual(at, sorted(at), f"{n}:{jn}: messages out of the settled order")
                self.assertEqual(g["run"].count("::error::"), 4, f"{n}:{jn}")

    def test_guard_body_is_byte_identical_in_every_occurrence(self):
        bodies = {f"{n}:{jn}": g.get("run") for n in wf.RELEASE_NAMES for jn, g in guards(n)}
        self.assertEqual(len(bodies), 9)
        self.assertEqual(len(set(bodies.values())), 1, "guard bodies differ")


class DocTests(unittest.TestCase):
    def test_doc_states_the_least_privilege_consequence_of_token_mode(self):
        doc = " ".join((wf.ROOT / "docs" / "release-flow.md").read_text().split())
        for fragment in ("**Least privilege.**", "gets none of our narrowing",
                         "Its scope is the caller's responsibility", "App mode stays the least-privilege option"):
            self.assertIn(fragment, doc)


if __name__ == "__main__":
    unittest.main()
