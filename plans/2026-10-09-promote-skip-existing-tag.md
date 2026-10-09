# Plan — promote-image `skip_existing_tag` (reusable-workflows v3.x)

> Approved 2026-10-09. This is the public copy: consumers are pseudonymised (consumer C) and
> private planning references are dropped, per DECISIONS.md 2026-10-04.

## Decision summary
- **What:** new optional input `skip_existing_tag` (bool, default `false`) on
  `.github/workflows/promote-image.yml`.
- **Behaviour when `true`:**
  - target tag absent → retag as today.
  - target tag present **on the same digest as the source** → skip the retag with a
    `::notice::`; the run CONTINUES to the GKE/Cloud Run roll and the deployment record.
  - target tag present **on a different digest** → FAIL, naming both digests.
  - the describe call fails for any reason other than "not found" (auth, API) → FAIL. An error
    never counts as "tag absent".
- **Default `false` = today's behaviour**, so the input contract only grows: a minor (semver)
  change, released as v3.x on an explicit ask only. No v2 backport.
- **Why:** a release run that retagged and then failed at the roll cannot be re-run today. The
  re-run calls `add-tag` again, and on an immutable repository consumer C reported
  `FAILED_PRECONDITION` even for the same digest (not re-verified here). The design does not
  rely on that error: it checks *before* `add-tag`, so it is correct whether or not the
  registry rejects a same-digest re-add. Consumer C's release flow re-runs a failed deploy
  (at most twice), which needs the re-run to be safe.
- **`:latest` is exempt** (with `also_tag_latest: true`): it is meant to move, so "already
  exists on another digest" is normal for it. It is always re-pointed at the source.
- Forward-only is unaffected: it allows "equal to live", and a failed roll never recorded the
  live Deployment.

## Steps (Doc → Test red → Implement → verify)
1. **Doc** `docs/promote-image.md`: Inputs row + a "Re-running a release" section (3 cases,
   the `:latest` exemption, the dry-run output).
2. **Test (red)** `tests/run_step_tests.py`: execute the shipped "Retag" step body against a
   stubbed `gcloud` that logs every call. Cases:
   a. skip=false, tag exists → `add-tag` with the target (old behaviour pinned; the positive
      control, green before and after).
   b. skip=true, tag absent (`NOT_FOUND`) → `add-tag` with the target.
   c. skip=true, same digest → no `add-tag`, rc 0, notice says "already".
   d. skip=true, other digest → rc 1, both digests named, no `add-tag`.
   e. skip=true, describe fails `PERMISSION_DENIED` → rc 1, no `add-tag`.
   f. skip=true, same digest, `also_tag_latest` → `add-tag` with `:latest` only.
   g. dry_run + same digest → prints "would skip", no write.
3. **Implement** in the "Retag (server-side, no rebuild)" step: source digest via
   `gcloud container images describe --format='value(image_summary.digest)'`; classify the
   target describe's stderr with the repo's existing not-found regex; any other error or an
   empty source digest fails. Drop the target from the destination list when the digests match;
   skip `add-tag` entirely when nothing is left. Summary line when skipped.
4. **Gates:** `actionlint`, `python3 tests/run_step_tests.py`, the SHA-pin grep.
5. **DECISIONS.md** entry.
6. PR; merge and the release are the owner's.

## Verification
- Step tests a–g green; case a green before and after.
- CI `step-bodies` log shows the new checks ran (count increased).
- Optional live control (owner's call): a consumer dry run with `skip_existing_tag: true` on an
  already-promoted tag prints "would skip".
