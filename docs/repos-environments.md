# repos-environments

Feature **F9** of [repos as code](repos-register.md): create the GitHub **environments** a service
repo needs, with their deployment branch (or tag) rule, from the `environments:` list in the
project's `repos.yaml`. Reusable workflow `repos-environments.yml`; the decisions live in
`scripts/repos_env_plan.py`, the workflow only fetches live state and applies the plan. The
register, the live-state JSON and the action list are defined in
[repos-register.md](repos-register.md) (sections 2, 3, 7 and 8).

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-environments.yml@v5.1.1
```

## Why it exists

A job that names an environment which does not exist **creates it with no branch rule**, so any
branch could then deploy to it. The point of an environment such as `prod` is "main only"; this
feature creates the environment first, with the rule, so that is never the case. v4 jobs also
refuse an environment that has no rule. Secrets are not part of this feature: they are written by
the repo's owner by hand, or by [distribute-env-secrets](distribute-env-secrets.md), and only
into an environment that already exists.

## The register key

Per repo, additive; every other feature ignores it:

```yaml
repos:
  - name: svc-a
    environments:
      - {name: prod,            branches: [main]}
      - {name: stage,           branches: [main], tags: ['v*']}
      - {name: stage-seed, branches: [main]}
```

`name` is required and unique within the repo. At least one of `branches` and `tags` is required;
each is a list of non-empty patterns. Required reviewers, wait timers, secrets and variables are
not keys. A repo with no `environments:` is not examined by F9, and an environment the register
does not list is reported, never changed ([The NEVER list](#the-never-list)).

## What it does, per repo and environment

| State found | Action |
|---|---|
| repo in the register does not exist | **error**, exit `1`, no plan at all (F9 never creates a repo; that is F2) |
| environment missing | `create-environment`, then one `add-branch-policy` per listed pattern |
| environment exists, custom branch policies off | switched on, then `add-branch-policy` for each missing pattern |
| a listed pattern missing | `add-branch-policy` |
| a policy present that the register does not list | `remove-branch-policy` (in `report`: `drift{would: "remove-branch-policy"}`) |
| everything as listed | `in-sync` |
| environment on the repo that the register does not list | `unmanaged-environment`, in both modes, never changed |

`mode` follows the register ([§4](repos-register.md#4-report-vs-enforce)): `report` (the default)
lists the actions and writes nothing; `enforce` applies them. Run `report` first and read the list.
The apply uses `PUT /repos/{owner}/{repo}/environments/{name}` with custom branch policies on and
protected-branches off, then `POST .../deployment-branch-policies` for each pattern (`type`
`branch` or `tag`). Both are idempotent: a second run is all `in-sync`.

The write token carries `administration: write` plus `actions: read` (the same read the planning token
has): removing a stale branch policy first LISTs the environment's policies, and that read needs it.
Before each `PUT` the step `GET`s the environment and merges. If it exists, the `PUT` body resends its
current `wait_timer`, `reviewers` (as `{type, id}`) and `prevent_self_review` beside
`deployment_branch_policy`, so existing protection is carried through unchanged whether or not GitHub
treats an omitted field as a reset. If the `GET` is a 404 the environment is new and the body holds only
`deployment_branch_policy`. Any other `GET` failure stops the step before the `PUT`.

## The NEVER list

F9, in any mode, never:

1. deletes an environment (deleting one deletes the secrets stored in it, which cannot be
   restored; this is item 11 of the register's [NEVER list](repos-register.md#5-the-never-list));
2. writes a secret or variable into an environment;
3. sets required reviewers or a wait timer (the reviewer rule is refused with HTTP 422 on a free
   private repo, so it is not offered at all);
4. creates a repo, or acts on a repo that is not in the register.

The planner has no verb for 1 to 3. An environment that `unmanaged-environment` reports is left
exactly as it is; retiring it is a decision for a human, after checking what it holds.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `register` | input | `repos.yaml` | path of the register |
| `environment` | input | `repo-admin` | the project repo's environment the job runs in; `main` only |
| `app_id` | input (req) | — | id of the GitHub App that creates the environments |
| `app_key` | secret (req) | — | the App private key, passed by name |

Whether the run is `report` or `enforce` comes from each repo's `mode` in the register, as for the
other GitHub-side features. In `report` the workflow mints a read token (`actions: read`,
`metadata: read`) and writes nothing. In `enforce` it mints `administration: write` narrowed to
exactly the repos the plan has write actions for, and mints no write token when that list is
empty. The job fails before minting a token unless it runs in the configured environment on
`refs/heads/main`. The run summary lists every repo and environment examined; zero examined fails.

## Credential

The App id and key are inputs, so the workflow does not assume which App is used.

**Ruling Q1 (owner, 2026-10-21):** the credential is the org's automation App (`<org>-automation`, formerly the release App). It holds
`Administration: write` for `enforce` (and `Actions: read` for `report`), alongside the
permissions it already holds. No separate repo-admin App exists. The App is installed on the
service repos, and `enforce` mints `administration: write` narrowed to the repos the plan writes
to. The rename and the permission grant are owner-side GitHub settings changes.
## Copy-paste

```yaml
name: repos-environments
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  environments:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-environments.yml@v5.1.1
    with:
      app_id: ${{ vars.RELEASE_APP_ID }}
    secrets:
      app_key: ${{ secrets.RELEASE_APP_KEY }}
```
