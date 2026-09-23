"""alertgen — compile an AlertSpec (infra/alerts/alerts.yaml) into backend alert rules.

    python3 -m alertgen validate --spec infra/alerts/alerts.yaml
    python3 -m alertgen render   --spec ... --target gmp|prometheus --out DIR

See docs/alertspec.md for the format and docs/service-alerts.md for the workflow.
"""

# Semver of the built-in catalog (alerting/catalog/*.yaml); stamped into every policy's
# userLabels as catalog_version. Bump rules: docs/alertspec.md#catalog-versioning.
CATALOG_VERSION = "1.0.0"
