# Public Cloud Run service via F7 + deploy-cloud-run read-back (reusable-workflows v5.1.0) — plan

## Decision summary (one screen)

| # | What | Decision |
|---|---|---|
| 1 | Who makes a Cloud Run service public | **F7 `repos-deploy-scope`, run from `<org>/project`** (env `repo-admin`), from a new `public: true` field on the service's `deploys:` entry in `repos.yaml` |
| 2 | Who runs the domain mapping | also **`<org>/project`** (`bootstrap-cf-service` under the `domain-mapper` identity, WIF `repo:<org>/project:environment:repo-admin`). Unchanged |
| 3 | What the service repo does | deploys code only. Its deployer holds `run.developer` ON its own service: it can read who may call it, never change it |
| 4 | Grant shape | reuse verb `add-resource-binding` (`run.service`, `roles/run.invoker`, member `allUsers`); no new verb, so the "no make-public verb" invariant holds |
| 5 | Turning `public` off | **report a `drift`, never remove** (owner, Q1) |
| 6 | deploy-cloud-run silent green | **read back and check** (owner, Q2): when `deploy_flags` has `--allow-unauthenticated`, read the service policy after deploy and fail unless `allUsers → roles/run.invoker` is present |
| 7 | Release | **v5.1.0** (additive). rotate-external-secret moves to **v5.2.0** (renumber its plan) |

## Context

Consumer B's new service deployed green but answers 403 to every request. deploy-cloud-run passed
`--allow-unauthenticated`, gcloud could not set the policy (the deployer has `run.developer`, which
lacks `run.services.setIamPolicy` — verified: 89 permissions, `getIamPolicy` present, `setIamPolicy`
absent), printed a warning, and exited 0. F7 creates every service with `--no-allow-unauthenticated`
and has no way to say a service should be public. The GCP `repo-admin` identity F7 runs as already
sets IAM on Cloud Run services (docs/repos-register.md:594-604), so F7 is the one writer of a
service's policy; infra-provisioning models no service bindings (its TODO, "Cloud Run services …
remain UNMODELLED").

## Answers written as spec

- **Where it runs (owner question, 2026-10-23).** Both the public grant and the domain mapping run
  from the org's `project` repo, not from the service repo. The register `repos.yaml` lives there,
  F7 runs there under environment `repo-admin`, and the domain mapper identity admits only that
  environment. A service repo deploys its code and can never change who may call its service.
- **Q2 (owner, 2026-10-23).** deploy-cloud-run checks the real result: when `deploy_flags` contains
  `--allow-unauthenticated`, after the deploy it reads the service's IAM policy and fails unless
  `allUsers` holds `roles/run.invoker`. It never greps gcloud's wording.
- **Q1 (owner, 2026-10-23).** When a service holds `allUsers → roles/run.invoker` but its register
  entry has no `public: true`, F7 never removes the grant. It emits a `drift` action
  (`would: "remove-public-invoker"`, in every mode) saying the service is public but the register
  says private, and a person removes the grant. F7 keeps its rule that it never removes anything.
  The fetch step already reads the service policy, so no new read is needed.

## Order — docs → red tests → implement

Worktree `.worktrees/rw-public-invoker`, branch `feat/public-invoker` from main `7667c74`.

1. **Docs** (`docs/repos-register.md` §3 deploys, F7 rules, "which feature reads which key",
   action-verb table; `docs/repos-deploy-scope.md` table row; `docs/deploy-cloud-run.md` — public
   services are made public by F7, and the read-back failure + its fix; schema
   `schemas/repos.v1.json` cloud_run branch gains `public: {const: true}` like `env_secret`).
2. **Red tests**, failures pasted:
   - `tests/run_repos_deploy_plan_tests.py`: `public: true` + no invoker → one
     `add-resource-binding` (run.invoker, allUsers); already held → nothing; absent `public` →
     never an allUsers binding; gated by `ready` like the other bindings; report mode → `drift`;
     Q1 case: no `public` while allUsers holds run.invoker → one `drift` (`would:
     remove-public-invoker`) in enforce AND report, and no write verb. The existing invariant test
     bans "public"/"remove" in VERB names; the `drift` verb is unaffected (the word is in `would`). Keep `unknown_keys_are_ignored` passing.
   - `tests/run_repos_apply_step_tests.py`: allow-list accepts exactly `run.service` +
     `roles/run.invoker` + `allUsers`; refuses `allAuthenticatedUsers`, `allUsers` with any other
     role, `allUsers` on a GAR repository.
   - `tests/run_deploy_env_tests.py`: flag present + policy has allUsers invoker → pass; flag
     present + policy lacks it → fail with a message naming F7 `public: true`; flag absent → no
     read; get-iam-policy error → fail (never pass on an unreadable policy).
3. **Implement**: `scripts/repos_deploy_plan.py` (one more `bind()` when `public`);
   `repos-deploy-scope.yml` apply allow-list (:206-212) gains the one exact invoker shape;
   `deploy-cloud-run.yml` "Deploy to Cloud Run" step (:616-676) gains a read-back after `"$@"`
   (or a following step), `shell: bash`, inputs via env.
4. RCA for the silent green (bug-fix-rca) + DECISIONS entry (why F7 owns it, why read-back, Q1).
5. `make ci`; critic review; fixes; ship: PR → merge → stamp v5.1.0 → release → ls-remote tag →
   read at tag. Then message consumer B the adoption steps (bump pins, `public: true` on its
   service, re-run F7 from project, drop `--allow-unauthenticated` from deploy_flags or keep it
   as a check, re-check `/.well-known/alive` 200).
6. Renumber rotate-external-secret's plan to v5.2.0; resume its critic fixes.

## Verification

- `make ci` green locally (promtool download permitting) and in CI.
- At the tag: F7 plan for a `public: true` fixture emits the invoker binding; deploy-cloud-run
  fails in the stubbed "policy lacks invoker" case.
- Live proof is consumer B's: F7 run shows the binding applied; `get-iam-policy` on its service
  shows `allUsers roles/run.invoker`; `/.well-known/alive` returns 200.
