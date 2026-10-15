#!/usr/bin/env python3
"""Live-consumer compatibility: does a CANDIDATE provider spec still serve what a BASELINE needs?

BASELINE is a provider spec a running (live) consumer depends on: the one it was built against
(the consumer's pinned copy of the provider spec at its live tag) or the one the live provider
serves today.
CANDIDATE is the provider spec about to ship. Unlike the api's fixture-parity test (strict both
ways, right for a candidate consumer) this is one-directional: it fails only when the candidate
could break the baseline's consumer. The rules are the list in docs/release-flow.md
§ Contract checks; in short, for every operation (method + path, path-parameter NAMES ignored):
  - operation missing, or it newly requires `security`;
  - RESPONSE (2xx JSON): a property missing / retyped / required->optional / newly nullable, an
    `items` or `additionalProperties` schema that changed the same way, a 2xx status or media type
    gone;
  - REQUEST: a parameter or body property removed / retyped / newly required / enum narrowed;
  - a oneOf/anyOf branch gone (matched by $ref name, else position); every branch is checked by
    the same rules; allOf is merged. A type one side states and the other does not = CHANGED.
Additive changes (new operations, optional fields/params, widened enums) pass.

Usage: spec_compat.py BASELINE CANDIDATE [--label X] [--pair "C -> P" --consumer-side live|candidate]
       (JSON or YAML files)
With --pair, env RELEASE_BREAKING (the plan's `breaking` output, JSON) is the owner-approved
list (waiver.py): in a `live` consumer check each listed finding of this pair is printed WAIVED
and written to $GITHUB_STEP_SUMMARY, an unlisted finding fails, and a listed one that did not
occur fails (stale). A `candidate` consumer check waives nothing. On failure a paste-ready
```breaking block is printed (R6).
Exit: 0 compatible (or every finding waived); 1 incompatible, or ZERO operations examined (a
check that examined nothing proves nothing; never waivable); 2 usage / unreadable file / PyYAML
missing for a YAML input / bad RELEASE_BREAKING (never waivable).
Reuses cli_ops_check's loader (PyYAML imported lazily, only for YAML input).
"""

from __future__ import annotations

import os
import re
import sys

import waiver
from cli_ops_check import METHODS, load


class Unresolved(Exception):
    pass


def norm_path(path):
    return re.sub(r"\{[^}]*\}", "{}", path)


def path_names(path):
    return re.findall(r"\{([^}]*)\}", path)


class Doc:
    """One spec plus local-$ref resolution."""

    def __init__(self, root):
        self.root = root or {}

    def deref(self, node):
        seen = 0
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise Unresolved(f"unresolved $ref {ref!r} (only local #/ refs are followed)")
            cur = self.root
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(cur, dict) or part not in cur:
                    raise Unresolved(f"unresolved $ref {ref!r}")
                cur = cur[part]
            node = cur
            seen += 1
            if seen > 50:
                raise Unresolved(f"$ref chain too long at {ref!r}")
        return node if isinstance(node, dict) else {}

    def flat(self, node):
        """Resolve $ref and merge allOf. Branch lists (oneOf/anyOf) keep their raw nodes."""
        node = self.deref(node)
        out = {"type": node.get("type"), "properties": dict(node.get("properties") or {}),
               "required": list(node.get("required") or []), "items": node.get("items"),
               "ap": node.get("additionalProperties"), "nullable": bool(node.get("nullable")),
               "enum": node.get("enum"),
               "writeonly": bool(node.get("writeOnly")),
               "lim": {k: node[k] for k in ("maxLength", "minLength", "pattern", "format")
                       if k in node},
               "disc": (node.get("discriminator") or {}).get("mapping"),
               # each oneOf / anyOf keyword is its OWN group (an allOf of two oneOfs is an
               # intersection, not one union)
               "groups": [list(node[k]) for k in ("oneOf", "anyOf") if node.get(k)]}
        for sub in node.get("allOf") or []:
            f = self.flat(sub)
            out["type"] = out["type"] or f["type"]
            for k, v in f["properties"].items():
                out["properties"].setdefault(k, v)
            out["required"] += f["required"]
            out["items"] = out["items"] or f["items"]
            out["ap"] = out["ap"] if out["ap"] is not None else f["ap"]
            out["nullable"] = out["nullable"] or f["nullable"]
            out["enum"] = out["enum"] or f["enum"]
            out["groups"] += f["groups"]
            out["writeonly"] = out["writeonly"] or f["writeonly"]
            out["disc"] = out["disc"] or f["disc"]
            for k, v in f["lim"].items():
                out["lim"].setdefault(k, v)
        return out


def type_key(t):
    return None if t is None else repr(sorted(t) if isinstance(t, list) else t)


def branch_label(node, i):
    if isinstance(node, dict) and isinstance(node.get("$ref"), str):
        return node["$ref"].rsplit("/", 1)[-1]
    return f"#{i}"


class Checker:
    def __init__(self, baseline, cand):
        self.p, self.c = Doc(baseline), Doc(cand)
        self.findings = []
        self.n_ops = 0
        self.n_props = 0

    def fail(self, where, msg):
        self.findings.append(f"{where}: {msg}")

    # -- one schema pair. mode "resp": the baseline consumer READS it; "req": it WRITES it.
    def compare(self, where, path, pn, cn, mode, seen):
        pd, cd = self.p.deref(pn), self.c.deref(cn)
        key = (id(pd), id(cd), mode)
        if key in seen:
            return
        seen = seen | {key}
        p, c = self.p.flat(pn), self.c.flat(cn)
        if type_key(p["type"]) != type_key(c["type"]):
            self.fail(where, f"{path}: type changed {p['type']!r} -> {c['type']!r}")
        if mode == "resp" and c["nullable"] and not p["nullable"]:
            self.fail(where, f"{path}: gained nullable")
        if mode == "resp" and c["writeonly"] and not p["writeonly"]:
            self.fail(where, f"{path}: became writeOnly")
        if mode == "req":
            if p["nullable"] and not c["nullable"]:
                self.fail(where, f"{path}: no longer nullable in candidate")
            # an enum REMOVED is a widening; an enum ADDED or shrunk narrows
            if c["enum"] is not None and (
                    p["enum"] is None
                    or not set(map(repr, p["enum"])) <= set(map(repr, c["enum"]))):
                self.fail(where, f"{path}: enum narrowed {p['enum']!r} -> {c['enum']!r}")
            self.check_limits(where, path, p["lim"], c["lim"])
        if p["disc"]:
            for k, v in p["disc"].items():
                if (c["disc"] or {}).get(k) != v:
                    self.fail(where, f"{path}: discriminator mapping {k!r} changed or gone")
        for name, psub in p["properties"].items():
            self.n_props += 1
            sub = f"{path}/{name}"
            if name not in c["properties"]:
                self.fail(where, f"{sub}: property " + ("removed" if mode == "req" else "missing")
                          + " in candidate")
                continue
            if mode == "resp" and name in p["required"] and name not in c["required"]:
                self.fail(where, f"{sub}: changed from required to optional in candidate")
            self.compare(where, sub, psub, c["properties"][name], mode, seen)
        if mode == "req":
            for name in c["required"]:
                self.n_props += 1
                if name not in p["properties"]:
                    self.fail(where, f"{path}/{name}: required in candidate, absent from baseline")
                elif name not in p["required"]:
                    self.fail(where, f"{path}/{name}: required in candidate, optional in baseline")
        if mode == "req" and p["items"] is None and c["items"] is not None:
            self.fail(where, f"{path}/[]: array items schema gained in candidate")
        if p["items"] is not None:
            if c["items"] is None:
                self.fail(where, f"{path}/[]: array items schema missing in candidate")
            else:
                self.compare(where, f"{path}/[]", p["items"], c["items"], mode, seen)
        if p["ap"] not in (None, False):
            if c["ap"] in (None, False):
                self.fail(where, f"{path}: additionalProperties removed in candidate")
            elif isinstance(p["ap"], dict) and isinstance(c["ap"], dict):
                self.compare(where, f"{path}/additionalProperties", p["ap"], c["ap"], mode, seen)
            elif isinstance(p["ap"], dict) != isinstance(c["ap"], dict):
                self.fail(where, f"{path}: additionalProperties changed "
                          f"{type(p['ap']).__name__} -> {type(c['ap']).__name__}")
        for gi, pg in enumerate(p["groups"]):
            if gi < len(c["groups"]):
                self.compare_branches(where, path, pg, c["groups"][gi], mode, seen)
            else:
                self.compare_branches(where, path, pg, [], mode, seen)
        if mode == "req":  # a group only the candidate has narrows what may be sent
            for cg in c["groups"][len(p["groups"]):]:
                for i, b in enumerate(cg):
                    need = self.c.flat(b)["required"]
                    if need:
                        self.fail(where, f"{path}/<{branch_label(b, i)}>: oneOf/anyOf part exists "
                                  f"only in candidate and requires {need}")

    @staticmethod
    def check_limits_fields(p, c):
        out = []
        pm, cm = p.get("maxLength"), c.get("maxLength")
        if cm is not None and (pm is None or cm < pm):
            out.append(f"maxLength tightened {pm!r} -> {cm!r}")
        pn, cn = p.get("minLength", 0), c.get("minLength")
        if cn is not None and cn > pn:
            out.append(f"minLength tightened {pn!r} -> {cn!r}")
        for k in ("pattern", "format"):
            if k in c and c[k] != p.get(k):
                out.append(f"{k} added or changed {p.get(k)!r} -> {c[k]!r}")
        return out

    def check_limits(self, where, path, p, c):
        for msg in self.check_limits_fields(p, c):
            self.fail(where, f"{path}: {msg}")

    def compare_branches(self, where, path, pb, cb, mode, seen):
        by_ref = {}
        for i, b in enumerate(cb):
            if isinstance(b, dict) and isinstance(b.get("$ref"), str):
                by_ref[b["$ref"].rsplit("/", 1)[-1]] = b
        for i, b in enumerate(pb):
            label = branch_label(b, i)
            if label in by_ref:
                match = by_ref[label]
            elif not label.startswith("#") or i >= len(cb):
                match = None
            else:
                match = cb[i]
            sub = f"{path}/<{label}>"
            if match is None:
                self.fail(where, f"{sub}: oneOf/anyOf branch gone in candidate")
                continue
            self.compare(where, sub, b, match, mode, seen)

    # -- operation level
    def params(self, doc, item, op, ptemplate, where):
        names = path_names(ptemplate)
        out = {}
        for prm in list(item.get("parameters") or []) + list(op.get("parameters") or []):
            prm = doc.deref(prm)
            if prm.get("name") is None:
                continue
            name = prm["name"]
            if "content" in prm and "schema" not in prm:
                self.fail(where, f"parameter {prm.get('in')}:{name}: declared through `content`, "
                          "uncomparable")
            if prm.get("in") == "path" and name in names:
                name = f"#{names.index(name)}"  # position: the NAME may be renamed freely
            out[(prm.get("in"), name)] = prm
        return out

    @staticmethod
    def param_schema(prm):
        if prm.get("schema") is not None:
            return prm["schema"]
        return {k: prm[k] for k in ("type", "items", "enum", "maxLength", "minLength",
                                    "pattern", "format") if k in prm}

    def body_schemas(self, doc, op, params):
        out = {}
        rb = doc.deref(op.get("requestBody") or {})
        for mt, v in (rb.get("content") or {}).items():
            if isinstance(v, dict) and v.get("schema") is not None:
                out[mt] = v["schema"]
        for (loc, _), prm in params.items():
            if loc == "body" and prm.get("schema") is not None:
                out["body"] = prm["schema"]
        return out

    def responses(self, doc, op):
        out = {}
        for code, r in (op.get("responses") or {}).items():
            if not str(code).upper().startswith("2"):
                continue
            r = doc.deref(r)
            schemas = {}
            for mt, v in (r.get("content") or {}).items():
                schemas[mt] = v.get("schema") if isinstance(v, dict) else None
            if r.get("schema") is not None:  # swagger 2
                schemas["*"] = r["schema"]
            out[str(code)] = schemas
        return out

    @staticmethod
    def alternatives(doc, op):
        """Effective security as a list of {scheme: scopes}; no requirement = [{}] (anonymous)."""
        sec = op["security"] if "security" in op else doc.root.get("security")
        alts = [s for s in (sec or []) if isinstance(s, dict)]
        return alts or [{}]

    @staticmethod
    def accepts(cand_alt, base_alt):
        """A request carrying exactly base_alt's credentials satisfies cand_alt."""
        for scheme, scopes in cand_alt.items():
            if scheme not in base_alt:
                return False
            if not set(scopes or []) <= set(base_alt[scheme] or []):
                return False
        return True

    def check_security(self, where, pop, cop):
        calts = self.alternatives(self.c, cop)
        for b in self.alternatives(self.p, pop):
            if not any(self.accepts(c, b) for c in calts):
                shown = " + ".join(f"{k}{list(v or [])}" for k, v in b.items()) or "anonymous"
                self.fail(where, f"security: candidate no longer accepts the baseline "
                          f"credential ({shown})")

    def check_op(self, method, ppath, cpath, pitem, citem):
        where = f"{method.upper()} {ppath}"
        pop, cop = pitem[method], citem[method]
        self.check_security(where, pop, cop)
        prb, crb = self.p.deref(pop.get("requestBody") or {}), self.c.deref(cop.get("requestBody") or {})
        if crb.get("required") and not prb.get("required"):
            self.fail(where, "request body: required in candidate, optional or absent in baseline")
        pp = self.params(self.p, pitem, pop, ppath, where)
        cp = self.params(self.c, citem, cop, cpath, where)
        for (loc, name), prm in pp.items():
            self.n_props += 1
            label = f"{loc}:{name}"
            if (loc, name) not in cp:
                self.fail(where, f"parameter {label}: removed in candidate")
                continue
            ps, cs = self.param_schema(prm), self.param_schema(cp[(loc, name)])
            if ps:
                self.compare(where, f"parameter {label}", ps, cs, "req", frozenset())
        for (loc, name), prm in cp.items():
            if prm.get("required") or loc == "path":
                old = pp.get((loc, name))
                label = f"{loc}:{name}"
                if old is None:
                    self.fail(where, f"parameter {label}: required in candidate, absent from baseline")
                elif not (old.get("required") or loc == "path"):
                    self.fail(where, f"parameter {label}: required in candidate, optional in baseline")
        pb, cb = self.body_schemas(self.p, pop, pp), self.body_schemas(self.c, cop, cp)
        for mt, psch in pb.items():
            if mt not in cb:
                self.fail(where, f"request body ({mt}): gone in candidate")
        for mt, csch in cb.items():
            psch = pb.get(mt)
            if psch is None:
                if self.c.flat(csch)["required"]:
                    self.fail(where, f"body/{mt}: required fields in candidate, no such body in baseline")
                continue
            self.compare(where, "body", psch, csch, "req", frozenset())
        presp, cresp = self.responses(self.p, pop), self.responses(self.c, cop)
        for code, pschemas in presp.items():
            if code not in cresp:
                self.fail(where, f"response {code}: missing in candidate")
                continue
            for mt, psch in pschemas.items():
                if mt not in cresp[code] and not (mt == "*" and cresp[code]):
                    self.fail(where, f"{code}: media type {mt} gone in candidate")
                    continue
                csch = cresp[code].get(mt)
                if csch is None and mt == "*":
                    csch = next(iter(cresp[code].values()))
                if psch is None:
                    continue
                if csch is None:
                    self.fail(where, f"{code}: response schema ({mt}) missing in candidate")
                    continue
                self.compare(where, code, psch, csch, "resp", frozenset())

    def run(self):
        ppaths = self.p.root.get("paths") or {}
        cnorm = {}
        for cpath, citem in (self.c.root.get("paths") or {}).items():
            cnorm[norm_path(cpath)] = (cpath, citem or {})
        for path, pitem in ppaths.items():
            pitem = pitem or {}
            if "$ref" in pitem:
                self.n_ops += 1
                self.fail(path, "path item is a $ref, uncomparable")
                continue
            if "$ref" in (cnorm.get(norm_path(path), (path, {}))[1]):
                self.n_ops += 1
                self.fail(path, "candidate path item is a $ref, uncomparable")
                continue
            for m in pitem:
                if m.lower() not in METHODS:
                    continue
                self.n_ops += 1
                cpath, citem = cnorm.get(norm_path(path), (path, {}))
                if m not in citem:
                    self.fail(f"{m.upper()} {path}", "operation missing in candidate")
                    continue
                try:
                    self.check_op(m, path, cpath, pitem, citem)
                except Unresolved as ex:
                    self.fail(f"{m.upper()} {path}", str(ex))
        return self.findings


def _take(argv, flag):
    """Remove `flag VALUE` from argv -> VALUE, None when absent; ValueError when VALUE is missing."""
    if flag not in argv:
        return None
    i = argv.index(flag)
    if i + 1 >= len(argv):
        raise ValueError(flag)
    value = argv[i + 1]
    del argv[i:i + 2]
    return value


def _summary(env, label, waived):
    path = env.get("GITHUB_STEP_SUMMARY")
    if not path or not waived:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"### {label}: {len(waived)} breaking change(s) WAIVED by "
                 f"`{waiver.LABEL}`\n\n")
        fh.writelines(f"- `{f}`\n" for f in waived)
        fh.write("\n")


def main(argv, env=None):
    env = os.environ if env is None else env
    argv = list(argv)
    try:
        raw_label = _take(argv, "--label")
        pair = _take(argv, "--pair")
        side = _take(argv, "--consumer-side")
    except ValueError:
        print(__doc__, file=sys.stderr)
        return 2
    label = f"spec-compat[{raw_label}]" if raw_label is not None else "spec-compat"
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if (pair is None) != (side is None):
            raise waiver.WaiverError("--pair and --consumer-side go together")
        if side is not None and side not in ("live", "candidate"):
            raise waiver.WaiverError(f"--consumer-side {side!r} is neither live nor candidate")
        if pair is not None:
            waiver.parse_pair(pair)
        entries = waiver.from_json(env.get("RELEASE_BREAKING", ""))
        if entries and pair is None:
            raise waiver.WaiverError("RELEASE_BREAKING lists approved breaks but --pair is not "
                                     "given, so none can be matched; pass --pair and "
                                     "--consumer-side from the checks matrix")
    except waiver.WaiverError as ex:
        print(f"{label}: {ex}", file=sys.stderr)
        return 2
    try:
        baseline, cand = load(argv[0]), load(argv[1])
    except (OSError, SystemExit, ValueError) as ex:
        print(f"{label}: {ex}", file=sys.stderr)
        return 2
    ck = Checker(baseline, cand)
    findings = ck.run()
    print(f"{label}: examined {ck.n_ops} operation(s), {ck.n_props} propert(ies)/parameter(s) "
          "of the baseline spec")
    if ck.n_ops == 0:  # never waivable (ruling 5)
        print("FAIL: examined 0 operations -- the baseline spec has no paths, nothing was checked")
        return 1
    if side == "live":
        waived, unlisted, stale = waiver.split(findings, pair, entries)
    else:  # no pair, or a candidate consumer: nothing is waived and nothing can go stale
        waived, unlisted, stale = [], list(dict.fromkeys(findings)), []
    for f in waived:
        print(f"WAIVED {f}")
    for f in unlisted:
        print(f"INCOMPATIBLE {f}")
    for f in stale:
        print(f"STALE approval (listed for {pair}, did not occur): {f}")
    _summary(env, label, waived)
    if unlisted or stale:
        print(f"FAIL: {len(unlisted)} incompatibility(ies) not approved, {len(stale)} stale "
              f"approval(s), {len(waived)} waived")
        if side == "candidate":
            print(f"A break in a candidate-consumer check cannot be waived with "
                  f"`{waiver.LABEL}`: the new consumer itself needs what the provider removed.")
        elif findings:
            print(f"To ship these as approved breaking changes, the owner labels the release PR "
                  f"`{waiver.LABEL}` and its body carries exactly:")
            print(waiver.paste_block(pair or "<consumer> -> <provider>", findings), end="")
        return 1
    if waived:
        print(f"ok: {len(waived)} incompatibility(ies) WAIVED by `{waiver.LABEL}`; nothing else")
        return 0
    print("ok: the candidate still serves everything the baseline spec uses")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
