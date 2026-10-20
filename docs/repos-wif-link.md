# repos-wif-link

Feature **F5** of [repos as code](repos-register.md): link each repo to the deploy identity it may
act as. Reusable workflow `repos-wif-link.yml`; the decisions live in `scripts/repos_wif_plan.py`,
the workflow only fetches live state and applies the plan. The register, the live-state JSON and
the action list are defined in [repos-register.md](repos-register.md) (sections 6, 7 and 8).

## What it does

For each service account in a repo's `gcp.service_accounts`, the SA's IAM policy must hold
`roles/iam.workloadIdentityUser` for that repo's principalSet
(`principalSet://iam.googleapis.com/projects/<number>/locations/global/workloadIdentityPools/<pool>/attribute.repository/<org>/<repo>`).

| Plan entry | Meaning | Applied by |
|---|---|---|
| `add-wif-binding` | the pair is not linked (enforce) | `gcloud iam service-accounts add-iam-policy-binding <sa> --member <principalSet> --role roles/iam.workloadIdentityUser` |
| `drift{would: add-wif-binding}` | the pair is not linked (report) | nothing |
| `in-sync` | every pair of the repo is linked and nothing else is on its SAs | nothing |
| `unregistered-binding` | a binding on a registered SA that the register does not list | nothing: reported (job warning), never removed |

**A repo links only its own deployers.** One writer per service-account policy: this workflow
writes only `<d>-deployer` accounts, and repo R may link only `<d>-deployer` for a `cloud_run: <d>`
in R's own `deploys:`. Anything else makes the planner exit `1` with no plan, in both modes:
`github-releaser` gives `error: <repo>: github-releaser is not a project SA: ask JGD (wif_repos)`,
and another repo's deployer gives `... is not a deployer of a deployable of <repo>`. `repo-admin`
fails by name. Linking `repo-admin` would give every branch and pull-request job of a repo the
identity that creates SAs and sets IAM. The old `protected_service_accounts` input is a deprecated
no-op. The rule is a mistake-guard; the exact audit on the access-provisioning side detects a breach.

The workflow never removes a binding, grants any other role, creates a service account (a missing
SA is an error; use [F6](repos-service-accounts.md)), or touches the pool or provider.

## Modes

The mode is the repo's `mode`, else `defaults.mode`, else `report`. In `report` the Apply step has
nothing to do and the job summary lists every repo examined (with the count). In `enforce` the
`add-wif-binding` actions run in plan order and the first failure stops the job.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `workload_identity_provider` | yes | | WIF provider used to authenticate |
| `service_account` | yes | | the repo-admin SA email |
| `project_id` | yes | | GCP project of the service accounts |
| `pool` | yes | | org-level workload identity pool id used in the principalSet |
| `project_number` | yes | | the GCP project NUMBER (digits) of `project_id`; an input, so the repo-admin SA needs no `projects.get` |
| `protected_service_accounts` | no | empty | DEPRECATED no-op: accepted so existing callers do not break, ignored (the `-deployer` name suffix decides which accounts are managed) |
| `register_path` | no | `repos.yaml` | register file in the caller repo |
| `environment` | no | `repo-admin` | GitHub environment holding the approval gate |

## Caller example

```yaml
jobs:
  wif-link:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-wif-link.yml@vX.Y.Z
    with:
      workload_identity_provider: projects/123/locations/global/workloadIdentityPools/p/providers/github
      service_account: repo-admin@example-proj.iam.gserviceaccount.com
      project_id: example-proj
      pool: example-pool
      project_number: '123456789'
```
