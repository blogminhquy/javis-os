"""Regression: a Zalo chatbot uses the NEXT ChatGPT OAuth account on quota.

NO network, NO actual Zalo messages, NO real credentials.
python tests/python/test_bot_oauth_rotation.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import base64
import json
import os
import stat
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bot-oauth-state-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-bot-oauth-brain-")

import bot_oauth_rotation as R  # noqa: E402
import engine  # noqa: E402
import openai_oauth  # noqa: E402
import plan_accounts  # noqa: E402
import model_routing  # noqa: E402
import config  # noqa: E402
import turn_context  # noqa: E402

errors = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        errors.append(name)


settings = {"model": {"accounts": {"openai-oauth": [
    {"id": "assistant", "label": "assistant", "enabled": True},
    {"id": plan_accounts.MAIN, "label": "old", "enabled": True},
]}}}
orig_settings = config.read_settings
orig_has_extra = plan_accounts.has_extra
orig_usable = plan_accounts.usable
orig_creds = openai_oauth.valid_creds_for
orig_rest = model_routing.mark_rest
calls, rests = [], []


def creds(aid):
    return {"access_token": "token-" + aid, "account_id": "chat-" + aid}


config.read_settings = lambda: settings
plan_accounts.has_extra = lambda m, prov: prov == "openai-oauth"
plan_accounts.usable = lambda m, prov: [
    {"id": a["id"], "enabled": True} for a in m["accounts"][prov]]
openai_oauth.valid_creds_for = creds
model_routing.mark_rest = lambda prov, aid, seconds=0, **kw: rests.append((prov, aid, seconds))

BOT = turn_context.make("zalo_personal", "user", "group", "group-mdn", la_chu=False)
BOT["bot_id"] = "bot_lyly"


async def collect(factory, context=None):
    token = turn_context.bind(context) if context else None
    try:
        return [ev async for ev in R.stream(factory, "token-main-original", "chat-main-original")]
    finally:
        if token:
            turn_context.reset(token)


async def _collect_mcp(token, aid, msg, tools, routing):
    return [ev async for ev in engine.responses_with_mcp(token, aid, "gpt-test", msg, "off", tools, routing)]


async def account_stream(token, aid):
    calls.append(aid)
    yield {"type": "meta", "model": "gpt-test"}
    if aid == "chat-assistant":
        yield {"type": "limit_exceeded", "raw": '{"error":{"code":"usage_limit_reached"}}'}
        yield {"type": "error", "ma": 429, "tam_thoi": True,
               "content": "ChatGPT 429: usage limit reached (usage_limit_reached)"}
    else:
        yield {"type": "text", "content": "Đã trả lời qua tài khoản còn lượt"}


try:
    result = asyncio.run(collect(account_stream, BOT))
    check("Models order assistant first, second account takes over", calls == ["chat-assistant", "chat-main"])
    check("the failed account's meta/error never reaches the customer",
          [ev["type"] for ev in result] == ["meta", "text"])
    check("one failed account is rested without resting both accounts",
          len(rests) == 1 and rests[0][1] == "assistant")
    check("successful account's answer preserved",
          any("còn lượt" in ev.get("content", "") for ev in result))

    calls.clear()
    rests.clear()
    plain = asyncio.run(collect(account_stream))
    check("non-bot caller never touches saved account order",
          calls == ["chat-main-original"] and plain[0]["type"] == "meta" and not rests)

    async def tool_then_error(token, aid):
        calls.append(aid)
        yield {"type": "meta", "model": "gpt-test"}
        yield {"type": "tool_call", "name": "write_order", "input": {}}
        yield {"type": "error", "ma": 429, "tam_thoi": True, "content": "usage_limit_reached"}

    calls.clear()
    rests.clear()
    got = asyncio.run(collect(tool_then_error, BOT))
    check("tool call before quota prevents any account switch",
          len(calls) == 1 and calls == ["chat-assistant"] and not rests
          and any(ev.get("type") == "tool_call" for ev in got))

    async def text_then_error(token, aid):
        calls.append(aid)
        yield {"type": "text", "content": "partial"}
        yield {"type": "error", "ma": 429, "tam_thoi": True, "content": "usage_limit_reached"}

    calls.clear()
    rests.clear()
    got = asyncio.run(collect(text_then_error, BOT))
    check("partial answer never reruns on another account",
          calls == ["chat-assistant"] and not rests and got[0]["content"] == "partial")

    async def always_quota(token, aid):
        calls.append(aid)
        yield {"type": "error", "ma": 429, "tam_thoi": True, "content": "ChatGPT usage_limit_reached"}

    calls.clear()
    rests.clear()
    got = asyncio.run(collect(always_quota, BOT))
    check("two exhausted accounts tried only once each",
          calls == ["chat-assistant", "chat-main"] and len(rests) == 2)
    check("final quota error not marked transient (prevents outer triple retry)",
          len(got) == 1 and got[0]["type"] == "error" and not got[0].get("tam_thoi")
          and "2 tài khoản" in got[0]["content"])

    async def auth_then_success(token, aid):
        calls.append(aid)
        if aid == "chat-assistant":
            yield {"type": "error", "ma": 401, "content": "ChatGPT 401: Unauthorized"}
        else:
            yield {"type": "text", "content": "ok"}

    calls.clear()
    rests.clear()
    got = asyncio.run(collect(auth_then_success, BOT))
    check("a bad login does not block the next signed-in account",
          calls == ["chat-assistant", "chat-main"] and got[-1]["content"] == "ok")

    # Actual engine wrappers preserve the exact message and MCP tool scope.
    orig_engine = engine._responses_with_mcp_account
    captured = []

    async def fake_mcp(token, aid, model, messages, reasoning, tools, route):
        captured.append((aid, model, messages, reasoning, tools, route))
        if aid == "chat-assistant":
            yield {"type": "error", "ma": 429, "tam_thoi": True,
                   "content": "ChatGPT usage_limit_reached"}
        else:
            yield {"type": "text", "content": "MCP answer"}

    engine._responses_with_mcp_account = fake_mcp
    try:
        t = turn_context.bind(BOT)
        try:
            tools = [{"fn": "javis_read_file", "schema": {}}]
            routing = {"javis_read_file": "fake-sandbox-route"}
            msg = [{"role": "user", "content": "Hello"}]
            got = asyncio.run(_collect_mcp("token-old", "chat-old", msg, tools, routing))
        finally:
            turn_context.reset(t)
        check("MCP wrapper rotates without modifying permissions or history",
              len(captured) == 2 and got[-1].get("content") == "MCP answer"
              and all(x[2] is msg and x[4] is tools and x[5] is routing for x in captured))
    finally:
        engine._responses_with_mcp_account = orig_engine

    # Extra auth.json is not the global default credentials slot.
    with tempfile.TemporaryDirectory(prefix="javis-bot-auth-") as dirname:
        folder = Path(dirname)
        auth = folder / "auth.json"
        orig_home = plan_accounts.home
        orig_extra_creds = openai_oauth.valid_creds_for
        plan_accounts.home = lambda provider, aid, create=False: folder if aid == "assistant" else None
        openai_oauth.valid_creds_for = orig_creds
        try:
            def jwt(exp):
                payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
                return "h." + payload + ".s"

            auth.write_text(json.dumps({"tokens": {
                "access_token": jwt(time.time()+3600),
                "refresh_token": "refresh-extra",
                "account_id": "extra-account"}, "last_refresh": ""}), encoding="utf-8")
            good = openai_oauth.valid_creds_for("assistant")
            check("reads the extra account's auth.json without changing global login",
                  good and good["account_id"] == "extra-account" and "access_token" in good)

            auth.write_text(json.dumps({"tokens": {
                "access_token": jwt(time.time()-60),
                "refresh_token": "refresh-extra",
                "account_id": "extra-account"}, "last_refresh": ""}), encoding="utf-8")
            orig_post = openai_oauth.httpx.post
            refreshes = []

            class Response:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"access_token": jwt(time.time()+3600),
                            "refresh_token": "refresh-next"}

            openai_oauth.httpx.post = lambda *a, **kw: (refreshes.append(kw.get("data")), Response())[1]
            try:
                good = openai_oauth.valid_creds_for("assistant")
            finally:
                openai_oauth.httpx.post = orig_post
            saved = json.loads(auth.read_text(encoding="utf-8"))
            check("extra refresh rotates its own credential, never account 1",
                  good and good["account_id"] == "extra-account" and
                  saved["tokens"]["refresh_token"] == "refresh-next" and
                  len(refreshes) == 1)
            check("extra auth remains private after atomic write",
                  (stat.S_IMODE(auth.stat().st_mode) & 0o077) == 0)
        finally:
            plan_accounts.home = orig_home
            openai_oauth.valid_creds_for = orig_extra_creds
finally:
    config.read_settings = orig_settings
    plan_accounts.has_extra = orig_has_extra
    plan_accounts.usable = orig_usable
    openai_oauth.valid_creds_for = orig_creds
    model_routing.mark_rest = orig_rest


if errors:
    raise SystemExit(f"FAILED {len(errors)}: {errors}")
print("ALL PASS")
