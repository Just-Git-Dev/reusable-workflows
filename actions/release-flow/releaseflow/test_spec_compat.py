"""Tests for spec_compat.py: pinned (live consumer's) spec vs candidate provider spec."""

import copy
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import spec_compat  # noqa: E402


def spec(paths, schemas=None):
    s = {"openapi": "3.0.0", "paths": paths}
    if schemas:
        s["components"] = {"schemas": schemas}
    return s


def ok(schema, code="200"):
    return {"responses": {code: {"content": {"application/json": {"schema": schema}}}}}


def obj(**props):
    return {"type": "object", "properties": props}


PINNED = spec({
    "/a": {"get": ok(obj(id={"type": "string"}, n={"type": "integer"}))},
    "/b": {"post": {
        "parameters": [{"name": "q", "in": "query", "required": False, "schema": {"type": "string"}}],
        "requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "required": ["x"], "properties": {"x": {"type": "string"},
                                                                "y": {"type": "string"}}}}}},
        "responses": {"201": {"content": {"application/json": {"schema": obj(
            items={"type": "array", "items": obj(k={"type": "string"})})}}}}}},
})


def run(pinned, cand):
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d, "a.json"), Path(d, "b.json")
        a.write_text(json.dumps(pinned))
        b.write_text(json.dumps(cand))
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = spec_compat.main([str(a), str(b)])
        return rc, out.getvalue() + err.getvalue()


class PassTests(unittest.TestCase):
    def test_identical_passes_and_counts(self):
        rc, out = run(PINNED, PINNED)
        self.assertEqual(rc, 0, out)
        self.assertIn("examined 2 operation(s)", out)
        self.assertRegex(out, r", \d+ propert")

    def test_additive_changes_pass(self):
        c = copy.deepcopy(PINNED)
        c["paths"]["/new"] = {"get": ok(obj(z={"type": "string"}))}
        c["paths"]["/a"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"]["properties"]["extra"] = {"type": "string"}
        c["paths"]["/b"]["post"]["parameters"].append(
            {"name": "opt", "in": "query", "required": False, "schema": {"type": "string"}})
        c["paths"]["/b"]["post"]["requestBody"]["content"]["application/json"]["schema"][
            "properties"]["optional_new"] = {"type": "string"}
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 0, out)

    def test_non_2xx_response_changes_ignored(self):
        p = spec({"/a": {"get": {"responses": {
            "200": {"content": {"application/json": {"schema": obj(id={"type": "string"})}}},
            "400": {"content": {"application/json": {"schema": obj(err={"type": "string"})}}}}}}})
        c = copy.deepcopy(p)
        c["paths"]["/a"]["get"]["responses"]["400"]["content"]["application/json"]["schema"] = obj()
        rc, out = run(p, c)
        self.assertEqual(rc, 0, out)


class FailTests(unittest.TestCase):
    def test_missing_operation(self):
        c = copy.deepcopy(PINNED)
        del c["paths"]["/a"]["get"]
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 1)
        self.assertIn("GET /a", out)
        self.assertIn("operation missing", out)

    def test_missing_response_property_names_pointer(self):
        c = copy.deepcopy(PINNED)
        del c["paths"]["/a"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"]["properties"]["n"]
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 1)
        self.assertIn("GET /a", out)
        self.assertIn("200/n", out)
        self.assertIn("missing", out)

    def test_nested_array_item_property_missing(self):
        c = copy.deepcopy(PINNED)
        del c["paths"]["/b"]["post"]["responses"]["201"]["content"]["application/json"][
            "schema"]["properties"]["items"]["items"]["properties"]["k"]
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 1)
        self.assertIn("201/items/[]/k", out)

    def test_type_changed(self):
        c = copy.deepcopy(PINNED)
        c["paths"]["/a"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"]["properties"]["n"]["type"] = "string"
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 1)
        self.assertIn("200/n", out)
        self.assertIn("type changed", out)

    def test_new_required_param(self):
        c = copy.deepcopy(PINNED)
        c["paths"]["/b"]["post"]["parameters"].append(
            {"name": "must", "in": "header", "required": True, "schema": {"type": "string"}})
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 1)
        self.assertIn("header:must", out)

    def test_param_became_required(self):
        c = copy.deepcopy(PINNED)
        c["paths"]["/b"]["post"]["parameters"][0]["required"] = True
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 1)
        self.assertIn("query:q", out)

    def test_body_property_newly_required(self):
        c = copy.deepcopy(PINNED)
        c["paths"]["/b"]["post"]["requestBody"]["content"]["application/json"]["schema"][
            "required"] = ["x", "y"]
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 1)
        self.assertIn("body/y", out)

    def test_body_required_property_absent_from_pinned(self):
        c = copy.deepcopy(PINNED)
        s = c["paths"]["/b"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        s["properties"]["brand_new"] = {"type": "string"}
        s["required"] = ["x", "brand_new"]
        rc, out = run(PINNED, c)
        self.assertEqual(rc, 1)
        self.assertIn("body/brand_new", out)

    def test_zero_operations_fails(self):
        rc, out = run({"openapi": "3.0.0", "paths": {}}, PINNED)
        self.assertEqual(rc, 1)
        self.assertIn("examined 0", out)

    def test_unreadable_file_fails(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = spec_compat.main(["/nonexistent/a.yaml", "/nonexistent/b.yaml"])
        self.assertEqual(rc, 2)


class RefTests(unittest.TestCase):
    def test_ref_resolved_and_property_missing_found(self):
        p = spec({"/a": {"get": ok({"$ref": "#/components/schemas/T"})}},
                 {"T": obj(id={"type": "string"}, name={"type": "string"})})
        c = copy.deepcopy(p)
        del c["components"]["schemas"]["T"]["properties"]["name"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1)
        self.assertIn("200/name", out)
        rc, out = run(p, p)
        self.assertEqual(rc, 0, out)

    def test_ref_on_one_side_inline_on_other(self):
        p = spec({"/a": {"get": ok({"$ref": "#/components/schemas/T"})}},
                 {"T": obj(id={"type": "string"})})
        c = spec({"/a": {"get": ok(obj(id={"type": "string"}))}})
        rc, out = run(p, c)
        self.assertEqual(rc, 0, out)

    def test_swagger2_definitions_ref(self):
        def s2(props):
            return {"swagger": "2.0", "paths": {"/a": {"get": {"responses": {
                "200": {"schema": {"$ref": "#/definitions/T"}}}}}},
                "definitions": {"T": obj(**props)}}
        rc, out = run(s2({"a": {"type": "string"}}), s2({"a": {"type": "string"}, "b": {"type": "string"}}))
        self.assertEqual(rc, 0, out)
        rc, out = run(s2({"a": {"type": "string"}, "b": {"type": "string"}}), s2({"a": {"type": "string"}}))
        self.assertEqual(rc, 1)
        self.assertIn("200/b", out)

    def test_cycle_terminates(self):
        tree = {"Node": {"type": "object", "properties": {
            "v": {"type": "string"}, "child": {"$ref": "#/components/schemas/Node"}}}}
        p = spec({"/a": {"get": ok({"$ref": "#/components/schemas/Node"})}}, tree)
        rc, out = run(p, p)
        self.assertEqual(rc, 0, out)
        c = copy.deepcopy(p)
        del c["components"]["schemas"]["Node"]["properties"]["v"]
        rc, out = run(p, c)
        self.assertEqual(rc, 1)
        self.assertIn("v", out)

    def test_allof_properties_merged(self):
        p = spec({"/a": {"get": ok({"allOf": [{"$ref": "#/components/schemas/Base"},
                                               obj(own={"type": "string"})]})}},
                 {"Base": obj(id={"type": "string"})})
        rc, out = run(p, p)
        self.assertEqual(rc, 0, out)
        c = copy.deepcopy(p)
        c["components"]["schemas"]["Base"]["properties"] = {}
        rc, out = run(p, c)
        self.assertEqual(rc, 1)
        self.assertIn("200/id", out)

    def test_ref_param_and_unresolvable_ref_fails(self):
        p = spec({"/a": {"get": ok({"$ref": "#/components/schemas/Gone"})}})
        rc, out = run(p, p)
        self.assertEqual(rc, 1)
        self.assertIn("unresolved", out)


if __name__ == "__main__":
    unittest.main()
