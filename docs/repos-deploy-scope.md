# repos-deploy-scope

Feature **F7** of [repos as code](repos-register.md): each repo can deploy only its own Cloud Run
service (or GKE workload), and no other service in the project. Reusable workflow
`repos-deploy-scope.yml`; the decisions live in `scripts/repos_deploy_plan.py`, the workflow only
fetches live state and applies the plan. The register, the live-state JSON and the action list are
defined in [repos-register.md](repos-register.md) (sections 6, 7 and 8).

## What it does, per `deploys:` entry

| Entry | Action |
|---|---|
| `cloud_run`, service missing | `gcloud run deploy <service> --image=<placeholder_image> --service-account=<runtime SA> --region <region> --no-allow-unauthenticated`, once |
| `cloud_run` | `roles/run.developer` ON that service for `<service>-deployer` (`gcloud run services add-iam-policy-binding`) |
| `cloud_run` with `image_repository` | `roles/artifactregistry.writer` ON that repository (`gcloud artifacts repositories add-iam-policy-binding`) |

**No service-account policy is written here** (one writer per service-account policy). The runtime
SA is derived as `<service>-run` (`runtime_service_account` is optional; when present it must equal
it, else the run is refused) and belongs to the access-provisioning side. The workflow only reads
its policy and reports a `needs-jgd` warning for each line that side must still declare:
`deployed_by: <service>-deployer` (the deployer's `roles/iam.serviceAccountUser` on it) and, while
the service is still to be created, `act_as: repo-admin`. The apply step's allow-list has no
`iam.serviceAccount` write, so a plan that carried one is refused before anything runs.

Order per deployable: the service, then the other bindings, then the `needs-jgd` reports. The
workflow never grants a project-level role, never deletes anything and never creates a
service-account key.

## Modes

The mode is the repo's `mode`, else `defaults.mode`, else `report`. In `report` the planner emits
only `drift`, `unsupported` and `in-sync`, so the Apply step has nothing to do and the job summary
lists every repo examined (with the count). In `enforce` the write actions run in plan order and
the first failure stops the job.

## Inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `workload_identity_provider` | yes | | WIF provider used to authenticate |
| `service_account` | yes | | the repo-admin SA email |
| `project_id` | yes | | GCP project of the services, runtime SAs and GAR repositories |
| `register_path` | no | `repos.yaml` | register file in the caller repo |
| `placeholder_image` | no | `us-docker.pkg.dev/cloudrun/container/hello` | image of the first, placeholder revision |
| `environment` | no | `repo-admin` | GitHub environment holding the approval gate |

## GKE is deferred

No project uses GKE, and creating in-cluster roles needs Kubernetes rights nothing here holds, so
this workflow never runs `kubectl`. A `deploys` entry with `gke` is reported as
`unsupported` (key `gke`) in the plan and a job warning, in both modes, and nothing is applied for
it. It is built, with its own tests, the day a project moves to GKE.

## What it reads

Only these read calls, all resource-level: `gcloud run services describe` and `get-iam-policy`
(the region is the register's `region`, never a lookup, so no `run.services.list` is needed),
`gcloud iam service-accounts get-iam-policy` on each runtime SA, and
`gcloud artifacts repositories get-iam-policy`. No project-level IAM is read, so there is no
`legacy-grant` report: it could only ever list the new per-service deployers, which hold no project
roles.

## Validation before planning

The planner validates the register against `schemas/repos.v1.json` (the same check as F1) before it
plans: a service name, region, repository or SA name of the wrong shape, or any such value
starting with `-` (for example `--ingress=all`), is an error and nothing is planned or applied. The
Apply step then re-checks the whole plan again before its first write (allowed verbs, the three
role/resource pairs, a `serviceAccount:` member, name and region shapes).

## Caller example

```yaml
jobs:
  deploy-scope:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-deploy-scope.yml@vX.Y.Z
    with:
      workload_identity_provider: projects/123/locations/global/workloadIdentityPools/p/providers/github
      service_account: repo-admin@example-proj.iam.gserviceaccount.com
      project_id: example-proj
```
