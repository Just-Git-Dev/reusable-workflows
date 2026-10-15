"""Contract checks for every INTERMEDIATE state of the publish order (owner ruling H7).

A failed deploy is not rolled back, so the mix of new and old services a half-finished
release leaves behind must keep working. The order is providers first; to make that
checkable, state k (k = 1..n) is "the first k listed repos at their candidate sha, every other
repo at its live_ref"; tool is always at live. For each state and each configured
(consumer, provider) contract one check is emitted, but only when at least one side is a
candidate -- a pair entirely at live changes nothing and would just import unrelated prod
drift into the release. Identical (consumer, consumer_ref, provider, provider_ref) tuples are
deduped and their state labels merged. The result is a list of dicts shaped for a GitHub
Actions matrix `include`; an empty list is valid (e.g. a site-only release).
"""

from __future__ import annotations

import publish


def contract_states(cfg, entries, resolved):
    order = publish.order(cfg, entries)
    all_services = [s.repo for s in cfg.services]
    checks = {}  # key -> dict, insertion ordered
    for k in range(1, len(order) + 1):
        new = set(order[:k])

        def ref(repo):
            r = resolved[repo]
            return r["ref"] if repo in new else r["live_ref"]

        label = (f"new {','.join(x for x in all_services if x in new)}; "
                 f"live {','.join(x for x in all_services if x not in new)}")
        for c in cfg.contracts:
            if c.consumer not in new and c.provider not in new:
                continue
            key = (c.consumer, ref(c.consumer), c.provider, ref(c.provider))
            entry = checks.setdefault(key, {
                "consumer": key[0], "consumer_ref": key[1],
                "provider": key[2], "provider_ref": key[3], "states": [],
                "provider_live_ref": resolved[c.provider]["live_ref"],
                "consumer_side":"candidate" if c.consumer in new else "live"})
            if label not in entry["states"]:
                entry["states"].append(label)
    return list(checks.values())
