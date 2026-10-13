"""Release manifest parser and the "which file did this PR/merge add" rule.

WHY a hand-written parser and not YAML: a manifest is the reviewed record of what goes to
prod. A general YAML parser accepts anchors, flow variants, duplicate keys and type
coercion (`sha: 1e10`), each a way for a reviewed file to mean something other than what the
reviewer read. The accepted grammar is five line shapes, anything else is an error carrying
its line number:

    # comment            (or blank)
    services:            (exactly once, before any entry)
      - {repo: X, version: vX.Y.Z, sha: <40 lowercase hex>}

so the file is still valid YAML for humans and editors, but we never ask YAML to read it.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_ENTRY = re.compile(
    r"^  - \{repo: ([a-z0-9][a-z0-9._-]*), +version: (v[0-9]+\.[0-9]+\.[0-9]+), +"
    r"sha: ([0-9a-f]{40})\}\Z")


class ManifestError(Exception):
    pass


class Entry(NamedTuple):
    repo: str
    version: str
    sha: str


def parse(text: str) -> list[Entry]:
    entries: list[Entry] = []
    seen_header = False
    for n, line in enumerate(text.split("\n"), 1):
        if line.endswith("\r"):
            raise ManifestError(f"line {n}: carriage return (use LF line endings)")
        if line.strip() == "" and "\t" not in line:
            continue
        if line.lstrip(" ").startswith("#"):
            continue
        if line == "services:":
            if seen_header:
                raise ManifestError(f"line {n}: 'services:' appears twice")
            seen_header = True
            continue
        m = _ENTRY.match(line)
        if m:
            if not seen_header:
                raise ManifestError(f"line {n}: entry before 'services:'")
            if any(e.repo == m.group(1) for e in entries):
                raise ManifestError(f"line {n}: duplicate repo {m.group(1)!r}")
            entries.append(Entry(*m.groups()))
            continue
        raise ManifestError(
            f"line {n}: not an accepted line (want '  - {{repo: X, version: vX.Y.Z, "
            f"sha: <40 lowercase hex>}}'): {line!r}")
    if not entries:
        raise ManifestError("no services listed (empty manifest)")
    return entries


def load(path) -> list[Entry]:
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def check_allowed(entries, allowed) -> None:
    bad = [e.repo for e in entries if e.repo not in allowed]
    if bad:
        raise ManifestError(f"repo(s) outside the allowed set {sorted(allowed)}: {bad}")


def _manifest_re(release_dir):
    return re.compile(rf"^{re.escape(release_dir)}/[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}-"
                      r"[a-z0-9][a-z0-9-]*\.yaml\Z")


def _any_yaml_re(release_dir):
    return re.compile(rf"^{re.escape(release_dir)}/[^/]+\.yaml\Z")


def path_ok(path, release_dir="releases") -> bool:
    """True iff `path` is a manifest path: <release_dir>/YYYY-MM-DD-<slug>.yaml."""
    return isinstance(path, str) and _manifest_re(release_dir).match(path) is not None


def find_added(name_status_lines, whole_tree=False, release_dir="releases") -> str:
    """The one manifest a PR/merge adds, from `git diff --name-status` lines.

    Without whole_tree only release_dir/ is considered (a diff scoped to it): exactly one A of
    <release_dir>/<date>-<slug>.yaml, and no M/D/R/C touching any <release_dir>/*.yaml
    (a merged manifest is the permanent record). With whole_tree the diff covers the entire
    PR, and ANY other change is an error: a release PR may carry nothing but its manifest.
    """
    name_ok, any_yaml = _manifest_re(release_dir), _any_yaml_re(release_dir)
    added: list[str] = []
    for raw in name_status_lines:
        raw = raw.rstrip("\n")
        if not raw.strip():
            continue
        parts = raw.split("\t")
        status, paths = parts[0], parts[1:]
        if not paths:
            raise ManifestError(f"unparseable diff line: {raw!r}")
        if status == "A" and len(paths) == 1 and any_yaml.match(paths[0]):
            if not name_ok.match(paths[0]):
                raise ManifestError(
                    f"{paths[0]}: manifest name must be {release_dir}/YYYY-MM-DD-<slug>.yaml")
            added.append(paths[0])
            continue
        if any(any_yaml.match(p) for p in paths):
            raise ManifestError(f"existing manifest touched ({status} {' '.join(paths)}): "
                                "merged manifests are immutable")
        if whole_tree:
            raise ManifestError(f"a release PR may change nothing but its manifest; "
                                f"found {status} {' '.join(paths)}")
    if len(added) != 1:
        raise ManifestError(f"expected exactly one added {release_dir}/*.yaml, found {len(added)}")
    return added[0]
