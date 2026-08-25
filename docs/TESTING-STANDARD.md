# Testing Across Repository Boundaries

### A standard for umbrella repositories and the services they don't contain

---

## 0. Who this is for

You have a system made of several services. Each service lives in its own Git
repository — its own CI, its own release cadence, its own deploy pipeline. Somewhere
above them sits an **umbrella repository**: the place that holds the architecture
docs, the decision log, the shared infrastructure config, and — sooner or later — the
end-to-end tests, because nowhere else can hold them.

The umbrella repo has a defining property:

> **It gates code it does not contain.**

Its working tree has an `api/` directory, a `ui/` directory, a `worker/` directory —
and every one of them is in `.gitignore`. They are sibling clones on a developer's
laptop and `actions/checkout` targets in CI. The umbrella owns the *test*; another
repo owns the *code under test*; and the commit that would break the test lands in
neither of them at the same time.

This document is the standard we arrived at for that shape. It is organised as ten
principles, a reference implementation, and an adoption scorecard. Every principle
exists because its absence produced a real, expensive, and — this is the part worth
your attention — *silent* failure.

---

## 1. The failure mode that defines this problem

Distributed testing has an obvious failure mode and a subtle one.

The obvious one is the flaky test: it goes red when nothing is wrong, you learn to
ignore it, and eventually it goes red when something *is* wrong and you ignore that
too. Everyone knows about flaky tests.

The subtle one is worse, and it is endemic to cross-repository testing:

> **The gate that is green because it never ran.**

A flaky test at least announces itself. A gate that silently does nothing looks
*exactly* like a gate that passes. It appears in the checks list. It has a green tick.
It has a duration. It contributes to your confidence at code review. And it has never,
in its entire life, executed a single assertion against the thing it claims to
protect.

We have now seen this defect arrive by **six independent mechanisms**. They are worth
enumerating precisely, because the mitigations are different for each and because once
you know the shapes you start seeing them everywhere.

### 1.1 The unprovisioned-secret fallback

A cross-repo checkout needs a credential. The author, sensibly, writes a fallback: *if
the deploy key isn't configured, do the cheap local approximation instead.* The
credential is then never provisioned — nobody notices, because the job is green — and
the fallback path is the **only path that ever executes**. The gate ships, runs for
months, catches nothing.

The tell: a conditional in a gate whose false branch still exits zero.

### 1.2 The conditional skip on a missing fixture

A test reads a config file from a sibling repo. If the file isn't there, the test
`skip`s — defensive, reasonable-looking. In the containerised run the mount path is
different, the file is never there, and every spec in the suite skips. The summary
line says `12 skipped`, which nobody reads, and the job is green.

The tell: `skip()` conditioned on the *presence of an input* rather than on a property
of the environment you deliberately support.

### 1.3 The gate that only runs where nobody looks

The unit tests exist. They are wired into exactly one workflow: the **deploy**
workflow, on a tag — that is, *after* merge, *after* review, *after* the version was
cut. For the entire pre-merge lifecycle of every change, nothing ran them. The repo
had tests and had no test gate, and the difference was invisible from the checks list
because there was no check to be missing.

The tell: `grep` your workflows for the test command. Count the call sites. If the
answer is one and that one is a deploy or release workflow, you have this.

### 1.4 The dispatch-only workflow that is never dispatched

A `workflow_dispatch`-only one-shot — a bootstrap, a rotation, a migration — points at
a script path that does not exist. It is never exercised by accident, because that is
what dispatch-only *means*. The defect sits in `main`, reviewed and merged, until the
day someone needs the thing to work, which is by definition a day when something is
already going wrong.

The tell: any workflow with no automatic trigger. It needs a *static* check standing
in for the run it never gets.

### 1.5 The stale image

The suite runs in containers. `compose up` builds only when the image tag is
**absent**, so the second and every subsequent invocation silently reuses whatever
image the last run left behind. You edit code, run the suite, and test the previous
binary. This one is not silent-green — it is worse, it is *silent-anything*: it will
happily report red for a bug you already fixed, or green for code you never built.

The tell: any harness where the build step and the run step are separable, and the run
step is the one people invoke while iterating.

### 1.6 The skip that means two different things

A test suite reports `41 skipped` on every run. Some of those are "not applicable to
this viewport, by design." Others are "should have run, and did not." **In a summary
line these are indistinguishable**, so the population of genuine failures hides inside
the population of deliberate exclusions, and the number is large enough that nobody
audits it.

The tell: a nonzero, *stable* skip count. Stable skips are conventions, and
conventions belong in configuration, not in runtime control flow.

### 1.7 What they have in common

Every one of these is a gate **degrading instead of failing**. The author wrote a
graceful path for a condition they expected to be temporary, and the temporary
condition became permanent because gracefulness removed the pressure to fix it.

That gives us the first and most important principle.

---

## 2. The ten principles

### Principle 1 — A gate that cannot do its job must go red

> **No fallback. No skip. No degrade. If a gate cannot fetch, mount, build, or reach
> what it exists to test, it fails.**

This is non-negotiable and it is the principle from which most of the others follow.

Concretely:

- **Missing credential → fail.** Check for it explicitly, in a first step, with an
  error message that says what to provision and where. Do not let a checkout failure
  three steps later be the diagnostic.
- **Missing fixture → fail.** A test whose input is absent has not passed.
- **Missing sibling checkout → fail.** With a message naming the repo and the clone
  command.
- **Never `|| true` a gate.** (`|| true` on a *`grep` that legitimately matches
  nothing* is fine and often necessary under `pipefail` — that is control flow, not a
  gate. Know which one you are writing.)

The counter-argument is always "but then CI breaks for people who haven't set it up."
Correct. That is the mechanism by which it gets set up. A gate measuring nothing while
showing green is strictly worse than a gate that is loudly broken, because the second
one gets fixed.

A useful phrasing to put in the error message itself:

> *Provision the credential rather than removing this step — a suite that cannot check
> out what it tests must go red, not degrade quietly.*

### Principle 2 — The SUT-span rule: a test is gated by the repo that spans its system under test

> **A test belongs in — and is gated by — the smallest repository that contains
> everything it exercises.**

This is the rule that decides what the umbrella owns.

- A test that touches **one service** belongs in that service's repo, gated by that
  repo's CI. Code and test land in the same commit. No cross-checkout, no ref pinning,
  no coordination.
- A test that touches **more than one repo** belongs in the umbrella, gated by the
  umbrella's CI. This is the *only* category the umbrella should own.

The failure this prevents is subtle: an integration suite that lives in the umbrella
but exercises exactly one service. It looks harmless, and it costs you the single most
valuable property in testing — **the ability to change code and its test in one
atomic commit**. Instead you get a two-repo dance, a `SERVICE_REF` pin, a window where
the umbrella's main is red through no fault of its own, and a strong incentive for
everyone to stop running the suite.

Apply the rule aggressively. Most suites that live in an umbrella do not belong there.
Moving one *down* into its service repo is almost always a net win: it gets faster, it
gets atomic, and it gets run.

### Principle 3 — One stack driver, no forks

> **The compose stack has exactly one driver script. Repos that need a different
> composition consume it through a thin shim, never a copy.**

The base stack (database, cache, the core service) is owned by whichever repo owns the
core service. That repo holds `test/support/stack.sh` and
`test/docker-compose.test.yml`. The umbrella needs a *bigger* stack — the core service
plus a BFF plus a web tier plus a browser runner. It gets it two ways, both of which
avoid duplication:

1. **Compose `include:`** — the umbrella's compose file `include:`s the base file and
   adds services. One definition of every shared service, ever.
2. **A shim script** — the umbrella's `tests/support/stack.sh` is fifteen lines: it
   locates the real driver in the sibling checkout, points `COMPOSE_FILE` at the
   umbrella's overlay, and `exec`s it with every argument forwarded.

The shim should say so in its own header, loudly:

```bash
# stack.sh — SHIM. The real driver lives in <core-service>/test/support/stack.sh.
# Do NOT re-implement stack logic here; fix it upstream.
```

The alternative — two copies of the driver — fails the way all duplicated
infrastructure fails: they drift, the second one rots, and a fix applied to one is
invisible in the other. Except worse than usual, because the symptom is a *test
environment* discrepancy, which presents as a flaky test rather than as a bug.

**Corollary — the driver, not the workflow, is the interface.** If your CI workflow
contains a bare `docker compose -f tests/e2e/docker-compose.yml run --rm e2e`, then
your *workflow YAML* is your stack driver, and it is one you cannot run locally. Every
lesson learned in CI has to be re-learned on the laptop. Put the logic in the script;
let the workflow call the script.

### Principle 4 — Container-native by default; host ports only as a CI overlay

> **The local stack binds no host ports. CI, which has no reverse proxy, re-adds them
> through an overlay compose file.**

Local development runs behind a shared reverse proxy on stable hostnames. Nothing
binds `127.0.0.1:5432`, including the datastores — you reach a containerised Postgres
with an ephemeral container joined to the compose network, and you run the test suite
there too. This keeps parallel stacks from colliding on ports and keeps the test
environment honest about service discovery.

CI runners have no such proxy. The naive resolutions are both bad: bind host ports
everywhere (and lose the property locally), or stand up a proxy in CI (and maintain
it). The right answer is a **layered overlay**:

```
docker-compose.test.yml    # base — no host ports, proxy hostnames
docker-compose.ci.yml      # overlay — re-adds host port bindings, nothing else
```

with the driver taking an env knob:

```bash
COMPOSE_EXTRA_FILE=docker-compose.ci.yml ./support/stack.sh up
```

The base file stays the source of truth for *what the stack is*; the overlay says only
*how CI reaches it*. Nobody has to remember to strip ports back out.

**Test datastores are throwaway.** `tmpfs` or unnamed volumes, `down -v` on exit, so
every run starts from a known-empty database. This is the one place `-v` is correct;
in a *development* stack it destroys the migration ledger and seed data and must never
be run casually.

### Principle 5 — Tier your stacks, and state what each tier cannot see

> **Every stack tier carries a written statement of the bug class it is structurally
> incapable of catching.**

A mature setup has at least two e2e tiers:

| Tier | Backend | Catches | **Structurally cannot catch** |
|---|---|---|---|
| **Mocked** | Request interception in the browser | UI logic, routing, rendering, empty/error states | Anything on the far side of the wire — contract drift, tenant leaks, auth bugs, real query behaviour |
| **Real** | Actual service + database + cache | Contract drift, isolation failures, integration bugs | Little; it is slow and heavier to keep green |

The mocked tier is fast, hermetic, and — the critical part — **asserts the UI against
fixtures the test itself wrote**. It cannot fail because the server changed, because
it never talks to a server. Left unstated, this reads as coverage. Stated plainly, it
reads as what it is: a fast tier that must be paired with a real one.

Write it in the compose file or the job comment, in those words. Future readers will
otherwise assume the green mocked suite means the integration works.

### Principle 6 — Build before you trust

> **The harness rebuilds the image under test on every invocation, unconditionally,
> exactly once.**

`compose up` builds only when the tag is missing. `compose run` reuses a running
container. Both are correct optimisations for a dev loop and wrong for a test gate,
because the person iterating on a fix is precisely the person invoking a single stage
directly, and they will be handed yesterday's binary with no indication anything is
stale.

The fix is a guarded build at the top of the harness:

```bash
APP_BUILT=0
build_app() {
  [ "$APP_BUILT" = "1" ] && return 0
  compose build app          # ONE service, not a bare `compose build`
  APP_BUILT=1
}
```

Two details that cost real debugging time to discover:

- **Build one service, not all of them.** If several services share an image tag via a
  YAML anchor, a bare `compose build` builds N identical images concurrently and they
  race to export the same tag: `failed to solve: image ... already exists`, which
  fails the gate before a test runs. Build the one service; the others consume it.
- **In CI, pass `--build` explicitly** (`compose run --rm --build e2e`). Bare `run`
  will happily attach to an already-running container serving the previous build's
  bundle.

### Principle 7 — Exclude, don't skip

> **A test that does not apply to a configuration is not *in* that configuration.**

If a suite runs under multiple projects — desktop and mobile viewports, two auth
modes, two backends — express inapplicability as **test selection** (`testMatch`,
`testIgnore`, a tag filter, a build tag), never as a runtime `skip`.

The reason is Principle 1 wearing a different hat. A skip and a failure-to-run are
indistinguishable in a summary line. A suite reporting a stable `41 skipped` has
trained everyone reading it to ignore the skip count, which is where the *real*
skipped test will hide.

Target: **the skip count is zero, or every skip is individually justified in review.**

### Principle 8 — Pin what you run; pin what you test, deliberately

Two separate pinning problems, routinely conflated.

**Pin what you run** — third-party actions, to full commit SHAs, with the version in a
trailing comment:

```yaml
- uses: some-org/some-action@3d39aea434753780c3b3d4a1a31c854b4dbf49d7 # v2.2.0
```

A moved tag is a supply-chain event. It is tempting to exempt test workflows on the
grounds that they mint no cloud credentials — but they check out every one of your
private repos and execute arbitrary build steps over the result. If you decide to
exempt them anyway, **write the exemption down**; the common state of the world is not
a decision but an oversight that a lint rule would have caught.

**Pin what you test** — sibling repo refs. Default to each sibling's `main` so the
gate tracks reality:

```yaml
env:
  API_REF: ${{ vars.API_REF || 'main' }}
  UI_REF:  ${{ vars.UI_REF  || 'main' }}
```

Using repository *variables* rather than hardcoded values buys you the release
cutover: when the umbrella's tests require unreleased sibling behaviour, pin the
variables to the release SHAs for the duration of the window, then clear them back to
`main`. Without this you get a genuinely nasty property — **a push to a sibling's main
can retroactively red-line the umbrella's main**, with no umbrella commit involved.

Whatever the refs resolve to, **echo them in the job**:

```yaml
- name: Print the refs under test
  run: |
    echo "umbrella $(git rev-parse --short HEAD)"
    echo "api      $(git -C api rev-parse --short HEAD) (${API_REF})"
    echo "ui       $(git -C ui  rev-parse --short HEAD) (${UI_REF})"
```

Ten lines of log that convert "the e2e failed" into "the e2e failed against api
`a1b2c3d`" — the difference between a bisect and a shrug.

### Principle 9 — Every gate is observable and leaves nothing behind

Four steps, on every stack-based job, no exceptions:

```yaml
- name: Stack logs on failure
  if: failure()
  run: docker compose -f <file> logs --no-color

- uses: actions/upload-artifact@<sha>
  if: failure()
  with:
    name: <suite>-report
    path: |
      tests/e2e/playwright-report
      tests/e2e/test-results
    retention-days: 14

- name: Tear down
  if: always()
  run: docker compose -f <file> down -v
```

`if: failure()` on the diagnostics, `if: always()` on the teardown. A red e2e with no
trace, no video, and no server log is not a signal, it is a rumour — and it is the
single biggest reason teams stop trusting their e2e suite.

Locally, the same discipline is a `trap`:

```bash
teardown() { "${COMPOSE[@]}" down -v >/dev/null 2>&1 || true; }
trap teardown EXIT
```

### Principle 10 — Trigger policy is a decision; record it

There is no universal right answer for *when* the umbrella suite runs, and pretending
otherwise produces cargo-culted triggers.

- **Umbrella owns real specs that change often** → run on push and PR. The suite is
  part of the repo's own feedback loop.
- **Umbrella is mostly docs and decision logs, and the code under test is entirely in
  siblings** → run on manual dispatch, plus a nightly schedule against siblings'
  `main`. Auto-running a fifteen-minute multi-repo stack on every documentation commit
  is pure waste, and the resulting noise is how a blocking gate becomes an ignored one.

Either is defensible. What is not defensible is having whichever one you have by
accident. Put the reasoning in a comment at the top of the workflow, with a date:

```yaml
# MANUAL-TRIGGER ONLY (<date>). This umbrella holds documentation plus the
# multi-repo suite; the code under test lives in sibling repos checked out at run
# time. An umbrella push is almost always a docs change with no bearing on the
# sibling code the suite exercises. Run by hand, or let the nightly schedule
# gate siblings' current main.
```

If you choose dispatch-only, you have opted into failure mode 1.4 and owe yourself the
mitigation: a **cheap always-on CI job** that statically checks what the dispatch-only
workflows can no longer check for themselves — a linter over every workflow file, and
an assertion that every script path a `run:` body invokes actually exists in the tree.
That check costs seconds and catches the class of defect that dispatch-only workflows
are uniquely prone to.

---

## 3. Reference implementation

### 3.1 The test layer cake

Five layers, each owned by exactly one repo per Principle 2:

| Layer | Lives in | Runs in CI of | Needs a stack? | Wall clock |
|---|---|---|---|---|
| **Unit** | service repo | service repo, every push/PR | no | seconds |
| **Contract** | service repo | service repo, every push/PR | no | seconds |
| **Integration** | service repo | service repo, every push/PR | yes, service-local | 1–3 min |
| **E2E (mocked)** | umbrella | umbrella | yes, no real backend | 2–5 min |
| **E2E (real)** | umbrella | umbrella | yes, full multi-repo | 8–20 min |

The **contract** layer deserves more attention than it usually gets: it is the cheapest
place to catch the most expensive class of cross-repo bug. Two gates pay for
themselves immediately:

- **Spec-drift** — the committed API spec matches what the server actually serves.
- **Version-bump** — a change to the spec requires a corresponding version bump,
  computed from the diff against the base revision.

The version-bump gate needs the base spec handed to it, because the test cannot read
git history. Which means the gate is **disabled by deleting a workflow step** — a
silent-green in waiting. Defend it in the comment:

```yaml
# Removing this step silently disables the gate: the test skips without a base
# to diff against. If it ever needs deleting, delete the test too.
```

### 3.2 File layout

```
<core-service-repo>/
  test/
    docker-compose.test.yml       # base stack — no host ports
    docker-compose.ci.yml         # overlay — host ports for CI
    support/
      stack.sh                    # THE driver. One copy in the whole system.
    integration/                  # service-spanning tests, gated here

<umbrella-repo>/
  tests/
    docker-compose.test.yml       # include:s the base, adds bff/web/runner
    support/
      stack.sh                    # SHIM → core-service driver
      factories.ts                # shared test data builders
    e2e/
      smoke/                      # mocked tier
      live/                       # real tier
      workflows/                  # multi-step user journeys, real tier
      contract/                   # static checks, no stack
      pages/                      # page objects
      fixtures/                   # auth, seed, api helpers
      playwright.config.ts
  .github/workflows/
    ci.yml                        # always-on: lint + static checks. Seconds.
    e2e.yml                       # the multi-repo gate
```

### 3.3 The `stack.sh` verb contract

Same verbs in every repo, so that knowing one harness means knowing all of them:

| Verb | Contract |
|---|---|
| `up` | Bring the stack to healthy. Idempotent. Blocks until health checks pass. |
| `down` | Stop and remove, `-v` included. Idempotent. Warns on leaked containers. |
| `seed` | Populate a fresh database; write credentials to a known env file. Idempotent. |
| `reset-data` | Truncate data tables, keep schema and stack. The fast inner loop. |
| `test [args…]` | Run the suite inside the network. Args forwarded to the runner. |
| `logs [svc]` | Tail. |
| `schema-guard` | Assert the migrated schema matches what the suite expects. |

Design notes that matter:

- **Single-source the compose project name.** The `-p` flag and any leak check must
  name the same project; two string literals will drift.
- **Env knobs, not forks:** `COMPOSE_FILE`, `COMPOSE_EXTRA_FILE`, `COMPOSE_PROFILES`.
- **Generate secrets before compose parses the file.** `env_file:` is resolved by the
  Docker CLI at parse time, so a key minted *during* `up` is invisible to the
  containers until the *next* `up` — the stack boots with a stale key and everything
  401s in a way that looks like a test bug. Generate first; mark the file
  `required: true` so a bare `docker compose up` fails loudly instead of booting
  wrong.
- **Every `run:` block declares `shell: bash`.** The implicit default omits
  `pipefail`, so a failure mid-pipe is invisible.

### 3.4 Multi-repo job skeleton

```yaml
jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      HAS_KEY: ${{ secrets.SERVICE_CHECKOUT_KEY != '' && 'yes' || 'no' }}
    steps:
      # P1 — fail loud, first, with an actionable message
      - name: Fail if a cross-repo checkout credential is missing
        if: env.HAS_KEY != 'yes'
        run: |
          echo "::error title=E2E cannot run::SERVICE_CHECKOUT_KEY is not provisioned.
          Provision it rather than removing this step — a suite that cannot check out
          what it tests must go red."
          exit 1

      # Checkout layout is load-bearing: compose reaches services at ../../<svc>
      # relative to tests/e2e, i.e. INSIDE the umbrella checkout where they are
      # gitignored. Checking a service out at the workspace root instead silently
      # leaves the build context missing.
      - uses: actions/checkout@<sha>
        with: { path: project }
      - uses: actions/checkout@<sha>
        with:
          repository: <org>/<service>
          path: project/<service>
          ref: ${{ env.SERVICE_REF }}
          ssh-key: ${{ secrets.SERVICE_CHECKOUT_KEY }}

      - name: Print the refs under test        # P8
        working-directory: project
        run: |
          echo "umbrella $(git rev-parse --short HEAD)"
          echo "service  $(git -C <service> rev-parse --short HEAD) (${SERVICE_REF})"

      - name: Run the suite                    # P3 + P6 (--build, via the driver)
        working-directory: project
        run: ./tests/support/stack.sh test

      - name: Stack logs on failure            # P9
        if: failure()
        working-directory: project
        run: ./tests/support/stack.sh logs

      - uses: actions/upload-artifact@<sha>    # P9
        if: failure()
        with:
          name: e2e-report
          path: project/tests/e2e/playwright-report
          retention-days: 14

      - name: Tear down                        # P9
        if: always()
        working-directory: project
        run: ./tests/support/stack.sh down
```

### 3.5 Cross-repo checkout credentials

Three options, in increasing order of scalability:

| Mechanism | Good for | Cost |
|---|---|---|
| **Per-repo deploy key** (read-only) | 2–3 siblings | One secret *per pair*; N×M rotation |
| **Fine-grained PAT**, `contents: read` on the named repos | 3–6 siblings, one org | One secret; but it is *somebody's* token and it expires |
| **Org-reader GitHub App**, short-lived installation token | many consumers of many providers | Setup cost once, then free; no expiry surprises |

Deploy keys are the right first move and the wrong tenth. The migration trigger is
when rotation becomes a chore, or when a *person* leaving would break CI — a PAT tied
to an individual is a bus factor of one hiding inside your pipeline.

Whichever you choose, Principle 1 applies to all three: check for presence explicitly,
fail loudly, name what to provision.

---

## 4. Adoption scorecard

Score honestly. Every "no" is a gate you cannot currently trust.

**Silent-green defence**
- [ ] No gate has a fallback path that exits zero when its input is missing
- [ ] No test `skip`s on the absence of a fixture, mount, or credential
- [ ] Every test command has a call site on push/PR, not only on tag or deploy
- [ ] Dispatch-only workflows are covered by an always-on static check
- [ ] The skip count is zero, or every skip is justified in review
- [ ] The harness rebuilds the image under test on every invocation

**Ownership**
- [ ] Every suite lives in the smallest repo containing its system under test
- [ ] No suite in the umbrella exercises only one repo
- [ ] There is exactly one stack driver; other repos consume it via a shim
- [ ] There is exactly one definition of each shared compose service

**Environment**
- [ ] The local stack binds no host ports, datastores included
- [ ] CI gets its ports from an overlay, not from edits to the base file
- [ ] Test datastores are throwaway and torn down with `-v` on exit
- [ ] Secrets are generated *before* compose parses the file

**Observability**
- [ ] Every stack job echoes the resolved sibling refs
- [ ] Stack logs are dumped on failure
- [ ] Reports and traces are uploaded on failure with a retention period
- [ ] Teardown runs on `always()`

**Pinning**
- [ ] Third-party actions are SHA-pinned — or the exemption is written down
- [ ] Sibling refs default to `main` and are pinnable via repository variables

**Layers**
- [ ] Unit + contract + integration run in each service repo on every PR
- [ ] The umbrella owns a mocked tier and a real tier
- [ ] Each tier states, in writing, the bug class it cannot catch
- [ ] A contract spec-drift gate exists
- [ ] A contract version-bump gate exists and is defended by a comment

---

## 5. Anti-pattern quick reference

| Smell | Why it's dangerous | Fix |
|---|---|---|
| `if [ -f "$X" ]; then … else <cheap approximation> fi` in a gate | The else branch becomes the only branch | Fail |
| `test.skip(!fs.existsSync(f))` | Green in every environment that lacks `f` | Fail |
| `npm test` appearing only in `deploy.yml` | No pre-merge gate exists at all | Add a push/PR job |
| `workflow_dispatch:` with no other trigger and no static check | Rots undetected until needed | Always-on lint + path check |
| `compose run` without `--build` | Tests the previous build | `--build`, or build in the driver |
| Bare `compose build` with shared image tags | Concurrent tag export race | Build one service |
| `\|\| true` on a gate command | Unconditional pass | Remove; keep only on genuinely-empty `grep` |
| Stable nonzero skip count | Real skips hide among conventional ones | Convert to `testIgnore` / project selection |
| `docker compose …` inline in workflow YAML | The workflow *is* the driver; unrunnable locally | Move into `stack.sh` |
| Two copies of the stack script | Drift presenting as flakiness | Shim + `include:` |
| Host port bindings "just for dev" | Collisions; dishonest service discovery | Overlay for CI only |
| Sibling refs unpinned during a release cutover | A sibling push retroactively reds your main | Repository variables |
| E2E red with no artifacts | Rumour, not signal | `if: failure()` upload |

---

## 6. The shortest version

If you remember one sentence from this document, make it the first principle, because
every other item here is a specific instance of it:

> **A gate that cannot do its job must go red.**

Everything else — the single driver, the overlay, the tiering, the ref echo, the
unconditional rebuild — is machinery for making sure that when something is broken,
you find out.
