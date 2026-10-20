# repos-service-accounts

Feature **F6** of [repos as code](repos-register.md): the project's own service accounts. Reusable
workflow `repos-service-accounts.yml`; the decisions live in `scripts/repos_sa_plan.py`, the
workflow only fetches live state and applies the plan. The register, the live-state JSON and the
action list are defined in [repos-register.md](repos-register.md) (sections 6, 7 and 8).

## What it does, per entry of `service_accounts:`

| Situation | Enforce | Report |
|---|---|---|
| SA missing | `gcloud iam service-accounts create <name> --display-name ... --description ...` | `drift{would: create-service-account}` |
| SA exists, description or display name differs | `gcloud iam service-accounts update <email> --description ...` or `--display-name ...` | `drift{would: update-service-account}` |
| SA exists and matches | `in-sync` | `in-sync` |
| SA exists live but is not in the register | no action | no action |

Name rule: 6-30 chars, `^[a-z][a-z0-9-]*$`, no trailing hyphen. `description` is required (what it
is for, who owns it, when and why it was made). `display_name` defaults to the name on create and
is compared only when the register states it. An invalid entry refuses the whole run.

A register entry that names a protected service account (`repo-admin` always, plus the
`protected_service_accounts` input) is an error: the run is refused with no plan. The
access-provisioning config owns those accounts and their descriptions.

The workflow never deletes a service account, never creates a key and never grants any role.

## Modes

Per entry: the entry's `mode`, else `defaults.mode`, else `report`. In `report` the job summary
lists the count of service accounts examined and every plan entry; nothing changes. In `enforce`
the write actions run in plan order and the first failure stops the job.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `workload_identity_provider` | yes | | WIF provider used to authenticate |
| `service_account` | yes | | the repo-admin SA email |
| `project_id` | yes | | GCP project the service accounts live in |
| `protected_service_accounts` | no | empty | comma or newline list of SA names F6 must never manage; merged with the always-protected `repo-admin` |
| `register_path` | no | `repos.yaml` | register file in the caller repo |
| `environment` | no | `repo-admin` | GitHub environment holding the approval gate |

## Caller example

```yaml
jobs:
  service-accounts:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-service-accounts.yml@vX.Y.Z
    with:
      workload_identity_provider: projects/123/locations/global/workloadIdentityPools/p/providers/github
      service_account: repo-admin@example-proj.iam.gserviceaccount.com
      project_id: example-proj
```
