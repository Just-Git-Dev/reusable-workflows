#!/usr/bin/env bash
# check-release-gate — read-only verdict on each service's release gate.
#
# For every {repo, tag, sha} in $SERVICES, confirm (1) the tag still resolves to
# `sha` and (2) the NEWEST `$CHECK_NAME` check run from GitHub Actions on `sha`
# completed with `success`. Never waits, starts or re-runs anything: a run that is
# queued or in progress is a failure, not something to poll. Every service is
# reported, then the step fails once if any did not pass.
#
# Inputs (env, never interpolated): GH_TOKEN, SERVICES (JSON array), CHECK_NAME.
# Outputs: `result` (JSON array) to $GITHUB_OUTPUT, a table to $GITHUB_STEP_SUMMARY.
# See docs/check-release-gate.md.
set -eo pipefail

CHECK_NAME="${CHECK_NAME:-release-gate}"
MAX_PEEL=5
N=0
M=0
RESULTS='[]'

count_line() { echo "examined ${N} services, ${M} passed"; }

die_input() {
  echo "::error::check-release-gate: invalid input — $1"
  count_line
  exit 1
}

# ---------------------------------------------------------------------------
# 1. Validate everything before the first API call.

if [[ -z "${CHECK_NAME// /}" ]]; then
  die_input "check_name is empty"
fi
if ! jq -e 'type == "array"' >/dev/null 2>&1 <<<"${SERVICES:-}"; then
  die_input "services is not a JSON array"
fi
if [[ "$(jq 'length' <<<"$SERVICES")" -eq 0 ]]; then
  die_input "services is empty — zero services is a failure, never a pass"
fi
BAD="$(jq -r '
  to_entries[]
  | .key as $i | .value as $s
  | if ($s | type) != "object" then "services[\($i)] is not an object"
    elif ($s.repo | type) != "string"
         or ($s.repo | test("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$") | not)
         or ($s.repo | split("/")[1] | IN(".", ".."))
      then "services[\($i)].repo must be owner/name"
    elif ($s.sha | type) != "string" or ($s.sha | test("^[0-9a-f]{40}$") | not)
      then "services[\($i)].sha must be a 40-character lowercase hex commit sha"
    elif ($s.tag | type) != "string" or ($s.tag | length) == 0
      then "services[\($i)].tag is empty"
    elif ($s.tag | test("^[A-Za-z0-9._][A-Za-z0-9._/-]*$") | not) or ($s.tag | contains(".."))
      then "services[\($i)].tag has characters outside [A-Za-z0-9._/-]"
    else empty end' <<<"$SERVICES")"
if [[ -n "$BAD" ]]; then
  die_input "$(paste -sd ';' <<<"$BAD")"
fi

CHECK_NAME_Q="$(jq -rn --arg s "$CHECK_NAME" '$s | @uri')"

# ---------------------------------------------------------------------------
# 2. Per service: tag, then gate. Never stop at the first failure.

API_OUT=""
API_ERR=""
# api <path> [extra gh flags...] — sets API_OUT; returns 0, or 1 with API_ERR set
# to "HTTP <code>" (or the raw message when gh printed no status).
api() {
  local path="$1" errf
  shift
  errf="$(mktemp)"
  if API_OUT="$(gh api "$@" "$path" 2>"$errf")"; then
    rm -f "$errf"
    return 0
  fi
  API_ERR="$(grep -oE 'HTTP [0-9]{3}' "$errf" | tail -n1 || true)"
  [[ -n "$API_ERR" ]] || API_ERR="$(tr '\n' ' ' <"$errf" | cut -c1-200)"
  [[ -n "$API_ERR" ]] || API_ERR="gh api failed with no message"
  rm -f "$errf"
  return 1
}

VERDICT=""
REASON=""
# check_tag <repo> <tag> <sha> — sets VERDICT/REASON on failure, returns 1.
check_tag() {
  local repo="$1" tag="$2" want="$3" type sha hops=0
  if ! api "repos/${repo}/git/ref/tags/${tag}"; then
    if [[ "$API_ERR" == "HTTP 404" ]]; then
      REASON="tag missing"
    else
      REASON="tag lookup failed (${API_ERR})"
    fi
    return 1
  fi
  type="$(jq -r '.object.type // empty' <<<"$API_OUT" 2>/dev/null || true)"
  sha="$(jq -r '.object.sha // empty' <<<"$API_OUT" 2>/dev/null || true)"
  # An annotated tag points at a tag object; follow it to the commit.
  while [[ "$type" == "tag" ]]; do
    if (( hops >= MAX_PEEL )); then
      REASON="tag did not resolve to a commit within ${MAX_PEEL} hops"
      return 1
    fi
    hops=$((hops + 1))
    if ! api "repos/${repo}/git/tags/${sha}"; then
      REASON="annotated tag lookup failed (${API_ERR})"
      return 1
    fi
    type="$(jq -r '.object.type // empty' <<<"$API_OUT" 2>/dev/null || true)"
    sha="$(jq -r '.object.sha // empty' <<<"$API_OUT" 2>/dev/null || true)"
  done
  if [[ "$type" != "commit" || -z "$sha" ]]; then
    REASON="tag resolves to an unexpected object (type=${type:-none})"
    return 1
  fi
  if [[ "$sha" != "$want" ]]; then
    REASON="tag moved: points at ${sha}"
    return 1
  fi
  return 0
}

# check_gate <repo> <sha> — sets REASON on failure, returns 1.
check_gate() {
  local repo="$1" sha="$2" newest status conclusion
  if ! api "repos/${repo}/commits/${sha}/check-runs?check_name=${CHECK_NAME_Q}&filter=all&per_page=100" \
       --paginate; then
    REASON="check-runs lookup failed (${API_ERR})"
    return 1
  fi
  # --paginate concatenates one object per page; slurp them back together.
  # Only GitHub Actions' own runs count — another app can post a same-named check.
  # Newest by started_at, ties broken by id (a re-run gets a higher id).
  if ! newest="$(jq -sc '[.[].check_runs[]?]
                         | map(select(.app.slug == "github-actions"))
                         | sort_by([(.started_at // ""), .id]) | last' <<<"$API_OUT" 2>/dev/null)"; then
    REASON="check-runs response could not be parsed"
    return 1
  fi
  if [[ -z "$newest" || "$newest" == "null" ]]; then
    REASON="no ${CHECK_NAME} run"
    return 1
  fi
  status="$(jq -r '.status // "unknown"' <<<"$newest")"
  conclusion="$(jq -r '.conclusion // "none"' <<<"$newest")"
  if [[ "$status" != "completed" ]]; then
    REASON="not finished: status=${status} (never waited on)"
    return 1
  fi
  if [[ "$conclusion" != "success" ]]; then
    REASON="conclusion=${conclusion}"
    return 1
  fi
  return 0
}

while IFS=$'\t' read -r REPO TAG SHA; do
  N=$((N + 1))
  VERDICT="fail"
  REASON=""
  if check_tag "$REPO" "$TAG" "$SHA" && check_gate "$REPO" "$SHA"; then
    VERDICT="pass"
    REASON="${CHECK_NAME} succeeded"
    M=$((M + 1))
    echo "PASS ${REPO}@${TAG} (${SHA:0:12}): ${REASON}"
  else
    echo "::error::${REPO}@${TAG} (${SHA:0:12}): ${REASON}"
  fi
  RESULTS="$(jq -c --arg repo "$REPO" --arg tag "$TAG" --arg sha "$SHA" \
                    --arg verdict "$VERDICT" --arg reason "$REASON" \
    '. + [{repo: $repo, tag: $tag, sha: $sha, verdict: $verdict, reason: $reason}]' \
    <<<"$RESULTS")"
done < <(jq -r '.[] | [.repo, .tag, .sha] | @tsv' <<<"$SERVICES")

# ---------------------------------------------------------------------------
# 3. Report.

count_line
echo "result=${RESULTS}" >>"${GITHUB_OUTPUT:-/dev/null}"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "### Release gate (\`${CHECK_NAME}\`) — ${M}/${N} passed"
    echo
    echo "| repo | tag | sha | verdict | reason |"
    echo "|---|---|---|---|---|"
    jq -r '.[] | "| \(.repo) | \(.tag) | `\(.sha[0:12])` | \(.verdict) | \(.reason | gsub("\\|"; "\\\\|")) |"' \
      <<<"$RESULTS"
  } >>"$GITHUB_STEP_SUMMARY"
fi

if (( N == 0 || M < N )); then
  echo "::error::check-release-gate: $((N - M)) of ${N} services did not pass their ${CHECK_NAME}"
  exit 1
fi
