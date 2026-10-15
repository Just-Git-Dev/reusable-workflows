# release-pr-check

Reusable workflow (`release-pr-check.yml`) for the first stage of the shared release flow. On a
release PR it checks that exactly one new manifest was added, nothing else changed, the manifest
parses strictly, every repo it names is in `allowed`, and a `breaking` block in the PR body comes with the `breaking-approved` label (shape only; see [Contract checks](release-flow.md#contract-checks)). It holds no secret and mints no App
token: it reads only the root repo, with the caller's `contents: read` token, and the config
comes from the PR's base commit. It catches mistakes, not attacks; the security boundary is the
merge guard in [`release-plan`](release-plan.md).

Inputs, caller example and the job name (`release-pr`, so the check run is
`release-pr / release-pr`): see
[release-flow.md, `release-pr-check.yml`](release-flow.md#release-pr-checkyml).
