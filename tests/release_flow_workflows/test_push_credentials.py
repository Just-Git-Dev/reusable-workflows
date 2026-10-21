"""A `git push` after a credential-less checkout must bring its own token — every workflow here.

`persist-credentials: false` (zizmor's artipacked fix) leaves no auth on the clone, so a later
plain `git push` dies with "could not read Username". That is how the v4.0.0 release run
39588229527 failed: #146 added the flag to release.yml's checkout and no test noticed, because
nothing runs release.yml before a release. So: any step that runs `git push` in a job whose
checkout does not persist credentials must take a token through its own `env:` and use it.
"""
import re
import unittest

import wf

PUSH = re.compile(r"\bgit\b[^\n]*\bpush\b")


class PushCredentialTests(unittest.TestCase):
    def test_push_after_credentialless_checkout_supplies_a_token(self):
        examined = 0
        for f in sorted(wf.WORKFLOWS_DIR.glob("*.yml")):
            for jn, job in (wf.load(f.name).get("jobs") or {}).items():
                steps = job.get("steps") or []
                bare = any("actions/checkout@" in (s.get("uses") or "")
                           and (s.get("with") or {}).get("persist-credentials") is False
                           for s in steps)
                for s in steps:
                    run = (s.get("run") or "").replace("\\\n", " ")  # join `\` continuations
                    if not (bare and PUSH.search(run)):
                        continue
                    examined += 1
                    env = s.get("env") or {}
                    tokens = [k for k, v in env.items() if "token" in str(v).lower()]
                    self.assertTrue(tokens, f"{f.name}:{jn}: `git push` with no token in env")
                    self.assertTrue(any(f"${k}" in run or f"${{{k}}}" in run for k in tokens),
                                    f"{f.name}:{jn}: push step never uses its token")
        # release.yml's tag push is the known case; finding none means the scan is broken.
        self.assertGreaterEqual(examined, 1, "no push-after-bare-checkout step examined")


if __name__ == "__main__":
    unittest.main()
