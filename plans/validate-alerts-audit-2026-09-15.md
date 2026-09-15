# `validate-alerts.yml` vacuity audit (Item 4b, owed to AutoMahn)

Scope: `.github/workflows/validate-alerts.yml` (537 lines), cross-checked against its step-body
tests in `tests/run_step_tests.py` (~L2183-2600) and the two 2026-09-01 findings in `DECISIONS.md`
(L534-603). Read-only audit; no fixes applied.

Hunted for two shapes named in `TODO.md`/plan Item 4b:
1. a threshold compared against a value the **policy itself derives**
2. a check that **assumes a scope the policy never declares**
...plus the adjacent shape: a check that silently no-ops on an absent input/empty result.

## Findings, one per check

| path:line | check | comparand source | verdict |
|---|---|---|---|
| `validate-alerts.yml:182-183` | channel file exists | fixed input path | SOUND |
| `validate-alerts.yml:186-191` | channel file has `type`/`displayName`/`labels` | fixed key set | SOUND |
| `validate-alerts.yml:194-197` | policy glob matched ≥1 file | — | SOUND (hard `sys.exit(1)` if empty, not a silent zero-pass) |
| `validate-alerts.yml:215-216` | `displayName` present | required-field check | SOUND |
| `validate-alerts.yml:218-220` | `combiner` ∈ `{OR,AND,AND_WITH_MATCHING_RESOURCE}` | fixed external enum (GCP's) | SOUND |
| `validate-alerts.yml:224-228` | `notificationChannels` non-empty and contains `NOTIFICATION_CHANNEL_PLACEHOLDER` | fixed external constant | SOUND |
| `validate-alerts.yml:238-247` | `documentation.content` non-empty, ≥ `DOC_MIN_CHARS=80` | fixed constant (not policy-derived) | SOUND — boundary-tested both sides (`run_step_tests.py:2588-2591`, 79 fails / 81 passes) |
| `validate-alerts.yml:248-250` | `content` doesn't merely restate `displayName` (normalized equality) | **both operands come from the same document**, but they are two independently-authored fields, not one derived from the other | SOUND, not vacuous — it can genuinely fail (copy-paste doc) or pass (real triage text); tested both ways at `run_step_tests.py` ~L2405-2420. Closest candidate to class 1 but does not fit it: neither side is *computed from* the other. |
| `validate-alerts.yml:253-254` | `conditions` non-empty | — | SOUND |
| `validate-alerts.yml:261-264` | exactly one of `CONDITION_KEYS` present | fixed external enum | SOUND |
| `validate-alerts.yml:266-269` | `conditionMatchedLog.filter` non-empty | presence only | SOUND but weak — no check that the filter's resource/log scope is valid; this is an **absent** check, not a vacuous one (never claims to have validated scope) |
| `validate-alerts.yml:270-281` | MQL `query` present; RCA's `numerator:`/`denominator:` regex rejected; `duration` format | fixed regex / format rule | SOUND |
| `validate-alerts.yml:285-297` | PromQL `query` present; `duration`/`evaluationInterval` format | format rule only, no upper bound | SOUND (format check), not derived/vacuous — just unbounded, a different gap |
| `validate-alerts.yml:304-309` | log-based condition requires `alertStrategy.notificationRateLimit.period`, format-checked | conditioned on `has_log_condition`, computed earlier in the same pass from the policy's own conditions | SOUND — not self-referential in the tautological sense; the gate condition and the gated value are different fields, and both directions are exercised (absent → fails per `TODO.md`/RCA context) |
| `validate-alerts.yml:314-322` | `alertStrategy.autoClose` required, range-checked `[1800s, 604800s]` | fixed constants matching GCP's documented `30m..168h` domain | SOUND |
| `validate-alerts.yml:349,358,434` | layer 2 (query execution) entirely skipped when `gcp_project == ''` | — | **DECLARED skip, not silent**: summary step (L527-531) prints `Query execution: _skipped_`; header comment (L34) documents it up front. Not the hunted "silent no-op" shape, but worth flagging: any caller that never sets `gcp_project` gets offline-lint-only coverage and that is easy to miss without reading the summary. |
| `validate-alerts.yml:379-382`, `452-455` | MQL/PromQL query-list file must exist, not just be empty | — | SOUND — this is the exact fix for the 2026-09-01 "missing list reads as zero-and-fine" bug; verified present in both layers (PromQL got it in the same fix, MQL was the original bug) |
| `validate-alerts.yml:385-423` (MQL), `458-503` (PromQL) | live POST of every extracted query to the real Monitoring API endpoint, response classified 200/400/401\|403/other | server response, not policy-derived | SOUND — genuine round trip, not self-referential |
| `validate-alerts.yml:480-486` | PromQL 200-with-error-envelope (`.status=="error"`) is still a failure | server response body | SOUND — explicit guard against "2xx is not consent," addressed here (see code comment L478-479) |
| `validate-alerts.yml:411-417`, `492-497` | `401`/`403` → hard `exit 1`, no partial count written | — | SOUND — "could not check" never reads as "checked and fine," matches the 2026-09-01 RCA prevention list and is tested (`mql_checked`/`promql_checked` absent from outputs on 403) |

## Test-layer cross-check (the "vacuous test hides a vacuous check" shape)

Read `tests/run_step_tests.py` at the four cited anchors (~L2183 PromQL-execution intro,
~L2212/2235 PromQL/MQL lint extraction, ~L2302 MQL exec-layer setup, ~L2420 actionability
section). All exercise the **real step body** via `subprocess.run(["bash", ..., "-c", body], ...)`
against a stubbed `curl` on `PATH` that inspects real argv/response bodies (`_run_exec_layer`,
L1125-1176) — not a mock of the workflow's own logic. Boundary cases are mutation-tested in both
directions (403 fails + writes no count; missing query-list fails, not zero; 79/81-char doc
boundary; PromQL 200-with-error-envelope). No test found that merely re-asserts a hardcoded
constant against itself.

**Gap, not vacuity**: no test exists for `combiner` validity, `notificationChannels` placeholder
requirement, `autoClose` out-of-range rejection, or the log-condition rate-limit requirement
(confirmed absent — searched for `"accepted range"`, `"invalid combiner"`, `"notify nobody"`,
`"requires alertStrategy"`, none found in `run_step_tests.py`). Direct code reading (table above)
shows these checks are structurally sound regardless — they compare policy fields to fixed
external constants, not to each other — so the gap is coverage, not a hidden vacuous pass. Recorded
here because the brief asked it be tested for, not because it changes any verdict.

## Structural verdict

No live instance of either named class (self-derived comparand, assumed-and-undeclared scope) was
found in the current file. Both are absent for the same structural reason: every comparand in this
lint is either (a) a fixed constant lifted from GCP's own documented API domain (`AUTOCLOSE_MIN/MAX`,
`COMBINERS`, `CONDITION_KEYS`, `PLACEHOLDER`, `DOC_MIN_CHARS`), or (b) two independently-authored
policy fields compared for a real anti-pattern (content-restates-displayName), never a value
*computed from* the field it's then checked against. The `gcp_project` scope that layer 2 runs
against is a required `workflow_call` input, not an assumption — a caller that omits it gets an
explicit, printed "skipped" rather than a silent pass.

The two 2026-09-01 findings that *were* vacuous (MQL missing-list read as zero-and-fine; PromQL
accepted by the lint and never executed) share a different shape from the two classes named in this
audit: both were **coverage gaps in the execution layer** (a check that should have run, didn't,
and the absence of a result was read as a pass) rather than a self-referential comparand or an
undeclared scope. Both are now closed and their fixes are present and tested in the current file
(query-list-must-exist guard on both layers; PromQL execution added as its own step). So "two
independent vacuity findings in one layer" reflects that this file's *execution* half (server
round-trips) previously had zero test coverage and thus zero adversarial pressure on its
fail-open paths — not that its offline *lint* half compares things to themselves. On this audit,
the lint half holds up: every comparand traces to either GCP's documented domain or an
independent field, and the execution half's known fail-open paths (missing list, 401/403, error
envelope) are now explicitly guarded and mutation-tested. Read together with the two closed
findings, the pattern this file has repeatedly hit is "a result that never arrived counted as a
pass," not the two shapes this audit was asked to hunt — those two remain "not found," not "found
and fixed."
