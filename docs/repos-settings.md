# repos-settings

Feature **F3** of [repos as code](repos-register.md): compare each registered repo's description,
visibility, default branch and `settings` with live. Reusable workflow `repos-settings.yml`; the
decision is `scripts/repos_plan.py --feature settings`.

## What it does

| Plan entry | Meaning | Applied by |
|---|---|---|
| `update-repo{field, from, to}` | one differing field (enforce) | `PATCH repos/<org>/<repo>` with `{field: to}` |
| `drift{would: update-repo, ...}` | the same, in report mode | nothing |
| `in-sync` | nothing differs | nothing |
| `skip` | the repo does not exist | nothing |

Only keys the register states are compared: `description`, `visibility`, `default_branch` (a repo's
own value, else `defaults`) and the boolean `settings` keys of the contract (a repo's `settings`
merged over `defaults.settings`; other keys are ignored). **Visibility is never written**, in
either direction: a difference is reported as `drift{would: update-repo, field: visibility}` in
both modes (a human changes it in GitHub; making a public repo private cannot be undone), and
`public` in the register is refused as a validation error. A `default_branch` that does not exist in the repo
is reported by the API error, never created. Repos not in the register get no action.

## Modes and tokens

Mode per repo is the repo's `mode`, else `defaults.mode`, else `report`. A **read** token
(`administration:read` + `metadata:read`, still read-only: the merge-setting fields may need the
former) is always minted; a **write** token (`administration:write`, `metadata:read`)
only when the plan holds a write action.

**Write token scope.** A step computes the plan's write targets (the repos with `update-repo` actions,
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
  settings:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-settings.yml@vX.Y.Z
    with:
      register: repos.yaml
      app-id: ${{ vars.RELEASE_APP_ID }}
    secrets:
      REPO_ADMIN_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}
```
