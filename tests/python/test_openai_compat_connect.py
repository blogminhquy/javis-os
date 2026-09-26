"""A saved API key must never be sent to a newly entered OpenAI-compatible endpoint."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-oc-connect-")

import config as cfg  # noqa: E402
import main  # noqa: E402


class Request:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


class Response:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def json(self):
        return {"data": [{"id": "test-model"}]}


seen = []


class Client:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url, headers):
        seen.append((url, headers.get("Authorization")))
        return Response(401 if "rejected.example" in url else 200)


async def check():
    with patch("httpx.AsyncClient", Client):
        first = await main.openai_compat_connect(Request({
            "base": "https://first.example/v1", "key": "private-key"}))
        assert first["ok"]
        second = await main.openai_compat_connect(Request({
            "base": "https://second.example/v1", "key": ""}))
        assert second["ok"]
        again = await main.openai_compat_connect(Request({
            "base": "https://second.example/v1", "key": ""}))
        assert again["ok"]
        rejected = await main.openai_compat_connect(Request({
            "base": "https://rejected.example/v1", "key": "new-key"}))
        assert not rejected["ok"]
    assert seen[0] == ("https://first.example/v1/models", "Bearer private-key")
    assert seen[1] == ("https://second.example/v1/models", "Bearer none"), seen[1]
    assert seen[2] == ("https://second.example/v1/models", "Bearer none")
    model = cfg.read_settings()["model"]
    assert model["openai_compat_base"] == "https://second.example/v1"
    assert model["openai_compat_key"] == "", "Old key remained attached to the new endpoint"


asyncio.run(check())
print("OK - key stays bound to its original endpoint")
