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
    for n in ("core", "gateway", "web", "site", "tool"):
        f.repo(n)
    make_live(f)
    f.repo("tool").add_release("v0.3.7")
    return f


def res(f, entries, **kw):
    return resolve.resolve(gh.Reader(f), CFG, entries, **kw)


class ConfigContractsTests(unittest.TestCase):
    def test_contracts_loaded_and_validated(self):
        self.assertEqual([(c.consumer, c.provider) for c in CFG.contracts],
                         [("gateway", "core"), ("tool", "core"), ("web", "gateway"), ("web", "core")])
        for bad in ({"consumer": "ghost", "provider": "core"},
                    {"consumer": "gateway", "provider": "ghost"}, {"consumer": "gateway"}):
            d = json.loads(json.dumps(CFG_DICT))
            d["contracts"].append(bad)
            with self.assertRaises(config.ConfigError, msg=str(bad)):
                config.from_dict(d)

    def test_real_file_has_contracts(self):
        cfg = config.load(Path(__file__).resolve().parent / "testdata" / "services.json")
        self.assertEqual([(c.consumer, c.provider) for c in cfg.contracts],
                         [("gateway", "core"), ("tool", "core"), ("web", "gateway"), ("web", "core")])


class LiveRefTests(unittest.TestCase):
    def test_listed_and_unlisted(self):
        f = world()
        out = res(f, [E("core", "v0.132.0", SHA_A)])
        self.assertEqual(out["core"], {"ref": SHA_A, "version": "v0.132.0", "listed": True,
                                         "image": f"{REG}/backend/core:{SHA_A}",
                                         "live_ref": "v0.131.0"})
        self.assertEqual(out["gateway"], {"ref": "v0.37.0", "version": "v0.37.0", "listed": False,
                                      "image": f"{REG}/backend/gateway:v0.37.0",
                                      "live_ref": "v0.37.0"})
        self.assertEqual(out["web"]["ref"], "v0.54.0")
        self.assertIsNone(out["web"]["image"])
        self.assertEqual(out["tool"], {"ref": "v0.3.7", "version": "v0.3.7", "listed": False,
                                      "image": None, "live_ref": "v0.3.7"})
        self.assertEqual(set(out), {"core", "gateway", "web", "site", "tool"})

    def live(self, runs, repo="gateway"):
        f = world()
        f.repo(repo).live_runs = runs
        return res(f, [E("core", "v0.132.0", SHA_A)])[repo]["live_ref"]

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
        f.repo("core").live_runs = [
            run("v0.131.0", "2026-10-01T00:00:00Z", title="Deploy v0.131.0"),
            run("main", "2026-10-02T00:00:00Z", event="workflow_dispatch",
                title="Deploy v0.130.0")]
        out = res(f, [E("gateway", "v0.38.0", SHA_B)])
        self.assertEqual(out["core"]["live_ref"], "v0.130.0")
        self.assertEqual(out["core"]["ref"], "v0.130.0")

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
        f.repo("web").live_runs = [run(f"v0.{i}.0", f"2026-01-{i + 1:02d}T00:00:00Z")
                                  for i in range(7)]
        self.assertEqual(res(f, [E("core", "v0.132.0", SHA_A)])["web"]["live_ref"], "v0.6.0")

    def test_no_successful_deploy_fails_loudly(self):
        for runs in (None, [], [run("main", "2026-01-01T00:00:00Z", event="push"),
                                       run("main", "2026-01-02T00:00:00Z",
                                           event="workflow_dispatch", title="Deploy DRYRUN v1.0.0")]):
            f = world()
            f.repo("site").live_runs = runs
            with self.assertRaises(resolve.ResolveError) as cm:
                res(f, [E("core", "v0.132.0", SHA_A)])
            self.assertIn("site", str(cm.exception))

    def test_tags_and_releases_do_not_define_live(self):
        f = world()
        f.repo("core").add_release("v0.5.0")
        f.repo("core").refs["v9.9.9"] = {"type": "commit", "sha": SHA_A}
        self.assertEqual(res(f, [E("gateway", "v0.38.0", SHA_B)])["core"]["ref"], "v0.131.0")
    def test_run_started_at_beats_created_at(self):
        # a RE-RUN of an old Deploy (rollback) keeps its original created_at
        f = world()
        old = run("v0.36.0", "2026-08-01T00:00:00Z")
        old["run_started_at"] = "2026-10-05T00:00:00Z"        # re-run last
        new = run("v0.37.0", "2026-09-20T00:00:00Z")
        new["run_started_at"] = "2026-09-20T00:00:00Z"
        f.repo("gateway").live_runs = [new, old]
        self.assertEqual(res(f, [E("core", "v0.132.0", SHA_A)])["gateway"]["live_ref"], "v0.36.0")
        # falls back to created_at only when run_started_at is absent
        del old["run_started_at"]
        del new["run_started_at"]
        self.assertEqual(res(f, [E("core", "v0.132.0", SHA_A)])["gateway"]["live_ref"], "v0.37.0")


class ToolTagRuleTests(unittest.TestCase):
    """tool is consumers_only = non-flow: released by tag, never gets drafts. Highest vX.Y.Z tag."""

    def tool_ref(self, f, **kw):
        return res(f, [E("core", "v0.132.0", SHA_A)], **kw)["tool"]["ref"]

    def test_legacy_tag_without_release_counts(self):
        f = world()
        f.repo("tool").refs["v0.4.0"] = {"type": "commit", "sha": SHA_A}
        self.assertEqual(self.tool_ref(f), "v0.4.0")

    def test_numeric_and_non_semver(self):
        f = world()
        for t in ("v0.9.0", "v0.100.0", "vnext", "v1.2"):
            f.repo("tool").refs[t] = {"type": "commit", "sha": SHA_A}
        self.assertEqual(self.tool_ref(f), "v0.100.0")

    def test_no_tag_is_error(self):
        f = world()
        f.repo("tool").refs.clear()
        f.repo("tool").releases.clear()
        with self.assertRaises(resolve.ResolveError):
            self.tool_ref(f)

    def test_no_draft_visibility_or_permission_check(self):
        f = world()
        f.repo("tool").can_push = False  # would have failed the old permissions.push fallback
        self.assertEqual(self.tool_ref(f), "v0.3.7")
        self.assertFalse([r for r in f.requests if r[1].endswith("/tool")])

    def test_drafts_proof_optional_but_checked_when_given(self):
        f = world()
        f.repo("core").add_release("v0.132.0", draft=True)
        self.assertEqual(self.tool_ref(f, drafts_proof=("core", "v0.132.0")), "v0.3.7")

    def test_drafts_proof_not_found_fails_loudly(self):
        f = world()
        f.repo("core").add_release("v0.132.0")  # published, not a draft
        for proof in (("core", "v0.132.0"), ("core", "v9.9.9")):
            with self.assertRaises(resolve.ResolveError) as cm:
                self.tool_ref(f, drafts_proof=proof)
            self.assertIn("cannot see the draft", str(cm.exception))


def state_checks(entries):
    f = world()
    resolved = res(f, entries)
    return states.contract_states(CFG, entries, resolved)


def key(c):
    return (c["consumer"], c["consumer_ref"], c["provider"], c["provider_ref"])


class StatesTests(unittest.TestCase):
    def test_core_plus_gateway_release(self):
        out = state_checks([E("core", "v0.132.0", SHA_A), E("gateway", "v0.38.0", SHA_B)])
        by = {key(c): c for c in out}
        self.assertEqual(len(by), len(out), "tuples must be deduped")
        new_i, new_a = SHA_A, SHA_B
        expect = {
            ("gateway", "v0.37.0", "core", new_i): "new core; live gateway,web,site",
            ("gateway", new_a, "core", new_i): "new core,gateway; live web,site",
            ("tool", "v0.3.7", "core", new_i): None,
            ("web", "v0.54.0", "gateway", new_a): "new core,gateway; live web,site",
            ("web", "v0.54.0", "core", new_i): None,   # web calls core through the gateway passthrough
        }
        self.assertEqual(set(by), set(expect))  # web@live/gateway@live changes nothing: absent
        for k, label in expect.items():
            if label:
                self.assertIn(label, by[k]["states"])
        # tool vs new core holds in BOTH states -> labels merged
        self.assertEqual(len(by[("tool", "v0.3.7", "core", new_i)]["states"]), 2)

    def test_shape_for_matrix_include(self):
        out = state_checks([E("core", "v0.132.0", SHA_A)])
        for c in out:
            self.assertEqual(set(c), {"consumer", "consumer_ref", "provider", "provider_ref",
                                      "states", "consumer_side",
                                      "provider_live_ref"})
            self.assertIn(c["consumer_side"], ("candidate", "live"))
            self.assertIsInstance(c["states"], list)
        json.dumps(out)

    def test_consumer_side(self):
        out = state_checks([E("core", "v0.132.0", SHA_A), E("gateway", "v0.38.0", SHA_B)])
        by = {key(c): c for c in out}
        self.assertEqual(by[("gateway", "v0.37.0", "core", SHA_A)]["consumer_side"], "live")
        self.assertEqual(by[("gateway", SHA_B, "core", SHA_A)]["consumer_side"], "candidate")
        self.assertEqual(by[("tool", "v0.3.7", "core", SHA_A)]["consumer_side"], "live")

    def test_provider_live_ref_is_the_providers_live_tag(self):
        out = state_checks([E("core", "v0.132.0", SHA_A), E("gateway", "v0.38.0", SHA_B)])
        by = {key(c): c for c in out}
        self.assertEqual(by[("gateway", "v0.37.0", "core", SHA_A)]["provider_live_ref"], "v0.131.0")
        self.assertEqual(by[("web", "v0.54.0", "gateway", SHA_B)]["provider_live_ref"], "v0.37.0")

    def test_ui_only_release(self):
        out = state_checks([E("web", "v0.55.0", SHA_C)])
        self.assertEqual({key(c) for c in out}, {("web", SHA_C, "gateway", "v0.37.0"),
                                                   ("web", SHA_C, "core", "v0.131.0")})

    def test_website_only_release_is_empty(self):
        self.assertEqual(state_checks([E("site", "v0.4.0", SHA_C)]), [])

    def test_order_is_config_order_not_manifest_order(self):
        out = state_checks([E("gateway", "v0.38.0", SHA_B), E("core", "v0.132.0", SHA_A)])
        self.assertTrue(any("new core; live gateway,web,site" in c["states"] for c in out))


if __name__ == "__main__":
    unittest.main()
