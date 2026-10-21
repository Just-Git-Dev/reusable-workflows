#!/usr/bin/env python3
"""Red tests for the deploy-env lint (docs/deploy-env-lint.md): .github/workflows/deploy-env-lint.yml
and the script it runs, scripts/deploy_env_lint.py.

NAMES THIS FILE INVENTS (the doc fixes the files read, not the script's CLI): the script is
`scripts/deploy_env_lint.py --root <repo checkout>`; it reads `<root>/deploy/env.<stage>.yaml`
(flat KEY: value maps) and `<root>/deploy/secret-keys.txt`, prints one finding line per problem
(containing the file name and the key), exits 1 on any finding, exits 0 when clean, and prints
how many env files it examined; zero env files -> non-zero. Env var REPOS_ENV_LINT overrides the
script path (non-vacuity checks).

Rules covered: 1-8 of docs/deploy-env-lint.md. Rule 9 (several services in one repo) is NOT
covered: the doc does not say how a multi-service repo lays its files out.

Usage:  python3 tests/run_deploy_env_lint_tests.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LINT = Path(os.environ.get("REPOS_ENV_LINT", ROOT / "scripts" / "deploy_env_lint.py"))
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-env-lint.yml"

CLEAN = {
    "stage": {
        "LOG_LEVEL": "info", "DB_HOST": "db.stage.example.com", "DB_SSL_MODE": "require",
        "DB_MAX_OPEN_CONNECTION": "10", "REDIS_HOST": "redis.stage.example.com",
        "REDIS_TLS_ENABLED": "true", "REDIS_DB": "0", "PUBSUB_BACKEND": "REDIS", "REDIS_PUBSUB_DB": "0",
    },
    "prod": {
        "LOG_LEVEL": "warn", "DB_HOST": "db.prod.example.com", "DB_SSL_MODE": "require",
        "DB_MAX_OPEN_CONNECTION": "20", "REDIS_HOST": "redis.prod.example.com",
        "REDIS_TLS_ENABLED": "true", "REDIS_DB": "0", "PUBSUB_BACKEND": "REDIS", "REDIS_PUBSUB_DB": "0",
    },
}


def lint(files, secret_keys="DB_PASSWORD_BUNDLE\n", dotenv=None):
    """files: {stage: {KEY: value}}. Returns (rc, combined output)."""
    assert LINT.is_file(), "lint script %s does not exist" % LINT.name
    with tempfile.TemporaryDirectory(dir=str(ROOT / ".scratch") if (ROOT / ".scratch").is_dir() else None) as d:
        dd = Path(d) / "deploy"
        dd.mkdir()
        for stage, kv in files.items():
            (dd / ("env.%s.yaml" % stage)).write_text(yaml.safe_dump(kv))
        (dd / "secret-keys.txt").write_text(secret_keys)
        if dotenv is not None:
            (Path(d) / "configs").mkdir()
            (Path(d) / "configs" / ".env").write_text(dotenv)
        p = subprocess.run([sys.executable, str(LINT), "--root", d], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def variant(stage=None, prod=None, drop_both=(), both=None):
    f = {"stage": dict(CLEAN["stage"]), "prod": dict(CLEAN["prod"])}
    for k in drop_both:
        f["stage"].pop(k, None)
        f["prod"].pop(k, None)
    for k, v in (both or {}).items():
        f["stage"][k] = v
        f["prod"][k] = v
    f["stage"].update(stage or {})
    f["prod"].update(prod or {})
    return f


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def finding(name, files, must_name, secret_keys="DB_PASSWORD_BUNDLE\n", file_hint=None):
    """Register a case: the lint must fail (rc 1) and name the offending key (and file)."""
    def fn():
        rc, out = lint(files, secret_keys)
        assert rc == 1, "rc=%s (want 1) out=%s" % (rc, out[-300:])
        assert must_name in out, "finding does not name %r: %s" % (must_name, out[-300:])
        if file_hint:
            assert file_hint in out, "finding does not name file %r: %s" % (file_hint, out[-300:])
    fn.__name__ = name
    CASES.append(fn)


@case
def workflow_exists_is_standalone_and_needs_no_credential():
    assert WORKFLOW.is_file(), "%s does not exist" % WORKFLOW.name
    doc = yaml.safe_load(WORKFLOW.read_text())
    on = doc.get("on", doc.get(True))
    assert "workflow_call" in on, "not a reusable workflow"
    text = WORKFLOW.read_text()
    assert "id-token" not in text and "workload_identity" not in text.lower(), "lint must call no cloud"


@case
def clean_repo_passes_and_reports_files_examined():
    rc, out = lint(CLEAN)
    assert rc == 0, "rc=%s out=%s" % (rc, out[-300:])
    assert "2" in out, "output does not state how many files it examined: %s" % out[-200:]


@case
def zero_env_files_fails():
    rc, out = lint({})
    assert rc != 0, "a lint that examined nothing must fail"


# rule 1: key sets differ between stage files
finding("rule1_key_missing_in_prod_is_refused", variant(stage={"EXTRA_FLAG": "1"}), "EXTRA_FLAG",
        file_hint="env.prod.yaml")
finding("rule1_key_missing_in_stage_is_refused", variant(prod={"ONLY_PROD": "1"}), "ONLY_PROD",
        file_hint="env.stage.yaml")
# rule 2: stage-pattern host in the prod file
finding("rule2_stage_host_in_prod_file_is_refused", variant(prod={"DB_HOST": "db.stage.example.com"}), "DB_HOST",
        file_hint="env.prod.yaml")
finding("rule2_stage_redis_host_in_prod_file_is_refused", variant(prod={"REDIS_HOST": "redis.stage.example.com"}),
        "REDIS_HOST", file_hint="env.prod.yaml")
# rule 3: connection-string keys
for k in ("REDIS_URL", "DATABASE_URL", "DB_URL", "PAYMENTS_DSN"):
    finding("rule3_%s_is_refused" % k.lower(), variant(both={k: "x://example"}), k)
# rule 4: pool and lifetime tuning keys
for k in ("REDIS_POOL_SIZE", "DB_MAX_OPEN_CONN", "DB_MAX_IDLE_CONN", "DB_MAX_CONN_LIFETIME_MIN"):
    finding("rule4_%s_is_refused" % k.lower(), variant(both={k: "5"}), k)
# rule 5: redis db index / pubsub db
finding("rule5_redis_db_nonzero_is_refused", variant(both={"REDIS_DB": "1"}), "REDIS_DB")
finding("rule5_pubsub_redis_without_pubsub_db_zero_is_refused",
        variant(drop_both=("REDIS_PUBSUB_DB",)), "REDIS_PUBSUB_DB")
finding("rule5_pubsub_db_nonzero_is_refused", variant(both={"REDIS_PUBSUB_DB": "2"}), "REDIS_PUBSUB_DB")
# rule 6: unencrypted transport for non-local hosts
finding("rule6_redis_tls_false_on_remote_host_is_refused", variant(both={"REDIS_TLS_ENABLED": "false"}),
        "REDIS_TLS_ENABLED")
for mode in ("disable", "allow", "prefer"):
    finding("rule6_db_ssl_mode_%s_on_remote_host_is_refused" % mode, variant(both={"DB_SSL_MODE": mode}), "DB_SSL_MODE")
finding("rule6_db_ssl_mode_unset_on_remote_host_is_refused", variant(drop_both=("DB_SSL_MODE",)), "DB_SSL_MODE")
# rule 7: password in plain config
finding("rule7_password_key_in_env_file_is_refused", variant(both={"DB_PASSWORD": "hunter2"}), "DB_PASSWORD")
finding("rule7_any_star_password_key_is_refused", variant(both={"SMTP_PASSWORD": "hunter2"}), "SMTP_PASSWORD")
# rule 8: pool size unset where DB_HOST is set
finding("rule8_db_max_open_connection_unset_is_refused", variant(drop_both=("DB_MAX_OPEN_CONNECTION",)),
        "DB_MAX_OPEN_CONNECTION")


@case
def rule6_localhost_hosts_are_exempt_from_transport_rule():
    f = variant(both={"DB_SSL_MODE": "disable", "REDIS_TLS_ENABLED": "false"})
    for s in f:
        f[s]["DB_HOST"] = "localhost" if s == "stage" else "postgres"
        f[s]["REDIS_HOST"] = "127.0.0.1" if s == "stage" else "redis"
    rc, out = lint(f)
    assert rc == 0, "local hosts must be exempt: rc=%s out=%s" % (rc, out[-300:])


@case
def rule8_does_not_fire_when_db_host_is_unset():
    f = variant(drop_both=("DB_HOST", "DB_SSL_MODE", "DB_MAX_OPEN_CONNECTION"))
    rc, out = lint(f)
    assert rc == 0, "no DB_HOST -> rule 8 must not fire: rc=%s out=%s" % (rc, out[-300:])


@case
def findings_never_print_a_password_value():
    rc, out = lint(variant(both={"DB_PASSWORD": "hunter2-SECRET"}))
    assert rc == 1 and "hunter2-SECRET" not in out, "password value printed: %s" % out[-300:]


@case
def several_findings_are_all_reported_in_one_run():
    rc, out = lint(variant(both={"REDIS_URL": "x", "DB_PASSWORD": "p", "REDIS_DB": "3"}))
    assert rc == 1 and all(k in out for k in ("REDIS_URL", "DB_PASSWORD", "REDIS_DB")), out[-400:]


@case
def m8_key_in_env_yaml_and_secret_keys_is_a_finding():
    rc, out = lint(variant(both={"LOG_LEVEL": "info"}), secret_keys="DB_PASSWORD_BUNDLE\nLOG_LEVEL\n")
    assert rc == 1 and "LOG_LEVEL" in out and "secret-keys.txt" in out, out[-300:]


@case
def m8_key_in_dotenv_and_env_yaml_is_a_finding():
    rc, out = lint(variant(both={"LOG_LEVEL": "info"}), dotenv="LOG_LEVEL=debug\n")
    assert rc == 1 and "LOG_LEVEL" in out and "configs/.env" in out, out[-300:]


@case
def m8_key_in_dotenv_and_secret_keys_is_a_finding():
    rc, out = lint(variant(), secret_keys="DB_PASSWORD_BUNDLE\n", dotenv="DB_PASSWORD_BUNDLE=x\n")
    assert rc == 1 and "DB_PASSWORD_BUNDLE" in out and "x\n" not in out.split("DB_PASSWORD_BUNDLE")[-1][:3], out[-300:]


@case
def m8_disjoint_keys_pass():
    rc, out = lint(variant(), dotenv="ONLY_LOCAL=1\n")
    assert rc == 0, out[-300:]


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
            print("ok   %s" % fn.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (fn.__name__, str(e)[:300]))
        except Exception as e:
            failed += 1
            print("FAIL %s: %s: %s" % (fn.__name__, type(e).__name__, str(e)[:300]))
    print("%d cases run, %d failed" % (len(CASES), failed))
    return 1 if failed or not CASES else 0


if __name__ == "__main__":
    sys.exit(main())
