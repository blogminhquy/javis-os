"""Channel setup contract, secret redaction and generic bot assignment (offline only)."""
from _paths import ROOT, SERVER  # noqa: F401
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

_state = tempfile.TemporaryDirectory(prefix="zernio-setup-")
os.environ["JAVIS_STATE_DIR"] = _state.name
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
import channel_accounts
import chatbot_store
import mcp_store
import zernio_bot as z
from fastapi import FastAPI
from fastapi.testclient import TestClient
import routes.channels as routes


class ZernioSetupTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        routes.register(app, routes.ChannelsDeps(bot_status=lambda _: {}, main_bot_token=lambda: ""))
        self.client = TestClient(app)
        self.connections = [
            {"id": "connection-a", "connector_id": "zernio", "label": "Team A", "enabled": True},
            {"id": "connection-b", "connector_id": "zernio", "label": "Team B", "enabled": True},
            {"id": "disabled", "connector_id": "zernio", "enabled": False},
            {"id": "unrelated", "connector_id": "other", "enabled": True}]
        self.patches = [patch.object(mcp_store, "list_connections", return_value=self.connections),
                        patch.object(mcp_store, "connection_secrets", side_effect=lambda cid: {"api_key": "private-" + cid}),
                        patch.object(z, "_rest_accounts", side_effect=lambda key: [{"id": "provider-" + key, "username": key, "platform": "instagram"}])]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.account_ids = []
        self.addCleanup(lambda: [channel_accounts.delete_account(a) for a in self.account_ids])

    def credentials(self):
        return {"connection_id": "connection-b", "account_id": "provider-private-connection-b", "username": "private-connection-b", "secret": "private-signing"}

    def create(self):
        response = self.client.post("/channels/accounts", data={"channel": "zernio", "token": json.dumps(self.credentials()), "bot_username": "untrusted"})
        self.assertEqual(response.status_code, 200, response.text)
        self.account_ids.append(response.json()["id"])
        return response.json()["id"]

    def test_explicit_connection_selection_never_guesses(self):
        self.assertEqual(z.connection_api_key(), "")
        for cid in ("unknown", "disabled", "unrelated"):
            self.assertEqual(z.connection_api_key(cid), "")
        self.assertEqual(z.connection_api_key("connection-b"), "private-connection-b")
        self.assertEqual(z.available_connections(), [{"id": "connection-a", "label": "Team A"}, {"id": "connection-b", "label": "Team B"}])
        self.assertEqual(z.connected_instagram_accounts("connection-b")[0]["id"], "provider-private-connection-b")

    def test_invalid_explicit_connection_never_falls_back_to_unique_default(self):
        self.connections[:] = self.connections[:1]
        credentials = self.credentials()
        credentials["connection_id"] = "unknown"
        for endpoint in ("/channels/verify-token", "/channels/accounts"):
            response = self.client.post(endpoint, data={"channel": "zernio", "token": json.dumps(credentials)})
            self.assertFalse(response.json()["ok"], response.text)
        aid = self.create_with_manual_key()
        response = self.client.post(f"/channels/accounts/{aid}/update", data={"token": json.dumps(credentials)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "missing_api_key")

    def create_with_manual_key(self):
        credentials = self.credentials()
        credentials.pop("connection_id")
        credentials["api_key"] = "private-connection-b"
        response = self.client.post("/channels/accounts", data={"channel": "zernio", "token": json.dumps(credentials)})
        self.assertEqual(response.status_code, 200, response.text)
        self.account_ids.append(response.json()["id"])
        return response.json()["id"]

    def test_creation_pins_verified_key_and_blank_update_reverifies(self):
        aid = self.create()
        stored = json.loads(channel_accounts.get_token(aid))
        self.assertEqual(stored["api_key"], "private-connection-b")
        self.assertNotIn("connection_id", stored)
        # Changing/removing the source cannot silently select a different key at runtime.
        self.connections.clear()
        self.assertEqual(z.split_credentials(channel_accounts.get_token(aid))["api_key"], "private-connection-b")
        with patch.object(z, "_rest_accounts", side_effect=z.CredentialsError("invalid_api_key")):
            response = self.client.post(f"/channels/accounts/{aid}/update", data={"label": "must not save", "token": ""})
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json()["ok"])
            self.assertNotEqual(channel_accounts.get_account(aid)["label"], "must not save")
        with patch.object(chatbot_store, "bots_using_account", return_value=[{"id": "enabled-mock", "enabled": True}]), \
             patch.object(routes._DEPS, "restart_bot", create=True) as restart:
            response = self.client.post(f"/channels/accounts/{aid}/update", data={"label": "verified", "token": ""})
            restart.assert_not_called()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("private-signing", response.text)
        self.assertNotIn('"api_key"', response.text)
        self.assertFalse(response.json()["account"]["meta"]["webhook_secret_verified"])

    def test_generic_assignment_works_for_two_different_bots_without_enabling(self):
        aid = self.create()
        bots = {name: {"id": name, "name": name, "enabled": False, "account_ids": []} for name in ("support", "sales")}
        def update(bot_id, patch_data):
            bots[bot_id].update(patch_data)
            return True, ""
        def users(account_id):
            return [b for b in bots.values() if account_id in b["account_ids"]]
        with patch.object(chatbot_store, "get_bot", side_effect=bots.get), \
             patch.object(chatbot_store, "bots_using_account", side_effect=users), \
             patch.object(chatbot_store, "update_bot", side_effect=update), \
             patch.object(chatbot_store, "account_limit_error", return_value=""):
            for bot_id in bots:
                response = self.client.post(f"/channels/accounts/{aid}/bot", data={"bot_id": bot_id})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["ok"])
                self.assertIn(aid, bots[bot_id]["account_ids"])
                self.assertFalse(bots[bot_id]["enabled"])
            self.assertNotIn(aid, bots["support"]["account_ids"])

    def test_private_setup_endpoints_and_manual_key_do_not_echo_secrets(self):
        import main
        client = TestClient(main.app)
        with patch.object(main.cfgmod, "gate_active", return_value=True), patch.object(main.cfgmod, "valid_session", return_value=False):
            self.assertEqual(client.get("/channels/zernio/connections").status_code, 401)
            self.assertEqual(client.post("/channels/zernio/connected-accounts", data={"api_key": "private-manual"}).status_code, 401)
        with patch.object(main.cfgmod, "gate_active", return_value=False), \
             patch.object(z, "_rest_accounts", return_value=[{"id": "provider-1", "username": "alice", "platform": "instagram"}]):
            for response in [client.get("/channels/zernio/connections"),
                             client.get("/channels/zernio/connected-accounts?connection_id=connection-b"),
                             client.post("/channels/zernio/connected-accounts", data={"api_key": "private-manual"}),
                             client.get("/channels/webhook-info?channel=zernio&config_only=true")]:
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["ok"])
                self.assertNotIn("private-", response.text)
            self.assertEqual(client.post("/channels/zernio/connected-accounts", data={"api_key": " "}).status_code, 400)
            with patch.object(z, "_rest_accounts", side_effect=z.CredentialsError("provider_unavailable")):
                response = client.post("/channels/zernio/connected-accounts", data={"api_key": "private-manual"})
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json(), {"ok": False, "error": "provider_unavailable"})
                self.assertEqual(client.get("/channels/webhook-info?channel=zernio&config_only=true").status_code, 200)


if __name__ == "__main__":
    unittest.main()
