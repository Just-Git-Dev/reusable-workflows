"""services.json loader.

The service names, their order and their deploy/health wiring live ONLY here, so another
project can reuse this package with its own file. But the file cannot widen scope by itself:
every command also takes a hard-coded `--allowed` list from the workflow, and restrict()
refuses a services.json naming anything outside it (an edit to this JSON in a PR must not be
able to point the write token at a new repo).

`consumers_only` repos (cli) are non-flow: they release by tag push, never get draft releases
or deploy runs from this flow, and appear only as the consumer side of a contract. Their
"live" version is simply the highest vX.Y.Z tag.

Optional top-level keys (defaults in brackets): release_dir [releases], base_branch [main],
changelog [{path: CHANGELOG.md, heading: "## {version}"}; null turns the check off],
deploy_run_name [Deploy {tag}]. Service kinds: image, pages, download (see docs/release-flow.md).
"""

from __future__ import annotations

import json
import re
from typing import NamedTuple, Optional

KINDS = ("image", "pages", "download")
DEFAULT_RELEASE_DIR = "releases"
DEFAULT_BASE_BRANCH = "main"
DEFAULT_DEPLOY_RUN_NAME = "Deploy {tag}"

# A relative path: segments of these characters, no empty segment, no "." or ".." segment.
_SEG = r"(?!\.{1,2}(?:/|\Z))[A-Za-z0-9._-]+"
_REL_PATH = re.compile(rf"^{_SEG}(?:/{_SEG})*\Z")
_BRANCH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]*\Z")


class ConfigError(Exception):
    pass


class Health(NamedTuple):
    path: str       # dotted path into the JSON health response
    expect: str     # the value found there


class Changelog(NamedTuple):
    path: str
    heading: str    # contains {version}


DEFAULT_HEALTH = Health("data.status", "UP")
DEFAULT_CHANGELOG = Changelog("CHANGELOG.md", "## {version}")


class Service(NamedTuple):
    repo: str
    kind: str
    order: int
    deploy_workflow: str
    health_url: Optional[str]
    image: Optional[str]
    # H8: workflows whose push run at a listed sha must be green: ((file, (paths_ignore...)), ...)
    ci: tuple = ()
    health: Optional[Health] = None   # image services only (default applied by the loader)
    assets: tuple = ()                # download services only


class Contract(NamedTuple):
    consumer: str
    provider: str


class Config:
    def __init__(self, owner, gar_registry, services, consumers_only, contracts=(),
                 release_dir=DEFAULT_RELEASE_DIR, base_branch=DEFAULT_BASE_BRANCH,
                 changelog=DEFAULT_CHANGELOG, deploy_run_name=DEFAULT_DEPLOY_RUN_NAME):
        self.owner = owner
        self.gar_registry = gar_registry
        self.services = services
        self.consumers_only = consumers_only
        self.contracts = list(contracts)
        self.release_dir = release_dir
        self.base_branch = base_branch
        self.changelog = changelog
        self.deploy_run_name = deploy_run_name

    def service(self, repo):
        for s in self.services:
            if s.repo == repo:
                return s
        return None

    def restrict(self, allowed):
        extra = [s.repo for s in self.services if s.repo not in allowed]
        if extra:
            raise ConfigError(f"services.json lists repo(s) outside --allowed: {extra}")


def parse_allowed(text):
    names = [p.strip() for p in text.split(",") if p.strip()]
    if not names:
        raise ConfigError("--allowed is empty")
    return names


def _need(d, key, where):
    v = d.get(key)
    if not isinstance(v, str) or not v:
        raise ConfigError(f"{where}: missing or non-string {key!r}")
    return v


def _rel_path(v, where, key):
    if not isinstance(v, str) or not _REL_PATH.match(v):
        raise ConfigError(f"{where}: {key} must be a relative path (letters, digits, . _ - and "
                          f"/; no leading /, no empty segment), got {v!r}")
    if ".." in v:
        raise ConfigError(f"{where}: {key} must not contain '..', got {v!r}")
    return v


def _top_options(d):
    release_dir = _rel_path(d.get("release_dir", DEFAULT_RELEASE_DIR), "config", "release_dir")
    branch = d.get("base_branch", DEFAULT_BASE_BRANCH)
    if not isinstance(branch, str) or not _BRANCH.match(branch) or ".." in branch \
            or "//" in branch or branch.endswith("/"):
        raise ConfigError(f"config: base_branch must be a branch name, got {branch!r}")
    name = d.get("deploy_run_name", DEFAULT_DEPLOY_RUN_NAME)
    if not isinstance(name, str) or name.count("{tag}") != 1:
        raise ConfigError(f"config: deploy_run_name must be a string containing {{tag}} "
                          f"exactly once, got {name!r}")
    raw = d.get("changelog", DEFAULT_CHANGELOG._asdict())
    if raw is None:
        changelog = None
    else:
        if not isinstance(raw, dict) or set(raw) - {"path", "heading"}:
            raise ConfigError("config: changelog must be null or {path, heading}, "
                              f"got {raw!r}")
        path = _rel_path(raw.get("path", DEFAULT_CHANGELOG.path), "config", "changelog.path")
        heading = raw.get("heading", DEFAULT_CHANGELOG.heading)
        if not isinstance(heading, str) or "{version}" not in heading or "\n" in heading:
            raise ConfigError("config: changelog.heading must be a one-line string containing "
                              f"{{version}}, got {heading!r}")
        changelog = Changelog(path, heading)
    return release_dir, branch, changelog, name


def _health(raw, where):
    if not isinstance(raw, dict) or set(raw) != {"path", "expect"}:
        raise ConfigError(f"{where}: health must be {{path, expect}}, got {raw!r}")
    path, expect = raw["path"], raw["expect"]
    if not isinstance(path, str) or not path or not all(path.split(".")):
        raise ConfigError(f"{where}: health.path must be a dotted path of non-empty names, "
                          f"got {path!r}")
    if not isinstance(expect, str) or not expect:
        raise ConfigError(f"{where}: health.expect must be a non-empty string, got {expect!r}")
    return Health(path, expect)


def _assets(raw, where):
    if not isinstance(raw, list) or not raw \
            or not all(isinstance(a, str) and a for a in raw) or len(set(raw)) != len(raw):
        raise ConfigError(f"{where}: assets must be a non-empty list of unique non-empty "
                          f"strings, got {raw!r}")
    return tuple(raw)


def from_dict(d) -> Config:
    owner = _need(d, "owner", "config")
    release_dir, base_branch, changelog, run_name = _top_options(d)
    consumers = d.get("consumers_only", [])
    if not isinstance(consumers, list) or not all(isinstance(c, str) and c for c in consumers) \
            or len(set(consumers)) != len(consumers):
        raise ConfigError("consumers_only must be a list of unique non-empty strings")
    services, seen, orders = [], set(), set()
    for raw in d.get("services") or []:
        repo = _need(raw, "repo", "service")
        where = f"service {repo}"
        kind = raw.get("kind")
        if kind not in KINDS:
            raise ConfigError(f"{where}: kind must be image|pages|download, got {kind!r}")
        order = raw.get("order")
        if not isinstance(order, int) or isinstance(order, bool):
            raise ConfigError(f"{where}: order must be an integer")
        if repo in seen or order in orders:
            raise ConfigError(f"{where}: duplicate repo or order")
        seen.add(repo)
        orders.add(order)
        wf = _need(raw, "deploy_workflow", where)
        health_url, image, health, assets = raw.get("health_url"), raw.get("image"), None, ()
        if kind == "image":
            health_url, image = _need(raw, "health_url", where), _need(raw, "image", where)
            health = _health(raw["health"], where) if "health" in raw else DEFAULT_HEALTH
        elif health_url or image:
            raise ConfigError(f"{where}: {kind} services take no health_url/image")
        elif "health" in raw:
            raise ConfigError(f"{where}: health is only allowed on image services, not {kind}")
        if kind == "download":
            assets = _assets(raw.get("assets"), where)
        elif "assets" in raw:
            raise ConfigError(f"{where}: assets is only allowed on download services, "
                              f"not {kind}")
        ci = []
        for w in raw.get("ci", []):
            ign = w.get("paths_ignore", []) if isinstance(w, dict) else None
            if not isinstance(w, dict) or not isinstance(w.get("workflow"), str) \
                    or not w["workflow"] or not isinstance(ign, list) \
                    or not all(isinstance(x, str) for x in ign) \
                    or set(w) - {"workflow", "paths_ignore"}:
                raise ConfigError(f"{where}: bad ci entry {w!r} "
                                  "(want {workflow: file, paths_ignore: [globs]})")
            ci.append((w["workflow"], tuple(ign)))
        services.append(Service(repo, kind, order, wf, health_url, image, tuple(ci), health,
                                assets))
    if not services:
        raise ConfigError("no services configured")
    registry = d.get("gar_registry")
    if any(s.kind == "image" for s in services):
        registry = _need(d, "gar_registry", "config")  # a resolved image is <registry>/<image>
    elif registry is not None and (not isinstance(registry, str) or not registry):
        raise ConfigError("config: gar_registry must be a non-empty string when given")
    overlap = seen & set(consumers)
    if overlap:
        raise ConfigError(f"consumers_only overlaps services: {sorted(overlap)}")
    contracts = []
    for c in d.get("contracts", []):
        if not isinstance(c, dict) or set(c) != {"consumer", "provider"}:
            raise ConfigError(f"contract must be {{consumer, provider}}, got {c!r}")
        for name in (c["consumer"], c["provider"]):
            if name not in seen and name not in consumers:
                raise ConfigError(f"contract names {name!r}, not in services/consumers_only")
        contracts.append(Contract(c["consumer"], c["provider"]))
    return Config(owner, registry, sorted(services, key=lambda s: s.order), consumers,
                  contracts, release_dir, base_branch, changelog, run_name)


def load(path) -> Config:
    try:
        with open(path, encoding="utf-8") as f:
            return from_dict(json.load(f))
    except (OSError, ValueError) as e:
        raise ConfigError(f"cannot read {path}: {e}") from e
