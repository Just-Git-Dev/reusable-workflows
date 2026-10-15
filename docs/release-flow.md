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
- uses: Just-Git-Dev/reusable-workflows/actions/release-flow@v3.5.2
# and, as jobs:
uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-plan.yml@v3.5.2
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
| R2 | Exactly one ```` ```breaking ```` block; every line parses; no duplicate line; no empty block; every pair is a configured contract. | `release-pr-check`, plan |
| R3 | Every listed pair has a **live-consumer** check in this release (`checks` entry with `consumer_side: live`). The approved list becomes the `breaking` output. | resolve |
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

### "Live" means a successful deploy, not a tag

A service's live version comes from its deploy workflow's **successful** runs, newest started
first. A run titled `Deploy vX.Y.Z` (from the deploy workflow's `run-name`) makes vX.Y.Z live; a
run titled `Deploy DRYRUN…` is skipped; a hand-dispatched run with no version in its title fails
the release, because then nobody knows what production runs. Tags and Releases are not used:
older repos carry stale ones.

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
| `ci` | all | `[{workflow, paths_ignore?}]`; each workflow's push run at the listed sha must be green |
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

## Inputs, outputs, secrets

**Secrets: pass `RELEASE_APP_KEY` to `release-plan`, `release-drafts` and `release-publish`
BY NAME** (`secrets: {RELEASE_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}}`), never with
`secrets: inherit`. Each of the three declares it as its one required `workflow_call` secret.
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

**`app-id` must resolve in the CALLER, so it cannot live only on the environment.** The shared
workflows never read `vars.RELEASE_APP_ID` themselves; the mint steps use `inputs.app-id`, and
an input's `with:` expression is evaluated in the caller's job. A job that `uses:` a reusable
workflow has no environment, so `${{ vars.RELEASE_APP_ID }}` there sees only repo and org
variables. If the variable exists only on the `release` environment, the input arrives empty
and the first mint fails with "The 'client-id' (or deprecated 'app-id') input must be set to a
non-empty string", before any write. This was measured in a consumer's rehearsal. Define
`RELEASE_APP_ID` as a **repo (or org) variable**, or pass the id as a literal. It is not
secret.

**The caller's `GITHUB_TOKEN`** is used only for reads of the root repo and the PR comment. A
called workflow's token can never have more than the calling job grants, so grant what each
call below lists.

### `release-pr-check.yml`

| input | required | default | meaning |
|---|---|---|---|
| `allowed` | yes | — | comma list of service repos a manifest may name |
| `config` | no | `releases/services.json` | path in the root repo |

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
| `app-id` | yes | — | the release App's id (not secret; e.g. `${{ vars.RELEASE_APP_ID }}` as a **repo/org** variable — an environment-only variable is empty here, see above) |
| `environment` | no | `release` | the environment holding `RELEASE_APP_KEY` |
| `config` | no | `releases/services.json` | |
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

Caller permissions: `contents: read`, `pull-requests: read`, `checks: read`, `actions: read`.

### `release-drafts.yml`

| input | required | default | meaning |
|---|---|---|---|
| `needs` | yes | — | `${{ toJSON(needs) }}` from the calling job |
| `allowed`, `app-id`, `environment`, `config` | as `release-plan` | | |
| `contracts-job` | no | `contracts` | the caller's contract job id. It may be `skipped` only when `checks` is `[]`. |

It refuses to run unless the `needs` include a job `plan` that succeeded, and every other job
in `needs` succeeded (the contract job may be skipped as above). Output: `drafts`, JSON
`{repo: release_id}` (in a rehearsal, `{repo: "rehearsal"}`). Caller permissions:
`contents: read`.

### `release-publish.yml`

| input | required | default | meaning |
|---|---|---|---|
| `needs` | yes | — | `${{ toJSON(needs) }}`; must include `plan` and `drafts` |
| `allowed`, `app-id`, `environment`, `config`, `contracts-job` | as above | | |
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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-pr-check.yml@v3.5.2
    with:
      allowed: backend,webapp,desktop
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
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-plan.yml@v3.5.2
    with:
      allowed: backend,webapp,desktop
      app-id: ${{ vars.RELEASE_APP_ID }}
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
      - uses: Just-Git-Dev/reusable-workflows/actions/release-flow@v3.5.2
      # once per matrix entry; --pair + RELEASE_BREAKING apply the breaking-approved list
      - run: release-flow spec-compat baseline.yaml candidate.yaml --label "$PAIR" --pair "$PAIR" --consumer-side "$SIDE"
        shell: bash
        env:
          PAIR: '${{ matrix.consumer }} -> ${{ matrix.provider }}'
          SIDE: ${{ matrix.consumer_side }}
          RELEASE_BREAKING: ${{ needs.plan.outputs.breaking }}

  drafts:
    needs: [plan, contracts]
    if: ${{ !cancelled() && needs.plan.result == 'success' }}
    permissions: {contents: read}
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-drafts.yml@v3.5.2
    with:
      needs: ${{ toJSON(needs) }}
      allowed: backend,webapp,desktop
      app-id: ${{ vars.RELEASE_APP_ID }}
    secrets:
      RELEASE_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}

  smoke:                         # the caller's own e2e, against the resolved refs
    needs: [plan, drafts]
    permissions: {contents: read}
    uses: ./.github/workflows/e2e.yml
    with:
      backend_ref: ${{ fromJSON(needs.plan.outputs.resolved).backend.ref }}

  publish:
    needs: [plan, contracts, drafts, smoke]
    if: ${{ always() }}
    permissions: {contents: read, pull-requests: write}
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/release-publish.yml@v3.5.2
    with:
      needs: ${{ toJSON(needs) }}
      required-jobs: plan,drafts,smoke
      allowed: backend,webapp,desktop
      app-id: ${{ vars.RELEASE_APP_ID }}
    secrets:
      RELEASE_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}
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
| `breaking-shape --event-file F` | R1 + R2 from a `pull_request` event payload (labels, body) | none |
| `breaking-approval (--pr N \| --head-branch B)` | R1 + R2 + R5 (real release, `--pr`) or R1 + R2 on the open PR of branch B (rehearsal); prints the approved list as JSON | read |
| `breaking-matrix --breaking J --checks J` | R3: every approved pair has a live-consumer check; prints the list | none |
| `report --stage S --result R [--detail T] [--drafts F]` | the report markdown | none |

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
