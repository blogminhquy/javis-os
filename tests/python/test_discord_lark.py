"""Discord and Lark/Feishu admin channels (0.85.0).

    python tests/run.py discord_lark

No network: both platforms are played by a local WebSocket server. What is guarded, in order of what
would hurt most if it broke:

  1. Lark's wire format. Frames are protobuf (`pbbp2.Frame`) encoded by hand here; the bytes must match
     what the official SDK produces, every data frame must be acknowledged with `{"code": 200}` or
     Lark redelivers it, and a large event split across frames must be joined before it is read.
  2. Both channels are FAIL-CLOSED like Slack: an empty allow-list lets nobody in, strangers get a
     pairing code. The allow-list holds PEOPLE (Discord user id, Lark open_id), not chats.
  3. Discord's gateway: identify with NO privileged intent, heartbeat, take READY, answer DMs and
     mentions, ignore bots and server chatter, and STOP retrying on a bad token (close 4004) instead
     of hammering Discord forever.
  4. Settings: new secrets are encrypted at rest, masked on read, kept when the form sends nothing;
     saving through /settings restarts the right channel. Lark defaults to the international cloud.
  5. Results of background work come back on the channel that asked (discord:/lark: prefixes).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-dclark-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import websockets  # noqa: E402

import channel_context  # noqa: E402
import discord_bot  # noqa: E402
import lark_bot  # noqa: E402
import owner_channels  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail!r}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


# ============================================================
# 1. Lark frame codec
# ============================================================
frame = {"seq_id": 7, "log_id": 2 ** 40 + 3, "service": 1234, "method": 1,
         "headers": {"type": "event", "message_id": "m-1", "sum": "1", "seq": "0", "trace_id": "t"},
         "payload": json.dumps({"x": "Xin chào"}).encode(), "log_id_new": "new-1"}
back = lark_bot.decode_frame(lark_bot.encode_frame(frame))
check("frame round-trips every field", all(back[k] == frame[k] for k in frame), back)

# The exact bytes the official SDK (lark-oapi 1.7.3, protobuf) writes for its ping frame:
# SeqID 0, LogID 0, service 42, method 0, one header type=ping. Field order and wire types must match.
SDK_PING = bytes.fromhex("0800" "1000" "182a" "2000" "2a0c0a0474797065120470696e67")
ours = lark_bot.LarkBot({"app_id": "a", "app_secret": "b"}, "", None)
ours._service_id = 42
check("ping frame is byte-identical to the official SDK", ours._ping_frame() == SDK_PING,
      ours._ping_frame().hex())
check("unknown fields are skipped, not fatal",
      lark_bot.decode_frame(lark_bot.encode_frame({"method": 1}) + bytes.fromhex("5005"))["method"] == 1)
try:
    lark_bot.decode_frame(b"\x0a\xff")
    check("a truncated frame raises instead of returning garbage", False)
except ValueError:
    check("a truncated frame raises instead of returning garbage", True)

ack = lark_bot.decode_frame(ours.ack_frame(frame, 0.0))
check("ack keeps the frame's headers, adds biz_rt, payload {code:200}",
      ack["headers"]["message_id"] == "m-1" and "biz_rt" in ack["headers"]
      and json.loads(ack["payload"]) == {"code": 200} and ack["seq_id"] == 7, ack)

p1 = dict(frame, headers=dict(frame["headers"], sum="2", seq="1", message_id="big"), payload=b'"b":2}')
p0 = dict(frame, headers=dict(frame["headers"], sum="2", seq="0", message_id="big"), payload=b'{"a":1,')
check("first half of a split event waits", ours.assemble(p1) is None)
check("second half joins in seq order, whatever order they came in",
      json.loads(ours.assemble(p0)) == {"a": 1, "b": 2})

check("Lark ids pick their receive_id_type by prefix",
      [lark_bot.receive_id_type(x) for x in ("oc_1", "ou_2", "on_3")] == ["chat_id", "open_id", "union_id"])
check("Lark is the default cloud, Feishu only when picked",
      owner_channels.lark_domain("") == "lark" and owner_channels.lark_domain("FEISHU") == "feishu"
      and lark_bot.LarkBot({"app_id": "a", "app_secret": "b"}, "", None).base == "https://open.larksuite.com")


# ============================================================
# 2. Lark: a whole session against a fake Lark
# ============================================================
def _event(mid, text, chat_type="p2p", chat="oc_dm", sender="ou_owner", mentions=None):
    return {"schema": "2.0",
            "header": {"event_id": "ev-" + mid, "event_type": "im.message.receive_v1"},
            "event": {"sender": {"sender_id": {"open_id": sender}, "sender_type": "user"},
                      "message": {"message_id": mid, "chat_id": chat, "chat_type": chat_type,
                                  "message_type": "text", "content": json.dumps({"text": text}),
                                  "mentions": mentions or []}}}


async def _lark_session():
    acks, pings, dispatched = [], [], []
    done = asyncio.Event()

    async def handler(ws):
        def data(payload, mid, **h):
            return lark_bot.encode_frame({"seq_id": 1, "service": 99, "method": 1,
                                          "headers": dict({"type": "event", "message_id": mid, "sum": "1",
                                                           "seq": "0", "trace_id": "t"}, **h),
                                          "payload": json.dumps(payload).encode()})
        await ws.send(data(_event("om_1", "doanh thu hôm nay?"), "f1"))
        await ws.send(data(_event("om_1", "doanh thu hôm nay?"), "f1-redelivered"))
        await ws.send(data(_event("om_2", "@_user_1 báo cáo tuần", chat_type="group", chat="oc_grp",
                                  mentions=[{"key": "@_user_1", "id": {"open_id": "ou_bot"}}]), "f2"))
        await ws.send(data(_event("om_3", "hai người nói chuyện", chat_type="group", chat="oc_grp"), "f3"))
        await ws.send(data(_event("om_4", "!stop"), "f4"))
        try:
            async for raw in ws:
                f = lark_bot.decode_frame(raw)
                (pings if f["method"] == 0 else acks).append(f)
                if len(acks) >= 5:
                    done.set()
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        bot = lark_bot.LarkBot({"app_id": "cli_x", "app_secret": "s", "domain": "lark"}, "", None)
        bot.bot_id = "ou_bot"

        async def fake_dispatch(client, chat, text, meta=None):
            dispatched.append((chat, text, meta["chat_type"], meta["user_id"], meta["mentioned"]))

        async def fake_endpoint(client):
            bot._service_id = 99
            return f"ws://127.0.0.1:{port}/?device_id=d&service_id=99"

        async def fake_whoami(client):
            return True
        bot._dispatch, bot._endpoint, bot._whoami = fake_dispatch, fake_endpoint, fake_whoami
        bot.start()
        try:
            await asyncio.wait_for(done.wait(), 5)
        except asyncio.TimeoutError:
            pass
        await asyncio.sleep(0.2)
        status = bot.status
        bot.stop()
    return acks, pings, dispatched, status


acks, pings, dispatched, status = run(_lark_session())
check("Lark: connected status after the socket opens", status == "polling", status)
check("Lark: every data frame is acknowledged with code 200",
      len(acks) == 5 and all(json.loads(a["payload"]) == {"code": 200} for a in acks), len(acks))
check("Lark: a ping goes out on connect, as a control frame with the service id",
      pings and pings[0]["headers"].get("type") == "ping" and pings[0]["service"] == 99, pings[:1])
check("Lark: DM answered, sender open_id is the user id",
      ("oc_dm", "doanh thu hôm nay?", "private", "ou_owner", False) in dispatched, dispatched)
check("Lark: a redelivered event is answered once",
      sum(1 for d in dispatched if d[1] == "doanh thu hôm nay?") == 1, dispatched)
check("Lark: a group mention is answered with the @_user_1 key stripped",
      ("oc_grp", "báo cáo tuần", "group", "ou_owner", True) in dispatched, dispatched)
check("Lark: group chatter without a mention is ignored",
      not any(d[1] == "hai người nói chuyện" for d in dispatched), dispatched)
check("Lark: !stop becomes /stop", any(d[1] == "/stop" for d in dispatched), dispatched)

ev_post = {"message_type": "post", "content": json.dumps(
    {"title": "Tiêu đề", "content": [[{"tag": "text", "text": "dòng một"}], [{"tag": "a", "href": "https://x"}]]}),
    "mentions": []}
check("Lark: rich-text (post) messages read as text",
      run(ours.message_text(None, ev_post, {})) == "Tiêu đề\ndòng một\nhttps://x")
check("Lark: a handshake refusal header becomes the owner's error",
      "too many" in lark_bot.handshake_error(type("E", (Exception,), {"headers": {
          "handshake-status": "514", "handshake-msg": "too many connections"}})()))


# ============================================================
# 3. Discord: a whole session against a fake gateway
# ============================================================
async def _discord_session(close_code=None):
    sent, dispatched = [], []
    got_identify = asyncio.Event()

    async def handler(ws):
        await ws.send(json.dumps({"op": 10, "d": {"heartbeat_interval": 150}}))
        try:
            async for raw in ws:
                m = json.loads(raw)
                sent.append(m)
                if m.get("op") == 1:
                    await ws.send(json.dumps({"op": 11}))
                if m.get("op") == 2:
                    got_identify.set()
                    if close_code:
                        await ws.close(code=close_code)
                        return
                    await ws.send(json.dumps({"op": 0, "s": 1, "t": "READY", "d": {
                        "session_id": "sess", "resume_gateway_url": "", "user": {"id": "999", "username": "javis"}}}))
                    msgs = [
                        {"id": "1", "channel_id": "dm1", "author": {"id": "42", "username": "quy"}, "content": "hello", "type": 0},
                        {"id": "1", "channel_id": "dm1", "author": {"id": "42", "username": "quy"}, "content": "hello", "type": 0},
                        {"id": "2", "channel_id": "c1", "guild_id": "g", "author": {"id": "42"}, "content": "people talking", "type": 0},
                        {"id": "3", "channel_id": "c1", "guild_id": "g", "author": {"id": "42"},
                         "content": "<@999> sales?", "mentions": [{"id": "999"}], "type": 0},
                        {"id": "4", "channel_id": "dm1", "author": {"id": "7", "bot": True}, "content": "beep", "type": 0},
                        {"id": "5", "channel_id": "dm1", "author": {"id": "42"}, "content": "!new", "type": 0},
                        {"id": "6", "channel_id": "dm1", "author": {"id": "42"}, "content": "pinned", "type": 6},
                    ]
                    for i, mm in enumerate(msgs):
                        await ws.send(json.dumps({"op": 0, "s": 2 + i, "t": "MESSAGE_CREATE", "d": mm}))
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        bot = discord_bot.DiscordBot("Bot tok.en", "", None)

        async def fake_dispatch(client, chat, text, meta=None):
            dispatched.append((chat, text, meta["chat_type"], meta["user_id"]))

        async def fake_whoami(client):
            bot.bot_id = "999"
            return True

        async def fake_url(client):
            return f"ws://127.0.0.1:{port}"
        bot._dispatch, bot._whoami, bot._gateway_url = fake_dispatch, fake_whoami, fake_url
        bot.start()
        try:
            await asyncio.wait_for(got_identify.wait(), 5)
        except asyncio.TimeoutError:
            pass
        await asyncio.sleep(0.6)
        state = (bot.status, bot.last_error, bot._task.done() if bot._task else True)
        bot.stop()
    return sent, dispatched, state


sent, dispatched, state = run(_discord_session())
ident = [m for m in sent if m.get("op") == 2]
check("Discord: token given as 'Bot xxx' is cleaned", discord_bot.DiscordBot("Bot abc", "", None).token == "abc")
check("Discord: identifies once, without any privileged intent",
      len(ident) == 1 and ident[0]["d"]["intents"] == discord_bot.INTENTS
      and not ident[0]["d"]["intents"] & ((1 << 1) | (1 << 8) | (1 << 15)), ident)
check("Discord: heartbeats are sent", any(m.get("op") == 1 for m in sent), [m.get("op") for m in sent])
check("Discord: READY marks the channel running", state[0] == "polling", state)
check("Discord: DM answered once", dispatched.count(("dm1", "hello", "private", "42")) == 1, dispatched)
check("Discord: server chatter without a mention is ignored",
      not any(d[1] == "people talking" for d in dispatched), dispatched)
check("Discord: a mention is answered with the mention stripped", ("c1", "sales?", "group", "42") in dispatched, dispatched)
check("Discord: other bots and system messages are ignored",
      not any(d[1] in ("beep", "pinned") for d in dispatched), dispatched)
check("Discord: !new becomes /new", any(d[1] == "/new" for d in dispatched), dispatched)

_, _, state = run(_discord_session(close_code=4004))
check("Discord: close 4004 (bad token) stops retrying and says why",
      state[0] == "error" and state[2] and "token" in state[1].lower(), state)

chunks = discord_bot._chunks("```\n" + "x = 1\n" * 500 + "```")
check("Discord: long answers split under 2000 characters", all(len(c) <= 2000 for c in chunks) and len(chunks) > 1)
check("Discord: a code block cut in two stays a code block on both sides",
      all(c.count("```") % 2 == 0 for c in chunks), [c[:10] + "..." + c[-10:] for c in chunks])


# ============================================================
# 4. Fail-closed pairing, prefixes, context block
# ============================================================
settings = {"discord": {"enabled": True, "bot_token": "t", "allow": ""},
            "lark": {"enabled": True, "app_id": "cli", "app_secret": "s", "allow": "ou_owner"}}
for ch in owner_channels.ALL:
    ch.wire(read_settings=lambda: json.loads(json.dumps(settings)),
            write_settings=lambda patch: [settings.setdefault(k, {}).update(v) for k, v in patch.items()])
D, L = owner_channels.DISCORD, owner_channels.LARK
r = D.precheck("hi", {"user_id": "42", "chat_id": "dm1", "user_name": "Quy"})
check("Discord control: empty allow-list blocks everyone, gives a pairing code",
      r is not None and D.queue.get("42", {}).get("ma", "x") in r["reply"], r)
check("the refusal names the renamed page", "Kênh Admin" in r["reply"] or "Admin channels" in r["reply"], r)
D.allow("42", True)
check("Discord: after Allow the user passes in any channel", D.precheck("hi", {"user_id": "42", "chat_id": "c9"}) is None)
check("Lark: allowed by open_id, not by chat id",
      L.precheck("hi", {"user_id": "ou_owner", "chat_id": "oc_x"}) is None
      and L.precheck("hi", {"user_id": "ou_other", "chat_id": "oc_x"}) is not None)
check("by_prefix finds discord: and lark:",
      owner_channels.by_prefix("discord:dm1") == (D, "dm1") and owner_channels.by_prefix("lark:oc_1") == (L, "oc_1"))
check("Discord and Lark trust the chat id a turn produced (a DM channel is not a user id)",
      D.trust_turn_ids and L.trust_turn_ids and not owner_channels.WHATSAPP.trust_turn_ids)
for src, must in (("discord", "2000 ký tự"), ("lark", "KHÔNG có bảng")):
    blk = channel_context.build_channel_block(src, {"chat_id": f"{src}:X", "chat_type": "group", "user_name": "An"})
    check(f"context block for {src}: keeps the {src}: prefix and its own rule",
          f"`{src}:`" in blk and must in blk, blk[-600:])


# ============================================================
# 5. Settings through the real endpoint, background results routing
# ============================================================
import config as cfgmod  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

for ch in owner_channels.ALL:
    ch.wire(read_settings=cfgmod.read_settings, write_settings=cfgmod.write_settings)
client = TestClient(main.app, base_url="http://localhost")
check("new secrets are encrypted at rest", {"discord.bot_token", "lark.app_secret"} <= set(cfgmod._SECRET_PATHS))
check("Lark settings default to the international cloud", cfgmod.read_settings().get("lark", {}).get("domain") == "lark")
client.post("/settings", data={"section": "lark", "data": json.dumps(
    {"enabled": False, "app_id": "  cli_abc  ", "app_secret": "sec-1", "domain": "Feishu", "allow": "ou_1;ou_2"})})
client.post("/settings", data={"section": "lark", "data": json.dumps({"app_secret": "", "allow": "ou_1, ou_2"})})
c = cfgmod.read_settings().get("lark", {})
check("Lark: app id trimmed, domain normalised, empty secret keeps the saved one",
      c.get("app_id") == "cli_abc" and c.get("domain") == "feishu" and c.get("app_secret") == "sec-1", c)
client.post("/settings", data={"section": "discord", "data": json.dumps(
    {"enabled": False, "bot_token": "disc-123456", "allow": "42"})})
g = client.get("/settings").json()
check("GET /settings masks Discord and Lark secrets",
      g["discord"]["bot_token"].startswith("••••") and g["discord"]["bot_token_set"]
      and g["lark"]["app_secret"].startswith("••••"), (g.get("discord"), g.get("lark")))
check("a disabled channel does not connect", owner_channels.DISCORD.bot is None and owner_channels.LARK.bot is None)
st = client.get("/discord/status").json()
check("/discord/status answers in the shared shape", st.get("configured") is True and st.get("allow_ids") == ["42"], st)
check("/lark/test explains what is missing instead of failing silently",
      client.post("/lark/test").json().get("ok") is False)

sent = []


async def fake_send_to(raw, text):
    sent.append((raw, text))
    return True, ""

orig = (D.send_to, L.send_to)
D.send_to, L.send_to = fake_send_to, fake_send_to
ok1 = run(main._gui_qua_kenh("discord:dm1", "done"))
ok2 = run(main._tg_send_to("lark:oc_1", "reminder"))
D.send_to, L.send_to = orig
check("loop/Kanban result for discord:... goes to Discord", ok1 == (True, "") and ("dm1", "done") in sent, sent)
check("reminder for lark:... goes to Lark", ok2 == (True, "") and ("oc_1", "reminder") in sent, sent)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
