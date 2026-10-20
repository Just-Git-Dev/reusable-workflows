# repos-register — repos as code

A project lists every GitHub repository it owns in one file, `repos.yaml`, kept in its root
repo (`<org>/project` below). A family of small reusable workflows acts on that register:
validate it, create missing repos, report or enforce repo settings and variables, create the
project's own GCP service accounts, link a repo to a GCP deploy identity (repo-level WIF), and
scope each deploy identity to the one service it deploys.

This page is the **contract** for the register format, for each feature, and for the planner
output every feature shares. It is written before the workflows exist (design of record,
2026-10-20); each feature's own `docs/<workflow>.md` page lands with its workflow and links back
here. Nothing on this page is implemented until that page exists.

## Contents

1. [The design in five lines](#1-the-design-in-five-lines)
2. [The register — `repos.yaml`](#2-the-register--reposyaml)
3. [Schema `schemas/repos.v1.json`, in words](#3-schema-schemasreposv1json-in-words)
4. [Report vs enforce](#4-report-vs-enforce)
5. [The NEVER list](#5-the-never-list)
6. [Features F1-F7 (adopt any one alone)](#6-features-f1-f7-adopt-any-one-alone)
7. [Planner / workflow split](#7-planner--workflow-split)
8. [The planner action list — the contract](#8-the-planner-action-list--the-contract)
9. [The `repo-admin` environment](#9-the-repo-admin-environment)
10. [Minimal caller](#10-minimal-caller)
11. [Branch protection — not supported yet](#11-branch-protection--not-supported-yet)

## 1. The design in five lines

- **One register per project**, in the project's own root repo — never in a central repo.
- **One reusable workflow per feature.** A project calls only the ones it adopted, in any order.
- **Each feature reads only its own keys** and ignores every other key, so no feature requires
  another, and a later feature adds a key without touching the rest.
- **Report first.** A repo starts in `mode: report` (differences listed, nothing changed) until
  the register switches it to `enforce`.
- **The NEVER list ([§5](#5-the-never-list)) is enforced in the planner**, not only in the
  workflow: a forbidden action cannot appear in a plan, so no workflow bug can apply one.

## 2. The register — `repos.yaml`

```yaml
version: 1
org: Example-Org                  # the GitHub org every repo below lives in
defaults:                         # applied to every repo unless the repo overrides the key
  mode: report                    # report | enforce
  visibility: private             # private | internal — checked, never changed to public
  default_branch: main
  settings: {delete_branch_on_merge: true, allow_auto_merge: false}

service_accounts:                 # F6: SAs the project creates in its own GCP project
  - name: payments-api-deployer
    description: "CI deployer for payments-api only (owner: payments team, 2026-10-20)"
  - name: payments-api-run
    description: "Cloud Run runtime identity of payments-api (owner: payments team)"

repos:
  - name: payments-api
    kind: go-service              # free text today; a future skeleton feature keys on it
    description: "Payments HTTP API"
    variables: {GCP_WIF_PROVIDER: "projects/123/locations/global/workloadIdentityPools/p/providers/github"}
    gcp: {service_accounts: [payments-api-deployer]}    # F5: SAs this repo may act as
    deploys:                                            # F7: what this repo may deploy
      - cloud_run: payments-api
        region: europe-west1
        runtime_service_account: payments-api-run
        image_repository: europe-west1/services         # <location>/<GAR repository>
  - name: ledger-worker
    status: new                   # F2 creates it if missing
    mode: enforce                 # overrides defaults.mode for this repo only
    deploys:
      - gke: {cluster: europe-west1/main, namespace: ledger, workload: ledger-worker}
  - name: billing-web
    rename_from: legacy-billing   # the ONLY way a rename ever happens
```

### Which feature reads which key

| Key | Read by | Notes |
|---|---|---|
| `version`, `org` | every feature | `version` must be `1`; `org` is the owner of every repo listed |
| `defaults.*` | the feature that reads the defaulted key | a repo's own key wins over the default |
| `repos[].name` | every feature | the repo's identity; unique in the file |
| `repos[].mode` | F2-F7 | `report` or `enforce` ([§4](#4-report-vs-enforce)) |
| `repos[].status`, `repos[].rename_from` | F2 create | `status: new` = create if missing |
| `repos[].description`, `visibility`, `default_branch`, `settings` | F3 settings | |
| `repos[].variables` | F4 variables | NON-secret values only |
| `repos[].gcp.service_accounts` | F5 WIF link | SAs must already exist; F5 never creates one |
| top-level `service_accounts:` | F6 service accounts | create-if-missing only |
| `repos[].deploys` | F7 deploy scope | Cloud Run or GKE entries |
| `repos[].kind` | nobody yet | inventory only |

**Unknown keys are ignored by every feature** — at any level, including inside a repo entry. A
feature never fails on a key it does not own, and never emits an action for one. The schema
([§3](#3-schema-schemasreposv1json-in-words)) allows additional properties for the same reason.

**Removing a repo from the register means "stop managing it".** No feature emits any action for
a repo that is not listed: it is not deleted, archived, renamed or reset. The same holds for a
removed service account, variable, link or deploy entry.

## 3. Schema `schemas/repos.v1.json`, in words

The JSON Schema (draft 2020-12) ships as `schemas/repos.v1.json` in this repo, with the workflows.
F1 validates against it; every planner validates the parts it reads before planning.

- **Top level** — required: `version` (integer, const `1`), `org` (string, a GitHub login:
  `^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$`), `repos` (array, may be empty). Optional: `defaults`
  (object), `service_accounts` (array). Additional properties allowed (ignored).
- **`defaults`** — optional keys `mode`, `visibility`, `default_branch`, `settings`, same types
  as on a repo.
- **`repos[]`** — object; required: `name` (string, `^[A-Za-z0-9._-]{1,100}$`, unique across the
  array). Optional:
  - `kind` (string), `description` (string, ≤ 350 chars)
  - `status` (enum `new` | `existing`; absent = `existing`)
  - `rename_from` (string, same pattern as `name`, must differ from `name` and from every other
    entry's `name`)
  - `mode` (enum **`report` | `enforce`**)
  - `visibility` (enum **`private` | `internal`**). **`public` is not allowed** — a register that
    says `public` is invalid, not merely ignored.
  - `default_branch` (string, non-empty)
  - `settings` (object; v1 keys: `delete_branch_on_merge`, `allow_auto_merge`,
    `allow_squash_merge`, `allow_merge_commit`, `allow_rebase_merge`, `has_issues`, `has_wiki`,
    `has_projects` — all boolean; other keys are ignored)
  - `variables` (object, keys `^[A-Z_][A-Z0-9_]*$` and not starting with `GITHUB_`, values
    string). Secrets never go here.
  - `gcp` (object): `service_accounts` (array of SA names, pattern below, unique)
  - `deploys` (array). Each item has **exactly one** of:
    - `cloud_run` (string, the service name) — then `region` (string) and
      `runtime_service_account` (SA name) are required, `image_repository`
      (`<location>/<repository>`) is optional;
    - `gke` (object, all required: `cluster` as `<location>/<name>`, `namespace`, `workload`).
- **`service_accounts[]`** — object; required: `name` and `description`.
  - `name`: string, **6-30 chars, `^[a-z][a-z0-9-]*$`** (the GCP account-id rule; the schema
    pattern is `^[a-z][a-z0-9-]{4,28}[a-z0-9]$`, which also forbids a trailing hyphen as GCP does).
  - `description`: string, non-empty, ≤ 256 chars — **required** (fleet rule: every SA says what
    it is for, who owns it, when and why it was made).
  - optional `display_name` (string, ≤ 100 chars).
- **Deployer naming** (F7, not schema-enforced): one deployer SA per deployable, conventionally
  `<deployable>-deployer`; the name must still fit 30 chars, so long service names abbreviate.

## 4. Report vs enforce

| | `report` (the default) | `enforce` |
|---|---|---|
| What the planner emits | `drift` entries only — never a write action | the write actions |
| What the workflow does | lists every examined repo in the job summary with its drift or "in sync" | applies the actions in order, then lists them |
| Token | the narrowest read permission the feature has | the write permission |

**Every repo added to the register starts in `report`**, because `defaults.mode` is `report` and
a repo inherits it. A repo moves to `enforce` only by a reviewed register change. The mode is per
repo: one repo can be enforced while the rest are reported.

F1 has no mode (it writes nothing). F6 has no repo, so it reads `defaults.mode` (an SA entry may
carry its own `mode`, same enum).

## 5. The NEVER list

No feature, in any mode, ever:

1. **deletes** a repository;
2. **archives** a repository;
3. **makes a repository public** (`visibility` is checked; `public` is invalid in the register);
4. **renames** a repository unless that repo's entry says `rename_from:` explicitly;
5. **creates a service-account key** (deploys are keyless, WIF only);
6. **deletes a service account**;
7. **grants a project-level IAM role** (only resource-level bindings: on one SA, one Cloud Run
   service, one Artifact Registry repository; project-level grants are the access-provisioning
   owner's, done by a human config change);
8. removes or changes a binding it did not add — F5 only ever **adds**
   `roles/iam.workloadIdentityUser` principalSets; it never removes one.

**Removing a repo (or SA, variable, link, deploy entry) from the register = stop managing it.**

**Where it is enforced:** in the planner. The planner's action vocabulary
([§8](#8-the-planner-action-list--the-contract)) contains no verb for any item above, and a
register that would need one (a `public` visibility, a `rename_from` that collides with an
existing repo) is refused with an error, not planned around. The workflow checks every action
name against the same allow-list before applying it — defence in depth, not the primary control.

## 6. Features F1-F7 (adopt any one alone)

No feature requires another. Each row lists what you must have to adopt that feature by itself.

| # | Workflow | Reads | Credential | Writes |
|---|---|---|---|---|
| F1 | `repos-register-check.yml` | the whole file, against the schema | none | nothing |
| F2 | `repos-create.yml` | `status`, `rename_from`, `visibility`, `default_branch`, `description` | App token: `administration:write`, `metadata:read` | GitHub repos |
| F3 | `repos-settings.yml` | `description`, `visibility`, `default_branch`, `settings` | report: `metadata:read`; enforce: `administration:write` | repo settings |
| F4 | `repos-variables.yml` | `variables` | report: `actions_variables:read`; enforce: `actions_variables:write` | repo variables |
| F5 | `repos-wif-link.yml` | `gcp.service_accounts` | GCP: the project's `repo-admin` SA via WIF (`id-token: write`) | SA IAM bindings |
| F6 | `repos-service-accounts.yml` | top-level `service_accounts` | GCP: `repo-admin` via WIF | service accounts |
| F7 | `repos-deploy-scope.yml` | `deploys` | GCP: `repo-admin` via WIF | Cloud Run service (create once) + resource-level IAM |

GitHub-side features (F2-F4) mint a GitHub App installation token narrowed with `permission-*`
inputs to exactly the row above, and run only in the `repo-admin` environment
([§9](#9-the-repo-admin-environment)). GCP-side features (F5-F7) hold no GitHub write.

**F1 — check the register.** Validates `repos.yaml` against `schemas/repos.v1.json` plus the
cross-entry rules the schema cannot express (unique names, `rename_from` collisions, `deploys`
referencing an SA name that is well-formed). Run it on every pull request that touches the
register. Adopt alone: a project that only wants an inventory calls F1 and nothing else.

**F2 — create repos.** For each `status: new` repo that does not exist: create it with the
register's visibility (default `private`), description and default branch. For each
`rename_from` whose old name exists and new name does not: rename. Idempotent — an existing repo
is `skip`ped ("exists, skipped"); a rename whose target already exists is `skip`ped if the old
name is gone, and refused if both exist. Needs the App installed on **all repositories** of the
org, or it cannot see the repo it just created.

**F3 — repo settings.** Compares description, visibility, default branch and `settings` with
live. Report lists the diff; enforce applies it. Visibility can move `internal` ↔ `private`, never
to `public`. A `default_branch` that does not exist in the repo is reported, never created.

**F4 — repo variables.** Same report/enforce for the NON-secret repository variables listed.
Variables live but not listed are not managed (left alone, not reported). Never deletes a
variable. Secrets are out of scope — they have their own distribution.

**F5 — link a repo to a deploy identity (repo-level WIF).** For each SA in a repo's
`gcp.service_accounts`, ensure the SA's IAM policy holds `roles/iam.workloadIdentityUser` for
`principalSet://iam.googleapis.com/projects/<number>/locations/global/workloadIdentityPools/<pool>/attribute.repository/<org>/<repo>`.
Inputs: the GCP project id and number, pool id, the `repo-admin` SA email and the WIF provider.
The SA must already exist — a missing SA is an error (F5 never creates one; that is F6). The
ORG-level pool and provider are set up once by the access-provisioning owner and are never
touched here; the provider's condition limits every link to repos of the same org.

**F6 — the project's own service accounts.** Creates each listed SA that does not exist, with its
required description. Never deletes one, never creates a key, never grants it a project-level
role. A listed SA that exists is `in-sync`, or `drift` if its description or display name differ
(enforce updates them).

**F7 — deploy scope.** Per `deploys:` entry, so a repo can deploy only its own service:
- **Cloud Run:** if the service does not exist, create it once with a placeholder image (resource
  IAM needs the service to exist), running as `runtime_service_account`; then bind the
  deployer SA (`<deployable>-deployer`, the repo's `gcp.service_accounts` entry) with
  `roles/run.developer` **on that service**, `roles/iam.serviceAccountUser` **on that runtime
  SA**, and `roles/artifactregistry.writer` **on `image_repository`** (GAR IAM is per repository,
  not per image — a dedicated repository per deployable is the stricter option).
- **GKE:** the deployer gets `roles/container.clusterViewer` on the cluster (to fetch
  credentials) and a namespaced Kubernetes `Role` whose rules always carry
  `resourceNames: [<workload>]`, bound to the Google identity — never `roles/container.developer`
  (it covers every namespace).
- **Migration aid:** reports (never fixes) any project-level `run.*` or `container.*` role a
  deployer still holds. Removing it is a human change in the access-provisioning config.

## 7. Planner / workflow split

Every feature is a **thin workflow over a pure planner**:

```
repos.yaml + live-state JSON  ──►  planner (pure: no network, no clock, no env)  ──►  action list JSON
                                                                                       │
workflow: fetch live state (gh api / gcloud) ─────────────────────────────────────────►  apply in order
```

- Planners: `scripts/repos_plan.py` (F1-F4), `scripts/repos_wif_plan.py` (F5),
  `scripts/repos_sa_plan.py` (F6), `scripts/repos_deploy_plan.py` (F7).
- Invocation: `python3 scripts/<planner>.py --feature <name> --register repos.yaml --state
  state.json` — stdout is the action list ([§8](#8-the-planner-action-list--the-contract)).
- Same input → same output, always. The planner reads only its two files; the workflow does every
  `gh api` / `gcloud` call. That is what lets fixture tests (`tests/run_repos_*_tests.py`) prove
  the decision logic and the NEVER list with no cloud and no GitHub.
- The live-state JSON shape for each feature is defined by its fixtures and documented on the
  feature's own page; the action list below is common to all.

## 8. The planner action list — the contract

**Output.** On success the planner prints, to stdout, one JSON **array** of action objects and
exits `0`. Every examined repo (or SA) yields at least one entry (`in-sync` when nothing
differs), so an empty array means the feature had nothing to examine. On any error it prints nothing to stdout, prints one line per
error to stderr as `error: <repo-or-sa-or-"register">: <reason>`, and exits `1`. **There is no
partial plan:** one error refuses the whole run.

**Each action object has exactly four keys**, in this order:

| Key | Type | Meaning |
|---|---|---|
| `feature` | string enum | `register`, `create`, `settings`, `variables`, `wif-link`, `service-accounts`, `deploy-scope` |
| `repo` | string or `null` | the register's repo `name`; `null` only for F6 actions (an SA has no repo) |
| `action` | string enum | one verb from the table below |
| `details` | object | the verb's fields below; always present, `{}` when it has none |

**Order.** Repos in register order; within a repo, actions in the order they must be applied
(F2: `rename-repo` before `create-repo`; F7: `create-service` before its bindings). F6 actions
(`repo: null`) follow register order of `service_accounts:`. Tests compare parsed JSON, not bytes.

**Non-write verbs** (allowed in any mode):

| `action` | `details` |
|---|---|
| `in-sync` | `{}` — emitted once per examined repo (or SA) with nothing to do, so a summary can list every repo examined |
| `skip` | `{"reason": string}` — e.g. `"exists"`, `"rename already done"` |
| `drift` | `{"would": <write verb>, ...that verb's details}` — a difference in `report` mode |
| `unsupported` | `{"key": string, "reason": string}` — a key this org or plan cannot honour (branch protection) |
| `legacy-grant` | `{"service_account": string, "role": string, "scope": "project"}` — F7 migration report |

**Write verbs** (emitted only for a repo or SA in `enforce` mode; one feature each):

| `feature` | `action` | `details` |
|---|---|---|
| `create` | `create-repo` | `{"visibility": "private"\|"internal", "default_branch": string, "description": string\|null}` |
| `create` | `rename-repo` | `{"from": string, "to": string}` |
| `settings` | `update-repo` | `{"field": string, "from": any, "to": any}` — one action per differing field |
| `variables` | `set-variable` | `{"name": string, "from": string\|null, "to": string}` — `from: null` = create |
| `wif-link` | `add-wif-binding` | `{"service_account": string, "role": "roles/iam.workloadIdentityUser", "member": string}` |
| `service-accounts` | `create-service-account` | `{"name": string, "display_name": string, "description": string}` |
| `service-accounts` | `update-service-account` | `{"name": string, "field": "description"\|"display_name", "from": string, "to": string}` |
| `deploy-scope` | `create-service` | `{"service": string, "region": string, "runtime_service_account": string, "image": "placeholder"}` |
| `deploy-scope` | `add-resource-binding` | `{"resource_type": "run.service"\|"iam.serviceAccount"\|"artifactregistry.repository"\|"container.cluster", "resource": string, "role": string, "member": string}` |
| `deploy-scope` | `apply-k8s-rbac` | `{"cluster": string, "namespace": string, "workload": string, "resource_names": [string], "member": string}` |

**Invariants every planner test may assert:**
- a repo in `report` mode yields only non-write verbs;
- no verb outside the two tables above is ever emitted (there is no delete, archive, unarchive,
  make-public, key-create or project-level-grant verb);
- `rename-repo` appears only for a repo whose entry has `rename_from`;
- `update-repo` with `field: "visibility"` never has `to: "public"`;
- `add-wif-binding.role` is always `roles/iam.workloadIdentityUser`;
- `add-resource-binding.resource_type` is never a project, and `apply-k8s-rbac.resource_names` is
  never empty;
- a repo absent from the register yields no action at all.

Example (F3, one repo enforced, one reported):

```json
[
  {"feature": "settings", "repo": "payments-api", "action": "update-repo",
   "details": {"field": "delete_branch_on_merge", "from": false, "to": true}},
  {"feature": "settings", "repo": "ledger-worker", "action": "drift",
   "details": {"would": "update-repo", "field": "description", "from": "", "to": "Ledger worker"}},
  {"feature": "settings", "repo": "billing-web", "action": "in-sync", "details": {}}
]
```

## 9. The `repo-admin` environment

The GitHub-side features act with the org's existing **release GitHub App**, extended with
`Administration: Read and write` and installed on all repositories — but with a **second private
key** held only in a protected environment, so it can be revoked without touching releases.

- In `<org>/project`: environment **`repo-admin`**, deployment branches **`main` only**, secret
  **`REPO_ADMIN_APP_KEY`** (the second key). The App id is the existing repo variable
  **`RELEASE_APP_ID`**.
- The reusable job declares `environment: ${{ inputs.environment }}` (default `repo-admin`), the
  same shape `release-drafts.yml` uses for its key, and F2-F4 fail before minting a token unless
  the environment is `repo-admin` and `github.ref` is `refs/heads/main`.
- Pass the key **by name** (`secrets: REPO_ADMIN_APP_KEY: ...`); `secrets: inherit` is same-org
  only.
- App settings (permissions, installation scope, keys) are UI-only: the owner sets them; no
  workflow can.

## 10. Minimal caller

A project adopting only F1 (on PRs) and F3 (on `main`) — every other feature is another job,
added when wanted:

```yaml
name: repos
on:
  pull_request:
    paths: [repos.yaml]
  push:
    branches: [main]
    paths: [repos.yaml]
  workflow_dispatch:
permissions:
  contents: read
jobs:
  check:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-register-check.yml@vX.Y.Z
    with:
      register: repos.yaml
  settings:
    if: github.ref == 'refs/heads/main'
    needs: check
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/repos-settings.yml@vX.Y.Z
    with:
      register: repos.yaml
      app-id: ${{ vars.RELEASE_APP_ID }}
      environment: repo-admin
    secrets:
      REPO_ADMIN_APP_KEY: ${{ secrets.REPO_ADMIN_APP_KEY }}
```

Pin an exact `vX.Y.Z` release, never `@main` or `@v1`. The input names above are the design of
record; the feature's own docs page is authoritative once it ships.

## 11. Branch protection — not supported yet

Branch protection is **not** a v1 key. When added, it becomes an optional `repos[].protection`
object read by one more feature; until then a `protection` key is ignored like any unknown key.
That feature will detect whether the org's plan supports protection for the repo (free-plan
private repos answer HTTP 403 on the rulesets/protection API) and emit `unsupported` with the
reason instead of failing — never an error, never a silent pass.
