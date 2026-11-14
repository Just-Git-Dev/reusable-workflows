# release-flow

A shared **multi-repo release flow** for a project that releases several service repos from one
root repo. The release is a reviewed file (a *release manifest*) merged into the root. The flow
then checks everything it can, writes draft Releases, smoke-tests the result, and publishes the
services one at a time, in order. Each publish triggers that service's own `Deploy` workflow,
and the flow waits until the deploy is proven live.

It is two things:

- **`actions/release-flow`**, a composite action that puts the `release-flow` CLI on `PATH`.
  All the logic lives in the CLI, which is plain Python (stdlib only, plus PyYAML for one
  subcommand) and unit-tested here.
- **Four reusable workflows** (`workflow_call`), which run the CLI in the right order with the
  right tokens:

| workflow | stage | writes? |
|---|---|---|
| [`release-pr-check.yml`](../.github/workflows/release-pr-check.yml) | on the release PR: exactly one new manifest, nothing else changed, the manifest's shape is valid | nothing, no secret |
| [`release-plan.yml`](../.github/workflows/release-plan.yml) | after merge: guard, plan, validate, CI-green, resolve, contract states, service gates | nothing (read-only tokens) |
| [`release-drafts.yml`](../.github/workflows/release-drafts.yml) | one **draft** Release per listed service, for the tag that already exists | draft Releases only |
| [`release-publish.yml`](../.github/workflows/release-publish.yml) | publish each draft in order, wait for its Deploy, prove it live, retry a failed deploy, then report | publish + re-run of its own failed Deploy |

```yaml
- uses: Just-Git-Dev/reusable-workflows/actions/release-flow@v6.2.1
# and, as jobs:
uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-plan.yml@v6.2.1
```

## Why this exists

The flow was built and proven in one project first. A second project needed the same thing, and
a copy per project drifts: every fix has to be made twice, and the copies stop agreeing on what
"live" means. So the proven code moved here, with every project-specific value turned into
config (`releases/services.json`) or a workflow input. Nothing in this repo names a project.

## What the caller keeps

A reusable workflow cannot call a workflow that its caller names. So two stages stay in the
caller's own `release.yml`, in between the shared ones:

1. **Contract checks.** Each project compares API specs its own way (spec copies, Go checks,
   `openapi-diff`). `release-plan` hands the caller the list of checks to run
   (`checks`, a matrix) and every service's resolved ref; the CLI also offers `spec-compat` and
   `ops-subset` for the caller to use.
2. **Smoke.** Usually the project's own `e2e.yml`, called as a workflow, against the resolved
   refs and images.

Any other pre-draft job the caller adds (for example pulling the candidate images) works the
same way: list it in `needs:`, and the drafts stage refuses to run unless it succeeded.

## Contract checks

The root release checks contracts **between services only**: each configured
`consumer -> provider` pair, at every intermediate state of the publish order (`checks`). Checks
inside one service (its own fixtures, its own client) belong to that service's CI.

`spec-compat BASELINE CANDIDATE` is one-directional. It fails only when the candidate provider
spec could break a consumer built against the baseline: an operation gone, a response property
missing, retyped, newly nullable or no longer required, a request parameter or body property
removed, newly required or narrowed, a `oneOf`/`anyOf` branch gone, new `security`, and a
construct it cannot compare. Additive changes pass. The full list is in the CLI reference
(`release-flow --help`). It prints `INCOMPATIBLE {where}: {msg}` per finding and
`examined N operation(s)`. Exit 1 = incompatible **or zero operations examined**; exit 2 = usage
or an unreadable file.

Both `spec-compat` and `ops-subset` take JSON or YAML, and the two sides may differ in format.
YAML is read with YAML 1.2 booleans: only `true`/`false` are booleans, so an unquoted `off`,
`on`, `yes` or `no` stays a string, exactly as it would in the JSON rendering of the same spec.
(Plain PyYAML follows YAML 1.1 and reads `off` as `false`. Up to v3.5.0, a JSON spec compared
with a raw YAML spec therefore reported a false "enum narrowed".)

### Breaking changes and the `breaking-approved` label

A removal that breaks a **live** consumer is a breaking change. It ships in one of two ways:

1. **Two releases (no label).** First release the consumer without its use of the item, so the
   live consumer no longer depends on it. Then release the provider removal. Every check stays
   green on its own.
2. **One release, approved.** The owner adds the label **`breaking-approved`** to the root
   release PR before merge, and the PR body lists **every** break exactly:

   ````
   ```breaking
   webapp -> backend | POST /login: body/extra_fields: property removed in candidate
   ```
   ````

   One line per break: `consumer -> provider | ` and then the spec-compat finding exactly as
   printed after `INCOMPATIBLE ` (`{where}: {msg}`). The pair uses the repo names from
   `services.json`, with no refs, because the manifest fixes the refs. Blank lines in the block
   are ignored.

**Accepted risk, signed by the label:** between the provider's deploy and the consumer's deploy,
the live consumer talks to a provider that no longer has the removed item. Use the label only
for an item the live consumer no longer exercises (for example, a field it sends but the
provider already ignores).

**The rules** (module `waiver.py`):

| # | rule | checked by |
|---|---|---|
| R1 | Label without a block, or a block without the label, fails. | `release-pr-check`, plan (rehearsal and real) |
| R2 | Exactly one ```` ```breaking ```` block; every line parses; no duplicate line; no empty block; every pair is a configured contract **or a declared `waiver_pairs` pair**. | `release-pr-check`, plan |
| R3 | Every listed pair has a **live-consumer** check in this release (`checks` entry with `consumer_side: live`); a declared pair needs only its presence in `waiver_pairs`. The approved list becomes the `breaking` output. | resolve |
| R4 | `spec-compat --pair "c -> p" --consumer-side live` with `RELEASE_BREAKING` set: each finding listed for this pair is printed `WAIVED` and written to the job summary; an unlisted finding fails; a listed entry that did not occur fails (no stale approvals). In a `--consumer-side candidate` check nothing is waived. | the caller's contracts job |
| R5 | A real release counts the label only if it was on the PR **before `merged_at`**: the last `labeled`/`unlabeled` event for it before the merge must be `labeled` (`issues/{n}/events`). A label added after the merge approves nothing. | plan (real release) |
| R6 | On any spec-compat failure, a ready-to-paste `breaking` block of what it found is printed. | the caller's contracts job |

**Never waivable:** spec-compat exit 2 (crash, unreadable file, bad `RELEASE_BREAKING`) and zero
operations examined fail with or without the label.

**Why only the live-consumer check.** One pair can appear in several states: in state 1 the
consumer is still live and the provider is new; in a later state both are new. The new consumer
was built without the removed item, so its check has nothing to waive, and a stale-entry rule
applied there would fail every approved release. A break in a candidate-consumer check means
the new consumer itself needs what the new provider removed. That is a broken release, not a
transient window, and no label can approve it. With the consumer live, the provider must be the
candidate (a state where both are live is not checked), so each pair has at most one
live-consumer check. Because of that, R3 and R4 together make "every waived finding" equal "the
block". Call spec-compat with `--pair` **once per matrix entry**.

### Caller-declared pairs (`waiver_pairs`)

A caller can have a compatibility stage of its own that is not a `contracts` pair. Example: consumer
A checks the oldest published client SDK against the candidate backend spec. It declares that pair
in the optional input `waiver_pairs`, and the same `breaking-approved` label and ```` ```breaking ````
block can then approve a break on it.

```yaml
waiver_pairs: "sdk-oldest -> backend"   # comma or newline separated; same string on both calls
```

- **Where.** Pass the **same** string to `release-pr-check` and to `release-plan`. If the two
  drift, the PR check and the Release disagree; the Release refuses before any write, so drift is
  safe.
- **Rules.** R1, R4, R5, R6 are unchanged. R2 accepts a configured contract or a declared pair.
  R3 for a declared pair is met by its presence in `waiver_pairs`; for a `contracts` pair it is
  unchanged (a live-consumer check is required).
- **Accepted risk.** The caller's own stage must run `spec-compat` for the declared pair
  (R4). If it does not, approved lines for that pair are never matched against findings, because
  R3 no longer forces "every waived finding equals the block" for declared pairs.
- **Refused with exit 2.** A malformed item, a duplicate, a declared pair that is also a configured
  contract (otherwise a caller could switch off R3's live-consumer check for a real contract by
  redeclaring it), and a provider that is not a service in `services.json`. A typo such as
  `sdk-oldest -> backned` fails the PR check on the first run with "provider 'backned' is not a
  service". The consumer side is a free name.
- **The caller's stage.** It runs
  `release-flow spec-compat BASE CAND --pair "sdk-oldest -> backend" --consumer-side live` with
  `RELEASE_BREAKING: ${{ needs.plan.outputs.breaking }}`. A stale entry fails there as for any pair.
- **Trap: the stage must always run.** The drafts verdict fails on any job in `needs` that is not
  `success`, except the contracts job when `checks` is `[]`. A declared-pair stage listed in
  drafts' `needs` must therefore run and pass when it has nothing to compare. Never `if:`-skip it.

**Pre-merge, for the author:**

1. Open the release PR. `release-pr-check` checks only the shape (R1, R2).
2. Run a **rehearsal** on it (see [Rehearsal](#rehearsal)). It fails in the contracts job and
   prints the ready-to-paste block (R6).
3. Paste the block into the PR body. `release-pr-check` re-runs on `edited` and is red (a block
   without the label).
4. The owner reviews the list and adds `breaking-approved`. `release-pr-check` re-runs on
   `labeled` and is green.
5. Rehearse again: green, with `WAIVED` lines in the contracts job's summary.
6. Merge. The real Release checks the same thing again (R1-R5) before its first write.

A post-merge failure before drafts writes nothing, so the same tags can be released again
through a corrected release PR. The merge guard judges the **newest** `release-pr` run on the PR
head, so the red run from step 3 does not block step 6. Every same-named run must still come
from GitHub Actions and from the release-pr workflow. The Release reads the PR body when its
plan job starts, seconds after the merge.

## Stages

```
release PR ──► release-pr-check (no secret)
merge ──► plan ──► [caller: contracts, images…] ──► drafts ──► [caller: smoke] ──► publish + report
           │                                          │                              │
           guard, validate, ci-green,                 first write                    one job per
           resolve, contract states,                  (draft Releases)               service, in
           service gates                                                             order
```

1. **PR check** (`release-pr-check`). The PR must add exactly one file
   `<release_dir>/YYYY-MM-DD-<slug>.yaml` and change nothing else. The manifest is parsed
   strictly and every repo in it must be in `allowed`. A `breaking` block in the PR body and the
   `breaking-approved` label must come together, and the block must be well-formed
   ([Contract checks](#contract-checks), R1-R2). It reads nothing outside the root repo
   and holds no secret. A PR can edit the workflow that runs this check, so this check catches
   mistakes, not attacks. The security boundary is the merge guard in the next stage.
2. **Plan** (`release-plan`), all read-only:
   - *guard*: the pushed commit belongs to exactly one **merged** PR into `base_branch`, whose
     `pr-check-name` check run came from GitHub Actions **and** from the workflow file
     `pr-check-workflow`; the newest such run on the PR head must be a success. A direct push
     releases nothing. No other run of the release workflow
     may be queued or running. A re-run attempt is refused.
   - *self-test*: the CLI's own unit tests run first (`python3 -P`, so nothing in the caller's
     checkout can be imported); a red or skipped test stops the release.
   - *plan*: the push changed exactly one manifest and nothing else; the publish order.
   - *breaking approval*: reads the release PR's label, body and label events (R1, R2, R5). In a
     rehearsal it reads the open PR whose branch is `manifest-ref`.
   - *validate*: for each listed service, the tag exists, is an annotated tag that peels to the
     listed sha, the sha is on `base_branch`, the version is above every existing Release and
     tag, no Release of that version exists yet, and the changelog has the version heading.
   - *ci-green*: each listed sha's own CI workflows (services.json `ci`) completed with success.
     A workflow with a path filter has no run on a push it filters out, so when there is no
     push run at the sha, ci-green reads the filter **from the workflow file at that sha**
     (`.github/workflows/<file>`, keys `on.push.paths` / `on.push.paths-ignore`; needs PyYAML)
     and walks first-parent ancestors (up to 20) to the nearest commit that has a run. That run
     must be green, and then:
     - `paths-ignore`: every file changed since that ancestor must match a `paths-ignore` glob.
     - `paths`: no file changed since that ancestor may be selected by `paths`. The patterns are
       read in order and the last one that matches a file decides, so
       `paths: ["src/**", "!src/docs/**"]` does not select `src/docs/a.md`.
     - no path filter: the run is `missing`.

     It **fails closed**, naming the reason, and never falls back to "no filter", when it cannot
     read the file at the sha, the YAML does not parse, PyYAML is missing, `push` is not a
     trigger, `push` lists only `tags`/`tags-ignore`, both `paths` and `paths-ignore` are set,
     a filter is not a list of strings, or a `paths-ignore` pattern starts with `!`. `on: push`
     and `on: [push, ...]` are push with no filter. A `paths_ignore` that services.json still
     declares must equal the file's `on.push.paths-ignore` exactly (same list, same order); the
     file is then read even when a run exists, and a mismatch fails with both values. Since
     v6.0.0; earlier versions trusted services.json and could not model `paths`.

     The drafts job re-runs ci-green just before the first write, but it holds a write token
     and installs nothing, so it never parses a workflow file. Plan's ci-green writes every
     filter it read to the `ci-filters` output (JSON `{repo/workflow@sha: {kind, globs}}`);
     drafts receives it inside `needs` and re-checks the runs with those filters. A file at a
     fixed sha cannot change, so plan's reading still holds. A filter drafts needs that plan
     did not hand over fails closed. Callers pass `toJSON(needs)` as before and change nothing.
   - *resolve*: every service's ref (the candidate sha if listed, else the **live** version) and
     image, and the contract checks for every intermediate state of the publish order. Every
     approved break must have a live-consumer check (R3); the list is the `breaking` output.
   - *service gates*: each listed service's own `release-gate` check on the tagged sha passed
     ([`check-release-gate`](check-release-gate.md)).
3. **Drafts** (`release-drafts`): the first write. One draft Release per listed service, for the
   existing tag. It creates no tag and no ref. It refuses to run unless every upstream job
   succeeded.
4. **Publish** (`release-publish`): in order, one job per service, each with its own token
   scoped to that one repo. Each job re-checks the draft and the tag, publishes the draft
   (`PATCH {"draft": false}`), waits for the run named `Deploy <tag>`, re-runs its failed jobs
   up to twice, and proves the service live (see `kind`). The first failure stops every later
   service. A final job writes the report to the run summary and, for a real release, as a
   comment on the release PR.

   **Read errors while polling are retried; writes never are** (since v6.1.0). Publish polls
   in two places: the deploy-runs list while it waits for the deploy run, and (`download`
   kind) the release while it waits for the assets. In both, a failed GitHub **read** whose
   failure is an HTTP 5xx or a network error is treated as one more poll that saw nothing: it
   sleeps the usual interval (15 s for the runs list, 10 s for assets) and polls again, inside
   the same deadline (15 min per deploy wait; 6 tries for assets), so the worst case is
   unchanged. Five such errors in a row stop the publish as `published-deploy-failed`, with
   the last HTTP status in the detail. A 4xx is never retried (it will not fix itself). The
   other reads (the draft and tag checks before the PATCH, the one re-read after it) are not
   polls and keep their single try. A
   **write** is never retried: the publish `PATCH` and the rerun of failed jobs each run once,
   and a 5xx on either stops at once as before, because a write that timed out may still have
   happened. Why: one HTTP 504 on the runs list (a consumer release, 2026-11) stopped a
   release after its api was already live; a re-run never publishes, so that one blip cost a
   whole release PR with bumped versions.

### "Live" means a successful deploy, not a tag

A service's live version comes from its deploy workflow's **successful** runs, newest started
first. A run titled `Deploy vX.Y.Z` (from the deploy workflow's `run-name`) makes vX.Y.Z live; a
run titled `Deploy DRYRUN…` is skipped. A hand-dispatched run with no version in its title
(a deploy workflow from before `run-name`) counts as its ref when that ref is itself a `vX.Y.Z`
tag, because such a workflow deploys the ref it runs on, the same way a legacy tag push does.
For example, `Deploy` run on tag `v0.3.9` makes v0.3.9 live. Dispatched on a branch or a sha
(`Deploy main`), it fails the release, because then nobody knows what production runs. Tags and
Releases are not used: older repos carry stale ones.

## Safety properties (unchanged from the proven flow)

- **Three writes, no more.** Every App write goes through one client whose allowlist is exactly:
  create a Release with `draft: true`; `PATCH releases/{id}` with the body exactly
  `{"draft": false}`; re-run the failed jobs of this release's own Deploy run. No tag, no ref,
  no delete. A test pins the list.
- **Versions burn on failure.** Nothing deletes a tag or a draft. A retry is a new release PR
  with bumped versions.
- **Tokens are minted per job**, read-only everywhere except drafts and publish, and only for
  the repos in `allowed` (publish: the one repo that job publishes). The App key lives in the
  caller's `environment` and is named only as the `private-key` of a mint step.
- **Inputs reach shell only through `env:`**, never `${{ }}` inside `run:`.
- **A re-run never publishes** (`GITHUB_RUN_ATTEMPT` must be `1`).
- **Only idempotent reads retry.** Publish re-tries a deploy-runs `GET` on a 5xx or network
  error, inside the existing deadline (Stage 4). No write is ever retried, so a retry cannot
  publish twice or re-run a deploy twice.

### Why publish is one job per service, not one job for all

An App installation token lives 60 minutes. One publish can take up to ~50 minutes (three
deploy attempts of 15 minutes each, plus health), so one job walking four services could
outlive its token halfway through. A matrix cannot promise order or stop at the first failure.
So `release-publish` has six fixed slots (`publish-1` … `publish-6`). Slot *n* publishes the
*n*-th listed repo, or is skipped. It runs only if every earlier slot succeeded or was skipped,
and it mints a fresh token for **that one repo**, so the write scope stays per service. The
report counts a slot whose repo is listed, in an ok non-rehearsal run, as FAILED unless it
succeeded: a run cancelled after `publish-1` leaves the later slots `skipped`, and that is not a
publish. Only an empty slot, or a rehearsal, may be skipped.

### How the workflows load the CLI, and why that is pinned by content

A reusable workflow cannot use `./actions/…` from this repo: `./` resolves against the
*caller's* checkout (DECISIONS 2026-09-15). A version-tag `uses:` would fail this repo's
SHA-pin gate, and a SHA pin cannot name the release commit itself. So each shared workflow
checks out this repo at its own baked-in `WORKFLOW_VERSION` (stamped at release by
`scripts/stamp_version.py`), and then asserts that the checked-out `actions/release-flow` tree
hash equals `RELEASE_FLOW_TREE`, a value also baked into the workflow file. A caller that pins
the workflow by commit SHA therefore runs exactly the CLI that was reviewed with it, even if a
tag were moved. `scripts/stamp_version.py --check` (CI) fails when `RELEASE_FLOW_TREE` does not
match `git rev-parse HEAD:actions/release-flow`; the release sweep updates it.

## Rehearsal

`rehearsal: true` (pass the manifest path with `manifest:` and the branch that holds it with
`manifest-ref:`) runs the whole flow with **zero writes**: guard (minus the merged-PR check, since there is no merge), self-test, validate,
ci-green, resolve, service gates, the caller's contracts and smoke. The drafts stage then only
runs its read-only pre-checks and mints no write token, and the publish stage publishes
nothing and writes the report to the run summary only. Use it to prove a new adoption, or a new
version of this package, without burning a version: the tags must exist, but no Release is
created, so the same tags can then be released for real.

Wire it as a `workflow_dispatch` of the same `release.yml`, so the rehearsal runs exactly the
file a real release runs.

**The route.** The `release` environment is restricted to the base branch, so a rehearsal must
run ON the base branch; but merging the manifest there would start a real release. So: open the
release PR and do not merge it, then dispatch the release workflow on the base branch with
`manifest` = the manifest's path and `manifest-ref` = the PR's branch. The plan job fetches that
branch as **data only** (never checked out, never executed) and reads the manifest with
`git show`. Empty `manifest-ref` reads the manifest from the checked-out base branch;
`manifest-ref` is refused outside a rehearsal.

**One manifest copy per run.** In every run, real or rehearsal, the plan job uploads the manifest
file as the artifact `release-manifest` and outputs its `sha256` (`manifest-sha256`). Every later
job that reads the manifest (resolve, service-gates, drafts, each publish slot) downloads that
artifact to `release-manifest/manifest.yaml` and refuses to continue unless its sha256 equals
plan's (the drafts and publish stages get plan's value from `needs` through `verdict`). A real
release behaves as before (same content); a rehearsal never needs the manifest on the base
branch.

## `releases/services.json`

Read from the root repo's checked-out `base_branch`. A release PR cannot change it (the PR may
add one manifest and nothing else), and it cannot widen access by itself: every command also
takes `allowed`, and a config naming a repo outside it is refused.

```json
{
  "owner": "consumer-a-org",
  "gar_registry": "asia-southeast1-docker.pkg.dev/consumer-a-project",
  "release_dir": "releases",
  "base_branch": "main",
  "changelog": {"path": "CHANGELOG.md", "heading": "## {version}"},
  "deploy_run_name": "Deploy {tag}",
  "services": [
    {"repo": "backend", "kind": "image", "order": 1, "deploy_workflow": "deploy.yml",
     "image": "backend/core", "health_url": "https://gateway.example.test/.well-known/health",
     "health": {"path": "data.status", "expect": "UP"},
     "ci": [{"workflow": "ci.yml", "paths_ignore": ["**.md", "docs/**"]}]},
    {"repo": "webapp", "kind": "pages", "order": 2, "deploy_workflow": "deploy.yml",
     "ci": [{"workflow": "test.yml"}]},
    {"repo": "desktop", "kind": "download", "order": 3, "deploy_workflow": "release.yml",
     "assets": ["Setup.msi", "app.exe"], "ci": [{"workflow": "release-gate.yml"}]}
  ],
  "consumers_only": ["tool"],
  "contracts": [{"consumer": "webapp", "provider": "backend"}]
}
```

| key | required | default | meaning |
|---|---|---|---|
| `owner` | yes | — | GitHub org of the root and every service. Must equal the root repo's owner. |
| `gar_registry` | only if a service has `kind: image` | — | registry prefix; a resolved image is `<gar_registry>/<image>:<ref>` |
| `release_dir` | no | `releases` | where manifests live; a manifest is `<release_dir>/YYYY-MM-DD-<slug>.yaml` |
| `base_branch` | no | `main` | the branch a release PR merges into and every listed sha must be on |
| `changelog` | no | `{"path": "CHANGELOG.md", "heading": "## {version}"}` | each listed sha must have a line starting with `heading` (with `{version}` filled in, followed by whitespace or end of line) in `path`. `null` turns the check off. |
| `deploy_run_name` | no | `Deploy {tag}` | the `run-name` every deploy workflow sets. Must contain `{tag}` exactly once. The dry-run marker is the same text with `{tag}` replaced by `DRYRUN`. |
| `services[]` | yes, at least one | — | the deployable repos |
| `consumers_only` | no | `[]` | repos that release by tag push outside this flow and appear only as the consumer side of a contract. Their live version is their highest `vX.Y.Z` tag. Every one must also be in the `read-only-repos` input. |
| `contracts[]` | no | `[]` | `{consumer, provider}` pairs; each name must be a service or a `consumers_only` repo |

Per service:

| key | applies to | meaning |
|---|---|---|
| `repo`, `order` | all | repo name (in `owner`) and its unique publish position |
| `kind` | all | `image`, `pages` or `download` (below) |
| `deploy_workflow` | all | file name of the workflow that deploys on `release: published` and sets `run-name` to `deploy_run_name` |
| `ci` | all | `[{workflow, paths_ignore?}]`; each workflow's push run at the listed sha must be green. The path filter is read from the workflow file (*ci-green* above); `paths_ignore` is optional and, when given, must equal the file's `on.push.paths-ignore` |
| `image` | `image` (required) | image path under `gar_registry` |
| `health_url` | `image` (required) | unauthenticated GET after the deploy |
| `health` | `image` (optional) | `{"path": "data.status", "expect": "UP"}` (the default): the health response must be HTTP 200 with the JSON value at the dotted `path` equal to `expect` |
| `assets` | `download` (required) | non-empty list of unique file names |

What **live** means per kind, after the publish:

- `image`: the `Deploy <tag>` run succeeded, then the health check passed (6 tries, 10 s apart).
- `pages`: the `Deploy <tag>` run succeeded.
- `download`: the `Deploy <tag>` run succeeded, then the published Release carries **every**
  name in `assets` with state `uploaded` (6 tries, 10 s apart). A missing asset is
  `published-deploy-failed`: the Release is public, so the version is burned.

`image`-only keys on another kind, or `assets` on a non-`download` service, are config errors.

## The manifest

```yaml
# releases/2026-10-13-backend-fix.yaml
services:
  - {repo: backend, version: v1.4.0, sha: 0123456789abcdef0123456789abcdef01234567}
```

Five line shapes only (comment, blank, `services:`, entry); anything else is an error with its
line number. It is deliberately not parsed as YAML: anchors, duplicate keys and type coercion
are each a way for a reviewed file to mean something other than what the reviewer read. The
owner pushes each **annotated** tag before opening the release PR; the flow never creates one.

## Proposing a release

`release-flow propose` opens the release PR for you, once the service gates are green. It is a
**local command**, run from a checkout of the root repo by the project's own session, right
after the tag push. It uses 0 Actions minutes, and no service repo ever triggers the root
(a scheduled root workflow polling every 15 min would cost about 2,900 billed min/mo, more
than it saves). Since v6.1.0.

```bash
cd <root-repo checkout>
release-flow propose backend@v1.4.0 webapp@v2.0.1 --slug backend-fix --allowed backend,webapp,desktop
```

Why: the 2026-11-03 review found the gap between a green gate and an opened release PR was
1-49 min in one project and often overnight in another, and five failed releases came from
ordering slips by hand: a PR opened before the tag existed, or a manifest filename with a dot.

### What it does, in order

Every step before step 7 only reads. A step that fails stops the command and nothing is
written, so re-running it is always safe.

1. **Arguments.** Each `REPO@TAG` names a service in `services.json` and in `--allowed`, with a
   `vX.Y.Z` tag; a repo may appear once. `--slug` matches `[a-z0-9][a-z0-9-]*` (so no dots, no
   underscores, no upper case). The manifest path is `<release_dir>/<today UTC>-<slug>.yaml`
   and must pass the same name rule as the PR check.
2. **Root repo.** The current directory is a git checkout whose `origin` is the root repo
   (`--root owner/name` overrides the detected name); its owner must equal `owner` in
   `services.json`. The `origin` URL (`git remote get-url origin`, https or ssh form) must name
   that same `owner/name`, so a fork checkout is refused before anything is fetched or pushed.
   It runs `git fetch origin <base_branch>` once and records that commit as **the base**; every
   later step uses that one commit, never `origin/<base_branch>` again (a fetch by another tool
   during the gate wait must not change what the PR is built on). The manifest path must not
   exist in the base, and the branch `release/<date>-<slug>` must not exist on `origin`.
   Inherited git environment variables (every name `git rev-parse --local-env-vars` lists, plus
   `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT` and its `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n`
   pairs) are removed from every git call, so a calling hook cannot redirect the push.
3. **Tags.** Each tag must exist and be an **annotated** tag; its commit is the manifest `sha`.
   A lightweight tag is refused with "re-push it with git tag -a".
4. **Gates.** It waits for each service's `release-gate` check run (from GitHub Actions only,
   newest wins; the same reading as [`check-release-gate`](check-release-gate.md)) on that sha
   to finish. It polls every 20 s, read-only, for up to `--wait-min` minutes (default 30). A
   gate that has not started yet is waited for, not failed. A read that fails with a 5xx or a
   network error is retried on the next poll (five in a row stop it).
5. **Validate.** The same checks the plan stage runs (*validate* in [Stages](#stages)): tag
   peels to the sha, sha on `base_branch`, version above every Release and tag, no Release of
   that version yet, changelog heading present. Every failure is listed.
6. **Manifest.** One file, the listed services in `services.json` order, re-read with the
   strict manifest parser before it is used, so propose cannot write a file the PR check
   would refuse.
7. **PR.** The commit is built with git plumbing from the base recorded in step 2 (its tree,
   and it as the only parent) plus the one manifest, so your working tree, index and current branch are never touched. It is pushed
   as `release/<date>-<slug>` and the PR is opened with `gh pr create` (title
   `release: backend v1.4.0, webapp v2.0.1`; the body lists each service, its sha and its
   green gate run). The PR URL `gh pr create` prints must be
   `https://github.com/<root>/pull/<number>`; anything else stops before auto-merge (exit 3),
   so `gh pr merge` is never called with an empty or foreign URL.
8. **Auto-merge.** Unless `--no-auto-merge`, it reads the base branch's required status checks
   (classic branch protection **and** rulesets) and enables auto-merge (`gh pr merge --auto
   --squash`; `--merge-method` changes it) **only if** the PR check (`--pr-check`, default
   `release-pr / release-pr`) is among them. If it is not required, or the protection cannot
   be read, auto-merge stays off: `gh pr merge --auto` on a branch with no required check
   merges at once, untested. The PR stays open for you to merge by hand.

`--dry-run` runs steps 1-6 and the protection read of step 8, prints the manifest, the branch
and the exact commands it would run. It writes nothing to GitHub and creates no object, commit
or branch; the one local change is that step 2's `git fetch` refreshes `origin/<base_branch>`,
the same as any fetch.

### Auto-merge: what the root repo must set

For the release PR to merge by itself, the root repo must (a) make `release-pr / release-pr` a
**required** status check on `base_branch`, and (b) allow auto-merge (repo setting *Allow
auto-merge*). Your approval then moves from the merge click to the tag push: once the tags
are pushed and the gates are green, the release goes out without another click.

Auto-merge adds no new risk for breaking changes. An unapproved break has no
`breaking-approved` label and no `breaking` block, so the plan stage fails before drafts
([Contract checks](#contract-checks)); nothing is written and the same tags can be released
again through a corrected PR. The merge guard is unchanged: an auto-merged PR is still a real
merged PR whose check run passed.

### What it prints

```
propose: root consumer-a-org/release, base main, manifest releases/2026-11-03-backend-fix.yaml
tag: backend v1.4.0 -> 0123456789ab (annotated)
gate: backend v1.4.0 release-gate in_progress (2m40s) https://github.com/.../runs/1
gate: backend v1.4.0 release-gate success https://github.com/.../runs/1
validate: 1 service(s), 0 failure(s)
pushed: release/2026-11-03-backend-fix @ 89abcdef0123
PR opened: https://github.com/consumer-a-org/release/pull/42
auto-merge: on (release-pr / release-pr is required on main)
```

A waiting line is printed only when a gate's state changes, and once a minute while it is
unchanged. The other endings:

| case | last line | exit |
|---|---|---|
| a gate finished red (any conclusion but `success`) | `gate red: backend v1.4.0 release-gate failure <url>: fix it and push a new tag; nothing was written` | 1 |
| a gate not finished in time | `gate not finished after 30 min: backend v1.4.0 (<state>); run propose again, nothing was written` | 1 |
| validate failed | one `FAIL: <repo>: <reason>` line each, then `nothing was written` | 1 |
| auto-merge refused (check not required) | `auto-merge: off (release-pr / release-pr is not a required check on main, so --auto would merge at once untested); merge by hand once it is green` | 0 |
| auto-merge denied (`gh pr merge` failed, e.g. under Claude's auto mode or with auto-merge disabled on the repo) | `auto-merge: off (gh pr merge failed: <reason>); run: ! gh pr merge <url> --auto --squash` | 0 |
| `--dry-run` | `dry run: nothing was written` | 0 |

Exit codes as for every subcommand: 0 PR opened (or dry run done); 1 a gate or a check failed;
2 usage, bad config, a repo outside `allowed`, manifest or branch already there; 3 an
unexpected GitHub or network error.

Token: `RELEASE_FLOW_READ_TOKEN` if set, else `gh auth token`. The push and the PR use your own
git and `gh` login; no App token is involved.

## Inputs, outputs, secrets

**Secrets: in App mode, pass `RELEASE_APP_KEY` to `release-plan`, `release-drafts` and
`release-publish` BY NAME** (`secrets: {RELEASE_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}}`),
never with `secrets: inherit`. Each of the three declares it as an optional `workflow_call`
secret (optional because a caller may pass `github-token` instead; see
[Credentials](#credentials)).
The jobs that mint a token declare `environment: <environment>`. Inside those jobs GitHub
resolves that environment's *variables*, but an environment *secret* the caller did not pass
resolves to an empty string, with no error until the mint fails ("The 'private-key' input must
be set to a non-empty string"). GitHub's docs say a caller "can pass a secret by name even if it
only exists in the environment". `inherit` is not a substitute. It works only when the caller is
in the same organization or enterprise as this repo, and a consumer whose root repo is in
another org measured exactly that empty-key failure with `inherit` in place. (An earlier
same-repo call had seemed to prove `inherit` worked.) Passing by name also hands over only this
one secret, where `inherit` hands over all of them. The environment must hold a secret named
**`RELEASE_APP_KEY`**: the private key of a GitHub App installed on
every repo in `allowed` and `read-only-repos`, with contents read/write, actions read/write and
checks read. Restrict the environment to `base_branch`. Inside the shared workflows the key is
named only as the `private-key` of a mint step. `release-pr-check` takes no secret: pass it
none.

**`client-id` must resolve in the CALLER, so it cannot live only on the environment.** It is
the App's **Client ID** (a string such as `Iv23li...`), not the numeric App ID. The shared
workflows never read `vars.RELEASE_APP_CLIENT_ID` themselves; the mint steps use
`inputs.client-id`, and an input's `with:` expression is evaluated in the caller's job. A job
that `uses:` a reusable workflow has no environment, so `${{ vars.RELEASE_APP_CLIENT_ID }}` there
sees only repo and org variables. If the variable exists only on the `release` environment, the
input arrives empty. The guard then fails the run with "App incomplete: missing client-id" (or
"no credentials", when no key is passed either), before any write. (Before v6 the same mistake
surfaced at the first mint, measured in a consumer's rehearsal.) Define `RELEASE_APP_CLIENT_ID`
as a **repo (or org) variable**, or pass the id as a literal. It is not secret.

### Credentials

Every job that needs more than the caller's `GITHUB_TOKEN` gets its token from one of two modes.
Pass exactly one.

- **App mode:** `client-id` (the App's Client ID) plus the secret `RELEASE_APP_KEY`. The
  workflows mint short-lived installation tokens from them, scoped per job.
- **Token mode:** one secret, `github-token` (for example a fine-grained PAT). Every job that
  would hold a minted token holds this one instead. No `client-id` and no `RELEASE_APP_KEY`.

A guard step runs first in every job that mints a token (each declares the caller's
environment, where a key or token is visible), before any mint. It fails the run with one of these `::error::` messages,
checked in this order (a `release-publish` rehearsal runs no publish job, so it does not run the
guard either; a missing `secrets:` on the publish call shows up only on the real run):

| case | message |
|---|---|
| any App field and `github-token` both passed | `pass the App or github-token, not both` |
| nothing passed | `no credentials: pass the App (client-id and its private key) or github-token` |
| key passed, `client-id` empty | `App incomplete: missing client-id` |
| `client-id` passed, key empty | `App incomplete: missing private key` |

Either App field counts as "the App is given". So half an App plus `github-token` is refused as
"both", and half an App alone is refused as "App incomplete". Nothing guesses which was meant.

**Least privilege.** A token you pass as `github-token` gets none of our narrowing: no per-job
`permissions`, no repository limit (one repo per publish slot), no read-only token for read jobs
or a rehearsal, and it is not revoked at the end of the job. We do not mint or revoke it. Its
scope is the caller's responsibility. App mode stays the least-privilege option. In token mode
the same token goes to every job of the flow, and there is no separate read token. The jobs that
hold it are:

- `release-plan`: `resolve` (it installs PyYAML from PyPI, then runs ci-green with the token in
  its env) and `service-gates` (it passes the token to the `check-release-gate` action). This
  holds in a rehearsal too.
- `release-drafts`: `drafts`.
- `release-publish`: `publish-1` to `publish-6`.

In App mode the first two hold a read-only token. Give a `github-token` only the access the whole
flow needs: contents read/write, actions read/write and checks read on every repo in `allowed`
and `read-only-repos`, and nothing else.

**The caller's `GITHUB_TOKEN`** is used only for reads of the root repo and the PR comment. A
called workflow's token can never have more than the calling job grants, so grant what each
call below lists.

### `release-pr-check.yml`

| input | required | default | meaning |
|---|---|---|---|
| `allowed` | yes | — | comma list of service repos a manifest may name |
| `config` | no | `releases/services.json` | path in the root repo |
| `waiver_pairs` | no | `''` | extra `consumer -> provider` pairs (not `contracts` pairs) the `breaking-approved` label may waive; comma or newline separated; pass the same string to `release-plan`. See [Caller-declared pairs](#caller-declared-pairs-waiver_pairs). |

Job name `release-pr`; called from a caller job also named `release-pr`, the check run is
`release-pr / release-pr`. Caller permissions: `contents: read`. Trigger it on
`[opened, synchronize, reopened, edited, labeled, unlabeled]`, so adding or removing
`breaking-approved` and editing the `breaking` block re-run the check. It reads the label and
body from the event payload, with no token.

### `release-plan.yml`

| input | required | default | meaning |
|---|---|---|---|
| `allowed` | yes | — | comma list of the service repos the App may write. **Hard-code it** in `release.yml`. |
| `read-only-repos` | no | `''` | comma list of extra repos the App may only read (the `consumers_only` repos) |
| `client-id` | no | `''` | App mode: the release App's Client ID, not the numeric App ID (not secret; e.g. `${{ vars.RELEASE_APP_CLIENT_ID }}` as a **repo/org** variable — an environment-only variable is empty here, see above). Leave it out in token mode; see [Credentials](#credentials). |
| `environment` | no | `release` | the environment holding `RELEASE_APP_KEY` |
| secret `RELEASE_APP_KEY` | no | — | App mode: the App's private key |
| secret `github-token` | no | — | token mode: one token used by every job instead of the App |
| `config` | no | `releases/services.json` | |
| `waiver_pairs` | no | `''` | as in `release-pr-check`; the same string must be passed to both |
| `release-workflow` | no | `release.yml` | file name of the caller's release workflow (for the concurrent-run guard) |
| `pr-check-name` | no | `release-pr / release-pr` | the check run the merged PR must carry |
| `pr-check-workflow` | no | `.github/workflows/release-pr.yml` | the workflow file that check must come from |
| `rehearsal` | no | `false` | see Rehearsal |
| `manifest` | rehearsal only | `''` | the manifest path to rehearse; must be empty for a real release |
| `manifest-ref` | no | `''` | rehearsal only: the branch to read the manifest from (fetched as data; letters, digits, `._/-`, no `..`). Empty = the checked-out base branch. Must be empty for a real release. |

| output | meaning |
|---|---|
| `manifest` | the manifest path |
| `manifest-sha256` | sha256 of the manifest file; later stages check the staged `release-manifest` artifact against it |
| `pr` | the release PR number (`''` in a rehearsal) |
| `order` | listed repos in publish order, comma-separated |
| `rehearsal` | `'true'` or `'false'` |
| `resolved` | JSON `{repo: {ref, version, listed, image, live_ref}}` for every service and `consumers_only` repo. `ref` is a 40-hex sha or `vX.Y.Z`. |
| `checks` | JSON list for a matrix `include`: `[{consumer, consumer_ref, provider, provider_ref, states, provider_live_ref, consumer_side}]`. There is one entry per distinct consumer@ref → provider@ref pair across every intermediate state of the publish order. `states` lists the labels of the states that need it (`new a,b; live c`). `provider_live_ref` is the provider's LIVE version even when `provider_ref` is its candidate, so a check can compare a consumer against what production serves. `consumer_side` is `candidate` when the consumer is in the manifest at that state, else `live`. `[]` when no contract involves a listed service. |
| `breaking` | JSON list of the approved breaking changes, `[{consumer, provider, finding}]` (see [Contract checks](#contract-checks)); `[]` without the `breaking-approved` label. Pass it to `spec-compat` as `RELEASE_BREAKING`. |
| `labels` | JSON list of the release PR's label names at the moment it merged: label events are replayed strictly before `merged_at` (the R5 rule), so a label added after the merge is not listed. A rehearsal reads the open PR's current labels; a rehearsal without `manifest-ref` gives `[]`. Use it instead of a caller-owned labels job, e.g. `contains(fromJSON(needs.plan.outputs.labels), 'skip-smoke')`. |

Caller permissions: `contents: read`, `pull-requests: read`, `checks: read`, `actions: read`.

### `release-drafts.yml`

| input | required | default | meaning |
|---|---|---|---|
| `needs` | yes | — | `${{ toJSON(needs) }}` from the calling job |
| `allowed`, `client-id`, `environment`, `config`, secrets `RELEASE_APP_KEY`, `github-token` | as `release-plan` | | |
| `contracts-job` | no | `contracts` | the caller's contract job id. It may be `skipped` only when `checks` is `[]`. |

It refuses to run unless the `needs` include a job `plan` that succeeded, and every other job
in `needs` succeeded (the contract job may be skipped as above). Output: `drafts`, JSON
`{repo: release_id}` (in a rehearsal, `{repo: "rehearsal"}`). Caller permissions:
`contents: read`.

### `release-publish.yml`

| input | required | default | meaning |
|---|---|---|---|
| `needs` | yes | — | `${{ toJSON(needs) }}`; must include `plan` and `drafts` |
| `allowed`, `client-id`, `environment`, `config`, `contracts-job`, secrets `RELEASE_APP_KEY`, `github-token` | as above | | |
| `required-jobs` | no | `plan,drafts` | comma list of job ids that must be present in `needs` |

Publishes up to **6** services (one job each); a manifest listing more is refused at plan. Call
it with `if: ${{ always() }}` so the report is written even when an earlier stage failed: in
that case, and in a rehearsal, it publishes nothing and only reports. Caller permissions:
`contents: read`, `pull-requests: write` (the PR comment).

## Caller example

```yaml
# .github/workflows/release-pr.yml
name: release-pr
on:
  pull_request:
    types: [opened, synchronize, reopened, edited, labeled, unlabeled]   # label/body = breaking approval
    paths: ['releases/*.yaml']   # manifests only, like release.yml: a config-only PR is not a release PR
permissions: {}
jobs:
  release-pr:
    permissions: {contents: read}
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-pr-check.yml@v6.2.1
    with:
      allowed: backend,webapp,desktop
      waiver_pairs: sdk-oldest -> backend   # optional; same string on the plan call
```

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    branches: [main]
    paths: ['releases/*.yaml']
  workflow_dispatch:
    inputs:
      manifest: {description: 'Rehearse this manifest (no writes)', required: true}
      manifest-ref: {description: 'Branch holding that manifest (the unmerged release PR branch)', required: true}
permissions: {}
jobs:
  plan:
    permissions: {contents: read, pull-requests: read, checks: read, actions: read}
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-plan.yml@v6.2.1
    with:
      allowed: backend,webapp,desktop
      client-id: ${{ vars.RELEASE_APP_CLIENT_ID }}
      waiver_pairs: sdk-oldest -> backend   # optional; same string as in release-pr.yml
      rehearsal: ${{ github.event_name == 'workflow_dispatch' }}
      manifest: ${{ inputs.manifest || '' }}
      manifest-ref: ${{ inputs.manifest-ref || '' }}
    secrets:
      RELEASE_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}   # by name; `inherit` is same-org only

  contracts:                     # the caller's own contract checks
    needs: plan
    if: ${{ needs.plan.outputs.checks != '[]' }}
    strategy: {matrix: {include: '${{ fromJSON(needs.plan.outputs.checks) }}'}}
    runs-on: ubuntu-latest
    permissions: {contents: read}
    steps:
      - uses: Just-Git-Dev/reusable-workflows/actions/release-flow@v6.2.1
      # once per matrix entry; --pair + RELEASE_BREAKING apply the breaking-approved list
      - run: release-flow spec-compat baseline.yaml candidate.yaml --label "$PAIR" --pair "$PAIR" --consumer-side "$SIDE"
        shell: bash
        env:
          PAIR: '${{ matrix.consumer }} -> ${{ matrix.provider }}'
          SIDE: ${{ matrix.consumer_side }}
          RELEASE_BREAKING: ${{ needs.plan.outputs.breaking }}

  sdk-compat:                    # a caller-declared pair (waiver_pairs); must always run, never `if:`-skipped
    needs: plan
    runs-on: ubuntu-latest
    permissions: {contents: read}
    steps:
      - uses: Just-Git-Dev/reusable-workflows/actions/release-flow@v6.2.1
      - run: release-flow spec-compat oldest-sdk.yaml candidate.yaml --label "$PAIR" --pair "$PAIR" --consumer-side live
        shell: bash
        env:
          PAIR: sdk-oldest -> backend
          RELEASE_BREAKING: ${{ needs.plan.outputs.breaking }}
      # the release PR's labels (no labels job): fromJSON(needs.plan.outputs.labels)

  drafts:
    needs: [plan, contracts, sdk-compat]
    if: ${{ !cancelled() && needs.plan.result == 'success' }}
    permissions: {contents: read}
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-drafts.yml@v6.2.1
    with:
      needs: ${{ toJSON(needs) }}
      allowed: backend,webapp,desktop
      client-id: ${{ vars.RELEASE_APP_CLIENT_ID }}
    secrets:
      RELEASE_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}

  smoke:                         # the caller's own e2e, against the resolved refs
    needs: [plan, drafts]
    permissions: {contents: read}
    uses: ./.github/workflows/e2e.yml
    with:
      backend_ref: ${{ fromJSON(needs.plan.outputs.resolved).backend.ref }}

  publish:
    needs: [plan, contracts, sdk-compat, drafts, smoke]
    if: ${{ always() }}
    permissions: {contents: read, pull-requests: write}
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-publish.yml@v6.2.1
    with:
      needs: ${{ toJSON(needs) }}
      required-jobs: plan,drafts,smoke
      allowed: backend,webapp,desktop
      client-id: ${{ vars.RELEASE_APP_CLIENT_ID }}
    secrets:
      RELEASE_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}
```

Token mode for `release-plan` (a complete job; `drafts` and `publish` change the same way). Drop
`client-id` and `RELEASE_APP_KEY`, pass `github-token`, never both. The token's scope is yours to
set, see [Credentials](#credentials).

```yaml
# .github/workflows/release-token.yml
name: Release (token mode)
on:
  workflow_dispatch:
permissions: {}
jobs:
  plan:
    permissions: {contents: read, pull-requests: read, checks: read, actions: read}
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-plan.yml@v6.2.1
    with:
      allowed: backend,webapp,desktop
    secrets:
      github-token: ${{ secrets.RELEASE_TOKEN }}   # by name; one token for every job
```

## Moving from a project-local copy

If the project carries its own copy of these scripts (the origin of this package):

1. Pin this version in `release-pr.yml` and `release.yml` as above. Keep `services.json`; add
   only the keys whose default does not fit (most projects need none).
2. Map the old jobs: gate + plan + resolve + service-gates → `release-plan`; drafts →
   `release-drafts`; the per-service publish jobs + report → `release-publish`. The contract
   and smoke jobs stay; point them at `needs.plan.outputs.resolved` / `checks`, and replace
   `python3 scripts/<old>/<cli>.py` with `release-flow` from the composite action.
3. The `release-pr` check name changes to `release-pr / release-pr` (a called workflow's checks
   are named `<caller job> / <called job>`); `pr-check-name` exists if yours differs.
4. Env names changed: `RELEASE_FLOW_READ_TOKEN` / `RELEASE_FLOW_WRITE_TOKEN`.
5. **Rehearse**: open the release PR for a manifest whose tags are not yet released and do NOT
   merge it, then run `workflow_dispatch` on the base branch with `manifest` = the manifest path
   and `manifest-ref` = the PR branch. It must reach smoke green with zero writes. Then delete the local copy, and let the next
   real release go through the shared flow.

## Where not to adopt it

- A single-repo project: tag and deploy directly; there is no order or contract to protect.
- A project whose deploys are not triggered by `release: published`, or do not set
  `run-name: Deploy <tag>`: "live" cannot be proven, and publish would time out.
- A project that wants a failed release retried in place: this flow burns versions on purpose.

## CLI reference

`release-flow <subcommand>`; `--config` defaults to `releases/services.json` in the **current
directory**. Every manifest-bearing command needs `--allowed`.

| subcommand | does | token |
|---|---|---|
| `config-check --allowed A [--read-only R]` | loads config; refuses a repo outside `allowed`, a `consumers_only` repo outside `read-only` (checked only when `--read-only` is given, even as `""`; only the plan job, whose token covers those repos, passes it), an `owner` other than `GITHUB_REPOSITORY_OWNER`; prints `{owner, release_dir, base_branch}` | none |
| `find-manifest --base B --head H [--pr]` | the one added manifest; anything else changed fails | none |
| `check-merge --sha S --check-name N [--workflow-path P]` | the merge guard above; prints the PR number | read |
| `concurrent --workflow W --run-id ID` | no other run of W active | read |
| `validate M`, `ci-green M` | as in *Plan* | read |
| `order M`, `gate-services M` | publish order; the `check-release-gate` input | none |
| `resolve M`, `contract-states M` | as in *Plan* | read |
| `drafts M [--check-only]` | create drafts; `--check-only` runs every pre-check and writes nothing (no write token needed) | write (read with `--check-only`) |
| `publish M --repo X` | publish one draft and prove it live; prints `{repo, status, detail}` | write |
| `spec-compat BASELINE CANDIDATE [--pair "C -> P" --consumer-side live\|candidate]`, `ops-subset CONSUMER_COPY PROVIDER` | contract checks on OpenAPI files; with `--pair`, applies `RELEASE_BREAKING` (R4) and prints a paste-ready block on failure (R6) | none |
| `breaking-shape --event-file F [--waiver-pairs S]` | R1 + R2 from a `pull_request` event payload (labels, body) | none |
| `breaking-approval (--pr N \| --head-branch B) [--waiver-pairs S] [--labels-out F]` | R1 + R2 + R5 (real release, `--pr`) or R1 + R2 on the open PR of branch B (rehearsal); prints the approved list as JSON; `--labels-out` writes the PR's label names (JSON) from the same read | read |
| `breaking-matrix --breaking J --checks J [--waiver-pairs S] [--config C]` | R3: every approved pair has a live-consumer check, or is a declared pair; prints the list | none |
| `report --stage S --result R [--detail T] [--drafts F]` | the report markdown | none |
| `ci-verdict --repo O/R --sha S --workflows W[,W] [--match sha\|tree] [--github-output F]` | did CI already pass for this code? prints `{reuse, run_url, why, examined}`; exit 0 either way ([ci-verdict](ci-verdict.md)) | read |
| `propose REPO@TAG... --slug S [--dry-run] [--no-auto-merge] [--wait-min N] [--root O/R] [--pr-check C] [--merge-method M]` | wait for the gates, validate, open the release PR, enable auto-merge only when the PR check is required ([Proposing a release](#proposing-a-release)) | read + your `gh` login |

Environment: `RELEASE_FLOW_READ_TOKEN`, `RELEASE_FLOW_WRITE_TOKEN`, `GITHUB_REPOSITORY`,
`GITHUB_REPOSITORY_OWNER`, `GITHUB_RUN_ATTEMPT`. Exit codes: 0 ok; 1 a check failed; 2 usage,
bad config or manifest, repo outside `allowed`, missing token, or refused (re-run); 3 an
unexpected GitHub or network error.

Publish statuses: `published+live`; `published-deploy-failed` (published, but the deploy or the
live proof failed); `published-postcheck-failed` (published, then the re-read disagreed: the
deploy may be live, investigate); `not published` (refused before the write; the draft is
untouched).

## Testing

`python3 tests/run_release_flow_tests.py` runs the CLI's unit tests (an in-memory fake GitHub
drives every command through `main(argv, env, deps)`) and the workflow-shape tests (token scopes,
SHA pins, `shell: bash`, no `${{ }}` in `run:`). CI runs it in `step-bodies`.
