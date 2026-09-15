# Provenance policy (4c) + release gate (4d) — options for the owner

**Status:** decision document, 2026-09-15. Written against `chore/survey-fixes-1-4`, tree swept to
`v2.7.0`. **Nothing here is implemented.** Both items are reserved for the owner by
[`plans/survey-fixes-1-4.md`](survey-fixes-1-4.md) §"Items 4c + 4d".

Builds on `TODO.md` §"Build attestations" and §"Release hygiene" — read those for the history;
this document does not restate them. It does **correct** two factual claims in them (§0).

---

## Decision summary

| | Question | Recommendation | Cost | Blocks |
|---|---|---|---|---|
| **4c** | What `provenance:`/`sbom:` policy for the build reusables? | **Option C — pin today's behaviour explicitly and expose it as two `workflow_call` inputs.** Set `provenance: 'mode=min'`, `sbom: 'false'` literally on all **three** build steps, defaulted from new inputs. Behaviour unchanged today; artifact shape stops being a hidden default. | one minor (`v2.8.0`), ~12 lines of YAML, 3 doc updates | nothing |
| **4d** | A GitHub ruleset requiring the tag-push check green before a release publishes? | **Do not build it — the mechanism does not exist.** Adopt **Option R2** instead: a `workflow_dispatch` release workflow that runs the sweep check *before* it creates the tag, plus a tag ruleset restricting who may create `v*.*.*`. | ~60-line workflow + one ruleset; changes the release ritual | §"Release hygiene" bullets 1–2 close |

**The one-line version of 4c:** the defect is not "provenance on" or "provenance off" — it is
**unset**. The artifact shape of every production deploy in the fleet is currently decided by a
default living *inside* a SHA-pinned action, so the next `build-push-action` bump can flip it
silently, and `cleanup-gar-images`' parent/child logic is written against that shape. Turning
provenance *off* buys registry tidiness that the sweep already handles in code
(`cleanup-gar-images.yml:531-537`, `:584-594`); it does not fix any live failure. Turning it
*on-and-explicit* costs nothing and removes the drift.

**The one-line version of 4d:** a ruleset **cannot** gate a release publish (releases are not a
ruleset target), and **cannot** usefully gate the tag push either — for two independent reasons,
either of which is fatal on its own: (1) a push ruleset is evaluated *before* the workflow that
the tag triggers has run, so there is no check to require; (2) even if it evaluated against the
tagged commit's existing check runs, those came from the **main-push** CI run, which calls
`stamp_version.py --check` **without** `--expect` (`.github/workflows/ci.yml:90-93`) and
therefore asserts only self-consistency. It would have been **green on `v2.6.1`**. The gate has
to move *before* the tag, which is what R2 does.

---

## 0. Corrections to the briefs (read before the bodies)

Both `TODO.md` §"Build attestations" and `plans/survey-fixes-1-4.md` §4c name
`deploy-cloud-run.yml` **and `promote-image.yml`** as the two files needing a provenance policy.
Verified 2026-09-15, both halves are wrong:

- **`promote-image.yml` builds nothing.** It retags server-side —
  `gcloud container images add-tag` at `promote-image.yml:438-464`, header at `:1-9`. It has no
  `buildx`, no `build-push-action`. `provenance:` is not a setting it could hold. It still
  *interacts* with the policy (§1.4).
- **There are THREE build surfaces, not one.** All pin the same action
  `docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a # v7.3.0`:
  - `deploy-cloud-run.yml:311`
  - `deploy-gke-service.yml:300`
  - `deploy-cluster-keyed.yml:313`

  A policy applied to one of three is drift by construction. Any implementation must touch all
  three, and `TODO.md` should be corrected in the same pass (owned by the `TODO.md` agent, not
  this file).

Also verified: **nothing in this repo verifies an attestation.** `/usr/bin/grep` for
`cosign|slsa-verifier|attest-build-provenance` across `.github/workflows/` returns zero hits.
That fact does real work in §1.3.

---

## 1. Item 4c — `provenance:` / `sbom:` policy

### 1.1 What is verified in this tree

| Claim | Status |
|---|---|
| No `provenance:`/`sbom:` is set on any build step | **VERIFIED** — `/usr/bin/grep -rn 'provenance\|sbom' .github/workflows/` matches only comments in `cleanup-gar-images.yml:289-294` |
| Default build platform is single-arch | **VERIFIED** — `deploy-cloud-run.yml:102-106`, `default: 'linux/amd64'` |
| Pushes today land as an OCI **index** with an `unknown/unknown` attestation child | **VERIFIED as observed behaviour** — `DECISIONS.md:1618-1622` and the Traide RCA (`DECISIONS.md:1620`): *52 untagged versions, 52 child links, zero orphans* |
| The sweep already keeps children of kept parents and reports the rest | **VERIFIED** — `cleanup-gar-images.yml:531-537` (child of a kept parent joins the keep-set), `:584-594` (only a *surviving, non-doomed* parent blocks), `:653-655` (`blocked_by_parent` reporting) |
| buildx's default is `provenance=mode=min` on registry push and `sbom=false` | **UNVERIFIED HERE** — from `docker/build-push-action` documentation, not checked against a live build. See §1.6 for the check that settles it |
| "Cloud Run needs a plain image" (`Realm-ID/issuer#2`, 2026-08-12) | **UNVERIFIED, and contradicted by current operation** — `deploy-cloud-run.yml` sets nothing, so *if* the default is attestations-on, `issuer` and `api` are both running from an index today. The contradiction is exactly as strong as the unverified default above; do not quote either as settled |

⚠️ **Do not infer the default from the child count.** One `unknown/unknown` child per platform is
consistent with provenance-only *and* with provenance+SBOM — buildx puts both in the **same**
attestation manifest as separate layers. The observed shape proves attestations are being
generated; it does not prove which kinds.

### 1.2 What each option actually changes in the registry

With the default `platforms: linux/amd64`, attestations are the *only* reason a push produces an
index at all. Turn them off and a push is a single image manifest: no index, no children.

| | Option | New pushes produce | Untagged children created | SLSA metadata |
|---|---|---|---|---|
| **A** | Keep the inherited default, document it | index + 1 platform child + 1 attestation child | 2 per push | unsigned, in-registry |
| **B** | `provenance: false`, `sbom: false` | one plain manifest | 0 | none |
| **C** | Inputs, defaulting to today's behaviour (`mode=min` / `false`) | as A, but *chosen* | 2 per push | as A |
| **D** | B **plus** `actions/attest-build-provenance` | one plain manifest | 0 | **signed**, in GitHub's attestation store, verifiable with `gh attestation verify` |

### 1.3 Resolving the tension the brief asks not to paper over

The stated tension — "this repo SHA-pins every third-party action precisely because supply-chain
guarantees matter, so turning provenance off trades a real thing for a cosmetic one" — is real
but **asymmetric**, in a way that decides the item:

1. **SHA-pinning is an enforced control.** CI greps for non-40-hex `@refs` (`CLAUDE.md`,
   `reusable-workflows` §rules). It fails a PR. It has a verifier.
2. **Registry provenance today is an unenforced one.** It is unsigned in-toto metadata that
   **nothing in this platform reads** (§0). There is no `cosign verify-attestation`, no
   `slsa-verifier`, no admission control on Cloud Run or GKE. Its guarantee is currently
   *potential*, not *realised*.
3. **The tidiness argument is worth much less than when it was written.** The Traide RCA's 52
   undeletable manifests were a **sweep bug**, and that bug is fixed (`cleanup-gar-images.yml:531-537`,
   `:584-594`). What remains is per-sweep registry-API cost (one v2 manifest GET per artifact,
   8-way pool, `cleanup-gar-images.yml:343-346`) and reporting noise.

So neither side is holding a live failure, and the *actual* defect is the third thing: the shape
is **inherited**. `docker/build-push-action` is SHA-pinned at `53b7df9`; the attestation default
is a behaviour *inside* that pin, and `cleanup-gar-images`' correctness is written against the
shape it produces. A future bump to v8 that flips the default changes the artifact topology of
every deploy in the fleet with no diff in this repo saying so. That is precisely the class of
silent drift the SHA-pinning rule exists to prevent — and it is currently un-pinned.

### 1.4 The interaction most likely to be got wrong

Whatever is chosen, these hold, and two of them are traps:

- 🪤 **Do not delete the `Resolve index → child manifests` step if provenance goes off.**
  `cleanup-gar-images.yml:298` is not obsolete under option B or D. Historical indexes already in
  GAR keep their children for as long as they are retained, and any caller that sets
  `platforms:` to more than one arch produces an index regardless of the provenance setting. The
  step degrades correctly to an empty map for plain manifests (the v2 GET returns an image
  manifest, `body.get("manifests", [])` is empty — `cleanup-gar-images.yml:341`), so leaving
  it in costs one API call per artifact and nothing else.
- 🪤 **The sweep's "kept" and "blocked" counts will drift downward for months, not overnight.**
  Under B/D, `blocked_by_parent` (`:610`, `:653-655`) shrinks only as old indexes age out. A run
  that reports 0 blocked is not evidence the change took effect; a run that still reports many is
  not evidence it did not.
- **`promote-image` is shape-agnostic.** `gcloud container images add-tag`
  (`promote-image.yml:464`) retags a digest whether it names an index or a plain manifest. Under
  B/D the `:vX.Y.Z` release tag would name an image manifest directly — which is also what makes
  the unverified 2026-08-12 "Cloud Run needs a plain image" claim moot either way: B/D gives it
  what it asked for, A/C is what is demonstrably running now.
- **The fail-safe is untouched.** Fewer than `build_retention_releases` releases ⇒ nothing is
  deleted (`cleanup-gar-images.yml:28-33`). No option here interacts with it.

### 1.5 Recommendation — Option C, with `sbom: false` stated literally

Set on **all three** build steps, sourced from two new `workflow_call` inputs:

```yaml
provenance: ${{ inputs.provenance }}   # new input, default 'mode=min'
sbom: ${{ inputs.sbom }}               # new input, default 'false'
```

Why C over the alternatives:

- **Over A (document the default):** documentation does not survive an action bump. C makes the
  artifact shape a reviewable line in this repo, which is the same argument that justifies
  SHA-pinning. This is the whole of the fix.
- **Over B (`provenance: false`):** B trades a real-but-unrealised guarantee for a benefit the
  sweep already delivers in code. It is also the one option that is **hard to reverse in the
  registry** — the metadata for builds made while it was off simply does not exist later.
- **Over D (`attest-build-provenance`):** D is the only option that makes the guarantee *real*
  (signed, with a verifier that ships in `gh`), and it is where this should eventually go. It is
  **not** recommended now because of a plan constraint: GitHub artifact attestations are
  available for public repos and for private repos on paid plans. `Traide-Co` and `AutoMahn` are
  **free** (ruling in the brief; `Just-Git-Dev` itself measured free — §2.1), and their app repos
  are private, so a reusable that unconditionally attests would fail for two of three orgs. D is
  reachable *from* C by flipping an input, which is the point of C.
- **`mode=min`, not `mode=max`:** `mode=max` embeds the full build definition including build
  args and environment. `deploy-cloud-run.yml:108` takes arbitrary `build_args` from callers. Do
  not publish those.

**What C is not:** it is not "let the caller decide" as a way of avoiding the decision. The
decision *is* the default, and the default is "keep today's behaviour, now written down". The
inputs exist so option D is a one-line change per repo when the plan constraint lifts.

### 1.6 The check that settles the unverified default — ✅ RUN 2026-09-15, DEFAULT CONFIRMED

**Settled empirically against a live artifact**, not from buildx's documentation. Subject:
`asia-southeast1-docker.pkg.dev/realm-id/backend/api:v0.124.0`.

1. The release tag names an **OCI index** (`application/vnd.oci.image.index.v1+json`) with two
   children: `linux/amd64`, and one `unknown/unknown` carrying
   `vnd.docker.reference.type: attestation-manifest`. → **attestations are ON today.**
2. That child manifest (its own digest `sha256:eda06d7c…`) has **exactly one layer**:
   `application/vnd.in-toto+json`, annotated
   `in-toto.io/predicate-type: https://slsa.dev/provenance/v1`. There is **no** SPDX layer.
   → **provenance ON, SBOM OFF.** `sbom: 'false'` is therefore a true no-op.
3. The provenance blob's `predicate.buildDefinition` contains only `buildType`,
   `externalParameters`, `internalParameters`, `resolvedDependencies` — **no `llbDefinition`, no
   `buildConfig`, no source map**, which are what `mode=max` embeds. → **`mode=min`.**

So Option C's defaults (`provenance: 'mode=min'`, `sbom: 'false'`) reproduce today's behaviour
exactly, and the change is genuinely inert at the registry. That was the condition the whole
option rests on.

⚠️ **Trap when re-running this.** The index entry's `vnd.docker.reference.digest` annotation is
the digest of the **subject image**, not of the attestation child. Fetching that annotation
returns the ordinary `linux/amd64` manifest — multi-megabyte filesystem layers and no in-toto
predicate — which reads like "attestations are off" when they are on. Use the child entry's own
`digest` field.

#### The check as originally specified

One command against a live artifact, no build required:

```bash
gcloud artifacts docker images describe \
  <region>-docker.pkg.dev/<proj>/<repo>/<image>:<vX.Y.Z> --format=json
# or, for the raw child list the sweep itself reads:
#   GET https://<host>/v2/<proj>/<repo>/<image>/manifests/<digest>
#   Accept: application/vnd.oci.image.index.v1+json
```

If the result is an index whose children include an `unknown/unknown` platform, attestations are
on. To distinguish provenance from SBOM, pull that child manifest and read its layer media types
(`in-toto` predicate `https://slsa.dev/provenance/` vs `https://spdx.dev/Document`).

---

## 2. Item 4d — the release ruleset

### 2.1 Plan and availability — verified

Queried 2026-09-15 via `gh api` (read-only):

- `Just-Git-Dev/reusable-workflows` — `"private": false`, `"visibility": "public"`, owner type
  `Organization`, default branch `main`. **VERIFIED.**
- `orgs/Just-Git-Dev` → `"plan": "free"`. **VERIFIED.**
- `repos/Just-Git-Dev/reusable-workflows/rulesets` → `[]`. **No rulesets exist today. VERIFIED.**

Rulesets and branch/tag protection are available on free plans **for public repositories**;
private repos need Team or Enterprise. This repo is public, so the free plan is **not** a blocker
here — INFERRED from GitHub's documented plan matrix, not tested by creating a ruleset. It *is* a
blocker for the same pattern in the consumers: `Realm-ID` is `team` (fine), `Traide-Co` and
`AutoMahn` are `free`, so any private app repo there cannot use rulesets at all. That asymmetry
matters for which fallback is portable (§2.4).

### 2.2 What a ruleset can and cannot gate — the part the whole item rests on

**It cannot do what `TODO.md` asks.** Stated plainly, as the brief requires, with the two reasons
separated because each is independently fatal:

1. **A release publish is not a ruleset target.** Ruleset targets are *branch*, *tag*, and *push*
   (org-level adds repository-property targeting). Creating or publishing a GitHub **Release** —
   including flipping a draft to published — is an API/UI action against the releases endpoint,
   not a ref update, so no ruleset evaluates it. There is no "require check X before publish"
   control anywhere in repository settings. *(INFERRED from the ruleset target model and the
   settings UI; the concrete check is §2.6.)*
2. **Ordering makes the tag-push variant vacuous even if the rule type existed.** Required status
   checks are a **branch**-target rule; tag rulesets offer creation/update/deletion, required
   signatures, and tag-name patterns. But suppose it were offered for tags. A push ruleset is
   evaluated *at ref-update time*, before any workflow the push triggers. `ci.yml` triggers on
   `push: tags: ['v*.*.*']` (`.github/workflows/ci.yml:8-12`) — the run whose green is wanted
   **cannot exist yet**. The rule would therefore have to evaluate the *tagged commit's* existing
   check runs, which came from the main-push CI run. That run takes the `else` branch and calls
   `stamp_version.py --check` with **no** `--expect` (`.github/workflows/ci.yml:90-93`), and
   `--expect` is the only thing that compares the tree against the tag
   (`scripts/stamp_version.py:211-221`). **It would have been green on the `v2.6.1` tag push.**

Point 2 is the important one and it is verifiable entirely in this tree: the check that caught
`v2.6.1` is *structurally incapable* of running before the tag exists, because its comparand is
the tag name. No gate placed at or before tag creation can consume it. The gate must be
*re-ordered*, not *enforced*.

### 2.3 Options

| | Option | Prevents the `v2.6.1` failure? | Cost | Breaks |
|---|---|---|---|---|
| **R0** | Runbook only ("never publish until the tag run is green") — `TODO.md`'s first bullet | No. This is the control that already existed and was ignored | zero | nothing |
| **R1** | Branch ruleset on `main` requiring the `version-sweep` check | No — main's check is self-consistency only (`ci.yml:93`); `main` was internally consistent at `v2.6.0` when `v2.6.1` was cut | small | nothing; still worth having for other reasons |
| **R2** | **Release workflow cuts the tag.** `workflow_dispatch(version)` → checkout `main` → `stamp_version.py --check --expect <version>` → **only if green**, create the tag and publish the release | **Yes** — the comparand exists before the tag does | ~60-line workflow; release ritual changes from `git tag` to "run the workflow" | direct `git tag && git push --tags` stops being the path |
| **R3** | R2 **+ tag ruleset** on `v*.*.*` restricting tag *creation* to a bypass list containing only the release workflow's identity | Yes, and makes R2 non-bypassable by habit | R2 + one ruleset | hand-tagging, deliberately. Emergency tags need a bypass or a ruleset toggle |
| **R4** | Detect-and-revert: `on: release: published` workflow that re-runs the check and, on failure, converts the release back to a draft and deletes the tag | No — it *corrects*, it does not prevent. Consumers can pin in the gap | ~30 lines | a published release can vanish under a consumer |

### 2.4 Recommendation — R2 now, R3 immediately after

**R2 is the fix**, because it is the only option that puts the assertion on the correct side of
the tag. Everything else either re-litigates a control that already fired and was ignored (R0,
and `TODO.md` is right that nothing needs *building* for it — but also right that it did not
work), gates the wrong assertion (R1), or cleans up after the fact (R4).

**R3 is what makes R2 structural rather than remembered** — and "structural rather than
remembered" is `TODO.md`'s own stated goal for this item. Without the tag ruleset, R2 is one
`git push --tags` away from being bypassed by exactly the habit that produced `v2.6.1`. The
ruleset is available here (§2.1) and it restricts a *creation*, which is a rule type tag rulesets
do support.

**Keep R1 as well** — it is cheap and it guarantees `main` is never internally inconsistent, which
is the precondition R2's `--expect` check depends on. It is not a substitute for R2.

**Do not build R4.** A control that un-publishes a release is worse than the failure it catches.

### 2.5 The trap that will break R2/R3 if it is not designed for

🪤 **A tag pushed by `GITHUB_TOKEN` does not trigger workflows.** If the release workflow creates
the tag with the default `GITHUB_TOKEN`, the existing `on: push: tags` CI run
(`.github/workflows/ci.yml:8-12`) **stops firing entirely** — and a gate that goes green because
it could not run is precisely the failure shape `plans/survey-fixes-1-4.md:145-148` warns about
for item 4a. Two consequences for whoever implements R2:

- The release workflow must run `--check --expect` **itself**, not delegate to the tag-push run.
  That is the gate; the tag-push run becomes belt-and-braces.
- If the tag-push CI run is wanted anyway, the tag must be created with a PAT or a GitHub App
  token, not `GITHUB_TOKEN`. Under R3 that identity is also the one that needs the ruleset
  bypass. State which, explicitly, in the implementation plan.

Second-order: the same trap makes the **consumer** repos' release flows worth a look, since
`promote-image` is driven by a release/tag event there (`docs/release-process.md:30-31`). Out of
scope for this document; do not fix it here.

### 2.6 The checks that settle the two INFERRED claims in §2.2

Both are read-only and take a minute in the UI:

1. Repo → Settings → Rules → New ruleset. Read the **Target** selector. If it offers only
   Branch/Tag/Push, claim 1 is confirmed: releases cannot be gated.
2. Choose **Tag** as the target and read the rule checklist. If "Require status checks to pass" is
   absent, the first half of claim 2 is confirmed. (The *ordering* half is already proven in-tree
   and does not depend on this.)

If — contrary to the above — a tag-target status-check rule does appear, R2 is still the
recommendation, because §2.2 point 2's ordering argument stands on its own.

---

## 3. Open questions for the owner

**Q1 — 4c: adopt Option C?** *(§1.5)*
OPTIONS: A document-only · **B `provenance: false`** · **C inputs defaulting to today** · D signed
attestations via `actions/attest-build-provenance`.
RECOMMENDATION: **C**, `provenance: 'mode=min'` / `sbom: 'false'`, on all three build steps.
BLOCKS: a `v2.8.0` minor and three doc updates. Consumers need no change (defaults preserve
behaviour). Choosing B instead makes the change irreversible for builds made while it is off.

**Q2 — 4d: accept that the requested ruleset does not exist, and adopt R2 (+R3)?** *(§2.4)*
OPTIONS: R0 runbook only · R1 branch ruleset · **R2 release workflow cuts the tag** · R3 R2 + tag
ruleset · R4 detect-and-revert.
RECOMMENDATION: **R2 now, R3 immediately after, keep R1 as a cheap extra.** Do not build R4.
BLOCKS: `TODO.md` §"Release hygiene" bullets 1 and 2 stay open until this is answered. R3 changes
who can cut a tag, which is an owner-only call.

**Q3 — who owns the `attest-build-provenance` follow-up?** *(§1.5, option D)*
The plan constraint (free-plan private consumers) is the only thing keeping D out. If the owner
wants signed provenance, the missing piece is not this repo — it is a verifier
(`gh attestation verify` / `cosign`) somewhere in the deploy path, without which D is the same
unrealised guarantee as A.
RECOMMENDATION: record as a `TODO.md` item under §"Build attestations", not as work in this wave.
BLOCKS: nothing today.

---

## 4. Verification ledger

**VERIFIED in this tree / via read-only `gh api`, 2026-09-15:** three build surfaces and their
line numbers (§0); `promote-image` retags and never builds; no attestation verifier anywhere in
the repo; the sweep's child keep/block logic; `platforms` default; `ci.yml`'s two-mode check and
that `--expect` is tag-only; `Just-Git-Dev` org plan `free`; the repo is public; zero rulesets
exist.

**UNVERIFIED — do not quote as fact:** buildx's exact default (`provenance=mode=min`,
`sbom=false`) on registry push; that a release publish cannot be a ruleset target; that tag-target
rulesets offer no status-check rule; that GitHub artifact attestations are unavailable for
free-plan private repos; and the 2026-08-12 `Realm-ID/issuer#2` claim that Cloud Run requires a
plain image (contradicted by current operation, but only as strongly as the buildx-default claim
it depends on).

**Checks that settle them:** §1.6 for the buildx default, §2.6 for the two ruleset claims.
