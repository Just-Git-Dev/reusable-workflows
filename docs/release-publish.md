# release-publish

Reusable workflow (`release-publish.yml`) for the last stage of the shared release flow. A
`verdict` job decides from the caller's `needs`; then up to six fixed jobs (`publish-1` to
`publish-6`) publish the drafts in order, each with its own token scoped to that one repo, wait
for the service's Deploy and prove it live. The first failure stops every later service. A final
`report` job writes the run summary and, for a real release, comments on the release PR. In a
rehearsal nothing is published and the report only goes to the run summary.

Inputs and the caller example: see
[release-flow.md, `release-publish.yml`](release-flow.md#release-publishyml). Why one job per
service is in the same page, under "Why publish is one job per service, not one job for all".

Credentials: either the App (`client-id`, the App's Client ID, plus the optional secret
`RELEASE_APP_KEY`) or the optional secret `github-token`, never both. In token mode every
`publish-N` job holds the same token, with no per-repo limit, and its scope is the caller's
responsibility. See [Credentials](release-flow.md#credentials).
