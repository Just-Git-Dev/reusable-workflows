# manage-config-secrets

Manages the **values** of a GKE service's non-sensitive config (a ConfigMap) and
its secrets. It only **writes values into their store** — it does not build,
deploy, roll a workload, or wire anything into pods. Pair it with
`deploy-gke-service` (which builds + rolls) as a separate caller job.

WIF auth; the WIF provider and SA are inputs.

## Scope boundary — what this does NOT do

- **No pod wiring.** Getting a `gsm` secret into a running pod (Secret Manager CSI
  driver + `SecretProviderClass`, or an ESO `ExternalSecret`) is a **separate
  provisioning workflow** — tracked in `TODO.md`. This workflow stops at writing
  the value into GSM.
- **No deploy / rollout.** Use `deploy-gke-service`. If a config/secret change must
  restart pods, have the deploy job stamp a checksum annotation.
- **`eso` backend is reserved, not implemented** — it errors. It marks the
  extension point for the wiring workflow above.

## Config (ConfigMap)

Set `config_file` to a caller-committed **dotenv** file. Two output shapes:

| `configmap_target` | Result | For |
|---|---|---|
| `keyvalue` (default) | one ConfigMap `data` entry per `KEY` | Go / backend services |
| `react-env-js` | a single `environment.js` (`window.env = {…}`) entry | React UIs that read config at runtime |

Applied via `kubectl create configmap … --dry-run=client -o yaml | kubectl apply
-f -` — the canonical, escaping-safe form. (Deliberately **not** zopsmart's
`generate-configmap`, which hand-rolls YAML with `cut`/`echo` and corrupts any
value containing `:` or a quote.)

## Secrets

Pass a **masked JSON payload** built in the caller with `toJSON()` — secrets never
live in the repo:

```yaml
secrets:
  payload_json: |
    {"DB_PASSWORD": ${{ toJSON(secrets.DB_PASSWORD) }},
     "API_KEY":     ${{ toJSON(secrets.API_KEY) }}}
```

| `secrets_backend` | Writes | Notes |
|---|---|---|
| `none` (default) | nothing | secrets skipped |
| `k8s` | one Opaque `Secret` in `namespace` | `kubectl apply` from the payload |
| `gsm` + `gsm_mode: blob` | one Secret Manager secret (`secret_name`), dotenv payload, new version | source-of-truth blob |
| `gsm` + `gsm_mode: individual` | one Secret Manager secret **per key**, named `<secret_name><KEY>` | new version per key |
| `eso` | — | reserved; errors "not implemented" |

`gsm` uses automatic replication unless `gsm_locations` (comma-separated regions)
is set.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `wif_provider` | input (req) | — | WIF provider resource name (not a secret) |
| `service_account` | input (req) | — | SA email to impersonate (not a secret) |
| `gcp_project` | input | `''` | project for `gsm`; empty ⇒ `cluster_project` |
| `checkout_ref` | input | `''` | ref to check out for `config_file`; empty ⇒ caller ref |
| `cluster_project` / `cluster_name` / `cluster_location` / `namespace` | input | `''` | **required** when writing a ConfigMap or a `k8s` Secret |
| `config_file` | input | `''` | dotenv path in the checkout; empty ⇒ no ConfigMap |
| `configmap_name` | input | `''` | required when `config_file` is set |
| `configmap_target` | input | `keyvalue` | `keyvalue` \| `react-env-js` |
| `secrets_backend` | input | `none` | `none` \| `k8s` \| `gsm` \| `eso` |
| `secret_name` | input | `''` | k8s/GSM-blob name, or GSM-individual prefix |
| `gsm_mode` | input | `blob` | `blob` \| `individual` (gsm only) |
| `gsm_locations` | input | `''` | user-managed replication regions; empty ⇒ automatic |
| `dry_run` | input | `false` | validate + print the plan; write nothing |
| `payload_json` | secret | — | required when `secrets_backend` is not `none` |

### Outputs

| Name | Notes |
|---|---|
| `configmap_written` | `true` if a ConfigMap was applied (false on dry run / skipped) |
| `secret_keys` | number of secret keys materialized (0 when skipped) |

## Required IAM on `service_account`

- ConfigMap / `k8s` secret: `roles/container.developer` on the cluster.
- `gsm` backend: `roles/secretmanager.admin` (create secrets + add versions).

## Example — one quizzing-pro service (config + k8s secret)

```yaml
jobs:
  config:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/manage-config-secrets.yml@vX.Y.Z
    with:
      wif_provider: ${{ vars.WIF_PROVIDER }}
      service_account: ${{ vars.DEPLOYER_SA }}
      cluster_project: ${{ vars.CLUSTER_PROJECT }}
      cluster_name: ${{ vars.CLUSTER_NAME }}
      cluster_location: ${{ vars.CLUSTER_LOCATION }}
      namespace: smart-quiz-stage
      config_file: ./configs/.stage.env
      configmap_name: api
      secrets_backend: k8s
      secret_name: api-secrets
    secrets:
      payload_json: |
        {"DB_PASSWORD": ${{ toJSON(secrets.DB_PASSWORD) }}}
```
