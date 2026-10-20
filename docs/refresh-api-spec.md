# refresh-api-spec

A **composite action** (not a reusable workflow) that keeps a repo's committed copy of another
service's API definition (OpenAPI / Swagger) up to date. A consumer repo calls it from its own
scheduled workflow. On each run it:

1. fetches the provider's published document from a URL the repo configures,
2. compares it with the committed copy **by meaning**, not by bytes,
3. if it changed: writes the copy, runs the repo's own update step and checks, pushes one fixed
   branch, opens (or updates) one PR, and **merges it if the checks passed** — otherwise leaves
   the PR open with the check output as a comment and **fails the run**, so GitHub emails the
   owner.

```yaml
- uses: Just-Git-Dev/reusable-workflows/actions/refresh-api-spec@v3.8.0
```

## Why this exists

A consumer that talks to another service keeps a **copy** of that service's API definition in
its own repo, and checks its client code against the copy on every PR. That way no service repo
ever reads another repo. The copy then has to be refreshed when the provider changes. There are
two ways, and each repo picks one per provider:

- **(a) by hand** — a developer pulls the new definition, runs the checks, and opens a PR. Right
  when a new definition is effectively a new program (a CLI whose command tree is generated from
  the spec) and a human should read it.
- **(b) on a schedule** — this action. Right when the repo has a real check that fails on an
  incompatible definition, so an automatic merge is only ever a merge the check accepted.

Every repo on path (b) needs the same fetch–compare–PR–merge loop, and a copy per repo drifts.
This is the one shared body.

## Design

**A composite action, because the checks need the caller's toolchain.** The checks are the
caller's own (`npm run check:contract`, `go test ./...`). They need node or go installed and
dependencies fetched. A composite action runs as a step inside the caller's job, after the
caller's own setup steps; a reusable workflow would have to re-implement every repo's setup.

**No cross-repo access.** It reads one HTTP URL and writes only to the calling repo, with the
caller's built-in `GITHUB_TOKEN`.

**Compared by meaning.** A provider may serve JSON while the copy is YAML, or serve the same JSON
with different spacing or key order. Both sides are parsed with `yq` and compared as canonical
JSON (keys sorted, no whitespace). Only a real change produces a commit; the copy is written back
in its own format (taken from the file extension), so a format difference alone never churns it.

**Refuses anything that is not a spec.** A wrong URL often still answers 200 — GoFr's catch-all
`/.well-known/{name}` serves the Swagger UI HTML page. The action fails unless the HTTP status is
200, the body is non-empty, and it parses to a mapping with a top-level `openapi` or `swagger`
key. A wrong URL is a red run, never a merged HTML "spec".

**One fixed branch, one PR.** The branch is always `spec-refresh/<name>` and is force-pushed
from the default branch's head. A refresh that keeps failing updates the same PR instead of
piling up new ones. When the provider's document goes back to matching the copy, an open PR is
left alone with a notice — closing it is a human call.

**Starts from a clean tree, on the default branch.** The action commits everything the update
step changed (`git add -A`), so it refuses to start if the working tree already has changes, and
it refuses to run on a checkout that is not the default branch's head — otherwise the PR would
carry unrelated commits or files.

## Inputs

| input | required | meaning |
|---|---|---|
| `name` | yes | Short id, e.g. `api`. Branch `spec-refresh/<name>`, PR title `chore: refresh <name> API spec`. Letters, digits, `.`, `_`, `-`. |
| `url` | yes | Where the provider publishes its document. |
| `copy_path` | yes | The committed copy, relative to the repo root. Format from the extension: `.json`, `.yaml` or `.yml`. May not exist yet (first adoption). |
| `check_command` | yes | The repo's checks, run after the copy is written, e.g. `npm run check:contract && npm test`. |
| `update_command` | no | Runs after the copy is written and before the checks — regenerate types, rewrite a pin or provenance file. Its changes are committed with the copy. |
| `request_headers` | no | Newline-separated `Name: value` headers, e.g. an access token for a protected environment. Take any sensitive value from a secret (`Authorization: Bearer ${{ secrets.SPEC_TOKEN }}`): the step's `env` is shown in the log header before the script runs, and only secrets are masked there. The script also masks every value; only the URL's host is printed. |
| `merge_method` | no | `squash` (default), `merge` or `rebase`. |
| `token` | no | Defaults to `github.token`. Needs `contents: write` and `pull-requests: write`. |

## Outputs

| output | meaning |
|---|---|
| `changed` | `true` if the fetched document differs in meaning from the copy, else `false`. |
| `pr_url` | The refresh PR, when one was opened or updated. |
| `checks` | `passed`, `failed`, or `skipped` (nothing changed). |

## Caller example

```yaml
name: Refresh API spec
on:
  schedule: [{ cron: "17 3 * * *" }]
  workflow_dispatch: {}
permissions:
  contents: write
  pull-requests: write
concurrency: { group: refresh-api-spec, cancel-in-progress: false }
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha>
      - uses: actions/setup-node@<sha>
        with: { node-version-file: .nvmrc }
      - run: npm ci
        shell: bash
      - uses: Just-Git-Dev/reusable-workflows/actions/refresh-api-spec@v3.8.0
        with:
          name: api
          url: ${{ vars.API_SPEC_URL }}
          copy_path: src/api/openapi.snapshot.json
          update_command: npm run api:generate
          check_command: npm run check:contract && npm test
```

One step per provider; give each a different `name`.

## Prerequisites (documented, not enforced)

- **A real contract check exists.** `check_command` must fail when the client code no longer
  matches the definition. Without one, an automatic merge proves nothing — use path (a) instead.
- **Repo setting "Allow GitHub Actions to create and approve pull requests" is ON** (Settings →
  Actions → General). Without it `gh pr create` is refused.
- **No required status check on the default branch.** A PR opened with `GITHUB_TOKEN` triggers
  no workflows, so a required check would never report and the merge is blocked. The action's own
  `check_command` is the check. A rule that requires a review blocks the merge the same way.
- **`actions/checkout` keeps its credentials** (the default `persist-credentials: true`), so the
  branch push works.

## Provider notes (GoFr)

- GoFr serves the document at `/.well-known/openapi.json` when the image ships
  `static/openapi.json`. Point `url` there, not at `/.well-known/swagger` (the UI page).
- Any other `/.well-known/<name>` returns the Swagger UI HTML with a 200 — the action rejects it
  as "not an OpenAPI document".
- A provider that does not want its definition public can leave `static/openapi.json` out of the
  image, or block `/.well-known/` at the edge; consumers of that provider then use path (a), or
  pass an access header via `request_headers` to a protected environment.

## Verification

`tests/run_refresh_api_spec_tests.py` runs the shipped `refresh.sh` against a local HTTP server
serving fixtures (real `curl`), a temporary git repo with a bare remote, and a `gh` stub that
logs every call. It covers: unchanged; same meaning in a different format; changed and checks
pass (pushed, PR opened, merged); changed and checks fail (PR opened, commented, not merged, run
fails); an existing PR updated rather than duplicated; HTTP 404; an HTML 200; an empty body; the
update step running before the checks; headers reaching the server and never reaching the log.

The live positive control runs after a release, in the first adopting repo: dispatch its
workflow against a URL serving a known-changed spec (PR opened and merged), and against the
Swagger UI page URL (red run, "not an OpenAPI document").
