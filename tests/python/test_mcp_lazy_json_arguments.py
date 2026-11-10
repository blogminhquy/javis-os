"""Preserve dynamic tool arguments without bypassing the existing guarded route."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import tempfile
import unittest

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="lazy-json-test-"))
import mcp_hub


class LazyJsonArgumentTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        async def guarded(args):
            self.calls.append(args)
            return json.dumps(args)
        tool = {"fn": "synthetic_tool", "name": "synthetic_tool", "description": "Synthetic only",
                "schema": {"type": "object", "properties": {"op": {"type": "string"}}}}
        _, self.route = mcp_hub._lazy_tools_and_route(
            [], {}, [tool], {"synthetic_tool": {"call": guarded}}, 8)

    def call(self, **kwargs):
        return asyncio.run(self.route["javis_run_tool"]["call"]({"name": "synthetic_tool", **kwargs}))

    def test_encoded_nested_fields_reach_guard_unchanged(self):
        payload = {"op": "ingest", "event": {"sender_id": "123", "ocr": {"bill_amount": 600000}}}
        self.call(args_json=json.dumps(payload))
        self.assertEqual(self.calls, [payload])

    def test_old_argument_shapes_remain_supported(self):
        self.call(args={"op": "pending"})
        self.call(args='{"op":"pending"}')
        self.assertEqual(self.calls, [{"op": "pending"}, {"op": "pending"}])

    def test_invalid_and_conflicting_arguments_never_dispatch(self):
        for payload in ({"args_json": "{"}, {"args_json": "[]"}, {"args_json": 1},
                        {"args": {"op": "get"}, "args_json": '{"op":"pending"}'}):
            self.assertTrue(self.call(**payload).startswith("ERROR:"))
        self.assertEqual(self.calls, [])

    def test_ungranted_tool_is_still_blocked(self):
        result = asyncio.run(self.route["javis_run_tool"]["call"](
            {"name": "not_granted", "args_json": '{"op":"pending"}'}))
        self.assertTrue(result.startswith("ERROR:"))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
