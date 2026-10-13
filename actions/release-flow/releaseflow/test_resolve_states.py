"""Tests for resolve.py (live = succeeded deploys) and states.py (intermediate contract states)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import gh  # noqa: E402
import manifest  # noqa: E402
import resolve  # noqa: E402
import states  # noqa: E402
from fake_github import (CFG_DICT, FakeGitHub, LIVE, SHA_A, SHA_B, SHA_C, make_live,  # noqa: E402
                         run)

CFG = config.from_dict(CFG_DICT)
REG = "asia-southeast1-docker.pkg.dev/consumer-a-project"


def E(repo, ver, sha):
    return manifest.Entry(repo, ver, sha)


def world():
    f = FakeGitHub()
    for n in ("issuer", "api", "ui", "website", "cli"):
        f.repo(n)
    make_live(f)
    f.repo("cli").add_release("v0.3.7")
    return f


def res(f, entries, **kw):
    return resolve.resolve(gh.Reader(f), CFG, entries, **kw)


class ConfigContractsTests(unittest.TestCase):
    def test_contracts_loaded_and_validated(self):
        self.assertEqual([(c.consumer, c.provider) for c in CFG.contracts],
                         [("api", "issuer"), ("cli", "issuer"), ("ui", "api"), ("ui", "issuer")])
        for bad in ({"consumer": "ghost", "provider": "issuer"},
                    {"consumer": "api", "provider": "ghost"}, {"consumer": "api"}):
            d = json.loads(json.dumps(CFG_DICT))
            d["contracts"].append(bad)
            with self.assertRaises(config.ConfigError, msg=str(bad)):
                config.from_dict(d)

    def test_real_file_has_contracts(self):
        cfg = config.load(Path(__file__).resolve().parent / "testdata" / "services.json")
        self.assertEqual([(c.consumer, c.provider) for c in cfg.contracts],
                         [("api", "issuer"), ("cli", "issuer"), ("ui", "api"), ("ui", "issuer")])


class LiveRefTests(unittest.TestCase):
    def test_listed_and_unlisted(self):
        f = world()
        out = res(f, [E("issuer", "v0.132.0", SHA_A)])
        self.assertEqual(out["issuer"], {"ref": SHA_A, "version": "v0.132.0", "listed": True,
                                         "image": f"{REG}/backend/api:{SHA_A}",
                                         "live_ref": "v0.131.0"})
        self.assertEqual(out["api"], {"ref": "v0.37.0", "version": "v0.37.0", "listed": False,
                                      "image": f"{REG}/backend/bff-api:v0.37.0",
                                      "live_ref": "v0.37.0"})
        self.assertEqual(out["ui"]["ref"], "v0.54.0")
        self.assertIsNone(out["ui"]["image"])
        self.assertEqual(out["cli"], {"ref": "v0.3.7", "version": "v0.3.7", "listed": False,
                                      "image": None, "live_ref": "v0.3.7"})
        self.assertEqual(set(out), {"issuer", "api", "ui", "website", "cli"})

    def live(self, runs, repo="api"):
        f = world()
        f.repo(repo).live_runs = runs
        return res(f, [E("issuer", "v0.132.0", SHA_A)])[repo]["live_ref"]

    def test_most_recently_created_successful_run_wins(self):
        self.assertEqual(self.live([
            run("v0.36.0", "2026-08-01T00:00:00Z"),
            run("v0.37.0", "2026-09-01T00:00:00Z", event="push"),   # newest usable
            run("v0.98.0", "2026-10-03T00:00:00Z", conclusion="failure"),
            run("v0.97.0", "2026-10-04T00:00:00Z", event="release", conclusion=None),
        ]), "v0.37.0")

    def test_dry_run_dispatch_is_skipped(self):
        self.assertEqual(self.live([
            run("main", "2026-10-05T00:00:00Z", event="workflow_dispatch",
                title="Deploy DRYRUN v0.132.0"),
            run("v0.37.0", "2026-09-01T00:00:00Z", title="Deploy v0.37.0")]), "v0.37.0")

    def test_dispatch_of_older_tag_is_live(self):
        # a hand deploy of v0.130.0 AFTER the v0.131.0 release: prod runs v0.130.0
        f = world()
        f.repo("issuer").live_runs = [
            run("v0.131.0", "2026-10-01T00:00:00Z", title="Deploy v0.131.0"),
            run("main", "2026-10-02T00:00:00Z", event="workflow_dispatch",
                title="Deploy v0.130.0")]
        out = res(f, [E("api", "v0.38.0", SHA_B)])
        self.assertEqual(out["issuer"]["live_ref"], "v0.130.0")
        self.assertEqual(out["issuer"]["ref"], "v0.130.0")

    def test_push_to_main_run_is_skipped(self):
        self.assertEqual(self.live([
            run("v0.37.0", "2026-09-01T00:00:00Z"),
            run("main", "2026-10-01T00:00:00Z", event="push", title="fix: a commit")]),
            "v0.37.0")

    def test_dispatch_with_unparseable_title_fails_loudly(self):
        for title in ("Deploy main", "Deploy v0.1", "Some commit message"):
            with self.assertRaises(resolve.ResolveError, msg=title) as cm:
                self.live([run("v0.37.0", "2026-09-01T00:00:00Z"),
                           run("main", "2026-10-01T00:00:00Z", event="workflow_dispatch",
                               title=title)])
            self.assertIn("actions/runs/", str(cm.exception))

    def test_legacy_tag_push_run_without_title_is_used(self):
        self.assertEqual(self.live([run("v0.37.0", "2026-09-01T00:00:00Z", event="push",
                                        title="Release v0.37.0 (#12)")]), "v0.37.0")

    def test_title_wins_over_head_branch(self):
        self.assertEqual(self.live([run("v0.37.0", "2026-09-01T00:00:00Z",
                                        title="Deploy v0.36.0")]), "v0.36.0")

    def test_paginated(self):
        f = world()
        f.page_size = 2
        f.repo("ui").live_runs = [run(f"v0.{i}.0", f"2026-01-{i + 1:02d}T00:00:00Z")
                                  for i in range(7)]
        self.assertEqual(res(f, [E("issuer", "v0.132.0", SHA_A)])["ui"]["live_ref"], "v0.6.0")

    def test_no_successful_deploy_fails_loudly(self):
        for runs in (None, [], [run("main", "2026-01-01T00:00:00Z", event="push"),
                                       run("main", "2026-01-02T00:00:00Z",
                                           event="workflow_dispatch", title="Deploy DRYRUN v1.0.0")]):
            f = world()
            f.repo("website").live_runs = runs
            with self.assertRaises(resolve.ResolveError) as cm:
                res(f, [E("issuer", "v0.132.0", SHA_A)])
            self.assertIn("website", str(cm.exception))

    def test_tags_and_releases_do_not_define_live(self):
        f = world()
        f.repo("issuer").add_release("v0.5.0")
        f.repo("issuer").refs["v9.9.9"] = {"type": "commit", "sha": SHA_A}
        self.assertEqual(res(f, [E("api", "v0.38.0", SHA_B)])["issuer"]["ref"], "v0.131.0")
    def test_run_started_at_beats_created_at(self):
        # a RE-RUN of an old Deploy (rollback) keeps its original created_at
        f = world()
        old = run("v0.36.0", "2026-08-01T00:00:00Z")
        old["run_started_at"] = "2026-10-05T00:00:00Z"        # re-run last
        new = run("v0.37.0", "2026-09-20T00:00:00Z")
        new["run_started_at"] = "2026-09-20T00:00:00Z"
        f.repo("api").live_runs = [new, old]
        self.assertEqual(res(f, [E("issuer", "v0.132.0", SHA_A)])["api"]["live_ref"], "v0.36.0")
        # falls back to created_at only when run_started_at is absent
        del old["run_started_at"]
        del new["run_started_at"]
        self.assertEqual(res(f, [E("issuer", "v0.132.0", SHA_A)])["api"]["live_ref"], "v0.37.0")


class CliTagRuleTests(unittest.TestCase):
    """cli is consumers_only = non-flow: released by tag, never gets drafts. Highest vX.Y.Z tag."""

    def cli(self, f, **kw):
        return res(f, [E("issuer", "v0.132.0", SHA_A)], **kw)["cli"]["ref"]

    def test_legacy_tag_without_release_counts(self):
        f = world()
        f.repo("cli").refs["v0.4.0"] = {"type": "commit", "sha": SHA_A}
        self.assertEqual(self.cli(f), "v0.4.0")

    def test_numeric_and_non_semver(self):
        f = world()
        for t in ("v0.9.0", "v0.100.0", "vnext", "v1.2"):
            f.repo("cli").refs[t] = {"type": "commit", "sha": SHA_A}
        self.assertEqual(self.cli(f), "v0.100.0")

    def test_no_tag_is_error(self):
        f = world()
        f.repo("cli").refs.clear()
        f.repo("cli").releases.clear()
        with self.assertRaises(resolve.ResolveError):
            self.cli(f)

    def test_no_draft_visibility_or_permission_check(self):
        f = world()
        f.repo("cli").can_push = False  # would have failed the old permissions.push fallback
        self.assertEqual(self.cli(f), "v0.3.7")
        self.assertFalse([r for r in f.requests if r[1].endswith("/cli")])

    def test_drafts_proof_optional_but_checked_when_given(self):
        f = world()
        f.repo("issuer").add_release("v0.132.0", draft=True)
        self.assertEqual(self.cli(f, drafts_proof=("issuer", "v0.132.0")), "v0.3.7")

    def test_drafts_proof_not_found_fails_loudly(self):
        f = world()
        f.repo("issuer").add_release("v0.132.0")  # published, not a draft
        for proof in (("issuer", "v0.132.0"), ("issuer", "v9.9.9")):
            with self.assertRaises(resolve.ResolveError) as cm:
                self.cli(f, drafts_proof=proof)
            self.assertIn("cannot see the draft", str(cm.exception))


def state_checks(entries):
    f = world()
    resolved = res(f, entries)
    return states.contract_states(CFG, entries, resolved)


def key(c):
    return (c["consumer"], c["consumer_ref"], c["provider"], c["provider_ref"])


class StatesTests(unittest.TestCase):
    def test_issuer_plus_api_release(self):
        out = state_checks([E("issuer", "v0.132.0", SHA_A), E("api", "v0.38.0", SHA_B)])
        by = {key(c): c for c in out}
        self.assertEqual(len(by), len(out), "tuples must be deduped")
        new_i, new_a = SHA_A, SHA_B
        expect = {
            ("api", "v0.37.0", "issuer", new_i): "new issuer; live api,ui,website",
            ("api", new_a, "issuer", new_i): "new issuer,api; live ui,website",
            ("cli", "v0.3.7", "issuer", new_i): None,
            ("ui", "v0.54.0", "api", new_a): "new issuer,api; live ui,website",
            ("ui", "v0.54.0", "issuer", new_i): None,   # ui calls issuer through the BFF passthrough
        }
        self.assertEqual(set(by), set(expect))  # ui@live/api@live changes nothing: absent
        for k, label in expect.items():
            if label:
                self.assertIn(label, by[k]["states"])
        # cli vs new issuer holds in BOTH states -> labels merged
        self.assertEqual(len(by[("cli", "v0.3.7", "issuer", new_i)]["states"]), 2)

    def test_shape_for_matrix_include(self):
        out = state_checks([E("issuer", "v0.132.0", SHA_A)])
        for c in out:
            self.assertEqual(set(c), {"consumer", "consumer_ref", "provider", "provider_ref",
                                      "states", "consumer_side",
                                      "provider_live_ref"})
            self.assertIn(c["consumer_side"], ("candidate", "live"))
            self.assertIsInstance(c["states"], list)
        json.dumps(out)

    def test_consumer_side(self):
        out = state_checks([E("issuer", "v0.132.0", SHA_A), E("api", "v0.38.0", SHA_B)])
        by = {key(c): c for c in out}
        self.assertEqual(by[("api", "v0.37.0", "issuer", SHA_A)]["consumer_side"], "live")
        self.assertEqual(by[("api", SHA_B, "issuer", SHA_A)]["consumer_side"], "candidate")
        self.assertEqual(by[("cli", "v0.3.7", "issuer", SHA_A)]["consumer_side"], "live")

    def test_provider_live_ref_is_the_providers_live_tag(self):
        out = state_checks([E("issuer", "v0.132.0", SHA_A), E("api", "v0.38.0", SHA_B)])
        by = {key(c): c for c in out}
        self.assertEqual(by[("api", "v0.37.0", "issuer", SHA_A)]["provider_live_ref"], "v0.131.0")
        self.assertEqual(by[("ui", "v0.54.0", "api", SHA_B)]["provider_live_ref"], "v0.37.0")

    def test_ui_only_release(self):
        out = state_checks([E("ui", "v0.55.0", SHA_C)])
        self.assertEqual({key(c) for c in out}, {("ui", SHA_C, "api", "v0.37.0"),
                                                   ("ui", SHA_C, "issuer", "v0.131.0")})

    def test_website_only_release_is_empty(self):
        self.assertEqual(state_checks([E("website", "v0.4.0", SHA_C)]), [])

    def test_order_is_config_order_not_manifest_order(self):
        out = state_checks([E("api", "v0.38.0", SHA_B), E("issuer", "v0.132.0", SHA_A)])
        self.assertTrue(any("new issuer; live api,ui,website" in c["states"] for c in out))


if __name__ == "__main__":
    unittest.main()
