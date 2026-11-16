"""Offline security, routing and durable delivery tests for the Zernio server channel."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError

_test_root = tempfile.TemporaryDirectory(prefix="zernio-test-")
os.environ["JAVIS_STATE_DIR"] = _test_root.name
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
import channels
import channel_accounts
import conversations
import zernio_bot as z


class ZernioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=_test_root.name)
        self.store = z.DurableState(Path(self.directory.name) / "state.json")
        z._state_store = self.store
        z._REGISTRY.clear()
        z._ACCOUNTS.clear()
        self.clock = 1805418540.0
        self.time_patch = patch.object(z, "_now", lambda: self.clock)
        self.time_patch.start()
        self.bot = self.make_bot("provider-a", "acc_a", "bot_a", "alice", "secret-a")
        self.other = self.make_bot("provider-b", "acc_b", "bot_b", "bob", "secret-b")
        self.inbox = []
        self.record_original = conversations.ghi_su_kien
        def record(event):
            self.inbox.append(event)
            return self.record_original(event)
        self.record_patch = patch.object(conversations, "ghi_su_kien", record)
        self.record_patch.start()
        self.mode_patch = patch.object(conversations, "che_do", return_value="bot")
        self.mode = self.mode_patch.start()
        # A test must never send any HTTP request unless explicitly mocked below.
        self.http_guard = patch("httpx.AsyncClient", side_effect=AssertionError("unexpected network"))
        self.http_guard.start()

    def make_bot(self, provider, account, bot_id, username, secret):
        bot = z.ZernioBot({"account_id": provider, "username": username, "secret": secret, "api_key": "private-key"}, "", AsyncMock(return_value={"text": "answer"}))
        bot.account_id, bot.bot_id = account, bot_id
        bot.send_delivery = AsyncMock(return_value={"kind": "accepted", "code": "", "retry_after_seconds": None})
        bot.start()
        return bot

    async def asyncTearDown(self):
        for timer in z._TIMERS.values():
            timer.cancel()
        z._TIMERS.clear()
        self.time_patch.stop()
        self.record_patch.stop()
        self.mode_patch.stop()
        self.http_guard.stop()
        z._REGISTRY.clear()
        z._ACCOUNTS.clear()
        self.directory.cleanup()

    def event(self, event_id="e1", message_id="m1", conv="same-conversation", bot=None, text="hello"):
        bot = bot or self.bot
        return {"id": event_id, "event": "message.received", "timestamp": datetime.datetime.fromtimestamp(self.clock, datetime.timezone.utc).isoformat(),
                "account": {"id": bot.provider_account_id, "username": bot.bot_username, "platform": "instagram"},
                "conversation": {"id": conv}, "message": {"id": message_id, "platformMessageId": message_id,
                "direction": "incoming", "text": text, "sender": {"id": "customer", "username": "customer"}}}

    async def receive(self, event=None, secret=None):
        raw = json.dumps(event or self.event()).encode()
        signature = hmac.new((secret or self.bot.secret).encode(), raw, hashlib.sha256).hexdigest()
        return await z.handle_webhook(raw, {"X-Zernio-Signature": signature})

    async def flush(self, bot=None, conv="same-conversation"):
        await z._flush(z._batch_key((bot or self.bot).provider_account_id, conv))

    async def test_two_accounts_same_conversation_route_and_inbox_ids(self):
        self.assertEqual((await self.receive())[0], 202)
        self.assertEqual((await self.receive(self.event("e2", "m2", bot=self.other), self.other.secret))[0], 202)
        self.assertEqual([(e["account_id"], e["bot_id"]) for e in self.inbox], [("acc_a", "bot_a"), ("acc_b", "bot_b")])
        self.assertTrue(all(isinstance(e["bot_id"], str) for e in self.inbox))
        self.clock += 5
        await asyncio.gather(self.flush(), self.flush(self.other))
        self.bot.answer_fn.assert_awaited_once()
        self.other.answer_fn.assert_awaited_once()
        self.assertEqual(self.bot.answer_fn.call_args.args[1]["account_id"], "acc_a")
        self.assertEqual(self.other.answer_fn.call_args.args[1]["provider_account_id"], "provider-b")

    async def test_wrong_or_missing_mapping_never_falls_back(self):
        event = self.event()
        event["account"]["id"] = "unmapped"
        self.assertEqual((await self.receive(event))[0], 404)
        self.assertEqual((await self.receive(self.event(bot=self.other)))[0], 401)
        self.bot.stop()
        self.assertEqual((await self.receive())[0], 404)
        self.assertFalse(self.inbox)
        self.other.answer_fn.assert_not_awaited()

    async def test_duplicate_assignment_rejected_and_stop_keeps_other_registration(self):
        with self.assertRaises(ValueError):
            self.make_bot("provider-a", "acc_wrong", "bot_wrong", "alice", "secret-a")
        self.assertIs(z._REGISTRY["provider-a"], self.bot)

    async def test_signature_envelope_replay_and_eligibility(self):
        raw = json.dumps(self.event()).encode()
        self.assertEqual((await z.handle_webhook(raw, {}))[0], 401)
        self.assertEqual((await self.receive(secret="wrong"))[0], 401)
        self.assertFalse(z.verify_signature(raw, "a" * 63, "secret-a"))
        self.assertEqual((await z.handle_webhook(b"{}" * z.MAX_BODY_BYTES, {}))[0], 413)
        for field, value in (("direction", "outgoing"), ("isEcho", True), ("historical", True)):
            event = self.event("event-" + field)
            event["message"][field] = value
            self.assertEqual((await self.receive(event))[0], 202)
        event = self.event("old")
        event["timestamp"] = "2000-01-01T00:00:00Z"
        self.assertEqual((await self.receive(event))[1]["ignored"], "replay_or_historical")
        event["timestamp"] = "bad"
        self.assertEqual((await self.receive(event))[0], 400)
        event = {"id": "test", "event": "webhook.test", "timestamp": self.event()["timestamp"], "message": "test"}
        self.assertEqual((await self.receive(event))[0], 200)
        self.assertFalse(self.inbox)

    async def test_malformed_nested_objects(self):
        for key in ("account", "message", "conversation", "metadata"):
            event = self.event()
            event[key] = ["bad"]
            self.assertEqual((await self.receive(event))[0], 400)
        event = self.event()
        event["message"]["sender"] = ["bad"]
        self.assertEqual((await self.receive(event))[0], 400)

    async def test_debounce_five_seconds_since_last_message(self):
        await self.receive()
        self.clock += 4
        await self.receive(self.event("e2", "m2", text="second"))
        self.clock += 1
        await self.flush()
        self.bot.answer_fn.assert_not_awaited()
        self.clock += 4
        await self.flush()
        self.assertEqual(self.bot.answer_fn.call_args.args[0], "hello\nsecond")
        self.bot.send_delivery.assert_awaited_once()

    async def test_restart_recovers_dedup_and_pending_timer(self):
        await self.receive()
        for timer in z._TIMERS.values():
            timer.cancel()
        z._TIMERS.clear()
        self.bot.stop()
        z._state_store = z.DurableState(self.store.file_path)
        self.bot.start()
        key = z._batch_key("provider-a", "same-conversation")
        self.assertIn(key, z._TIMERS)
        self.assertEqual((await self.receive())[1].get("duplicate"), True)
        self.assertEqual((await self.receive(self.event("retry-event")))[1]["status"], "duplicate_message")
        self.clock += 5
        await self.flush()
        self.bot.answer_fn.assert_awaited_once()
        self.assertEqual(len([e for e in self.inbox if e["sender_type"] == "customer"]), 1)
        self.assertEqual(len([e for e in self.inbox if e["sender_type"] == "ai"]), 1)

    async def test_silent_and_takeover_messages_remain_in_real_inbox(self):
        await self.receive()
        self.assertTrue(conversations.tin_theo_id("zernio", "acc_a", "same-conversation", "m1"))
        self.mode.return_value = "human"
        self.clock += 5
        await self.flush()
        self.bot.answer_fn.assert_not_awaited()
        self.assertEqual(len(self.inbox), 1)
        self.mode.return_value = "bot"
        self.bot.answer_fn.return_value = {"im_lang": True, "text": "hidden"}
        await self.receive(self.event("e2", "m2"))
        self.clock += 5
        await self.flush()
        self.bot.send_delivery.assert_not_awaited()
        self.assertTrue(conversations.tin_theo_id("zernio", "acc_a", "same-conversation", "m2"))

    async def test_takeover_during_model_prevents_send(self):
        async def answer(*args):
            self.mode.return_value = "human"
            return "do not send"
        self.bot.answer_fn.side_effect = answer
        await self.receive()
        self.clock += 5
        await self.flush()
        self.bot.send_delivery.assert_not_awaited()

    async def test_concurrent_flush_and_arrival_do_not_overwrite_messages(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def answer(*args):
            entered.set()
            await release.wait()
            return "answer"
        self.bot.answer_fn.side_effect = answer
        await self.receive()
        self.clock += 5
        task = asyncio.create_task(self.flush())
        await entered.wait()
        await self.receive(self.event("new", "new-message", text="new message"))
        await self.receive(self.event("other", "other-message", bot=self.other), self.other.secret)
        await self.flush()  # Same conversation is already locked.
        release.set()
        await task
        state = self.store.load()
        key = z._batch_key("provider-a", "same-conversation")
        self.assertEqual([m["id"] for m in state["conversations"][key]["messages"]], ["new-message"])
        self.assertEqual(len(state["conversations"][z._batch_key("provider-b", "same-conversation")]["messages"]), 1)
        self.bot.answer_fn.assert_awaited_once()
        self.clock += 5
        await self.flush()
        self.assertEqual(self.bot.answer_fn.await_count, 2)

    async def test_failed_send_restart_reuses_reply_and_idempotency_key(self):
        self.bot.send_delivery.return_value = {"kind": "retry", "code": "provider_unavailable", "retry_after_seconds": None}
        await self.receive()
        self.clock += 5
        await self.flush()
        key = self.bot.send_delivery.call_args.args[2]
        z._state_store = z.DurableState(self.store.file_path)
        self.bot.send_delivery.return_value = {"kind": "accepted", "code": "", "retry_after_seconds": None}
        self.clock = self.delivery_state()["next_retry_at"]
        await self.flush()
        self.bot.answer_fn.assert_awaited_once()
        self.assertEqual(self.bot.send_delivery.call_args.args[2], key)
        self.assertNotIn("processing", self.store.load()["conversations"][z._batch_key("provider-a", "same-conversation")])

    async def test_inbox_failure_not_acknowledged_or_deduplicated(self):
        with patch.object(conversations, "ghi_su_kien", return_value={"ok": False}):
            with self.assertRaisesRegex(RuntimeError, "inbox_write_failed"):
                await self.receive()
        self.assertNotIn("e1", self.store.load()["events"])
        self.assertEqual((await self.receive())[0], 202)

    async def test_assignment_change_never_runs_old_pending_batch(self):
        await self.receive()
        self.clock += 5
        self.bot.bot_id = "bot_reassigned"
        await self.flush()
        self.bot.answer_fn.assert_not_awaited()
        self.assertTrue(self.store.load()["conversations"][z._batch_key("provider-a", "same-conversation")]["messages"])

    async def test_legacy_json_migration_preserves_inbox_and_removes_permanent_cap(self):
        legacy = Path(self.directory.name) / "legacy.json"
        legacy.write_text(json.dumps({"events": {}, "messages": {}, "conversations": {"old-chat": {
            "account_id": "provider-a", "messages": [self.event()["message"]], "replies_in_window": 5, "takeover": True}}}))
        z._state_store = z.DurableState(legacy)
        z.resume_pending("provider-a")
        await self.flush(conv="old-chat")
        self.bot.answer_fn.assert_awaited_once()
        self.assertTrue(conversations.tin_theo_id("zernio", "acc_a", "old-chat", "m1"))

    async def test_no_permanent_five_reply_cap(self):
        for number in range(7):
            await self.receive(self.event(f"cap-e{number}", f"cap-m{number}"))
            self.clock += 5
            await self.flush()
        self.assertEqual(self.bot.send_delivery.await_count, 7)

    async def test_adapter_fail_closed_scoped_and_durable(self):
        payload = {"conversationId": "adapter-chat", "account": {"id": "provider-a"},
                   "messages": [self.event()["message"]], "policy": {"maxCustomerReplies": 1}}
        with patch.dict(os.environ, {"ZERNIO_ADAPTER_TOKEN": "", "ZERNIO_ADAPTER_ACCOUNT_ID": ""}):
            self.assertEqual((await z.handle_inbound(payload, "Bearer any"))[0], 401)
        with patch.dict(os.environ, {"ZERNIO_ADAPTER_TOKEN": "scoped", "ZERNIO_ADAPTER_ACCOUNT_ID": "provider-a"}):
            self.assertEqual((await z.handle_inbound(payload, "scoped"))[0], 401)
            payload["account"]["id"] = "provider-b"
            self.assertEqual((await z.handle_inbound(payload, "Bearer scoped"))[0], 403)
            payload["account"]["id"] = "provider-a"
            payload["bot_id"] = "bot_b"
            self.assertEqual((await z.handle_inbound(payload, "Bearer scoped"))[0], 400)
            payload.pop("bot_id")
            self.mode.return_value = "human"
            status, result = await z.handle_inbound(payload, "Bearer scoped")
            self.assertEqual(status, 202)
            self.assertTrue(result["takeover"])
            self.assertFalse(result["replySent"])
            self.assertTrue(conversations.tin_theo_id("zernio", "acc_a", "adapter-chat", "m1"))
            self.bot.answer_fn.assert_not_awaited()
            self.assertEqual((await z.handle_inbound(payload, "Bearer scoped"))[0], 202)
            self.assertEqual(len(self.inbox), 1)

    async def test_real_rest_verification_mock_success_mismatch_and_failure(self):
        credentials = {"account_id": "provider-a", "username": "alice", "secret": "private-secret", "api_key": "private-key"}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({"accounts": [{"_id": "provider-a", "username": "alice", "platform": "instagram", "accessToken": "never-public"}]}).encode()
        with patch("urllib.request.urlopen", return_value=Response()) as request:
            result = await channels.module("zernio").verify_token(credentials)
            self.assertTrue(result["ok"])
            self.assertTrue(request.call_args.args[0].full_url.startswith("https://zernio.com/api/v1/accounts?"))
            self.assertEqual(request.call_args.args[0].get_header("Authorization"), "Bearer private-key")
            self.assertNotIn("private", json.dumps(result))
            self.assertNotIn("accessToken", json.dumps(result))
            self.assertFalse(result["meta"]["webhook_secret_verified"])
            self.assertFalse((await z.whoami(dict(credentials, account_id="wrong")))["ok"])
            self.assertEqual((await z.whoami(dict(credentials, username="bob")))["error"], "account_username_mismatch")
        with patch("urllib.request.urlopen", side_effect=HTTPError("url", 401, "secret-provider-response", {}, None)):
            result = await z.whoami(credentials)
            self.assertEqual(result, {"ok": False, "error": "invalid_api_key"})
        with patch("urllib.request.urlopen", side_effect=TimeoutError("secret")):
            self.assertEqual((await z.whoami(credentials))["error"], "provider_unavailable")
        self.assertEqual((await z.whoami(dict(credentials, api_key="")))["error"], "missing_api_key")

    async def test_stale_public_metadata_cannot_leak(self):
        public = channel_accounts._public({"id": "acc_a", "channel": "zernio", "token_enc": "private", "meta": {
            "account_id": "provider-a", "username": "alice", "secret": "hidden", "api_key": "hidden", "nested": {"secret": "hidden"}}})
        self.assertNotIn("hidden", json.dumps(public))
        self.assertNotIn("private", json.dumps(public))

    async def test_runtime_start_preserves_both_account_identities(self):
        import chatbot_runtime as runtime
        cfg = {"id": "bot_runtime", "channel": "zernio", "brain": "test"}
        token = json.dumps({"account_id": "provider-runtime", "username": "runtime", "secret": "runtime-secret", "api_key": "key"})
        with patch.object(runtime.chatbot_store, "get_bot", return_value=cfg), \
             patch.object(runtime.chatbot_store, "tokens", return_value=[({"id": "acc_runtime", "channel": "zernio"}, token)]), \
             patch.object(runtime, "_make_answer_fn", return_value=AsyncMock()), \
             patch.object(runtime, "_make_command_fn", return_value=None), \
             patch.object(runtime, "_make_precheck_fn", return_value=None), \
             patch.object(runtime, "_make_event_fn", return_value=None), \
             patch.object(runtime, "_inbox_dir", return_value=self.directory.name), \
             patch.object(runtime, "_admin_token", return_value=""), \
             patch.dict(runtime._deps, {"answer": lambda: None}):
            ok, error = runtime.start_bot("bot_runtime")
            self.assertTrue(ok, error)
            bot = z._REGISTRY["provider-runtime"]
            self.assertEqual((bot.account_id, bot.provider_account_id, bot.bot_id),
                             ("acc_runtime", "provider-runtime", "bot_runtime"))
            runtime.stop_bot("bot_runtime")

    async def test_reassignment_quarantines_old_batch_and_accepts_new_messages(self):
        await self.receive()
        self.bot.bot_id = "bot_new"
        await self.receive(self.event("new-assignment", "new-message"))
        self.clock += 5
        await self.flush()
        self.assertEqual(self.bot.answer_fn.call_args.args[1]["message_id"], "new-message")
        state = self.store.load()
        self.assertEqual(state["quarantined_batches"][0]["bot_id"], "bot_a")
        self.assertEqual(state["quarantined_batches"][0]["messages"][0]["id"], "m1")
        self.assertEqual(len([e for e in self.inbox if e["sender_type"] == "customer"]), 2)
        self.assertEqual(len([e for e in self.inbox if e["sender_type"] == "ai"]), 1)

    def delivery_state(self):
        return self.store.load()["conversations"][z._batch_key("provider-a", "same-conversation")]

    def restart_delivery(self):
        for timer in z._TIMERS.values():
            timer.cancel()
        z._TIMERS.clear()
        self.bot.stop()
        z._state_store = z.DurableState(self.store.file_path)
        self.bot.start()

    def mock_provider(self, status=503, retry_after=None, error=None):
        from types import SimpleNamespace
        client = AsyncMock()
        client.post.return_value = SimpleNamespace(status_code=status, headers={"Retry-After": retry_after})
        client.post.side_effect = error
        context = AsyncMock()
        context.__aenter__.return_value = client
        self.provider_patch = patch("httpx.AsyncClient", return_value=context)
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        # Use production transport; mock only the external HTTP boundary.
        del self.bot.send_delivery
        return client

    async def test_expired_batch_handoffs_without_head_of_line_retry(self):
        client = self.mock_provider()
        self.mode_patch.stop()
        cid = conversations.conversation_id_of("zernio", "acc_a", "same-conversation")
        if cid:
            conversations.dat_che_do(cid, "ai")
        await self.receive()
        self.clock += 5
        await self.flush()
        self.clock += 23 * 3600
        await self.flush()
        current = self.delivery_state()
        self.assertNotIn("processing", current)
        self.assertEqual(current["delivery_issue"]["reason"], "idempotency_window_expired")
        self.assertEqual(current["delivery_batch"]["processing"][0]["id"], "m1")
        self.assertTrue(current["delivery_batch"]["send_key"])
        self.assertEqual(conversations.che_do("zernio", "acc_a", "same-conversation"), "human")
        await self.receive(self.event("e2", "m2"))
        self.restart_delivery()
        self.clock += 5
        await self.flush()
        self.assertTrue(conversations.tin_theo_id("zernio", "acc_a", "same-conversation", "m2"))
        self.assertNotIn("processing", self.delivery_state())
        self.assertEqual(client.post.await_count, 1)

    async def test_auth_error_blocks_once(self):
        client = self.mock_provider(401)
        await self.receive()
        self.clock += 5
        await self.flush()
        self.assertEqual(self.delivery_state().get("delivery_issue", {}).get("reason"), "provider_http_401")
        key = z._batch_key("provider-a", "same-conversation")
        self.assertNotIn(key, z._TIMERS)
        self.restart_delivery()
        self.clock += 100
        await self.flush()
        self.assertEqual(client.post.await_count, 1)
        self.assertNotIn(key, z._TIMERS)

    async def test_restart_preserves_reply_and_send_key(self):
        client = self.mock_provider(error=TimeoutError())
        await self.receive()
        self.clock += 5
        await self.flush()
        current = self.delivery_state()
        self.assertEqual(current.get("attempts"), 1)
        self.assertEqual(current.get("delivery_issue", {}).get("reason"), "provider_unavailable")
        self.assertEqual(current["delivery_issue"]["attempts"], 1)
        self.assertEqual(current["delivery_issue"]["next_retry_at"], current["next_retry_at"])
        retry_at = current["next_retry_at"]
        self.assertGreaterEqual(retry_at, self.clock + 5)
        self.restart_delivery()
        await self.receive(self.event("e2", "m2"))
        await self.flush()
        self.assertEqual(client.post.await_count, 1)
        self.clock = retry_at
        await self.flush()
        self.assertEqual(self.delivery_state()["attempts"], 2)
        self.assertEqual(self.delivery_state()["reply"], current["reply"])
        self.assertEqual(self.delivery_state()["send_key"], current["send_key"])
        self.assertEqual(client.post.call_args_list[0].kwargs["headers"]["Idempotency-Key"],
                         client.post.call_args_list[1].kwargs["headers"]["Idempotency-Key"])
        self.bot.answer_fn.assert_awaited_once()

    async def test_retry_after_survives_restart_and_deadline(self):
        client = self.mock_provider(429, "120")
        await self.receive()
        self.clock += 5
        await self.flush()
        self.assertEqual(self.delivery_state().get("next_retry_at"), self.clock + 120)
        self.restart_delivery()
        self.clock += 119
        await self.flush()
        self.assertEqual(client.post.await_count, 1)
        self.clock += 1
        client.post.return_value.headers = {"Retry-After": "999999"}
        await self.flush()
        self.assertNotIn("processing", self.delivery_state())
        self.assertEqual(self.delivery_state()["delivery_issue"]["reason"], "idempotency_window_expired")

    async def test_restart_completes_handoff_between_databases(self):
        self.mock_provider(403)
        await self.receive()
        self.clock += 5
        with patch.object(conversations, "dat_che_do", side_effect=RuntimeError("simulated crash")):
            await self.flush()
        current = self.delivery_state()
        self.assertIn("delivery_issue", current)
        self.assertTrue(current["handoff_pending"])
        issue_id = current["delivery_issue"]["id"]
        self.restart_delivery()
        await self.flush()
        self.assertFalse(self.delivery_state()["handoff_pending"])
        self.assertEqual(self.delivery_state()["delivery_issue"]["id"], issue_id)
        cid = conversations.conversation_id_of("zernio", "acc_a", "same-conversation")
        self.assertEqual(conversations.chi_tiet(cid)["mode"], "human")

    async def test_inflight_reassignment_cannot_write_reply_into_new_batch(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def answer(*args):
            entered.set()
            await release.wait()
            return "old bot answer"
        self.bot.answer_fn.side_effect = answer
        await self.receive()
        self.clock += 5
        task = asyncio.create_task(self.flush())
        await entered.wait()
        self.bot.bot_id = "new-assignment"
        await self.receive(self.event("new-event", "new-message"))
        release.set()
        await task
        current = self.store.load()["conversations"][z._batch_key("provider-a", "same-conversation")]
        self.assertNotIn("reply", current)
        self.assertNotIn("processing", current)
        self.assertEqual(current["messages"][0]["id"], "new-message")
        self.bot.send_delivery.assert_not_awaited()

    async def test_outbound_uses_provider_identity_and_sanitizes_errors(self):
        class Response:
            status_code = 201
            text = "private-provider-response"
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, url, **kwargs):
                self_test.assertTrue(url.startswith("https://zernio.com/api/v1/inbox/conversations/"))
                self_test.assertEqual(kwargs["json"]["accountId"], "provider-a")
                self_test.assertEqual(kwargs["headers"]["Idempotency-Key"], "stable-key")
                return Response()
        self_test = self
        with patch("httpx.AsyncClient", Client):
            self.assertTrue((await z.send_api_message(self.bot.creds, "chat", "text", "stable-key"))[0])
            Response.status_code = 403
            self.assertEqual(await z.send_api_message(self.bot.creds, "chat", "text", "stable-key"), (False, "provider_http_403"))

    async def test_account_http_api_always_verifies_and_returns_safe_metadata(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import routes.channels as routes
        app = FastAPI()
        routes.register(app, routes.ChannelsDeps(bot_status=lambda _: {}, main_bot_token=lambda: ""))
        client = TestClient(app)
        token = json.dumps({"account_id": "provider-http", "username": "http", "secret": "private-secret", "api_key": "private-key"})
        verified = {"ok": True, "username": "http", "meta": {"account_id": "provider-http", "username": "http", "platform": "instagram"}}
        with patch.object(routes, "verify_token", AsyncMock(return_value={"ok": False, "error": "invalid_api_key", "code": "invalid_api_key"})) as verify:
            result = client.post("/channels/accounts", data={"channel": " ZERNIO ", "token": token, "bot_username": "skip-check"})
            self.assertEqual(result.status_code, 400)
            verify.assert_awaited_once()
        with patch.object(routes, "verify_token", AsyncMock(return_value=verified)):
            result = client.post("/channels/accounts", data={"channel": "zernio", "token": token, "bot_username": "skip-check"})
            self.assertEqual(result.status_code, 200, result.text)
            account_id = result.json()["id"]
            self.assertEqual(result.json()["account"]["meta"]["account_id"], "provider-http")
            self.assertNotIn("private", result.text)
            updated = client.post(f"/channels/accounts/{account_id}/update", data={"token": token, "bot_username": "fake-name"})
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertNotIn("private", updated.text)
            changed = client.post(f"/channels/accounts/{account_id}/update", data={"token": token.replace("provider-http", "another-provider")})
            self.assertEqual(changed.status_code, 400)
            self.assertEqual(changed.json()["code"], "provider_identity_changed")
        channel_accounts.delete_account(account_id)

    async def test_rest_pagination_and_failures(self):
        class Response:
            def __init__(self, data): self.data = data
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps(self.data).encode()
        pages = [Response({"accounts": [], "pagination": {"nextCursor": "next"}}),
                 Response({"accounts": [{"id": "last", "platform": "instagram", "username": "last"}]})]
        with patch("urllib.request.urlopen", side_effect=pages) as request:
            self.assertEqual(z._rest_accounts("key")[0]["id"], "last")
            self.assertIn("cursor=next", request.call_args.args[0].full_url)
        with patch("urllib.request.urlopen", return_value=Response({"unexpected": []})):
            with self.assertRaisesRegex(z.CredentialsError, "invalid_provider_response"):
                z._rest_accounts("key")

    async def test_cross_process_lock_is_released_after_worker_exit(self):
        import subprocess
        import sys
        program = """
import sqlite3, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import zernio_bot as z
store = z.DurableState(Path(sys.argv[2]))
guard = store.conversation_lock('process-lock')
print('locked' if guard else 'failed', flush=True)
sys.stdin.read()
"""
        child = subprocess.Popen([sys.executable, "-c", program, str(SERVER), str(self.store.file_path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(await asyncio.to_thread(child.stdout.readline), "locked\n")
            self.assertIsNone(self.store.conversation_lock("process-lock"))
        finally:
            child.terminate()
            await asyncio.to_thread(child.wait, 10)
            child.stdin.close()
            child.stdout.close()
        guard = self.store.conversation_lock("process-lock")
        self.assertIsNotNone(guard)
        guard.close()

    async def test_actual_public_ingress_and_private_webhook_info(self):
        from fastapi.testclient import TestClient
        import main
        client = TestClient(main.app)
        with patch.object(main.cfgmod, "gate_active", return_value=True), \
             patch.object(main.cfgmod, "valid_session", return_value=False):
            raw = json.dumps(self.event()).encode()
            signature = hmac.new(self.bot.secret.encode(), raw, hashlib.sha256).hexdigest()
            response = client.post("/webhooks/zernio", content=raw,
                                   headers={"X-Zernio-Signature": signature, "Content-Type": "application/json"})
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(client.post("/webhooks/zernio", content=raw).status_code, 401)
            self.assertEqual(client.post("/webhooks/zernio/extra", content=raw).status_code, 401)
            self.assertEqual(client.post("/zernio/inbound", json={}).status_code, 401)
            self.assertEqual(client.get("/channels/webhook-info?channel=zernio").status_code, 401)
            self.assertEqual(client.get("/channels/zernio/connected-accounts").status_code, 401)
        with patch.object(main.cfgmod, "gate_active", return_value=False), \
             patch.object(z, "connected_instagram_accounts", return_value=[{"id": "provider-a", "username": "alice", "platform": "instagram"}]):
            response = client.get("/channels/webhook-info?channel=zernio")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertTrue(body["webhook_url"].endswith("/webhooks/zernio"))
            self.assertEqual(body["signature_algorithm"], "HMAC-SHA256")
            self.assertEqual(body["account_id_kind"], "zernio_provider")
            self.assertEqual(body["verify_token"], "")
            self.assertNotIn("private-key", response.text)
            self.assertNotIn("secret-a", response.text)
        with patch.object(main.cfgmod, "gate_active", return_value=False), \
             patch.object(z, "connected_instagram_accounts", side_effect=z.CredentialsError("provider_unavailable")):
            response = client.get("/channels/webhook-info?channel=zernio")
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json()["error"], "provider_unavailable")

    async def test_public_route_allowlists_are_exact(self):
        # Parse the constant without importing main and starting server services.
        import ast
        tree = ast.parse((ROOT / "server/main.py").read_text())
        values = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ("_AUTH_PUBLIC_EXACT", "_AUTH_PUBLIC_PREFIX"):
                        values[target.id] = ast.literal_eval(node.value)
        self.assertIn("/webhooks/zernio", values["_AUTH_PUBLIC_EXACT"])
        for path in ("/webhooks/zernio/extra", "/zernio/webhook", "/channels/zernio/connected-accounts", "/channels/zernio/webhook-info"):
            self.assertNotIn(path, values["_AUTH_PUBLIC_EXACT"])
            self.assertFalse(any(path.startswith(prefix) for prefix in values["_AUTH_PUBLIC_PREFIX"]))
        import bot_shield
        self.assertIn("/webhooks/zernio", bot_shield.MACHINE_EXACT)


if __name__ == "__main__":
    unittest.main()
