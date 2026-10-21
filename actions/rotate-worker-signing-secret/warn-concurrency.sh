#!/usr/bin/env bash
# Say, on every run, which concurrency group the calling job must declare.
#
# A composite action cannot declare `concurrency:`, and no GitHub context exposes the running
# job's concurrency group, so the action cannot tell whether the caller set one. A DIRECT caller
# therefore always gets a ::warning:: naming the block. Our own wrapper workflow declares the
# group itself and passes concurrency_declared: 'true', so it gets a ::notice:: instead. Without
# the group, two bundle writers (sync-bundle-key, rotate-signing-keypair, this action) can both
# read version N and the second write silently drops the first one's keys.
# tests/run_concurrency_tests.py pins the group string.
#
# Env: GCP_PROJECT, BUNDLE_SECRET, CONCURRENCY_DECLARED.
set -eo pipefail

MSG="rotate-worker-signing-secret cannot see or set the calling job's concurrency group. The job that uses this action MUST declare: concurrency: { group: bundle-write-${GCP_PROJECT}-${BUNDLE_SECRET}, cancel-in-progress: false }. Without it, two bundle writers can both read version N and the second write silently drops the first one's keys."
if [ "$CONCURRENCY_DECLARED" = "true" ]; then
  echo "::notice::The wrapper workflow declares the concurrency group (bundle-write-${GCP_PROJECT}-${BUNDLE_SECRET}, cancel-in-progress: false) itself. ${MSG}"
else
  echo "::warning::${MSG}"
fi
