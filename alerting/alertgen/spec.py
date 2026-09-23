"""Load the AlertSpec and the built-in catalog, and check the spec's top-level shape.

Unknown keys are errors everywhere: a typo (`pakcs:`, `treshold:`) must never be the reason
a rule silently keeps its default or silently turns off.
"""
import re
from pathlib import Path

import yaml

SERVICE_RE = re.compile(r"^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$")

API_VERSION = "alertspec/v1"
CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"
TOP_KEYS = {"apiVersion", "services", "packs", "overrides", "custom"}


class SpecError(Exception):
    """One or more problems with a spec. str() lists every problem, one per line."""

    def __init__(self, problems):
        if isinstance(problems, str):
            problems = [problems]
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


def load_catalog(catalog_dir: Path = CATALOG_DIR):
    """-> (packs, rules). packs: name -> {platforms, rule ids}; rules: id -> rule def + pack."""
    packs, rules = {}, {}
    for f in sorted(catalog_dir.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text())
        name = doc["pack"]
        platforms = frozenset(doc["platforms"])
        packs[name] = {"platforms": platforms, "rules": []}
        for r in doc["rules"]:
            if r["id"] in rules:
                raise SpecError(f"catalog: duplicate rule id {r['id']} ({f.name})")
            rules[r["id"]] = dict(r, pack=name, platforms=platforms)
            packs[name]["rules"].append(r["id"])
    return packs, rules


def load_spec(path) -> dict:
    try:
        doc = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as e:
        raise SpecError(f"{path}: cannot read spec ({e})")
    return doc


def check_top(spec) -> list:
    """Top-level shape problems (empty list when fine)."""
    if not isinstance(spec, dict):
        return ["spec must be a YAML mapping"]
    problems = []
    for k in sorted(set(spec) - TOP_KEYS):
        problems.append(f"unknown top-level key {k!r} (allowed: {', '.join(sorted(TOP_KEYS))})")
    if spec.get("apiVersion") != API_VERSION:
        problems.append(f"apiVersion must be {API_VERSION!r}, got {spec.get('apiVersion')!r}")
    svcs = spec.get("services")
    if not isinstance(svcs, list) or not svcs or not all(isinstance(s, str) and s for s in svcs):
        problems.append("services must be a non-empty list of service names")
    elif len(set(svcs)) != len(svcs):
        problems.append("services lists a name twice")
    else:
        # Cloud Run's own service-name rule. It also keeps names safe to splice into a
        # logging filter and a label value, and keeps `_` free to join group keys with.
        for s in svcs:
            if not SERVICE_RE.match(s):
                problems.append(f"services: {s!r} is not a valid service name (lowercase "
                                "letters, digits and '-', starting with a letter)")
    for key, typ in (("packs", list), ("overrides", dict), ("custom", list)):
        if key in spec and not isinstance(spec[key], typ):
            problems.append(f"{key} must be a {'list' if typ is list else 'mapping'}")
    return problems
