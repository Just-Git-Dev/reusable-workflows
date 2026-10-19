# Local gate == CI. `make ci` runs exactly the checks .github/workflows/ci.yml runs, in CI's
# order; ci.yml calls the same targets, so the two cannot drift (tests/run_ci_make_tests.py
# fails if they do). Tool pins below must equal SC_VERSION / AL_VERSION / PROM_VERSION in ci.yml.
SHELL := bash
.SHELLFLAGS := -eo pipefail -c

SHELLCHECK_VERSION := 0.11.0
ACTIONLINT_VERSION := 1.7.12
PROMTOOL_VERSION := 3.13.1

# Order = CI's order. Add a check by adding a target and listing it here AND in ci.yml.
CHECKS := tools actionlint canary shellcheck \
  venv catalog docs-coverage doc-anchors version-sweep stamp-tests v1-frozen v1-selftest \
  doc-examples plan-fixtures secret-plan-fixtures concurrency-groups \
  step-bodies release-gate refresh-api-spec release-flow compile-actions \
  tools-promtool alertgen alert-catalog pinned ci-gate-tests

# CI runs python3.12; prefer it, then 3.13 (the laptop's python3 may be newer).
PYBIN := $(shell command -v python3.12 || command -v python3.13 || command -v python3)
VENV := .venv
PY := $(VENV)/bin/python
# Set EXPECT=vX.Y.Z (ci.yml does, on a tag push) to also assert the tree agrees with that tag.
EXPECT ?=

.PHONY: ci hooks $(CHECKS)

ci:
	@if [ "$$(git config core.hooksPath 2>/dev/null)" != ".githooks" ]; then \
	  echo "ci: warning: pre-push hook not installed; run 'make hooks'"; fi
	@n=0; for t in $(CHECKS); do \
	  echo "== ci: $$t"; \
	  $(MAKE) --no-print-directory $$t || { echo "ci: FAILED at target '$$t' ($$n of $(words $(CHECKS)) checks passed before it)"; exit 1; }; \
	  n=$$((n+1)); \
	done; echo "ci: OK, $$n of $(words $(CHECKS)) checks ran and passed"

hooks:
	git config core.hooksPath .githooks
	@echo "pre-push hook installed (core.hooksPath=.githooks); bypass: git push --no-verify"

# Fails when a local linter differs from the version CI pins: another version is not the same gate.
tools:
	@bad=0; \
	got=$$(shellcheck --version 2>/dev/null | sed -n 's/^version: //p'); \
	[ "$$got" = "$(SHELLCHECK_VERSION)" ] || { echo "tools: shellcheck '$$got' != pinned $(SHELLCHECK_VERSION); install: brew install shellcheck (or the v$(SHELLCHECK_VERSION) release from github.com/koalaman/shellcheck)"; bad=1; }; \
	got=$$(actionlint --version 2>/dev/null | sed -n 1p); \
	[ "$$got" = "$(ACTIONLINT_VERSION)" ] || { echo "tools: actionlint '$$got' != pinned $(ACTIONLINT_VERSION); install: go install github.com/rhysd/actionlint/cmd/actionlint@v$(ACTIONLINT_VERSION) (or the release from github.com/rhysd/actionlint)"; bad=1; }; \
	[ $$bad = 0 ] && echo "tools: shellcheck $(SHELLCHECK_VERSION), actionlint $(ACTIONLINT_VERSION)"

# promtool is the alertgen oracle: a different version is a different judge. Separate from `tools`
# because only the alertgen CI job installs it.
tools-promtool:
	@got=$$(promtool --version 2>/dev/null | sed -n 's/^promtool, version \([^ ]*\).*/\1/p'); \
	[ "$$got" = "$(PROMTOOL_VERSION)" ] || { echo "tools-promtool: promtool '$$got' != pinned $(PROMTOOL_VERSION); install: the prometheus-$(PROMTOOL_VERSION) release from github.com/prometheus/prometheus/releases (put its promtool first on PATH)"; exit 1; }; \
	echo "tools-promtool: promtool $(PROMTOOL_VERSION)"

# Build .venv from the pinned requirements on first run; rebuild when the file changes.
venv: $(VENV)/.stamp
$(VENV)/.stamp: requirements-ci.txt
	$(PYBIN) -m venv $(VENV)
	$(PY) -m pip install --quiet --disable-pip-version-check -r requirements-ci.txt
	touch $@

# actionlint runs shellcheck over every `run:` body; the explicit path stops it falling back to another one.
actionlint: tools
	actionlint -shellcheck="$$(command -v shellcheck)"

# Positive control: a wrong -shellcheck path makes actionlint report success with no shellcheck at all.
canary: tools
	@d=.ci-canary; rm -rf $$d; mkdir -p $$d/.github/workflows; trap 'rm -rf $$d' EXIT; \
	printf 'on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          f=$$(ls)\n          rm $$f\n' \
	  > $$d/.github/workflows/canary.yml; \
	cd $$d; out=$$(actionlint -shellcheck="$$(command -v shellcheck)" .github/workflows/canary.yml 2>&1 || true); \
	grep -q SC2086 <<<"$$out" || { echo "::error::canary SC2086 not reported; shellcheck is not running inside actionlint"; echo "$$out"; exit 1; }; \
	echo "canary: SC2086 reported (examined 1 canary workflow)"

# actionlint only reads .github/workflows/, so a composite action's script under actions/ is never
# shellchecked by the target above. Fails on zero files once actions/ exists.
shellcheck: tools
	@files=$$(find actions -name '*.sh' -type f | sort); n=$$(printf '%s\n' "$$files" | grep -c . || true); \
	echo "shellchecking $$n script(s) under actions/"; \
	if [ -d actions ] && [ "$$n" -eq 0 ]; then echo "::error::actions/ exists but no *.sh found — the glob is broken"; exit 1; fi; \
	shellcheck $$files

# catalog.json is generated; it stays true only by failing here when a contract changes unregenerated.
catalog: venv
	$(PY) scripts/gen_catalog.py --check

# A new workflow appears in catalog.json and looks fine while never reaching the README or docs/.
docs-coverage: venv
	$(PY) scripts/check_docs_coverage.py

# Dead in-page anchors in DECISIONS.md fail silently on click, so they need a gate.
doc-anchors: venv
	$(PY) scripts/check_doc_anchors.py

# On a PR this only asserts the tree agrees with ITSELF; with EXPECT set (tag push) also with the tag.
version-sweep: venv
	$(PY) scripts/stamp_version.py --check $(if $(EXPECT),--expect "$(EXPECT)")

stamp-tests: venv
	$(PY) tests/run_stamp_tests.py

# `v1` is a frozen legacy alias; needs the tag resolvable (CI checks out with fetch-depth 0).
v1-frozen: venv
	$(PY) scripts/check_v1_frozen.py

v1-selftest: venv
	$(PY) scripts/check_v1_frozen.py --self-test

# Every complete ```yaml workflow example in docs/ is extracted and linted (a copy-paste example once
# failed at startup for everyone who used it). The examples go in a mktemp dir OUTSIDE the repo:
# actionlint resolves `./.github/workflows/x.yml` refs against the enclosing git repo.
doc-examples: tools venv
	@d=$$(mktemp -d); trap 'rm -rf "$$d"' EXIT; \
	$(PY) scripts/extract_doc_examples.py "$$d"; \
	actionlint -shellcheck="$$(command -v shellcheck)" "$$d"/.github/workflows/*.yml

# actionlint's shellcheck does not descend into `<<'PY'` heredocs: these run the shipped algorithms.
plan-fixtures: venv
	$(PY) tests/run_plan_tests.py

secret-plan-fixtures: venv
	$(PY) tests/run_secret_plan_tests.py

# Bundle writers of the same blob serialise only if their concurrency-group strings are identical.
concurrency-groups: venv
	$(PY) tests/run_concurrency_tests.py

# Step bodies run against stubbed commands and a fake clock; shellcheck lints them but never runs them.
step-bodies: venv
	$(PY) tests/run_step_tests.py

release-gate: venv
	$(PY) tests/run_check_release_gate_tests.py

refresh-api-spec: venv
	$(PY) tests/run_refresh_api_spec_tests.py

release-flow: venv
	$(PY) tests/run_release_flow_tests.py

# Every Python file under actions/ must at least compile; counts what it examined.
compile-actions: venv
	@files=$$(find actions -name '*.py' -not -path '*/testdata/*' | sort); n=$$(printf '%s\n' "$$files" | grep -c . || true); \
	[ "$$n" -gt 0 ] || { echo "::error::no Python files under actions/ (the glob is broken)"; exit 1; }; \
	$(PY) -m py_compile $$files; \
	echo "compiled $$n file(s)"

# Spec validation, golden renders, promtool oracle (fails, not skips, without promtool).
alertgen: tools-promtool venv
	$(PY) tests/run_alertgen_tests.py

alert-catalog: venv
	$(PY) scripts/gen_alert_catalog.py --check

# A moved tag on an action is a supply-chain event. Python, not `grep -P`: BSD grep has no -P, so
# locally the grep errored and the step still passed.
pinned: venv
	$(PY) scripts/check_pinned_actions.py .github/workflows actions

# The gate's own tests: ci.yml == make ci, and the pre-push hook guards.
ci-gate-tests: venv
	$(PY) tests/run_ci_make_tests.py
	$(PY) tests/run_pre_push_hook_tests.py
