#!/usr/bin/env python3
"""Self-test for `run:` step bodies that shellcheck can lint but cannot execute.

TODO.md records the gap this closes: actionlint/shellcheck accept a step body
that is wrong at *runtime* (the Summary-step AND-list bug shipped that way), and
nothing in CI ever ran one. This runner extracts a named step's `run:` script
straight out of the workflow YAML and executes it under `bash -eo pipefail`
(GitHub's `shell: bash`) against stubbed commands. There is no copy to drift.

Covered today: promote-image's "Wait for source image" poll — the CI→CD handoff
guard, whose failure mode is either a release that gives up too early or a job
that burns its whole timeout.

Time is faked: `sleep N` advances a clock file and `date +%s` reads it, so the
backoff schedule is asserted exactly and the suite runs instantly.

Usage:  python3 tests/run_step_tests.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROMOTE = ROOT / ".github" / "workflows" / "promote-image.yml"

FAILURES = []


def extract_step(workflow: Path, job: str, step_name: str) -> str:
    """Return the `run:` body of a named step, as shipped."""
    doc = yaml.safe_load(workflow.read_text())
    for step in doc["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            if "run" not in step:
                raise SystemExit(f"step '{step_name}' has no run: body")
            return step["run"]
    raise SystemExit(f"step '{step_name}' not found in {workflow.name}:{job}")


def run_wait_step(body: str, *, wait_seconds: int, appear_at_attempt: int | None):
    """Execute the poll body with a fake clock and a stubbed gcloud.

    appear_at_attempt: 1-based probe number at which `describe` starts
    succeeding; None = never.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub_dir = tmp / "bin"
        stub_dir.mkdir()
        clock = tmp / "clock"
        clock.write_text("1000000000\n")
        attempts = tmp / "attempts"
        attempts.write_text("")
        sleeps = tmp / "sleeps"
        sleeps.write_text("")

        # `sleep N` advances the fake clock instead of blocking.
        (stub_dir / "sleep").write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$1" >> "{sleeps}"\n'
            f'now=$(cat "{clock}")\n'
            f'echo $(( now + ${{1%%.*}} )) > "{clock}"\n'
        )
        (stub_dir / "date").write_text(
            "#!/usr/bin/env bash\n"
            f'if [ "$1" = "+%s" ]; then cat "{clock}"; else /bin/date "$@"; fi\n'
        )
        appear = "" if appear_at_attempt is None else str(appear_at_attempt)
        (stub_dir / "gcloud").write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$*" >> "{attempts}"\n'
            f'n=$(wc -l < "{attempts}")\n'
            f'appear="{appear}"\n'
            'if [ -n "$appear" ] && [ "$n" -ge "$appear" ]; then exit 0; fi\n'
            "exit 1\n"
        )
        for f in stub_dir.iterdir():
            f.chmod(0o755)

        env = dict(os.environ)
        env["PATH"] = f"{stub_dir}:{env['PATH']}"
        env["SOURCE"] = "us-docker.pkg.dev/p/r/img:deadbeef"
        env["WAIT_SECONDS"] = str(wait_seconds)

        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            env=env, capture_output=True, text=True,
        )
        return {
            "rc": proc.returncode,
            "out": proc.stdout + proc.stderr,
            "attempts": len([l for l in attempts.read_text().splitlines() if l]),
            "sleeps": [int(s) for s in sleeps.read_text().split()],
            "elapsed": int(clock.read_text()) - 1000000000,
        }


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


def main():
    body = extract_step(PROMOTE, "promote", "Wait for source image")
    print("promote-image · Wait for source image")

    # 1. Already built: one probe, no sleeping, no wasted runner minutes.
    r = run_wait_step(body, wait_seconds=900, appear_at_attempt=1)
    check("present on first probe exits 0", r["rc"] == 0, r["out"])
    check("present on first probe probes once", r["attempts"] == 1, r["attempts"])
    check("present on first probe never sleeps", r["sleeps"] == [], r["sleeps"])

    # 2. The race itself: build lands mid-poll. Backoff doubles from 10, caps 30.
    r = run_wait_step(body, wait_seconds=900, appear_at_attempt=6)
    check("image appearing mid-poll exits 0", r["rc"] == 0, r["out"])
    check("polls until it appears", r["attempts"] == 6, r["attempts"])
    check("backoff is 10,20,30,30,30", r["sleeps"] == [10, 20, 30, 30, 30], r["sleeps"])

    # 3. Build never produced it: fail with an actionable message, not a hang.
    r = run_wait_step(body, wait_seconds=100, appear_at_attempt=None)
    check("never appears exits 1", r["rc"] == 1, r["out"])
    check("never appears names the image", "img:deadbeef" in r["out"], r["out"])
    check("never appears names the budget", "100s" in r["out"], r["out"])
    check("never appears points at the build run", "build for this commit" in r["out"], r["out"])
    check("no sleep exceeds the 30s cap", all(s <= 30 for s in r["sleeps"]), r["sleeps"])
    check("does not overshoot the budget", r["elapsed"] <= 100, r["elapsed"])
    check("spends the budget it was given", r["elapsed"] == 100, r["elapsed"])
    # Probe-then-deadline ordering: the budget must buy a final check.
    check("probes once more than it sleeps", r["attempts"] == len(r["sleeps"]) + 1,
          (r["attempts"], r["sleeps"]))

    # 4. Degenerate budget: still exactly one probe, no negative sleep.
    r = run_wait_step(body, wait_seconds=1, appear_at_attempt=None)
    check("1s budget probes twice", r["attempts"] == 2, r["attempts"])
    check("1s budget clamps the sleep", r["sleeps"] == [1], r["sleeps"])

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
