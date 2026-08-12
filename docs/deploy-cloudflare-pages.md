# deploy-cloudflare-pages

Builds a static site and deploys it to a Cloudflare Pages project via
[`cloudflare/wrangler-action`](https://github.com/cloudflare/wrangler-action).
Everything project-specific is an input: Pages project name, account id, build
command, output directory, Node version.

Pushes authored by `dependabot[bot]` or `renovate*` are skipped — bot actors
cannot hold deploy credentials, so those runs would only fail noisily.

## Inputs / secrets

| Name | Kind | Default | Notes |
|---|---|---|---|
| `project_name` | input (req) | — | Cloudflare Pages project |
| `account_id` | input (req) | — | Cloudflare account id — not a credential, pass a repo/org variable |
| `working_directory` | input | `.` | build and deploy from here |
| `build_command` | input | `npm ci && npm run build` | run in `working_directory` |
| `install_command` | input | `''` | optional install run *before* `build_command`. Empty ⇒ today's behaviour (`build_command` installs too). Required by `cache_node_modules` |
| `output_dir` | input | `dist` | static assets, relative to `working_directory` |
| `node_version` | input | `24` | any setup-node spec: `24`, `22`, `lts/*`. Defaults to the **active LTS**; Node 20 is EOL (2026-04-30) |
| `node_cache` | input | `npm` | `npm`/`yarn`/`pnpm`; empty string disables caching |
| `cache_dependency_path` | input | `<working_directory>/package-lock.json` | lockfile the cache keys on |
| `cache_node_modules` | input | `false` | cache the installed tree and skip `install_command` on an exact hit — see [Caching node_modules](#caching-node_modules) |
| `npm_registry_url` | input | `''` | private npm registry the build authenticates against. Empty ⇒ untouched — see [Private registries](#private-registries) |
| `npm_registry_scope` | input | `''` | package scope routed there, e.g. `@acme`. Optional for GitHub Packages |
| `npm_auth_token` | **secret** | — | optional; token for `npm_registry_url`, exposed to the build step as `NODE_AUTH_TOKEN` |
| `branch` | input | `main` | Pages deployment branch |
| `ref` | input | `''` | git ref to check out and deploy; empty ⇒ the triggering ref. Set it to re-deploy a specific tag from a `workflow_dispatch` run |
| `build_env` | input | `''` | extra build environment, newline-separated `KEY=VALUE` (values may contain spaces); scoped to the build step only |
| `smoke_path` | input | `''` | path to fetch after deploying; empty skips the check — see [Smoke check](#smoke-check) |
| `smoke_url_base` | input | `''` | origin for the check; empty ⇒ **this run's deployment URL** |
| `smoke_expect` | input | `''` | newline-separated substrings that must all appear in the body |
| `smoke_status` | input | `200` | status the request must return |
| `smoke_attempts` / `smoke_interval_seconds` | input | `8` / `5` | bounded retry for propagation |
| `cloudflare_api_token` | **secret** (req) | — | needs `Cloudflare Pages: Edit` |

## Outputs

`deployment_url` — the URL of the deployment this run produced.

## Caching node_modules

`node_cache` is `setup-node`'s cache of the **npm download cache** (`~/.npm`); npm
still unpacks and links the whole tree on every run, which for a large app is most
of the build time.

Caching the tree itself takes two inputs, because the default `build_command`
installs *and* builds — and `npm ci` **deletes `node_modules` before installing**, so
a restored tree would be thrown away. Split the install out first:

```yaml
    with:
      install_command: npm ci
      build_command: npm run build      # no longer installs
      cache_node_modules: true
```

Setting `cache_node_modules` without `install_command` **fails the run immediately**
rather than deploying a build that silently never used the cache.

On an exact lockfile hit the install is skipped entirely, which is the point and also
the risk — the same trade-offs as [`ci-node`](ci-node.md#caching-node_modules):
lifecycle scripts (`postinstall`, `prisma generate`, `husky`) do not run; the key is
exact-match only (no `restore-keys`) and includes the Node version `setup-node`
resolved; only the top-level `node_modules` under `working_directory` is cached. A
skipped install prints a `::notice::`.

## Private registries

If the build installs a scoped package from a private registry, point
`npm_registry_url` at it and pass the token as the `npm_auth_token` **secret** —
inputs are not masked in logs. `actions/setup-node` writes
`$RUNNER_TEMP/.npmrc` with `//<registry>/:_authToken=${NODE_AUTH_TOKEN}` and
`@scope:registry=<url>`; the token is exposed to the **build** step, since the
default `build_command` is what installs — and to the **install** step as well, for
callers who split the install out via `install_command`.

```yaml
    with:
      npm_registry_url: https://npm.pkg.github.com
      npm_registry_scope: '@acme'
      build_command: npm ci --legacy-peer-deps && npm run build
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      npm_auth_token: ${{ secrets.PACKAGES_READ_PAT }}
```

For GitHub Packages the token needs `read:packages`, and must be a PAT when the
package lives in another repo — `GITHUB_TOKEN` only reaches packages owned by, or
shared with, the caller repo. Only one registry is supported, and a repo-committed
`.npmrc` still outranks setup-node's user-level file. Leaving `npm_registry_url`
empty is a true no-op. Same contract as [`ci-node`](ci-node.md#private-registries).

## The API token

`cloudflare_api_token` must be a token with the **Cloudflare Pages: Edit**
permission, minted in the Cloudflare dashboard by a human. See
[rotate-cloudflare-token](rotate-cloudflare-token.md) for the rotation runbook
and an expiry nag you can schedule.

## Copy-paste: one workflow for CI + stage + prod

The complete pipeline in a single file — gates run on every pull request, and a
deploy cannot start unless they pass, because `needs:` is a real job dependency
rather than a `&&` inside a build command. Change the four `CHANGE ME` values and
it works as-is.

```yaml
name: CI/CD

on:
  pull_request:
  push:
    branches: [main]          # CHANGE ME — your integration branch
    tags: ['v*.*.*']

permissions:
  contents: read

jobs:
  # Runs on every PR, every push and every tag. Nothing deploys without it.
  ci:
    # README badges are on by default, and the badge commit needs write. Drop
    # this block and nothing breaks — the push degrades to a warning — or set
    # `update_badges: false` to turn badges off. Scoped to this job, so the
    # deploy jobs stay read-only.
    permissions:
      contents: write
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-node.yml@v2.1.0
    with:
      node_version: '24'
      # Chain extra gates with && — each is a plain shell command.
      lint_command: npm run lint && npm run prettier:check
      test_command: npm test
      # Optional: fail under a line-coverage floor (needs an Istanbul
      # json-summary reporter). 0, the default, means measure but never gate.
      coverage_threshold: 0

  stage:
    needs: ci
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'   # CHANGE ME
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-pages.yml@v2.1.0
    with:
      project_name: myapp-stage                       # CHANGE ME
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      build_command: npm ci && npm run build
      output_dir: dist
      node_version: '24'
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}

  prod:
    needs: ci
    if: startsWith(github.ref, 'refs/tags/v')
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-pages.yml@v2.1.0
    with:
      project_name: myapp-prod                        # CHANGE ME
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      build_command: npm ci && npm run build
      output_dir: dist
      node_version: '24'
      # Deploy the tag itself, not whatever the default branch points at.
      ref: ${{ github.ref_name }}
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

**Why one workflow and not one per environment.** The environments differ by
*trigger*, not by parameters, so splitting the file means duplicating the `ci`
block and letting the two drift. One file also means the whole pipeline reads
top to bottom.

**Why not a matrix over environments.** `strategy` *is* allowed on a job that
calls a reusable workflow, but each matrix entry would still need its own `if:`
for its trigger — more machinery, less clarity. Reach for a matrix when the same
target is deployed several times under **one** trigger (say three Pages projects
for three brands).

**Note the deploy jobs build again.** `needs:` does not share an artifact between
jobs. For a static bundle from a pinned lockfile that rebuild is deterministic;
see the rejected build-once entry in `TODO.md` for why we do not plumb artifacts
between them.

Private registry, coverage gating and README badges are all opt-in on top of
this — see [ci-node](ci-node.md) and [Private registries](#private-registries).

## Example caller

Deploy only, when CI already lives elsewhere:

```yaml
name: Deploy website
on:
  push:
    tags: ['v*.*.*']
  workflow_dispatch: {}

permissions:
  contents: read

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-pages.yml@v2.1.0
    with:
      project_name: my-website
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      build_command: npm ci && npm run build
      output_dir: dist
      node_version: '24'
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

A monorepo subdirectory:

```yaml
    with:
      project_name: my-docs
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      working_directory: apps/docs
      output_dir: build
```

Re-deploy a specific tag from a manual run, with build-time variables:

```yaml
on:
  workflow_dispatch:
    inputs:
      tag: { description: 'Tag to (re)deploy', required: true }

jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-pages.yml@v2.1.0
    with:
      project_name: my-app
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      ref: ${{ github.event.inputs.tag }}   # check out & deploy that tag, not the default branch
      build_command: npm ci && npm run build
      build_env: |
        VITE_API_BASE=${{ vars.API_BASE }}
        VITE_FIREBASE_PROJECT=${{ vars.FIREBASE_PROJECT }}
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

`build_env` keeps caller build vars out of `build_command` — they're exported
into the build step's shell only, never `$GITHUB_ENV`, so nothing leaks to later
steps.

## Multiple environments (stage + prod)

A Pages **project** has exactly two environments: **production** (its configured
production branch) and **preview** (every other branch). This workflow passes
`branch` straight through to `wrangler pages deploy --branch=…`, which is what
selects between them. There are two ways to run stage and prod, and the choice is
decided by **where your DNS lives**, not by preference.

### Option A — one project per environment (works with any DNS)

Two Pages projects, each deploying to its own production branch. Two caller jobs
differing in the project and whatever selects the environment's config:

```yaml
# .github/workflows/deploy-pages-stage.yaml   → push to `development`
jobs:
  deploy:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/deploy-cloudflare-pages.yml@v2.1.0
    with:
      project_name: myapp-stage
      account_id: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
      build_command: bash scripts/pages-build.sh configs/.stage.env
      output_dir: out
      branch: main            # production deployment OF THE STAGE PROJECT
    secrets:
      cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}

# .github/workflows/deploy-pages-prod.yaml    → push of a `v*.*.*` tag
      project_name: myapp-prod
      build_command: bash scripts/pages-build.sh configs/.prod.env
      branch: main
```

Each project gets its own custom domain, its own deployment history and rollback,
and its own settings. A subdomain custom domain needs only a CNAME at your
existing DNS provider — the zone does **not** have to be on Cloudflare.

### Option B — one project, branch aliases (needs the zone on Cloudflare)

One project; prod deploys with `branch: main` and stage with `branch: development`.
The stage deploy becomes a **preview** deployment with a stable alias at
`development.<project>.pages.dev` that always tracks the latest commit.

```yaml
      project_name: myapp
      branch: ${{ github.ref_name == 'main' && 'main' || 'development' }}
```

To put a real hostname on the stage branch you add the custom domain to the
project and then repoint its CNAME from `<project>.pages.dev` to
`development.<project>.pages.dev`. **Cloudflare only honours this for a proxied
Cloudflare DNS record** — with external DNS or an unproxied record the hostname
serves production instead, silently. So Option B requires the zone to be on
Cloudflare.

Concurrency already keys on `<project_name>-<branch>`, so a stage deploy and a
prod deploy never cancel each other under either option.

### Choosing

| | Option A (two projects) | Option B (one project) |
|---|---|---|
| Zone must be on Cloudflare | no | **yes**, for a stage hostname |
| Per-PR preview deploys | no | yes, free |
| Isolation of prod settings/history | full | shared project |
| Custom domain per environment | independent | via branch alias |

Pick A unless the zone is already on Cloudflare; consolidating to B later costs
one DNS change and one input.

### Per-environment configuration

Cloudflare's dashboard variables are **not** an option for a static bundle: build
variables only apply when Cloudflare runs the build (Git integration), and runtime
variables/bindings are readable only by Pages Functions via `context.env`, never by
a browser bundle. When this workflow builds in Actions and uploads the result,
neither reaches your JavaScript.

So per-environment config is a **build-time** concern. Either pass it with
`build_env`, or — if the values are committed per environment — source the right
file inside `build_command`:

```yaml
      build_command: >-
        set -a && . ./configs/.prod.env && set +a && npm ci && npm run build
```

Note you **cannot** put `environment: prod` on a job that calls a reusable
workflow (GitHub allows only `name`, `uses`, `with`, `secrets`, `needs`, `if`,
`permissions`), so GitHub environment-scoped variables cannot feed this workflow
directly — they would need a marshalling job that outputs them.


## Smoke check

A green deploy proves the upload succeeded. It does not prove the site works.

`Realm-ID/ui` added a post-deploy check by hand after the **2026-06-29 outage**, where a
stale bundle went live in production with a broken client-routed path and nothing caught
it. This generalises that guard.

```yaml
    with:
      smoke_path: /device
      smoke_expect: |
        id="root"
        <title>RealmID</title>
```

Opt-in — with `smoke_path` empty nothing runs. When set it is **blocking**: a check that
reported without failing would not have caught that outage either.

**It retries.** Cloudflare Pages deploys are eventually consistent, so a single request
would false-fail on slow propagation. The default is 8 attempts, 5s apart, stopping the
moment the response is healthy.

**Pick stable markers.** A root element id or the `<title>` survives a rebuild; a hashed
asset filename like `/assets/index-a1b2c3.js` changes every build and makes the check
brittle. Markers are matched literally, and **all** must be present.

**Which URL it tests.** By default, the deployment URL produced by *this run* — so it tests
the bundle just uploaded. Set `smoke_url_base` to a custom domain only for
production-branch deploys: a preview deploy does not update the custom domain, so checking
it would test the *previous* release and pass no matter what you shipped.

## Concurrency

Keyed on `<project_name>-<branch>` with `cancel-in-progress: true` — a newer
deploy of the same branch supersedes an in-flight one rather than racing it.
