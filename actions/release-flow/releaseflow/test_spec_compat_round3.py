"""Round-3 rules for spec_compat.py: security scheme identity, request tightenings, uncomparable
constructs, allOf-of-oneOfs grouping, and the widening cases that must keep passing."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_spec_compat import ok, obj, run, spec  # noqa: E402

S = {"type": "string"}
I = {"type": "integer"}
SCHEMES = {"securitySchemes": {n: {"type": "http", "scheme": "bearer"}
                               for n in ("BearerAccess", "BearerPlatformToken")}}


def with_sec(paths):
    d = spec(paths)
    d.setdefault("components", {}).update(SCHEMES)
    return d


def op(security=None, **kw):
    o = {"responses": {"200": {"description": "ok"}}, **kw}
    if security is not None:
        o["security"] = security
    return o


def body_op(schema, required=None, **kw):
    rb = {"content": {"application/json": {"schema": schema}}}
    if required is not None:
        rb["required"] = required
    return op(requestBody=rb, **kw)


def fails(test, p, c, needle):
    rc, out = run(p, c)
    test.assertEqual(rc, 1, out)
    test.assertIn(needle, out)


def passes(test, p, c):
    rc, out = run(p, c)
    test.assertEqual(rc, 0, out)


class SecurityTests(unittest.TestCase):
    def test_scheme_swap_fails(self):
        p = with_sec({"/x": {"delete": op([{"BearerAccess": []}])}})
        c = with_sec({"/x": {"delete": op([{"BearerPlatformToken": []}])}})
        fails(self, p, c, "security")

    def test_every_baseline_alternative_must_still_be_accepted(self):
        p = with_sec({"/x": {"get": op([{"BearerAccess": []}, {"BearerPlatformToken": []}])}})
        c = with_sec({"/x": {"get": op([{"BearerAccess": []}])}})
        fails(self, p, c, "security")

    def test_added_alternative_and_same_scheme_pass(self):
        p = with_sec({"/x": {"get": op([{"BearerAccess": []}])}})
        c = with_sec({"/x": {"get": op([{"BearerAccess": []}, {"BearerPlatformToken": []}])}})
        passes(self, p, c)
        passes(self, p, p)

    def test_scopes_must_not_grow(self):
        p = with_sec({"/x": {"get": op([{"BearerAccess": ["a"]}])}})
        c = with_sec({"/x": {"get": op([{"BearerAccess": ["a", "b"]}])}})
        fails(self, p, c, "security")
        passes(self, c, p)

    def test_anonymous_alternative_must_stay_accepted(self):
        p = with_sec({"/x": {"get": op([{}, {"BearerAccess": []}])}})
        c = with_sec({"/x": {"get": op([{"BearerAccess": []}])}})
        fails(self, p, c, "security")

    def test_dropping_auth_passes(self):
        p = with_sec({"/x": {"get": op([{"BearerAccess": []}])}})
        c = with_sec({"/x": {"get": op([])}})
        passes(self, p, c)


class RequestTighteningTests(unittest.TestCase):
    def test_request_body_becomes_required(self):
        a = spec({"/x": {"post": body_op(obj(a=S), required=False)}})
        b = spec({"/x": {"post": body_op(obj(a=S), required=True)}})
        fails(self, a, b, "request body")
        a = spec({"/x": {"post": op()}})
        fails(self, a, b, "request body")
        passes(self, b, b)

    def test_request_nullable_removed(self):
        p = spec({"/x": {"post": body_op(obj(a={"type": "string", "nullable": True}))}})
        c = spec({"/x": {"post": body_op(obj(a=S))}})
        fails(self, p, c, "nullable")
        passes(self, c, p)

    def test_candidate_only_oneof_group_requiring_a_field(self):
        p = spec({"/x": {"post": body_op(obj(a=S))}})
        c = spec({"/x": {"post": body_op({**obj(a=S), "oneOf": [
            {"required": ["b"], "properties": {"b": S}}, {"required": ["c"], "properties": {"c": S}}]})}})
        fails(self, p, c, "only in candidate")

    def test_candidate_only_allof_part_requiring_a_field(self):
        p = spec({"/x": {"post": body_op({"allOf": [obj(a=S)]})}})
        c = spec({"/x": {"post": body_op({"allOf": [obj(a=S), {"type": "object", "required": ["z"],
                                                                "properties": {"z": S}}]})}})
        fails(self, p, c, "z")

    def test_request_enum_removed_is_widening_and_passes(self):
        p = spec({"/x": {"post": body_op(obj(a={"type": "string", "enum": ["k"]}))}})
        c = spec({"/x": {"post": body_op(obj(a=S))}})
        passes(self, p, c)
        fails(self, c, p, "enum")  # the reverse (enum added) narrows

    def test_string_limits_tightened_fail_loosened_pass(self):
        def b(**lim):
            return spec({"/x": {"post": body_op(obj(a={"type": "string", **lim}))}})
        fails(self, b(maxLength=200), b(maxLength=10), "maxLength")
        fails(self, b(), b(maxLength=10), "maxLength")
        fails(self, b(minLength=1), b(minLength=5), "minLength")
        fails(self, b(), b(minLength=1), "minLength")
        fails(self, b(), b(pattern="^a"), "pattern")
        fails(self, b(pattern="^a"), b(pattern="^b"), "pattern")
        fails(self, b(), b(format="uuid"), "format")
        fails(self, b(format="uuid"), b(format="date"), "format")
        passes(self, b(maxLength=10), b(maxLength=200))
        passes(self, b(maxLength=10), b())
        passes(self, b(pattern="^a"), b(pattern="^a"))

    def test_header_param_max_length_lowered(self):
        def b(n):
            return spec({"/x": {"get": op(parameters=[
                {"in": "header", "name": "X-D", "schema": {"type": "string", "maxLength": n}}])}})
        fails(self, b(120), b(4), "maxLength")

    def test_request_array_gains_items(self):
        p = spec({"/x": {"post": body_op(obj(l={"type": "array"}))}})
        c = spec({"/x": {"post": body_op(obj(l={"type": "array", "items": I}))}})
        fails(self, p, c, "items")


class ResponseExtraTests(unittest.TestCase):
    def test_response_property_becomes_write_only(self):
        p = spec({"/x": {"get": ok(obj(a=S))}})
        c = spec({"/x": {"get": ok(obj(a={"type": "string", "writeOnly": True}))}})
        fails(self, p, c, "writeOnly")

    def test_discriminator_mapping_key_renamed(self):
        def d(key):
            return spec({"/x": {"get": ok({"oneOf": [{"$ref": "#/components/schemas/K"}],
                                           "discriminator": {"propertyName": "g",
                                                             "mapping": {key: "#/components/schemas/K"}}})}},
                        {"K": obj(g=S)})
        fails(self, d("k"), d("kk"), "discriminator")
        passes(self, d("k"), d("k"))


class UncomparableTests(unittest.TestCase):
    def test_ref_path_item_fails(self):
        p = spec({"/x": {"get": op()}, "/y": {"$ref": "#/components/pathItems/Y"}})
        p["components"] = {"pathItems": {"Y": {"get": op()}}}
        c = spec({"/x": {"get": op()}})
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("/y", out)
        self.assertIn("uncomparable", out)
        self.assertIn("examined 2 operation", out.replace("operation(s)", "operation"))  # counted

    def test_content_declared_parameter_fails(self):
        def b(t):
            return spec({"/x": {"get": op(parameters=[
                {"in": "query", "name": "q", "content": {"application/json": {"schema": t}}}])}})
        fails(self, b(S), b(I), "uncomparable")


class GroupingTests(unittest.TestCase):
    def test_allof_of_two_oneofs_is_two_groups(self):
        a, b = obj(a=S), obj(b=S)
        p = spec({"/x": {"get": ok({"allOf": [{"oneOf": [a, b]}]})}})
        c = spec({"/x": {"get": ok({"allOf": [{"oneOf": [a]}, {"oneOf": [b]}]})}})
        fails(self, p, c, "branch")

    def test_branch_appended_to_first_of_two_groups_passes(self):
        a, b, n = obj(a=S), obj(b=S), obj(z=S)
        p = spec({"/x": {"get": ok({"allOf": [{"oneOf": [a, b]}, {"oneOf": [a, n]}]})}})
        c = spec({"/x": {"get": ok({"allOf": [{"oneOf": [a, b, obj(q=S)]}, {"oneOf": [a, n]}]})}})
        passes(self, p, c)

    def test_appended_branch_with_required_still_passes(self):
        a = obj(a=S)
        p = spec({"/x": {"post": body_op({"oneOf": [a]})}})
        c = spec({"/x": {"post": body_op({"oneOf": [a, {"type": "object", "required": ["n"],
                                                         "properties": {"n": S}}]})}})
        passes(self, p, c)


if __name__ == "__main__":
    unittest.main()
