#!/usr/bin/env python3
"""release-flow release-PR flow driver. The workflows are thin; the logic is here and unit-tested.

Subcommands (M = path to the release manifest; every command that touches a manifest or
services.json also needs `--allowed core,gateway,web,site`, a list HARD-CODED in the
workflow, so editing services.json cannot widen what the write token touches; `--config`
defaults to releases/services.json in the CURRENT DIRECTORY):

  config-check --allowed A [--read-only R]   loads the config; refuses a repo outside A, (only
                                           when --read-only is given, even as "") a
                                           consumers_only repo outside R, an owner other than
                                           GITHUB_REPOSITORY_OWNER; prints one compact JSON line
                                           {owner, release_dir, base_branch}.   no token
  find-manifest --base B --head H [--pr]   git diff --name-status B H over the WHOLE tree; the
                                           one added <release_dir>/*.yaml is printed; ANY other
                                           change (or 0/2+ manifests) fails. Same rule for the
                                           PR (--pr) and the merge run (before..after). The
                                           config must be readable (exit 2 otherwise).
  check-merge --sha S --check-name N [--workflow-path P]
                                           S must belong to exactly one MERGED PR into the
                                           config's base_branch whose head's check run N
                                           (from workflow P, default
                                           .github/workflows/release-pr.yml) concluded
                                           success. Needs GITHUB_REPOSITORY. A direct push fails.
  verdict --stage drafts|publish --needs-file F --contracts-job J [--required a,b] --allowed A
                                           [--manifest-file M]
                                           F = GitHub's toJSON(needs). M = the manifest the plan
                                           stage staged (read instead of the repo path; its
                                           sha256 must equal plan's manifest-sha256 output).
                                           Prints one compact JSON
                                           line {ok, rehearsal, manifest, manifest_sha256, pr,
                                           order, failed_stage, failures}; exit 0 ok, 1 not ok, 2
                                           unreadable input.   no token
  concurrent --workflow W --run-id ID      fail if another run of W in the root repo is
                                           queued/in_progress/waiting/pending.
  validate M       all PR/merge checks, every failure listed.   read token
  ci-green M       H8: each listed sha's own CI (services.json `ci`) must be completed/success;
                   exit 1 on any failure or 0 examined; stderr says "examined N".  read token.
                   `drafts` runs the same check in its pre-check, before any write.
  resolve M [--drafts-proof REPO:TAG]
                   JSON {repo: {ref, version, listed, image, live_ref}} incl. consumers_only.
                   live_ref of a deployable repo comes from its successful Deploy runs (see
                   resolve.py); unlisted ref = live_ref. tool's live_ref = highest tag not on a
                   DRAFT release, which needs a token that sees drafts: with --drafts-proof the
                   draft REPO:TAG (just created by `drafts`; REPO in --allowed) must be
                   visible, else exit 1; without it, repo permissions.push must be true.
                   read token (the App token that sees drafts)
  contract-states M [--drafts-proof REPO:TAG]
                   JSON list for a Actions matrix `include`: [{consumer, consumer_ref,
                   provider, provider_ref, states:[labels]}] over every intermediate state of
                   the publish order (states.py). [] is valid (stderr says why).
  order M          listed repos in services.json order, one per line. More than
                   MAX_PUBLISH_SLOTS (6) is refused (exit 2).
  gate-services M  one compact JSON line [{"repo":"consumer-a-org/X","tag":"vX.Y.Z","sha":<40hex>}]
                   for the LISTED services, in publish order: the input of the service-gates
                   job's check-release-gate action. An empty list is an error.   no token
  drafts M [--check-only]
                   validate everything (tag exists, annotated, peels to the sha), then a DRAFT
                   release per repo for the existing tag; creates NO tag and NO ref. Prints
                   {repo: release_id} JSON (also on failure: what exists).   write token
                   --check-only runs every pre-check and nothing else (no Writer is built),
                   prints {repo: "rehearsal"}.   read token only
  publish M --repo X   publish ONE repo's draft, wait for Deploy (+health for image kind,
                   +every configured asset uploaded for download kind);
                   prints {"repo","status","detail"} JSON.  write token; refuses unless
                   GITHUB_RUN_ATTEMPT == "1" (a re-run never publishes).
  ops-subset CONSUMER_VENDORED_SPEC PROVIDER_SPEC [--label X]
                   every (method, path) the consumer's vendored copy of the provider's spec
                   declares exists in the candidate provider spec (examined N; 0 = failure).
                   For a consumer that vendors a copy of its provider's spec (for mocks),
                   where byte identity cannot hold for "consumer@live vs provider@new".
  spec-compat BASELINE CANDIDATE [--label X] [--pair "C -> P" --consumer-side live|candidate]
                   a LIVE consumer's baseline provider spec (its pin, or what the live provider
                   serves) vs the candidate provider spec; fails when the candidate could break
                   that consumer. Operations match by method + path (path-param names ignored).
                   Fails on: operation missing; a baseline `security` alternative no candidate
                   alternative still accepts; RESPONSE 2xx property missing / retyped /
                   required->optional / nullable added / writeOnly, items or additionalProperties
                   changed, status or media type gone; REQUEST param or body property removed /
                   retyped / newly required / nullable lost / enum narrowed / string limit
                   tightened (maxLength, minLength, pattern, format), body newly required,
                   candidate-only oneOf/anyOf/allOf part with `required`; a oneOf/anyOf branch
                   gone; discriminator mapping changed; a construct it cannot compare ($ref path
                   item, `content` parameter). Additive changes and widened/removed enums pass.
                   Prints examined N; 0 operations = failure. Typically consumer@live ->
                   provider@new. With --pair, env RELEASE_BREAKING (plan's `breaking`) waives the
                   owner-approved findings of a `live` consumer check (WAIVED; an unlisted or a
                   stale one fails); on failure prints a paste-ready ```breaking block.
  breaking-shape --event-file F
                   R1 + R2 of the breaking-approved waiver from a pull_request event payload:
                   the label and a well-formed ```breaking block come together; pairs are
                   configured contracts. Prints the list as JSON.   no token
  breaking-approval (--pr N | --head-branch B)
                   R1 + R2 on the merged release PR N, plus R5 (the label predates merged_at,
                   from its issue events); or, for a rehearsal, on the one OPEN PR of branch B.
                   Prints the approved list as JSON.   read token (pull-requests: read)
  breaking-matrix --breaking J --checks J
                   R3: every approved pair has a live-consumer entry in the checks matrix.
                   Prints the list.   no token
  report --stage S --result success|failure [--detail T] [--drafts FILE] [--publish FILE]
                   markdown to stdout (FILE = JSON {repo: release_id} / {repo: status}).

Environment: RELEASE_FLOW_READ_TOKEN (all GitHub reads; drafts/publish fall back to the write
token, `drafts --check-only` does not), RELEASE_FLOW_WRITE_TOKEN (drafts/publish only;
validate/resolve never build a Writer), GITHUB_REPOSITORY (check-merge, concurrent),
GITHUB_REPOSITORY_OWNER (config-check), GITHUB_RUN_ATTEMPT (publish).

Exit codes: 0 ok; 1 a check or stage FAILED (the normal red); 2 usage, bad config/manifest,
repo outside --allowed, missing token, or refused to run (re-run); 3 unexpected GitHub /
network error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ci as ci_mod  # noqa: E402
import ops_subset  # noqa: E402
import spec_compat  # noqa: E402
import config as config_mod  # noqa: E402
import drafts as drafts_mod  # noqa: E402
import gh  # noqa: E402
import guard  # noqa: E402
import manifest as manifest_mod  # noqa: E402
import publish as publish_mod  # noqa: E402
import report as report_mod  # noqa: E402
import resolve as resolve_mod  # noqa: E402
import states as states_mod  # noqa: E402
import validate as validate_mod  # noqa: E402
import verdict as verdict_mod  # noqa: E402
import waiver as waiver_mod  # noqa: E402

DEFAULT_CONFIG = Path("releases") / "services.json"  # relative to the CURRENT directory


class Usage(Exception):
    pass


def git_diff(base, head):
    r = subprocess.run(["git", "diff", "--name-status", "--no-renames", base, head],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise Usage(f"git diff failed: {r.stderr.strip()}")
    return r.stdout.splitlines()


def build_parser():
    p = argparse.ArgumentParser(prog="release-flow", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_manifest(name, **kw):
        s = sub.add_parser(name)
        s.add_argument("manifest")
        s.add_argument("--config", default=str(DEFAULT_CONFIG))
        s.add_argument("--allowed", required=True)
        return s

    s = sub.add_parser("find-manifest")
    s.add_argument("--base", required=True)
    s.add_argument("--head", required=True)
    s.add_argument("--pr", action="store_true")
    s.add_argument("--config", default=str(DEFAULT_CONFIG))
    s = sub.add_parser("check-merge")
    s.add_argument("--sha", required=True)
    s.add_argument("--check-name", required=True)
    s.add_argument("--config", default=str(DEFAULT_CONFIG))
    s.add_argument("--workflow-path", default=guard.WORKFLOW_PATH)
    s = sub.add_parser("config-check")
    s.add_argument("--allowed", required=True)
    s.add_argument("--read-only", default=None)   # absent = rule off; given (even "") = enforced
    s.add_argument("--config", default=str(DEFAULT_CONFIG))
    s = sub.add_parser("verdict")
    s.add_argument("--stage", required=True, choices=["drafts", "publish"])
    s.add_argument("--needs-file", required=True)
    s.add_argument("--contracts-job", required=True)
    s.add_argument("--required", default="")
    s.add_argument("--manifest-file", default="")
    s.add_argument("--config", default=str(DEFAULT_CONFIG))
    s.add_argument("--allowed", required=True)
    s = sub.add_parser("concurrent")
    s.add_argument("--workflow", required=True)
    s.add_argument("--run-id", required=True)
    for n in ("validate", "ci-green", "order", "gate-services"):
        with_manifest(n)
    with_manifest("drafts").add_argument("--check-only", action="store_true")
    for n in ("resolve", "contract-states"):
        with_manifest(n).add_argument("--drafts-proof", metavar="REPO:TAG")
    s = with_manifest("publish")
    s.add_argument("--repo", required=True)
    s = sub.add_parser("ops-subset")
    s.add_argument("consumer_spec", metavar="CONSUMER_VENDORED_SPEC")
    s.add_argument("provider_spec", metavar="PROVIDER_SPEC")
    s.add_argument("--label", default="")
    s = sub.add_parser("spec-compat")
    s.add_argument("pinned_spec", metavar="PINNED")
    s.add_argument("candidate_spec", metavar="CANDIDATE")
    s.add_argument("--label", default="")
    s.add_argument("--pair", default=None)
    s.add_argument("--consumer-side", default=None)
    s = sub.add_parser("breaking-shape")
    s.add_argument("--event-file", required=True)
    s.add_argument("--config", default=str(DEFAULT_CONFIG))
    s = sub.add_parser("breaking-approval")
    s.add_argument("--pr", default=None)
    s.add_argument("--head-branch", default=None)
    s.add_argument("--config", default=str(DEFAULT_CONFIG))
    s = sub.add_parser("breaking-matrix")
    s.add_argument("--breaking", required=True)
    s.add_argument("--checks", required=True)
    s = sub.add_parser("report")
    s.add_argument("--stage", required=True)
    s.add_argument("--result", required=True, choices=["success", "failure"])
    s.add_argument("--detail", default="")
    s.add_argument("--drafts")
    s.add_argument("--publish")
    return p


def _err(msg):
    print(msg, file=sys.stderr)


def _token(env, *names):
    for n in names:
        if env.get(n):
            return env[n]
    raise Usage(f"{' or '.join(names)} is not set")


def _load(args):
    cfg = config_mod.load(args.config)
    cfg.restrict(config_mod.parse_allowed(args.allowed))
    entries = manifest_mod.load(args.manifest)
    manifest_mod.check_allowed(entries, config_mod.parse_allowed(args.allowed))
    return cfg, entries


def _root(env):
    if not env.get("GITHUB_REPOSITORY"):
        raise Usage("GITHUB_REPOSITORY is not set")
    return env["GITHUB_REPOSITORY"]


def gate_services(cfg, entries):
    """The input of devops's check-release-gate action: one {repo, tag, sha} per LISTED
    service, in publish order. Zero services is an error: an empty list would let a gate
    that examined nothing report success."""
    if not entries:
        raise Usage("gate-services: the manifest lists no services; nothing to gate")
    return [{"repo": f"{cfg.owner}/{r}", "tag": e.version, "sha": e.sha}
            for r in publish_mod.order(cfg, entries)
            for e in entries if e.repo == r]


def _csv(text):
    return [p.strip() for p in text.split(",") if p.strip()]


def _config_check(args, env):
    cfg = config_mod.load(args.config)
    cfg.restrict(config_mod.parse_allowed(args.allowed))
    # Only the job that mints a token covering these repos passes --read-only; the rest omit it.
    unread = [] if args.read_only is None else [
        c for c in cfg.consumers_only if c not in _csv(args.read_only)]
    if unread:
        raise config_mod.ConfigError(
            f"consumers_only repo(s) {unread} must also be in --read-only (the App needs read "
            "access to them)")
    running_owner = env.get("GITHUB_REPOSITORY_OWNER")
    if not running_owner:
        raise Usage("GITHUB_REPOSITORY_OWNER is not set")
    if cfg.owner != running_owner:
        raise config_mod.ConfigError(f"config owner {cfg.owner!r} is not the running repo's "
                                     f"owner {running_owner!r}")
    print(json.dumps({"owner": cfg.owner, "release_dir": cfg.release_dir,
                      "base_branch": cfg.base_branch}, separators=(",", ":")))
    return 0


def _verdict(args):
    """Exit 0 ok, 1 not ok (JSON still printed), 2 unreadable needs file / bad config /
    unreadable manifest of an otherwise ok verdict. A needs file that is not a JSON object is
    not exit 2: it is a stage that must not proceed, blamed on `plan`."""
    cfg = config_mod.load(args.config)
    cfg.restrict(config_mod.parse_allowed(args.allowed))
    try:
        raw = Path(args.needs_file).read_text(encoding="utf-8")
    except (OSError, ValueError) as ex:
        raise Usage(f"cannot read --needs-file {args.needs_file}: {ex}") from ex
    try:
        needs = json.loads(raw)
    except ValueError as ex:
        needs, why = None, str(ex)
    else:
        why = "not a JSON object"
    if isinstance(needs, dict):
        res = verdict_mod.judge(needs, args.contracts_job, _csv(args.required), cfg.release_dir)
    else:
        res = verdict_mod.unparseable(why)
    res["order"] = []
    if res["ok"]:
        path = args.manifest_file or res["manifest"]
        try:
            if args.manifest_file:
                got = hashlib.sha256(Path(path).read_bytes()).hexdigest()
                if not re.fullmatch(r"[0-9a-f]{64}", res["manifest_sha256"]) \
                        or got != res["manifest_sha256"]:
                    raise Usage(f"the staged manifest {path} has sha256 {got}, but plan "
                                f"reported {res['manifest_sha256']!r}")
            entries = manifest_mod.load(path)
        except OSError as ex:
            raise Usage(f"cannot read the manifest {path}: {ex}") from ex
        manifest_mod.check_allowed(entries, config_mod.parse_allowed(args.allowed))
        res["order"] = publish_mod.order(cfg, entries)
    out = {k: res[k] for k in ("ok", "rehearsal", "manifest", "manifest_sha256", "pr", "order",
                               "failed_stage", "failures")}
    print(json.dumps(out, separators=(",", ":")))
    return 0 if res["ok"] else 1


def _breaking(args, env, transport):
    """The breaking-approved waiver (waiver.py). Prints the approved list as compact JSON.
    Exit 1 = a rule failed; 2 = unreadable input (raised as Usage / ConfigError)."""
    try:
        if args.cmd == "breaking-matrix":
            try:
                checks = json.loads(args.checks)
            except ValueError as ex:
                raise Usage(f"--checks is not JSON: {ex}") from ex
            if not isinstance(checks, list):
                raise Usage("--checks must be a JSON list")
            try:
                entries = waiver_mod.from_json(args.breaking)
            except waiver_mod.WaiverError as ex:
                raise Usage(str(ex)) from ex
            waiver_mod.check_matrix(entries, checks)
        elif args.cmd == "breaking-shape":
            cfg = config_mod.load(args.config)
            try:
                event = json.loads(Path(args.event_file).read_text(encoding="utf-8"))
            except (OSError, ValueError) as ex:
                raise Usage(f"cannot read --event-file {args.event_file}: {ex}") from ex
            pr = event.get("pull_request") if isinstance(event, dict) else None
            if not isinstance(pr, dict):
                raise Usage("the event is not a pull_request event")
            names = [lb.get("name") for lb in pr.get("labels") or []]
            contracts = {(c.consumer, c.provider) for c in cfg.contracts}
            entries = waiver_mod.check_shape(names, pr.get("body"), contracts)
        else:
            if (args.pr is None) == (args.head_branch is None):
                raise Usage("breaking-approval needs exactly one of --pr and --head-branch")
            if args.pr is not None and not re.fullmatch(r"[0-9]+", args.pr):
                raise Usage(f"--pr {args.pr!r} is not a PR number")
            if args.head_branch is not None and not re.fullmatch(r"[A-Za-z0-9._/-]+",
                                                                 args.head_branch):
                raise Usage(f"--head-branch {args.head_branch!r} is not a plain branch name")
            cfg = config_mod.load(args.config)
            reader = gh.Reader(transport(_token(env, "RELEASE_FLOW_READ_TOKEN")))
            contracts = {(c.consumer, c.provider) for c in cfg.contracts}
            try:
                entries = guard.breaking_approval(reader, _root(env), contracts,
                                                  pr=args.pr, head_branch=args.head_branch)
            except guard.GuardError as ex:
                _err(f"FAIL: {ex}")
                return 1
    except waiver_mod.WaiverError as ex:
        _err(f"FAIL: {ex}")
        return 1
    print(waiver_mod.to_json(entries))
    return 0


def run(args, env, deps):
    cmd = args.cmd
    transport = lambda tok: deps.get("transport") or gh.urllib_transport(tok)  # noqa: E731

    if cmd == "ops-subset":
        return ops_subset.main([args.consumer_spec, args.provider_spec,
                                   *(["--label", args.label] if args.label else [])])
    if cmd == "spec-compat":
        return spec_compat.main([args.pinned_spec, args.candidate_spec,
                                 *(["--label", args.label] if args.label else []),
                                 *(["--pair", args.pair] if args.pair is not None else []),
                                 *(["--consumer-side", args.consumer_side]
                                   if args.consumer_side is not None else [])], env=env)
    if cmd in ("breaking-shape", "breaking-approval", "breaking-matrix"):
        return _breaking(args, env, transport)
    if cmd == "report":
        load_json = lambda p: json.loads(Path(p).read_text()) if p else None  # noqa: E731
        sys.stdout.write(report_mod.render(args.stage, args.result, args.detail,
                                           load_json(args.drafts), load_json(args.publish)))
        return 0
    if cmd == "config-check":
        return _config_check(args, env)
    if cmd == "verdict":
        return _verdict(args)
    if cmd == "find-manifest":
        # The config is REQUIRED here: a manifest path rule from a guessed release_dir would
        # accept or reject the wrong files, so an unreadable config is exit 2, never a default.
        cfg = config_mod.load(args.config)
        try:
            print(manifest_mod.find_added((deps.get("git_diff") or git_diff)(args.base, args.head),
                                          whole_tree=True, release_dir=cfg.release_dir))
        except manifest_mod.ManifestError as ex:
            _err(f"FAIL: {ex}")
            return 1
        return 0
    if cmd == "check-merge":
        cfg = config_mod.load(args.config)
        reader = gh.Reader(transport(_token(env, "RELEASE_FLOW_READ_TOKEN")))
        try:
            pr = guard.check_merge(reader, _root(env), args.sha, args.check_name,
                                   cfg.base_branch, args.workflow_path)
        except guard.GuardError as ex:
            _err(f"FAIL: {ex}")
            return 1
        print(pr)
        return 0
    if cmd == "concurrent":
        reader = gh.Reader(transport(_token(env, "RELEASE_FLOW_READ_TOKEN")))
        try:
            guard.concurrent(reader, _root(env), args.workflow, args.run_id)
        except guard.GuardError as ex:
            _err(f"FAIL: {ex}")
            return 1
        return 0

    # ---- manifest-bearing commands
    cfg, entries = _load(args)
    if cmd == "order":
        ordered = publish_mod.order(cfg, entries)
        if len(ordered) > publish_mod.MAX_PUBLISH_SLOTS:
            raise Usage(f"the manifest lists {len(ordered)} services, but the shared workflow "
                        f"has {publish_mod.MAX_PUBLISH_SLOTS} publish slots; split the release")
        print("\n".join(ordered))
        return 0
    if cmd == "gate-services":
        print(json.dumps(gate_services(cfg, entries), separators=(",", ":")))
        return 0

    if cmd in ("validate", "ci-green", "resolve", "contract-states"):
        reader = gh.Reader(transport(_token(env, "RELEASE_FLOW_READ_TOKEN")))
        if cmd == "ci-green":
            failures, examined = ci_mod.check(reader, cfg, entries)
            if examined == 0:
                failures.append("examined 0 CI workflows: nothing was checked")
            for f in failures:
                _err(f"FAIL: {f}")
            _err(f"ci-green: examined {examined} workflow(s), {len(failures)} failure(s)")
            return 1 if failures else 0
        if cmd == "validate":
            failures = validate_mod.validate_manifest(reader, cfg, entries)
            for f in failures:
                _err(f"FAIL: {f}")
            if not failures:
                _err(f"ok: {len(entries)} service(s) validated")
            return 1 if failures else 0
        proof = None
        if args.drafts_proof:
            m = re.fullmatch(r"([a-z0-9][a-z0-9._-]*):(v[0-9]+\.[0-9]+\.[0-9]+)",
                             args.drafts_proof)
            if not m or m.group(1) not in config_mod.parse_allowed(args.allowed):
                raise Usage("--drafts-proof must be REPO:vX.Y.Z with REPO in --allowed, got "
                            f"{args.drafts_proof!r}")
            proof = m.groups()
        try:
            resolved = resolve_mod.resolve(reader, cfg, entries, proof)
        except resolve_mod.ResolveError as ex:
            _err(f"FAIL: {ex}")
            return 1
        if cmd == "resolve":
            print(json.dumps(resolved, indent=2))
            return 0
        checks = states_mod.contract_states(cfg, entries, resolved)
        if not checks:
            _err("no contract pair involves a listed repo as consumer or provider "
                 f"(listed: {', '.join(e.repo for e in entries)}); nothing to check")
        print(json.dumps(checks))
        return 0

    if cmd == "drafts" and args.check_only:
        # Rehearsal: every pre-check `drafts` runs, with the READ token only. No Writer is
        # built, so nothing in this branch can write.
        reader = gh.Reader(transport(_token(env, "RELEASE_FLOW_READ_TOKEN")))
        failures = drafts_mod.precheck(reader, cfg, entries)
        if failures:
            for f in failures:
                _err(f"FAIL: {f}")
            print("{}")
            return 1
        print(json.dumps({e.repo: "rehearsal" for e in entries}, separators=(",", ":")))
        return 0

    # drafts / publish: write token required
    if cmd == "publish" and env.get("GITHUB_RUN_ATTEMPT") != "1":
        raise Usage("refusing to publish: GITHUB_RUN_ATTEMPT is "
                    f"{env.get('GITHUB_RUN_ATTEMPT')!r}, not '1' (a re-run never publishes)")
    wtok = _token(env, "RELEASE_FLOW_WRITE_TOKEN")
    reader = gh.Reader(transport(env.get("RELEASE_FLOW_READ_TOKEN") or wtok))
    writer = gh.Writer(transport(wtok))
    if cmd == "drafts":
        try:
            print(json.dumps(drafts_mod.create_drafts(reader, writer, cfg, entries), indent=2))
        except drafts_mod.DraftsError as ex:
            for f in ex.failures:
                _err(f"FAIL: {f}")
            print(json.dumps(ex.created, indent=2))
            return 1
        return 0
    entry = next((e for e in entries if e.repo == args.repo), None)
    if entry is None:
        raise Usage(f"{args.repo} is not listed in the manifest")
    res = publish_mod.publish_repo(
        reader, writer, cfg, entry, deps.get("health_get") or gh.http_get_json,
        deps.get("clock") or time.monotonic, deps.get("sleep") or time.sleep)
    print(json.dumps({"repo": args.repo, "status": res.status, "detail": res.detail}))
    if res.status != publish_mod.LIVE:
        _err(f"FAIL: {args.repo}: {res.status}: {res.detail}")
        return 1
    return 0


def main(argv=None, env=None, deps=None):
    import os
    env = os.environ if env is None else env
    args = build_parser().parse_args(argv)
    try:
        return run(args, env, deps or {})
    except (Usage, config_mod.ConfigError, manifest_mod.ManifestError) as ex:
        _err(f"error: {ex}")
        return 2
    except gh.GitHubError as ex:
        _err(f"GitHub error: {ex}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
