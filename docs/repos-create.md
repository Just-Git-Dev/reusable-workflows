# repos-create

Feature **F2** of [repos as code](repos-register.md): create the repos the register marks
`status: new` and rename a repo that says `rename_from`. Reusable workflow `repos-create.yml`; the
decision is `scripts/repos_plan.py --feature create`.

## What it does

| Plan entry | Meaning | Applied by |
|---|---|---|
| `create-repo` | `status: new` and the repo is missing (enforce) | `POST orgs/<org>/repos` with name, visibility, description |
| `rename-repo` | `rename_from` exists, the new name does not (enforce) | `PATCH repos/<org>/<old>` with the new name |
| `drift{would: ...}` | the same, in report mode | nothing |
| `skip` | the repo exists (`exists`), or the rename is already done | nothing |
| `in-sync` | an existing repo with nothing to create | nothing |

It never deletes, archives or makes a repo public (`visibility: public` is refused at validation), never renames
without `rename_from`, and refuses the whole run when both the old and the new name exist.
The register's `default_branch` is carried in the `create-repo` entry, but a branch cannot exist in
an empty repo: the first push creates it, and [F3](repos-settings.md) reports a default branch that
does not match.

## Modes and tokens

Mode per repo is the repo's `mode`, else `defaults.mode`, else `report`. A **read** token
(`metadata:read`) is always minted. A **write** token (`administration:write`, `metadata:read`) is
minted only when the plan holds a write action, so a `report` run never holds write access. The App
must be installed on **all repositories** of the org, or it cannot see a repo it just created.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `register` | no | `repos.yaml` | Plain relative path of the register |
| `app-id` | yes | | The GitHub App id (not secret), e.g. `vars.RELEASE_APP_ID` |
| `environment` | no | `repo-admin` | Must be `repo-admin`; holds the secret |

Secret `REPO_ADMIN_APP_KEY` (required, pass it by name). The job refuses to start unless the
environment is `repo-admin` and the ref is `refs/heads/main`, before any token is minted. The job
summary lists every repo examined with the count; enforce stops at the first failed write. See
[section 9 of the contract](repos-register.md#9-the-repo-admin-environment).

## Caller

```yaml
jobs:
  create:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-create.yml@vX.Y.Z
    with:
      register: repos.yaml
      app-id: ${{ vars.RELEASE_APP_ID }}
    secrets:
      REPO_ADMIN_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}
```
