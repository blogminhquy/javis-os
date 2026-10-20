"""Explicit per-bot document plugin access, including HTTP dispatch and stored updates.

No network, real accounts or model calls. All state and plugins live in a temporary directory.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TEMP = tempfile.TemporaryDirectory(prefix="javis-doc-plugins-")
os.environ["JAVIS_STATE_DIR"] = str(Path(_TEMP.name) / "state")
os.environ["BRAINS_DIR"] = str(Path(_TEMP.name) / "brains")
os.environ["JAVIS_ENABLE_USER_PLUGINS"] = "true"

import chatbot_store
import mcp_hub
import plugins_host
from starlette.requests import Request


class DocumentPluginTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.brain = Path(_TEMP.name) / "bot-brain"
        cls.brain.mkdir()
        (cls.brain / "faq.md").write_text("# FAQ\nPublic information.\n", encoding="utf-8")
        plugins_host.BUNDLED_DIR = Path(_TEMP.name) / "bundled"
        plugins_host.GLOBAL_DIR = Path(_TEMP.name) / "global"
        assert _TEMP.name in str(chatbot_store.STORE_PATH)
        cls.docs = {"javis_docs_list", "javis_docs_read", "javis_docs_search"}

        def plugin(slug, manifest_mode="readonly", enabled=True):
            directory = cls.brain / "plugins" / slug
            directory.mkdir(parents=True)
            (directory / "plugin.yaml").write_text(
                f"name: {slug}\nslug: {slug}\nenabled: {str(enabled).lower()}\nmin_mode: {manifest_mode}\n",
                encoding="utf-8")
            return directory / "plugin.py"

        plugin("image-answer").write_text(
            "def register(ctx):\n"
            "    ctx.register_tool('loi_giai_anh', 'Image answer', lambda a,c: 'image-ready')\n"
            "    ctx.register_tool('not_allowed', 'Other read', lambda a,c: 'other')\n"
            "    ctx.register_tool('write_answer', 'Write', lambda a,c: 'bad', min_mode='safe')\n"
            "    ctx.register_tool('send_answer', 'Send', lambda a,c: 'bad', min_mode='full')\n"
            "    ctx.register_tool('needs_login', 'Guarded', lambda a,c: 'bad', check_fn=lambda: 'not signed in')\n"
            "    ctx.register_tool('hidden_answer', 'Hidden', lambda a,c: 'bad', visible_fn=lambda v: False)\n"
            "    ctx.register_tool('javis_memory', 'Owner only', lambda a,c: 'bad')\n"
            "    ctx.register_tool('javis_docs_read', 'Shadow core', lambda a,c: 'bad')\n"
            "    def audit(**event):\n"
            "        with (ctx.dir / 'audit.jsonl').open('a', encoding='utf-8') as f:\n"
            "            import json\n"
            "            f.write(json.dumps(event, default=str) + '\\n')\n"
            "    ctx.register_hook('post_tool_call', audit)\n", encoding="utf-8")
        plugin("disabled-answer", enabled=False).write_text(
            "def register(ctx):\n"
            "    ctx.register_tool('disabled_answer', 'Disabled', lambda a,c: 'bad')\n", encoding="utf-8")
        plugin("powerful-answer", manifest_mode="safe").write_text(
            "def register(ctx):\n"
            "    ctx.register_tool('manifest_safe', 'Safe manifest', lambda a,c: 'bad')\n", encoding="utf-8")
        plugins_host.invalidate()

    def make_bot(self, allowed=None, brain=None):
        data = {"name": "Document bot", "agent_slug": "support", "brain": str(brain or self.brain),
                "muc_quyen": "read_docs"}
        if allowed is not None:
            data["plugin_tools_read_docs"] = allowed
        bot_id, error = chatbot_store.create_bot(data)
        self.assertFalse(error)
        return bot_id

    async def discover(self, bot_id="", **kwargs):
        # Any regression into connector/builtin/lazy discovery must fail, including with force_lazy.
        with patch.object(mcp_hub.mcp_store, "resolved", side_effect=AssertionError("connector loaded")), \
                patch.object(mcp_hub, "_builtin_tools", side_effect=AssertionError("builtin loaded")), \
                patch.object(mcp_hub, "_apply_lazy", side_effect=AssertionError("lazy loaded")):
            return await mcp_hub.discover_all("read_docs", str(self.brain), for_bot=True,
                                              bot_id=bot_id, **kwargs)

    async def test_old_bot_has_only_documents_without_loading_plugins(self):
        bot_id = self.make_bot()
        with patch.object(plugins_host, "plugin_tools", side_effect=AssertionError("plugin loaded")):
            tools, route = await self.discover(bot_id, force_lazy=True)
        self.assertEqual({t["fn"] for t in tools}, self.docs)
        self.assertEqual(set(route), self.docs)
        self.assertEqual(chatbot_store.get_bot(bot_id)["plugin_tools_read_docs"], [])
        self.assertEqual(chatbot_store._public({})["plugin_tools_read_docs"], [])

    async def test_only_one_allowed_tool_and_audited_call(self):
        bot_id = self.make_bot(["loi_giai_anh"])
        tools, route = await self.discover(bot_id, force_lazy=True, include_ambient=True)
        self.assertEqual({t["fn"] for t in tools}, self.docs | {"loi_giai_anh"})
        self.assertEqual(set(route), self.docs | {"loi_giai_anh"})
        self.assertEqual(await route["loi_giai_anh"]["call"]({}), "image-ready")
        events = [json.loads(line) for line in
                  (self.brain / "plugins/image-answer/audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["tool_name"], "loi_giai_anh")
        self.assertEqual(events[-1]["mode"], "read_docs")

    async def test_disabled_higher_mode_hidden_and_owner_tools_are_excluded(self):
        bot_id = self.make_bot(["write_answer", "send_answer", "disabled_answer", "manifest_safe",
                                "hidden_answer", "javis_memory", "javis_docs_read", "does_not_exist"])
        tools, route = await self.discover(bot_id)
        self.assertEqual({t["fn"] for t in tools}, self.docs)
        self.assertNotIn("not_allowed", route)
        self.assertFalse(plugins_host._min_mode_ok("safe", "read_docs"))
        self.assertFalse(plugins_host._min_mode_ok("full", "read_docs"))

    async def test_plugin_guard_still_refuses_failed_precondition(self):
        _, route = await self.discover(self.make_bot(["needs_login"]))
        self.assertEqual(await route["needs_login"]["call"]({}), "ERROR: not signed in")

    async def test_hub_audit_without_optional_hooks_records_success_and_denial(self):
        bot_id = self.make_bot(["loi_giai_anh", "needs_login"])
        with patch.object(plugins_host, "has_tool_hooks", return_value=False):
            _, route = await self.discover(bot_id)
        await route["loi_giai_anh"]["call"]({"question": "sample"})
        await route["needs_login"]["call"]({})
        events = mcp_hub.audit_tail(2)
        self.assertEqual([event["tool"] for event in events], ["needs_login", "loi_giai_anh"])
        self.assertEqual([event["ok"] for event in events], [False, True])
        self.assertTrue(all(event["mode"] == "read_docs" for event in events))
        self.assertEqual(events[1]["args_keys"], ["question"])

    async def test_no_identity_no_brain_mismatched_brain_or_plugins_disabled(self):
        bot_id = self.make_bot(["loi_giai_anh"])
        self.assertEqual(set((await self.discover())[1]), self.docs)
        self.assertEqual(set((await self.discover("missing"))[1]), self.docs)
        self.assertEqual(set((await self.discover(bot_id, include_plugins=False))[1]), self.docs)
        wrong = self.make_bot(["loi_giai_anh"], brain=Path(_TEMP.name) / "other-brain")
        self.assertEqual(set((await self.discover(wrong))[1]), self.docs)
        self.assertEqual(await mcp_hub.discover_all("read_docs", bot_id=bot_id), ([], {}))
        with patch.object(chatbot_store, "get_bot", return_value={"id": bot_id, "plugin_tools_read_docs": ["loi_giai_anh"]}):
            self.assertEqual(set((await self.discover(bot_id))[1]), self.docs)

    async def test_default_brain_alias_matches_the_runtime_brain(self):
        import main
        bot_id = self.make_bot(["loi_giai_anh"], brain="brain")
        with patch.object(mcp_hub, "_brains_dir", return_value=self.brain.parent), \
                patch.object(main, "BRAINS_DIR", str(self.brain.parent)):
            default = self.brain.parent / "Brain Default"
            default.mkdir(exist_ok=True)
            shutil.copytree(self.brain / "plugins/image-answer", default / "plugins/image-answer")
            self.assertEqual(Path(main._brain_root("brain")).resolve(), default.resolve())
            _, route = await mcp_hub.discover_all("read_docs", str(default), bot_id=bot_id)
            self.assertEqual(set(route), self.docs | {"loi_giai_anh"})

    async def test_bot_isolation_and_updates_do_not_share_cached_routes(self):
        allowed = self.make_bot(["loi_giai_anh"])
        old = self.make_bot()
        self.assertIn("loi_giai_anh", (await self.discover(allowed))[1])
        self.assertNotIn("loi_giai_anh", (await self.discover(old))[1])
        self.assertEqual(chatbot_store.update_bot(allowed, {"plugin_tools_read_docs": "[]"}), (True, ""))
        self.assertNotIn("loi_giai_anh", (await self.discover(allowed))[1])
        self.assertEqual(chatbot_store.update_bot(old, {"plugin_tools_read_docs": '["loi_giai_anh"]'}), (True, ""))
        self.assertIn("loi_giai_anh", (await self.discover(old))[1])

    async def test_validation_rejects_entire_bad_update(self):
        bot_id = self.make_bot(["loi_giai_anh", "loi_giai_anh"])
        self.assertEqual(chatbot_store.get_bot(bot_id)["plugin_tools_read_docs"], ["loi_giai_anh"])
        for invalid in ("*", '{"loi_giai_anh":true}', '["*"]', [2], ["../tool"], ["tool"] * 129):
            ok, error = chatbot_store.update_bot(bot_id, {"name": "must not save", "plugin_tools_read_docs": invalid})
            self.assertFalse(ok, invalid)
            self.assertTrue(error)
            self.assertEqual(chatbot_store.get_bot(bot_id)["name"], "Document bot")
            self.assertEqual(chatbot_store.get_bot(bot_id)["plugin_tools_read_docs"], ["loi_giai_anh"])

    async def test_http_list_call_and_missing_vault(self):
        bot_id = self.make_bot(["loi_giai_anh"])

        async def rpc(method, params=None, vault=None):
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}
            headers = [(b"authorization", b"Bearer test-only"), (b"x-javis-mode", b"read_docs"),
                       (b"x-javis-bot", b"1"), (b"x-javis-bot-id", bot_id.encode())]
            if vault:
                headers.append((b"x-javis-vault", vault.encode()))
            request = Request({"type": "http", "method": "POST", "path": "/hub/mcp", "headers": headers}, receive)
            with patch.object(mcp_hub, "hub_token", return_value="test-only"):
                response = await mcp_hub.handle_http(request)
            return json.loads(response.body)["result"]

        listed = await rpc("tools/list", vault=str(self.brain))
        self.assertEqual({t["name"] for t in listed["tools"]}, self.docs | {"loi_giai_anh"})
        called = await rpc("tools/call", {"name": "loi_giai_anh"}, str(self.brain))
        self.assertFalse(called["isError"])
        self.assertEqual(called["content"][0]["text"], "image-ready")
        denied = await rpc("tools/call", {"name": "not_allowed"}, str(self.brain))
        self.assertTrue(denied["isError"])
        self.assertEqual((await rpc("tools/list"))["tools"], [])

    async def test_claude_configs_are_separate_for_bots_sharing_a_brain(self):
        first = self.make_bot(["loi_giai_anh"])
        second = self.make_bot()
        paths = [mcp_hub.claude_config_path("read_docs", str(self.brain), bot=True, bot_id=b)
                 for b in (first, second)]
        self.assertNotEqual(*paths)
        for path, bot_id in zip(paths, (first, second)):
            headers = json.loads(Path(path).read_text(encoding="utf-8"))["mcpServers"]["javis"]["headers"]
            self.assertEqual(headers["X-Javis-Bot-Id"], bot_id)

    async def test_existing_update_endpoint_saves_and_rejects_bad_form_data(self):
        import main
        bot_id = self.make_bot()

        class FormRequest:
            def __init__(self, value):
                self.value = value

            async def form(self):
                return {"plugin_tools_read_docs": self.value}

        result = await main.chatbots_update(bot_id, FormRequest('["loi_giai_anh"]'))
        self.assertEqual(result, {"ok": True})
        self.assertEqual(chatbot_store.get_bot(bot_id)["plugin_tools_read_docs"], ["loi_giai_anh"])
        result = await main.chatbots_update(bot_id, FormRequest('*'))
        self.assertEqual(result.status_code, 400)
        self.assertEqual(chatbot_store.get_bot(bot_id)["plugin_tools_read_docs"], ["loi_giai_anh"])


if __name__ == "__main__":
    unittest.main()
