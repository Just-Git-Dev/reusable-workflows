"""H8: each listed commit's own CI must be green before the run writes anything.

Per listed repo and per workflow in services.json `ci`, the newest push run for that exact sha
(`actions/workflows/{file}/runs?head_sha=SHA&event=push`) must be completed/success. In
progress is a failure ("not finished yet"), not a wait. A workflow with a push path filter
may have NO run at the sha. The filter is read from the workflow file at the sha
(`on.push.paths` / `on.push.paths-ignore`), never trusted from services.json. Then walk the
first-parent ancestors (up to MAX_WALK) to the nearest commit that has a run, require that run
to be green, and require of every file changed between it and the sha:
  paths-ignore: it matches a glob (so the push was rightly skipped);
  paths: it is NOT selected (globs in order, last match wins, `!` excludes).
No run and no filter is "missing". A trigger that cannot be read or is not modelled fails
closed with the reason. A services.json `paths_ignore`, when declared, must equal the file's
`paths-ignore` exactly. All failures are collected, and the number of (repo, workflow) pairs
examined is returned: a check that examined nothing proves nothing, so the caller treats 0 as
a failure.
"""

from __future__ import annotations

import base64
import re

import gh

MAX_WALK = 20
COMPARE_FILE_CAP = 300  # GitHub truncates compare's file list here; beyond it we cannot verify


class TriggerError(Exception):
    """The push trigger could not be read or is a form this module does not model."""


def glob_match(pattern, path):
    """GitHub path-filter globs: `*` and `?` stay inside one path segment, `**` crosses `/`."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.fullmatch("".join(out), path, re.S) is not None


def selected(globs, path):
    """Does a `paths` filter select `path`? Patterns in order; the last match decides, and a
    `!` pattern that matches deselects (GitHub's rule)."""
    hit = False
    for g in globs:
        if g.startswith("!"):
            if glob_match(g[1:], path):
                hit = False
        elif glob_match(g, path):
            hit = True
    return hit


def _load_yaml(text):
    try:
        import yaml  # lazy: only a trigger read needs it, like spec-compat / ops-subset
    except ImportError as e:
        raise TriggerError("PyYAML is not installed; it is needed to read the path filter") \
            from e
    from ops_subset import _spec_loader  # YAML 1.2 booleans: the key `on` stays "on", not True
    try:
        return yaml.load(text, Loader=_spec_loader(yaml))  # noqa: S506 (a SafeLoader subclass)
    except yaml.YAMLError as e:
        raise TriggerError(f"the workflow file is not valid YAML: {e}") from e


def _push_filter(reader, base, wf, sha):
    """-> ("paths" | "paths-ignore" | None, globs): the push path filter of `wf` at `sha`.
    Raises TriggerError for anything it cannot read or does not model: fail closed."""
    path = f".github/workflows/{wf}"
    status, data = reader.get(f"{base}/contents/{path}?ref={sha}")
    if not 200 <= status < 300 or not isinstance(data, dict) or "content" not in data:
        raise TriggerError(f"cannot read {path} at this commit (HTTP {status})")
    doc = _load_yaml(base64.b64decode(data["content"]).decode("utf-8", "replace"))
    on = doc.get("on") if isinstance(doc, dict) else None
    if isinstance(on, str):
        on = [on]
    if isinstance(on, list):  # `on: push` / `on: [push, ...]`: push with no filter
        if "push" not in on:
            raise TriggerError(f"push is not a trigger (on: {on})")
        return None, ()
    if not isinstance(on, dict) or "push" not in on:
        raise TriggerError("push is not a trigger")
    push = on["push"] if on["push"] is not None else {}
    if not isinstance(push, dict):
        raise TriggerError(f"on.push is not a mapping: {push!r}")
    if ({"tags", "tags-ignore"} & set(push)) and not ({"branches", "branches-ignore"} & set(push)):
        raise TriggerError("on.push filters tags only, so a branch push never runs it")
    kinds = [k for k in ("paths", "paths-ignore") if k in push]
    if len(kinds) > 1:
        raise TriggerError("on.push sets both paths and paths-ignore")
    if not kinds:
        return None, ()
    kind, globs = kinds[0], push[kinds[0]]
    if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
        raise TriggerError(f"on.push.{kind} is not a list of strings: {globs!r}")
    if kind == "paths-ignore" and any(g.startswith("!") for g in globs):
        raise TriggerError("a `!` pattern in on.push.paths-ignore is not modelled")
    return kind, tuple(globs)


def _newest_run(reader, base, wf, sha):
    data = reader.get_ok(f"{base}/actions/workflows/{wf}/runs?head_sha={sha}&event=push")
    runs = sorted(data.get("workflow_runs", []), key=lambda r: r.get("created_at", ""),
                  reverse=True)
    return runs[0] if runs else None


def _verdict(run, label):
    """None if green, else the failure text."""
    if run.get("status") != "completed":
        return f"{label}: not finished yet: {run.get('html_url')}"
    if run.get("conclusion") != "success":
        return f"{label}: {run.get('conclusion')}: {run.get('html_url')}"
    return None


def filter_key(repo, wf, sha):
    return f"{repo}/{wf}@{sha}"


def _check_one(reader, base, repo, sha, wf, declared, get_filter):
    """`declared` is services.json's paths_ignore (a tuple), or None when it declares none."""
    label = f"{repo}@{sha[:8]} {wf}"
    run = _newest_run(reader, base, wf, sha)
    if run and declared is None:
        return _verdict(run, label)  # the filter cannot matter: no file read
    try:
        kind, globs = get_filter(wf)
    except TriggerError as ex:
        return f"{label}: cannot use the push trigger: {ex}"
    if declared is not None:
        got = list(globs) if kind == "paths-ignore" else None
        if got != list(declared):
            return (f"{label}: services.json paths_ignore {list(declared)} does not match the "
                    f"workflow's on.push.paths-ignore {got}; drop paths_ignore from "
                    "services.json (the workflow file is read) or make them equal")
    if run:
        return _verdict(run, label)
    if kind is None:
        return f"{label}: missing (no push run at this commit)"
    cur = sha
    for _ in range(MAX_WALK):
        parents = reader.get_ok(f"{base}/commits/{cur}").get("parents") or []
        if not parents:
            return f"{label}: no run found and the history ends (root commit)"
        cur = parents[0]["sha"]
        run = _newest_run(reader, base, wf, cur)
        if not run:
            continue
        bad = _verdict(run, f"{label} (ancestor {cur[:8]})")
        if bad:
            return bad
        files = [f["filename"] for f in
                 reader.get_ok(f"{base}/compare/{cur}...{sha}").get("files", [])]
        if len(files) >= COMPARE_FILE_CAP:
            return f"{label}: {len(files)}+ changed files since ancestor {cur[:8]}; cannot verify"
        for name in files:
            if kind == "paths-ignore" and not any(glob_match(g, name) for g in globs):
                return (f"{label}: no run at the commit and {name} (changed since green ancestor "
                        f"{cur[:8]}) is not covered by paths-ignore {list(globs)}")
            if kind == "paths" and selected(globs, name):
                return (f"{label}: no run at the commit and {name} (changed since green ancestor "
                        f"{cur[:8]}) is selected by paths {list(globs)}, so it should have run")
        return None
    return f"{label}: no run found within {MAX_WALK} first-parent ancestors"


def _filter_source(reader, base, repo, sha, handed, read):
    """-> get_filter(wf). With `handed` (drafts: {filter_key: {kind, globs}} from plan) the
    filter comes only from it and a missing key fails closed, so a write job never parses YAML.
    Otherwise it is read from the file and recorded in `read` (plan hands it on). A file at a
    fixed sha cannot change, so plan's reading is still the truth at drafts time."""
    def get_filter(wf):
        key = filter_key(repo, wf, sha)
        if handed is not None:
            f = handed.get(key)
            if not isinstance(f, dict) or f.get("kind") not in ("paths", "paths-ignore", None) \
                    or not isinstance(f.get("globs"), list) \
                    or not all(isinstance(g, str) for g in f["globs"]):
                raise TriggerError(f"plan handed over no usable filter for {key}")
            return f["kind"], tuple(f["globs"])
        kind, globs = _push_filter(reader, base, wf, sha)
        if read is not None:
            read[key] = {"kind": kind, "globs": list(globs)}
        return kind, globs
    return get_filter


def check(reader, cfg, entries, handed=None, read=None):
    """-> (failures, examined). `handed` / `read`: see _filter_source."""
    failures, examined = [], 0
    for e in entries:
        svc = cfg.service(e.repo)
        if svc is None or not svc.ci:
            failures.append(f"{e.repo}: no CI workflows configured in services.json")
            continue
        base = f"repos/{cfg.owner}/{e.repo}"
        get_filter = _filter_source(reader, base, e.repo, e.sha, handed, read)
        for wf, ignore in svc.ci:
            examined += 1
            try:
                bad = _check_one(reader, base, e.repo, e.sha, wf, ignore, get_filter)
            except gh.GitHubError as ex:
                bad = f"{e.repo}@{e.sha[:8]} {wf}: cannot read CI state: {ex}"
            if bad:
                failures.append(bad)
    return failures, examined
