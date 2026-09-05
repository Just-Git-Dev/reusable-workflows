#!/usr/bin/env bash
#
# Behavioural test of the `pinned` gate that consumer repos carry in
# .github/workflows/workflow-hygiene.yml.
#
# WHY THIS EXISTS, and why it is not a grep.
# ------------------------------------------
# The gate rejects third-party actions that are not SHA-pinned, while
# deliberately exempting first-party `Just-Git-Dev/reusable-workflows/...@vX.Y.Z`
# refs (semver there tracks the INPUT CONTRACT — see the platform rule in
# CLAUDE.md and DECISIONS 2026-07-01). Two sessions independently tried to verify
# that exemption by grepping for its implementation:
#
#     grep -c "grep -v 'Just-Git-Dev/reusable-workflows/'" <file>
#
# That check is wrong in both directions. It reports "fixed" for a `grep -v` that
# is present but broken, and "not fixed" for a correct regex-only implementation.
# It also returns 0 — not an error — when the path does not resolve at all, which
# is how both sessions produced a confident false negative on the same day (one
# from a stale guess at the filename, one from the wrong working directory).
#
# This script asserts BEHAVIOUR instead. Two properties make that real:
#
#   1. It EXECUTES THE GATE THE REPO SHIPS. The `Reject mutable action refs`
#      step's `run:` body is extracted from that repo's own workflow-hygiene.yml
#      and run as-is, including its exit codes. An earlier draft of this script
#      carried its own pasted copy of the pipeline — which would have gone green
#      against a repo whose real gate was broken, reproducing the exact defect it
#      was written to detect. Never reintroduce a local copy of the gate here.
#
#   2. It runs under GNU grep inside ubuntu:24.04, because that is what CI runs.
#      Do not "simplify" this to a host run: the dev laptops here resolve `grep`
#      to ugrep, whose -P differs, so a host pass is not evidence about CI.
#
# USAGE
#   scripts/pin_gate_behaviour.sh [--ref <git-ref>] <repo-path>...
#
#   --ref   Ref to read every repo at. Default per repo: origin/ci/workflow-hygiene
#           if present, else HEAD. The resolved ref is printed for each repo —
#           read it. Some repos carry more than one hygiene branch (a superseded
#           one and the branch an open PR actually points at), and the default
#           will happily pick the stale one.
#
#   Exit 0 iff every assertion in every repo passed. Vacuous coverage is
#   reported but does not fail the run.
#
# NOT WIRED TO CI ON PURPOSE. The subjects are sibling consumer repos that do not
# exist in this repo's checkout, so a CI job here would find nothing to test and
# go green — the inert-gate failure this script exists to catch. Run it by hand
# when changing the gate, or when a consumer repo's copy is in doubt.
#
# SELF-TEST
#   scripts/pin_gate_behaviour.sh --self-test
# mutates a known-good gate three ways (exemption deleted, exemption widened to
# the whole org, matcher neutered) and requires this script to go red on each.
# A checker whose red path nobody has watched fire is not evidence of anything.
set -uo pipefail

GATE_STEP='Reject mutable action refs'

# --------------------------------------------------------------------------
# Container half. Re-invoked inside docker with the extracted trees mounted.
# Each trees/<name>/ holds the repo's .github/workflows plus gate.sh, the
# repo's own step body.
# --------------------------------------------------------------------------
if [ "${1:-}" = "--in-container" ]; then
  fail=0

  # An empty mount must be an error, never an empty loop. `for x in dir/*/`
  # iterates the literal glob when nothing matches, which previously produced a
  # bogus FAIL attributed to a real repo. A harness that can report a verdict
  # about a tree it never read is worse than one that crashes.
  shopt -s nullglob
  trees=(/w/trees/*/)
  if [ "${#trees[@]}" -eq 0 ]; then
    echo "::error::/w/trees is empty — nothing was staged into the container." >&2
    exit 2
  fi

  # Run a repo's own gate with `cwd` set so its hardcoded `.github/workflows`
  # path resolves to whichever tree we want it to scan. Returns the gate's own
  # exit status: 0 = accepted, 1 = rejected.
  run_gate() { ( cd "$2" && bash "$1/gate.sh" >/dev/null 2>&1 ); }

  plant() {
    mkdir -p "$1/.github/workflows"
    printf '%s' "$2" > "$1/.github/workflows/p.yml"
  }

  for tree in "${trees[@]}"; do
    tree="${tree%/}"
    name=$(basename "$tree")
    echo "===== $name ====="

    # Real callers, excluding the self-test's own planted `@v2.6.0` string,
    # which lives inside a printf and so never starts the line with `uses:`.
    # Counting it is the off-by-one that made 0-caller repos look covered.
    callers=$(grep -rhE '^[[:space:]]*uses:[[:space:]]*Just-Git-Dev/reusable-workflows/' \
                --include='*.yml' "$tree/.github/workflows" 2>/dev/null | wc -l | tr -d ' ')

    # 1. The gate must ACCEPT the repo's real tree — literally what CI runs on merge.
    if ! run_gate "$tree" "$tree"; then
      echo "  FAIL  real-tree: the repo's own gate REJECTS its own workflows"
      ( cd "$tree" && bash gate.sh 2>&1 | sed 's/^/          /' )
      fail=1
    elif [ "$callers" -eq 0 ]; then
      # Acceptance proves nothing when there is nothing to be accepted. Say so
      # rather than banking a pass: if someone later widens the exclusion into a
      # catch-all, this repo's real tree would keep reporting green either way.
      echo "  VACUOUS  real-tree: accepted, but 0 first-party callers present —"
      echo "           proves nothing here; coverage rests on assertion 3 below."
    else
      echo "  ok    real-tree: accepted, with $callers real first-party caller(s)"
    fi

    t=$(mktemp -d)

    # 2. Must REJECT a mutable third-party ref — the gate's whole purpose.
    plant "$t" 'on: push
jobs:
  x:
    steps:
      - uses: actions/checkout@v4
'
    if run_gate "$tree" "$t"; then
      echo "  FAIL  accepted actions/checkout@v4 — the gate is inert"; fail=1
    else
      echo "  ok    rejects actions/checkout@v4"
    fi

    # 3. Must ACCEPT a first-party reusable workflow at a release tag. This is
    #    the exemption itself, and the only coverage in a 0-caller repo.
    plant "$t" 'on: push
jobs:
  x:
    uses: Just-Git-Dev/reusable-workflows/.github/workflows/ci-go.yml@v2.6.0
'
    if run_gate "$tree" "$t"; then
      echo "  ok    accepts first-party reusable-workflows@v2.6.0"
    else
      echo "  FAIL  rejects first-party reusable-workflows@v2.6.0 — exemption missing"; fail=1
    fi

    # 4. Must REJECT another Just-Git-Dev repo at a mutable ref. Without this,
    #    an exclusion widened from the reusable-workflows path to the whole org
    #    would pass assertions 1-3 unnoticed.
    plant "$t" 'on: push
jobs:
  x:
    uses: Just-Git-Dev/other-repo/.github/workflows/x.yml@main
'
    if run_gate "$tree" "$t"; then
      echo "  FAIL  accepted Just-Git-Dev/other-repo@main — exclusion is org-wide"; fail=1
    else
      echo "  ok    rejects Just-Git-Dev/other-repo@main"
    fi

    rm -rf "$t"
  done

  echo
  [ "$fail" -eq 0 ] && echo "ALL ASSERTIONS PASSED" || echo "FAILURES PRESENT"
  exit "$fail"
fi

# --------------------------------------------------------------------------
# Host half.
# --------------------------------------------------------------------------
here=$(cd "$(dirname "$0")" && pwd)
self="$here/$(basename "$0")"

# NOT mktemp -d: on macOS that lands in /var/folders, which Docker Desktop does
# not share, and the container mount silently comes up empty. Stage under the
# working tree (shared, because $HOME is) and clean up on exit.
# Unique per run. A fixed path reused by two back-to-back runs races with
# Docker Desktop's file sharing: the second mount can come up empty against a
# directory the host has just deleted and recreated, and the run then reports a
# FAIL that belongs to no repo. Observed 2026-09-05.
work="${PIN_GATE_WORKDIR:-$PWD/.scratch/pin-gate-behaviour.$$}"

stage() {  # stage <name> <workflow-dir>
  local name="$1" wfdir="$2" dest="$work/trees/$1"
  mkdir -p "$dest/.github/workflows"
  cp "$wfdir"/*.yml "$wfdir"/*.yaml "$dest/.github/workflows/" 2>/dev/null
  if ! python3 "$here/pin_gate_extract.py" \
        "$dest/.github/workflows/workflow-hygiene.yml" "$GATE_STEP" > "$dest/gate.sh"; then
    echo "FAILED to extract the '$GATE_STEP' step from $name — cannot test it." >&2
    rm -rf "$dest"
    return 1
  fi
}

# ---- self-test: prove the red path fires ----------------------------------
if [ "${1:-}" = "--self-test" ]; then
  ref=origin/ci/workflow-hygiene
  src="${2:-$here/../../../auth/issuer}"
  rm -rf "$work"; mkdir -p "$work/trees" "$work/scripts" || exit 1
  trap 'rm -rf "$work"' EXIT
  cp "$self" "$work/scripts/pin_gate_behaviour.sh"

  base="$work/base"; mkdir -p "$base"
  git -C "$src" archive "$ref" .github/workflows | tar -x -C "$base" 2>/dev/null \
    || { echo "self-test needs a repo with the gate; pass one as \$2"; exit 2; }
  hy="$base/.github/workflows/workflow-hygiene.yml"
  [ -f "$hy" ] || { echo "no workflow-hygiene.yml in $src@$ref"; exit 2; }

  mk() {  # mk <name> <sed-program>   — a mutant of the known-good gate
    local d="$work/mut/$1"; mkdir -p "$d/.github/workflows"
    cp "$base"/.github/workflows/*.yml "$d/.github/workflows/"
    sed -i '' "$2" "$d/.github/workflows/workflow-hygiene.yml" 2>/dev/null \
      || sed -i "$2" "$d/.github/workflows/workflow-hygiene.yml"
    stage "$1" "$d/.github/workflows"
  }

  # The three ways this gate has actually been got wrong or could be.
  mk control     's/@@nothing@@/x/'
  mk no-exemption "s#| grep -v 'Just-Git-Dev/reusable-workflows/'#| cat#"
  mk org-wide     "s#grep -v 'Just-Git-Dev/reusable-workflows/'#grep -v 'Just-Git-Dev/'#"
  mk inert        "s#\[^\\./\]\[^@\]+@#@@unmatchable@@#"

  echo "--- self-test: running the harness over 1 control + 3 mutants ---"
  out="$work/self-test.out"
  docker run --rm -v "$work:/w" -w /w ubuntu:24.04 \
    bash /w/scripts/pin_gate_behaviour.sh --in-container > "$out" 2>&1
  sed 's/^/    /' "$out"
  echo
  rc=0
  chk() {  # chk <mutant> <expect-pass|expect-fail>
    local got; got=$(awk -v n="===== $1 =====" '$0==n{f=1;next} /^===== /{f=0} f' "$out" \
                     | grep -c 'FAIL')
    if [ "$2" = expect-pass ] && [ "$got" -ne 0 ]; then
      echo "SELF-TEST FAILED: control mutant '$1' reported $got failure(s)"; rc=1
    elif [ "$2" = expect-fail ] && [ "$got" -eq 0 ]; then
      echo "SELF-TEST FAILED: mutant '$1' was NOT caught — the harness is blind to it"; rc=1
    else
      echo "ok  $1: $2 ($got FAIL line(s))"
    fi
  }
  chk control      expect-pass
  chk no-exemption expect-fail
  chk org-wide     expect-fail
  chk inert        expect-fail
  echo
  [ "$rc" -eq 0 ] && echo "SELF-TEST PASSED — the harness fires on every mutant." \
                  || echo "SELF-TEST FAILED."
  exit "$rc"
fi

# ---- normal run ------------------------------------------------------------
ref_override=""
if [ "${1:-}" = "--ref" ]; then ref_override="${2:?--ref needs a value}"; shift 2; fi
[ "$#" -gt 0 ] || { sed -n '/^# USAGE/,/^# SELF-TEST/p' "$0" | sed 's/^# \?//'; exit 2; }

rm -rf "$work" && mkdir -p "$work/trees" "$work/scripts" || exit 1
trap 'rm -rf "$work"' EXIT
cp "$self" "$work/scripts/pin_gate_behaviour.sh"

absent=0
for repo in "$@"; do
  [ -d "$repo/.git" ] || { echo "skip: $repo is not a git repo"; absent=1; continue; }
  if [ -n "$ref_override" ]; then
    ref="$ref_override"
  elif git -C "$repo" rev-parse --verify -q origin/ci/workflow-hygiene >/dev/null; then
    ref=origin/ci/workflow-hygiene
  else
    ref=HEAD
  fi

  # cat-file -e errors on a missing path. `grep -c` would have returned 0 here
  # and been read as "the fix is absent" — the exact false negative this script
  # replaces. Absence of the file and absence of the fix are different facts.
  if ! git -C "$repo" cat-file -e "$ref:.github/workflows/workflow-hygiene.yml" 2>/dev/null; then
    echo "absent: $repo @ $ref has no .github/workflows/workflow-hygiene.yml"
    absent=1; continue
  fi

  name=$(printf '%s' "${repo%/}" | awk -F/ '{print $(NF-1)"_"$NF}')
  x="$work/x/$name"; mkdir -p "$x"
  git -C "$repo" archive "$ref" .github/workflows | tar -x -C "$x" || exit 1
  stage "$name" "$x/.github/workflows" || { absent=1; continue; }
  echo "extracted: $repo @ $ref -> $name"
done

[ -n "$(ls -A "$work/trees" 2>/dev/null)" ] || { echo "nothing to test"; exit 2; }
echo
docker run --rm -v "$work:/w" -w /w ubuntu:24.04 \
  bash /w/scripts/pin_gate_behaviour.sh --in-container
rc=$?
[ "$absent" -eq 0 ] || echo "NOTE: one or more repos were absent/skipped (see above)."
exit "$rc"
