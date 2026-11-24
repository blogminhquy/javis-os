"""mcp_hub._drive_guard_wrap phải FAIL-SECURE: guard lỗi trên route Composio -> từ chối, không bỏ qua guard."""
import asyncio
import os
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mcp_hub  # noqa: E402


async def _real(args):
    return "REAL"


class DriveGuardWrapFailSecure(unittest.TestCase):
    def _wrap_with_broken_guard(self, connector):
        with mock.patch("drive_guard_hub.wrap", side_effect=RuntimeError("boom")), redirect_stderr(io.StringIO()):
            return mcp_hub._drive_guard_wrap(_real, {"connector_id": connector}, "COMPOSIO_MULTI_EXECUTE_TOOL", "fn")

    def test_composio_route_refused_when_guard_fails(self):
        wrapped = self._wrap_with_broken_guard("composio")
        out = asyncio.run(wrapped({}))
        self.assertTrue(str(out).startswith("ERROR:"), out)
        self.assertIn("cấu hình guard lỗi", out)

    def test_other_connector_unaffected_when_guard_fails(self):
        wrapped = self._wrap_with_broken_guard("zalo")
        self.assertIs(wrapped, _real)


if __name__ == "__main__":
    unittest.main()
