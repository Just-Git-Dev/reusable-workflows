# Just-Git-Dev / reusable-workflows

Shared **`workflow_call`** GitHub Actions workflows for the AutoMahn, Realm-ID,
and Traide-Co orgs. These orgs run the same infra stack (**GCP Cloud Run + Neon
Postgres + Upstash Redis + Cloudflare Pages/Workers/R2**, WIF auth, an
`app-secrets` Secret Manager bundle mounted into Cloud Run), so the ops
workflows were duplicated near-verbatim across all three. This repo is the
single source of truth for them.

## ⚠️ Why this repo is public

The three consumer orgs are on GitHub **Free** with **no shared enterprise**.
GitHub only allows a repo to call a reusable workflow from a **private** repo in
the **same org / enterprise**. To share across orgs, the host repo **must be
public**.

- **No secrets live here.** Callers pass every secret at call time; nothing
  sensitive is committed.
- What *is* public is infra topology (service names, GAR repo, SM mount paths,
  regions). That was the accepted trade-off — see `DECISIONS.md`.
- Consumers **cannot use `secrets: inherit`** across orgs — every secret must be
  passed explicitly (see each doc's example).

## Pin to a tag, never `@main`

Callers reference workflows by **release tag**, so a change here can't silently
alter every org's ops. Bump the tag deliberately.

```yaml
uses: Just-Git-Dev/reusable-workflows/.github/workflows/<name>.yml@v1
```

## Workflows

| Workflow | Purpose | Docs |
|---|---|---|
| `bootstrap-alerts.yml` | Apply GCP Monitoring channel + alert policies from the caller's `infra/alerts/` | [docs](docs/bootstrap-alerts.md) |
| `sync-bundle-key.yml` | Upsert key(s) into the `app-secrets` SM bundle → roll Cloud Run → disable old version | [docs](docs/sync-bundle-key.md) |
| `neon-backup.yml` | pg_dump prod Neon → private artifact (custom or plain-gz) | [docs](docs/neon-backup.md) |
| `cleanup-gar-images.yml` | Age-sweep GAR images with live Service+Job digest protection | [docs](docs/cleanup-gar-images.md) |
| `rotate-cloudflare-token.yml` | Verify the CF API token is active + print a rotation runbook | [docs](docs/rotate-cloudflare-token.md) |

## Convention

- WIF provider + service account are passed as **inputs** (resource identifiers,
  not credentials) — this deliberately erases the per-org SA var-name drift
  (`GCP_ROTATOR_SA` / `GCP_INFRA_SA` / `GCP_RELEASER_SA` / `GCP_CLEANER_SA`).
- Each caller keeps its own trigger (`schedule` / `workflow_dispatch`) and its
  own `infra/` files; the reusable workflow checks out the **caller** repo.
