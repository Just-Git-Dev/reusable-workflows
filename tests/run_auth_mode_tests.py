"""v6 auth modes: every workflow that needs a GitHub credential takes EITHER a GitHub App
(`client-id` + its private key) OR a caller `github-token`, never both and never neither.

Files covered (the 9 of v6.0.0 item #3, plans/2026-11-01-v6-auth-client-id-and-token.md):
  .github/workflows/{release-plan,release-drafts,release-publish,repos-create,repos-environments,
  repos-settings,repos-variables,distribute-env-secrets,rotate-external-secret}.yml
  actions/rotate-external-secret/{action.yml,validate-auth.sh}
(rotate-external-secret.yml is a thin wrapper: its guard and mint live in the composite action.)

What this pins:
  * structure: no app-id / app_id input or `with:` key; `client-id` (`client_id`) input optional;
    the key secret and `github-token` optional; every mint is gated on the client id being non-empty
    and passes `client-id:`; every consumer of a mint token falls back to the caller token.
  * the guard step ("Refuse unless exactly one credential mode") is one body, byte-identical in the
    8 workflows and in validate-auth.sh (trailing newlines ignored), env CLIENT_ID / KEY_SET /
    TOKEN_SET, and runs before every mint in the first job.
  * behaviour: the guard body is extracted and run under `bash -eo pipefail -c` for every
    credential combination, asserting rc and the exact `::error::` message.

Run: .venv/bin/python tests/run_auth_mode_tests.py
"""

import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from action_steps import ACTIONS, action_steps  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
ACTION_DIR = ACTIONS / "rotate-external-secret"
ACTION_YML = ACTION_DIR / "action.yml"
VALIDATE_AUTH = ACTION_DIR / "validate-auth.sh"

GUARD = "Refuse unless exactly one credential mode"
MINT_RE = re.compile(r"^actions/create-github-app-token@")
MINT_TOKEN_RE = re.compile(r"steps\.([A-Za-z0-9_-]+)\.outputs\.token(?![A-Za-z0-9_])")
TOKEN = "github-token"

# workflow -> (client-id input, key secret)
WORKFLOWS = {
    "release-plan": ("client-id", "RELEASE_APP_KEY"),
    "release-drafts": ("client-id", "RELEASE_APP_KEY"),
    "release-publish": ("client-id", "RELEASE_APP_KEY"),
    "repos-create": ("client-id", "REPO_ADMIN_APP_KEY"),
    "repos-settings": ("client-id", "REPO_ADMIN_APP_KEY"),
    "repos-variables": ("client-id", "REPO_ADMIN_APP_KEY"),
    "repos-environments": ("client_id", "app_key"),
    "distribute-env-secrets": ("client_id", "app_key"),
}
WRAPPER = "rotate-external-secret"

MSG_BOTH = "pass the App or github-token, not both"
MSG_NEITHER = "no credentials: pass the App (client-id and its private key) or github-token"
MSG_NO_ID = "App incomplete: missing client-id"
MSG_NO_KEY = "App incomplete: missing private key"
# (label, CLIENT_ID, KEY_SET, TOKEN_SET, expected message or None for success)
COMBOS = [
    ("App only", "Iv23liAbCdEf", "true", "false", None),
    ("token only", "", "false", "true", None),
    ("both", "Iv23liAbCdEf", "true", "true", MSG_BOTH),
    ("neither", "", "false", "false", MSG_NEITHER),
    ("client-id only + token", "Iv23liAbCdEf", "false", "true", MSG_BOTH),
    ("key only", "", "true", "false", MSG_NO_ID),
    ("key only + token", "", "true", "true", MSG_BOTH),
    ("client-id only", "Iv23liAbCdEf", "false", "false", MSG_NO_KEY),
]

CASES = 0
FAILURES = []


def check(name, cond, detail=""):
    global CASES
    CASES += 1
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}"[:500])
        FAILURES.append(name)


def load(path):
    return yaml.safe_load(Path(path).read_text())


def call_of(doc):
    on = doc.get("on") or doc.get(True)
    return on["workflow_call"]


def mint_steps(steps):
    return [s for s in steps if MINT_RE.match(s.get("uses", ""))]


def guard_in(steps):
    return [s for s in steps if s.get("name") == GUARD]


def norm(expr):
    return re.sub(r"\s+", "", str(expr))


def guard_bodies():
    """label -> guard `run` text (None when the step or script is missing)."""
    out = {}
    for wf in WORKFLOWS:
        doc = load(WF / f"{wf}.yml")
        for jn, job in doc["jobs"].items():
            g = guard_in(job.get("steps", []))
            if g:
                out[f"{wf}:{jn}"] = g[0].get("run")
        if not any(k.startswith(wf + ":") for k in out):
            out[wf] = None
    out["validate-auth.sh"] = None
    if VALIDATE_AUTH.is_file() and ACTION_YML.is_file():
        try:
            g = guard_in(action_steps(ACTION_DIR))
            out["validate-auth.sh"] = g[0].get("run") if g else None
        except OSError:
            pass
    return out


def run_guard(body, client_id, key_set, token_set):
    p = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", body],
        env={"PATH": "/usr/bin:/bin", "CLIENT_ID": client_id, "KEY_SET": key_set, "TOKEN_SET": token_set},
        capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


def workflow_cases():
    print("\nworkflows: inputs, secrets, mints, guard placement")
    for wf, (idname, keyname) in WORKFLOWS.items():
        path = WF / f"{wf}.yml"
        text = path.read_text()
        doc = yaml.safe_load(text)
        call = call_of(doc)
        ins, secs = call.get("inputs", {}), call.get("secrets", {})
        check(f"{wf}: no app-id / app_id input", not {"app-id", "app_id"} & set(ins), sorted(ins))
        check(f"{wf}: input {idname} exists and is optional",
              idname in ins and ins[idname].get("required") is not True, ins.get(idname))
        check(f"{wf}: secret {keyname} exists and is optional",
              keyname in secs and secs[keyname].get("required") is not True, secs.get(keyname))
        check(f"{wf}: secret {TOKEN} exists and is optional",
              TOKEN in secs and secs[TOKEN].get("required") is not True, secs.get(TOKEN))
        check(f"{wf}: no inputs.app-id / inputs.app_id expression left", not re.search(r"inputs\.app[-_]id", text))

        mints = []
        for jn, job in doc["jobs"].items():
            for s in mint_steps(job.get("steps", [])):
                mints.append((jn, s))
        check(f"{wf}: has at least one mint step", len(mints) >= 1, len(mints))
        gate = f"inputs.{idname}!=''"
        for jn, s in mints:
            tag = f"{wf}/{jn}/{s.get('id')}"
            w = s.get("with", {})
            check(f"{tag}: mint passes client-id from inputs.{idname}, not app-id",
                  norm(w.get("client-id")) == "${{inputs.%s}}" % idname and "app-id" not in w, w)
            check(f"{tag}: mint is gated on the client id being non-empty",
                  gate in norm(s.get("if", "")), s.get("if"))
        mint_ids = {s.get("id") for _, s in mints}
        bare = []
        for m in MINT_TOKEN_RE.finditer(text):
            if m.group(1) in mint_ids and not re.match(r"\s*\|\|\s*secrets\.github-token\s*\}\}", text[m.end():]):
                bare.append(text[max(0, m.start() - 40):m.end() + 40].replace("\n", " "))
        check(f"{wf}: every mint-token consumer falls back to `|| secrets.{TOKEN}`", not bare, bare[:2])

        # guard placement: the guard is the first step (only "Refuse*" may precede) of EVERY job
        # that mints, each such job declares `environment:`, and no job without a mint has one.
        n_mint_jobs = n_guards = 0
        for jn, job in doc["jobs"].items():
            steps = job.get("steps", [])
            g = guard_in(steps)
            has_mint = bool(mint_steps(steps))
            tag = f"{wf}:{jn}"
            if not has_mint:
                check(f"{tag}: no guard in a job without a mint", not g, len(g))
                continue
            n_mint_jobs += 1
            n_guards += len(g)
            check(f"{tag}: exactly one guard step '{GUARD}'", len(g) == 1, len(g))
            if len(g) != 1:
                continue
            gi = steps.index(g[0])
            before = [s.get("name", "") for s in steps[:gi]]
            check(f"{tag}: guard is first (only Refuse* before it)",
                  all(str(n).startswith("Refuse") for n in before), before)
            check(f"{tag}: no mint runs before the guard", not mint_steps(steps[:gi]), before)
            if wf.startswith("release-"):
                check(f"{tag}: job with a mint and guard declares environment:", bool(job.get("environment")),
                      job.get("environment"))
            check(f"{tag}: guard declares shell: bash", g[0].get("shell") == "bash" or
                  (doc.get("defaults", {}).get("run", {}).get("shell") == "bash"), g[0])
            env = {k: norm(v) for k, v in (g[0].get("env") or {}).items()}
            want = {"CLIENT_ID": "${{inputs.%s}}" % idname, "KEY_SET": "${{secrets.%s!=''}}" % keyname,
                    "TOKEN_SET": "${{secrets.%s!=''}}" % TOKEN}
            check(f"{tag}: guard env is exactly CLIENT_ID / KEY_SET / TOKEN_SET", env == want, env)
            check(f"{tag}: guard run has no ${{{{ }}}} expression", "${{" not in g[0].get("run", ""))
        check(f"{wf}: examined {n_mint_jobs} minting job(s), each with its own guard",
              n_mint_jobs >= 1 and n_guards == n_mint_jobs, (n_mint_jobs, n_guards))


def wrapper_cases():
    print("\nrotate-external-secret wrapper")
    path = WF / f"{WRAPPER}.yml"
    text = path.read_text()
    doc = yaml.safe_load(text)
    call = call_of(doc)
    ins, secs = call["inputs"], call["secrets"]
    check("wrapper: no app_id / app-id input", not {"app_id", "app-id"} & set(ins), sorted(ins))
    check("wrapper: input client_id exists and is optional",
          "client_id" in ins and ins["client_id"].get("required") is not True, ins.get("client_id"))
    check("wrapper: secret app_key exists and is optional",
          "app_key" in secs and secs["app_key"].get("required") is not True, secs.get("app_key"))
    check(f"wrapper: secret {TOKEN} exists and is optional",
          TOKEN in secs and secs[TOKEN].get("required") is not True, secs.get(TOKEN))
    check("wrapper: no inputs.app_id expression left", not re.search(r"inputs\.app[-_]id", text))
    steps = doc["jobs"]["rotate"]["steps"]
    calls = [s for s in steps if "actions/rotate-external-secret@" in s.get("uses", "")]
    w = calls[0].get("with", {}) if calls else {}
    check("wrapper: forwards client_id unchanged", norm(w.get("client_id")) == "${{inputs.client_id}}", w.get("client_id"))
    check("wrapper: no app_id forwarded", "app_id" not in w, sorted(w))
    check(f"wrapper: forwards secrets.{TOKEN} as {TOKEN}", norm(w.get(TOKEN)) == "${{secrets.github-token}}", w.get(TOKEN))
    check("wrapper: forwards app_key by static name", norm(w.get("app_key")) == "${{secrets.app_key}}", w.get("app_key"))


def action_cases():
    print("\nactions/rotate-external-secret: inputs, mint, guard")
    text = ACTION_YML.read_text()
    doc = yaml.safe_load(text)
    ins = doc["inputs"]
    check("action: no app_id input", "app_id" not in ins, sorted(ins))
    check("action: client_id input exists and is optional",
          "client_id" in ins and ins["client_id"].get("required") is not True, ins.get("client_id"))
    check("action: app_key input is optional", "app_key" in ins and ins["app_key"].get("required") is not True, ins.get("app_key"))
    check(f"action: {TOKEN} input exists and is optional",
          TOKEN in ins and ins[TOKEN].get("required") is not True, ins.get(TOKEN))
    check("action: no inputs.app_id expression left", not re.search(r"inputs\.app[-_]id", text))
    steps = doc["runs"]["steps"]
    mints = mint_steps(steps)
    check("action: exactly one mint step", len(mints) == 1, len(mints))
    for s in mints:
        w = s.get("with", {})
        check("action: mint passes client-id from inputs.client_id, not app-id",
              norm(w.get("client-id")) == "${{inputs.client_id}}" and "app-id" not in w, w)
        check("action: mint is gated on client_id being non-empty", "inputs.client_id!=''" in norm(s.get("if", "")), s.get("if"))
    ids = {s.get("id") for s in mints}
    bare = []
    for m in MINT_TOKEN_RE.finditer(text):
        if m.group(1) in ids and not re.match(r"\s*\|\|\s*inputs\.github-token\s*\}\}", text[m.end():]):
            bare.append(text[max(0, m.start() - 30):m.end() + 40].replace("\n", " "))
    check(f"action: every mint-token consumer falls back to `|| inputs.{TOKEN}`", not bare, bare[:2])
    g = guard_in(steps)
    check(f"action: exactly one guard step '{GUARD}'", len(g) == 1, len(g))
    if len(g) == 1:
        gi = steps.index(g[0])
        check("action: the guard runs before the mint", not mint_steps(steps[:gi]))
        check("action: guard runs validate-auth.sh with shell: bash",
              g[0].get("shell") == "bash" and "validate-auth.sh" in g[0].get("run", ""), g[0])
        env = {k: norm(v) for k, v in (g[0].get("env") or {}).items()}
        want = {"CLIENT_ID": "${{inputs.client_id}}", "KEY_SET": "${{inputs.app_key!=''}}",
                "TOKEN_SET": "${{inputs.github-token!=''}}"}
        check("action: guard env is exactly CLIENT_ID / KEY_SET / TOKEN_SET", env == want, env)
    inp = next((s for s in steps if s.get("name") == "Validate inputs"), {})
    check("action: Validate inputs gets CLIENT_ID, not APP_ID",
          "CLIENT_ID" in (inp.get("env") or {}) and "APP_ID" not in (inp.get("env") or {}), inp.get("env"))


def body_cases():
    print("\nguard body: byte-identical across the 8 workflows and validate-auth.sh")
    check("validate-auth.sh exists", VALIDATE_AUTH.is_file(), "actions/rotate-external-secret/validate-auth.sh is missing")
    bodies = guard_bodies()
    check("every workflow has guard bodies and validate-auth.sh was found",
          all(b is not None for b in bodies.values()), sorted(k for k, b in bodies.items() if b is None))
    found = {k: b.rstrip("\n") for k, b in bodies.items() if b is not None}
    check("guard body is non-empty and mentions the four messages",
          bool(found) and all(m in b for b in found.values() for m in (MSG_BOTH, MSG_NEITHER, MSG_NO_ID, MSG_NO_KEY)),
          "bodies missing a settled message")
    check("all found guard bodies are identical", len(set(found.values())) == 1 and len(found) >= 9, f"{len(found)} found, {len(set(found.values()))} distinct")
    return bodies


def behaviour_cases(bodies):
    print("\nguard behaviour under bash -eo pipefail -c")
    for label, body in bodies.items():
        if body is None:
            check(f"{label}: guard body available to run", False, "no guard step / script to extract")
            continue
        for combo, cid, key, tok, msg in COMBOS:
            rc, out = run_guard(body, cid, key, tok)
            errs = [ln for ln in out.splitlines() if ln.startswith("::error::")]
            if msg is None:
                check(f"{label}: {combo} passes", rc == 0 and not errs, f"rc={rc} out={out!r}")
            else:
                check(f"{label}: {combo} is refused with the settled message",
                      rc == 1 and errs == ["::error::" + msg], f"rc={rc} out={out!r}")


def main():
    workflow_cases()
    wrapper_cases()
    action_cases()
    bodies = body_cases()
    behaviour_cases(bodies)
    print(f"\n{CASES} cases ran, {len(FAILURES)} failed")
    return 1 if FAILURES or CASES == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
