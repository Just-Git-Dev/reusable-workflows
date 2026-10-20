# repos-variables

Feature **F4** of [repos as code](repos-register.md): keep the NON-secret repository variables a
repo's `variables:` lists. Reusable workflow `repos-variables.yml`; the decision is
`scripts/repos_plan.py --feature variables`. Secrets are out of scope.

## What it does

| Plan entry | Meaning | Applied by |
|---|---|---|
| `set-variable{name, from, to}` | a listed variable differs (enforce); `from: null` = missing | `POST` (create) or `PATCH` (update) on `repos/<org>/<repo>/actions/variables` |
| `drift{would: set-variable, ...}` | the same, in report mode | nothing |
| `in-sync` | every listed variable matches | nothing |
| `skip` | the repo does not exist | nothing |

Variables that exist live but are not listed are left alone and not reported. Nothing is ever
deleted. Names must match `^[A-Z_][A-Z0-9_]*$` and not start with `GITHUB_`; values are strings.

## Modes and tokens

Mode per repo is the repo's `mode`, else `defaults.mode`, else `report`. A **read** token
(`metadata:read`, `actions_variables:read`) is always minted; a **write** token
(`actions_variables:write`, `metadata:read`) only when the plan holds a write action.

**Write token scope.** A step computes the plan's write targets (the repos with `set-variable` actions,
comma separated) and the write token is minted with `repositories:` set to exactly that list, so it
cannot touch any other repo. With no write targets no write token is minted and nothing is applied
(an empty `repositories:` would grant every repo). See [repos-register.md](repos-register.md) section 9.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `register` | no | `repos.yaml` | Plain relative path of the register |
| `app-id` | yes | | The GitHub App id (not secret), e.g. `vars.RELEASE_APP_ID` |
| `environment` | no | `repo-admin` | Must be `repo-admin`; holds the secret |

Secret `REPO_ADMIN_APP_KEY` (required, pass it by name). The job refuses to start unless the
environment is `repo-admin` and the ref is `refs/heads/main`. The job summary lists every repo
examined with the count; enforce stops at the first failed write.
See [section 9 of the contract](repos-register.md#9-the-repo-admin-environment).

## Caller

```yaml
jobs:
  variables:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-variables.yml@vX.Y.Z
    with:
      register: repos.yaml
      app-id: ${{ vars.RELEASE_APP_ID }}
    secrets:
      REPO_ADMIN_APP_KEY: ${{ secrets.REPO_ADMIN_APP_KEY }}
```
