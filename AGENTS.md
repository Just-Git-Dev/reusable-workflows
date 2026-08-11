# AGENTS.md — onboarding a repo onto these workflows

For a coding agent (or a human) wiring a repository up to
`Just-Git-Dev/reusable-workflows` for the first time, or upgrading an existing caller.

**Read this file, then [`catalog.json`](catalog.json).** `catalog.json` is generated from
the shipped YAML and verified in CI, so it is the authoritative input contract — every
workflow, every input, its type, default and whether it is required. Prose can drift; that
file cannot. Per-workflow prose lives in `docs/<workflow>.md`, and the *why* behind any
behaviour lives in `DECISIONS.md`.

Do **not** read the workflow YAML to learn a contract. The files run to ~7,500 lines and
`catalog.json` already holds the answer.

## 1. Resolve the version to pin

```bash
gh release view --repo Just-Git-Dev/reusable-workflows --json tagName -q .tagName
```

Pin that **exact tag**. Never `@main` — these workflows mint cloud credentials and delete
artifacts. Never `@v1`: it is a frozen legacy alias, not a moving major.

The version is deliberately absent from `catalog.json` so the file cannot go stale between
releases. Resolve it at read time.

### Then let Dependabot hold it for you

Pinning an exact tag is only half the job — the other half is not being stranded on it.
Dependabot has updated **reusable workflow** refs since March 2023, not just actions, so six
lines keep your pins current without anyone remembering:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"          # finds .github/workflows/*
    schedule:
      interval: "weekly"
```

**Add this when you onboard.** This repository is public and most callers are private, so
there is no mechanism by which we can notice that *you* are behind and tell you — the only
party who can watch your pins is you. A 2026-07-27 audit of the repos we could see found 18
of 27 caller lines six or more releases stale, every one of them a repo whose owner had not
noticed. Dependabot turns that into a PR you can merge or ignore.

## 2. Pick the workflow

| You want to… | Use |
|---|---|
| Lint · test · build a Node/React repo | `ci-node` |
| Same for Go | `ci-go` |
| Deploy a static site / SPA | `deploy-cloudflare-pages` |
| Build + roll a Cloud Run service | `deploy-cloud-run` |
| Build + roll a GKE workload | `deploy-gke-service` |
| Deploy to EKS/AKS/any registry | `deploy-cluster-keyed` |
| Promote a built image to prod (no rebuild) | `promote-image` |
| Roll back to a prior image | `rollback-service` |
| Run a migration / one-shot job | `run-db-job` |
| Manage config values + secrets | `manage-config-secrets` |
| Rotate a key, secret or token | `rotate-*`, `sync-bundle-key` |
| Back up Postgres | `neon-backup` |
| Sweep old images / revisions | `cleanup-gar-images`, `cleanup-cloud-run-revisions` |
| Apply alerts / dashboards | `bootstrap-alerts`, `bootstrap-dashboards` |

One reusable per **target type**. Two different targets ⇒ two jobs, not one workflow with a
`target:` switch.

## 3. Shape of a caller

**One workflow file per repo, one job per environment**, joined with `needs:`. Environments
differ by *trigger*, not parameters, so splitting the file duplicates the CI block and lets
the two drift. A full copy-paste example is in
[`docs/deploy-cloudflare-pages.md`](docs/deploy-cloudflare-pages.md#copy-paste-one-workflow-for-ci--stage--prod)
— it is extracted and linted by this repo's CI, so it works verbatim.

Use a matrix only when the *same* target is deployed several times under **one** trigger.

## 4. Traps that cost real debugging time

These are not style preferences. Each one has cost someone a broken pipeline.

**Caller permissions cap the called workflow, and the failure is silent.** If any job in a
called workflow declares more than the caller granted, GitHub aborts the whole run at
startup with `startup_failure` and **no logs** — before any job-level `if:` is evaluated. It
is not enough for the job to be skipped. Grant what the workflow's jobs declare
(`jobs.*.declared_permissions` in `catalog.json`); `inherits-caller` means the job takes
whatever you give it.

**`environment:` is not allowed on a job that calls a reusable workflow.** Permitted keys
are `name`, `uses`, `with`, `secrets`, `needs`, `if`, `permissions`, `strategy`,
`concurrency`. GitHub environment-scoped variables therefore cannot feed a reusable caller
directly — marshal them through a preceding job, or commit per-environment config and
select it in `build_command`.

**Tokens go in `secrets:`, never `with:`.** `workflow_call` inputs are **not masked** in
logs. Registry URLs and scopes are fine as inputs; the token is not.

**`build_command` is the extension seam.** Env sourcing, output assembly, extra gates — put
them in a script in your repo and call it. Do not ask for a new input for something a shell
command already does.

**Static hosts have no runtime config.** Cloudflare dashboard variables reach Pages
*Functions* via `context.env`, never a browser bundle, and build variables only apply when
Cloudflare runs the build. If CI builds and uploads, bake config at build time.

## 5. Before you upgrade an existing caller

Repinning is not automatically safe. Additive input changes are; **default changes and
behaviour changes are not.**

```bash
# What actually changed in the contract you depend on:
git diff <current-pin>..<new-tag> -- .github/workflows/<workflow>.yml
```

Then read the release notes for every version in between — behaviour changes are called out
at the top.

**For a destructive workflow (`cleanup-*`, `retire-*`), dry-run both pins and diff the
plans.** Do not trust a documented invariant. On 2026-08-11 this repo's own docs claimed the
GAR retention change was "keep-only, so it can only ever delete less"; a dry-run comparison
on a real repo showed the new version planned *more* deletions (103 → 105). The claim was
reasoning about intent, never a measurement. See `DECISIONS.md`.

## 6. What a new repo needs before its first green run

- `vars.CLOUDFLARE_ACCOUNT_ID` (Pages) or a WIF provider + service account (GCP)
- `secrets.CLOUDFLARE_API_TOKEN` with **Pages: Edit**, or the relevant cloud secret
- `permissions: id-token: write` on any job authenticating to GCP via WIF
- `permissions: contents: write` on the CI job if you want README badges (on by default;
  without it they are generated and the push degrades to a warning)
- A private-registry token as `npm_auth_token` if you consume scoped packages

## 7. Keeping this file honest

`catalog.json` is generated: run `python3 scripts/gen_catalog.py` after changing any
`workflow_call` contract. CI fails if it is stale. This file is hand-written — if you learn
something here the hard way, add it to §4 rather than to a commit message.
