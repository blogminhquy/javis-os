"""Failed custom MCP OAuth attempts report the auth mode left in storage."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-mcp-oauth-")

import main  # noqa: E402
import mcp_store  # noqa: E402


class Request:
    url = SimpleNamespace(scheme="http", netloc="localhost:7777")
    headers = {}

    def __init__(self, conn_id):
        self.conn_id = conn_id

    async def json(self):
        return {"id": self.conn_id}


async def check():
    for has_token, expected_auth in ((False, "header"), (True, "oauth")):
        conn_id, error = mcp_store.add_connection("custom", {
            "label": "OAuth test", "url": "https://mcp.example/mcp", "auth": "oauth"})
        assert not error
        with patch.object(main.oauth_mcp, "start_auth", AsyncMock(return_value={
                "ok": False, "error": "authorization unavailable"})), \
             patch.object(main.oauth_mcp, "status", return_value={"connected": has_token}):
            result = await main.connect_oauth_start(Request(conn_id))
        assert result["ok"] is False
        assert result["auth"] == expected_auth, result
        assert mcp_store.get_connection(conn_id)["auth"] == expected_auth


asyncio.run(check())
print("OK - OAuth failure reports the persisted auth mode")
