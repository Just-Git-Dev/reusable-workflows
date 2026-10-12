#!/usr/bin/env bash
# refresh-api-spec — fetch a provider's published OpenAPI document, compare it by
# meaning with the committed copy, and if it changed: write the copy, run the
# caller's update + checks, push one fixed branch, open (or reuse) one PR, and
# merge it only if the checks passed. See docs/refresh-api-spec.md.
#
# Env (from action.yml): SPEC_NAME SPEC_URL COPY_PATH CHECK_COMMAND
#   UPDATE_COMMAND REQUEST_HEADERS MERGE_METHOD GH_TOKEN
# Runs from the caller's checkout root. Needs bash, curl, git, yq (v4), gh.
set -euo pipefail

out() { printf '%s=%s\n' "$1" "$2" >> "${GITHUB_OUTPUT:-/dev/null}"; }
die() { printf '::error::%s\n' "$*"; exit 1; }

MERGE_METHOD="${MERGE_METHOD:-squash}"
UPDATE_COMMAND="${UPDATE_COMMAND:-}"
REQUEST_HEADERS="${REQUEST_HEADERS:-}"

# ---------------------------------------------------------------- inputs
[[ "${SPEC_NAME:-}" =~ ^[A-Za-z0-9._-]+$ && "$SPEC_NAME" != *..* ]] \
  || die "name must be letters, digits, '.', '_' or '-' (got '${SPEC_NAME:-}')"
[[ -n "${SPEC_URL:-}" ]] || die "url is empty"
[[ -n "${COPY_PATH:-}" ]] || die "copy_path is empty"
[[ -n "${CHECK_COMMAND:-}" ]] || die "check_command is empty — without a check, an automatic merge proves nothing"
case "$COPY_PATH" in
  *.json) FORMAT=json ;;
  *.yaml|*.yml) FORMAT=yaml ;;
  *) die "copy_path must end in .json, .yaml or .yml (got '$COPY_PATH')" ;;
esac
case "$MERGE_METHOD" in
  squash|merge|rebase) ;;
  *) die "merge_method must be squash, merge or rebase (got '$MERGE_METHOD')" ;;
esac

BRANCH="spec-refresh/$SPEC_NAME"
TITLE="chore: refresh $SPEC_NAME API spec"
if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then export GH_REPO="$GITHUB_REPOSITORY"; fi

# Everything the update step changes is committed (git add -A), so start clean.
dirty="$(git status --porcelain)"
[[ -z "$dirty" ]] || die "working tree is not clean before the refresh; the action commits everything it changes, so it refuses to start: $(printf '%s' "$dirty" | tr '\n' ' ')"

work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/refresh-api-spec.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# ---------------------------------------------------------------- fetch
# Only the host is printed: a path or query string may carry a key.
host="$(printf '%s' "$SPEC_URL" | sed -E 's#^[A-Za-z][A-Za-z0-9+.-]*://##; s#[/?\#].*$##; s#^.*@##')"

curl_args=(-sS -L --max-time 60 -o "$work/body" -w '%{http_code}')
if [[ -n "$REQUEST_HEADERS" ]]; then
  : > "$work/headers"
  chmod 600 "$work/headers"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -n "${line//[[:space:]]/}" ]] || continue
    [[ "$line" == *:* ]] || die "request_headers: a line has no ':' (expected 'Name: value')"
    value="${line#*:}"
    value="${value#"${value%%[![:space:]]*}"}"
    [[ -z "$value" ]] || printf '::add-mask::%s\n' "$value"
    printf '%s\n' "$line" >> "$work/headers"
  done <<< "$REQUEST_HEADERS"
  curl_args+=(-H "@$work/headers")
fi

status="$(curl "${curl_args[@]}" "$SPEC_URL")" || die "fetch from $host failed (curl exit $?)"
bytes="$(wc -c < "$work/body" | tr -d ' ')"
echo "fetched $bytes bytes from $host (HTTP $status)"
[[ "$status" == "200" ]] || die "fetch from $host returned HTTP $status, expected 200"
[[ "$bytes" -gt 0 ]] || die "fetch from $host returned an empty body"

# ---------------------------------------------------------------- validate
# JSON is YAML, so one parser reads either. A body that does not parse, or is
# not a mapping with a top-level openapi/swagger key, is refused: GoFr's
# catch-all /.well-known/{name} answers 200 with the Swagger UI HTML page.
if ! yq -p=yaml -e '(tag == "!!map") and (has("openapi") or has("swagger"))' "$work/body" \
    > /dev/null 2>&1; then
  die "response from $host is not an OpenAPI document (no top-level 'openapi' or 'swagger' key) — check the url"
fi

# ---------------------------------------------------------------- compare
canon() { yq -p=yaml -o=json -I=0 'sort_keys(..)' "$1"; }
canon "$work/body" > "$work/fetched.canon"
if [[ -f "$COPY_PATH" ]]; then
  canon "$COPY_PATH" > "$work/copy.canon" || die "the committed copy $COPY_PATH does not parse"
else
  echo "no committed copy at $COPY_PATH yet — creating it"
  : > "$work/copy.canon"
fi

open_pr() { gh pr list --head "$BRANCH" --state open --json url --jq '.[0].url // empty'; }

if cmp -s "$work/fetched.canon" "$work/copy.canon"; then
  echo "$COPY_PATH matches the published document — nothing to do"
  out changed false
  out checks skipped
  pr="$(open_pr)"
  if [[ -n "$pr" ]]; then
    printf '::notice::the published document matches %s again; refresh PR %s is still open — close it if it is no longer wanted\n' \
      "$COPY_PATH" "$pr"
    out pr_url "$pr"
  fi
  exit 0
fi
out changed true
echo "the published document differs from $COPY_PATH"

# ---------------------------------------------------------------- write + update
base="$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name)"
[[ -n "$base" ]] || die "could not resolve the default branch"
git fetch --quiet origin "$base"
[[ "$(git rev-parse HEAD)" == "$(git rev-parse FETCH_HEAD)" ]] \
  || die "the checkout is not the head of the default branch '$base'; run this on '$base' so the PR carries only the refresh"

mkdir -p "$(dirname "$COPY_PATH")"
if [[ "$FORMAT" == json ]]; then
  yq -p=yaml -o=json -I=2 '.' "$work/body" > "$COPY_PATH"
else
  yq -P -p=yaml -o=yaml '.' "$work/body" > "$COPY_PATH"  # -P: block style, not JSON's flow style
fi

if [[ -n "$UPDATE_COMMAND" ]]; then
  echo "running update_command"
  bash -c "$UPDATE_COMMAND" || die "update_command failed (exit $?); nothing was pushed"
fi

# ---------------------------------------------------------------- branch + PR
git checkout --quiet -B "$BRANCH"
git add -A
# Identity via env, not -c: an inherited GIT_AUTHOR_* would override -c user.*.
bot='github-actions[bot]'
bot_email='41898282+github-actions[bot]@users.noreply.github.com'
GIT_AUTHOR_NAME="$bot" GIT_AUTHOR_EMAIL="$bot_email" \
GIT_COMMITTER_NAME="$bot" GIT_COMMITTER_EMAIL="$bot_email" \
  git commit --quiet -m "$TITLE" -m "Fetched from $host by the refresh-api-spec action."
head_sha="$(git rev-parse HEAD)"
git push --quiet --force origin "HEAD:refs/heads/$BRANCH"
echo "pushed $BRANCH at $head_sha"

run_url="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"
pr="$(open_pr)"
if [[ -n "$pr" ]]; then
  echo "updated the open refresh PR $pr"
else
  # shellcheck disable=SC2016  # the backticks are Markdown, not command substitution
  printf 'The document published at `%s` no longer matches `%s`.\n\nOpened by the `refresh-api-spec` action in %s. It merges this PR itself if `check_command` passes; otherwise the check output is commented below and the PR stays open.\n' \
    "$host" "$COPY_PATH" "$run_url" > "$work/pr-body.md"
  pr="$(gh pr create --base "$base" --head "$BRANCH" --title "$TITLE" --body-file "$work/pr-body.md")"
  echo "opened $pr"
fi
out pr_url "$pr"

# ---------------------------------------------------------------- checks + merge
echo "running check_command"
set +e
bash -c "$CHECK_COMMAND" 2>&1 | tee "$work/check.log"
rc="${PIPESTATUS[0]}"
set -e

if [[ "$rc" -ne 0 ]]; then
  out checks failed
  {
    printf 'Checks failed (exit %s) in %s — not merged.\n\nLast 60 lines:\n\n```\n' "$rc" "$run_url"
    tail -n 60 "$work/check.log"
    printf '```\n'
  } > "$work/comment.md"
  gh pr comment "$pr" --body-file "$work/comment.md" || echo "::warning::could not comment on $pr"
  die "check_command failed (exit $rc); $pr left open, not merged"
fi
out checks passed
gh pr merge "$pr" "--$MERGE_METHOD" --delete-branch --match-head-commit "$head_sha"
echo "checks passed; merged $pr"
