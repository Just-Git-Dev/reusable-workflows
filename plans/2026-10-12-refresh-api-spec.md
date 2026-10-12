# Plan — `refresh-api-spec` composite action (reusable-workflows, next minor v3.2.0)

## Decision summary (one screen)

- **What:** a composite action `actions/refresh-api-spec/` that a consumer repo calls from its own
  scheduled workflow (QA plan **K4 path (b)**). It fetches a provider's published OpenAPI document
  from a URL the repo configures, compares it with the committed copy, and if it changed: writes
  the copy, runs the repo's checks, pushes one fixed branch, opens (or updates) one PR, and
  **merges it if the checks passed** — otherwise leaves the PR open and **fails the run** (GitHub
  emails the owner).
- **Why a composite action, not a reusable workflow:** the checks need the consumer's own toolchain
  (node / go) and its `npm ci`. A composite action runs inside the caller's job after the caller's
  own setup steps; a reusable workflow would have to re-implement every repo's setup. Same pattern
  as `check-release-gate`. (K4 text says "shared workflow" — reworded to "shared action".)
- **No cross-repo access:** it reads one HTTP URL and writes only to the calling repo, using the
  caller's built-in `GITHUB_TOKEN`.
- **Compares by meaning, not bytes:** GoFr serves JSON; a copy may be YAML. Both are parsed and
  compared as canonical JSON (`yq`, preinstalled on GitHub's Ubuntu runners), and the copy is
  written back in its own format.
- **Refuses a non-spec response:** GoFr's catch-all `/.well-known/{name}` returns the Swagger UI
  HTML page with a 200. The action fails unless the body parses and has a top-level `openapi` or
  `swagger` key — a wrong URL is a red run, never a merged HTML "spec".
- **Release:** v3.2.0 (adds an action = minor), cut only on the owner's explicit ask.
- **Caller prerequisites (documented, not enforced):** a real contract check exists (else auto-merge
  is vacuous — K4); repo setting "Allow GitHub Actions to create and approve pull requests" ON; no
  required-status-check rule on the default branch (PRs opened by `GITHUB_TOKEN` trigger no CI, so
  a required check would never report and block the merge).

## Context

Owner rulings 2026-10-12 (QA plan K4 rewritten, K5, P6 amended; claude-config e1fe83b): each
consumer keeps a committed copy of each provider's API definition; each repo chooses to refresh it
by hand (path a) or by a scheduled fetch from a configured URL with auto-merge (path b); no service
repo reads another repo. devops builds the shared piece for path (b). Consumer A adopts first (its ui
has copies under `web/src/mocks/vendor/` but no contract check yet — that check is consumer A's
prerequisite, not this plan's).

## Contract (`actions/refresh-api-spec/action.yml`)

| input | required | meaning |
|---|---|---|
| `name` | yes | short id, e.g. `api`; branch is `spec-refresh/<name>`, PR title `chore: refresh <name> API spec` |
| `url` | yes | where the provider publishes its document (any environment) |
| `copy_path` | yes | the committed copy; format taken from the extension (`.json` / `.yaml` / `.yml`) |
| `check_command` | yes | the repo's checks, run after the copy is written (e.g. `npm run check:contract && npm test`) |
| `update_command` | no | runs after writing the copy, before checks — regenerate types, rewrite a provenance file |
| `request_headers` | no | newline-separated headers (e.g. an access token for a protected stage); masked |
| `merge_method` | no | `squash` (default) / `merge` / `rebase` |
| `token` | no | defaults to `github.token` |

Outputs: `changed` (`true`/`false`), `pr_url`, `checks` (`passed`/`failed`/`skipped`).

## Logic (`actions/refresh-api-spec/refresh.sh`, bash + curl + yq + gh)

1. Fetch with `curl -sS -w '%{http_code}'`; fail unless HTTP 200 and a non-empty body. Print the
   URL host (not the headers) and byte count.
2. Parse the body as JSON-or-YAML with `yq`; fail "not an OpenAPI document" unless it has top-level
   `openapi` or `swagger`.
3. Canonicalise both (sorted keys, compact JSON) and compare. Equal → `changed=false`, exit 0. If an
   open `spec-refresh/<name>` PR exists while equal, leave it and print a notice (no auto-close).
4. Write the fetched document to `copy_path` in the copy's format; run `update_command`.
5. Commit on `spec-refresh/<name>` (from the default branch head) and force-push it — one branch,
   so repeated failures never pile up PRs.
6. Find an open PR for that branch; create it if none (`gh pr create`).
7. Run `check_command`. Pass → `gh pr merge --<method> --delete-branch`, `checks=passed`. Fail →
   comment the last 60 lines of output on the PR, `checks=failed`, exit 1.
All `run:` steps `shell: bash`; git identity `github-actions[bot]`.

## Steps (Design → Doc → Test red → Implement → Release)

1. **Doc** — `docs/refresh-api-spec.md` (purpose, the K4 two paths, caller example below, inputs,
   prerequisites, GoFr notes: path `/.well-known/openapi.json`, catch-all HTML, how a provider opts
   out); README catalog row; `DECISIONS.md` entry (why composite, why semantic compare, why fail
   on non-spec, why fixed branch). Generic wording only — no consumer names (public repo).
2. **Test (red)** — `tests/run_refresh_api_spec_tests.py`, same style as
   `run_check_release_gate_tests.py`: runs the SHIPPED script against a local `http.server` serving
   fixtures (real curl), a temp git repo with a bare remote, and a `gh` stub that logs argv. Cases:
   unchanged → no push/PR; JSON served vs YAML copy, same meaning → unchanged; changed + check pass
   → branch pushed, PR created, merged; changed + check fail → PR created, NOT merged, exit 1,
   comment posted; existing open PR → updated, not duplicated; HTTP 404 → fail; 200 HTML body →
   fail "not an OpenAPI document"; empty body → fail; `update_command` runs before checks; headers
   reach the server and never appear in the log. Every case states how many it ran; 0 = fail. Git
   calls in the test scrub `GIT_DIR`/`GIT_INDEX_FILE` (hook tripwire). Confirm red (script absent).
3. **Implement** — `action.yml` + `refresh.sh` until green; `actionlint`; SHA-pin gate unaffected
   (no third-party actions).
4. **CI** — add `python3 tests/run_refresh_api_spec_tests.py` step to `.github/workflows/ci.yml`.
5. **Ship** — branch + PR (owner merges); release v3.2.0 only on the owner's ask; then tell consumer A
   the pin.

Caller example (in the doc):
```yaml
on: { schedule: [{ cron: "17 3 * * *" }], workflow_dispatch: {} }
permissions: { contents: write, pull-requests: write }
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha>
      - uses: actions/setup-node@<sha>
        with: { node-version-file: .nvmrc }
      - run: npm ci
        shell: bash
      - uses: Just-Git-Dev/reusable-workflows/actions/refresh-api-spec@v3.2.0
        with:
          name: api
          url: ${{ vars.API_SPEC_URL }}
          copy_path: src/api/openapi.snapshot.json
          update_command: npm run api:generate
          check_command: npm run check:contract && npm test
```

## Verification

- `python3 tests/run_refresh_api_spec_tests.py` green, red first; `actionlint` clean; CI green on PR.
- Live positive control after release: consumer A's ui (once its contract check exists) dispatches the
  workflow against a URL serving a known-changed spec → PR opened and merged; against the Swagger
  UI page URL → red run "not an OpenAPI document".

## Out of scope / follow-ups

- consumer A's ui→api contract check (consumer A, prerequisite); which env each consumer A pair points at (consumer A).
- Provider-side "don't publish" (leave `static/openapi.json` out of the image / block `/.well-known/`
  at the edge) — each provider's own choice, documented only.
- Updating K4's wording "shared workflow" → "shared action" in the QA plan (devops, same PR day).
