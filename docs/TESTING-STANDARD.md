# Testing Across Repository Boundaries

### A standard for umbrella repositories and the services they don't contain

> **Source of truth: the `testing` skill.** The general rules — the tiers, the placement
> rule, seed data, skips, guards, caches — live there and are maintained there. This
> document is the **umbrella-repo application** of that skill: the failure modes that only
> appear when a gate spans repositories it does not contain, and the machinery for them.
> Where a principle below is the skill's rule wearing a cross-repo hat, it says so and
> cites the section. **Nothing here overrides the skill.** If the two ever disagree, the
> skill is right and this file has a bug — fix it here, not there.

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

This document is the standard we arrived at for that shape — we call that top repo the **root
repo** (earlier drafts said *umbrella*; the two words mean the same thing). It is organised as
eleven principles, a reference implementation, and an adoption scorecard. Every principle exists
because its absence produced a real, expensive, and — this is the part worth your attention —
*silent* failure.

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

We have now seen this defect arrive by **seven independent mechanisms**. They are worth
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

### 1.7 The guard that is inert in CI and alive on a laptop

A guard in repo A asserts something about repo B — every handler struct has an E2E spec,
every route has a UI reference. It resolves the sibling by relative path
(`"$ROOT/../<sibling>/e2e"`), and when that directory is absent it prints a friendly note and
exits zero. Locally the sibling *is* checked out, so it works, and the author sees it
work. In CI nothing checks out the sibling, so it takes the skip branch on every run it
has ever had.

The tell is not in the script — it is that **the ADR and the contributor README both
describe it as a CI gate.** Documentation asserting a gate that does not exist is the
most expensive version of this failure, because the documentation is the reason nobody
checks. For each guard, name the CI job that can actually see *both* sides. In a service
repo there is none by design — service repos never check out each other (Principle 2) —
so the guard must be redesigned to run in the repo it inspects, moved to the root repo,
or labelled local-only in the docs. If you cannot do one of the three, the guard is
decoration.

See the skill's §0.4 (repo guards) for the general rule.

### 1.8 What they have in common

Every one of these is a gate **degrading instead of failing**. The author wrote a
graceful path for a condition they expected to be temporary, and the temporary
condition became permanent because gracefulness removed the pressure to fix it.

That gives us the first and most important principle.

---

## 2. The eleven principles

### Principle 1 — A gate that cannot do its job must go red

*Skill §9 (local/CI parity — a conditional check fails closed). This is that rule, and this document exists because cross-repo gates break it more than any other kind.*

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

*Now stated generally in skill §0 — the umbrella-owns-E2E rule is a consequence of it, not the rule. What follows is how it lands when the siblings are separate repos.*

> **A test belongs in — and is gated by — the smallest repository that contains
> everything it exercises.**

This is the rule that decides what the umbrella owns.

- A test that touches **one service** belongs in that service's repo, gated by that
  repo's CI. Code and test land in the same commit. No cross-checkout, no ref pinning,
  no coordination.
- A test that touches **more than one repo** belongs in the umbrella, gated by the
  umbrella's CI. This is the *only* category the umbrella should own.

The rule cuts both ways. **A service repo's tests never depend on another repo** — no
sibling checkout, no reading another repo's `main`, no peer image to test against. Each
business rule is proven once, in the service that owns it, with that service's own
datastores real and every service it calls replaced by a stand-in (Principle 5). A
consumer checks its calls against **its own committed copy** of the provider's API
definition; refreshing the copy is an ordinary pull request on the consumer. The root
repo is the only repo that reads the others — with a read-only GitHub App, or by pulling
the built images (preferred: they are exactly what deploys). Importing a private library
is a build dependency, not a cross-repo test, and is outside this rule.

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

*Skill §0 (one driver, no forks) carries the general rule, including its sharpest form: a fork's cost is that a fix reaches only the copy that found the bug, while the un-fixed copy's suite goes on certifying the old behaviour. It also covers the case this section does not — copies that are **structurally forced** (a git hook, a compose `command:` and a CI `run:` cannot reference each other), where the answer is a guard asserting they agree, not de-duplication.*

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

### Principle 4 — Container-native everywhere; the test runner joins the network

> **No stack binds host ports — not locally, not in CI. The test runner runs inside the
> compose network and reaches services by their service names.**

Local development runs behind a shared reverse proxy on stable hostnames. Nothing
binds `127.0.0.1:5432`, including the datastores — you reach a containerised Postgres
with an ephemeral container joined to the compose network, and you run the test suite
there too. This keeps parallel stacks from colliding on ports and keeps the test
environment honest about service discovery.

CI runners have no such proxy, and they do not need one: the runner is a container in
the same compose network (`stack.sh test` already runs "inside the network", §3.3).
The tempting alternative — an overlay file that re-adds host ports for CI — means CI
reaches the stack a different way than the laptop does, and the ports leak back into
local use the first time someone runs with the overlay "just to debug". If a CI job
truly needs a proxy hostname (cookie domain, TLS), run the proxy as one more service in
the same compose file; still no host ports.

**Test datastores are throwaway.** `tmpfs` or unnamed volumes, `down -v` on exit, so
every run starts from a known-empty database. This is the one place `-v` is correct;
in a *development* stack it destroys the migration ledger and seed data and must never
be run casually.

### Principle 5 — Tier your stacks, say what stands in for what, and state what each tier cannot see

*Skill §0 (tiers) and §8 (what stands in for what).*

> **Every stack tier carries a written statement of the bug class it is structurally
> incapable of catching.**

| Tier | Lives in | Backend | Catches | **Structurally cannot catch** |
|---|---|---|---|---|
| **Integration** | each service repo | the service + its own real datastores; every other service injected as a stand-in | every business rule the service owns | whether the stand-ins tell the truth; whether the pieces connect |
| **Mocked browser** | the UI repo | request interception; replies **generated from the provider's API definition** | UI logic, routing, rendering, empty/error states | anything on the far side of the wire — whether the server implements the definition, tenant leaks, real query behaviour |
| **End-to-end** | the root repo only | every service at a chosen version + real datastores | "do the pieces connect", contract drift between real services | little; slow, so depth is chosen by tag (`smoke`, `full`) rather than by deleting tests |

**What stands in for what.** A service's own datastores are always real. A service you own is
replaced, at the integration tier, by a stand-in **generated from its API definition**; where
that is not enough, the service being imitated **publishes a hand-written fake and proves it
faithful in its own CI**, running one set of conformance cases against both the real service and
the fake. Consumers use the published fake and never write their own. A service you **do not**
own sits behind one adapter in your code, with a fake of that adapter for every pull request;
the fake and the real checks share one case list. Real checks run in the root repo's end-to-end
suite **where the outside service offers a test account or test mode with no real side effects**;
where it does not, it stays a fake (built from recordings of the real system if no sandbox
exists).

The same integration suite can be pointed at the actual services instead of stand-ins — the
test code does not change, only the injected target. That is not a CI job: its purpose is to
find **gaps in the stand-in**, and a gap found is fixed in the provider's fake and added to its
conformance cases, so the provider's CI catches it from then on.

Write each tier's blind spot in the compose file or the job comment, in those words. Future
readers will otherwise assume the green mocked suite means the integration works.

### Principle 6 — Build before you trust

*Skill §11. The same family of failure one layer down is the **test-result cache** — skill §11.2: a suite can truncate and re-seed its entire database and the very next run will report `ok (cached)`, because the database is outside the cache key. Rebuilding the image does not save you from that; bypassing the result cache does.*

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

*Skill §14, which now also carries the **skip taxonomy** — classify a skip by its predicate, not its reason string. The dangerous one for an umbrella: a skip guarded by the test's own precondition (`if len(subjects) < 2`), which fires exactly when the test was valuable.*

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

**Pin what you test** — the service versions. The root repo's pre-release run tests a
**chosen set of release candidates** (service tags) with **every other service at its
current live version**. Never default to a service's `main`: a push to a service's main
would then retroactively red-line the root repo with no root commit involved, and the run
would test something nobody is about to ship.

**Keep an append-only release log in the root repo.** Every release pull request adds one
new file naming the versions it releases; files are never edited or deleted. "Live", for
each service, is the **most recent log entry that names it**, read from git. Do not use the
forge's "latest release": it is ordered by when a release was created, not by version, so a
re-published old release would read as live. The log is also your release history.

```yaml
# releases/2026-10-07-1.yml — added by the release PR; merging it starts the release run.
# Providers first: Releases are published in this order.
api: v1.4.0
web: v2.0.1        # every service not listed runs at its last logged version
```

Whatever the versions resolve to, **echo them in the job**:

```yaml
- name: Print the versions under test
  shell: bash
  run: |
    echo "root     $(git rev-parse --short HEAD)"
    echo "api      ${API_VERSION}  (candidate | live)"
    echo "web      ${WEB_VERSION}  (candidate | live)"
```

Ten lines of log that convert "the e2e failed" into "the e2e failed against api
`v1.4.0`" — the difference between a bisect and a shrug.

### Principle 9 — Every gate is observable and leaves nothing behind

*Skill §10 (failure artifacts) and §11.1 (teardown).*

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

There is no universal right answer for *when* the root repo's suite runs, and pretending
otherwise produces cargo-culted triggers. The reference fleet's choice is described below.
Whatever you choose, record it with its reason. The valid options:

- **On a merged release pull request** (the reference fleet's gate, described below).
- **By hand** (`workflow_dispatch`), for the full tag set, or to run a red release again.
- **On a schedule** (e.g. a nightly full run against the last logged versions). This is a
  valid option, and it catches outside-service drift sooner. **It is not used by the
  reference fleet**, which accepts noticing that drift at the next release instead.
- **On the root repo's own push and PR** — only if the root repo itself owns real specs
  that change often. A root push that is almost always a docs change should not start a
  fifteen-minute multi-repo stack.

**The release gate.** A release starts as a pull request in the root repo that **adds one
new file to an append-only release log** (Principle 8), naming the service tags to
release (the *candidates*), providers before consumers. Review happens on that PR, so
every release leaves a reviewed record. Merging it starts the run. In order, and each step
stops the release on red:
  1. **Contract re-check.** Run each consumer's own contract check against the provider's
     API definition **at the version being released**, instead of against the consumer's
     committed copy. Any call or fixture that no longer matches fails the release, naming
     the consumer, the call and the file. (A consumer's own check proves only "my code
     matches my copy"; this is the one place that proves the copy is still true.) It does
     not compare definition files, so a change to an endpoint no consumer calls does not
     block — and it covers every call a consumer makes, in seconds, where `smoke` covers a
     few journeys.
  2. **`smoke`** — the end-to-end scenarios tagged `smoke`, against the candidates' exact
     images, every other service at its live version. It starts from a freshly migrated,
     empty database, so it does **not** prove a migration against live data. That stays
     each service's own pre-deploy migration check.
  3. **Create every Release as a draft.** A draft deploys nothing.
  4. **Publish them all in one pass**, in the order the log entry lists them, but only
     once every draft exists. If any earlier step fails, a red `smoke` included, **delete
     the drafts**, so nothing goes live. The workflow also has a `workflow_dispatch` trigger
     to run it again, so a flaky red can be retried without a new commit. That is the only
     retry. Don't auto-retry inside a run: it hides real intermittent bugs.

**Build once; a tag only retags.** Every push to a service's main builds one image,
labelled with its commit. A tag on a service repo means **"ready"**. First, the tag needs a
green integration run that the forge already recorded for that exact commit; if there is
none, the tag runs the suite. Then it **retags** the existing image as `vX.Y.Z`, with no
rebuild and no deploy. A laptop run never counts: the forge has no record of it. So the
images `smoke` passes are byte-for-byte the ones that deploy (see this repo's
`docs/release-process.md` and the `promote-image` workflow). When a Release is published,
the service deploys itself: migrations first, then promote the image.

**Every deploy ends up in the log.**
- A hand-started deploy may only re-deploy a version the log already records.
- A hotfix goes through a normal release pull request.
- A fast rollback (`rollback-service`) is allowed at any time, followed by a log entry
  recording what is now live.
- A multi-service release relies on expand/contract migrations (`docs/release-process.md`):
  old and new versions work against the same schema, so deploy order does not matter.

**Dependencies point one way.** Services never call the root repo. The root repo only reads
service repos and creates Releases in them.

Traps in this flow:

- **A Release created with a workflow's default `GITHUB_TOKEN` does not start other
  workflows.** Create Releases with a GitHub App token. Before relying on it, prove once
  that an App-created Release starts the service's `release: published` workflow.
- **The permission that creates Releases also allows pushing.** `contents: write` is the
  narrowest permission that can create a Release. So "the root repo never pushes" must be
  enforced: use rulesets on each service repo that let only humans push to `main` or create
  `v*` tags. The App never needs either. Prove that the ruleset blocks the App's push while
  still allowing its Release.
- **Once published, each deploy can still fail on its own.** The rollback and log rules
  above handle that. The gate does not.
- **Whatever trigger you choose is a cost you accept, not one you forget.** Write it at the
  top of the workflow, with a date:

```yaml
# RELEASE GATE (<date>). Runs when a release PR adds a file under releases/; also
# workflow_dispatch to run again. Order: contract re-check -> smoke -> draft
# Releases -> publish all (delete drafts on any failure). No schedule, by decision:
# outside-service drift surfaces at the next release, for smoke-tagged journeys only.
```

Whatever runs by hand only has opted into failure mode 1.4 and owes the mitigation: a
**cheap always-on CI job** that statically checks what the dispatch-only workflows can no
longer check for themselves — a linter over every workflow file, and an assertion that
every script path a `run:` body invokes actually exists in the tree.

---

### Principle 11 — Test the logic inside your config, extracted from the shipped file

> **A `run:` body is code. Extract it from the workflow at run time and execute it against
> stubs — never against a transcribed copy.**

*Skill §0.5 carries the general rule and the four assertions that keep the extraction
honest. It matters disproportionately here: in a repo whose deliverable IS configuration,
this is not a niche tier — it is the only tier there is.*

A linter can lint a `run:` body; nothing runs it. `shellcheck` accepts a step that is
wrong at runtime, and a reusable workflow's step bodies are executed in *consumers'*
production ops runs, which is the worst place to discover the difference.

Extract, stub, and fake the clock:

```bash
# Pull the step out of the shipped workflow — a pasted copy passes forever after
# the workflow changes.
python3 - "$WORKFLOW" "$WORK/step.sh" <<'PY'
import sys, yaml
jobs = yaml.safe_load(open(sys.argv[1]))["jobs"]
runs = [s["run"] for s in jobs["<job>"]["steps"] if "run" in s]
if len(runs) != 1:                      # the extraction found what you meant
    sys.exit(f"expected exactly one run: step, found {len(runs)}")
open(sys.argv[2], "w").write(runs[0])
PY
```

The four assertions, in cross-repo terms:

- **The extraction found exactly what you meant** — assert the count, not the presence.
- **The gate is wired in.** For a reusable workflow that means the consumer's `needs:`
  edge, not just that the job exists.
- **The shipped constants are in range.** The case table supplies its own `ATTEMPTS`/
  `GRACE`, so the values the workflow actually ships are invisible to every case — read
  them out of the file and assert their relationship, or a retry loop collapsed to one
  attempt passes the whole suite.
- **The exit code, where two paths share one.** "Allowed because the check was green" and
  "allowed because no check was found" both exit 0. Pin the branch with a string the run
  must emit.

## 3. Reference implementation

### 3.1 The test layer cake

Six layers, each owned by exactly one repo per Principle 2:

| Layer | Lives in | Runs in CI of | Needs a stack? | Wall clock |
|---|---|---|---|---|
| **Unit** | service repo | service repo, every PR — never switched off | no | seconds |
| **Contract** | service repo | service repo, every PR — against the committed copy | no | seconds |
| **Integration** | service repo | service repo, **at each tag**, before the image is retagged (an existing green run for the same commit counts), or by hand — never on a PR; stand-ins only | yes, service-local | 1–3 min |
| **Mocked browser** | UI repo | UI repo, every PR | no real backend | 1–5 min |
| **End-to-end** | root repo | root repo: `smoke` pre-release, full tag set by hand | yes, whole project | 8–20 min |
| **Config-embedded** | the repo shipping the config | that repo, every PR | no — stubs + a faked clock | seconds |

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

```text
<core-service-repo>/
  test/
    docker-compose.test.yml       # base stack — no host ports, here or in CI
    support/
      stack.sh                    # THE driver. One copy in the whole system.
    integration/                  # this service's rules; peers are stand-ins

<ui-repo>/
  tests/mocked/                   # mocked browser tier; replies generated from
                                  # the committed copy of the API definition

<root-repo>/
  tests/
    docker-compose.test.yml       # include:s the base, adds bff/web/runner
    support/
      stack.sh                    # SHIM → core-service driver
      factories.ts                # shared test data builders
    e2e/
      workflows/                  # one scenario per documented workflow,
                                  # each tagged @smoke and/or @full
      contract/                   # static checks, no stack
      pages/                      # page objects
      fixtures/                   # auth, seed, api helpers
      playwright.config.ts
  releases/                       # append-only release log; never edited
    2026-10-07-1.yml              # one file per release PR; "live" = the latest
                                  #   entry naming a service
  .github/workflows/
    ci.yml                        # always-on: lint + static checks. Seconds.
    release.yml                   # on a merged release PR (+ run again by hand):
                                  #   contract re-check -> smoke -> draft Releases
                                  #   -> publish all, or delete the drafts
    e2e-full.yml                  # by hand: the full tag set
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
- **Env knobs, not forks:** `COMPOSE_FILE`, `COMPOSE_PROFILES`.
- **Generate secrets before compose parses the file.** `env_file:` is resolved by the
  Docker CLI at parse time, so a key minted *during* `up` is invisible to the
  containers until the *next* `up` — the stack boots with a stale key and everything
  401s in a way that looks like a test bug. Generate first; mark the file
  `required: true` so a bare `docker compose up` fails loudly instead of booting
  wrong.
- **Every `run:` block declares `shell: bash`.** The implicit default omits
  `pipefail`, so a failure mid-pipe is invisible.

### 3.4 Release job skeleton

```yaml
on:
  push:                     # a merged release PR adds one file to the release log
    branches: [main]
    paths: ['releases/**']
  workflow_dispatch: {}     # "run again" on the newest log entry, without a new commit

concurrency: { group: release, cancel-in-progress: false }   # one release at a time

jobs:
  release:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions: { contents: read, id-token: write }   # id-token: cloud login to pull images
    steps:
      # P1 — fail loud, first, with an actionable message
      - name: Fail if the GitHub App credential is missing
        shell: bash
        env: { HAS_KEY: "${{ secrets.ROOT_APP_PRIVATE_KEY != '' && 'yes' || 'no' }}" }
        run: |
          [ "$HAS_KEY" = yes ] && exit 0
          echo "::error title=Pre-release cannot run::ROOT_APP_PRIVATE_KEY is not provisioned.
          Provision it rather than removing this step — a gate that cannot read what it
          tests, or create the Releases it promises, must go red."
          exit 1

      - uses: actions/create-github-app-token@<sha>
        id: app
        with:
          app-id: ${{ vars.ROOT_APP_ID }}
          private-key: ${{ secrets.ROOT_APP_PRIVATE_KEY }}
          owner: ${{ github.repository_owner }}

      - uses: actions/checkout@<sha>

      - name: Resolve versions (newest log entry, else last logged version)   # P8
        shell: bash
        run: ./tests/support/resolve-versions.sh releases/

      # P10 step 1: each consumer's OWN contract check, pointed at the provider's
      # definition at the candidate version instead of the consumer's committed copy.
      - name: Contract re-check — every consumer against the released definitions
        shell: bash
        env: { GH_TOKEN: "${{ steps.app.outputs.token }}" }
        run: ./tests/support/recheck-consumer-contracts.sh

      # Pull the images that deploy; check out source only where seeding needs it.
      - name: Run the smoke scenarios          # P3 + P6, via the driver
        shell: bash
        run: ./tests/support/stack.sh test --grep "@smoke"

      # P10 steps 3-4 — App token, not GITHUB_TOKEN (that one starts no deploy).
      - name: Create every Release as a draft  # a draft deploys nothing
        shell: bash
        env: { GH_TOKEN: "${{ steps.app.outputs.token }}" }
        run: ./tests/support/releases.sh draft   # gh release create --draft --verify-tag

      - name: Publish all drafts, in log order (providers first)
        shell: bash
        env: { GH_TOKEN: "${{ steps.app.outputs.token }}" }
        run: ./tests/support/releases.sh publish

      - name: Delete the drafts on any failure before publishing
        if: failure()
        shell: bash
        env: { GH_TOKEN: "${{ steps.app.outputs.token }}" }
        run: ./tests/support/releases.sh delete-unpublished-drafts

      - name: Stack logs on failure            # P9
        if: failure()
        shell: bash
        run: ./tests/support/stack.sh logs

      - uses: actions/upload-artifact@<sha>    # P9
        if: failure()
        with:
          name: e2e-report
          path: tests/e2e/playwright-report
          retention-days: 14

      - name: Tear down                        # P9
        if: always()
        shell: bash
        run: ./tests/support/stack.sh down
```

### 3.5 How the root repo reads service repos

Only the root repo reads other repos (Principle 2). Two ways to read, which you can combine,
plus one separate identity for writing Releases:

| Mechanism | Good for | Cost |
|---|---|---|
| **Pulled images** from your registry, with the CI's cloud OIDC login | every service that ships as an image — preferred, it is exactly what deploys | none beyond the login you already have |
| **A read-only GitHub App**, short-lived installation token | source checkouts (seeding tools not in the image, static sites rebuilt from source) | setup once; read-only |
| **A per-project release GitHub App**, key held only by that project's root repo | **creating Releases** | `contents: write` on its own project's service repos only. That permission also allows pushing, so pair it with rulesets that let only humans push to `main` or create `v*` tags |

Distribute the App keys and any test-account credentials through your config-driven
provisioning engine, not by hand, so they are reviewed and rotated centrally.

Per-repo deploy keys and personal access tokens still work but scale badly (one secret
per pair; a token tied to a person is a bus factor of one). A **build** dependency — a
service importing a private library — is not a cross-repo test and may keep whatever
credential it already uses.

Whichever you choose, Principle 1 applies: check for presence explicitly, fail loudly,
name what to provision.

---

## 4. Adoption scorecard

Score honestly. Every "no" is a gate you cannot currently trust.

**Silent-green defence**
- [ ] No gate has a fallback path that exits zero when its input is missing
- [ ] No test `skip`s on the absence of a fixture, mount, or credential
- [ ] Every test command has an automatic call site (pull request, service tag, or the
      pre-release run); whatever runs only by hand is covered by an always-on static check
- [ ] The skip count is zero, or every skip is justified in review
- [ ] The harness rebuilds the image under test on every invocation
- [ ] No test-result cache is trusted on a tier with real dependencies (skill §11.2)
- [ ] No service repo's CI checks out another repo; every cross-repo guard runs in the repo
      it inspects, in the root repo, or is documented as local-only (§1.7)
- [ ] No job that is off by default is counted as proven by a green "skipped" tick — one
      executed run is on record
- [ ] Fixtures are committed and byte-checked; a missing one fails
- [ ] Every parity check strips comments before matching
- [ ] No skip is guarded by the test's own precondition (skill §14)

**Guards that can be wrong**
- [ ] Every guard has a `--self-test`, run in CI immediately before the guard itself
- [ ] Each self-test burns both ways — must-fire *and* must-stay-silent on the near-misses
- [ ] Every guard reports how many subjects it examined, not just its verdict
- [ ] Every baseline/ratchet file carries a reason **per entry**, not one per file
- [ ] Baselines are compared as an equality, so a fixed offender fails until it is removed
- [ ] Each guard records its default direction — does an unlisted subject pass or fail?

**Config as code**
- [ ] Every `run:` body with a loop, a retry or a decision has an extract-and-execute test
- [ ] Those tests extract from the shipped file; no transcribed copies
- [ ] They assert the extraction count, the wiring, and the shipped constants

**Ownership**
- [ ] Every suite lives in the smallest repo containing its system under test
- [ ] No suite in the umbrella exercises only one repo
- [ ] There is exactly one stack driver; other repos consume it via a shim
- [ ] There is exactly one definition of each shared compose service

**Environment**
- [ ] No stack binds host ports — locally or in CI; the test runner joins the network
- [ ] CI creates any `external: true` volume the compose file needs before `up`
- [ ] A production backend is chosen only by an explicit opt-in, never by a variable merely
      being set
- [ ] Test datastores are throwaway and torn down with `-v` on exit
- [ ] Secrets are generated *before* compose parses the file

**Observability**
- [ ] Every stack job echoes the resolved service versions (candidate or live)
- [ ] Stack logs are dumped on failure
- [ ] Reports and traces are uploaded on failure with a retention period
- [ ] Teardown runs on `always()`

**Pinning**
- [ ] Third-party actions are SHA-pinned — or the exemption is written down
- [ ] The pre-release run tests chosen candidates plus live versions, never `main`

**Layers**
- [ ] Unit + contract + mocked browser run in each service repo on every PR, never switched
      off, and nothing else does; integration runs at each tag, before build + publish, against
      stand-ins only
- [ ] The UI repo owns the mocked tier; the root repo owns the end-to-end tier, tagged by depth
- [ ] Every hand-written stand-in is published by the service it imitates and passes the same
      conformance cases as the real service
- [ ] Every outside service sits behind one adapter with a fake; fake and real checks share
      one case list; real checks use test accounts or test modes only, never production
- [ ] The pre-release run first re-runs every consumer's contract check against the
      provider's definition at the released version
- [ ] A release starts as a reviewed pull request adding one file to an append-only
      release log; "live" is read from that log, never from the forge's release order
- [ ] Releases are created as drafts and published together; a failure deletes the drafts
- [ ] An image is built once at main; a tag retags it, and the gate tests that exact image
- [ ] The trigger choice (release PR, by hand, schedule, push) is written at the top of the
      workflow with its date and reason
- [ ] Every `flaky` tag has an owner and an expiry, and a check fails past the expiry;
      no automatic retries inside a run
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
| A guard resolving `"$ROOT/../<sibling>"` and `exit 0` when absent | Inert in CI, alive on a laptop — while the ADR calls it a CI gate | Redesign it to run in the repo it inspects, move it to the root repo, or document it as local-only |
| `if len(subjects) < 2: skip` | Skips exactly when the test was valuable | Hard-fail the precondition |
| `go test` on a tier with a real DB and no `-count=1` | `ok (cached)` after a full truncate + re-seed | Bypass the result cache in the driver |
| A baseline compared as a subset | A fixed offender never leaves the file | Compare as an equality |
| A transcribed copy of a `run:` body in a test | Passes forever after the workflow changes | Extract from the shipped file |
| A guard whose success line states no count | "Passed" and "examined nothing" print the same | State the subject count |
| `\|\| true` on a gate command | Unconditional pass | Remove; keep only on genuinely-empty `grep` |
| Stable nonzero skip count | Real skips hide among conventional ones | Convert to `testIgnore` / project selection |
| `docker compose …` inline in workflow YAML | The workflow *is* the driver; unrunnable locally | Move into `stack.sh` |
| Two copies of the stack script | Drift presenting as flakiness | Shim + `include:` |
| Host port bindings "just for dev", or "just for CI" | Collisions; dishonest service discovery; CI reaches the stack differently from the laptop | Runner inside the compose network |
| Root suite testing services' `main` | A service push retroactively reds the root repo; tests what nobody is shipping | Candidates + last logged versions |
| A service repo's CI checking out a sibling | The service's tests now depend on another repo's state | Committed copy of the definition; move the test to the root repo |
| A hand-written fake of a service you own, kept by the consumer | Drifts from the real service with nobody to notice | Provider publishes the fake and runs conformance cases against both |
| Mocked browser replies written by hand | The UI is tested against what the author believed | Generate them from the API definition |
| A required check satisfied by a skipped job | A job whose `if:` is false shows green | One executed run on record per off-by-default job |
| A parity check matching commented-out lines | A disabled gate still counts as present | Strip comments first |
| `external: true` volume on a fresh CI runner | `compose up` fails before a test runs | `docker volume create <name>` in the job first |
| Production backend selected because its URL is in the environment | A test run writes to production | Explicit opt-in variable |
| A "real" outside-service check that reads production | Tests now depend on, and can leak, live data | Test account or test mode; otherwise stay a fake |
| A nightly run as the *only* release gate | Nobody owns its red; it tests what nobody is shipping | A release gate on a reviewed release PR; a schedule may run alongside it |
| Rebuilding at the tag or at deploy | The gate tested different bytes from the ones that ship | Build once at main; retag; promote |
| A hand deploy of a version the gate never saw | An untested version goes live | Hand deploys re-deploy logged versions only; hotfixes go through a release PR |
| Automatic retries inside a test run | Real intermittent bugs pass on the second try | Tag `flaky` with owner + expiry; retry the whole run by hand |
| E2E red with no artifacts | Rumour, not signal | `if: failure()` upload |

---

## 6. The shortest version

If you remember one sentence from this document, make it the first principle, because
every other item here is a specific instance of it:

> **A gate that cannot do its job must go red.**

Everything else — the single driver, the shared network, the tiering, the version echo, the
unconditional rebuild — is machinery for making sure that when something is broken,
you find out.
