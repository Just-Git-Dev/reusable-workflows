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

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROMOTE = ROOT / ".github" / "workflows" / "promote-image.yml"
CI_NODE = ROOT / ".github" / "workflows" / "ci-node.yml"
CI_GO = ROOT / ".github" / "workflows" / "ci-go.yml"
GAR = ROOT / ".github" / "workflows" / "cleanup-gar-images.yml"
PAGES = ROOT / ".github" / "workflows" / "deploy-cloudflare-pages.yml"

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


def run_badge_push_step(body: str, *, push_mode: str, has_changes: bool = True):
    """Execute the badge Commit + push body against a stubbed git.

    push_mode: 'ok'          push succeeds first time
               'denied'      remote rejects for permissions (read-only token)
               'transient'   first push rejected (non-fast-forward), retry succeeds
               'hard'        both attempts fail for a non-permission reason
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub_dir = tmp / "bin"
        stub_dir.mkdir()
        pushes = tmp / "pushes"
        pushes.write_text("")
        pulls = tmp / "pulls"
        pulls.write_text("")

        git = stub_dir / "git"
        git.write_text(f"""#!/usr/bin/env bash
case "$1" in
  diff)   exit {0 if not has_changes else 1} ;;
  config|add|commit) exit 0 ;;
  pull)   echo x >> {pulls} ; exit 0 ;;
  push)
    echo x >> {pushes}
    n=$(wc -l < {pushes} | tr -d ' ')
    case "{push_mode}" in
      ok)        exit 0 ;;
      denied)    echo "remote: Permission to o/r.git denied to github-actions[bot]" >&2
                 echo "fatal: unable to access: The requested URL returned error: 403" >&2
                 exit 128 ;;
      transient) if [ "$n" -ge 2 ]; then exit 0; fi
                 echo "! [rejected] main -> main (non-fast-forward)" >&2 ; exit 1 ;;
      hard)      echo "fatal: the remote end hung up unexpectedly" >&2 ; exit 128 ;;
    esac ;;
esac
exit 0
""")
        git.chmod(0o755)
        readme = tmp / "README.md"
        readme.write_text("# t\n")

        env = dict(os.environ)
        env["PATH"] = f"{stub_dir}:{env['PATH']}"
        env["README"] = str(readme)
        env["BRANCH"] = "main"
        env["RUNNER_TEMP"] = str(tmp)

        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {
            "rc": proc.returncode,
            "out": proc.stdout + proc.stderr,
            "pushes": len(pushes.read_text().split()),
            "pulls": len(pulls.read_text().split()),
        }


def run_coverage_step(body: str, *, summary_pct=None, threshold=0):
    """Execute the ci-node Coverage body. summary_pct=None ⇒ no report on disk."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        summary = tmp / "coverage-summary.json"
        if summary_pct is not None:
            summary.write_text(json.dumps({"total": {"lines": {"pct": summary_pct}}}))
        out = tmp / "gh_output"
        out.write_text("")
        env = dict(os.environ)
        env.update(SUMMARY=str(summary), COVERAGE_THRESHOLD=str(threshold),
                   GITHUB_OUTPUT=str(out))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "output": out.read_text()}


def run_relock_step(body: str, *, relock="true", update_ok=True, readback="true"):
    """Execute the GAR relock body against a stubbed gcloud.

    update_ok: does `repositories update --immutable-tags` succeed
    readback:  what `describe` reports afterwards ("true" = protected again)
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        calls = tmp / "calls"
        calls.write_text("")
        gcloud = stub / "gcloud"
        gcloud.write_text(f"""#!/usr/bin/env bash
echo "$@" >> {calls}
case "$*" in
  *"--immutable-tags"*) exit {0 if update_ok else 1} ;;
  *describe*)           echo "{readback}" ; exit 0 ;;
esac
exit 0
""")
        gcloud.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(RELOCK=relock, GCP_PROJECT="p", GCP_REGION="r", GAR_REPO="repo")
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "calls": calls.read_text()}


def run_smoke_step(body: str, *, base="https://x.pages.dev", path="/", expect="",
                   want="200", attempts=3, statuses=None, bodies=None):
    """Execute the Pages smoke body against a stubbed curl.

    statuses/bodies: per-attempt responses, last value repeats.
    """
    statuses = statuses or ["200"]
    bodies = bodies or ["<div id=\"root\"></div>"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"; stub.mkdir()
        n = tmp / "n"; n.write_text("0")
        (stub / "curl").write_text(f"""#!/usr/bin/env bash
i=$(cat {n}); i=$((i+1)); echo "$i" > {n}
statuses=({" ".join(statuses)})
idx=$((i-1)); last=$(( ${{#statuses[@]}} - 1 )); [ $idx -gt $last ] && idx=$last
# -o <file> is the 3rd arg in the shipped invocation
out=""; prev=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done
bodies_dir={tmp}/bodies
cp "$bodies_dir/$((idx+1))" "$out" 2>/dev/null || cp "$bodies_dir/$(ls $bodies_dir | tail -1)" "$out"
echo -n "${{statuses[$idx]}}"
""")
        (stub / "curl").chmod(0o755)
        (stub / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")  # no real waiting
        (stub / "sleep").chmod(0o755)
        bd = tmp / "bodies"; bd.mkdir()
        for i, b in enumerate(bodies, 1):
            (bd / str(i)).write_text(b)
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(BASE=base, SMOKE_PATH=path, EXPECT=expect, WANT=want,
                   ATTEMPTS=str(attempts), INTERVAL="1", RUNNER_TEMP=str(tmp),
                   GITHUB_STEP_SUMMARY=str(tmp / "summary"))
        proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                              capture_output=True, text=True, env=env, cwd=tmp)
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "attempts": int(n.read_text().strip() or 0)}


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

    # ---- badge push: must never fail a caller's CI over a cosmetic README ----
    node_body = extract_step(CI_NODE, "badges", "Commit + push")
    go_body = extract_step(CI_GO, "badges", "Commit + push")
    print("\nci-node / ci-go · badges · Commit + push")
    check("ci-node and ci-go bodies are identical", node_body == go_body,
          "the two must not drift")

    r = run_badge_push_step(node_body, push_mode="ok")
    check("successful push exits 0", r["rc"] == 0, r["out"])
    check("successful push pushes once", r["pushes"] == 1, r["pushes"])
    check("successful push emits no warning", "::warning::" not in r["out"], r["out"])

    # The default-on case that must not break anyone: caller granted only read.
    r = run_badge_push_step(node_body, push_mode="denied")
    check("read-only token exits 0", r["rc"] == 0, r["out"])
    check("read-only token warns", "::warning::" in r["out"], r["out"])
    check("read-only token names the fix", "contents: write" in r["out"], r["out"])
    check("read-only token offers the opt-out", "update_badges" in r["out"], r["out"])
    check("read-only token does not retry", r["pulls"] == 0, r["pulls"])

    r = run_badge_push_step(node_body, push_mode="transient")
    check("race with a concurrent push rebases once", r["pulls"] == 1, r["pulls"])
    check("race retry succeeds", r["rc"] == 0, r["out"])

    # Contract changed 2026-08-11 (hard-error audit): this used to assert exit 1 on a
    # push failure that is not a permission problem. That was opt-in-era semantics left
    # in place when badges went default-on in v1.21.0 — it fails the CI of a caller who
    # never asked for badges, over a cosmetic README commit. The error must still be
    # SURFACED; it must not gate the build.
    r = run_badge_push_step(node_body, push_mode="hard")
    check("genuine failure exits 0 (cosmetic feature, default-on)", r["rc"] == 0, r["out"])
    check("genuine failure surfaces the error", "hung up unexpectedly" in r["out"], r["out"])
    check("genuine failure warns", "::warning::" in r["out"], r["out"])
    check("genuine failure offers the opt-out", "update_badges" in r["out"], r["out"])

    r = run_badge_push_step(node_body, push_mode="ok", has_changes=False)
    check("no README change pushes nothing", r["pushes"] == 0, r["pushes"])
    check("no README change exits 0", r["rc"] == 0, r["out"])

    # ---- coverage: badges are on by default, so a missing report must not fail
    # a caller who never asked for a gate. Regression from v1.21.0, caught by
    # Traide-Co/webapp (vitest without --coverage). ----
    cov = extract_step(CI_NODE, "node", "Coverage")
    print("\nci-node · Coverage")

    r = run_coverage_step(cov, summary_pct=None, threshold=0)
    check("missing report without a gate exits 0", r["rc"] == 0, r["out"])
    check("missing report without a gate warns", "::warning::" in r["out"], r["out"])
    check("missing report without a gate names the reporter flag",
          "json-summary" in r["out"], r["out"])
    check("missing report without a gate sets no coverage output",
          "coverage=" not in r["output"], r["output"])

    r = run_coverage_step(cov, summary_pct=None, threshold=80)
    check("missing report WITH a gate exits 1", r["rc"] == 1, r["out"])
    check("missing report WITH a gate says why", "coverage_threshold is 80" in r["out"], r["out"])

    r = run_coverage_step(cov, summary_pct=83.5, threshold=0)
    check("report present exits 0", r["rc"] == 0, r["out"])
    check("report present emits the value", "coverage=83.5" in r["output"], r["output"])

    r = run_coverage_step(cov, summary_pct=50, threshold=80)
    check("below threshold exits 1", r["rc"] == 1, r["out"])
    check("below threshold names both numbers",
          "50%" in r["out"] and "80%" in r["out"], r["out"])

    r = run_coverage_step(cov, summary_pct=90, threshold=80)
    check("above threshold exits 0", r["rc"] == 0, r["out"])

    # ---- fleet drift: pure classification logic, no network ----
    sys.path.insert(0, str(ROOT / "scripts"))
    import fleet_drift as fd
    print("\nfleet_drift · pin classification")
    check("exact latest is current", fd.minors_behind("v1.21.1", "v1.21.1") == 0)
    check("two minors behind", fd.minors_behind("v1.19.0", "v1.21.1") == 2)
    check("six minors behind", fd.minors_behind("v1.15.0", "v1.21.1") == 6)
    check("a major behind is maximal", fd.minors_behind("v0.9.0", "v1.21.1") == 99)
    check("@main is not a release", fd.minors_behind("main", "v1.21.1") is None)
    check("@v1 alias is not a release", fd.minors_behind("v1", "v1.21.1") is None)
    check("a SHA pin is not a release", fd.minors_behind("3d60a0d", "v1.21.1") is None)
    rows = fd.classify([
        {"repo": "o/a", "file": "ci.yml", "workflow": "ci-node", "ref": "v1.21.1"},
        {"repo": "o/b", "file": "d.yml", "workflow": "promote-image", "ref": "v1"},
        {"repo": "o/c", "file": "d.yml", "workflow": "cleanup-gar-images", "ref": "v1.15.0"},
    ], "v1.21.1", 1)
    check("classifies OK / MUTABLE / STALE",
          [r["status"] for r in rows] == ["OK", "MUTABLE", "STALE"],
          [r["status"] for r in rows])
    md = fd.render_md(rows, "v1.21.1")
    check("markdown lists only the problems", md.count("| MUTABLE |") == 1 and md.count("| STALE |") == 1)
    check("markdown omits healthy pins", "o/a" not in md)
    check("clean fleet renders a clean report",
          "are current" in fd.render_md([{"repo": "o/a", "file": "c", "workflow": "w",
                                          "ref": "v1.21.1", "status": "OK", "detail": ""}], "v1.21.1"))
    # ---- GAR relock: the repo must end the run as protected as it started ----
    relock = extract_step(GAR, "cleanup", "Relock immutable tags")
    print("\ncleanup-gar-images · Relock immutable tags")

    r = run_relock_step(relock)
    check("happy path exits 0", r["rc"] == 0, r["out"])
    check("happy path re-enables", "--immutable-tags" in r["calls"], r["calls"])
    check("happy path verifies by readback", "describe" in r["calls"], r["calls"])

    # The dangerous case: gcloud says OK but the repo is still unlocked.
    r = run_relock_step(relock, update_ok=True, readback="false")
    check("unlocked-after-relock FAILS the job", r["rc"] == 1, r["out"])
    check("unlocked-after-relock says UNLOCKED", "UNLOCKED" in r["out"], r["out"])
    check("unlocked-after-relock gives the fix command",
          "--immutable-tags" in r["out"], r["out"])

    # Trust the readback, not the exit code: update fails but repo is protected.
    r = run_relock_step(relock, update_ok=False, readback="true")
    check("readback wins over a failed update", r["rc"] == 0, r["out"])

    r = run_relock_step(relock, update_ok=False, readback="false")
    check("genuine relock failure exits 1", r["rc"] == 1, r["out"])

    # Opt-out: warn loudly, change nothing, do not fail.
    r = run_relock_step(relock, relock="false")
    check("opt-out exits 0", r["rc"] == 0, r["out"])
    check("opt-out warns it is left unlocked", "LEFT UNLOCKED" in r["out"], r["out"])
    check("opt-out touches nothing", r["calls"].strip() == "", r["calls"])

    # ---- Pages smoke check: a green deploy is not a working site ----
    smoke = extract_step(PAGES, "deploy", "Smoke check")
    print("\ndeploy-cloudflare-pages · Smoke check")

    r = run_smoke_step(smoke)
    check("healthy first response passes", r["rc"] == 0, r["out"])
    check("healthy first response stops at one request", r["attempts"] == 1, r["attempts"])

    # Pages is eventually consistent: a 404 then a 200 must not fail the deploy.
    r = run_smoke_step(smoke, statuses=["404", "404", "200"], attempts=5)
    check("retries through propagation", r["rc"] == 0, r["out"])
    check("stops as soon as it is healthy", r["attempts"] == 3, r["attempts"])

    r = run_smoke_step(smoke, statuses=["500"], attempts=3)
    check("persistent bad status fails", r["rc"] == 1, r["out"])
    check("persistent bad status exhausts attempts", r["attempts"] == 3, r["attempts"])
    check("failure names the URL", "https://x.pages.dev/" in r["out"], r["out"])

    # The outage case: 200, but the wrong bundle is being served.
    r = run_smoke_step(smoke, expect='<title>RealmID</title>',
                       bodies=["<div id=\"root\"></div>"], attempts=2)
    check("200 with a missing marker FAILS", r["rc"] == 1, r["out"])
    check("missing marker is named", "RealmID" in r["out"], r["out"])

    r = run_smoke_step(smoke, expect='id="root"\n<title>RealmID</title>',
                       bodies=['<div id="root"></div><title>RealmID</title>'])
    check("all markers present passes", r["rc"] == 0, r["out"])

    r = run_smoke_step(smoke, base="", attempts=1)
    check("no URL to test fails clearly", r["rc"] == 1, r["out"])
    check("no URL explains why", "no deployment URL" in r["out"], r["out"])

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
