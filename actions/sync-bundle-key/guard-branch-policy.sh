#!/usr/bin/env bash
# S0: refuse an environment with no deployment branch policy.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

[ -n "$ENVIRONMENT" ] || exit 0
[ "$REQUIRE_BRANCH_POLICY" = "true" ] || exit 0
ENV_JSON=$(gh api "repos/${REPO}/environments/${ENVIRONMENT}")
if ! printf '%s' "$ENV_JSON" | jq -e '.deployment_branch_policy != null' >/dev/null 2>&1; then
  echo "::error::Environment '${ENVIRONMENT}' has no deployment branch policy. Refusing to run: any branch could deploy to it. Run repos-environments to converge it, or set require_branch_policy: false."
  exit 1
fi
echo "Environment '${ENVIRONMENT}' has a deployment branch policy."
