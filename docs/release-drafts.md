# release-drafts

Reusable workflow (`release-drafts.yml`) for the third stage of the shared release flow: the first
write. A `verdict` job refuses to go on unless every upstream job in the caller's `needs`
succeeded; then the `drafts` job creates one **draft** Release per listed service, for the tag
that already exists. It creates no tag and no ref. In a rehearsal it mints a read-only token and
runs `drafts --check-only`, so nothing is written.

Inputs, the `drafts` output and the caller example: see
[release-flow.md, `release-drafts.yml`](release-flow.md#release-draftsyml).
