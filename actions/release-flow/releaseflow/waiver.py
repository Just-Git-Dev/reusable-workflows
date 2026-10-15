"""The `breaking-approved` waiver: a spec-compat break of a LIVE consumer ships in one release when
the owner labels the root release PR and its body lists every break exactly.

The block (PR body), one line per break, pair first; the text after `|` is the spec-compat
finding exactly as printed after `INCOMPATIBLE `:

    ```breaking
    webapp -> backend | POST /login: body/extra_fields: property removed in candidate
    ```

Rules (docs/release-flow.md § Contract checks): R1 label and block come together; R2 one block,
every line parses, no duplicates, every pair a configured contract; R3 every listed pair has a
live-consumer check in `checks`; R4 (spec_compat) listed findings are WAIVED, unlisted ones and
listed ones that did not occur fail; R5 a real release counts the label only if it was on the
PR before `merged_at`; R6 (spec_compat) a failure prints a paste-ready block. Stdlib only.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import NamedTuple

LABEL = "breaking-approved"
_NAME = r"[a-z0-9][a-z0-9._-]*"
_PAIR_RE = re.compile(rf"^({_NAME}) -> ({_NAME})$")
_LINE_RE = re.compile(rf"^({_NAME}) -> ({_NAME}) \| (\S.*)$")
_OPEN_RE = re.compile(r"^```breaking[ \t]*$")
_CLOSE_RE = re.compile(r"^```[ \t]*$")


class WaiverError(Exception):
    pass


class Entry(NamedTuple):
    consumer: str
    provider: str
    finding: str

    @property
    def pair(self):
        return f"{self.consumer} -> {self.provider}"

    @property
    def line(self):
        return f"{self.pair} | {self.finding}"


def parse_pair(text):
    m = _PAIR_RE.match(text or "")
    if not m:
        raise WaiverError(f"pair {text!r} is not 'consumer -> provider' (repo names)")
    return m.group(1), m.group(2)


def parse_block(body):
    """-> None when the body has no ```breaking block, else its entries (R2 syntax)."""
    lines = (body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks, cur = [], None
    for raw in lines:
        if cur is None:
            if _OPEN_RE.match(raw.strip()):
                cur = []
        elif _CLOSE_RE.match(raw.strip()):
            blocks.append(cur)
            cur = None
        else:
            cur.append(raw)
    if cur is not None:
        raise WaiverError("the ```breaking block is not closed with ```")
    if not blocks:
        return None
    if len(blocks) > 1:
        raise WaiverError(f"the PR body has {len(blocks)} ```breaking blocks; want exactly one")
    out, seen = [], set()
    for raw in blocks[0]:
        line = raw.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            raise WaiverError(f"breaking line {line!r} is not "
                              "'consumer -> provider | <finding as spec-compat printed it>'")
        e = Entry(m.group(1), m.group(2), m.group(3).strip())
        if e in seen:
            raise WaiverError(f"duplicate breaking line {e.line!r}")
        seen.add(e)
        out.append(e)
    if not out:
        raise WaiverError("the ```breaking block is empty; an empty list approves nothing, "
                          "remove the block (and the label)")
    return out


def check_shape(labels, body, contracts):
    """R1 + R2. labels: label names; contracts: {(consumer, provider)}. -> entries ([] = none)."""
    entries = parse_block(body)
    has_label = LABEL in labels
    if has_label and entries is None:
        raise WaiverError(f"the PR has the {LABEL!r} label but its body has no ```breaking "
                          "block: list every approved break, or remove the label")
    if entries is not None and not has_label:
        raise WaiverError(f"the PR body lists breaking changes but the PR lacks the {LABEL!r} "
                          "label: only the owner's label approves them")
    for e in entries or []:
        if (e.consumer, e.provider) not in contracts:
            raise WaiverError(f"breaking pair {e.pair!r} is not a configured contract "
                              f"(services.json `contracts`)")
    return entries or []


def _ts(text):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError as ex:
        raise WaiverError(f"unparseable timestamp {text!r}") from ex


def label_before_merge(events, merged_at):
    """R5: True when the last labeled/unlabeled event for LABEL strictly before merged_at is
    `labeled`. A label added at or after the merge approves nothing."""
    if not merged_at:
        raise WaiverError("the PR has no merged_at; a label cannot be dated against a merge")
    cut = _ts(merged_at)
    state = False
    mine = [e for e in events or []
            if e.get("event") in ("labeled", "unlabeled")
            and (e.get("label") or {}).get("name") == LABEL]
    for e in sorted(mine, key=lambda e: _ts(e.get("created_at"))):
        if _ts(e.get("created_at")) >= cut:
            break
        state = e["event"] == "labeled"
    return state


def check_matrix(entries, checks):
    """R3: each listed pair needs a `checks` entry with consumer_side live."""
    live = {(c.get("consumer"), c.get("provider")) for c in checks or []
            if c.get("consumer_side") == "live"}
    for e in entries:
        if (e.consumer, e.provider) not in live:
            raise WaiverError(f"breaking pair {e.pair!r} has no live-consumer contract check in "
                              "this release; only a break of a LIVE consumer can be approved")


def to_json(entries):
    return json.dumps([e._asdict() for e in entries], separators=(",", ":"))


def from_json(text):
    if not (text or "").strip():
        return []
    try:
        data = json.loads(text)
    except ValueError as ex:
        raise WaiverError(f"breaking list is not JSON: {ex}") from ex
    if not isinstance(data, list):
        raise WaiverError("breaking list must be a JSON list")
    out = []
    for d in data:
        if not isinstance(d, dict) or set(d) != {"consumer", "provider", "finding"} \
                or not all(isinstance(v, str) and v for v in d.values()):
            raise WaiverError(f"breaking entry {d!r} is not {{consumer, provider, finding}}")
        parse_pair(f"{d['consumer']} -> {d['provider']}")
        out.append(Entry(d["consumer"], d["provider"], d["finding"]))
    return out


def split(findings, pair, entries):
    """R4 for one pair -> (waived, unlisted, stale), each de-duplicated, in input order."""
    listed = [e.finding for e in entries if e.pair == pair]
    uniq = list(dict.fromkeys(findings))
    waived = [f for f in uniq if f in listed]
    unlisted = [f for f in uniq if f not in listed]
    stale = [f for f in listed if f not in uniq]
    return waived, unlisted, stale


def paste_block(pair, findings):
    """R6: the block to paste into the release PR body."""
    body = "\n".join(f"{pair} | {f}" for f in dict.fromkeys(findings))
    return f"```breaking\n{body}\n```\n"
