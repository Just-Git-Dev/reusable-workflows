# Plan — `fail_on_inert` for `cleanup-gar-images`

Owner-approved 2026-10-15.

## Summary

- **What:** a new optional input, `fail_on_inert` (boolean, default `false`). When on, the run goes
  **red** if any image in the registry has **zero release-tagged images**. Today that case only
  logs a `::warning::` on a green run.
- **Why:** consumer B had one image tagged `0.1.x` (no `v`). The default `release_tag_pattern`
  never matched it, so the sweep was inert for that image — 2.68 GB kept for weeks while every
  daily run finished green with `deleted=0`. Nobody reads warnings on a green run.
- **Contract:** additive inputs → minor release **v3.6.0**. Existing callers see no change.

## Rulings

1. An image is **inert** only when it has **zero** release-tagged images. An image with fewer
   releases than `build_retention_releases` (no boundary yet) stays a warning, not a failure —
   that is the normal state of a young service.
2. Callers can exempt images with `allow_inert_images` (comma-separated image names, the last
   path segment). Exempt images keep the warning only.
3. The run fails **at the end**, after deletions and the immutable-tag end-state step, so healthy
   images are still cleaned and the repository is never left unlocked.
4. Dry runs fail too, so a scheduled preview also surfaces an inert image.
5. After merge, release v3.6.0; consumers opt in by bumping the pin and setting
   `fail_on_inert: true`.

The no-releases fail-safe itself (no boundary ⇒ nothing deleted) is unchanged. This change only
makes it visible.

## Steps

1. **Docs** — `docs/cleanup-gar-images.md` inputs table + a "Making an inert sweep fail" section +
   caller example; input descriptions in the workflow; `DECISIONS.md` entry + index line;
   `catalog.json` if it lists inputs.
2. **Tests (red first)** — `tests/run_plan_tests.py` gains an optional `expect_inert` /
   `expect_inert_allowed` check; fixtures `v15` (inert image listed, healthy image's deletions
   unchanged) and `v16` (allow-listed image not listed); `expect_inert: []` on a healthy fixture.
   `tests/run_step_tests.py` gains a "Fail on inert images" section: flag off → rc 0; flag on +
   inert → rc 1 with `::error::` naming image and pattern; flag on + none → rc 0; flag on +
   allow-listed only → rc 0; summary mentions inert images.
3. **Implement** — plan step always records `inert` and `inert_allowed` in the plan JSON; summary
   step lists them; new last step `Fail on inert images` (`shell: bash`), gated on the flag and on
   the plan having been produced.
4. **Gates** — `actionlint`, both test runners, consumer-name sweep of diff and PR text.

## Verification

Red → green on both runners; CI green. Positive control after rollout: a dry run against a repo
with a non-matching image must go red naming it.
