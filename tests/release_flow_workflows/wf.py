"""Helpers for the release-flow workflow-shape tests (stdlib unittest + PyYAML).

The four shared release workflows mint GitHub App tokens that can publish (= deploy), so what
these tests read is the one thing a unit test CAN read: the YAML shape. They never run a
workflow. Ported and generalised from the two shape tests of the project the flow was proven in.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
NAMES = ["release-pr-check.yml", "release-plan.yml", "release-drafts.yml", "release-publish.yml"]
MINT = "actions/create-github-app-token@"
CHECKOUT = "actions/checkout@"
SHA_RE = re.compile(r"@[0-9a-f]{40}$")
SLOTS = 6


def path(name):
    return WORKFLOWS_DIR / name


def text(name):
    return path(name).read_text()


def load(name):
    wf = yaml.safe_load(text(name))
    assert isinstance(wf, dict), name
    return wf


def on_block(wf):
    # PyYAML (YAML 1.1) reads the bare key `on` as the boolean True.
    return wf.get("on", wf.get(True)) or {}


def jobs(wf):
    return wf.get("jobs") or {}


def all_steps():
    """(file, job_name, job, step) for every step of every job of the four workflows."""
    out = []
    for n in NAMES:
        for jn, job in jobs(load(n)).items():
            for st in job.get("steps") or []:
                out.append((n, jn, job, st))
    return out


def mint_steps():
    return [t for t in all_steps() if str(t[3].get("uses", "")).startswith(MINT)]


def perms(step):
    return {k: v for k, v in (step.get("with") or {}).items() if k.startswith("permission-")}


def step_by_id(job, sid):
    for i, st in enumerate(job["steps"]):
        if st.get("id") == sid:
            return i, st
    raise KeyError(sid)
