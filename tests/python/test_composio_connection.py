"""Composio Connect key failures must point to the Javis-side credential."""

from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import json

import connect_health
import mcp_client
import mcp_hub
import mcp_store


REJECTED = (
    'HTTP 401: {"error":"Authorization required","reason":'
    '"Bearer token rejected: not a valid AuthKit JWT for this resource, '
    'or no matching Composio account"}'
)


def _composio():
    return {
        "id": "composio-test", "connector_id": "composio", "label": "Composio",
        "auth": "apikey", "transport": "http", "url": "https://connect.composio.dev/mcp",
        "headers": {"x-consumer-api-key": "ck_invalid"}, "perm": "readonly",
    }


class _RejectedPool:
    async def list_tools(self, spec):
        raise mcp_client.McpHttpError(REJECTED)


def test_health_names_rejected_composio_consumer_key():
    rec = asyncio.run(connect_health.check_one(_composio(), _RejectedPool()))
    assert rec["ok"] is False and rec["kind"] == "auth"
    assert "consumer key" in rec["message"].lower()
    assert "Connect my agent" in rec["message"]
    assert "Javis" in rec["message"]
    assert "Kết nối hoặc Kết nối lại" in rec["message"]
    assert "Hết phiên đăng nhập" not in rec["message"]


def test_connect_test_names_rejected_composio_consumer_key(monkeypatch):
    monkeypatch.setattr(mcp_store, "resolved", lambda enabled_only=False: [_composio()])
    monkeypatch.setattr(mcp_client, "pool", _RejectedPool())
    result = asyncio.run(mcp_hub.validate_connection("composio-test"))
    assert result["ok"] is False
    assert "consumer key" in result["error"].lower()
    assert "Connect my agent" in result["error"]
    assert "Kết nối hoặc Kết nối lại" in result["error"]


def test_catalog_uses_consumer_connect_instructions():
    catalog = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
    composio = next(c for c in catalog["connectors"] if c["id"] == "composio")
    guide = composio["auth"]["guide"]
    assert "Connect my agent" in guide
    assert "x-consumer-api-key" in guide
    assert "platform.composio.dev" not in guide


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
