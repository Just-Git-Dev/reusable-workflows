#!/usr/bin/env bash
# Say, on every run, which concurrency group the calling job must declare.
#
# A composite action cannot declare `concurrency:`, and no GitHub context exposes the running job's
# group. A DIRECT caller therefore always gets a ::warning:: naming the block; our wrapper workflow
# declares the group itself and passes concurrency_declared: 'true', so it gets a ::notice::.
# Two overlapping runs would both advance the same state variable.
#
# Env: WORKER_SCRIPT, SLOT_A, CONCURRENCY_DECLARED.
set -eo pipefail

GROUP="rotate-external-${WORKER_SCRIPT}-${SLOT_A}"
MSG="rotate-external-secret cannot see or set the calling job's concurrency group. The job that uses this action MUST declare: concurrency: { group: ${GROUP}, cancel-in-progress: false }. Without it, two overlapping runs can both advance the same state variable."
if [ "$CONCURRENCY_DECLARED" = "true" ]; then
  echo "::notice::The wrapper workflow declares the concurrency group (${GROUP}, cancel-in-progress: false) itself. ${MSG}"
else
  echo "::warning::${MSG}"
fi
