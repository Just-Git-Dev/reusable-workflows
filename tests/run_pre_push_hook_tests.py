#!/usr/bin/env python3
"""The pre-push hook must gate the COMMIT BEING PUSHED, and must not leak git's env into checks.

`make ci` reads the working tree. A hook that just runs it validates whatever is checked out,
which can differ from the sha being pushed; so the hook refuses a dirty tree and a pushed ref
whose sha is not HEAD. It also unsets every `git rev-parse --local-env-vars` name, because a
test that calls git inside a hook otherwise acts on the hooked repo.

Usage:  python3 tests/run_pre_push_hook_tests.py
"""
import os
import subprocess
import sys
import tempfile

HOOK = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", ".githooks", "pre-push"))
ZERO = "0" * 40


def _clean_env(**extra):
    out = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True)
    env = {k: v for k, v in os.environ.items() if k not in out.stdout.split()}
    env.update(extra)
    return env


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                          env=_clean_env(GIT_CONFIG_GLOBAL="/dev/null"), check=True).stdout.strip()


def repo():
    d = tempfile.mkdtemp()
    git(d, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(d, "config", k, v)
    for name in ("a", "b"):
        with open(os.path.join(d, name), "w") as fh:
            fh.write(name)
        git(d, "add", name)
        git(d, "commit", "-q", "-m", name)
    return d


def fake_make(gate):
    """A dir holding a `make` that runs `gate` instead of the real suite. The hook has no env
    seam for replacing its gate (a stray `PRE_PUSH_GATE=true git push` must not skip it), so the
    tests put this first on PATH instead."""
    b = tempfile.mkdtemp()
    path = os.path.join(b, "make")
    with open(path, "w") as fh:
        fh.write(f"#!/usr/bin/env bash\n{gate}\n")
    os.chmod(path, 0o755)
    return b


def hook(d, stdin, gate="true", **env):
    assert os.path.exists(HOOK), "no .githooks/pre-push"
    e = _clean_env(**env)
    e["PATH"] = fake_make(gate) + os.pathsep + e["PATH"]
    return subprocess.run([HOOK], cwd=d, input=stdin, capture_output=True, text=True, env=e)


def push(d, ref, gate="true"):
    """A real `git push` of `ref` to a local bare remote with the hook installed."""
    bare = tempfile.mkdtemp()
    git(bare, "init", "-q", "--bare")
    git(d, "config", "core.hooksPath", os.path.dirname(HOOK))
    e = _clean_env(GIT_CONFIG_GLOBAL="/dev/null")
    e["PATH"] = fake_make(gate) + os.pathsep + e["PATH"]
    return subprocess.run(["git", "-C", d, "push", bare, ref], capture_output=True, text=True, env=e)


def test_annotated_tag_at_head_passes():
    """`git tag -a` pushes a tag OBJECT whose sha is never HEAD's; it must be peeled to its commit."""
    d = repo()
    git(d, "tag", "-a", "v1.0.0", "-m", "release")
    r = push(d, "refs/tags/v1.0.0")
    assert r.returncode == 0, r.stderr


def test_annotated_tag_at_another_commit_is_refused():
    d = repo()
    git(d, "tag", "-a", "v0.9.0", "-m", "old", "HEAD~1")
    r = push(d, "refs/tags/v0.9.0")
    assert r.returncode != 0 and "HEAD is" in r.stderr


def test_a_stray_pre_push_gate_env_var_does_not_replace_the_gate():
    d = repo()
    head = git(d, "rev-parse", "HEAD")
    r = hook(d, f"refs/heads/main {head} refs/heads/main {ZERO}\n", gate="false", PRE_PUSH_GATE="true")
    assert r.returncode == 1 and "gate FAILED" in r.stderr


def test_passes_when_clean_head_and_gate_green():
    d = repo()
    head = git(d, "rev-parse", "HEAD")
    assert hook(d, f"refs/heads/main {head} refs/heads/main {ZERO}\n").returncode == 0


def test_gate_failure_blocks_the_push():
    d = repo()
    head = git(d, "rev-parse", "HEAD")
    r = hook(d, f"refs/heads/main {head} refs/heads/main {ZERO}\n", gate="false")
    assert r.returncode == 1 and "gate FAILED" in r.stderr


def test_refuses_a_pushed_ref_that_is_not_head():
    d = repo()
    older = git(d, "rev-parse", "HEAD~1")
    r = hook(d, f"refs/heads/old {older} refs/heads/old {ZERO}\n")
    assert r.returncode == 1 and "HEAD is" in r.stderr


def test_refuses_a_dirty_tree():
    d = repo()
    head = git(d, "rev-parse", "HEAD")
    with open(os.path.join(d, "a"), "w") as fh:
        fh.write("changed")
    r = hook(d, f"refs/heads/main {head} refs/heads/main {ZERO}\n")
    assert r.returncode == 1 and "dirty" in r.stderr


def test_branch_deletion_needs_no_gate():
    d = repo()
    assert hook(d, f"(delete) {ZERO} refs/heads/x abc\n", gate="false").returncode == 0


def test_git_env_is_scrubbed_before_the_gate_runs():
    d = repo()
    head = git(d, "rev-parse", "HEAD")
    gate = 'test -z "${GIT_DIR:-}" && test -z "${GIT_INDEX_FILE:-}"'
    r = hook(d, f"refs/heads/main {head} refs/heads/main {ZERO}\n", gate=gate,
             GIT_DIR=os.path.join(d, ".git"), GIT_INDEX_FILE=os.path.join(d, ".git", "index"))
    assert r.returncode == 0, r.stderr


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests, "no tests collected"
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
    print(f"pre-push hook: {len(tests) - failed} of {len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
