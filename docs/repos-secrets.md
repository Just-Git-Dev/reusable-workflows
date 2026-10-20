# repos-secrets

Feature **F8** of [repos as code](repos-register.md): each Cloud Run service the register lists
with `env_secret: true` gets exactly one Secret Manager secret, `<service>-env`, whose **whole IAM
policy has one writer: this workflow** (owner ruling 24, extending the one-writer rule for
service-account policies to secrets). Reusable workflow `repos-secrets.yml`; the decisions live in
`scripts/repos_secrets_plan.py`, the workflow only fetches live state and applies the plan. The
register, the live-state JSON and the action list are defined in
[repos-register.md](repos-register.md) (sections 6, 7 and 8).

## The rule

- **A secret named `<service>-env`, for a `cloud_run: <service>` the register lists, belongs to the
  project.** Only F8 creates it and writes its policy. The name is derived like `<service>-deployer`
  and `<service>-run`, never chosen: a repo that deploys `api` can never name `web-env`.
- **The policy is exactly two principals** (the project writes both lines):

  | Principal | Roles | Why |
  |---|---|---|
  | `<service>-run` (the runtime SA) | `roles/secretmanager.secretAccessor` | the running service reads the secret |
  | `<service>-deployer` (the repo's own deployer) | `roles/secretmanager.secretAccessor`, `roles/secretmanager.secretVersionManager`, `roles/secretmanager.viewer` | the value sync (`sync-bundle-key`) reads the blob, adds a version, disables and destroys old ones, and `describe`s the secret |

  The deployer's three roles are Google's predefined roles, which include `versions.destroy`: the
  syncing identity MAY destroy versions (the sync destroys every disabled version except the newest,
  see [sync-bundle-key](sync-bundle-key.md)). There is no custom no-destroy role.
- **Values are never touched here.** F8 holds no `secretmanager.versions.*` permission: it cannot
  add, read, disable, enable or destroy a version. Values come only from the owning repo's
  workflow ([sync-bundle-key](sync-bundle-key.md)), never by hand.

## What it does, per `deploys:` entry with `env_secret: true`

| State found | Action |
|---|---|
| deployer SA `<service>-deployer` missing | **error**, exit `1`, nothing planned for any repo: run F6 first |
| runtime SA `<service>-run` missing | `needs-jgd` for that service, nothing else planned for it (the access-provisioning side declares `<service>-run`) |
| secret `<service>-env` missing | `create-secret` (empty, no version; replication from the `replication` input; labels `managed-by=repos-secrets` and `deployable=<service>`) |
| secret present | **adopt**: `adopt` is reported, the secret is never recreated and its versions are never read |
| a wanted (role, member) line missing | `add-secret-binding` |
| a (role, member) line that is not wanted | `drift{would: "remove-secret-binding"}`; written as `remove-secret-binding` only in `enforce` AND with `prune: true` |
| everything as wanted | `in-sync` |

`env_secret` must be the boolean `true`; any other value, including a string such as `web-env`, is an
error (the name is derived, never chosen).

## The NEVER list

F8 never, in any mode:

1. deletes a secret;
2. adds, reads (accesses), enables, disables or destroys a secret version;
3. touches a secret that is not `<service>-env` for a `cloud_run: <service>` in the register;
4. binds a role other than the four above to a principal other than the two above;
5. grants a project-level role (every binding is on one secret);
6. removes a binding unless the run is `enforce` AND `prune: true`.

The planner's action vocabulary has no verb for 1 and 2 (`create-secret`, `add-secret-binding` and
`remove-secret-binding` are the only writes). The apply step re-checks the **whole plan** before its
first write: allowed verbs only, every secret name ends in `-env`, every role is one of the four, every
member is a `serviceAccount:` of the form `<service>-run` / `<service>-deployer` in the project, and
`remove-secret-binding` is refused unless `prune` is true. One bad action means nothing is applied.

## Modes

The mode is the repo's `mode`, else `defaults.mode`, else `report`. In `report` the planner emits
only `drift`, `adopt`, `needs-jgd` and `in-sync` and writes nothing, so the report proves the plan
(ruling 4). In `enforce` the writes run in plan order and the first failure stops the job. `prune`
(workflow input, default `false`) follows the fleet's no-prune-by-default convention: without it, extra
members are only reported.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `workload_identity_provider` | yes | | WIF provider used to authenticate |
| `service_account` | yes | | the repo-admin SA email (needs `secretmanager.secrets.create/get/getIamPolicy/setIamPolicy`) |
| `project_id` | yes | | GCP project of the secrets and service accounts |
| `register_path` | no | `repos.yaml` | register file in the caller repo |
| `prune` | no | `false` | remove policy lines F8 would not write (enforce only) |
| `replication` | no | `automatic` | `automatic`, or a region (user-managed replication in that region) for a newly created secret |
| `environment` | no | `repo-admin` | GitHub environment holding the approval gate |

## What it reads

Only resource-level read calls: `gcloud secrets describe` and `get-iam-policy` on each
`<service>-env`, and `gcloud iam service-accounts describe` on `<service>-deployer` and
`<service>-run`. No version is listed or accessed, no project-level IAM is read.

## Adopting a secret that already exists

Existing `<service>-env` secrets are adopted in place: versions untouched, only the policy converges.
Adopt in `report` first and read the plan; run `enforce` without `prune`, switch each syncing
caller to the service's `-deployer` account, prove a real sync, and only then run `enforce` with
`prune: true` so the earlier writers are removed. Nothing ever runs with neither identity bound.

## Caller example

```yaml
jobs:
  secrets:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-secrets.yml@vX.Y.Z
    with:
      workload_identity_provider: projects/123/locations/global/workloadIdentityPools/p/providers/github
      service_account: repo-admin@example-proj.iam.gserviceaccount.com
      project_id: example-proj
```
