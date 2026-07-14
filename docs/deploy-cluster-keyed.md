# deploy-cluster-keyed

**Key-based, multi-cloud, multi-registry** build → push → roll for Kubernetes
workloads that cannot use keyless WIF. This is the parity path for the parts of
`zopsmart/workflows` the WIF-native deploy workflows deliberately don't cover:
**EKS / AKS / raw-kubeconfig** clusters and **ECR / ACR / GHCR / DockerHub**
registries.

> **Prefer the keyless workflows whenever you can.** This one takes long-lived
> credentials as secrets by design:
>
> | Target | Use |
> |---|---|
> | GCP + GAR + Cloud Run | [`deploy-cloud-run`](deploy-cloud-run.md) |
> | GCP + GAR + GKE | [`deploy-gke-service`](deploy-gke-service.md) |
> | Non-GCP cloud, or a registry/cluster without federation | **this workflow** |
>
> Reach for `deploy-cluster-keyed` only when a stored key is unavoidable, and
> rotate the credentials.

## How it authenticates

- **Registry** (`registry_type`): `gar` \| `gcr` \| `ecr` \| `acr` \| `ghcr` \|
  `dockerhub` \| `custom`. Login is CLI-based (`gcloud`/`aws`/`az`/`docker`, all
  preinstalled on the runner). `ghcr` uses the workflow token — no secret needed.
- **Cluster** (`cluster_type`, empty ⇒ auto-detected from the credential format):
  `gke` \| `eks` \| `aks` \| `kubeconfig`. GKE uses the SHA-pinned Google auth
  actions (they install the `gke-gcloud-auth-plugin`); the rest are CLI.

**Order:** the image is built and pushed **before** cluster auth runs, so the
registry credential and the cluster credential — which may point at different
clouds — never overwrite one another.

## Credential formats (secrets)

| `registry_credentials` / `cluster_credentials` | Format |
|---|---|
| GCP (`gar`/`gcr`/`gke`) | service-account key **JSON** |
| AWS (`ecr`/`eks`) | JSON `{aws_access_key_id, aws_secret_access_key, aws_region?}` |
| Azure (`acr`/`aks`) | JSON `{clientId, clientSecret, tenantId}` |
| DockerHub / custom | JSON `{username, password}` or `"username:password"` |
| kubeconfig | base64-encoded kubeconfig |
| ghcr | — (uses the workflow token; leave `registry_credentials` unset) |

## Inputs (abridged)

| Group | Inputs |
|---|---|
| registry | `registry_type` (req), `image_registry`, `registry_project`, `registry_repo`, `registry_region`, `image_name` (⇒ `svc_name`), `image_tag` (⇒ SHA) |
| cluster | `cluster_type` (auto), `cluster_name`, `cluster_region`, `cluster_project`, `azure_resource_group` |
| deploy | `namespace` (req), `svc_name` (req), `workload_type` (`deployment`\|`cron`), `deploy_method` (`kubectl`\|`helm`), `helm_*`, `app_version` |
| build | `context`, `dockerfile`, `platforms`, `build_args`, `dry_run` |

## Example — ECR + EKS (kubectl)

```yaml
name: Deploy api (EKS)
on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cluster-keyed.yml@v1.4.0
    with:
      registry_type: ecr
      image_registry: 1234567890.dkr.ecr.us-east-1.amazonaws.com
      image_name: api
      cluster_type: eks
      cluster_name: prod
      cluster_region: us-east-1
      namespace: default
      svc_name: api
    secrets:
      registry_credentials: ${{ secrets.AWS_ECR_JSON }}
      cluster_credentials:  ${{ secrets.AWS_EKS_JSON }}
```

## Example — GHCR + kubeconfig (helm), token-auth registry

```yaml
    with:
      registry_type: ghcr
      registry_project: my-org
      image_name: worker
      cluster_type: kubeconfig
      namespace: apps
      svc_name: worker
      deploy_method: helm
      helm_chart: ./charts/worker
    secrets:
      cluster_credentials: ${{ secrets.KUBECONFIG_B64 }}
      # registry_credentials unset — ghcr uses the workflow token
```

## Example — the zopsmart-style GAR + GKE deploy, key-based

If a caller is still on an SA-JSON key (not yet migrated to WIF), this reproduces
the old `zopsmart/workflows` GAR+GKE deploy 1:1 as an interim step:

```yaml
    with:
      registry_type: gar
      image_registry: us-central1-docker.pkg.dev
      registry_project: zopsmart-products
      registry_repo: training-upskilling
      image_name: training-ui
      cluster_type: gke
      cluster_project: zopsmart-products
      cluster_name: internal-products
      cluster_region: us-central1
      namespace: training
      svc_name: training-ui
    secrets:
      registry_credentials: ${{ secrets.PROD_DEPLOY_KEY }}
      cluster_credentials:  ${{ secrets.PROD_DEPLOY_KEY }}
```

Then migrate to `deploy-gke-service` (keyless WIF) when the deployer SA is
federated — that is the destination, this is the bridge.

## Dry run

`dry_run: true` builds the image (validating the Dockerfile) but does not push,
skips registry login, and passes `--dry-run` to kubectl/helm.

## Concurrency

Keyed on `<cluster>-<namespace>-<svc>` with `cancel-in-progress: false`.
