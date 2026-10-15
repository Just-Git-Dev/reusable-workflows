"""cli_ops_check.load(): a YAML spec must read the same as its JSON rendering.

PyYAML's safe_load follows YAML 1.1, where an unquoted on/off/yes/no (any case) is a
boolean. JSON (and YAML 1.2, which OpenAPI tooling emits) keeps them as strings. So a JSON
baseline compared with a raw YAML candidate saw the enum value "off" vanish and reported a
false enum narrowing (consumer C, 2026-10-15). Only true/false are booleans here.
"""

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import cli_ops_check  # noqa: E402
import spec_compat  # noqa: E402

YAML_SPEC = """\
openapi: 3.0.0
paths:
  /settings:
    get:
      parameters:
        - name: enforcement
          in: query
          required: false
          schema:
            type: string
            enum: [off, on, yes, no, Off, ON, Yes, NO, y, n, strict]
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  mode:
                    type: string
                    enum: [off, on, yes, no, Off, ON, Yes, NO, y, n, strict]
                  flag:
                    type: boolean
                    default: false
                  other:
                    type: boolean
                    default: true
"""

MODES = ["off", "on", "yes", "no", "Off", "ON", "Yes", "NO", "y", "n", "strict"]

JSON_SPEC = {"openapi": "3.0.0", "paths": {"/settings": {"get": {"parameters": [
    {"name": "enforcement", "in": "query", "required": False,
     "schema": {"type": "string", "enum": MODES}}],
    "responses": {"200": {
    "content": {"application/json": {"schema": {"type": "object", "properties": {
        "mode": {"type": "string", "enum": MODES},
        "flag": {"type": "boolean", "default": False},
        "other": {"type": "boolean", "default": True},
    }}}}}}}}}}


class YamlLoadTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.yaml_path = Path(self.d.name, "swagger.yaml")
        self.yaml_path.write_text(YAML_SPEC)
        self.json_path = Path(self.d.name, "openapi.json")
        self.json_path.write_text(json.dumps(JSON_SPEC))

    def test_yaml_reads_equal_to_its_json_rendering(self):
        self.assertEqual(cli_ops_check.load(str(self.yaml_path)), JSON_SPEC)

    def test_yaml_1_2_booleans_still_parse(self):
        props = cli_ops_check.load(str(self.yaml_path))["paths"]["/settings"]["get"][
            "responses"]["200"]["content"]["application/json"]["schema"]["properties"]
        self.assertIs(props["flag"]["default"], False)
        self.assertIs(props["other"]["default"], True)

    def test_spec_compat_json_vs_yaml_reports_no_false_break(self):
        for a, b in ((self.json_path, self.yaml_path), (self.yaml_path, self.json_path)):
            out = StringIO()
            with redirect_stdout(out), redirect_stderr(out):
                rc = spec_compat.main([str(a), str(b)])
            self.assertEqual(rc, 0, f"{a.name} -> {b.name}:\n{out.getvalue()}")

    def test_loader_does_not_mutate_pyyaml_safe_loader(self):
        import yaml
        cli_ops_check.load(str(self.yaml_path))
        self.assertIs(yaml.safe_load("x: off")["x"], False)


if __name__ == "__main__":
    unittest.main()
