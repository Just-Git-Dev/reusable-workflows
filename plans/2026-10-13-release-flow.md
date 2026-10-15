# F2 shared release package: scripts + shared workflows in reusable-workflows

## Decision summary (one screen)

**What:** consumer A's proven release flow (`<consumer-A>/scripts/f2`, 13 Python modules, 271 tests, and its
736-line `release.yml`) becomes one package in the public `reusable-workflows` (rw) repo. Both
consumer A and consumer B pin it by exact tag, and consumer B keeps no copy of its own (owner, 2026-10-12;
scope widened by the owner on 2026-10-13 to include the shared workflow). The package has:
- **`actions/release-flow/`**: a composite action that puts the `release-flow` CLI (the ported
  f2 scripts) on PATH. It follows the existing `check-release-gate` and `refresh-api-spec`
  pattern.
- **Four shared workflows** (`workflow_call`):
  - `release-pr-check.yml`: the PR check;
  - `release-plan.yml`: guard, plan, validate, ci-green, order, resolve, the service gates
    (check-release-gate), and contract-states as an output;
  - `release-drafts.yml`: H2;
  - `release-publish.yml`: H4 in order, the H7/H9 retry, and the H5 report.
- **The caller keeps two jobs of its own, in between:** contract checks (consumer A runs Go + spec copies;
  consumer B runs openapi-diff) and smoke (each project's own `e2e.yml` `workflow_call`). A reusable
  workflow cannot call a workflow the caller names, so these stay with the caller. A caller's
  `release.yml` shrinks to roughly 80 lines.

**Key choices:**
1. Everything consumer A-specific becomes `releases/services.json` config or a workflow input. The
   config gains these keys:
   - `release_dir` (default `releases/`);
   - `base_branch` (default `main`);
   - `changelog` (`{path, heading}` or `null`);
   - `deploy_run_name` (default `Deploy {tag}`);
   - `health` (`{path: "data.status", expect: "UP"}`);
   - a new kind, **`download`**, with `assets: [...]`. Live means `Deploy <tag>` succeeded AND the
     Release carries every named asset (consumer B's sync: `Setup.msi`, `sync.exe`).
2. **Publish runs in one job** that walks the order, instead of consumer A's four hand-written jobs. Its
   App token is scoped to exactly the repos in the release manifest. This keeps least privilege
   per release, though not per service. A matrix can't guarantee order or stop-on-failure.
3. **Rehearsal mode** (`rehearsal: true`) runs plan → contracts → smoke and then stops: no drafts,
   no publish, no writes. That is how both projects prove the shared flow without burning a
   version (consumer B asked for this; consumer A uses it as the migration proof).
4. **Behaviour stays identical.** The `gh.py` write allowlist (3 calls), burn-on-failure, the
   annotated-tag peel, ci-green, and H7/H9 are unchanged. The ported 271 tests must pass with only
   placeholder renames (`consumer A` → `consumer-a-org`).
5. **Public, no names.** Nothing in rw names a consumer. Before every push and PR, a diff/PR-text
   grep checks for that (memory rule).

**Release:** rw v3.3.0 (minor: new workflows and a new action; no existing input changes). Tagging
needs your explicit OK at that step (push/merge never implies a release).
**Rollout:** consumer A first (its own session migrates, then a rehearsal proves parity, then its next
real release), then consumer B (adopts directly; a rehearsal; its G-final hold stays). devops never
edits either project's repo.

## Context
The owner ruled on 2026-10-12 (QA plan H6, "Shared release scripts") that consumer A's `scripts/f2`
becomes one shared, versioned package with no project names, adding a `download` kind for consumer B's
sync service. On 2026-10-13 the owner widened it to "scripts + shared workflow". consumer A's flow is
now proven: root Release run 38352494299 on 2026-10-13 went gates → drafts → smoke → publish,
devops-verified. consumer B has no local copy and its `release.yml` waits for the package tag
(consumer B session, 2026-10-13).

## Facts from exploration (verified = devops read it; agent = from an agent's summary, unverified)
- rw precedent (agent): composite actions `actions/<name>/action.yml` run `$GITHUB_ACTION_PATH/<script>`.
  Consumers pin `Just-Git-Dev/reusable-workflows/actions/<name>@vX.Y.Z`. Inside a reusable workflow
  only the fully-qualified `@vX.Y.Z` form works (DECISIONS 2026-09-15 trap). Release steps:
  `scripts/stamp_version.py vX.Y.Z` PR, then `gh workflow run release.yml -f version=…`. CI jobs:
  `lint` (actionlint + shellcheck `actions/**/*.sh`), `docs-coverage` (`docs/<name>.md` + README
  link), `step-bodies` (test runners), `pinned-actions`. Test runners: stdlib `tests/run_*.py`.
  There is no consumer-name CI guard, and no Python lint.
- consumer A f2 (agent): CLI `f2.py` with subcommands find-manifest, check-merge, concurrent, validate,
  ci-green, order, drafts, gate-services, resolve, contract-states, publish, ops-subset,
  spec-compat, report. Exit codes 0/1/2/3. Env `F2_READ_TOKEN`, `F2_WRITE_TOKEN`. Tests use
  `fake_github.FakeGitHub`, an in-memory transport, through `main(argv, env, deps)`. Runtime is
  stdlib-only except PyYAML (lazy, `ops_subset`). The literals to parameterise are at
  `guard.py:14,33,48`, `validate.py:106,127`, `publish.py:29-34,95,133-135`, `resolve.py:31-32`,
  `gh.py:58,77`, `manifest.py:24-25`, and `f2.py:103`.
- consumer B (agent, plus consumer B's own reply): there is no local copy. Its draft `releases/services.json`
  already uses `kind: download` + `assets`. All four deploys set `run-name: Deploy <tag>`. The gateway
  health check is consumer A-shaped. Order is gateway → webapp → site → sync. Smoke comes from its `e2e.yml`
  `workflow_call`, on an unmerged branch.
- Root never dispatches a Deploy dry run (H9). `Deploy DRYRUN` runs are only excluded when working
  out what is live. consumer B has been told.

## Plan: doc → test (red) → implement → handoff (dispatcher waves, partitioned by file)

Every brief says: never `git checkout/restore/stash/reset/clean`; return BLOCKED instead of
guessing; read sibling repos via Bash (`/usr/bin/grep`); never write to /tmp; no consumer names in
any rw file. Work happens on an rw branch `feat/release-flow` (not main).

| wave | agent | owns | does | returns |
|---|---|---|---|---|
| W1 | me | `docs/release-flow.md`, README link, rw `DECISIONS.md` entry | the design doc: why; the stages; the `services.json` schema (all keys, `download`); workflow inputs/outputs/secrets; the rehearsal; a caller example; the migration guide from a project-local f2; "where not to adopt" | — |
| W2 | builder | `actions/release-flow/releaseflow/**` (ported modules + tests), `tests/run_release_flow_tests.py` | (a) copy f2 verbatim, rename to placeholders, keep all 271 tests green; (b) **red tests first** for each new config key, the `download` kind, `publish-all` ordered stop-on-failure, rehearsal guards, and the default config/path; (c) implement → green; (d) a mutation check on each new behaviour | red/green output, test count, mutation table |
| W3 | builder | `actions/release-flow/action.yml`, `.github/workflows/release-{pr-check,plan,drafts,publish}.yml`, workflow-shape tests (ported from consumer A `test_workflow_shape/tokens`, generalised) | the composite action puts the CLI on PATH; the four `workflow_call` bodies. The App token is minted per job (`create-github-app-token`, SHA-pinned), with an `environment` input for the key. Write scope only in drafts/publish. Every `run:` has `shell: bash`. | actionlint clean, shape tests green |
| W3b | builder (after W3) | `ci.yml` wiring, `catalog.json` regen | add the test runner to `step-bodies` (with PyYAML), `py_compile` over `actions/**/*.py`, catalog | CI-equivalent local run |
| W4 | critic | read-only | review against H1–H9/J1/K1–K3 and consumer A's proven `release.yml` (`<consumer-A>/.github/workflows/release.yml`): any behaviour drift, token-scope widening, vacuous passes, consumer-name leaks | findings |
| W5 | me | PR | consumer-name grep on diff + PR text; open the PR; CI green; **owner merges**; then `stamp_version.py v3.3.0` PR and release, **only on the owner's explicit OK** | ls-remote, tag |
| W6 | me → project sessions | SendMessage | consumer A (consumer A session): migrate `release.yml` to the shared workflows, delete `scripts/f2`, rehearse, report the run id. Then consumer B (consumer B session): adopt, rehearse. devops verifies each run read-only. | run ids |

## Verification
1. W2: the 271 ported tests pass unchanged except placeholder renames (proves behaviour parity).
   The new tests go red first, then green, and every mutation of a new behaviour turns the suite red.
2. W3: actionlint clean. Shape tests assert per-job token scopes: write only in drafts/publish, and
   publish scoped to the manifest repos. They also assert SHA pins and `shell: bash`.
3. the consumer-name grep (memory rule; pattern kept out of this public file) over the diff and PR text returns 0.
4. The rw CI run is green on the PR.
5. **End-to-end:** consumer A's rehearsal run on the shared workflows reaches smoke green and makes zero
   writes (the release-run log shows no POST/PATCH). Its next real release publishes through them.
   consumer B's rehearsal then passes too.
6. DECISIONS entries in rw and claude-config; the tracker updated.

## Checklist
- [ ] W1 docs + DECISIONS
- [ ] W2 scripts ported (271 green) + new behaviours red → green + mutations
- [ ] W3 action + 4 shared workflows + shape tests
- [ ] W3b CI wiring
- [ ] W4 critic addressed
- [ ] W5 PR merged (owner) → v3.3.0 tagged (owner OK)
- [ ] W6 consumer A migrated + rehearsal verified → real release verified → consumer B adopted + rehearsal verified

