#!/usr/bin/env python3
"""Generate the catalog table in docs/alertspec.md from alerting/catalog/*.yaml.

The table is what a spec author reads to pick packs and learn the defaults they are
overriding; if it drifts from the YAML, they tune against numbers that are not shipped.
Same pattern as gen_catalog.py: generated, and `--check` fails CI when stale.

    python3 scripts/gen_alert_catalog.py          # rewrite the table
    python3 scripts/gen_alert_catalog.py --check  # fail if it is stale
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "alerting" / "catalog"
DOC = ROOT / "docs" / "alertspec.md"
BEGIN = "<!-- BEGIN GENERATED CATALOG (scripts/gen_alert_catalog.py) -->"
END = "<!-- END GENERATED CATALOG -->"


def default_text(r):
    kind = r["kind"]
    if kind == "log_match":
        return f"any match, rate limit {r.get('rate_limit', '300s')}"
    parts = []
    if "threshold" in r:
        parts.append(f"{r.get('op', '>')} {r['threshold']} over {r['window']}")
    else:
        parts.append(f"over {r['window']}")
    parts.append(f"for {r.get('for', '0s')}")
    if "min_requests" in r:
        parts.append(f"min {r['min_requests']} req")
    return ", ".join(parts)


def table():
    rows = ["| Pack | Rule id | Signal | Default | Severity | On by default |",
            "|---|---|---|---|---|---|"]
    for f in sorted(CATALOG.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text())
        for r in doc["rules"]:
            on = "yes" if r.get("enabled", True) else "no"
            rows.append(f"| `{doc['pack']}` | `{r['id']}` | {r['signal']} | {default_text(r)} "
                        f"| {r['severity']} | {on} |")
    return "\n".join(rows)


def main(argv):
    text = DOC.read_text()
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    new = f"{head}{BEGIN}\n{table()}\n{END}{tail}"
    if "--check" in argv:
        if new != text:
            print("::error::docs/alertspec.md catalog table is stale — run "
                  "python3 scripts/gen_alert_catalog.py")
            return 1
        print("docs/alertspec.md catalog table is current.")
        return 0
    DOC.write_text(new)
    print("wrote docs/alertspec.md catalog table")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
