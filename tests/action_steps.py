"""Step-body access for composite actions (`runs.steps`), mirroring `extract_step` in
run_step_tests.py (which reads `jobs.<job>.steps`).

A composite action keeps its logic in scripts beside action.yml (so `make shellcheck` lints it) and
each step is `run: '"$GITHUB_ACTION_PATH/<name>.sh"'`. The step-body runners execute a body under
`bash -eo pipefail -c`, so `extract_action_step` returns the SCRIPT's text with its header (shebang,
comments, `set -eo pipefail`) removed: the same string the old inline `run:` body was, which keeps
the "three bundle writers are byte-identical" check meaningful while the two rotators are still
inline.

`job_steps` is the one entry point a workflow-level test needs: it returns a job's steps, and when
the job is a thin wrapper (a step `uses:` this repo's `actions/<name>@...`) it returns that action's
steps instead, each with `run` resolved to the script body and the script path in `_script`.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTIONS = ROOT / "actions"

SCRIPT_REF = re.compile(r'^"?\$GITHUB_ACTION_PATH/([A-Za-z0-9._-]+\.sh)"?\s*$')
ACTION_REF = re.compile(r"^Just-Git-Dev/reusable-workflows/actions/([A-Za-z0-9._-]+)@")
SET_LINE = re.compile(r"^set -eo pipefail$", re.M)


def action_dir(action):
    """`action` is an action name ('sync-bundle-key'), a directory, or an action.yml path."""
    p = Path(action)
    if p.name == "action.yml":
        return p.parent
    return p if p.is_absolute() else ACTIONS / str(action)


def script_body(path: Path) -> str:
    """The script minus its header: everything after the `set -eo pipefail` line."""
    text = path.read_text()
    m = SET_LINE.search(text)
    return text[m.end():].lstrip("\n") if m else text


def resolve_run(step: dict, adir: Path):
    """The `run:` text of an action step with a script reference replaced by the script body."""
    run = step.get("run")
    if run is None:
        return None
    m = SCRIPT_REF.match(run.strip())
    return script_body(adir / m.group(1)) if m else run


def action_steps(action):
    adir = action_dir(action)
    doc = yaml.safe_load((adir / "action.yml").read_text())
    out = []
    for st in doc["runs"]["steps"]:
        st = dict(st)
        run = st.get("run")
        m = SCRIPT_REF.match(run.strip()) if run else None
        if m:
            st["_script"] = adir / m.group(1)
            st["run"] = script_body(adir / m.group(1))
        out.append(st)
    return out


def extract_action_step(action, step_name: str):
    """Body of a named step of a composite action, or None when there is no such `run` step."""
    for st in action_steps(action):
        if st.get("name") == step_name and "run" in st:
            return st["run"]
    return None


def job_steps(workflow: Path, job: str):
    """A job's steps; a wrapper job (it `uses:` this repo's action) yields the action's steps."""
    doc = yaml.safe_load(Path(workflow).read_text())
    steps = doc["jobs"][job]["steps"]
    for st in steps:
        m = ACTION_REF.match(st.get("uses", ""))
        if m and (ACTIONS / m.group(1) / "action.yml").exists():
            return action_steps(m.group(1))
    return steps
