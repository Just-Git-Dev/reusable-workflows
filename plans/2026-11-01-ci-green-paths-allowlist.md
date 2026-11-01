# ci-green: model an `on.push.paths` allowlist (reusable-workflows, release-flow H8)

## Decision summary (one screen)

- **Problem:** H8 `ci-green` (`actions/release-flow/releaseflow/ci.py`) walks back to a green
  ancestor only when the services.json `ci` entry declares `paths_ignore`. A workflow filtered by
  an `on.push.paths:` allowlist has no run on most commits, so "no run" reads as "missing".
  Consumer C hit it; its workaround `"paths_ignore": ["**"]` turns the changed-files check into a
  no-op (RW TODO §"ci-green cannot model an `on.push.paths` allowlist", merged in #172).
- **Recommended shape (Q1 = A):** ci-green reads the trigger filter FROM THE WORKFLOW FILE at the
  listed sha (`on.push.paths` / `on.push.paths-ignore`) instead of trusting services.json.
  Why not "declare `paths` in services.json + a drift check" (the TODO's wording): the drift check
  must parse the same YAML anyway, so declaring it again only adds a second copy that can be wrong.
- **Walk-back rule, one sentence each:** no run at the sha →
  `paths-ignore` filter: every file changed since the green ancestor must match it (today's rule);
  `paths` filter: NO file changed since the green ancestor may be selected by it (GitHub's
  order-sensitive `!` negation honoured); no filter: "missing" (today's rule).
- **Cost:** ci-green needs PyYAML (already installed in release-plan for unit tests; must be
  added wherever ci-green runs without it, e.g. release-drafts' pre-check), plus one contents
  read per (repo, workflow).
- **Owner questions:** 4, all answered 2026-11-01 (below). Nothing is built until you say build.
- **Release scope (owner 2026-11-01):** v6.0.0 carries three breaking items and ships once:
  this change; #3 (`app-id` → `client-id`, plus a caller-supplied token as an alternative to the
  GitHub App on every workflow that needs more than `GITHUB_TOKEN`); and removing the deprecated
  `rotate-worker-signing-secret`. This plan covers only ci-green; #3 gets its own plan. ci-green
  lands on a v6 branch and is not released by itself.

## Context

- Evidence basis: `ci.py`, `config.py:201-210`, `docs/release-flow.md:285,315`,
  `test_ci.py`, `fake_github.py` read in this session (2026-11-01). Consumer C's incident is the
  peer's report, recorded in the TODO; not re-verified here.
- ci-green runs from `release_flow.py:451-459` (CLI) and `drafts.py:32` (drafts pre-check).
- `glob_match` (ci.py:24) already implements GitHub's `*` / `**` / `?`; reuse it.
- The CLI is stdlib-only except `spec-compat` / `ops-subset`, which import PyYAML lazily
  (`ops_subset.py:16`, and its YAML-1.2-booleans loader at :28). Reuse that lazy-import pattern
  and loader idea (PyYAML reads the key `on:` as boolean `True`; handle both).

## Open questions for the owner (plain words)

1. **ANSWERED 2026-11-01 (owner: A):** ci-green reads the trigger filter from the workflow file
   at the listed sha (`on.push.paths` / `on.push.paths-ignore`); services.json does not declare a
   `paths` allowlist. Was: A (recommended): read it from the workflow file at the sha. Example: consumer C's
   `changelog-hygiene.yml` says `on: push: paths: ["CHANGELOG.md"]`; ci-green reads that and needs
   nothing in services.json. B: declare `"paths": [...]` in services.json and also check it
   matches the file (same YAML parsing, two copies). C: declare only, no check (cheapest; can
   silently drift, which is the original failure class).
2. **ANSWERED 2026-11-01 (owner: fail now, major):** a services.json `ci` entry that still
   declares `paths_ignore` must equal the workflow file's `on.push.paths-ignore` exactly; any
   mismatch (including consumer C's `["**"]` against a `paths:` allowlist) fails the gate with both
   values named. This ships as **v6.0.0**; consumer C removes its workaround before upgrading.
   Was: **What happens to an existing `paths_ignore` in services.json** (under A).
   Recommended: still accepted, but it must equal the file's `paths-ignore`; a mismatch fails
   with "services.json says X, the workflow says Y". Consumer C's `["**"]` workaround would then
   FAIL until removed: a config that passed now fails, so this is a **major** (v6) by our semver
   rule, or a minor that only WARNS on mismatch until v6. Recommended: warn in v5.x, fail in v6.
3. **ANSWERED 2026-11-01 (owner: support):** a `paths` filter's `!` patterns follow GitHub's rule,
   evaluated in order with the last matching pattern deciding whether a file is selected.
   Was: **`!` negation in `paths`** (GitHub: `paths: ["src/**", "!src/docs/**"]`, last match wins).
   Recommended: support it, since it is part of the trigger language. Alternative: refuse such a
   workflow with a clear error.
4. **ANSWERED 2026-11-01 (owner: fail closed):** when ci-green cannot read or does not understand
   a workflow's trigger at the sha (404, YAML error, a form it does not model, `push` with only
   `tags:`), the gate fails with that reason and never falls back to "no filter".
   Was: **A workflow file ci-green cannot read or does not understand** (404 at the sha, YAML error,
   `on:` as a list/string, `push:` with only `tags:`). Recommended: fail closed with the reason
   ("cannot read the trigger of ci.yml at abc12345"), never fall back to "no filter".

## Steps (Doc → Test red → Implement → Refactor)

1. **Branch** `feat/ci-green-paths-allowlist` off `main` (4686fd8); carry the uncommitted
   `TODO.md` edit (#3 owner ruling on App + token auth) as its own first commit.
2. **Docs first:** `docs/release-flow.md` §H8 and the `ci` row (L315) state the rule from the
   decision summary + the answers to Q1-Q4; `ci.py` module docstring the same; `action.yml`
   description notes PyYAML for ci-green.
3. **Tests, confirmed red** (`actions/release-flow/releaseflow/test_ci.py`), one per scenario:
   - allowlist, no run at sha, changed files outside `paths` → green via ancestor;
   - allowlist, a changed file selected by `paths` → red, names the file;
   - negation: file under `!src/docs/**` → not selected → green;
   - paths-ignore read from the file (today's behaviour, now file-sourced) still passes;
   - services.json `paths_ignore` ≠ file → warn or fail per Q2;
   - unreadable / unparseable / list-form `on:` → fail closed per Q4;
   - `on:` parsed as `True` by PyYAML → handled;
   - examined count unchanged (positive control: a run that exercises the new path counts 1).
   `fake_github.py`: generalise the `contents/` route (today only `changelog_path`, L143) to
   serve workflow files per (path, ref).
4. **Implement** in `ci.py`: `_trigger_filter(reader, base, wf, sha)` → `("paths"|"ignore"|None,
   globs)`; `_selected(globs, path)` for last-match-wins with `!`; `_check_one` picks the rule.
   `config.py`: keep `paths_ignore` parsing; add the mismatch handling from Q2.
5. **Workflows:** make sure every job that runs ci-green installs PyYAML (verify
   `release-plan.yml` ~L197 is in the same job as ci-green; add the step to `release-drafts.yml`).
6. **Records:** `DECISIONS.md` entry (why file-sourced, why fail closed, why v6 bundles three
   items), `CHANGELOG.md` under an unreleased v6.0.0 heading with the consumer migration note
   ("remove a `paths_ignore` that differs from the workflow file"), tick the TODO item. No tag:
   v6.0.0 is cut only on your explicit ask, after #3 and the removal land.

## Verification

- `python3 -m unittest` in `actions/release-flow/releaseflow` (with PyYAML; a skip is a fail),
  red before step 4, green after; report the test count.
- `actionlint` + the SHA-pin check (`ci.yml` equivalents), `workflow_preflight.py`.
- Live proof is consumer C's: after release, its session removes the `["**"]` workaround and
  re-runs its release rehearsal. Handed over through that session, not run from here.
