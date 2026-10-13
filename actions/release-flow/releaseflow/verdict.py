"""The gate in front of the drafts and publish stages: is the `needs` context good enough?

The caller passes GitHub's `toJSON(needs)`: {job_id: {"result": ..., "outputs": {...}}}. This
module decides, from that alone, whether the stage may proceed, and which job to blame when it
may not. Pure: no network, no clock.

Rules:
  - job `plan` must be present, result success, with a non-empty outputs.manifest that matches
    the release_dir manifest rule;
  - every job in `required` must be present;
  - every job present must have result success, except the contracts job, which may be skipped
    or absent ONLY when plan.outputs.checks == "[]" (otherwise it must be present and success).
"""

from __future__ import annotations

import manifest as manifest_mod

PLAN = "plan"


def _result(entry):
    return entry.get("result") if isinstance(entry, dict) else None


def _outputs(entry):
    out = entry.get("outputs") if isinstance(entry, dict) else None
    return out if isinstance(out, dict) else {}


def _text(v):
    return v if isinstance(v, str) else ""


def unparseable(why):
    """The verdict for a needs file that cannot be read as an object: not ok, blame plan."""
    return {"ok": False, "rehearsal": False, "manifest": "", "manifest_sha256": "", "pr": "",
            "order": [],
            "failed_stage": PLAN, "failures": [f"needs unreadable: {why}"]}


def judge(needs, contracts_job, required, release_dir):
    """-> dict with ok, rehearsal, manifest, pr, failed_stage, failures (no `order`)."""
    failures, bad = [], set()

    def fail(job, msg):
        bad.add(job)
        failures.append(msg)

    plan = needs.get(PLAN)
    outputs = _outputs(plan)
    manifest = _text(outputs.get("manifest"))
    if PLAN not in needs:
        fail(PLAN, "job 'plan' is missing from needs")
    elif _result(plan) != "success":
        fail(PLAN, f"job 'plan' is {_result(plan)!r}, not success")
    elif not manifest:
        fail(PLAN, "job 'plan' has no manifest output")
    elif not manifest_mod.path_ok(manifest, release_dir):
        fail(PLAN, f"plan manifest {manifest!r} is not {release_dir}/YYYY-MM-DD-<slug>.yaml")
    plan_ok = PLAN not in bad

    for job in required:
        if job not in needs:
            fail(job, f"required job {job!r} is missing from needs")
    # With no usable plan we cannot know whether contracts had work to do: be strict.
    no_checks = plan_ok and outputs.get("checks") == "[]"
    for job, entry in needs.items():
        if job == PLAN:
            continue
        result = _result(entry)
        if result == "success":
            continue
        if job == contracts_job and result == "skipped" and no_checks:
            continue
        fail(job, f"job {job!r} is {result!r}, not success")
    if contracts_job not in needs and plan_ok and not no_checks:
        fail(contracts_job, f"contracts job {contracts_job!r} is missing but plan has checks")

    ordered = [j for j in required if j in bad]
    ordered += sorted(bad - set(ordered))
    return {"ok": not bad, "rehearsal": outputs.get("rehearsal") == "true",
            "manifest": manifest, "manifest_sha256": _text(outputs.get("manifest-sha256")),
            "pr": _text(outputs.get("pr")),
            "failed_stage": ordered[0] if ordered else "", "failures": failures}
