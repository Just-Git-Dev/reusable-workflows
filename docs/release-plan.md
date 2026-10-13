# release-plan

Reusable workflow (`release-plan.yml`) for the second stage of the shared release flow, run
after the release PR is merged. Read-only throughout: the merge guard, the CLI self-test, the one
manifest and the publish order (`plan`), then `resolve` (validate, ci-green, resolve refs and
images, contract states) and `service-gates`. With `rehearsal: true` it skips only the merged-PR
check and runs the rest, so a release can be rehearsed with zero writes.

Inputs, outputs (`manifest`, `manifest-sha256`, `pr`, `order`, `rehearsal`, `resolved`, `checks`) and the caller
example: see [release-flow.md, `release-plan.yml`](release-flow.md#release-planyml). The token
rules and the `RELEASE_FLOW_TREE` pin are in the same page.
