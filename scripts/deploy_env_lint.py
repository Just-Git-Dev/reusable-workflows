#!/usr/bin/env python3
"""Lint a service repo's committed deploy env files (docs/deploy-env-lint.md, rules 1-8).

Reads <root>/deploy/env.<stage>.yaml (flat KEY: value maps) and <root>/deploy/secret-keys.txt,
prints one finding line per problem (file and key; a value only where the value is the problem and
never for a *_PASSWORD key), prints how many env files it examined, exits 1 on any finding and
exits 1 when it examined zero env files (a lint that looked at nothing proves nothing).

Rule 9 (datastore keys differing between several services of one repo) is not implemented: the
doc does not say how a multi-service repo lays its files out.

Usage:  python3 scripts/deploy_env_lint.py --root <repo checkout> [--deploy-dir deploy]
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

LOCAL_HOSTS = {"localhost", "127.0.0.1", "redis", "postgres"}
CONN_STRING = re.compile(r"^(REDIS_URL|DATABASE_URL|DB_URL|.*_DSN)$")
TUNING = {"REDIS_POOL_SIZE", "DB_MAX_OPEN_CONN", "DB_MAX_IDLE_CONN", "DB_MAX_CONN_LIFETIME_MIN"}
STAGE_HOST = re.compile(r"(^|[.\-_])stag(e|ing)([.\-_]|$)", re.I)
BAD_SSL = {"", "disable", "allow", "prefer"}


def norm(v):
    """YAML turns an unquoted true/0 into bool/int; compare as the string the env var would be."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip()


def load(path):
    data = yaml.safe_load(path.read_text())
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("%s is not a flat KEY: value map" % path.name)
    return {str(k): norm(v) for k, v in data.items()}


def lint_file(name, env, is_prod):
    out = []
    for k in sorted(env):
        if CONN_STRING.match(k):
            out.append("%s: %s: connection-string key is refused (use the discrete host/port keys)" % (name, k))
        if k in TUNING:
            out.append("%s: %s: pool/lifetime tuning key is refused" % (name, k))
        if k.endswith("_PASSWORD"):
            out.append("%s: %s: a password in plain config is refused (it belongs in the bundle secret)" % (name, k))
        if is_prod and k.endswith("_HOST") and STAGE_HOST.search(env[k]):
            out.append("%s: %s: stage-pattern host %r in the prod file" % (name, k, env[k]))
    redis_host = env.get("REDIS_HOST", "")
    db_host = env.get("DB_HOST", "")
    if redis_host and redis_host not in LOCAL_HOSTS:
        if "REDIS_DB" in env and env["REDIS_DB"] != "0":
            out.append("%s: REDIS_DB: must be 0 on a managed serverless host, got %r" % (name, env["REDIS_DB"]))
        if env.get("REDIS_TLS_ENABLED") != "true":
            out.append("%s: REDIS_TLS_ENABLED: must be true for host %s, got %r"
                       % (name, redis_host, env.get("REDIS_TLS_ENABLED", "")))
        if env.get("PUBSUB_BACKEND") == "REDIS" and env.get("REDIS_PUBSUB_DB") != "0":
            out.append("%s: REDIS_PUBSUB_DB: must be 0 when PUBSUB_BACKEND=REDIS, got %r"
                       % (name, env.get("REDIS_PUBSUB_DB", "")))
    if db_host:
        if db_host not in LOCAL_HOSTS and env.get("DB_SSL_MODE", "").lower() in BAD_SSL:
            out.append("%s: DB_SSL_MODE: must be set and not disable/allow/prefer for host %s, got %r"
                       % (name, db_host, env.get("DB_SSL_MODE", "")))
        if not env.get("DB_MAX_OPEN_CONNECTION"):
            out.append("%s: DB_MAX_OPEN_CONNECTION: must be set where DB_HOST is set" % name)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repo checkout")
    ap.add_argument("--deploy-dir", default="deploy", help="directory under root holding the env files")
    a = ap.parse_args()
    d = Path(a.root) / a.deploy_dir
    files = sorted(d.glob("env.*.yaml")) if d.is_dir() else []
    print("deploy-env-lint: examined %d env file(s): %s" % (len(files), ", ".join(f.name for f in files) or "none"))
    if not files:
        print("deploy-env-lint: no env files under %s; a lint that examined nothing proves nothing" % d)
        return 1
    findings, envs = [], {}
    for f in files:
        try:
            envs[f.name] = load(f)
        except (ValueError, yaml.YAMLError) as e:
            findings.append("%s: unreadable: %s" % (f.name, str(e).splitlines()[0]))
    for n, env in envs.items():
        findings += lint_file(n, env, n == "env.prod.yaml")
    names = sorted(envs)
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            for k in sorted(set(envs[x]) - set(envs[y])):
                findings.append("%s: %s: key present in %s but missing here" % (y, k, x))
            for k in sorted(set(envs[y]) - set(envs[x])):
                findings.append("%s: %s: key present in %s but missing here" % (x, k, y))
    sk = d / "secret-keys.txt"
    sk_keys = set()
    if sk.is_file():
        sk_keys = {ln.strip() for ln in sk.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    dotenv = Path(a.root) / "configs" / ".env"
    dot_keys = set()
    if dotenv.is_file():
        for ln in dotenv.read_text().splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                dot_keys.add(ln.split("=", 1)[0].replace("export ", "").strip())
    # MIGRATION-v4 item 3: a key lives in exactly one of configs/.env, env.<stage>.yaml,
    # secret-keys.txt. Names only, never values.
    for n_, env in envs.items():
        for k in sorted(set(env) & sk_keys):
            findings.append("%s: %s: also listed in secret-keys.txt (a key lives in one place)" % (n_, k))
        for k in sorted(set(env) & dot_keys):
            findings.append("%s: %s: also set in configs/.env (a key lives in one place)" % (n_, k))
    for k in sorted(dot_keys & sk_keys):
        findings.append("configs/.env: %s: also listed in secret-keys.txt (a key lives in one place)" % k)
    if sk.is_file():
        n = len(sk_keys)
        print("deploy-env-lint: secret-keys.txt lists %d bundle key(s)" % n)
    for line in findings:
        print("FINDING " + line)
    print("deploy-env-lint: %d finding(s) in %d file(s)" % (len(findings), len(files)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
