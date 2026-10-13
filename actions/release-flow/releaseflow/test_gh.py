"""Tests for gh.py: the Writer allowlist is the safety property of the whole flow."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gh  # noqa: E402
from fake_github import FakeGitHub, OWNER, SHA_A  # noqa: E402

P = f"repos/{OWNER}/issuer"


def writer():
    fake = FakeGitHub()
    fake.repo("issuer")
    return fake, gh.Writer(fake)


class AllowlistTests(unittest.TestCase):
    def test_allowlist_is_exactly_these_three(self):
        # Adding a fourth write is a deliberate edit to this test. The flow creates NO tags
        # and NO refs: the owner pushes the annotated tag (J1).
        self.assertEqual(gh.ALLOWED_CALLS, (
            "POST repos/{o}/{r}/releases  body.draft is true",
            "PATCH repos/{o}/{r}/releases/{id}  body == {\"draft\": false}",
            "POST repos/{o}/{r}/actions/runs/{id}/rerun-failed-jobs  no body",
        ))

    def test_rerun_failed_jobs_allowed_only_exactly(self):
        fake, w = writer()
        fake.repo("issuer").stage_draft("v1.0.0", SHA_A)
        fake.repo("issuer").published_tag = "v1.0.0"
        w.rerun_failed(OWNER, "issuer", 2)
        self.assertEqual(fake.writes(), [("POST", f"{P}/actions/runs/2/rerun-failed-jobs", None)])

    def test_every_other_actions_endpoint_is_refused(self):
        forbidden = [
            ("POST", "actions/runs/2/rerun", None),
            ("POST", "actions/runs/2/cancel", None),
            ("POST", "actions/runs/2/force-cancel", None),
            ("POST", "actions/runs/2/approve", None),
            ("POST", "actions/jobs/2/rerun", None),
            ("POST", "actions/workflows/deploy.yml/dispatches", {"ref": "main"}),
            ("PUT", "actions/workflows/deploy.yml/enable", None),
            ("PUT", "actions/workflows/deploy.yml/disable", None),
            ("POST", "actions/workflows/deploy.yml/enable", None),
            ("DELETE", "actions/runs/2", None),
            ("DELETE", "actions/runs/2/logs", None),
            ("DELETE", "actions/caches/1", None),
            ("DELETE", "actions/secrets/X", None),
            ("PUT", "actions/secrets/X", {"encrypted_value": "x"}),
            ("GET", "actions/runs/2", None),
            ("POST", "actions/runs/abc/rerun-failed-jobs", None),
            ("POST", "actions/runs/2/rerun-failed-jobs?x=1", None),
            ("POST", "actions/runs/2/rerun-failed-jobs", {"enable_debug_logging": True}),
            ("POST", "actions/runs/2/rerun-failed-jobs/", None),
            ("PATCH", "actions/runs/2/rerun-failed-jobs", None),
            ("PUT", "actions/runs/2/rerun-failed-jobs", None),
        ]
        for method, rest, body in forbidden:
            self.refused(method, f"{P}/{rest}", body)

    def test_allowed_calls_pass_and_hit_transport(self):
        fake, w = writer()
        s, rel = w.request("POST", f"{P}/releases", {"tag_name": "v1.0.0", "name": "v1.0.0",
                                                      "draft": True,
                                                      "generate_release_notes": True})
        s, _ = w.request("PATCH", f"{P}/releases/{rel['id']}", {"draft": False})
        self.assertEqual(s, 200)
        self.assertEqual([r[0] for r in fake.writes()], ["POST", "PATCH"])

    def test_tag_and_ref_creation_are_refused(self):
        tag = {"tag": "v1.0.0", "message": "v1.0.0", "object": SHA_A, "type": "commit"}
        self.refused("POST", f"{P}/git/tags", tag)
        self.refused("POST", f"{P}/git/refs", {"ref": "refs/tags/v1.0.0", "sha": SHA_A})
        self.assertFalse(hasattr(gh.Writer, "create_tag"))
        self.assertFalse(hasattr(gh.Writer, "create_ref"))

    def refused(self, method, path, body=None):
        fake, w = writer()
        with self.assertRaises(gh.Refused, msg=f"{method} {path} {body}"):
            w.request(method, path, body)
        self.assertEqual(fake.requests, [], "a refused call must never reach the transport")

    def test_refusals(self):
        self.refused("DELETE", f"{P}/git/refs/tags/v1.0.0")
        self.refused("DELETE", f"{P}/releases/1")
        self.refused("GET", f"{P}/releases")  # Writer is not a reader
        self.refused("POST", f"{P}/git/refs", {"ref": "refs/heads/main", "sha": SHA_A})
        self.refused("POST", f"{P}/git/refs", {"ref": "refs/tags/v1.0", "sha": SHA_A})
        self.refused("POST", f"{P}/git/refs", {"ref": "refs/tags/v1.0.0x", "sha": SHA_A})
        self.refused("POST", f"{P}/git/refs", {"ref": "refs/tags/v1.0.0\nx", "sha": SHA_A})
        self.refused("POST", f"{P}/releases", {"tag_name": "v1.0.0", "draft": False})
        self.refused("POST", f"{P}/releases", {"tag_name": "v1.0.0"})
        self.refused("POST", f"{P}/releases", {"tag_name": "v1.0.0", "draft": "true"})
        self.refused("PATCH", f"{P}/releases/5", {"draft": False, "name": "x"})
        self.refused("PATCH", f"{P}/releases/5", {"draft": True})
        self.refused("PATCH", f"{P}/releases/5", {"draft": 0})
        self.refused("PATCH", f"{P}/releases/5", {})
        self.refused("PATCH", f"{P}/releases/5", None)
        self.refused("PATCH", f"{P}/releases/abc", {"draft": False})
        self.refused("PATCH", f"{P}/git/refs/tags/v1.0.0", {"sha": SHA_A, "force": True})
        self.refused("PUT", f"{P}/releases/5", {"draft": False})
        self.refused("POST", f"{P}/git/tags?x=1", {"tag": "v1.0.0"})
        self.refused("POST", f"{P}/issues", {"title": "x"})
        self.refused("POST", f"{P}/releases/5/assets", {})

    def test_helpers_raise_on_http_error(self):
        fake, w = writer()
        fake.fail.append(("POST", "/releases", 422))
        with self.assertRaises(gh.GitHubError):
            w.create_draft(OWNER, "issuer", "v1.0.0")

    def test_reader_has_no_write_surface(self):
        r = gh.Reader(FakeGitHub())
        self.assertFalse(hasattr(r, "request"))
        self.assertFalse(any(hasattr(r, n) for n in ("post", "patch", "delete", "put")))

    def test_reader_paginates_until_empty(self):
        fake = FakeGitHub(page_size=2)
        repo = fake.repo("issuer")
        for i in range(5):
            repo.add_release(f"v0.0.{i}")
        got = gh.Reader(fake).paginate(f"{P}/releases")
        self.assertEqual(len(got), 5)

    def test_paginate_refuses_an_endpoint_that_ignores_page(self):
        # git/matching-refs returns every ref on every page (real GitHub, 2026-10-09); a
        # paginate() over it must fail fast and say why, not loop to the 200-page cap.
        fake = FakeGitHub()
        fake.repo("issuer").add_tag("v0.1.0", "a" * 40)
        with self.assertRaisesRegex(gh.GitHubError, "not paginated"):
            gh.Reader(fake).paginate(f"{P}/git/matching-refs/tags/v")

    def test_semver_tags_reads_unpaginated_matching_refs_once(self):
        import validate
        fake = FakeGitHub(page_size=2)
        repo = fake.repo("issuer")
        for i in range(5):
            repo.add_tag(f"v0.{i}.0", f"{i}" * 40)
        tags = validate.semver_tags(gh.Reader(fake), P)
        self.assertEqual([t for _, t in tags], [f"v0.{i}.0" for i in range(5)])


if __name__ == "__main__":
    unittest.main()
