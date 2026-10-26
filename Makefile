# Local gate == CI. `make ci` runs exactly the checks .github/workflows/ci.yml runs, in CI's
# order; ci.yml calls the same targets, so the two cannot drift (tests/run_ci_make_tests.py
# fails if they do). Tool pins below must equal SC_VERSION / AL_VERSION / PROM_VERSION in ci.yml.
SHELL := bash
.SHELLFLAGS := -eo pipefail -c

SHELLCHECK_VERSION := 0.11.0
ACTIONLINT_VERSION := 1.7.12
ZIZMOR_VERSION := 1.31.1
PROMTOOL_VERSION := 3.13.1
# From the v3.13.1 release's sha256sums.txt; linux-amd64 must equal PROM_SHA256 in ci.yml.
PROMTOOL_SHA256_darwin-arm64 := 28d1f1224b2a22f84c801487fad4b3bd58f94a8cb58cf9340557e787030c9703
PROMTOOL_SHA256_darwin-amd64 := bc6cef4bdbeb3d0974ac161684dd2a0c4d4e341a13a4a634917b1c09d0f33fc5
PROMTOOL_SHA256_linux-amd64 := 962b812371aff838d152b6ff2d56fdb7a6396f5542f48ebf73421b9721f0d103
# A fetched promtool (see tools-promtool) goes first on PATH for every target.
export PATH := $(CURDIR)/.tools/bin:$(PATH)

# Order = CI's order. Add a check by adding a target and listing it here AND in ci.yml.
CHECKS := tools actionlint canary shellcheck preflight zizmor \
  venv catalog docs-coverage doc-anchors version-sweep stamp-tests v1-frozen v1-selftest \
  doc-examples plan-fixtures secret-plan-fixtures repos-plan-fixtures concurrency-groups \
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
#
# When PATH has no promtool of exactly that version, the pinned release for this OS/arch is
# fetched into the gitignored .tools/bin (first on PATH, see above), its sha256 verified against
# the values from the release's sha256sums.txt. A checksum mismatch or an unsupported platform
# fails loudly. CI installs promtool itself first, so this never downloads there.
tools-promtool:
	@have() { promtool --version 2>/dev/null | sed -n 's/^promtool, version \([^ ]*\).*/\1/p'; }; \
	if [ "$$(have)" != "$(PROMTOOL_VERSION)" ]; then \
	  arch=$$(uname -m); case "$$arch" in x86_64) arch=amd64;; aarch64) arch=arm64;; esac; \
	  plat=$$(uname -s | tr 'A-Z' 'a-z')-$$arch; \
	  case "$$plat" in \
	    darwin-arm64) sha=$(PROMTOOL_SHA256_darwin-arm64);; \
	    darwin-amd64) sha=$(PROMTOOL_SHA256_darwin-amd64);; \
	    linux-amd64) sha=$(PROMTOOL_SHA256_linux-amd64);; \
	    *) echo "tools-promtool: unsupported platform '$$plat' (have: darwin-arm64 darwin-amd64 linux-amd64); install promtool $(PROMTOOL_VERSION) by hand and put it first on PATH"; exit 1;; \
	  esac; \
	  echo "tools-promtool: '$$(have)' != pinned $(PROMTOOL_VERSION); fetching the $$plat release into .tools/"; \
	  tb=prometheus-$(PROMTOOL_VERSION).$$plat.tar.gz; mkdir -p .tools/bin; \
	  curl -sSfL -o ".tools/$$tb" "https://github.com/prometheus/prometheus/releases/download/v$(PROMTOOL_VERSION)/$$tb"; \
	  got=$$( (sha256sum ".tools/$$tb" 2>/dev/null || shasum -a 256 ".tools/$$tb") | cut -d' ' -f1); \
	  [ "$$got" = "$$sha" ] || { echo "tools-promtool: CHECKSUM MISMATCH for $$tb: got $$got, want $$sha"; rm -f ".tools/$$tb"; exit 1; }; \
	  tar -xzf ".tools/$$tb" -C .tools --strip-components=1 "prometheus-$(PROMTOOL_VERSION).$$plat/promtool"; \
	  mv .tools/promtool .tools/bin/promtool; rm -f ".tools/$$tb"; \
	fi; \
	[ "$$(have)" = "$(PROMTOOL_VERSION)" ] || { echo "tools-promtool: promtool '$$(have)' != pinned $(PROMTOOL_VERSION) after fetch"; exit 1; }; \
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
	@export EXPECT; \
	$(PY) scripts/stamp_version.py --check $${EXPECT:+--expect "$$EXPECT"}

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

# Repos-as-code planners (docs/repos-register.md): pure planners, fixture-tested with no cloud.
repos-plan-fixtures: venv
	$(PY) tests/run_repos_plan_tests.py
	$(PY) tests/run_repos_wif_plan_tests.py
	$(PY) tests/run_repos_sa_plan_tests.py
	$(PY) tests/run_repos_deploy_plan_tests.py
	$(PY) tests/run_repos_secrets_tests.py
	$(PY) tests/run_repos_apply_step_tests.py
	$(PY) tests/run_repos_env_plan_tests.py

# Bundle writers of the same blob serialise only if their concurrency-group strings are identical.
concurrency-groups: venv
	$(PY) tests/run_concurrency_tests.py

# Step bodies run against stubbed commands and a fake clock; shellcheck lints them but never runs them.
step-bodies: venv
	$(PY) tests/run_step_tests.py
	$(PY) tests/run_sync_v4_tests.py
	$(PY) tests/run_rotator_action_tests.py
	$(PY) tests/run_rotate_external_tests.py
	$(PY) tests/run_deploy_env_tests.py
	$(PY) tests/run_distribute_env_tests.py
	$(PY) tests/run_deploy_env_lint_tests.py
	$(PY) tests/run_rollback_pin_tests.py
	$(PY) tests/run_cloud_run_update_env_tests.py
	$(PY) tests/run_step_env_wiring_tests.py

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
	$(PY) tests/run_pinned_actions_tests.py
	$(PY) scripts/check_pinned_actions.py .github/workflows actions

# The gate's own tests: ci.yml == make ci, and the pre-push hook guards.
ci-gate-tests: venv
	$(PY) tests/run_ci_make_tests.py
	$(PY) tests/run_pre_push_hook_tests.py

# Vendored workflow-preflight (scripts/workflow_preflight.py, config .workflow-preflight.json):
# pinned lint + canary + SHA pins, CI-vs-laptop job parity, reusable-workflow call contracts, and
# the static half of the secret/variable reference check. No network except the one git ls-remote
# that verifies a pinned reusable-workflow tag (lint prints a WARNING, never silence, if offline).
preflight: tools
	python3 scripts/workflow_preflight.py lint
	python3 scripts/workflow_preflight.py parity
	python3 scripts/workflow_preflight.py calls
	python3 scripts/workflow_preflight.py refs --static

# zizmor security audit of the workflows and composite actions, default persona, policy in
# zizmor.yml. --offline: the online audits need a token, and a PR from a fork must not be handed
# one. Only the lint job installs zizmor, so its version check lives here, not in `tools`.
# Asserts files exist so "no findings" cannot mean "looked at nothing".
zizmor:
	@got=$$(zizmor --version 2>/dev/null | awk '{print $$2}'); \
	[ "$$got" = "$(ZIZMOR_VERSION)" ] || { echo "zizmor: '$$got' != pinned $(ZIZMOR_VERSION); install: brew install zizmor (or the v$(ZIZMOR_VERSION) release from github.com/zizmorcore/zizmor)"; exit 1; }
	@n=$$(ls .github/workflows/*.yml | wc -l | tr -d ' '); [ "$$n" -gt 0 ] || { echo "zizmor: no workflows found"; exit 1; }
	zizmor --offline --no-progress --config zizmor.yml .github/workflows actions
	@echo "zizmor: audited $$(ls .github/workflows/*.yml | wc -l | tr -d ' ') workflow files plus actions/"
