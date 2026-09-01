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
RETIRE = ROOT / ".github" / "workflows" / "retire-gar-packages.yml"
PAGES = ROOT / ".github" / "workflows" / "deploy-cloudflare-pages.yml"
SYNC = ROOT / ".github" / "workflows" / "sync-bundle-key.yml"
KEYPAIR = ROOT / ".github" / "workflows" / "rotate-signing-keypair.yml"
WORKER = ROOT / ".github" / "workflows" / "rotate-worker-signing-secret.yml"
SWEEP = ROOT / ".github" / "workflows" / "cleanup-secret-versions.yml"
CFWORKER = ROOT / ".github" / "workflows" / "deploy-cloudflare-worker.yml"
CFSERVICE = ROOT / ".github" / "workflows" / "bootstrap-cf-service.yml"
CFDNS = ROOT / ".github" / "workflows" / "bootstrap-cf-dns.yml"
CRUPDATE = ROOT / ".github" / "workflows" / "cloud-run-update.yml"
ALERTS = ROOT / ".github" / "workflows" / "validate-alerts.yml"

# The three writers that add a bundle version, and the job each does it in.
WRITERS = [(SYNC, "sync"), (KEYPAIR, "rotate"), (WORKER, "rotate")]
DISABLE_STEP = "Disable superseded bundle version(s)"

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


def run_relock_step(body: str, *, policy="enforce", started="true", can_update="true",
                    update_ok=True, readback="true"):
    """Execute the GAR end-state body against a stubbed gcloud.

    policy:     resolved immutable_tags_policy (enforce | preserve | unlock)
    started:    was the repository immutable BEFORE the sweep
    can_update: did the permission pre-flight pass
    update_ok:  does `repositories update --immutable-tags` succeed
    readback:   what `describe` reports afterwards ("true" = protected)
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
        env.update(POLICY=policy, STARTED=started, CAN_UPDATE=can_update,
                   GCP_PROJECT="p", GCP_REGION="r", GAR_REPO="repo")
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "calls": calls.read_text()}


def run_exec_step(body: str, *, degraded="false"):
    """Execute the deletion body against a stubbed gcloud, with a 2-tagged /
    2-untagged plan. Returns which images gcloud was actually asked to delete."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        deleted = tmp / "deleted"
        deleted.write_text("")
        gcloud = stub / "gcloud"
        gcloud.write_text(f'#!/usr/bin/env bash\nfor a in "$@"; do case "$a" in *@sha256:*) '
                          f'echo "$a" >> {deleted} ;; esac; done\nexit 0\n')
        gcloud.chmod(0o755)
        plan = {"to_delete": [
            {"image": "r/img@sha256:t1", "tags": ["v1.0.0"]},
            {"image": "r/img@sha256:t2", "tags": ["v1.1.0"]},
            {"image": "r/img@sha256:u1", "tags": []},
            {"image": "r/img@sha256:u2", "tags": []},
        ]}
        (tmp / "delete-plan.json").write_text(json.dumps(plan))
        out = tmp / "gh_output"
        out.write_text("")
        summary = tmp / "gh_summary"
        summary.write_text("")
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(DEGRADED=degraded, GCP_PROJECT="p", GITHUB_OUTPUT=str(out),
                   GITHUB_STEP_SUMMARY=str(summary))
        # the step reads /tmp/delete-plan.json; point it at the fixture
        body = body.replace("/tmp/delete-plan.json", str(tmp / "delete-plan.json"))
        body = body.replace("/tmp/exec.log", str(tmp / "exec.log"))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "deleted": deleted.read_text().split(),
                "output": out.read_text(), "summary": summary.read_text()}


def run_perm_step(body: str, *, started="true", granted=True):
    """Execute the immutability permission pre-flight against a stubbed curl.

    granted: does :testIamPermissions echo the permission back
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        body_json = ('{"permissions":["artifactregistry.repositories.update"]}'
                     if granted else "{}")
        for name, script in {
            "curl": f'#!/usr/bin/env bash\necho \'{body_json}\'\n',
            "gcloud": '#!/usr/bin/env bash\necho token\n',
        }.items():
            p = stub / name
            p.write_text(script)
            p.chmod(0o755)
        out = tmp / "gh_output"
        out.write_text("")
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(STARTED=started, GCP_PROJECT="p", GCP_REGION="r", GAR_REPO="repo",
                   GITHUB_OUTPUT=str(out))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "output": out.read_text()}


def run_immutable_step(body: str, *, state="true", describe_ok=True):
    """Execute the immutability detector against a stubbed `repositories describe`.

    state:       what `--format=value(dockerConfig.immutableTags)` prints
    describe_ok: does describe succeed at all (a denied/missing repo prints
                 nothing and exits non-zero, which must read as NOT locked
                 rather than taking the step down)
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        gcloud = stub / "gcloud"
        gcloud.write_text("#!/usr/bin/env bash\n"
                          + (f'echo "{state}"\nexit 0\n' if describe_ok else "exit 1\n"))
        gcloud.chmod(0o755)
        out = tmp / "gh_output"
        out.write_text("")
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(GCP_PROJECT="p", GCP_REGION="r", GAR_REPO="repo",
                   GITHUB_OUTPUT=str(out))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "output": out.read_text()}


def run_retire_exec_step(body: str, *, fail_with=None):
    """Execute the package-retirement body against a stubbed gcloud.

    fail_with: stderr text `packages delete` fails with (None = it succeeds).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        deleted = tmp / "deleted"
        deleted.write_text("")
        gcloud = stub / "gcloud"
        if fail_with is None:
            gcloud.write_text(f'#!/usr/bin/env bash\necho "$*" >> {deleted}\nexit 0\n')
        else:
            gcloud.write_text(f'#!/usr/bin/env bash\necho "{fail_with}" >&2\nexit 1\n')
        gcloud.chmod(0o755)
        retire_list = tmp / "retire.txt"
        retire_list.write_text("dead-svc\n")
        out = tmp / "gh_output"
        out.write_text("")
        summary = tmp / "gh_summary"
        summary.write_text("")
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(GCP_PROJECT="p", GCP_REGION="r", GAR_REPO="repo",
                   GITHUB_OUTPUT=str(out), GITHUB_STEP_SUMMARY=str(summary))
        body = body.replace("/tmp/retire.txt", str(retire_list))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "deleted": deleted.read_text(), "output": out.read_text()}


def run_cleanup_latest_step(body: str, *, dry_run="true", degraded="false",
                            policy="enforce", started="false", existing=("latest",),
                            packages=("host/p/repo/api",)):
    """Execute the stranded-:latest cleanup against a stubbed gcloud.

    existing: the tags that actually exist on every package. Matching must be
    EXACT — a repo carrying `latest-rc` but not `latest` has nothing to clean.
    Returns every gcloud call, so a dry run can be asserted to make none.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        calls = tmp / "calls"
        calls.write_text("")
        # `tags list --format=value(tag,version)` emits TAB-separated rows.
        rows = "".join(f'  printf "%s\\t%s\\n" "{t}" "sha256:dead{i}"\n'
                       for i, t in enumerate(existing))
        gcloud = stub / "gcloud"
        gcloud.write_text(
            '#!/usr/bin/env bash\n'
            f'echo "$*" >> {calls}\n'
            'if [ "$3" = "tags" ] && [ "$4" = "list" ]; then\n'
            f'{rows}'
            '  exit 0\n'
            'fi\n'
            'exit 0\n')
        gcloud.chmod(0o755)
        # The step reads the package list off the plan the sweep already built.
        plan = {"per_package": {p: {"total": 3, "delete": 1} for p in packages}}
        (tmp / "delete-plan.json").write_text(json.dumps(plan))
        out = tmp / "gh_output"
        out.write_text("")
        summary = tmp / "gh_summary"
        summary.write_text("")
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(DEGRADED=degraded, POLICY=policy, STARTED=started, DRY_RUN=dry_run,
                   GCP_PROJECT="p", GCP_REGION="r", GAR_REPO="repo",
                   SERVICE_ACCOUNT="sa@p.iam.gserviceaccount.com",
                   GITHUB_OUTPUT=str(out), GITHUB_STEP_SUMMARY=str(summary))
        body = body.replace("/tmp/delete-plan.json", str(tmp / "delete-plan.json"))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        text = calls.read_text()
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "calls": text,
                "deletes": [ln for ln in text.splitlines() if "tags delete" in ln],
                "output": out.read_text(), "summary": summary.read_text()}


def run_disable_keep_step(body: str, *, keep="1", enabled=("7", "6"),
                          disable_fails=False):
    """Execute a writer's keep-set disable body against a stubbed gcloud.

    enabled: the ENABLED version names as `versions list --sort-by=~createTime`
    returns them — NEWEST FIRST. The newest must never appear in the disable
    set: `latest` resolves server-side to it, so disabling it is a silent live
    rollback (DECISIONS.md 2026-08-16).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        calls = tmp / "calls"
        calls.write_text("")
        rows = "".join(f'  echo "{v}"\n' for v in enabled)
        gcloud = stub / "gcloud"
        gcloud.write_text(
            '#!/usr/bin/env bash\n'
            f'echo "$*" >> {calls}\n'
            'if [ "$2" = "versions" ] && [ "$3" = "list" ]; then\n'
            f'{rows}'
            '  exit 0\n'
            'fi\n'
            'if [ "$2" = "versions" ] && [ "$3" = "disable" ]; then\n'
            f'  exit {1 if disable_fails else 0}\n'
            'fi\n'
            'exit 0\n')
        gcloud.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(KEEP_ENABLED_COUNT=keep, BUNDLE_SECRET="app-secrets",
                   GCP_PROJECT="p",
                   GITHUB_STEP_SUMMARY=str(tmp / "summary"))
        # Keep the scratch lists inside the sandbox rather than the real /tmp.
        body = body.replace("/tmp/", f"{tmp}/")
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        text = calls.read_text()
        # `--secret=` / `--project=` trail the version, so pull the positional arg.
        disabled = [ln.split()[3] for ln in text.splitlines()
                    if "versions disable" in ln]
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "calls": text, "disabled": disabled,
                "destroys": [ln for ln in text.splitlines()
                             if "versions destroy" in ln]}


def run_policy_step(body: str, *, policy_in="enforce", relock_in="true", keep_tags=""):
    """Execute the policy resolver, which folds the deprecated boolean in."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "gh_output"
        out.write_text("")
        env = dict(os.environ)
        env.update(POLICY_IN=policy_in, RELOCK_IN=relock_in, KEEP_TAGS=keep_tags,
                   GITHUB_OUTPUT=str(out))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "output": out.read_text()}


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


def run_collect_targets_step(body: str, *, secrets_list="", can_list=True,
                             existing=("app-secrets",)):
    """Execute cleanup-secret-versions' "Collect target secrets" against a stubbed gcloud.

    can_list: does project-level `gcloud secrets list` succeed? A caller holding only
              resource-scoped grants on the secrets it named cannot list the project,
              and must still be able to run a sweep it named explicitly.
    existing: which secret names `gcloud secrets describe` accepts.

    The step writes to absolute /tmp paths (they are runner paths in production); the
    body is rewritten to the case's tempdir so cases cannot bleed into each other.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        gcloud = stub / "gcloud"
        gcloud.write_text(
            "#!/usr/bin/env bash\n"
            'if [ "$1 $2" = "secrets list" ]; then\n'
            + ("  printf '%s\\n' " + " ".join(f"'{n}'" for n in existing) + "\n  exit 0\n"
               if can_list else
               '  echo "PERMISSION_DENIED: secretmanager.secrets.list" >&2\n  exit 1\n')
            + 'fi\n'
            'if [ "$1 $2" = "secrets describe" ]; then\n'
            '  case " ' + " ".join(existing) + ' " in *" $3 "*) exit 0;; esac\n'
            '  echo "NOT_FOUND: $3" >&2; exit 1\n'
            'fi\n'
            'exit 0\n'
        )
        gcloud.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(GCP_PROJECT="p", SECRETS_LIST=secrets_list)
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
             body.replace("/tmp/", f"{tmp}/")],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        targets = (tmp / "targets.txt")
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "targets": targets.read_text().split() if targets.exists() else []}


def _git(cwd, *args):
    # -c overrides, not inherited config: a developer with `tag.annotate=true` set globally
    # would otherwise get "fatal: no tag message?" from the plain `git tag` below, and the
    # suite would fail on their machine for a reason that has nothing to do with the step.
    subprocess.run(["git", "-c", "tag.annotate=false", "-c", "tag.gpgSign=false",
                    "-c", "commit.gpgSign=false", *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


def run_worker_changed_step(body: str, *, watch_paths, history, ref):
    """Execute deploy-cloudflare-worker's change-skip against a REAL git repo.

    The step's whole job is a `git diff` between two tags, so stubbing git would test the
    stub. `history` is [(tag, {path: contents}), ...] applied in order; `ref` is the tag
    being deployed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _git(tmp, "init", "-q", "-b", "main")
        _git(tmp, "config", "user.email", "t@t")
        _git(tmp, "config", "user.name", "t")
        for tag, files in history:
            for rel, content in files.items():
                f = tmp / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(content)
            _git(tmp, "add", "-A")
            _git(tmp, "commit", "-q", "--allow-empty", "-m", tag)
            _git(tmp, "tag", tag)
        env = dict(os.environ)
        env.update(WATCH_PATHS=watch_paths, REF=ref,
                   GITHUB_OUTPUT=str(tmp / "out.txt"))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        out = (tmp / "out.txt")
        outs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l) \
            if out.exists() else {}
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr, "skip": outs.get("skip")}


def run_worker_deploy_step(body: str, *, version="", env_name="", dry_run="false"):
    """Execute the wrangler invocation against a stubbed npx that records its argv."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        npx = stub / "npx"
        npx.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" > "$ARGV_FILE"\nexit 0\n')
        npx.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(WRANGLER_VERSION=version, WRANGLER_ENV=env_name, DRY_RUN=dry_run,
                   ARGV_FILE=str(tmp / "argv.txt"),
                   CLOUDFLARE_API_TOKEN="t", CLOUDFLARE_ACCOUNT_ID="a")
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        argv = (tmp / "argv.txt")
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr,
                "argv": argv.read_text().strip() if argv.exists() else ""}


def run_worker_resolve_step(body: str, *, ref_in="", require="false",
                            fallback="main", name_in="", worker_dir="cf-worker"):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = dict(os.environ)
        env.update(REF_IN=ref_in, REQUIRE_SEMVER=require, FALLBACK_REF=fallback,
                   WORKER_NAME_IN=name_in, WORKER_DIR=worker_dir,
                   GITHUB_OUTPUT=str(tmp / "out.txt"))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        out = (tmp / "out.txt")
        outs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l) \
            if out.exists() else {}
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr, **outs}


def _run_body(body, env_extra, *, stubs=None):
    """Run a step body under `shell: bash` with optional stub executables on PATH."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = dict(os.environ)
        if stubs:
            bin_ = tmp / "bin"
            bin_.mkdir()
            for name, script in stubs.items():
                f = bin_ / name
                f.write_text(script)
                f.chmod(0o755)
            env["PATH"] = f"{bin_}:{env['PATH']}"
        env.update({k: str(v) for k, v in env_extra.items()})
        env["GITHUB_OUTPUT"] = str(tmp / "out.txt")
        env["GITHUB_ENV"] = str(tmp / "env.txt")
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        res = {"rc": proc.returncode, "out": proc.stdout + proc.stderr}
        for key, fn in (("outputs", "out.txt"), ("env", "env.txt")):
            f = tmp / fn
            res[key] = dict(l.split("=", 1) for l in f.read_text().splitlines()
                            if "=" in l) if f.exists() else {}
        return res


def run_cf_validate_step(body, **kw):
    env = {"MODE": "", "SERVICE": "", "RUN_URL": "", "WIF": "", "SA": "", "PROJECT": ""}
    env.update({k.upper(): v for k, v in kw.items()})
    return _run_body(body, env)


def run_cf_runurl_step(body, *, run_url="", service="svc", live_url="https://svc-x-as.a.run.app"):
    gcloud = ('#!/usr/bin/env bash\n'
              + (f'printf "%s\\n" "{live_url}"\n' if live_url else '')
              + 'exit 0\n')
    return _run_body(body,
                     {"RUN_URL": run_url, "SERVICE": service,
                      "REGION": "r", "PROJECT": "p"},
                     stubs={"gcloud": gcloud})


def run_cf_originrule_step(body, *, existing_rules=None, ruleset_exists=True,
                           host="img.example.com", run_url="svc-new-as.a.run.app",
                           dry="false"):
    """Drive the Origin Rule splice against a stubbed Cloudflare API.

    The stub records the PUT/POST body so the test can assert what would actually be sent —
    the splice is read-modify-write of the whole zone entrypoint, so a mistake silently
    deletes other people's rules rather than erroring.
    """
    if existing_rules is None:
        existing_rules = []
    get_payload = json.dumps({"success": ruleset_exists,
                              "result": {"rules": existing_rules}})
    curl = (
        '#!/usr/bin/env bash\n'
        'method=GET; data=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    -X) method="$2"; shift 2;;\n'
        '    -d) data="$2"; shift 2;;\n'
        '    *) shift;;\n'
        '  esac\n'
        'done\n'
        'if [ "$method" = "GET" ]; then\n'
        "  cat <<'JSON'\n" + get_payload + "\nJSON\n"
        'else\n'
        '  printf "%s" "$data" > "$SENT_FILE"\n'
        '  printf "%s\\n" "$method" > "$SENT_METHOD"\n'
        '  echo \'{"success":true}\'\n'
        'fi\n'
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        r = _run_body(body,
                      {"CF_API_TOKEN": "t", "ZONE_ID": "z", "HOST": host,
                       "RUN_URL": run_url, "DRY": dry, "VERSION": "vTEST",
                       "SENT_FILE": str(tmp / "sent.json"),
                       "SENT_METHOD": str(tmp / "method.txt")},
                      stubs={"curl": curl})
        sent = tmp / "sent.json"
        meth = tmp / "method.txt"
        r["sent"] = json.loads(sent.read_text()) if sent.exists() and sent.read_text().strip() else None
        r["method"] = meth.read_text().strip() if meth.exists() else None
        return r


def run_cf_dns_step(body, *, mode="dns-only", existing_id="", dry="false"):
    get_payload = json.dumps({"success": True,
                              "result": ([{"id": existing_id}] if existing_id else [])})
    curl = (
        '#!/usr/bin/env bash\n'
        'method=GET; data=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    -X) method="$2"; shift 2;;\n'
        '    -d) data="$2"; shift 2;;\n'
        '    *) shift;;\n'
        '  esac\n'
        'done\n'
        'if [ "$method" = "GET" ]; then\n'
        "  cat <<'JSON'\n" + get_payload + "\nJSON\n"
        'else\n'
        '  printf "%s" "$data" > "$SENT_FILE"\n'
        '  printf "%s\\n" "$method" > "$SENT_METHOD"\n'
        '  echo \'{"success":true}\'\n'
        'fi\n'
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        r = _run_body(body,
                      {"CF_API_TOKEN": "t", "ZONE_ID": "z", "HOST": "img.example.com",
                       "MODE": mode, "RUN_URL": "svc-x-as.a.run.app", "DRY": dry,
                       "SENT_FILE": str(tmp / "sent.json"),
                       "SENT_METHOD": str(tmp / "method.txt")},
                      stubs={"curl": curl})
        sent = tmp / "sent.json"
        meth = tmp / "method.txt"
        r["sent"] = json.loads(sent.read_text()) if sent.exists() and sent.read_text().strip() else None
        r["method"] = meth.read_text().strip() if meth.exists() else None
        return r


def _cf_curl_stub(get_payload_by_kind):
    """A curl stub that answers GETs from a lookup table and records every mutation.

    get_payload_by_kind maps a substring of the URL to the JSON body to return, so one stub
    can serve both the dns_records lookups and the ruleset entrypoint.
    """
    branches = "".join(
        f'  case "$url" in *{frag}*) cat <<\'JSON\'\n{payload}\nJSON\n  return 0;; esac\n'
        for frag, payload in get_payload_by_kind.items())
    return (
        '#!/usr/bin/env bash\n'
        'method=GET; data=""; url=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    -X) method="$2"; shift 2;;\n'
        '    -d) data="$2"; shift 2;;\n'
        '    --data-urlencode) shift 2;;\n'
        '    -H) shift 2;;\n'
        '    -*) shift;;\n'
        '    *) url="$1"; shift;;\n'
        '  esac\n'
        'done\n'
        'answer() {\n' + branches +
        '  echo \'{"success":true,"result":[]}\'\n'
        '}\n'
        'if [ "$method" = "GET" ]; then\n'
        '  answer\n'
        'else\n'
        '  printf "%s\\t%s\\t%s\\n" "$method" "$url" "$data" >> "$SENT_FILE"\n'
        '  echo \'{"success":true,"result":{"rules":[]}}\'\n'
        'fi\n'
    )


def _sent_rows(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        m, u, d = parts[0], parts[1], parts[2]
        rows.append({"method": m, "url": u,
                     "body": json.loads(d) if d.strip().startswith("{") else d})
    return rows


def run_cfdns_records_step(body, *, records, existing=None, dry="false", zone="example.com"):
    """Drive the record convergence against a stubbed Cloudflare API."""
    payload = json.dumps({"success": True, "result": existing or []})
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sent = tmp / "sent.tsv"
        r = _run_body(body,
                      {"CF_API_TOKEN": "t", "ZONE_ID": "z", "ZONE_NAME": zone,
                       "RECORDS": json.dumps(records), "DRY": dry,
                       "SENT_FILE": str(sent)},
                      stubs={"curl": _cf_curl_stub({"dns_records": payload})})
        r["sent"] = _sent_rows(sent)
        return r


def run_cfdns_rules_step(body, *, rules, existing_rules=None, ruleset_exists=True,
                         prune="false", dry="false"):
    payload = json.dumps({"success": ruleset_exists,
                          "result": {"rules": existing_rules or []}})
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sent = tmp / "sent.tsv"
        r = _run_body(body,
                      {"CF_API_TOKEN": "t", "ZONE_ID": "z", "RULES": json.dumps(rules),
                       "PRUNE": prune, "DRY": dry, "VERSION": "vTEST",
                       "SENT_FILE": str(sent)},
                      stubs={"curl": _cf_curl_stub({"entrypoint": payload})})
        r["sent"] = _sent_rows(sent)
        return r


def run_crupdate_apply_step(body, **kw):
    """Drive cloud-run-update's argument assembly against a gcloud stub that records argv."""
    env = {"SERVICE": "svc", "PROJECT": "p", "REGION": "r", "RUNTIME_SA": "",
           "ENV_VARS": "", "ENV_MODE": "update", "CLEAR_ENV": "false",
           "SECRETS": "", "SEC_MODE": "update", "LABELS": "", "PORT": "", "CPU": "",
           "MEMORY": "", "CONCURRENCY": "", "MIN_INST": "", "MAX_INST": "", "BOOST": "",
           "REQ_TIMEOUT": "", "PROBE": "", "EXTRA": "", "DRY": "false"}
    env.update({k.upper(): v for k, v in kw.items()})
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        argv = tmp / "argv.txt"
        gcloud = ('#!/usr/bin/env bash\n'
                  'if [ "$3" = "describe" ]; then echo "https://svc-x.a.run.app"; exit 0; fi\n'
                  'printf "%s\\n" "$@" > "$ARGV_FILE"\n'
                  'exit 0\n')
        env["ARGV_FILE"] = str(argv)
        r = _run_body(body, env, stubs={"gcloud": gcloud})
        r["argv"] = argv.read_text().splitlines() if argv.exists() else []
        return r


# --- validate-alerts: the offline lint and the two query-execution layers -----

CHANNEL_OK = ("type: email\n"
              "displayName: Ops\n"
              "labels:\n"
              "  email_address: ops@example.com\n")


def policy_yaml(condition: str, *, name="Test policy") -> str:
    """A policy that passes every rule in the lint except what `condition` breaks."""
    return (f"displayName: {name}\n"
            "combiner: OR\n"
            "notificationChannels:\n"
            "  - NOTIFICATION_CHANNEL_PLACEHOLDER\n"
            "conditions:\n"
            f"{condition}"
            "alertStrategy:\n"
            "  autoClose: 1800s\n")


PROMQL_COND = ("  - displayName: promql\n"
               "    conditionPrometheusQueryLanguage:\n"
               "      query: |\n"
               "        rate(automahn_reconciler_runs_total{status=\"failed\"}[5m]) > 0\n"
               "      duration: 300s\n")

MQL_COND = ("  - displayName: mql\n"
            "    conditionMonitoringQueryLanguage:\n"
            "      query: |\n"
            "        fetch cloud_run_revision | metric 'run.googleapis.com/request_count'\n"
            "      duration: 300s\n")


def _nul_pairs(path: Path):
    """Read the NUL-delimited (file, query) pairs the lint hands the exec layers."""
    if not path.exists():
        return None
    parts = path.read_bytes().split(b"\x00")[:-1]
    return [(parts[i].decode(), parts[i + 1].decode()) for i in range(0, len(parts), 2)]


def run_alerts_lint_step(body: str, policies: dict, *, channel=CHANNEL_OK):
    """Execute the offline lint over a synthetic alerts dir."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        adir = tmp / "infra" / "alerts"
        adir.mkdir(parents=True)
        if channel is not None:
            (adir / "email-channel.yaml").write_text(channel)
        for fname, text in policies.items():
            (adir / fname).write_text(text)
        out = tmp / "gh_output"
        out.write_text("")
        env = dict(os.environ)
        env.update(ALERTS_DIR="infra/alerts", CHANNEL_FILE="email-channel.yaml",
                   POLICY_GLOB="policy-*.yaml", RUNNER_TEMP=str(tmp),
                   GITHUB_OUTPUT=str(out))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        outs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr, "outputs": outs,
                "promql": _nul_pairs(tmp / "promql_queries.txt"),
                "mql": _nul_pairs(tmp / "mql_queries.txt")}


def run_promql_step(body: str, *, queries, statuses=("200",), bodies=None, token="t"):
    """Execute the PromQL exec layer against a stubbed curl.

    queries:  (file, query) pairs, as the lint would have written them
    statuses: per-call HTTP code, last value repeats
    bodies:   per-call response JSON, last value repeats
    """
    bodies = bodies or ['{"status":"success","data":{"resultType":"vector","result":[]}}']
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        bd = tmp / "bodies"
        bd.mkdir()
        for i, b in enumerate(bodies, 1):
            (bd / str(i)).write_text(b)
        n = tmp / "n"
        n.write_text("0")
        (stub / "curl").write_text(f"""#!/usr/bin/env bash
i=$(cat {n}); i=$((i+1)); echo "$i" > {n}
printf '%s\\n' "$@" >> {tmp}/argv.txt
statuses=({" ".join(statuses)})
idx=$((i-1)); last=$(( ${{#statuses[@]}} - 1 )); [ $idx -gt $last ] && idx=$last
out=""; prev=""
for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done
b={bd}/$((idx+1)); [ -f "$b" ] || b={bd}/$(ls {bd} | sort -n | tail -1)
cp "$b" "$out"
printf '%s' "${{statuses[$idx]}}"
""")
        (stub / "curl").chmod(0o755)
        qf = tmp / "promql_queries.txt"
        with open(qf, "wb") as fh:
            for f, q in queries:
                fh.write(f.encode() + b"\x00" + q.encode() + b"\x00")
        out = tmp / "gh_output"
        out.write_text("")
        env = dict(os.environ)
        env["PATH"] = f"{stub}:{env['PATH']}"
        env.update(ACCESS_TOKEN=token, GCP_PROJECT="proj", RUNNER_TEMP=str(tmp),
                   GITHUB_OUTPUT=str(out))
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        outs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)
        argv = (tmp / "argv.txt")
        return {"rc": proc.returncode, "out": proc.stdout + proc.stderr, "outputs": outs,
                "calls": int(n.read_text().strip() or 0),
                "argv": argv.read_text() if argv.exists() else ""}


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
    # ---- GAR policy resolver: one enum, with the deprecated boolean folded in ----
    resolver = extract_step(GAR, "cleanup", "Resolve immutable-tag policy")
    print("\ncleanup-gar-images · Resolve immutable-tag policy")

    r = run_policy_step(resolver)
    check("default resolves to enforce", "policy=enforce" in r["output"], r["output"])
    check("default exits 0", r["rc"] == 0, r["out"])

    for p in ("enforce", "preserve", "unlock"):
        r = run_policy_step(resolver, policy_in=p)
        check(f"{p} passes through", f"policy={p}" in r["output"], r["output"])

    r = run_policy_step(resolver, policy_in="lock-it-please")
    check("an unknown policy FAILS the job", r["rc"] == 1, r["out"])
    check("an unknown policy names the valid values", "enforce" in r["out"], r["out"])

    # Back-compat: the deprecated boolean still means "leave it unlocked".
    r = run_policy_step(resolver, relock_in="false")
    check("relock_immutable_tags:false maps to unlock",
          "policy=unlock" in r["output"], r["output"])
    check("the deprecated boolean warns", "deprecated" in r["out"].lower(), r["out"])
    r = run_policy_step(resolver, policy_in="preserve", relock_in="true")
    check("the boolean's default does not override the policy",
          "policy=preserve" in r["output"], r["output"])

    # A registry build cache is a MOVING tag; `enforce` lets it be created once and
    # never updated, so the cache freezes at its first push and silently stops helping.
    # v2.4.0 dropped `buildcache` from the default keep-set and warns when a caller
    # opts back into it under `enforce`.
    def warned(res):
        return "keep_tags contains 'buildcache'" in res["out"]

    r = run_policy_step(resolver, policy_in="enforce", keep_tags="latest,buildcache")
    check("enforce + buildcache warns", warned(r), r["out"])
    check("enforce + buildcache does NOT fail the job", r["rc"] == 0, r["out"])

    r = run_policy_step(resolver, policy_in="enforce", keep_tags="latest, buildcache")
    check("the warning survives whitespace (csv() strips it, so must we)",
          warned(r), r["out"])

    r = run_policy_step(resolver, policy_in="enforce", keep_tags="latest")
    check("enforce without buildcache is quiet", not warned(r), r["out"])

    for p in ("preserve", "unlock"):
        r = run_policy_step(resolver, policy_in=p, keep_tags="latest,buildcache")
        check(f"{p} + buildcache is quiet — that is the supported combination",
              not warned(r), r["out"])

    # Substring matches would fire on an unrelated tag that merely contains the word.
    for tag in ("latest,mybuildcache", "buildcache-old", "latest,buildcaches"):
        r = run_policy_step(resolver, policy_in="enforce", keep_tags=tag)
        check(f"'{tag}' does not trip the warning", not warned(r), r["out"])

    # ---- GAR permission pre-flight: one probe, two verdicts ----
    perm = extract_step(GAR, "cleanup", "Verify permission to toggle immutability")
    print("\ncleanup-gar-images · Verify permission to toggle immutability")

    r = run_perm_step(perm, granted=True)
    check("granted exits 0", r["rc"] == 0, r["out"])
    check("granted records can_update=true", "can_update=true" in r["output"], r["output"])

    r = run_perm_step(perm, started="true", granted=False)
    check("locked + denied records can_update=false", "can_update=false" in r["output"], r["output"])

    # Locked repo, no permission: DEGRADE rather than fail. Tagged images are
    # undeletable under immutability, but untagged manifests are not — so the
    # sweep does what it still can and names what it could not.
    r = run_perm_step(perm, started="true", granted=False)
    check("locked + denied degrades instead of failing", r["rc"] == 0, r["out"])
    check("locked + denied marks the run degraded",
          "degraded=true" in r["output"], r["output"])
    check("locked + denied says tagged images are skipped",
          "tagged" in r["out"].lower(), r["out"])

    # Unlocked repo under enforce: warn, but let the sweep do its real job.
    r = run_perm_step(perm, started="false", granted=False)
    check("unlocked + denied does NOT fail the sweep", r["rc"] == 0, r["out"])
    check("unlocked + denied warns the policy is not in effect",
          "LEFT UNLOCKED" in r["out"] and "::warning::" in r["out"], r["out"])
    check("unlocked + denied names the fix",
          "artifactregistry.repositories.update" in r["out"], r["out"])

    # ---- GAR executor: a degraded run deletes what it still can ----
    execstep = extract_step(GAR, "cleanup", "Execute deletions")
    print("\ncleanup-gar-images · Execute deletions")

    r = run_exec_step(execstep, degraded="false")
    check("normal run deletes tagged and untagged", len(r["deleted"]) == 4, r["deleted"])
    check("normal run exits 0", r["rc"] == 0, r["out"])

    r = run_exec_step(execstep, degraded="true")
    check("degraded run deletes ONLY untagged",
          sorted(r["deleted"]) == ["r/img@sha256:u1", "r/img@sha256:u2"], r["deleted"])
    check("degraded run does not fail the job", r["rc"] == 0, r["out"])
    check("degraded run warns", "::warning::" in r["out"], r["out"])
    check("degraded run names how many it skipped",
          "2" in r["out"] and "tagged" in r["out"].lower(), r["out"])
    check("degraded run reports it in the summary",
          "tagged" in r["summary"].lower(), r["summary"])

    # ---- GAR end-state: the repo must end an applied run LOCKED by default ----
    relock = extract_step(GAR, "cleanup", "Ensure immutable-tag end-state")
    print("\ncleanup-gar-images · Ensure immutable-tag end-state")

    r = run_relock_step(relock)
    check("happy path exits 0", r["rc"] == 0, r["out"])
    check("happy path re-enables", "--immutable-tags" in r["calls"], r["calls"])
    check("happy path verifies by readback", "describe" in r["calls"], r["calls"])

    # The new behaviour: a repo that was NEVER locked ends the run locked.
    r = run_relock_step(relock, started="false")
    check("enforce locks a repo that started unlocked", r["rc"] == 0, r["out"])
    check("enforce actually calls update", "--immutable-tags" in r["calls"], r["calls"])
    check("enforce readback-verifies too", "describe" in r["calls"], r["calls"])

    # The dangerous case: gcloud says OK but the repo is still unlocked.
    r = run_relock_step(relock, update_ok=True, readback="false")
    check("unlocked-after-relock FAILS the job", r["rc"] == 1, r["out"])
    check("unlocked-after-relock says UNLOCKED", "UNLOCKED" in r["out"], r["out"])
    check("unlocked-after-relock gives the fix command",
          "--immutable-tags" in r["out"], r["out"])
    r = run_relock_step(relock, started="false", update_ok=True, readback="false")
    check("failed ENFORCE fails the job too", r["rc"] == 1, r["out"])

    # Trust the readback, not the exit code: update fails but repo is protected.
    r = run_relock_step(relock, update_ok=False, readback="true")
    check("readback wins over a failed update", r["rc"] == 0, r["out"])

    r = run_relock_step(relock, update_ok=False, readback="false")
    check("genuine relock failure exits 1", r["rc"] == 1, r["out"])

    # preserve = the pre-v2.1.0 contract: restore what was there, nothing more.
    r = run_relock_step(relock, policy="preserve", started="true")
    check("preserve relocks a repo that started locked",
          r["rc"] == 0 and "--immutable-tags" in r["calls"], r["calls"])
    r = run_relock_step(relock, policy="preserve", started="false")
    check("preserve leaves an unlocked repo alone", r["rc"] == 0, r["out"])
    check("preserve touches nothing", r["calls"].strip() == "", r["calls"])

    # Opt-out: warn loudly, change nothing, do not fail.
    r = run_relock_step(relock, policy="unlock")
    check("opt-out exits 0", r["rc"] == 0, r["out"])
    check("opt-out warns it is left unlocked", "LEFT UNLOCKED" in r["out"], r["out"])
    check("opt-out touches nothing", r["calls"].strip() == "", r["calls"])

    # Missing permission is asymmetric: enforcing cannot lose a guarantee that
    # was never there, so it warns; a repo that STARTED locked was never
    # unlocked either (the pre-flight fails the job before any deletion).
    r = run_relock_step(relock, started="false", can_update="false")
    check("enforce without permission does not fail the job", r["rc"] == 0, r["out"])
    check("enforce without permission touches nothing", r["calls"].strip() == "", r["calls"])
    r = run_relock_step(relock, started="true", can_update="false")
    check("no-permission + started-locked does not cry UNLOCKED",
          r["rc"] == 0 and "FAILED TO RE-LOCK" not in r["out"], r["out"])

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

    # ---- retire-gar-packages under immutability ----
    # A locked repository refuses `packages delete` for any package holding a
    # tagged image, and this workflow exits 1 on the raw gcloud error. Both
    # backend repos are locked, so the whole workflow is a trap until it does
    # what the image sweep does: detect, pre-flight, unlock, act, restore.
    # Unlike the sweep there is no degraded half-run to fall back to — a
    # package delete is all-or-nothing — so a locked repo with no permission
    # must fail BEFORE anything is deleted, not partway through.
    print("\nretire-gar-packages · immutability handling")

    detect = extract_step(RETIRE, "retire", "Check tag immutability")
    r = run_immutable_step(detect, state="true")
    check("locked repo is detected", "immutable=true" in r["output"], r["output"])
    r = run_immutable_step(detect, state="false")
    check("unlocked repo is detected", "immutable=false" in r["output"], r["output"])
    r = run_immutable_step(detect, describe_ok=False)
    check("undescribable repo reads as unlocked, does not abort",
          r["rc"] == 0 and "immutable=false" in r["output"], r["out"])

    perm = extract_step(RETIRE, "retire", "Verify permission to toggle immutability")
    r = run_perm_step(perm, started="true", granted=True)
    check("retire · granted exits 0", r["rc"] == 0, r["out"])
    check("retire · granted records can_update=true",
          "can_update=true" in r["output"], r["output"])

    # The whole point: fail closed, and say WHY, before the destructive step.
    r = run_perm_step(perm, started="true", granted=False)
    check("retire · locked + denied FAILS the run", r["rc"] == 1, r["out"])
    check("retire · locked + denied blames immutability, not gcloud",
          "immutable" in r["out"].lower(), r["out"])
    check("retire · locked + denied names the missing permission",
          "artifactregistry.repositories.update" in r["out"], r["out"])

    endstate = extract_step(RETIRE, "retire", "Ensure immutable-tag end-state")
    r = run_relock_step(endstate, policy="preserve", started="true",
                        can_update="true", readback="true")
    check("retire · a locked repo ends the run locked again", r["rc"] == 0, r["out"])
    check("retire · re-lock is confirmed by readback, not exit code",
          "describe" in r["calls"], r["calls"])

    r = run_relock_step(endstate, policy="preserve", started="true",
                        can_update="true", update_ok=False, readback="false")
    check("retire · failing to restore the lock FAILS the run", r["rc"] == 1, r["out"])
    check("retire · failed restore names the repair command",
          "--immutable-tags" in r["out"], r["out"])

    # Preserve semantics: a repo that was never locked is left as it was found.
    r = run_relock_step(endstate, policy="preserve", started="false",
                        can_update="true", readback="false")
    check("retire · an unlocked repo is left unlocked", r["rc"] == 0, r["out"])
    check("retire · leaving it unlocked does not run an update",
          "--immutable-tags" not in r["calls"], r["calls"])

    execstep = extract_step(RETIRE, "retire", "Execute retirement")
    r = run_retire_exec_step(execstep)
    check("retire · a clean delete counts the package",
          "retired=1" in r["output"], r["output"])
    r = run_retire_exec_step(execstep, fail_with="FAILED_PRECONDITION: repository has immutable tags")
    check("retire · a delete failure still fails the run", r["rc"] == 1, r["out"])
    check("retire · an immutability failure is named as such",
          "immutab" in r["out"].lower(), r["out"])

    # ---- cleanup-gar-images · stranded :latest cleanup ----
    #
    # Removes a TAG REFERENCE, never a digest. A moving :latest left in a repo
    # that has since been LOCKED is otherwise permanent: it pins its digest alive,
    # `keep_tags` shields it from the sweep, and an immutable repo refuses to move
    # or remove it. Dropping `latest` from keep_tags instead is NOT equivalent —
    # under build-once/promote a released digest carries both a :<sha> tag and
    # vX.Y.Z, so deleting the digest would take a release with it.
    #
    # This is a CONVERGENCE RULE, not a one-shot: it deletes :latest, then finds
    # nothing, forever. That is why it defaults to true and runs on the schedule.
    print("\ncleanup-gar-images · Clean up stranded :latest")
    clatest = extract_step(GAR, "cleanup", "Clean up stranded :latest tag")

    # A dry run is the READ path: report what is there, touch nothing. It is the
    # only way to see a keep-set digest at all — the plan JSON enumerates
    # to_delete/blocked_by_parent, never the kept.
    r = run_cleanup_latest_step(clatest, dry_run="true")
    check("latest · dry run exits 0", r["rc"] == 0, r["out"])
    check("latest · dry run deletes nothing", r["deletes"] == [], r["calls"])
    check("latest · dry run reports the digest behind the tag",
          "sha256:dead0" in r["out"], r["out"])

    r = run_cleanup_latest_step(clatest, dry_run="false")
    check("latest · apply exits 0", r["rc"] == 0, r["out"])
    check("latest · apply deletes the tag", len(r["deletes"]) == 1, r["calls"])
    check("latest · apply targets pkg:latest, never a digest",
          any(":latest" in d and "@sha256" not in d for d in r["deletes"]), r["deletes"])
    check("latest · apply counts what it removed",
          "tags_deleted=1" in r["output"], r["output"])

    # Convergence: the second run finds nothing and must stay green.
    r = run_cleanup_latest_step(clatest, dry_run="false", existing=())
    check("latest · an already-absent tag exits 0", r["rc"] == 0, r["out"])
    check("latest · an already-absent tag deletes nothing", r["deletes"] == [], r["calls"])
    check("latest · an already-absent tag counts zero",
          "tags_deleted=0" in r["output"], r["output"])

    # Matching must be EXACT. gcloud's `--filter=tag:x` is a has/contains
    # operator, not equality, so a repo carrying `latest-rc` could be read as
    # having `latest` — and the delete would then fail on a tag that never
    # existed. Nothing is destroyed either way, but a confusing red run is not
    # an acceptable substitute for a clean no-op.
    r = run_cleanup_latest_step(clatest, dry_run="false", existing=("latest-rc", "v1.0.0"))
    check("latest · a similarly-named tag is NOT treated as :latest",
          r["deletes"] == [], r["calls"])
    check("latest · a similarly-named tag leaves the run green", r["rc"] == 0, r["out"])

    # Every image in the repo, not just one.
    r = run_cleanup_latest_step(clatest, dry_run="false",
                                packages=("host/p/repo/api", "host/p/repo/bff-api"))
    check("latest · sweeps every package in the plan", len(r["deletes"]) == 2, r["calls"])

    # ---- the policy gate, which is what makes defaulting to true safe ----
    #
    # Under `enforce` a moving :latest CANNOT be pushed, so any :latest present is
    # stranded by definition. Under `preserve` that only holds if the repo is
    # already locked. Under `unlock` the repo is deliberately left writable and
    # :latest may be a live, updating tag — exactly the case `preserve` exists for.
    r = run_cleanup_latest_step(clatest, dry_run="false", policy="preserve", started="true")
    check("latest · preserve + already locked cleans up", len(r["deletes"]) == 1, r["calls"])

    r = run_cleanup_latest_step(clatest, dry_run="false", policy="preserve", started="false")
    check("latest · preserve + unlocked leaves a live :latest alone",
          r["deletes"] == [], r["calls"])
    check("latest · preserve + unlocked exits 0", r["rc"] == 0, r["out"])
    check("latest · preserve + unlocked says why it declined",
          "live" in r["out"].lower(), r["out"])

    r = run_cleanup_latest_step(clatest, dry_run="false", policy="unlock", started="true")
    check("latest · unlock never touches :latest even if locked",
          r["deletes"] == [], r["calls"])

    # Divergence from the sweep's own semantics: the sweep DEGRADES on
    # locked+no-permission (skip tagged, exit green), which is right for a
    # retention policy. Here it would mean reporting a cleanup that did not happen.
    r = run_cleanup_latest_step(clatest, dry_run="false", degraded="true")
    check("latest · degraded FAILS rather than reporting success", r["rc"] == 1, r["out"])
    check("latest · degraded blames immutability", "immutab" in r["out"].lower(), r["out"])
    check("latest · degraded names the missing permission",
          "artifactregistry.repositories.update" in r["out"], r["out"])
    check("latest · degraded names the service account, not a generic fallback",
          "sa@p.iam.gserviceaccount.com" in r["out"], r["out"])
    check("latest · degraded deletes nothing", r["deletes"] == [], r["calls"])

    gar_doc = yaml.safe_load(GAR.read_text())
    inputs = gar_doc[True]["workflow_call"]["inputs"]
    check("latest · cleanup_latest_tag defaults to true",
          inputs["cleanup_latest_tag"]["default"] is True, inputs["cleanup_latest_tag"])
    check("latest · cleanup_latest_tag is a boolean",
          inputs["cleanup_latest_tag"]["type"] == "boolean", inputs["cleanup_latest_tag"])
    check("latest · the CSV delete_tags input is gone", "delete_tags" not in inputs,
          sorted(inputs))

    step = [s for s in gar_doc["jobs"]["cleanup"]["steps"]
            if s.get("name") == "Clean up stranded :latest tag"][0]
    check("latest · the step is gated on the input",
          "cleanup_latest_tag" in str(step.get("if", "")), step.get("if"))
    # It is a convergence rule, so it must NOT be limited to manual dispatch.
    check("latest · is not restricted to workflow_dispatch",
          "event_name" not in str(step.get("if", "")), step.get("if"))

    # Ordering is load-bearing: the plan is built long before any tag is touched,
    # so the reviewed dry-run digest set still matches what the sweep does. The
    # now-untagged digest is reclaimed on the NEXT run, by design.
    names = [s.get("name") for s in gar_doc["jobs"]["cleanup"]["steps"]]
    check("latest · runs after the sweep, preserving plan/apply parity",
          names.index("Clean up stranded :latest tag") > names.index("Execute deletions"), names)
    check("latest · runs before the re-lock, i.e. inside the unlock window",
          names.index("Clean up stranded :latest tag")
          < names.index("Ensure immutable-tag end-state"), names)

    # ---- writers · keep_enabled_count -------------------------------------
    #
    # The writers disable; they never destroy. Destruction needs the quarantine
    # clock and the Cloud Run consumer scan, which live in cleanup-secret-versions
    # and which these workflows deliberately lack the IAM to perform.
    for wf, job in WRITERS:
        print(f"\n{wf.stem} · {DISABLE_STEP}")
        body = extract_step(wf, job, DISABLE_STEP)
        doc = yaml.safe_load(wf.read_text())
        inputs = doc[True]["workflow_call"]["inputs"]

        check(f"{wf.stem} · keep_enabled_count defaults to '1'",
              inputs["keep_enabled_count"]["default"] == "1",
              inputs.get("keep_enabled_count"))
        check(f"{wf.stem} · keep_enabled_count is a string, as the repo's other counts are",
              inputs["keep_enabled_count"]["type"] == "string",
              inputs.get("keep_enabled_count"))

        # 1. Fresh secret: the version this run added is the only ENABLED one.
        r = run_disable_keep_step(body, keep="1", enabled=("7",))
        check(f"{wf.stem} · sole version is never disabled", r["disabled"] == [], r["calls"])
        check(f"{wf.stem} · sole version exits 0", r["rc"] == 0, r["out"])

        # 2. The steady state these workflows maintain — one superseded version.
        r = run_disable_keep_step(body, keep="1", enabled=("7", "6"))
        check(f"{wf.stem} · keep=1 disables exactly the superseded version",
              r["disabled"] == ["6"], r["calls"])

        # 3. keep=2 buys a rollback target that needs no re-enable.
        r = run_disable_keep_step(body, keep="2", enabled=("7", "6", "5"))
        check(f"{wf.stem} · keep=2 leaves one previous version enabled",
              r["disabled"] == ["5"], r["calls"])

        # 4. A pre-existing ENABLED tail: swept, and said out loud. This is the
        #    one case where the default is NOT identical to the old behaviour.
        r = run_disable_keep_step(body, keep="1", enabled=("7", "6", "5", "4"))
        check(f"{wf.stem} · keep=1 sweeps a pre-existing tail",
              r["disabled"] == ["6", "5", "4"], r["calls"])
        check(f"{wf.stem} · sweeping a tail emits a warning",
              "::warning::" in r["out"], r["out"])

        # 5. `latest` resolves to the newest ENABLED version, so it is never touched.
        check(f"{wf.stem} · never disables the latest-resolving version",
              "7" not in r["disabled"], r["disabled"])

        # 6. Destruction is not this workflow's job, at any input.
        check(f"{wf.stem} · never destroys", r["destroys"] == [], r["calls"])

        # 7. keep=0 would disable every version and strand `latest`.
        r = run_disable_keep_step(body, keep="0", enabled=("7", "6"))
        check(f"{wf.stem} · keep=0 is rejected", r["rc"] != 0, r["out"])
        check(f"{wf.stem} · keep=0 disables nothing", r["disabled"] == [], r["calls"])

        # 8. A non-numeric input must not reach `[ -lt ]` as a bare word.
        r = run_disable_keep_step(body, keep="all", enabled=("7", "6"))
        check(f"{wf.stem} · non-numeric keep_enabled_count is rejected",
              r["rc"] != 0, r["out"])
        check(f"{wf.stem} · non-numeric keep_enabled_count disables nothing",
              r["disabled"] == [], r["calls"])

        # 9. Ordering: disable only after the services rolled onto the new version.
        names = [s.get("name") for s in doc["jobs"][job]["steps"]]
        check(f"{wf.stem} · disables after the Cloud Run roll",
              names.index(DISABLE_STEP) > names.index("Force new Cloud Run revision(s)"),
              names)

    # sync-bundle-key alone fails hard on a disable error; the two rotators
    # tolerate it with `|| true` because the credential is already live by then.
    r = run_disable_keep_step(extract_step(SYNC, "sync", DISABLE_STEP),
                              keep="1", enabled=("7", "6"), disable_fails=True)
    check("sync-bundle-key · a failed disable fails the step", r["rc"] != 0, r["out"])

    # ── cleanup-secret-versions · Collect target secrets ──────────────────────
    # The workflow's stated IAM contract is secretVersionManager + run.viewer +
    # logging.viewer. Listing every secret in the project needs a fourth thing it
    # never mentions — project-level secretmanager.secrets.list — which locks out
    # exactly the resource-scoped callers the fleet moved to.
    body = extract_step(SWEEP, "cleanup", "Collect target secrets")
    print("\ncleanup-secret-versions · Collect target secrets")

    r = run_collect_targets_step(body, secrets_list="app-secrets", can_list=False)
    check("named secrets sweep without project-level list", r["rc"] == 0, r["out"])
    check("named secrets resolve as targets", r["targets"] == ["app-secrets"], r["targets"])

    r = run_collect_targets_step(body, secrets_list="app-secrets, api-env",
                                 can_list=False, existing=("app-secrets", "api-env"))
    check("several named secrets resolve", r["targets"] == ["api-env", "app-secrets"], r["targets"])

    # A typo must still be caught — a sweep that silently covers nothing reads as success.
    r = run_collect_targets_step(body, secrets_list="app-secrets,ap-secrets", can_list=False)
    check("a misnamed secret aborts", r["rc"] == 1, r["out"])
    check("a misnamed secret is named in the error", "ap-secrets" in r["out"], r["out"])

    # Sweeping EVERYTHING still needs the project list, and still warns.
    r = run_collect_targets_step(body, secrets_list="", can_list=True,
                                 existing=("app-secrets", "api-env"))
    check("empty list sweeps every secret", r["targets"] == ["api-env", "app-secrets"], r["targets"])
    check("empty list warns", "::warning::" in r["out"], r["out"])

    # ── deploy-cloudflare-worker ────────────────────────────────────────────
    print("\ndeploy-cloudflare-worker · Resolve ref and worker name")
    body = extract_step(CFWORKER, "deploy", "Resolve ref and worker name")

    r = run_worker_resolve_step(body, ref_in="", fallback="v1.2.3", require="true")
    check("a semver tag passes the gate", r["rc"] == 0, r["out"])
    check("empty ref falls back to the trigger ref", r.get("ref") == "v1.2.3", r)
    check("worker name defaults to the directory", r.get("worker_name") == "cf-worker", r)

    # The gate exists for the dispatch typo: deploying 'v1.2' must cost seconds, not a roll.
    r = run_worker_resolve_step(body, ref_in="v1.2", require="true")
    check("a non-semver ref fails when required", r["rc"] == 1, r["out"])
    check("the rejected ref is named", "v1.2" in r["out"], r["out"])

    r = run_worker_resolve_step(body, ref_in="some-branch", require="false", name_in="w")
    check("the gate is off by default", r["rc"] == 0, r["out"])
    check("an explicit worker name wins", r.get("worker_name") == "w", r)

    print("\ndeploy-cloudflare-worker · Decide whether the worker changed")
    body = extract_step(CFWORKER, "deploy", "Decide whether the worker changed")
    hist = [("v1.0.0", {"cf-worker/index.js": "a", "other/x": "1"}),
            ("v1.1.0", {"other/x": "2"})]

    r = run_worker_changed_step(body, watch_paths="", history=hist, ref="v1.1.0")
    check("empty watch_paths never skips", r["skip"] == "false", r)

    r = run_worker_changed_step(body, watch_paths="cf-worker/", history=hist, ref="v1.1.0")
    check("untouched worker dir skips", r["skip"] == "true", r)

    r = run_worker_changed_step(body, watch_paths="other/", history=hist, ref="v1.1.0")
    check("a touched path deploys", r["skip"] == "false", r)

    # Several paths: ANY of them changing must deploy, or a workflow-file edit is swallowed.
    r = run_worker_changed_step(body, watch_paths="cf-worker/\nother/",
                                history=hist, ref="v1.1.0")
    check("any watched path changing deploys", r["skip"] == "false", r)

    # The first release has nothing to diff against; skipping it would ship nothing, ever.
    r = run_worker_changed_step(body, watch_paths="cf-worker/",
                                history=[("v1.0.0", {"cf-worker/index.js": "a"})],
                                ref="v1.0.0")
    check("the first tag never skips", r["skip"] == "false", r)

    # Blank lines in a YAML block scalar are normal; they must not become a path.
    r = run_worker_changed_step(body, watch_paths="\n  cf-worker/  \n\n",
                                history=hist, ref="v1.1.0")
    check("blank/padded watch_paths lines are ignored", r["skip"] == "true", r)

    print("\ndeploy-cloudflare-worker · Deploy worker")
    body = extract_step(CFWORKER, "deploy", "Deploy worker")

    r = run_worker_deploy_step(body)
    check("default deploy exits 0", r["rc"] == 0, r["out"])
    check("default resolves wrangler from the lockfile",
          r["argv"] == "--yes wrangler deploy", r["argv"])

    r = run_worker_deploy_step(body, version="4.42.0", env_name="staging", dry_run="true")
    check("version, env and dry-run all reach wrangler",
          r["argv"] == "--yes wrangler@4.42.0 deploy --env staging --dry-run", r["argv"])

    # An unset optional must not become an empty argument — `--env ''` is not the same as
    # omitting --env, and wrangler would deploy the wrong config.
    r = run_worker_deploy_step(body, env_name="")
    check("an empty env adds no --env flag", "--env" not in r["argv"], r["argv"])


    # ── bootstrap-cf-service ────────────────────────────────────────────────
    print("\nbootstrap-cf-service · Validate inputs")
    body = extract_step(CFSERVICE, "bootstrap", "Validate inputs")

    r = run_cf_validate_step(body, mode="sideways")
    check("an unknown mode is rejected", r["rc"] == 1, r["out"])

    # dns-only ALWAYS needs gcloud: the domain mapping is the whole route.
    r = run_cf_validate_step(body, mode="dns-only", service="s",
                             wif="w", sa="a", project="p")
    check("dns-only with full GCP inputs passes", r["rc"] == 0, r["out"])
    check("dns-only needs gcloud", r["env"].get("need_gcloud") == "true", r["env"])

    r = run_cf_validate_step(body, mode="dns-only", service="s")
    check("dns-only without WIF fails", r["rc"] == 1, r["out"])

    r = run_cf_validate_step(body, mode="dns-only", wif="w", sa="a", project="p")
    check("dns-only without a service fails", r["rc"] == 1, r["out"])

    # The one path that needs no GCP access at all — today's proxied caller.
    r = run_cf_validate_step(body, mode="proxied", run_url="svc-x-as.a.run.app")
    check("proxied with an explicit URL needs no GCP", r["rc"] == 0, r["out"])
    check("proxied with an explicit URL skips auth",
          r["env"].get("need_gcloud") == "false", r["env"])

    r = run_cf_validate_step(body, mode="proxied", service="s",
                             wif="w", sa="a", project="p")
    check("proxied can derive the URL with WIF", r["rc"] == 0, r["out"])
    check("deriving the URL needs gcloud", r["env"].get("need_gcloud") == "true", r["env"])

    r = run_cf_validate_step(body, mode="proxied")
    check("proxied with neither URL nor service fails", r["rc"] == 1, r["out"])

    print("\nbootstrap-cf-service · Resolve the Cloud Run URL")
    body = extract_step(CFSERVICE, "bootstrap", "Resolve the Cloud Run URL")

    # The scheme must come off: it is used as a CNAME target and a Host header, and
    # "https://x.run.app" is valid in neither.
    r = run_cf_runurl_step(body)
    check("a resolved URL loses its scheme",
          r["outputs"].get("cloud_run_url") == "svc-x-as.a.run.app", r["outputs"])

    r = run_cf_runurl_step(body, run_url="given-as.a.run.app")
    check("an explicit URL is used verbatim",
          r["outputs"].get("cloud_run_url") == "given-as.a.run.app", r["outputs"])

    r = run_cf_runurl_step(body, live_url="")
    check("an unreadable service fails loudly", r["rc"] == 1, r["out"])

    print("\nbootstrap-cf-service · Upsert the DNS record")
    body = extract_step(CFSERVICE, "bootstrap", "Upsert the DNS record")

    r = run_cf_dns_step(body, mode="dns-only")
    check("dns-only points at ghs and is unproxied",
          r["sent"]["content"] == "ghs.googlehosted.com" and r["sent"]["proxied"] is False,
          r["sent"])
    check("no existing record creates", r["method"] == "POST", r["method"])

    r = run_cf_dns_step(body, mode="proxied", existing_id="rec1")
    check("proxied points at the run.app host and is proxied",
          r["sent"]["content"] == "svc-x-as.a.run.app" and r["sent"]["proxied"] is True,
          r["sent"])
    check("an existing record is patched, not duplicated", r["method"] == "PATCH", r["method"])

    r = run_cf_dns_step(body, mode="proxied", dry="true")
    check("dry_run writes nothing", r["sent"] is None, r["sent"])
    check("dry_run still says what it would do", "would upsert" in r["out"], r["out"])

    print("\nbootstrap-cf-service · Upsert the Origin Rule (Host header override)")
    body = extract_step(CFSERVICE, "bootstrap", "Upsert the Origin Rule (Host header override)")

    r = run_cf_originrule_step(body, existing_rules=[])
    check("an empty ruleset gets our rule", r["method"] == "PUT", r["method"])
    check("the rule overrides Host to the run.app host",
          r["sent"]["rules"][0]["action_parameters"]["host_header"] == "svc-new-as.a.run.app",
          r["sent"])

    # The entrypoint is written WHOLE, so an unrelated rule that is not preserved is silently
    # deleted from the zone. This is the failure this test exists for.
    other = {"expression": '(http.host eq "other.example.com")', "action": "route",
             "action_parameters": {"host_header": "other-as.a.run.app"},
             "id": "srv1", "version": "3", "last_updated": "x", "ref": "r1"}
    r = run_cf_originrule_step(body, existing_rules=[other])
    exprs = [x["expression"] for x in r["sent"]["rules"]]
    check("an unrelated rule survives the splice",
          '(http.host eq "other.example.com")' in exprs, exprs)
    check("our rule is appended", len(r["sent"]["rules"]) == 2, r["sent"])
    # CF 400s on PUT if server-assigned fields are echoed back.
    kept = [x for x in r["sent"]["rules"] if x["expression"] != '(http.host eq "img.example.com")'][0]
    check("server-assigned fields are stripped from kept rules",
          not any(k in kept for k in ("id", "version", "last_updated", "ref")), kept)

    # Re-running must refresh in place, not stack a second rule for the same host.
    stale = {"expression": '(http.host eq "img.example.com")', "action": "route",
             "action_parameters": {"host_header": "svc-OLD-as.a.run.app"}, "id": "s2"}
    r = run_cf_originrule_step(body, existing_rules=[stale])
    check("a re-run does not stack a duplicate rule", len(r["sent"]["rules"]) == 1, r["sent"])
    check("a re-run refreshes a stale origin host",
          r["sent"]["rules"][0]["action_parameters"]["host_header"] == "svc-new-as.a.run.app",
          r["sent"])

    # No entrypoint yet for this phase ⇒ create the ruleset, not PUT to a missing one.
    r = run_cf_originrule_step(body, ruleset_exists=False)
    check("a missing entrypoint ruleset is created", r["method"] == "POST", r["method"])
    check("the created ruleset declares the origin phase",
          r["sent"]["phase"] == "http_request_origin", r["sent"])

    r = run_cf_originrule_step(body, dry="true")
    check("dry_run writes no ruleset", r["sent"] is None, r["sent"])

    # ── bootstrap-cf-dns ────────────────────────────────────────────────────
    print("\nbootstrap-cf-dns · Validate the inputs")
    body = extract_step(CFDNS, "bootstrap", "Validate the inputs")

    r = _run_body(body, {"RECORDS": "[]", "RULES": "[]"})
    check("empty arrays are valid", r["rc"] == 0, r["out"])

    r = _run_body(body, {"RECORDS": "{}", "RULES": "[]"})
    check("a non-array records input is rejected", r["rc"] == 1, r["out"])

    # Validating up front matters: a run that writes three records then dies on the fourth
    # leaves the zone in a state nobody declared.
    r = _run_body(body, {"RECORDS": '[{"type":"A","name":"x","content":"1.2.3.4"},'
                                    '{"type":"A","name":"y"}]', "RULES": "[]"})
    check("a record missing content is rejected before any write", r["rc"] == 1, r["out"])
    check("the offending index is named", "records[1]" in r["out"], r["out"])

    r = _run_body(body, {"RECORDS": "[]", "RULES": '[{"hostname":"a.example.com"}]'})
    check("an origin rule without host_header is rejected", r["rc"] == 1, r["out"])

    print("\nbootstrap-cf-dns · Converge the DNS records")
    body = extract_step(CFDNS, "bootstrap", "Converge the DNS records")

    r = run_cfdns_records_step(body, records=[
        {"type": "CNAME", "name": "api", "content": "ghs.googlehosted.com"}])
    check("a new record is POSTed", r["sent"][0]["method"] == "POST", r["sent"])
    check("a short name is qualified against the zone",
          r["sent"][0]["body"]["name"] == "api.example.com", r["sent"][0]["body"])
    check("proxied defaults to false", r["sent"][0]["body"]["proxied"] is False,
          r["sent"][0]["body"])

    r = run_cfdns_records_step(body, records=[
        {"type": "AAAA", "name": "files", "content": "100::", "proxied": True}],
        existing=[{"id": "rec9", "content": "100::"}])
    check("an existing record is PUT, not duplicated", r["sent"][0]["method"] == "PUT", r["sent"])
    check("the existing record id is targeted", "rec9" in r["sent"][0]["url"], r["sent"][0]["url"])
    check("proxied passes through", r["sent"][0]["body"]["proxied"] is True, r["sent"][0]["body"])

    # An already-qualified name must not become api.example.com.example.com.
    r = run_cfdns_records_step(body, records=[
        {"type": "A", "name": "api.example.com", "content": "1.2.3.4"}])
    check("an fqdn name is left alone",
          r["sent"][0]["body"]["name"] == "api.example.com", r["sent"][0]["body"])

    r = run_cfdns_records_step(body, records=[{"type": "A", "name": "@", "content": "1.2.3.4"}])
    check("@ resolves to the apex", r["sent"][0]["body"]["name"] == "example.com",
          r["sent"][0]["body"])

    # THE TXT CASE: several TXT records legitimately share one name (SPF, DMARC, per-vendor
    # verification tokens). Matching on name+type alone would overwrite someone else's token.
    r = run_cfdns_records_step(body,
        records=[{"type": "TXT", "name": "@", "content": "realm-verify=NEW"}],
        existing=[{"id": "txt-other", "content": "v=spf1 -all"}])
    check("a TXT with different content creates rather than overwrites",
          r["sent"][0]["method"] == "POST", r["sent"])

    r = run_cfdns_records_step(body,
        records=[{"type": "TXT", "name": "@", "content": "realm-verify=NEW"}],
        existing=[{"id": "txt-other", "content": "v=spf1 -all"},
                  {"id": "txt-mine", "content": "realm-verify=NEW"}])
    check("a TXT with matching content updates that one",
          r["sent"][0]["method"] == "PUT" and "txt-mine" in r["sent"][0]["url"], r["sent"])

    # `replaces` is how a hostname moves between routing models; without it nothing is deleted.
    r = run_cfdns_records_step(body, records=[
        {"type": "CNAME", "name": "api-cr", "content": "ghs.googlehosted.com",
         "replaces": ["AAAA"]}], existing=[{"id": "stale1", "content": "100::"}])
    check("replaces deletes the stale type first",
          r["sent"][0]["method"] == "DELETE" and "stale1" in r["sent"][0]["url"], r["sent"])
    check("and still upserts the record", r["sent"][1]["method"] in ("POST", "PUT"), r["sent"])

    r = run_cfdns_records_step(body, records=[
        {"type": "CNAME", "name": "api-cr", "content": "ghs.googlehosted.com"}],
        existing=[{"id": "stale1", "content": "100::"}])
    check("without replaces nothing is deleted",
          all(x["method"] != "DELETE" for x in r["sent"]), r["sent"])

    r = run_cfdns_records_step(body, records=[{"type": "A", "name": "x", "content": "1.2.3.4"}],
                               dry="true")
    check("dry_run writes nothing", r["sent"] == [], r["sent"])
    check("dry_run still reports the intent", "would" in r["out"], r["out"])

    print("\nbootstrap-cf-dns · Converge the Origin Rules")
    body = extract_step(CFDNS, "bootstrap", "Converge the Origin Rules")
    mine = [{"hostname": "api.example.com", "host_header": "svc-as.a.run.app"}]

    r = run_cfdns_rules_step(body, rules=mine)
    rules = r["sent"][0]["body"]["rules"]
    check("the rule sets host_header, origin and sni",
          rules[0]["action_parameters"]["host_header"] == "svc-as.a.run.app"
          and rules[0]["action_parameters"]["origin"]["host"] == "svc-as.a.run.app"
          and rules[0]["action_parameters"]["sni"]["value"] == "svc-as.a.run.app", rules)
    check("hostname becomes an exact-match expression",
          rules[0]["expression"] == '(http.host eq "api.example.com")', rules)

    # THE COEXISTENCE CASE. bootstrap-cf-service splices a per-hostname rule into this same
    # document. Default behaviour must not delete it — the inline predecessor's full-ruleset
    # PUT did exactly that.
    other = {"expression": '(http.host eq "img.example.com")', "action": "route",
             "action_parameters": {"host_header": "img-as.a.run.app"},
             "id": "srv1", "version": "2", "last_updated": "x", "ref": "r"}
    r = run_cfdns_rules_step(body, rules=mine, existing_rules=[other])
    exprs = [x["expression"] for x in r["sent"][0]["body"]["rules"]]
    check("another writer's rule is preserved by default",
          '(http.host eq "img.example.com")' in exprs, exprs)
    kept = [x for x in r["sent"][0]["body"]["rules"]
            if x["expression"] == '(http.host eq "img.example.com")'][0]
    check("server-assigned fields are stripped from the kept rule",
          not any(k in kept for k in ("id", "version", "last_updated", "ref")), kept)

    r = run_cfdns_rules_step(body, rules=mine, existing_rules=[other], prune="true")
    exprs = [x["expression"] for x in r["sent"][0]["body"]["rules"]]
    check("prune deletes the undeclared rule",
          '(http.host eq "img.example.com")' not in exprs, exprs)
    check("prune warns about what it dropped", "::warning::" in r["out"], r["out"])

    # Re-running must refresh in place, not stack a duplicate for the same expression.
    stale = {"expression": '(http.host eq "api.example.com")', "action": "route",
             "action_parameters": {"host_header": "OLD-as.a.run.app"}, "id": "s1"}
    r = run_cfdns_rules_step(body, rules=mine, existing_rules=[stale])
    check("a re-run does not stack a duplicate",
          len(r["sent"][0]["body"]["rules"]) == 1, r["sent"][0]["body"])
    check("a re-run refreshes the stale origin",
          r["sent"][0]["body"]["rules"][0]["action_parameters"]["host_header"]
          == "svc-as.a.run.app", r["sent"][0]["body"])

    r = run_cfdns_rules_step(body, rules=mine, ruleset_exists=False)
    check("a missing entrypoint is created", r["sent"][0]["method"] == "POST", r["sent"])
    check("the created ruleset names the origin phase",
          r["sent"][0]["body"]["phase"] == "http_request_origin", r["sent"][0]["body"])

    r = run_cfdns_rules_step(body, rules=mine, dry="true")
    check("dry_run writes no ruleset", r["sent"] == [], r["sent"])

    # ── cloud-run-update ────────────────────────────────────────────────────
    print("\ncloud-run-update · Validate the inputs")
    body = extract_step(CRUPDATE, "update", "Validate the inputs")

    r = _run_body(body, {"ENV_MODE": "update", "SEC_MODE": "set", "BOOST": ""})
    check("valid modes pass", r["rc"] == 0, r["out"])
    r = _run_body(body, {"ENV_MODE": "merge", "SEC_MODE": "set", "BOOST": ""})
    check("an unknown env_vars_mode is rejected", r["rc"] == 1, r["out"])
    r = _run_body(body, {"ENV_MODE": "set", "SEC_MODE": "set", "BOOST": "yes"})
    check("a non-boolean cpu_boost is rejected", r["rc"] == 1, r["out"])

    print("\ncloud-run-update · Apply the configuration")
    body = extract_step(CRUPDATE, "update", "Apply the configuration")

    # THE CENTRAL PROPERTY: an unset input must not appear at all. A workflow that always
    # sent every flag would reset settings the caller never mentioned to this file's defaults.
    r = run_crupdate_apply_step(body)
    check("a bare run targets the service only",
          r["argv"] == ["run", "services", "update", "svc", "--project=p", "--region=r",
                        "--quiet"], r["argv"])

    r = run_crupdate_apply_step(body, max_inst="5")
    check("only the flag that was set is sent",
          [a for a in r["argv"] if a.startswith("--")]
          == ["--project=p", "--region=r", "--max-instances=5", "--quiet"], r["argv"])

    r = run_crupdate_apply_step(body, cpu="1", memory="512Mi", concurrency="80",
                                min_inst="0", max_inst="3", port="8000",
                                req_timeout="60s", runtime_sa="run@p.iam.gserviceaccount.com")
    for want in ["--cpu=1", "--memory=512Mi", "--concurrency=80", "--min-instances=0",
                 "--max-instances=3", "--port=8000", "--timeout=60s",
                 "--service-account=run@p.iam.gserviceaccount.com"]:
        check(f"{want} is passed", want in r["argv"], r["argv"])

    # cpu_boost is a tri-state string precisely so "leave it alone" is expressible.
    r = run_crupdate_apply_step(body, boost="true")
    check("cpu_boost true sends --cpu-boost", "--cpu-boost" in r["argv"], r["argv"])
    r = run_crupdate_apply_step(body, boost="false")
    check("cpu_boost false sends --no-cpu-boost", "--no-cpu-boost" in r["argv"], r["argv"])
    r = run_crupdate_apply_step(body)
    check("cpu_boost empty sends neither",
          not any("cpu-boost" in a for a in r["argv"]), r["argv"])

    # The delimiter must be chosen, not hardcoded: a CORS method list is full of commas, and
    # a comma-joined --set-env-vars would split it into junk variables.
    r = run_crupdate_apply_step(
        body, env_vars="ALLOW_METHODS=GET,POST,PUT\nREALM=abc", env_mode="set")
    flag = [a for a in r["argv"] if a.startswith("--set-env-vars=")][0]
    check("commas in a value survive",
          flag == "--set-env-vars=^@^ALLOW_METHODS=GET,POST,PUT@REALM=abc", flag)

    # …and when the values themselves contain the first candidate, the next one is used.
    r = run_crupdate_apply_step(body, env_vars="MAIL=a@b.com\nX=1")
    flag = [a for a in r["argv"] if a.startswith("--update-env-vars=")][0]
    check("a value containing @ moves to the next delimiter",
          flag == "--update-env-vars=^#^MAIL=a@b.com#X=1", flag)

    # If every candidate occurs, guessing would corrupt the value — fail instead.
    r = run_crupdate_apply_step(body, env_vars="X=@ #%|~!+")
    check("no usable delimiter fails loudly", r["rc"] == 1, r["out"])
    check("and says why", "delimiter" in r["out"], r["out"])

    r = run_crupdate_apply_step(body, env_vars="A=1", env_mode="update")
    check("update mode merges", any(a.startswith("--update-env-vars=") for a in r["argv"]),
          r["argv"])
    r = run_crupdate_apply_step(body, env_vars="A=1", env_mode="set")
    check("set mode replaces", any(a.startswith("--set-env-vars=") for a in r["argv"]),
          r["argv"])

    r = run_crupdate_apply_step(body, secrets="/configs/.env=issuer-env:latest",
                                sec_mode="set")
    check("secrets are passed in gcloud syntax",
          "--set-secrets=^@^/configs/.env=issuer-env:latest" in r["argv"], r["argv"])

    r = run_crupdate_apply_step(body, clear_env="true", env_vars="A=1")
    check("clear_env_vars precedes the env flags",
          r["argv"].index("--clear-env-vars")
          < min(i for i, a in enumerate(r["argv"]) if "env-vars=" in a and a != "--clear-env-vars"),
          r["argv"])

    # One flag per line: a spec with spaces must arrive as ONE argument, not word-split.
    r = run_crupdate_apply_step(body, extra="--set-cloudsql-instances=p:r:db\n--description=a b c")
    check("extra_args passes each line as one argument",
          "--description=a b c" in r["argv"], r["argv"])
    check("and keeps the other flag", "--set-cloudsql-instances=p:r:db" in r["argv"], r["argv"])

    r = run_crupdate_apply_step(body, max_inst="9", dry="true")
    check("dry_run calls no gcloud", r["argv"] == [], r["argv"])
    check("dry_run prints the command it would run",
          "--max-instances=9" in r["out"], r["out"])


    # ---- validate-alerts: PromQL is executed, not merely linted ----------
    # TODO.md/DECISIONS 2026-09-01: conditionPrometheusQueryLanguage passed the
    # offline lint and was then never run against the API — a green tick from a
    # check that did not check. These pin both halves of the fix.
    lint = extract_step(ALERTS, "validate", "Lint policy files (offline)")

    r = run_alerts_lint_step(lint, {"policy-a.yaml": policy_yaml(PROMQL_COND)})
    check("lint passes a well-formed PromQL policy", r["rc"] == 0, r["out"])
    check("lint reports promql_found", r["outputs"].get("promql_found") == "1", r["outputs"])
    check("lint hands the PromQL query to the exec layer",
          r["promql"] and "automahn_reconciler_runs_total" in r["promql"][0][1], r["promql"])

    r = run_alerts_lint_step(lint, {"policy-a.yaml": policy_yaml(MQL_COND),
                                    "policy-b.yaml": policy_yaml(PROMQL_COND)})
    check("MQL and PromQL are counted separately",
          (r["outputs"].get("mql_found"), r["outputs"].get("promql_found")) == ("1", "1"),
          r["outputs"])

    r = run_alerts_lint_step(lint, {"policy-a.yaml": policy_yaml(
        "  - displayName: promql\n    conditionPrometheusQueryLanguage:\n      duration: 300s\n")})
    check("a PromQL condition with no query fails the lint", r["rc"] != 0, r["out"])

    r = run_alerts_lint_step(lint, {"policy-a.yaml": policy_yaml(
        "  - displayName: promql\n    conditionPrometheusQueryLanguage:\n"
        "      query: up\n      duration: 300\n")})
    check("a non-string PromQL duration fails the lint", r["rc"] != 0, r["out"])

    promql = extract_step(ALERTS, "validate",
                          "Validate PromQL queries against the Monitoring API")
    Q = [("infra/alerts/policy-a.yaml", "up > 0")]

    r = run_promql_step(promql, queries=Q)
    check("a valid PromQL query passes", r["rc"] == 0, r["out"])
    check("promql_checked counts what was executed",
          r["outputs"].get("promql_checked") == "1", r["outputs"])
    check("the query is sent to the Prometheus-compatible endpoint",
          "prometheus/api/v1/query" in r["argv"], r["argv"])
    check("the query travels url-encoded, not spliced into the URL",
          "query=up > 0" in r["argv"] and "--data-urlencode" in r["argv"], r["argv"])

    r = run_promql_step(promql, queries=[], statuses=("200",))
    check("no PromQL queries is not a failure", r["rc"] == 0, r["out"])
    check("and reports zero executed", r["outputs"].get("promql_checked") == "0", r["outputs"])

    r = run_promql_step(promql, queries=Q, statuses=("400",),
                        bodies=['{"status":"error","errorType":"bad_data",'
                                '"error":"parse error: unexpected identifier"}'])
    check("a rejected PromQL query fails the step", r["rc"] != 0, r["out"])
    check("and surfaces the API's own message", "parse error" in r["out"], r["out"])

    # Prometheus can answer 200 with an error envelope; a 2xx must not read as OK.
    r = run_promql_step(promql, queries=Q,
                        bodies=['{"status":"error","error":"execution: bad range"}'])
    check("HTTP 200 with an error envelope still fails", r["rc"] != 0, r["out"])

    # THE PATTERN: never let "could not check" report as "checked and fine".
    r = run_promql_step(promql, queries=Q, statuses=("403",),
                        bodies=['{"error":{"message":"Permission denied"}}'])
    check("403 fails the step rather than passing", r["rc"] != 0, r["out"])
    check("and says the check could not run", "could not run" in r["out"], r["out"])
    check("403 writes no promql_checked at all — 'could not check' is not a count",
          "promql_checked" not in r["outputs"], r["outputs"])

    r = run_promql_step(promql, queries=Q, token="")
    check("a missing access token fails loudly", r["rc"] != 0, r["out"])

    r = run_promql_step(promql, queries=Q * 2, statuses=("200", "400"),
                        bodies=['{"status":"success"}', '{"status":"error","error":"nope"}'])
    check("every query is executed, not just the first", r["calls"] == 2, r["calls"])
    check("one bad query among many fails the step", r["rc"] != 0, r["out"])


    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
