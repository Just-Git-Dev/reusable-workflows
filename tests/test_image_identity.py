#!/usr/bin/env python3
"""Tests for actions/image-identity/identity.py (docs/image-identity.md). No Docker needed.

The script runs as shipped (subprocess). Its `docker` is IMAGE_IDENTITY_DOCKER, pointed at a stub
that serves a pre-built tarball for `save`, a fixed RepoDigest for `inspect`, and a configurable
set of "loaded" refs for `load`/`inspect`. Tarballs are built by hand in both layouts: classic
("Config": "<hex>.json") and containerd/OCI ("Config": "blobs/sha256/<hex>").

Usage:  python3 tests/test_image_identity.py
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "actions" / "image-identity" / "identity.py"

CFG_A = hashlib.sha256(b"config-a").hexdigest()
CFG_B = hashlib.sha256(b"config-b").hexdigest()

# argv: save -o PATH REF... | image inspect [--format F] REF | load -i PATH
DOCKER_STUB = r'''#!/usr/bin/env python3
import os, shutil, sys
a = sys.argv[1:]
if a[:1] == ["save"]:
    shutil.copy(os.environ["STUB_TAR"], a[a.index("-o") + 1]); sys.exit(0)
if a[:2] == ["image", "inspect"]:
    ref = a[-1]
    loaded = os.environ.get("STUB_LOADED")
    if "--format" in a:
        print(os.environ.get("STUB_REPO_DIGEST", "repo@sha256:" + "d" * 64)); sys.exit(0)
    sys.exit(0 if loaded is None or ref in loaded.split(",") else 1)
if a[:1] == ["load"]:
    sys.exit(0)
if a[:1] == ["info"]:
    drv = os.environ.get("STUB_DRIVER")
    if drv is None:
        sys.exit(1)
    print(drv); sys.exit(0)
sys.exit(2)
'''


def manifest_entry(layout, cfg, tag):
    config = f"{cfg}.json" if layout == "classic" else f"blobs/sha256/{cfg}"
    return {"Config": config, "RepoTags": [tag], "Layers": []}


def make_tar(path, entries, raw_manifest=None):
    with tarfile.open(path, "w") as t:
        data = raw_manifest if raw_manifest is not None else json.dumps(entries).encode()
        ti = tarfile.TarInfo("manifest.json")
        ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.d = Path(self._td.name)
        (self.d / "docker").write_text(DOCKER_STUB)
        (self.d / "docker").chmod(0o755)
        self.out = self.d / "gh_output"
        self.summary = self.d / "summary"
        self.src = self.d / "src.tar"
        self.path = self.d / "images.tar"

    def run_script(self, mode, loaded=None, **env):
        e = {k: v for k, v in os.environ.items() if not k.startswith(("ID_", "STUB_"))}
        e.update(IMAGE_IDENTITY_DOCKER=str(self.d / "docker"), STUB_TAR=str(self.src),
                 GITHUB_OUTPUT=str(self.out), GITHUB_STEP_SUMMARY=str(self.summary),
                 ID_MODE=mode)
        if loaded is not None:
            e["STUB_LOADED"] = loaded
        e.update({k: str(v) for k, v in env.items()})
        return subprocess.run([sys.executable, str(SCRIPT)], env=e, capture_output=True, text=True)

    def outputs(self):
        return dict(l.split("=", 1) for l in self.out.read_text().splitlines() if "=" in l)

    def record(self, entries, images, **kw):
        make_tar(self.src, entries)
        return self.run_script("record", ID_IMAGES=images, ID_PATH=self.path, **kw)


class RecordTests(Base):
    def test_record_classic_layout(self):
        r = self.record([manifest_entry("classic", CFG_A, "alpine:3.20")], "alpine:3.20")
        self.assertEqual(r.returncode, 0, r.stderr)
        o = self.outputs()
        self.assertEqual(o["tar_sha256"], sha(self.path))
        ident = json.loads(o["identity"])
        self.assertEqual(ident["alpine:3.20"]["config"], f"sha256:{CFG_A}")
        self.assertEqual(ident["alpine:3.20"]["repo_digest"], "repo@sha256:" + "d" * 64)
        self.assertEqual(json.loads(Path(f"{self.path}.identity.json").read_text()), ident)
        self.assertNotIn(" ", o["identity"], "identity must be compact JSON")

    def test_record_oci_layout(self):
        r = self.record([manifest_entry("oci", CFG_B, "alpine:3.20")], "alpine:3.20")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.outputs()["identity"])["alpine:3.20"]["config"],
                         f"sha256:{CFG_B}")

    def test_record_two_refs_mixed_layouts_and_normalised_tags(self):
        r = self.record([manifest_entry("classic", CFG_A, "alpine:3.20"),
                         manifest_entry("oci", CFG_B, "docker.io/library/busybox:latest")],
                        "alpine:3.20\nbusybox\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        ident = json.loads(self.outputs()["identity"])
        self.assertEqual(ident["alpine:3.20"]["config"], f"sha256:{CFG_A}")
        self.assertEqual(ident["busybox"]["config"], f"sha256:{CFG_B}")

    def test_record_missing_ref_in_manifest_fails(self):
        r = self.record([manifest_entry("classic", CFG_A, "alpine:3.20")], "alpine:3.20\nnginx:1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)
        self.assertIn("nginx:1", r.stdout + r.stderr)

    def test_record_digest_ref_fails_with_tag_hint(self):
        r = self.record([manifest_entry("classic", CFG_A, "alpine:3.20")], "alpine@sha256:" + "e" * 64)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("digest ref", r.stdout + r.stderr)
        self.assertIn("docker tag", r.stdout + r.stderr)
        self.assertFalse(self.path.exists(), "a digest ref must be refused before docker save runs")

    def test_image_store_is_reported_and_never_fatal(self):
        # The store is diagnostic: it shows in the log which store each side really had, so a CI
        # round trip can be checked to have crossed stores. An unreadable `docker info` is not an error.
        cases = [('[["driver-type","io.containerd.snapshotter.v1"]]', "image store: containerd"),
                 ('[["Backing Filesystem","extfs"]]', "image store: classic"),
                 (None, "image store: unknown")]
        for drv, want in cases:
            with self.subTest(drv=drv):
                env = {} if drv is None else {"STUB_DRIVER": drv}
                r = self.record([manifest_entry("classic", CFG_A, "alpine:3.20")], "alpine:3.20", **env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(want, r.stdout)

    def test_record_empty_images_fails(self):
        r = self.record([manifest_entry("classic", CFG_A, "alpine:3.20")], " \n\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_record_empty_path_fails(self):
        make_tar(self.src, [])
        r = self.run_script("record", ID_IMAGES="alpine:3.20", ID_PATH="")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_record_garbage_manifest_fails(self):
        make_tar(self.src, None, raw_manifest=b"not json{")
        r = self.run_script("record", ID_IMAGES="alpine:3.20", ID_PATH=self.path)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_record_bad_config_value_fails(self):
        bad = {"Config": "blobs/sha256/zzz", "RepoTags": ["alpine:3.20"]}
        r = self.record([bad], "alpine:3.20")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_record_empty_repo_digest_fails(self):
        r = self.record([manifest_entry("classic", CFG_A, "alpine:3.20")], "alpine:3.20",
                        STUB_REPO_DIGEST="")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)


class VerifyTests(Base):
    def recorded(self, layout="classic"):
        r = self.record([manifest_entry(layout, CFG_A, "alpine:3.20")], "alpine:3.20")
        self.assertEqual(r.returncode, 0, r.stderr)
        o = self.outputs()
        return o["tar_sha256"], o["identity"]

    def verify(self, tar_sha256, identity, **kw):
        return self.run_script("verify", ID_PATH=self.path, ID_TAR_SHA256=tar_sha256,
                               ID_IDENTITY=identity, **kw)

    def test_verify_ok_both_layouts_and_summary(self):
        for layout in ("classic", "oci"):
            with self.subTest(layout=layout):
                t, i = self.recorded(layout)
                r = self.verify(t, i)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(f"sha256:{CFG_A}", self.summary.read_text())

    def test_verify_tampered_byte_fails(self):
        t, i = self.recorded()
        b = bytearray(self.path.read_bytes())
        b[-1] ^= 0xFF
        self.path.write_bytes(bytes(b))
        r = self.verify(t, i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_verify_missing_ref_after_load_fails(self):
        t, i = self.recorded()
        r = self.verify(t, i, loaded="something-else:1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("alpine:3.20", r.stdout + r.stderr)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_verify_empty_hash_never_equals_empty(self):
        self.recorded()
        r = self.verify("", json.dumps({"alpine:3.20": {"config": f"sha256:{CFG_A}",
                                                          "repo_digest": "x"}}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_verify_empty_identity_fails(self):
        t, _ = self.recorded()
        for ident in ("", "{}", "null"):
            with self.subTest(identity=ident):
                r = self.verify(t, ident)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("::error::", r.stdout + r.stderr)

    def test_verify_garbage_identity_fails(self):
        t, _ = self.recorded()
        r = self.verify(t, "not json")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_verify_missing_tarball_fails(self):
        t, i = self.recorded()
        self.path.unlink()
        r = self.verify(t, i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)


class ModeTests(Base):
    def test_unknown_or_empty_mode_fails(self):
        for m in ("", "load", "RECORD"):
            with self.subTest(mode=m):
                r = self.run_script(m)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("::error::", r.stdout + r.stderr)

    def test_id_is_never_used(self):
        self.assertTrue(SCRIPT.exists(), "identity.py missing")
        code = SCRIPT.read_text() + (SCRIPT.parent / "action.yml").read_text()
        self.assertNotIn("{{.Id}}", code)
        self.assertNotIn(".Id}}", code)


if __name__ == "__main__":
    unittest.main(verbosity=1)
