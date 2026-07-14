# TODO — reusable-workflows

- [ ] `.github/workflows/` — **Create a GSM→k8s wiring/provisioning workflow.**
  `manage-config-secrets.yml` only *manages the values* (writes the ConfigMap and
  writes secrets into the chosen store: k8s Secret / GSM blob / GSM individual).
  It deliberately does **not** wire a GSM secret into pods. A separate reusable
  should provision that delivery path — e.g. install/configure the Secret Manager
  CSI driver + `SecretProviderClass`, or (later) an External Secrets Operator
  `ExternalSecret`/`SecretStore` — so a GSM-backed secret actually reaches the
  workload. `manage-config-secrets.yml` reserves the `eso` backend value as the
  extension point; the wiring workflow is its counterpart.
- [ ] `.github/workflows/manage-config-secrets.yml` — implement the reserved `eso`
  backend (currently errors "not implemented"): emit an `ExternalSecret` CR
  referencing the GSM secret written by the `gsm` backend.
