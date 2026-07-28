# Release process — trunk-based, build-once, promote-by-retag

The model these workflows are meant to serve. It is **descriptive of the intended
flow**, not a workflow you call — the pieces are `deploy-cloud-run` /
`deploy-gke-service` (build stage) and [`promote-image`](promote-image.md) (retag
to prod). Where a rule is **not yet enforced by a workflow**, it says so and links
`TODO.md`.

Core ideas: **trunk-based development**, **build the artifact exactly once**, and
**promote that same artifact by retagging** — prod runs the identical bytes stage
tested, never a rebuild that could drift.

## Branches → environments

Two long-lived branches, both feeding the **same stage environment**:

- `development` — integration branch. Every push builds `image:<sha>` once and
  deploys it to **stage** (fast feedback).
- `main` — the release-candidate / prod source. A merge to `main` is "this is
  releasable."
- **prod** — a **retag** of a stage-proven digest onto `:vX.Y.Z`, then roll. No
  build.

**Triggers are the caller's, not the reusables'.** Every workflow here is
`workflow_call` — none encodes a trigger (see README, "Callers own their trigger").
The flows below are **defaults**, freely overridable:

| Env | Default trigger | Also valid (caller's choice) |
|---|---|---|
| stage | `push` to `development` | tag on `development`, `push` to `main`, `workflow_dispatch` |
| prod | release (semver tag) on `main` | `workflow_dispatch`, tag elsewhere, manual promote |

The model (build-once, forward-only, promote-by-retag) holds regardless of which
trigger a caller wires — nothing below assumes "push to `development`" or "tag on
`main`".

```
feature/* ─PR─▶ development ─(push)─▶ build image:<sha> ─▶ STAGE
                     │
                merge to main (squash OK — see below)
                     │
              main tip already stage-green?
                ├─ yes ─▶ retag :<sha>→:vX.Y.Z ─▶ PROD   (promote-image, no build)
                └─ no  ─▶ build image:<sha> ─▶ STAGE ─▶ gate ─▶ retag ─▶ PROD

hotfix/*  ─PR─▶ main ─▶ STAGE first (validate) ─▶ retag ─▶ PROD
```

## The single promotion rule (merge-strategy agnostic)

Do **not** branch logic on "was the merge a fast-forward or a squash." Branch on
the artifact:

> **Does `main`'s tip commit already have a stage-green digest?**
> - **Yes** (ff — the commit was built & validated as `development`'s tip): promote
>   that digest straight to prod. No build, no re-test.
> - **No** (squash / merge-commit / rebase / direct commit minted a new SHA): build
>   it, deploy to stage, pass the gate, then promote.

This one predicate subsumes ff-detection and works under **any** merge strategy —
which is what lets us keep squash merges. Because prod always promotes the digest
built *from `main`'s own tip*, stage tests the **exact** prod artifact even when a
squash mints a brand-new commit. Prod is always a retag of a stage-green digest,
never a rebuild.

## The CI→CD handoff is a race, and must be treated as one

Build-once means the build and the promote are **separate workflow runs** with no
`needs:` edge between them — that is inherent to the model, not an accident of
wiring. So a release tag can, and routinely does, reach `promote-image` before the
build for `main`'s tip has pushed `:<sha>`. The promote then fails on a perfectly
healthy build, and re-running it minutes later succeeds.

Close the window explicitly with **`source_wait_seconds`** on `promote-image` (see
[promote-image.md](promote-image.md#racing-the-build-ci--cd-handoff)): it polls GAR
for the source image with backoff instead of probing once. Size it at your build's
p99 plus queue time and keep `timeout_minutes` above it.

**Status: opt-in, default `0` (fail immediately).** Any caller cutting tags from
automation, or by hand right after a merge, should set it. It waits on the
*artifact*, so it holds whichever workflow or trigger built the image. A caller
that prefers no waiting can instead trigger its promote from `workflow_run` on the
build, which removes the race structurally at the cost of per-repo boilerplate.

## Forward-only — every environment

> **Reject a deploy if the candidate commit is an ancestor of (already fully
> contained in) the environment's current live commit.** Skip if equal. Allow if it
> is a descendant *or* divergent.

- One rule, applied per environment (each env tracks its own live commit).
- On the **shared stage env**, "divergent" must be *allowed* — a squash commit on
  `main` is not a descendant of `development`'s tip, and blocking it would stop your
  own release candidate reaching stage. "Not strictly behind" allows the lineage
  switch while still catching an accidental redeploy of older code.
- On **prod** the rule auto-strengthens to strict forward: `main` is a linear total
  order and **prod releases only from `main`**, so "divergent" can't occur — you get
  strict "latest-release-only" for free. A release cut from an older commit than
  what's live is rejected.
- Serialize deploys per env (a concurrency lock) so read-compare-deploy is atomic;
  out-of-order releases then resolve correctly regardless of arrival order.

**Status: enforced on stage and prod (opt-in).** `promote-image` (prod),
`deploy-cloud-run` and `deploy-gke-service` (stage) all implement the guard behind
`enforce_forward_only` (default off). Each reads the live commit from the env's
latest successful GitHub Deployment, compares via the GitHub compare API, and blocks
a strictly-behind (out-of-order) deploy/release. On the stage workflows the guard runs
*before the build*, so a blocked deploy wastes no build. Requires `environment` set
(that's what the baseline is keyed on).

## Rollback — explicitly OUT of the promote flow

**Transient (fast) rollback is not part of this release pipeline and must be
handled outside it.** The promote flow is forward-only and immutable-tag driven; a
fast rollback is, by definition, a temporary *backward* artifact move, and mixing
it into the forward promote path would corrupt the invariant. Keep them separate.

There are two distinct actions, and they are **not** the same mechanism:

### 1. Transient fast rollback — the bridge (out-of-band)

Get an already-built, prod-proven digest live in **seconds**, because the real fix
(`git revert` → rebuild → stage → gate → new tag) takes minutes and an outage can't
wait. This is a **temporary bridge**, valid only until the revert lands.

```
outage ─▶ FAST ROLLBACK: re-select an existing good digest   ← seconds, transient
             │   (prod runs old-but-proven image; main tip still holds the bad code)
             ▼
         ...limps along until the permanent fix ships...
```

Properties of the bridge:
- **No rebuild** — it re-selects an existing digest that was already prod-proven.
- It lives **outside** the promote workflow, as
  [`rollback-service`](rollback-service.md) — a separate, caller-dispatched reusable
  taking a tag/digest input that rolls the service and stamps the live commit.
- **No pin/freeze.** This stack is push-based — Cloud Run and GKE hold the image
  they were rolled onto, and no reconciler re-derives "latest tag" — so nothing
  autonomously undoes a rollback. (A pin *would* be mandatory under a GitOps
  reconciler like Argo/Flux, which is why it's a common reflex; it isn't needed
  here.) The only re-clobber risk is a human manually re-promoting the bad tag
  mid-incident; if that ever needs guarding, **quarantine the specific bad artifact**
  in `promote-image` (see `TODO.md`) rather than freezing all promotion — the
  permanent fix is a *new* tag, so it promotes with no unpin dance.

### 2. Permanent fix — `git revert` + a new linear tag (the real fix)

```
git revert C_bad ─▶ C_fix  (descendant of C_bad — FORWARD on the tree)
     │
     ▼
build ─▶ STAGE ─▶ gate ─▶ new linear tag vX.Y.(Z+1) ─▶ promote-image ─▶ PROD
     │
     ▼
prod = latest linear tag again ─▶ forward-only restored
```

The revert commit is a **descendant** of the bad commit, so it satisfies
forward-only and flows through the normal promote path unchanged. Once its tag is
live, prod is back to "latest linear tag = live" and the bridge is superseded.
**This** is the git-native, cleanly-tracked record of the incident; the fast bridge
is just there to stop the bleeding until it ships.

### The hard constraint — migrations

Fast rollback only restores service if the prior image can still run against the
**current** database schema. A **non-backward-compatible migration** in the bad
release breaks this — old code against a new schema. Fast rollback is therefore only
as safe as your migrations are **backward-compatible (expand/contract, N/N+1)**.
Where that discipline is absent, the fast bridge is off the table and you must roll
*forward* with a data fix (path 2 only).

## Why this shape (and not full GitOps)

Prod stays **tag-driven** (immutable `vX.Y.Z` via `promote-image`); rollback is a
separate, incident-scoped bridge. The alternative — an always-pointer-driven GitOps
reconciler — would remove the divergence window but adds a permanent parallel
source of truth and a reconciler to freeze during incidents. The lighter model was
chosen because it matches how `promote-image` already works and needs no pin. See
the 2026-07-15 entries in [DECISIONS.md](../DECISIONS.md).
