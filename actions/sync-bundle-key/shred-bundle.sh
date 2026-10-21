#!/usr/bin/env bash
# Remove every local copy of the bundle.
# Env-only inputs (never interpolated): see the step's env: in action.yml.
# Step body moved verbatim from the v4.0.0 reusable workflow; docs/sync-bundle-key-action.md.
set -eo pipefail

rm -f /tmp/bundle.env /tmp/bundle.env.new /tmp/enabled.raw /tmp/enabled.txt /tmp/keep.txt /tmp/to-disable.txt /tmp/revisions.json /tmp/service.json /tmp/job.json /tmp/consumers.raw /tmp/consumers.txt /tmp/jobs.txt /tmp/jobs.raw /tmp/rev.json /tmp/live.txt /tmp/keys.*
