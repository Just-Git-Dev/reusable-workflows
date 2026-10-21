#!/usr/bin/env bash
# Warn, on every run, which concurrency group the calling job must declare.
#
# A composite action cannot declare `concurrency:`, and no GitHub context exposes the running
# job's concurrency group, so the action cannot tell whether the caller set one. It therefore
# always says what is required. Without the group, two bundle writers (this action,
# rotate-signing-keypair, rotate-worker-signing-secret) can both read version N and the second
# write silently drops the first one's keys. tests/run_concurrency_tests.py pins the group string.
#
# Env: GCP_PROJECT, BUNDLE_SECRET.
set -eo pipefail

echo "::warning::sync-bundle-key cannot see or set the calling job's concurrency group. The job that uses this action MUST declare: concurrency: { group: bundle-write-${GCP_PROJECT}-${BUNDLE_SECRET}, cancel-in-progress: false }. Without it, two bundle writers can both read version N and the second write silently drops the first one's keys."
