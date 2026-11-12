#!/usr/bin/env python3
"""image-identity: prove two jobs handled the same image bytes (docs/image-identity.md).

Stdlib only. Inputs arrive as env vars (ID_MODE, ID_IMAGES, ID_PATH, ID_TAR_SHA256, ID_IDENTITY).
`docker` is $IMAGE_IDENTITY_DOCKER (default `docker`) so the tests can stub it.

`docker image inspect .Id` is never used: it is the config digest on the classic image store and
the manifest/index digest on the containerd store. The config digest is read from the tarball's
own manifest.json instead, which is the same on both. Every failure is a non-zero exit with an
`::error::` line; an empty value is never equal to anything.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile

HEX64 = re.compile(r"[0-9a-f]{64}")


class Fail(Exception):
    pass


def docker(*args):
    return subprocess.run([os.environ.get("IMAGE_IDENTITY_DOCKER") or "docker", *args],
                          capture_output=True, text=True)


def need(name):
    v = os.environ.get(name, "").strip()
    if not v:
        raise Fail(f"input {name.removeprefix('ID_').lower()} is empty")
    return v


def sha256_file(path):
    if not os.path.isfile(path):
        raise Fail(f"tarball {path} does not exist")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_ref(ref):
    """Name docker was given vs the name in RepoTags can differ in registry/library/:latest."""
    r = ref.strip()
    for p in ("index.docker.io/", "docker.io/"):
        if r.startswith(p):
            r = r[len(p):]
    if r.startswith("library/"):
        r = r[len("library/"):]
    last = r.rsplit("/", 1)[-1]
    if "@" not in r and ":" not in last:
        r += ":latest"
    return r


def config_hex(value):
    """Classic `<hex>.json` or containerd/OCI `blobs/sha256/<hex>` -> the 64 hex chars."""
    if not isinstance(value, str):
        raise Fail(f"manifest Config is not a string: {value!r}")
    h = value.removeprefix("blobs/sha256/").removesuffix(".json")
    if not HEX64.fullmatch(h):
        raise Fail(f"manifest Config {value!r} is neither <hex>.json nor blobs/sha256/<hex>")
    return h


def manifest_configs(path):
    """{normalised ref: config hex} from the tarball's own manifest.json."""
    try:
        with tarfile.open(path) as t:
            member = t.extractfile("manifest.json")
            if member is None:
                raise Fail(f"{path}: manifest.json is not a file")
            entries = json.loads(member.read().decode("utf-8"))
    except Fail:
        raise
    except (KeyError, tarfile.TarError, OSError, ValueError) as e:
        raise Fail(f"cannot read manifest.json from {path}: {e}")
    if not isinstance(entries, list) or not entries:
        raise Fail(f"{path}: manifest.json is not a non-empty list")
    out = {}
    for e in entries:
        if not isinstance(e, dict):
            raise Fail(f"{path}: manifest.json entry is not an object")
        cfg = config_hex(e.get("Config"))
        for tag in e.get("RepoTags") or []:
            out[norm_ref(tag)] = cfg
    return out


def emit_output(name, value):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def image_store():
    """Diagnostic only: which image store this daemon uses. Never fails the action."""
    r = docker("info", "--format", "{{json .DriverStatus}}")
    if r.returncode != 0 or not r.stdout.strip():
        return "unknown"
    return "containerd" if "io.containerd.snapshotter" in r.stdout else "classic"


def record():
    refs = [r.strip() for r in os.environ.get("ID_IMAGES", "").splitlines() if r.strip()]
    if not refs:
        raise Fail("input images is empty")
    path = need("ID_PATH")
    for ref in refs:
        if "@" in ref:
            raise Fail(f"{ref} is a digest ref; docker save records no RepoTags for it. "
                       "`docker tag` it to a name:tag first and pass that (docs/image-identity.md)")
    print(f"image store: {image_store()}")
    r = docker("save", "-o", path, *refs)
    if r.returncode != 0:
        raise Fail(f"docker save failed: {r.stderr.strip()}")
    tar_sha = sha256_file(path)
    configs = manifest_configs(path)
    identity = {}
    for ref in refs:
        cfg = configs.get(norm_ref(ref))
        if not cfg:
            raise Fail(f"{ref} is not in the tarball's manifest.json (RepoTags: {sorted(configs)})")
        r = docker("image", "inspect", "--format", "{{index .RepoDigests 0}}", ref)
        repo_digest = r.stdout.strip()
        if r.returncode != 0 or not repo_digest:
            raise Fail(f"cannot read RepoDigests[0] of {ref}: {r.stderr.strip() or 'empty'}")
        identity[ref] = {"config": f"sha256:{cfg}", "repo_digest": repo_digest}
    blob = json.dumps(identity, separators=(",", ":"), sort_keys=True)
    with open(f"{path}.identity.json", "w", encoding="utf-8") as fh:
        fh.write(blob + "\n")
    emit_output("tar_sha256", tar_sha)
    emit_output("identity", blob)
    print(f"recorded {len(identity)} image(s); tarball sha256 {tar_sha}")


def verify():
    path = need("ID_PATH")
    want = need("ID_TAR_SHA256").lower()
    raw = need("ID_IDENTITY")
    if not HEX64.fullmatch(want):
        raise Fail(f"tar_sha256 {want!r} is not 64 hex characters")
    try:
        identity = json.loads(raw)
    except ValueError as e:
        raise Fail(f"identity is not valid JSON: {e}")
    if not isinstance(identity, dict) or not identity:
        raise Fail("identity is empty or not an object; nothing to verify")
    print(f"image store: {image_store()}")
    got = sha256_file(path)
    if got != want:
        raise Fail(f"tarball sha256 {got} != recorded {want}: the artifact is not what was pulled")
    r = docker("load", "-i", path)
    if r.returncode != 0:
        raise Fail(f"docker load failed: {r.stderr.strip()}")
    missing = [ref for ref in identity if docker("image", "inspect", ref).returncode != 0]
    if missing:
        raise Fail(f"image(s) missing after docker load: {', '.join(missing)}")
    lines = ["### image identity (verified)", "", f"tarball sha256: `{got}`", "",
             "| image | config digest | repo digest |", "|---|---|---|"]
    for ref, v in identity.items():
        if not isinstance(v, dict) or not v.get("config"):
            raise Fail(f"identity entry for {ref} has no config digest")
        lines.append(f"| `{ref}` | `{v['config']}` | `{v.get('repo_digest', '')}` |")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    text = "\n".join(lines) + "\n"
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)


def main():
    try:
        mode = os.environ.get("ID_MODE", "")
        if mode == "record":
            record()
        elif mode == "verify":
            verify()
        else:
            raise Fail(f"mode must be 'record' or 'verify', got {mode!r}")
    except Fail as e:
        print(f"::error::image-identity: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
