"""Round-2 rules for spec_compat.py (docs/release-flow.md § Contract checks, every bullet)."""

import copy
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from test_spec_compat import ok, obj, run, spec  # noqa: E402

DATA = Path(__file__).resolve().parent / "testdata"
S = {"type": "string"}
I = {"type": "integer"}


def ref(n):
    return {"$ref": f"#/components/schemas/{n}"}


def resp_schema(d, path="/a", method="get", code="200"):
    return d["paths"][path][method]["responses"][code]["content"]["application/json"]["schema"]


def req_schema(d, path="/b", method="post"):
    return d["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]


def one_of_resp():
    return spec({"/a": {"get": ok({"oneOf": [ref("A"), ref("B")]})}},
                {"A": {"type": "object", "required": ["tok"],
                       "properties": {"tok": S, "kind": {"type": "string", "enum": ["a"]}}},
                 "B": obj(other=S)})


def one_of_req():
    return spec({"/b": {"post": {"requestBody": {"content": {"application/json": {"schema": {
        "oneOf": [ref("RA"), ref("RB")]}}}}, "responses": {"200": {"description": "x"}}}}},
        {"RA": obj(a=S), "RB": {"type": "object", "properties": {"b": S, "mode": {"type": "string", "enum": ["x", "y"]}}}})


class OneOfTests(unittest.TestCase):
    def test_response_branch_property_deleted_fails(self):
        p = one_of_resp()
        c = copy.deepcopy(p)
        del c["components"]["schemas"]["A"]["properties"]["tok"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("tok", out)
        self.assertIn("A", out)

    def test_response_anyof_branch_property_deleted_fails(self):
        p = one_of_resp()
        p["paths"]["/a"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {
            "anyOf": [ref("A"), ref("B")]}
        c = copy.deepcopy(p)
        del c["components"]["schemas"]["B"]["properties"]["other"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("other", out)

    def test_response_branch_gone_fails_branch_added_passes(self):
        p = one_of_resp()
        c = copy.deepcopy(p)
        resp_schema(c)["oneOf"] = [ref("A")]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("branch", out)
        c = copy.deepcopy(p)
        c["components"]["schemas"]["C"] = obj(z=S)
        resp_schema(c)["oneOf"].append(ref("C"))
        rc, out = run(p, c)
        self.assertEqual(rc, 0, out)

    def test_request_branch_new_required_field_fails(self):
        p = one_of_req()
        c = copy.deepcopy(p)
        b = c["components"]["schemas"]["RA"]
        b["properties"]["nonce"] = S
        b["required"] = ["nonce"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("nonce", out)

    def test_request_branch_property_removed_fails(self):
        p = one_of_req()
        c = copy.deepcopy(p)
        del c["components"]["schemas"]["RB"]["properties"]["b"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("removed", out)

    def test_request_branch_gone_fails(self):
        p = one_of_req()
        c = copy.deepcopy(p)
        req_schema(c)["oneOf"] = [ref("RA")]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("branch", out)

    def test_request_enum_narrowed_fails_widened_passes(self):
        p = one_of_req()
        c = copy.deepcopy(p)
        c["components"]["schemas"]["RB"]["properties"]["mode"]["enum"] = ["x"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("enum", out)
        c = copy.deepcopy(p)
        c["components"]["schemas"]["RB"]["properties"]["mode"]["enum"] = ["x", "y", "z"]
        rc, out = run(p, c)
        self.assertEqual(rc, 0, out)

    def test_allof_containing_oneof_is_followed(self):
        p = spec({"/a": {"get": ok({"allOf": [obj(id=S), {"oneOf": [ref("A")]}]})}},
                 {"A": obj(tok=S)})
        c = copy.deepcopy(p)
        del c["components"]["schemas"]["A"]["properties"]["tok"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("tok", out)


class TypeAndShapeTests(unittest.TestCase):
    def test_typed_to_untyped_is_changed(self):
        p = spec({"/a": {"get": ok(obj(v=S))}})
        c = spec({"/a": {"get": ok(obj(v={"oneOf": [I, {"type": "object"}]}))}})
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("type changed", out)

    def test_both_untyped_passes(self):
        p = spec({"/a": {"get": ok(obj(v={"description": "any"}))}})
        rc, out = run(p, p)
        self.assertEqual(rc, 0, out)

    def test_request_property_retyped_fails(self):
        p = one_of_req()
        c = copy.deepcopy(p)
        c["components"]["schemas"]["RA"]["properties"]["a"] = I
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("type changed", out)

    def test_request_param_removed_fails(self):
        p = spec({"/b": {"get": {"parameters": [{"name": "q", "in": "query", "schema": S}],
                                  "responses": {"200": {"description": "x"}}}}})
        c = spec({"/b": {"get": {"responses": {"200": {"description": "x"}}}}})
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("query:q", out)

    def test_request_param_retyped_fails(self):
        p = spec({"/b": {"get": {"parameters": [{"name": "q", "in": "query", "schema": S}],
                                  "responses": {"200": {"description": "x"}}}}})
        c = copy.deepcopy(p)
        c["paths"]["/b"]["get"]["parameters"][0]["schema"] = I
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("query:q", out)

    def test_security_newly_required_fails(self):
        p = spec({"/a": {"get": ok(obj(v=S))}})
        c = copy.deepcopy(p)
        c["paths"]["/a"]["get"]["security"] = [{"Bearer": []}]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("security", out)
        rc, out = run(c, c)
        self.assertEqual(rc, 0, out)
        rc, out = run(c, p)  # auth dropped: not a break for the consumer
        self.assertEqual(rc, 0, out)

    def test_root_level_security_counts(self):
        p = spec({"/a": {"get": ok(obj(v=S))}})
        c = copy.deepcopy(p)
        c["security"] = [{"Bearer": []}]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)

    def test_response_required_to_optional_fails(self):
        p = spec({"/a": {"get": ok({"type": "object", "required": ["v"], "properties": {"v": S}})}})
        c = copy.deepcopy(p)
        resp_schema(c)["required"] = []
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("optional", out)

    def test_response_nullable_added_fails(self):
        p = spec({"/a": {"get": ok(obj(v=S))}})
        c = copy.deepcopy(p)
        resp_schema(c)["properties"]["v"]["nullable"] = True
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("nullable", out)

    def test_items_type_change_fails(self):
        p = spec({"/a": {"get": ok({"type": "array", "items": S})}})
        c = spec({"/a": {"get": ok({"type": "array", "items": I})}})
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("[]", out)

    def test_additional_properties_changes_fail(self):
        p = spec({"/a": {"get": ok(obj(m={"type": "object", "additionalProperties": S}))}})
        c = copy.deepcopy(p)
        resp_schema(c)["properties"]["m"]["additionalProperties"] = I
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("additionalProperties", out)
        c = copy.deepcopy(p)
        del resp_schema(c)["properties"]["m"]["additionalProperties"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("additionalProperties", out)

    def test_2xx_status_gone_fails(self):
        p = spec({"/a": {"get": {"responses": {"200": ok(obj(v=S))["responses"]["200"],
                                                 "202": ok(obj(w=S))["responses"]["200"]}}}})
        c = copy.deepcopy(p)
        del c["paths"]["/a"]["get"]["responses"]["202"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("202", out)

    def test_media_type_gone_fails(self):
        p = spec({"/a": {"get": ok(obj(v=S))}})
        c = copy.deepcopy(p)
        r = c["paths"]["/a"]["get"]["responses"]["200"]
        r["content"] = {"text/plain": r["content"]["application/json"]}
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("application/json", out)

    def test_path_param_names_are_ignored(self):
        p = spec({"/t/{tid}/x": {"get": {
            "parameters": [{"name": "tid", "in": "path", "required": True, "schema": S}],
            **ok(obj(v=S))}}})
        c = spec({"/t/{tenant_id}/x": {"get": {
            "parameters": [{"name": "tenant_id", "in": "path", "required": True, "schema": S}],
            **ok(obj(v=S))}}})
        rc, out = run(p, c)
        self.assertEqual(rc, 0, out)
        rc, out = run(c, p)
        self.assertEqual(rc, 0, out)

    def test_widened_response_enum_and_new_ops_still_pass(self):
        p = spec({"/a": {"get": ok(obj(v={"type": "string", "enum": ["a"]}))}})
        c = copy.deepcopy(p)
        resp_schema(c)["properties"]["v"]["enum"] = ["a", "b"]
        c["paths"]["/n"] = {"get": ok(obj(z=S))}
        rc, out = run(p, c)
        self.assertEqual(rc, 0, out)


class RealDataTests(unittest.TestCase):
    """Reduced real specs: api v0.37.0's pinned issuer spec vs issuer v0.134.0 (login, token,
    logout and their $ref closure)."""

    def load(self):
        pinned = json.loads((DATA / "g5-pinned-api037-reduced.json").read_text())
        cand = json.loads((DATA / "g5-issuer134-reduced.json").read_text())
        return pinned, cand

    def test_additive_release_passes(self):
        p, c = self.load()
        rc, out = run(p, c)
        self.assertEqual(rc, 0, out)
        self.assertIn("examined 3 operation(s)", out)

    def test_deleting_login_response_m2m_access_token_fails(self):
        p, c = self.load()
        self.assertIn("access_token", p["components"]["schemas"]["LoginResponseM2M"]["properties"])
        del c["components"]["schemas"]["LoginResponseM2M"]["properties"]["access_token"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1, out)
        self.assertIn("access_token", out)
        self.assertIn("/auth/login", out)


if __name__ == "__main__":
    unittest.main()
