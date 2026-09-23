"""Command line: `python3 -m alertgen {validate,render} ...` (run with PYTHONPATH=alerting)."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import yaml

from . import CATALOG_VERSION
from .compile import resolve
from .spec import SpecError, load_spec

TARGETS = {"gmp", "prometheus"}
NOT_BUILT = {"dynatrace": "the Dynatrace (DQL) mapping is documented in docs/alertspec.md "
                          "but not built yet"}


def _warn(msg):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning::{msg}")
    else:
        print(f"warning: {msg}", file=sys.stderr)


def _error(msg):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for line in str(msg).splitlines():
            print(f"::error::{line}")
    else:
        print(f"error: {msg}", file=sys.stderr)


def _parser():
    p = argparse.ArgumentParser(prog="alertgen")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="resolve the spec and print the effective rules")
    v.add_argument("--spec", required=True)
    r = sub.add_parser("render", help="render the spec for a backend")
    r.add_argument("--spec", required=True)
    r.add_argument("--target", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--owner", help="gmp: the owning repo (e.g. org/repo), stamped as alertgen_owner")
    r.add_argument("--oracle", action="store_true",
                   help="prometheus: also render GCP-only rules (for promtool tests)")
    r.add_argument("--crd", metavar="NAME", help="prometheus: wrap as a PrometheusRule CR")
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    warnings = []
    try:
        rules = resolve(load_spec(args.spec), warnings=warnings)
    except SpecError as e:
        _error(f"{args.spec}: {len(e.problems)} problem(s)\n" + str(e))
        return 1
    for w in warnings:
        _warn(w)

    if args.cmd == "validate":
        for r in rules:
            thr = f" {r.op} {r.threshold_text}" if r.threshold is not None else ""
            print(f"{r.key:45} {r.severity:6} {','.join(r.services):20} {r.kind}{thr}")
        print(f"{len(rules)} rule(s) OK")
        return 0

    if args.target in NOT_BUILT:
        _error(f"--target {args.target}: {NOT_BUILT[args.target]}")
        return 1
    if args.target not in TARGETS:
        _error(f"--target must be one of {sorted(TARGETS)}")
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.target == "gmp":
        from .render_gmp import render
        if not args.owner:
            _error("--owner is required for --target gmp (it scopes the managed update)")
            return 1
        res = render(rules, owner=args.owner)
        for fname, pol in res.policies:
            (out / fname).write_text(yaml.safe_dump(pol, sort_keys=True, allow_unicode=True))
        (out / "probes.json").write_text(json.dumps(res.probes, indent=2, sort_keys=True) + "\n")
        hashes = [pol["userLabels"]["spec_hash"] for _, pol in res.policies]
        manifest = {
            "catalog_version": CATALOG_VERSION,
            "owner": res.policies[0][1]["userLabels"]["alertgen_owner"] if res.policies else "",
            "spec_hash": hashlib.sha256("".join(hashes).encode()).hexdigest()[:16],
            "policies": [{"file": f, "rule_id": p["userLabels"]["rule_id"],
                          "displayName": p["displayName"], "severity": p["severity"],
                          "spec_hash": p["userLabels"]["spec_hash"]} for f, p in res.policies],
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"rendered {len(res.policies)} policy file(s), {len(res.probes)} probe(s) -> {out}")
        return 0
    from .render_prom import render
    try:
        doc = render(rules, oracle=args.oracle, crd_name=args.crd)
    except SpecError as e:
        _error(str(e))
        return 1
    (out / "prometheus-rules.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    print(f"rendered prometheus rules -> {out / 'prometheus-rules.yaml'}")
    return 0
