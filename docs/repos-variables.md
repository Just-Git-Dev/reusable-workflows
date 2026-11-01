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
| `client-id` | no | | The GitHub App's Client ID (not secret; not the numeric App ID), e.g. `vars.RELEASE_APP_CLIENT_ID` |
| `environment` | no | `repo-admin` | Must be `repo-admin`; holds the secret |

Secrets: `REPO_ADMIN_APP_KEY` (optional) and `github-token` (optional). The job refuses to start unless the
environment is `repo-admin` and the ref is `refs/heads/main`. The job summary lists every repo
examined with the count; enforce stops at the first failed write.
See [section 9 of the contract](repos-register.md#9-the-repo-admin-environment).

Credentials: pass the App (`client-id` plus the secret `REPO_ADMIN_APP_KEY`, by name) OR the
secret `github-token`, never both. All three are optional; the guard step refuses a call that
gets neither, both, or half the App, before any token is minted. It prints one of:

- `pass the App or github-token, not both`
- `no credentials: pass the App (client-id and its private key) or github-token`
- `App incomplete: missing client-id`
- `App incomplete: missing private key`

In token mode the one caller token is present in `report` runs too (App mode mints a read-only
token there), and this workflow never mints or revokes it: its scope and lifetime are the caller's
responsibility.

## Caller

```yaml
jobs:
  variables:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-variables.yml@vX.Y.Z
    with:
      register: repos.yaml
      client-id: ${{ vars.RELEASE_APP_CLIENT_ID }}
    secrets:
      REPO_ADMIN_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}
```

Token mode (no App): drop `client-id` and the key, pass one token instead.

```yaml
jobs:
  variables:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-variables.yml@vX.Y.Z
    with:
      register: repos.yaml
    secrets:
      github-token: ${{ secrets.REPO_ADMIN_TOKEN }}
```
