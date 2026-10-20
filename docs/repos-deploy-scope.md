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
| `cloud_run` | `roles/iam.serviceAccountUser` ON that service's runtime SA only (`gcloud iam service-accounts add-iam-policy-binding`) |
| `cloud_run` with `image_repository` | `roles/artifactregistry.writer` ON that repository (`gcloud artifacts repositories add-iam-policy-binding`) |
| `gke` | `kubectl apply` of a `Role` limited by `resourceNames: [<workload>]` plus a `RoleBinding` (credentials via `gcloud container clusters get-credentials`) |
| any | a project-level `roles/run.*` or `roles/container.*` role the deployer still holds is reported as `legacy-grant` and never removed |

Order per repo: create the service before any binding. The workflow never grants a project-level
role, never deletes anything and never creates a service-account key.

## Modes

The mode is the repo's `mode`, else `defaults.mode`, else `report`. In `report` the planner emits
only `drift`, `legacy-grant` and `in-sync`, so the Apply step has nothing to do and the job summary
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

## GKE cluster viewer is a project-level grant, made elsewhere

`roles/container.clusterViewer` exists only at project level (GKE has no cluster-resource IAM
policy), so this workflow never grants it. Make the deployer SA's project-level grant in the
access-provisioning config, like every other project-level grant. A GKE deployer that does not
hold it at project level gets an `unsupported` entry (key `gke.cluster_viewer`) in the plan and a
warning, in both modes; it is never applied. A project-level `clusterViewer` is not reported as a
`legacy-grant`. Live state for in-cluster RBAC is not read, so GKE entries always plan
`apply-k8s-rbac`.

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
