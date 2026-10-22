#!/usr/bin/env bash
# Say, on every run, that this action is deprecated. It stays until v6 so its callers can move.
set -eo pipefail

echo "::notice::rotate-worker-signing-secret is deprecated since v5.1.0 in favour of rotate-external-secret (docs/rotate-external-secret.md) and is removed in v6."
