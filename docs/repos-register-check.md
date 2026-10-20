# repos-register-check

Feature **F1** of [repos as code](repos-register.md): validate the register. Reusable workflow
`repos-register-check.yml`; the decision is `scripts/repos_plan.py --feature register`, which
validates the whole file against `schemas/repos.v1.json` and applies the cross-entry rules (unique
names, `rename_from` collisions). It writes nothing, mints no token and needs no environment, so
run it on every pull request that touches the register.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `register` | no | `repos.yaml` | Plain relative path of the register in the caller repo |

No secrets. Caller permissions: `contents: read`.

## What you see

- Valid: the job summary says how many repos were examined and lists them. An empty `repos:` list
  passes with a warning, because nothing was examined.
- Invalid: one `::error::` annotation per problem (`<repo|sa|register>: <reason>`), the same lines
  in the summary, and the job fails. `visibility: public` is a validation error.

## Caller

```yaml
jobs:
  check:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-register-check.yml@vX.Y.Z
    with:
      register: repos.yaml
```

The workflow checks this repo out at its own release tag (`WORKFLOW_VERSION`) to get the planner
and installs the pinned `requirements-ci.txt` (PyYAML, jsonschema). Pin an exact `vX.Y.Z`.
