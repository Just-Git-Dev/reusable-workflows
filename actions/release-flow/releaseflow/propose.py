"""`release-flow propose`: wait for the service gates, validate, write ONE manifest, open the
root release PR, and enable auto-merge only when the PR check is a required check.

A LOCAL command (docs/release-flow.md, "Proposing a release"). Everything before the push only
reads. The commit is built with git plumbing (blob, temporary index, tree, commit-tree) from
origin/<base> plus the one manifest, so the working tree, index and HEAD are never touched.

Side effects are injected through `deps` (all optional, real defaults): transport, runner,
clock, sleep, today, out. Stdlib only.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import time
import urllib.parse

import config as config_mod
import gh
import manifest as manifest_mod
import validate

POLL_S = 20
MAX_READ_ERRORS = 5
PRINT_EVERY_S = 60
INDEX_NAME = "release-flow-propose.index"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")
# Inherited by a git hook / wrapper; would redirect every git call to the wrong repo or index.
# Every name `git rev-parse --local-env-vars` lists, GIT_NAMESPACE, and the GIT_CONFIG_KEY_n /
# GIT_CONFIG_VALUE_n pairs (_SCRUB_RE); docs/release-flow.md step 2.
_SCRUB = ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS",
          "GIT_CONFIG_COUNT", "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE",
          "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS",
          "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE", "GIT_COMMON_DIR",
          "GIT_NAMESPACE")
_SCRUB_RE = re.compile(r"^GIT_CONFIG_(KEY|VALUE)_\d+$")


class Stop(Exception):
    """End the command with `code`, after printing `msg` (if any)."""

    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.code = code


def add_arguments(p):
    p.add_argument("targets", nargs="+", metavar="REPO@TAG")
    p.add_argument("--slug", required=True)
    p.add_argument("--allowed", required=True)
    p.add_argument("--config", default="releases/services.json")
    p.add_argument("--root", help="owner/name of the root repo (default: gh repo view)")
    p.add_argument("--pr-check", default="release-pr / release-pr")
    p.add_argument("--gate-check", default="release-gate")
    p.add_argument("--wait-min", type=int, default=30)
    p.add_argument("--no-auto-merge", action="store_true")
    p.add_argument("--merge-method", choices=("squash", "merge", "rebase"), default="squash")
    p.add_argument("--dry-run", action="store_true")


def _default_runner(argv, env=None, input=None):
    try:
        r = subprocess.run(argv, env=env, input=input, capture_output=True, text=True)
    except OSError as ex:
        return 127, "", str(ex)
    return r.returncode, r.stdout, r.stderr


def _default_today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


class _Ctx:
    def __init__(self, args, env, deps):
        self.args = args
        self.env = {k: v for k, v in env.items() if k not in _SCRUB and not _SCRUB_RE.match(k)}
        self.runner = deps.get("runner") or _default_runner
        self.clock = deps.get("clock") or time.monotonic
        self.sleep = deps.get("sleep") or time.sleep
        self.today = deps.get("today") or _default_today
        self.out = deps.get("out") or print
        self._transport = deps.get("transport")

    def git(self, *argv, input=None, extra_env=None):
        env = {**self.env, **(extra_env or {})}
        return self.runner(["git", *argv], env=env, input=input)

    def must(self, argv, what, input=None, extra_env=None):
        rc, out, err = self.runner(argv, env={**self.env, **(extra_env or {})}, input=input)
        if rc != 0:
            raise gh.GitHubError(f"{what} failed (rc={rc}): {(err or out).strip()[:300]}")
        return out.strip()

    def reader(self):
        if self._transport is None:
            token = self.env.get("RELEASE_FLOW_READ_TOKEN")
            if not token:
                rc, out, err = self.runner(["gh", "auth", "token"], env=self.env)
                token = out.strip()
                if rc != 0 or not token:
                    raise Stop(2, "error: no token: set RELEASE_FLOW_READ_TOKEN or run "
                                  f"gh auth login ({err.strip()[:200]})")
            self._transport = gh.urllib_transport(token)
        return gh.Reader(self._transport)


def run(args, env, deps) -> int:
    ctx = _Ctx(args, env, deps or {})
    try:
        return _run(ctx)
    except Stop as s:
        if str(s):
            ctx.out(str(s))
        return s.code
    except (config_mod.ConfigError, manifest_mod.ManifestError) as ex:
        ctx.out(f"error: {ex}")
        return 2
    except gh.GitHubError as ex:
        ctx.out(f"GitHub error: {ex}")
        return 3


# --- steps ---------------------------------------------------------------------------------
def _parse_targets(args, cfg, allowed):
    if not SLUG_RE.match(args.slug):
        raise Stop(2, f"error: --slug {args.slug!r} must match [a-z0-9][a-z0-9-]* "
                      "(no dots, underscores or upper case)")
    if args.wait_min < 0:
        raise Stop(2, "error: --wait-min must be >= 0")
    wanted = []
    for t in args.targets:
        repo, sep, tag = t.partition("@")
        if not sep or not repo or validate.semver(tag) is None:
            raise Stop(2, f"error: {t!r} is not REPO@vX.Y.Z")
        if repo not in allowed:
            raise Stop(2, f"error: {repo} is not in --allowed {sorted(allowed)}")
        if cfg.service(repo) is None:
            raise Stop(2, f"error: {repo} is not in services.json")
        if any(r == repo for r, _ in wanted):
            raise Stop(2, f"error: {repo} is listed twice")
        wanted.append((repo, tag))
    order = {s.repo: i for i, s in enumerate(cfg.services)}
    return sorted(wanted, key=lambda rt: order[rt[0]])      # services.json order


def _root_repo(ctx, cfg):
    root = ctx.args.root
    if not root:
        rc, out, err = ctx.runner(["gh", "repo", "view", "--json", "nameWithOwner"],
                                  env=ctx.env)
        try:
            root = json.loads(out)["nameWithOwner"] if rc == 0 else None
        except (ValueError, KeyError, TypeError):
            root = None
        if not root:
            raise Stop(2, "error: cannot detect the root repo (gh repo view failed: "
                          f"{err.strip()[:200]}); run inside the root checkout or pass --root")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", root):
        raise Stop(2, f"error: --root {root!r} is not owner/name")
    if root.split("/")[0] != cfg.owner:
        raise Stop(2, f"error: root repo owner {root.split('/')[0]!r} is not services.json "
                      f"owner {cfg.owner!r}")
    return root


_ORIGIN_RES = (
    re.compile(r"https://github\.com/([^/\s]+/[^/\s]+?)(?:\.git)?/?\Z", re.I),
    re.compile(r"git@github\.com:([^/\s]+/[^/\s]+?)(?:\.git)?\Z", re.I),
    re.compile(r"ssh://git@github\.com/([^/\s]+/[^/\s]+?)(?:\.git)?\Z", re.I))


def _check_origin(ctx, root):
    """Exit 2 unless `origin` names the root repo (a fork checkout must not be pushed to)."""
    rc, out, err = ctx.git("remote", "get-url", "origin")
    url = out.strip()
    if rc != 0:
        raise Stop(2, f"error: git remote get-url origin failed: {err.strip()[:200]}")
    for rx in _ORIGIN_RES:
        m = rx.match(url)
        if m:
            if m.group(1).lower() == root.lower():
                return
            raise Stop(2, f"error: origin is {m.group(1)}, not the root repo {root}; "
                          "run propose inside a checkout of the root repo")
    raise Stop(2, f"error: cannot read an owner/name from the origin URL {url!r} "
                  f"(expected an https or ssh github.com URL of {root})")


def _resolve_tags(ctx, reader, cfg, wanted):
    """-> [Entry]; exit 1 listing every tag that is missing or not annotated."""
    entries, bad = [], []
    for repo, tag in wanted:
        base = f"repos/{cfg.owner}/{repo}"
        status, ref = reader.get(f"{base}/git/ref/tags/{tag}")
        if status == 404:
            bad.append(f"FAIL: {repo}: tag {tag} does not exist (push the annotated tag first)")
            continue
        if status != 200 or not isinstance(ref, dict):
            raise gh.GitHubError(f"GET {base}/git/ref/tags/{tag}: HTTP {status}", status)
        obj = ref.get("object") or {}
        if obj.get("type") != "tag":
            bad.append(f"FAIL: {repo}: tag {tag} is not annotated; re-push it with git tag -a")
            continue
        status, tobj = reader.get(f"{base}/git/tags/{obj.get('sha')}")
        target = (tobj or {}).get("object") if status == 200 and isinstance(tobj, dict) else None
        if not target or target.get("type") != "commit":
            bad.append(f"FAIL: {repo}: cannot peel tag {tag} to a commit (HTTP {status})")
            continue
        entries.append(manifest_mod.Entry(repo, tag, target["sha"]))
        ctx.out(f"tag: {repo} {tag} -> {target['sha'][:12]} (annotated)")
    if bad:
        for b in bad:
            ctx.out(b)
        raise Stop(1, "nothing was written")
    return entries


def _read_gate(reader, owner, e, gate_check):
    """-> (state, conclusion, run_or_None) for the newest github-actions run of the gate."""
    q = urllib.parse.quote(gate_check, safe="")
    status, data = reader.get(f"repos/{owner}/{e.repo}/commits/{e.sha}/check-runs"
                              f"?check_name={q}&filter=all&per_page=100")
    if status >= 500:
        return None
    if status != 200 or not isinstance(data, dict):
        raise gh.GitHubError(f"GET check-runs for {e.repo}@{e.sha[:12]}: HTTP {status}", status)
    runs = [r for r in data.get("check_runs") or []
            if (r.get("app") or {}).get("slug") == "github-actions"]
    if not runs:
        return "not started", None, None
    newest = max(runs, key=lambda r: (r.get("started_at") or "", r.get("id") or 0))
    return newest.get("status") or "unknown", newest.get("conclusion"), newest


def _wait_gates(ctx, reader, cfg, entries):
    """Poll until every gate finished green; -> {repo: run}. Exit 1 red / timeout."""
    a = ctx.args
    t0 = ctx.clock()
    deadline = t0 + a.wait_min * 60
    done, last = {}, {}                  # last: repo -> (state, printed_at)
    errors = 0
    while True:
        round_failed = False
        for e in entries:
            if e.repo in done:
                continue
            try:
                got = _read_gate(reader, cfg.owner, e, a.gate_check)
            except gh.GitHubError as ex:
                if ex.status and ex.status < 500:
                    raise
                got = None               # network error: retry on the next poll
            if got is None:
                round_failed = True
                continue
            state, conclusion, run_ = got
            url = (run_ or {}).get("html_url", "")
            now = ctx.clock()
            if state == "completed":
                if conclusion != "success":
                    raise Stop(1, f"gate red: {e.repo} {e.version} {a.gate_check} "
                                  f"{conclusion} {url}: fix it and push a new tag; "
                                  "nothing was written")
                ctx.out(f"gate: {e.repo} {e.version} {a.gate_check} success {url}")
                done[e.repo] = run_
                continue
            prev = last.get(e.repo)
            if prev is None or prev[0] != state or now - prev[1] >= PRINT_EVERY_S:
                m, s = divmod(int(now - t0), 60)
                ctx.out(f"gate: {e.repo} {e.version} {a.gate_check} {state} "
                        f"({m}m{s:02d}s) {url}".rstrip())
                last[e.repo] = (state, now)
        errors = errors + 1 if round_failed else 0
        if errors >= MAX_READ_ERRORS:
            raise gh.GitHubError(f"gate read failed {MAX_READ_ERRORS} polls in a row")
        if len(done) == len(entries):
            return done
        if ctx.clock() >= deadline:
            pending = ", ".join(f"{e.repo} {e.version} ({last.get(e.repo, ('unknown',))[0]})"
                                for e in entries if e.repo not in done)
            raise Stop(1, f"gate not finished after {a.wait_min} min: {pending}; "
                          "run propose again, nothing was written")
        ctx.sleep(POLL_S)


def _manifest_text(cfg, entries):
    lines = ["# Release manifest, written by `release-flow propose`.", "services:"]
    lines += [f"  - {{repo: {e.repo}, version: {e.version}, sha: {e.sha}}}" for e in entries]
    text = "\n".join(lines) + "\n"
    if [tuple(x) for x in manifest_mod.parse(text)] != [tuple(x) for x in entries]:
        raise manifest_mod.ManifestError("generated manifest does not parse back to the entries")
    return text


def _required_checks(reader, root, base):
    """-> (set_of_contexts, [read problems]). Classic protection AND rulesets."""
    found, problems = set(), []
    status, data = reader.get(f"repos/{root}/branches/{base}/protection/required_status_checks")
    if status == 200 and isinstance(data, dict):
        found.update(c for c in data.get("contexts") or [] if isinstance(c, str))
        found.update(c.get("context") for c in data.get("checks") or [] if isinstance(c, dict))
    else:
        problems.append(f"branch protection: HTTP {status}")
    status, data = reader.get(f"repos/{root}/rules/branches/{base}")
    if status == 200 and isinstance(data, list):
        for rule in data:
            if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
                for c in (rule.get("parameters") or {}).get("required_status_checks") or []:
                    if isinstance(c, dict):
                        found.add(c.get("context"))
    else:
        problems.append(f"rulesets: HTTP {status}")
    return found, problems


def _auto_merge_decision(ctx, reader, root, base):
    """-> (enable: bool, line: str). Fail safe: any doubt means off."""
    check = ctx.args.pr_check
    try:
        found, problems = _required_checks(reader, root, base)
    except gh.GitHubError as ex:
        return False, (f"auto-merge: off (cannot read required checks on {base}: {ex}); "
                       "merge by hand once it is green")
    if check in found:
        return True, f"auto-merge: on ({check} is required on {base})"
    if problems:
        return False, (f"auto-merge: off (cannot confirm {check} is required on {base}: "
                       f"{'; '.join(problems)}); merge by hand once it is green")
    return False, (f"auto-merge: off ({check} is not a required check on {base}, so --auto "
                   "would merge at once untested); merge by hand once it is green")


def _pr_text(entries, gates):
    title = "release: " + ", ".join(f"{e.repo} {e.version}" for e in entries)
    body = ["Release manifest proposed by `release-flow propose`.", ""]
    for e in entries:
        body.append(f"- {e.repo} {e.version}: sha {e.sha}, gate {gates[e.repo].get('html_url')}")
    return title, "\n".join(body) + "\n"


def _run(ctx):
    a, out = ctx.args, ctx.out
    cfg = config_mod.load(a.config)
    allowed = config_mod.parse_allowed(a.allowed)
    cfg.restrict(allowed)
    wanted = _parse_targets(a, cfg, allowed)
    date = ctx.today()
    path = f"{cfg.release_dir}/{date}-{a.slug}.yaml"
    if not manifest_mod.path_ok(path, cfg.release_dir):
        raise Stop(2, f"error: manifest path {path} is not "
                      f"{cfg.release_dir}/YYYY-MM-DD-<slug>.yaml")
    branch = f"release/{date}-{a.slug}"
    base = cfg.base_branch

    root = _root_repo(ctx, cfg)
    _check_origin(ctx, root)
    ctx.must(["git", "fetch", "origin", base], "git fetch")
    base_sha = ctx.must(["git", "rev-parse", f"origin/{base}"], "git rev-parse")
    rc, _, _ = ctx.git("cat-file", "-e", f"{base_sha}:{path}")
    if rc == 0:
        raise Stop(2, f"error: {path} already exists on origin/{base}; pick another --slug")
    rc, listing, err = ctx.git("ls-remote", "--heads", "origin", branch)
    if rc != 0:
        raise gh.GitHubError(f"git ls-remote failed: {err.strip()[:200]}")
    if listing.strip():
        raise Stop(2, f"error: branch {branch} already exists on origin; pick another --slug")
    out(f"propose: root {root}, base {base}, manifest {path}")

    reader = ctx.reader()
    entries = _resolve_tags(ctx, reader, cfg, wanted)
    gates = _wait_gates(ctx, reader, cfg, entries)

    failures = validate.validate_manifest(reader, cfg, entries)
    out(f"validate: {len(entries)} service(s), {len(failures)} failure(s)")
    if failures:
        for f in failures:
            out(f"FAIL: {f}")
        raise Stop(1, "nothing was written")

    text = _manifest_text(cfg, entries)
    title, body = _pr_text(entries, gates)

    if a.dry_run:
        out(f"--- {path}")
        out(text.rstrip("\n"))
        out("---")
        out(f"branch: {branch} (from origin/{base} @ {base_sha[:12]})")
        out("would run: git hash-object -w --stdin; git read-tree/update-index/write-tree on "
            f"a temporary index ({INDEX_NAME}); git commit-tree; "
            f"git push origin <commit>:refs/heads/{branch}")
        out(f"would run: gh pr create --repo {root} --base {base} --head {branch} "
            f"--title {title!r}")
        if a.no_auto_merge:
            out("auto-merge: off (--no-auto-merge)")
        else:
            enable, line = _auto_merge_decision(ctx, reader, root, base)
            out(line.replace("auto-merge: on", "auto-merge: would be on", 1) if enable else line)
        raise Stop(0, "dry run: nothing was written")

    blob = ctx.must(["git", "hash-object", "-w", "--stdin"], "git hash-object", input=text)
    index = os.path.abspath(ctx.must(["git", "rev-parse", "--git-path", INDEX_NAME],
                                     "git rev-parse --git-path"))   # may be relative to cwd
    ienv = {"GIT_INDEX_FILE": index}
    try:
        os.remove(index)                 # a stale index from a failed run
    except OSError:
        pass
    ctx.must(["git", "read-tree", base_sha], "git read-tree", extra_env=ienv)
    ctx.must(["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}"],
             "git update-index", extra_env=ienv)
    tree = ctx.must(["git", "write-tree"], "git write-tree", extra_env=ienv)
    try:
        os.remove(index)
    except OSError:
        pass
    commit = ctx.must(["git", "commit-tree", tree, "-p", base_sha, "-m", title],
                      "git commit-tree")
    ctx.must(["git", "push", "origin", f"{commit}:refs/heads/{branch}"], "git push")
    out(f"pushed: {branch} @ {commit[:12]}")
    pr = ctx.must(["gh", "pr", "create", "--repo", root, "--base", base, "--head", branch,
                   "--title", title, "--body", body], "gh pr create")
    lines = [ln.strip() for ln in pr.splitlines() if ln.strip()]
    url = lines[-1] if lines else ""
    if not re.fullmatch(rf"https://github\.com/{re.escape(root)}/pull/\d+", url, re.I):
        raise gh.GitHubError(f"gh pr create printed no pull request URL of {root} "
                             f"(last line: {url[:200]!r}); the PR may exist, check by hand")
    out(f"PR opened: {url}")

    if a.no_auto_merge:
        out("auto-merge: off (--no-auto-merge); merge by hand once it is green")
        return 0
    enable, line = _auto_merge_decision(ctx, reader, root, base)
    if not enable:
        out(line)
        return 0
    rc, _, err = ctx.runner(["gh", "pr", "merge", url, "--auto", f"--{a.merge_method}"],
                            env=ctx.env)
    if rc != 0:
        reason = ((err or "").strip().splitlines() or ["unknown error"])[0]
        out(f"auto-merge: off (gh pr merge failed: {reason}); "
            f"run: ! gh pr merge {url} --auto --{a.merge_method}")
        return 0
    out(line)
    return 0
