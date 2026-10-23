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
6. [Features F1-F9 (adopt any one alone)](#6-features-f1-f9-adopt-any-one-alone)
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
  visibility: private             # private | internal — checked and reported, never changed
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
        region: europe-west1                            # runtime SA is derived: payments-api-run
        image_repository: europe-west1/services         # <location>/<GAR repository>
        env_secret: true                                # F8: secret payments-api-env (derived name)
        public: true                                    # F7: anyone may call it (allUsers run.invoker)
  - name: ledger-worker
    status: new                   # F2 creates it if missing
    mode: enforce                 # overrides defaults.mode for this repo only
    deploys:
      - gke: {cluster: europe-west1/main, namespace: ledger, workload: ledger-worker}  # reported unsupported
  - name: billing-web
    rename_from: legacy-billing   # the ONLY way a rename ever happens
```

### Which feature reads which key

| Key | Read by | Notes |
|---|---|---|
| `version`, `org` | every feature | `version` must be `1`; `org` is the owner of every repo listed |
| `defaults.*` | the feature that reads the defaulted key | a repo's own key wins over the default |
| `repos[].name` | every feature | the repo's identity; unique in the file |
| `repos[].mode` | F2-F7, F9 | `report` or `enforce` ([§4](#4-report-vs-enforce)) |
| `repos[].status`, `repos[].rename_from` | F2 create | `status: new` = create if missing |
| `repos[].description`, `visibility`, `default_branch`, `settings` | F3 settings | |
| `repos[].variables` | F4 variables | NON-secret values only |
| `repos[].gcp.service_accounts` | F5 WIF link | SAs must already exist; F5 never creates one |
| top-level `service_accounts:` | F6 service accounts | create-if-missing only |
| `repos[].deploys` | F7 deploy scope | Cloud Run entries; a GKE entry is reported `unsupported` |
| `repos[].deploys[].public` | F7 deploy scope | `true` = anyone may call this Cloud Run service (`allUsers` holds `roles/run.invoker` on it); absent = private; any other value is an error |
| `repos[].deploys[].env_secret` | F8 secrets | `true` = this Cloud Run entry gets the secret `<cloud_run>-env`; any other value is an error (the name is derived, never chosen) |
| `repos[].environments` | F9 environments | GitHub deployment environments of this repo and their branch/tag policy ([§6](#6-features-f1-f9-adopt-any-one-alone)); no secrets, no reviewers |
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
      are required, `image_repository` (`<location>/<repository>`) is optional.
      `runtime_service_account` is optional and **derived**: the runtime SA is always
      `<cloud_run>-run`; a value that is present must equal it, or F7 exits `1`.
      `env_secret` is optional and must be the boolean `true` when present (F8; the secret name
      `<cloud_run>-env` is derived, so a string such as `web-env` is refused). `public` is optional
      and must be the boolean `true` when present (F7); a private service omits the key. A `cloud_run` name
      may appear under only one repo (a deployable belongs to exactly one repo; F1-F9 refuse a
      register that lists it twice);
    - `environments` (array, optional; F9). Each entry is an object with required `name`
      (string, `^[A-Za-z0-9._-]{1,100}$`, unique within the repo) and at least one of `branches`
      (array of non-empty branch-name patterns) or `tags` (array of non-empty tag-name patterns);
      anything else on the entry is ignored. An entry with neither is an error. Required reviewers,
      wait timers and secrets are deliberately not keys (reviewers return HTTP 422 on a free
      private repo; secrets belong to `distribute-env-secrets` and the owner). The same `name` may
      appear under different repos;
    - `gke` (object, all required: `cluster` as `<location>/<name>`, `namespace`, `workload`). The
      schema accepts it so a register can record intent, but F7 does not act on it
      ([§6](#6-features-f1-f9-adopt-any-one-alone)).
  - **Names that reach a command line** (`cloud_run`, `region`, `image_repository`, every repo
    name and `rename_from`, `default_branch`, SA names, the `gke` fields) are checked against
    patterns and may never start with `-`, so no register value can turn into a flag: Cloud Run
    service `^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$`, region `^[a-z]+-[a-z]+[0-9]$`, repo name
    `^[A-Za-z0-9._-]{1,100}$` that does not start with `-` and is not `.` or `..`. Free text
    (descriptions, variable values) is always the value of a `--field name=value` argument, never
    a positional, so it is not pattern-checked.

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
3. **makes a repository public** (`visibility` is checked; `visibility: public` is invalid in the
   register). A Cloud Run service is a different thing: F7 lets anyone call one only when its
   `deploys` entry says `public: true` ([§6](#6-features-f1-f9-adopt-any-one-alone));
4. **renames** a repository unless that repo's entry says `rename_from:` explicitly;
5. **creates a service-account key** (deploys are keyless, WIF only);
6. **deletes a service account**;
7. **grants a project-level IAM role** (only resource-level bindings: on one SA, one Cloud Run
   service, one Artifact Registry repository, one `<d>-env` secret; project-level grants are the
   access-provisioning owner's, done by a human config change);
8. removes or changes a binding it did not add — F5 only ever **adds**
   `roles/iam.workloadIdentityUser` principalSets; it never removes one;
9. **writes the policy of, or creates or edits, a service account that is not the project's own.**
   One writer per service-account policy (owner ruling 21): the NAME says who writes it. A
   `^[a-z][a-z0-9-]*-deployer$` account is the project's (F5 links it, F6 creates and updates it);
   every other account (`repo-admin`, the CI accounts, every runtime `<d>-run`) belongs to the
   access-provisioning side, which is the only writer of its policy. `repo-admin` fails the suffix
   rule by name, so no list has to be kept in step. The old `protected_service_accounts` input was
   **removed** (owner ruling 2026-10-20: no release had shipped it). Why: linking `repo-admin` to a repo would hand its
   power to every branch and pull-request job of that repo, with no environment review in the way.
   This is a mistake-guard, not a barrier: `repo-admin` can still write project-wide, and the exact
   audit on the access-provisioning side is what detects a breach;
10. **changes the visibility of an existing repository, in either direction** (F3 reports a
    difference and never writes it, in `report` and `enforce` mode alike; a human flips it in
    GitHub). Making a public repository private cannot be undone: stars and watchers are lost.
    Visibility is only ever set when F2 creates a repo.
11. **deletes an environment** (F9 plans no delete verb; deleting an environment deletes the
    secrets stored in it, which nothing here can restore). An environment the register does not
    list is reported (`unmanaged-environment`), never touched.

**Removing a repo (or SA, variable, link, deploy entry) from the register = stop managing it.**

**Where it is enforced:** in the planner. The planner's action vocabulary
([§8](#8-the-planner-action-list--the-contract)) contains no verb for any item above, and a
register that would need one (a `public` visibility, a `rename_from` that collides with an
existing repo) is refused with an error, not planned around. The workflow checks every action
name against the same allow-list before applying it — defence in depth, not the primary control.

## 6. Features F1-F9 (adopt any one alone)

No feature requires another. Each row lists what you must have to adopt that feature by itself.

| # | Workflow | Reads | Credential | Writes |
|---|---|---|---|---|
| F1 | `repos-register-check.yml` | the whole file, against the schema | none | nothing |
| F2 | `repos-create.yml` | `status`, `rename_from`, `visibility`, `default_branch`, `description` | App token: `administration:write`, `metadata:read` | GitHub repos |
| F3 | `repos-settings.yml` | `description`, `visibility`, `default_branch`, `settings` | report: `administration:read` + `metadata:read` (still read-only); enforce: `administration:write` | repo settings (never `visibility`) |
| F4 | `repos-variables.yml` | `variables` | report: `actions_variables:read`; enforce: `actions_variables:write` | repo variables |
| F5 | `repos-wif-link.yml` | `gcp.service_accounts` | GCP: the project's `repo-admin` SA via WIF (`id-token: write`) | SA IAM bindings |
| F6 | `repos-service-accounts.yml` | top-level `service_accounts` | GCP: `repo-admin` via WIF | service accounts |
| F7 | `repos-deploy-scope.yml` | `deploys` | GCP: `repo-admin` via WIF | Cloud Run service (create once) + resource-level IAM |
| F8 | `repos-secrets.yml` | `deploys[].env_secret` | GCP: `repo-admin` via WIF | Secret Manager secret `<d>-env` (create once, never its versions) + that secret's IAM policy |
| F9 | `repos-environments.yml` | `environments` | report: `actions:read`; enforce: `administration:write` on the repos it writes to. The org's automation App (`<org>-automation`) holds it, per the Q1 ruling ([§9](#9-the-repo-admin-environment)) | GitHub environments + their deployment branch/tag policies (never deletes one) |

GitHub-side features (F2-F4, F9) mint a GitHub App installation token narrowed with `permission-*`
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
live. Report lists the diff; enforce applies it, except **visibility, which is never written**: a
difference is always `drift{would: "update-repo", field: "visibility", from, to}`, even in
`enforce` mode, and the repo counts as drifting (no `in-sync`) until a human changes it in GitHub.
The report token holds `administration:read` beside `metadata:read` so the merge-setting fields
(`allow_*`, `delete_branch_on_merge`) can be read; it can write nothing. (Whether `metadata:read`
alone would return those fields is not stated in GitHub's permission table, which lists
`GET /repos/{owner}/{repo}` under Metadata only; unverified, so the broader read is requested.) A `default_branch` that does not exist in the repo is reported, never created.

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
**A repo links only its own deployers** ([§5](#5-the-never-list), item 9): repo R may link only
`<d>-deployer` for a `cloud_run: <d>` in R's own `deploys:`. Anything else makes the planner exit `1`
with no plan at all (not a partial one), in report and enforce mode alike: `github-releaser`
gives `error: <repo>: github-releaser is not a project SA: ask JGD (wif_repos) ...`, and another
repo's deployer gives `... is not a deployer of a deployable of <repo> ...`. Linking a repo to a
shared access-provisioning CI identity is that side's `wif_repos`, not this register's.

**F6 — the project's own service accounts.** Creates each listed SA that does not exist, with its
required description. Never deletes one, never creates a key, never grants it a project-level
role, and refuses (error, exit `1`, no plan) a register entry whose name is not a `-deployer`
account (`... is not a project SA`) or is not `<d>-deployer` for a `cloud_run: <d>` that some repo
in the register deploys (`github-deployer` with no `github` deployable is refused): it creates and
updates only the project's own deployers and never adopts any other account, even one that already
exists. F5 and F6 also refuse a register that lists a deployable under two repos, as F1-F4 and F7
do, and their apply steps re-check the `-deployer` suffix on the whole plan before any write. The access-provisioning config owns
those accounts and their descriptions. A listed SA that exists is `in-sync`, or `drift` if its
description or display name differ (enforce updates them).

**F7 — deploy scope.** First the same schema check as F1 (a refused register plans nothing, so
a service name like `--ingress=all` never reaches `gcloud`). Then, per `deploys:` entry, so a repo can deploy only its own service:
- **Cloud Run:** if the service does not exist, create it once with a placeholder image (resource
  IAM needs the service to exist), running as the derived runtime SA `<deployable>-run`; then bind
  the deployer SA (`<deployable>-deployer`, the repo's `gcp.service_accounts` entry) with
  `roles/run.developer` **on that service** and `roles/artifactregistry.writer` **on
  `image_repository`** (GAR IAM is per repository, not per image — a dedicated repository per
  deployable is the stricter option).
- **Public services: `public: true`** (owner, 2026-10-23). F7 is the one writer of who may *call* a
  service. For an entry with `public: true` it adds `allUsers` → `roles/run.invoker` **on that
  service** (an `add-resource-binding`, gated like every other binding, after `create-service`).
  The service repo cannot do it: its deployer holds `run.developer`, which can read the service's
  policy but not set it, so `--allow-unauthenticated` in its `deploy_flags` only makes gcloud warn
  (deploy-cloud-run then fails its read-back, [deploy-cloud-run.md](deploy-cloud-run.md#public-services)).
  The grant runs from the org's `project` repo, never from the service repo. **F7 never removes it:**
  a service where `allUsers` holds `roles/run.invoker` but whose entry has no `public: true` is
  `drift{would: "remove-public-invoker", resource_type: "run.service", resource, region, role,
  member: "allUsers", reason}` in **every** mode (plus a run warning), and a person removes the
  grant or adds `public: true` (owner Q1, 2026-10-23). The apply step also checks, from the
  register itself rather than the planner, that each `allUsers` binding is on a `public: true`
  entry (`public.json`, written by the Plan step), so a planner bug cannot open another service.
  An org policy that restricts members to
  the org's domain refuses `allUsers`; the binding then fails in the apply step, loudly.
- **F7 writes no service-account policy** (ruling 21). The runtime SA `<deployable>-run` is
  declared by the access-provisioning side, which is the only writer of its policy; its config
  carries `deployed_by: <deployable>-deployer` (the deployer's `roles/iam.serviceAccountUser` on it)
  and, while a service is still to be created, an `act_as` line for `repo-admin`. F7 only **reads**
  that policy and reports `needs-jgd{resource_type: "iam.serviceAccount", resource, role, member,
  needs}` for each line that is not live (`needs` is `deployed_by: <deployable>-deployer` or
  `act_as: repo-admin`), in both modes; a runtime SA that does not exist yet reads as empty. The fix
  is one access-provisioning config change, never a write from here.
- **A new service waits for its `act_as` line.** `gcloud run deploy --service-account=<d>-run` needs
  repo-admin's `act_as` on that account, which F7 cannot grant. While the service does not exist
  and that line is not live (or `<d>-run` is absent), F7 plans **only** `needs-jgd` for the
  deployable (the `act_as` line and the `deployed_by` line): no `create-service`, no binding, in
  both modes, so the apply never reaches `gcloud run deploy` and never half-applies a register.
  The next run, once the line is live, creates and binds. An existing service is unaffected.
- **Derived ids must be valid GCP ids.** `<d>-deployer` and `<d>-run` must each be 6-30 chars; a
  deployable that breaks either (`a-run` is 5) is `error: <repo>: ...`, exit `1`, no plan.
- **The runtime SA is derived, not chosen.** `runtime_service_account` is optional; if present it
  must equal `<deployable>-run`, else exit `1`, `error: <repo>: ...`, no plan. So a repo can never
  point its service at another identity (such as `repo-admin`), and a deployable under two repos is
  refused in the register itself ([§3](#3-schema-schemasreposv1json-in-words)).
- **GKE is deferred.** No project uses GKE, and in-cluster Role/RoleBinding creation needs
  Kubernetes rights nothing here holds. A `deploys` entry with `gke` yields
  `unsupported{key: "gke", reason}` in both modes and nothing else; F7 never runs `kubectl`. It is
  built, with its own tests, the day a project moves to GKE.
- **The region comes from the register**, never from a live lookup: the `region` of the `deploys`
  entry travels in the `details` of every `run.service` binding, so the workflow needs no
  `run.services.list` permission, for new and existing services alike.
- **No legacy-grant scan.** F7 does not read project-level IAM. The scan only ever looked at the
  new `<deployable>-deployer` accounts, which never held project roles, so it could not report the
  shared accounts it was meant to migrate; moving a project off a shared account's project-level
  roles is a human change in the access-provisioning config.

**F8 — per-service secrets** (owner ruling 24; page [repos-secrets.md](repos-secrets.md)). Same
schema check as F1 first (a refused register plans nothing). For each `cloud_run: <d>` entry with
`env_secret: true`, F8 owns the secret `<d>-env` and its **whole** IAM policy (one writer per secret
policy, ruling 21's rule extended). The desired policy is exactly: `<d>-run` →
`roles/secretmanager.secretAccessor`; `<d>-deployer` → `secretAccessor`, `secretVersionManager`,
`viewer` (the sync role set; it includes `versions.destroy`, by owner choice). Per deployable: a
missing `<d>-deployer` is `error: <repo>: ... run F6 first` (exit `1`, no plan at all); a missing
`<d>-run` is `needs-jgd` and nothing else for that deployable; a missing secret is `create-secret`
(empty, no version); an existing one is `adopt`ed (never recreated, versions never read); a missing
policy line is `add-secret-binding`; a line that is not wanted is `drift{would:
"remove-secret-binding"}`, written only in `enforce` with `--prune`. **F8 never** deletes a secret,
adds/reads/disables/destroys a version, touches a secret that is not `<d>-env` for a registered `d`,
or binds any other role. `env_secret` must be boolean `true`: a name is derived, never chosen.

**F9 — environments** (page [repos-environments.md](repos-environments.md)). Same schema check as
F1 first. For each repo with an `environments:` list, F9 makes the repo's GitHub environments
match it: a missing environment is `create-environment` (custom branch policies on, protected
branches off), a missing branch or tag policy is `add-branch-policy`, a policy on a listed
environment that the register does not list is `remove-branch-policy` (in `report`, a `drift`), an
environment that matches is `in-sync`, and an environment on the repo that the register does not
list is `unmanaged-environment` (report only, in both modes). **F9 never** deletes an environment
([§5](#5-the-never-list) item 11), writes a secret or variable into one, sets required reviewers
or wait timers, or touches a repo that is not in the register. It runs from the project repo
against the project's service repos; a service repo never calls it.

## 7. Planner / workflow split

Every feature is a **thin workflow over a pure planner**:

```
repos.yaml + live-state JSON  ──►  planner (pure: no network, no clock, no env)  ──►  action list JSON
                                                                                       │
workflow: fetch live state (gh api / gcloud) ─────────────────────────────────────────►  apply in order
```

- Planners: `scripts/repos_plan.py` (F1-F4), `scripts/repos_wif_plan.py` (F5),
  `scripts/repos_sa_plan.py` (F6), `scripts/repos_deploy_plan.py` (F7),
  `scripts/repos_secrets_plan.py` (F8), `scripts/repos_env_plan.py` (F9).
- Invocation: `python3 scripts/<planner>.py --feature <name> --register repos.yaml --state
  state.json` — stdout is the action list ([§8](#8-the-planner-action-list--the-contract)).
- Same input → same output, always. The planner reads only its two files; the workflow does every
  `gh api` / `gcloud` call. That is what lets fixture tests (`tests/run_repos_*_tests.py`) prove
  the decision logic and the NEVER list with no cloud and no GitHub.
- The live-state JSON shape and the CLI of each planner are stated in
  [§7.1](#71-planner-command-lines-and-live-state-json) and the naming rules in
  [§7.2](#72-naming-formats-ordering-and-modes); the action list below is common to all.

### 7.1 Planner command lines and live-state JSON

Every planner takes `--feature <name> --register <repos.yaml> --state <state.json>`, print the
[§8](#8-the-planner-action-list--the-contract) action list to stdout and exit `0`, or print
nothing to stdout, one `error: <repo|sa|register>: <reason>` line per error to stderr and exit
`1`. An unknown `--feature` exits non-zero with nothing on stdout. The register is read as YAML
(JSON is valid YAML, so a fixture may be JSON in a `.yaml` file).
F7 also needs `--repo-admin-sa-email`, the full email of the `repo-admin` service account (the
workflow's `service_account` input, the identity it authenticates as); without it F7 exits `2`.
There is no `--protected-service-accounts` flag any more (owner ruling 2026-10-20; an unknown flag exits `2`).
Which accounts a planner may manage is decided by the `-deployer` name suffix
(`scripts/repos_protected.py`, `is_project_sa`), not by a list.

| Planner | `--feature` values | Notes on the inputs |
|---|---|---|
| `scripts/repos_plan.py` (F1-F4) | `register`, `create`, `settings`, `variables` | `--state` may be omitted for `register` (F1 needs no live state) |
| `scripts/repos_wif_plan.py` (F5) | `wif-link` | none |
| `scripts/repos_sa_plan.py` (F6) | `service-accounts` | none |
| `scripts/repos_deploy_plan.py` (F7) | `deploy-scope` | required `--repo-admin-sa-email <email>` |
| `scripts/repos_secrets_plan.py` (F8) | `secrets` | optional `--prune` (allow `remove-secret-binding` in enforce) |
| `scripts/repos_env_plan.py` (F9) | `environments` | none |

**F1-F4 live state** — one entry per repo the workflow looked up. A repo with `exists: false`, or
absent from `repos`, does not exist. Live repos the register does not list produce no action.

```json
{"repos": {"payments-api": {"exists": true, "description": "Payments HTTP API",
  "visibility": "private", "default_branch": "main",
  "settings": {"delete_branch_on_merge": true}, "variables": {"GCP_WIF_PROVIDER": "projects/123/..."}}}}
```

F1 (`register`) emits one `in-sync` entry (feature `register`) per repo when the register is valid.

**F5 live state** — keyed by SA account-id (the register's SA name):

```json
{"project_number": "123456789", "pool": "example-pool",
 "service_accounts": {"payments-api-deployer": {"exists": true,
   "policy": {"etag": "BwX...", "bindings": [{"role": "roles/iam.workloadIdentityUser", "members": ["principalSet://..."]}]}}}}
```

`project_number` is the GCP project **number** (a string), used in the principalSet. A name absent
from `service_accounts`, or with `exists: false`, is a missing SA and an error
(`error: <sa-or-repo>: ...`).

**F6 live state** — the SAs that exist live:

```json
{"service_accounts": [{"name": "payments-api-deployer", "description": "...", "display_name": "..."}]}
```

A register with no `service_accounts`, or an empty list, yields `[]`. Errors are named
`error: <sa>: ...`. Every F6 action has `repo: null`.

**F7 live state:**

```json
{"project_id": "example-proj",
 "cloud_run_services": {"payments-api": {"iam": [{"role": "roles/run.developer", "members": ["serviceAccount:..."]}]}},
 "service_accounts": {"payments-api-run": {"iam": []}},
 "gar_repositories": {"europe-west1/services": {"iam": []}}}
```

A Cloud Run service whose key is absent from `cloud_run_services` does not exist. `iam` is a list
of `{"role", "members"}` policy entries. `service_accounts` is keyed by runtime SA name and holds
that SA's own policy. F7 reads no project-level IAM and no cluster. A deployer name longer than 30
characters is an error (`error: <repo>: ...`).

**F9 live state** — one entry per repo the workflow looked up, keyed by repo name. A repo with
`exists: false` is an error (F9 never creates a repo). Otherwise `environments` maps each
environment that exists on the repo to `{"custom_branch_policies": boolean, "policies": [{"name":
string, "type": "branch"|"tag"}]}`; an environment absent from the map does not exist. The workflow
builds it from `GET /repos/{o}/{r}/environments` and, per environment,
`GET .../deployment-branch-policies`. For an existing environment whose `custom_branch_policies`
is `false`, the apply step switches custom policies on (the same idempotent `PUT` that creates an
environment) before the first `add-branch-policy`; no extra verb is needed.

**F8 live state:**

```json
{"project_id": "example-proj",
 "secrets": {"payments-api-env": {"iam": [{"role": "roles/secretmanager.secretAccessor", "members": ["serviceAccount:..."]}]}},
 "service_accounts": {"payments-api-deployer": {}, "payments-api-run": {}}}
```

A secret whose key is absent from `secrets` does not exist. `service_accounts` lists only the
accounts that exist (keyed by account name; the value is ignored). F8 reads no secret version and
no project-level IAM.

### 7.2 Naming formats, ordering and modes

- **Mode per repo** = the repo's `mode`, else `defaults.mode`, else `report`. For F6 the unit is
  the SA entry: its `mode`, else `defaults.mode`, else `report`. In `report` mode only non-write
  verbs are emitted; a write that would happen becomes `drift{would: <verb>, ...}` carrying that
  verb's details.
- **`in-sync` emission:** exactly one per examined repo (or SA) that has nothing to do, and none
  for a repo (or SA) that has any other action, including `drift`.
- **Deployer SA** (F7) is `<deployable>-deployer`, where the deployable is the
  Cloud Run service name.
- **Member formats.** F5 `member` is
  `principalSet://iam.googleapis.com/projects/<project_number>/locations/global/workloadIdentityPools/<pool>/attribute.repository/<org>/<repo>`.
  F7 `member` is `serviceAccount:<sa>@<project_id>.iam.gserviceaccount.com`.
- **`add-resource-binding.resource`** by `resource_type`: `run.service` is the service name;
  `artifactregistry.repository` is
  `<location>/<repo>` (the register's `image_repository`). A `run.service` binding also carries
  `region` in its `details` (the register's `region`); no other resource type does.
- **F7 action order per deployable:** `create-service` (if the service is missing),
  `roles/run.developer` on the service, `roles/artifactregistry.writer` on the repository, then
  the `needs-jgd` lines (`act_as: repo-admin` only while the service is missing, then
  `deployed_by: <d>-deployer`); F7 emits no `iam.serviceAccount` binding. A `gke` entry yields
  one `unsupported` (`key: "gke"`) and nothing else.
- **F5 `unregistered-binding`.** A binding on a registered SA that the register does not list is
  reported, in both modes, with the non-write verb
  `unregistered-binding{service_account, role, member}`. It is never removed. Precisely:
  - *Registered SA* = an SA named in at least one repo's `gcp.service_accounts`. An SA no repo
    lists is not examined, whatever its policy holds.
  - *Listed* = the binding's role is `roles/iam.workloadIdentityUser` AND its member is the F5
    `principalSet` of some repo that lists that SA. Anything else on a registered SA is
    unregistered: another role (even for a listed member), another repo, org or pool (a
    near-miss), a user or group member. One entry per (role, member) pair, in policy order.
  - *The `repo` field* is the first repo, in register order, that lists the SA; the SA is
    reported once, not once per repo. The entries follow that repo's own `add-wif-binding` or
    `drift`.
  - *In-sync.* An `unregistered-binding` counts as an action: it suppresses the `in-sync` of the
    repo it is attached to.
- **Validation scope.** Each planner validates only the keys it reads. F1-F3 reject
  `visibility: public`; F4-F7 do not read `visibility`, so they do not reject it.
- **F6 `display_name`** defaults to the SA name when the register omits it (used by
  `create-service-account`). A field is compared only when the register states it, so an SA with
  no `display_name` in the register is never reported as drifting on it.
- **Missing dependency.** Each planner test runner FAILS, never skips, when a required Python
  dependency (PyYAML, jsonschema) is missing.

## 8. The planner action list — the contract

**Output.** On success the planner prints, to stdout, one JSON **array** of action objects and
exits `0`. Every examined repo (or SA) yields at least one entry (`in-sync` when nothing
differs), so an empty array means the feature had nothing to examine. On any error it prints nothing to stdout, prints one line per
error to stderr as `error: <repo-or-sa-or-"register">: <reason>`, and exits `1`. **There is no
partial plan:** one error refuses the whole run.

**Each action object has exactly four keys**, in this order:

| Key | Type | Meaning |
|---|---|---|
| `feature` | string enum | `register`, `create`, `settings`, `variables`, `wif-link`, `service-accounts`, `deploy-scope`, `secrets`, `environments` |
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
| `drift` | `{"would": <write verb>, ...that verb's details}` — a difference in `report` mode; and in ANY mode: (F3) every `visibility` difference, because visibility is never written, and (F7) `would: "remove-public-invoker"` for a public service whose entry has no `public: true`, because F7 never removes a grant |
| `unsupported` | `{"key": string, "reason": string}` — something this org, plan or feature cannot honour: branch protection, or (F7) `key: "gke"`, a `deploys` entry the feature does not act on |
| `unregistered-binding` | `{"service_account": string, "role": string, "member": string}` — F5: a binding on a registered SA that the register does not list; reported, never removed |
| `needs-jgd` | `{"resource_type": "iam.serviceAccount", "resource": string, "role": "roles/iam.serviceAccountUser", "member": string, "needs": string}` — F7: a line on the runtime SA `<d>-run`'s policy that the access-provisioning side must declare (`deployed_by: <d>-deployer`, or `act_as: repo-admin` while a service is still to be created); reported in both modes, never written. F8 uses the same verb for a missing runtime SA, with `{"resource_type": "iam.serviceAccount", "resource": "<d>-run@<project>...", "needs": "service account <d>-run"}` (no `role`/`member`) |
| `unmanaged-environment` | `{"environment": string}` — F9: an environment exists on a registered repo and the register does not list it; reported in both modes, never changed or deleted |
| `adopt` | `{"secret": string}` — F8: the secret `<d>-env` already exists and lacks a wanted policy line; it is never recreated and its versions are never read. Emitted in both modes |

**Write verbs** (emitted only for a repo or SA in `enforce` mode; one feature each; `update-repo` never carries `visibility`):

| `feature` | `action` | `details` |
|---|---|---|
| `create` | `create-repo` | `{"visibility": "private"\|"internal", "default_branch": string, "description": string\|null}` |
| `create` | `rename-repo` | `{"from": string, "to": string}` |
| `settings` | `update-repo` | `{"field": string, "from": any, "to": any}` — one action per differing field |
| `variables` | `set-variable` | `{"name": string, "from": string\|null, "to": string}` — `from: null` = create |
| `wif-link` | `add-wif-binding` | `{"service_account": string, "role": "roles/iam.workloadIdentityUser", "member": string}` |
| `service-accounts` | `create-service-account` | `{"name": string, "display_name": string, "description": string}` |
| `service-accounts` | `update-service-account` | `{"name": string, "field": "description"\|"display_name", "from": string, "to": string}` |
| `deploy-scope` | `create-service` | `{"service": string, "region": string, "runtime_service_account": string (derived `<service>-run`), "image": "placeholder"}` |
| `deploy-scope` | `add-resource-binding` | `{"resource_type": "run.service"\|"artifactregistry.repository", "resource": string, "role": string, "member": string}`; a `run.service` binding adds `"region": string` (from the register). `member` is a `serviceAccount:` except for one shape: `public: true` gives `run.service` + `roles/run.invoker` + `"allUsers"`; the apply refuses every other non-SA member |
| `secrets` | `create-secret` | `{"secret": string (`<d>-env`), "labels": {"managed-by": "repos-secrets", "deployable": string}}` |
| `secrets` | `add-secret-binding` | `{"secret": string, "role": one of the four F8 roles, "member": "serviceAccount:<d>-run@..." or "serviceAccount:<d>-deployer@..."}` |
| `environments` | `create-environment` | `{"environment": string}` — created with custom deployment policies on; its policies follow as `add-branch-policy` actions |
| `environments` | `add-branch-policy` | `{"environment": string, "name": string, "type": "branch"\|"tag"}` |
| `environments` | `remove-branch-policy` | same fields; a policy on a listed environment that the register does not list. In `report` a `drift` with `would: "remove-branch-policy"` |
| `secrets` | `remove-secret-binding` | same fields; emitted only in `enforce` with `--prune`, otherwise a `drift` with `would: "remove-secret-binding"` |

**Invariants every planner test may assert:**
- a repo in `report` mode yields only non-write verbs;
- no verb outside the two tables above is ever emitted (there is no delete, archive, unarchive,
  make-public, key-create or project-level-grant verb);
- `rename-repo` appears only for a repo whose entry has `rename_from`;
- `update-repo` never has `field: "visibility"` (a visibility difference is `drift`, in every mode);
- `add-wif-binding.role` is always `roles/iam.workloadIdentityUser`;
- `add-resource-binding.resource_type` is never a project;
- a repo absent from the register yields no action at all;
- the `environments` feature never emits a delete verb, nor a verb that writes a secret, a variable or a reviewer rule.

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

The GitHub-side features act with the org's existing **automation GitHub App** (formerly the
release App), extended with `Administration: Read and write` and installed on all repositories,
using **the same private key releases use**. There is no second key (owner, 2026-10-21): every key
of an App mints tokens with the App's full permission set, so a second key would add one more
secret to rotate and no isolation. What bounds admin actions is the environment rule below, the
narrowed tokens and the planner's allow-list, not which key is used.

- In `<org>/project`: environment **`repo-admin`**, deployment branches **`main` only**, secret
  **`RELEASE_APP_KEY`** (a copy of the release key, as an environment secret). The App id is the
  existing repo variable **`RELEASE_APP_ID`**.
- **Why `repo-admin` is separate from `release` when both hold the same key.** On the GitHub side
  they are equivalent: the same key mints the same tokens. The split is load-bearing on the GCP side.
  The project's GCP `repo-admin` service account (create service accounts, set IAM on them, on Cloud
  Run services, registries and `<d>-env` secrets) admits only the WIF subject
  `repo:<org>/project:environment:repo-admin`. So release jobs can never obtain it, whatever they
  run. Merging the two environments would hand that identity to the whole release flow.
- **Bootstrapping `repo-admin` (once per project repo, before the first run).** F9 cannot create the
  environment its own job runs in, and a job that names a missing environment creates it with no
  branch rule. So the project creates it first, by API, in the same shape as `release`:
  `gh api -X PUT repos/<org>/project/environments/repo-admin -F 'deployment_branch_policy[protected_branches]=false' -F 'deployment_branch_policy[custom_branch_policies]=true'`,
  then `gh api -X POST repos/<org>/project/environments/repo-admin/deployment-branch-policies -f name=main -f type=branch`,
  then reads both back (exactly one policy, `main`). The org owner then adds the environment secret
  `RELEASE_APP_KEY` by hand.
- The reusable job declares `environment: ${{ inputs.environment }}` (default `repo-admin`), the
  same shape `release-drafts.yml` uses for its key, and F2-F4 and F9 enforce fail before minting a token unless
  the environment is `repo-admin` and `github.ref` is `refs/heads/main`.
- Pass the key **by name** into the workflows' `REPO_ADMIN_APP_KEY` input
  (`REPO_ADMIN_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}`); `secrets: inherit` is same-org only.
- **The write token is narrowed to the repos it writes to.** F3, F4 and F9 mint the write token with
  the action's `repositories:` input set to exactly the repos the plan has write actions for
  (unique, plan order, comma separated; every one exists, because the planner only plans writes
  for live repos). When that list is empty no write token is minted and nothing is applied: an
  empty `repositories:` would mean every repository of the installation. The read token that
  fetches live state is not narrowed (it is read-only).
- App settings (permissions, installation scope, keys) are UI-only: the owner sets them; no
  workflow can.

### F9 (environments) credential

F9 takes the App id (`app_id`, an input) and the private key (`app_key`, a secret passed by name)
as inputs, so the workflow does not depend on which App the project uses. It follows this
section's shape: the job runs in the `repo-admin` environment on `main` only; `report` mints a
read token (`actions: read`, `metadata: read`); `enforce` mints `administration: write` narrowed
to exactly the repos the plan has write actions for, and mints nothing when that list is empty.

**Ruling Q1 (owner, 2026-10-21):** F9's credential is the org's automation App (`<org>-automation`, formerly the release App), extended with
`Administration: write` (the design of record above), plus `Environments: write` for
`distribute-env-secrets`. No separate repo-admin App is created. The rename and the grant are
owner-side GitHub settings changes.

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
      REPO_ADMIN_APP_KEY: ${{ secrets.RELEASE_APP_KEY }}
```

Pin an exact `vX.Y.Z` release, never `@main` or `@v1`. The input names above are the design of
record; the feature's own docs page is authoritative once it ships.

## 11. Branch protection — not supported yet

Branch protection is **not** a v1 key. When added, it becomes an optional `repos[].protection`
object read by one more feature; until then a `protection` key is ignored like any unknown key.
That feature will detect whether the org's plan supports protection for the repo (free-plan
private repos answer HTTP 403 on the rulesets/protection API) and emit `unsupported` with the
reason instead of failing — never an error, never a silent pass.
