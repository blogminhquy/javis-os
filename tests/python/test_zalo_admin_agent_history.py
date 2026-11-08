"""The owner's Zalo admin bot, its agents, and where its chats show on the Partners page (2026-11-08).

    python tests/python/test_zalo_admin_agent_history.py        (no network, scratch brains)

Owner report: "khi giao bot Zalo làm kênh admin ... nó không hiện lịch sử chat lên trên Javis, nhất là nối với một
agent. Khi mà nối agent với cả bot Zalo đấy thì nó không hiện kênh admin lên trên chat." Pinned here through the real
Zalo admin functions and the real shell (`_tg_answer`), with only the model engine faked:
  1. `@<agent> ...` and /agent on the Zalo admin bot reach that agent, like Telegram.
  2. Zalo commands act on the session its turns use (`zalo:<id>`): /reset, /stop, /agent.
  3. Where the chats are stored and listed: Javis Core's history holds the plain admin chats, an agent's history
     holds the admin chats routed to it (`<channel>@<slug>`), an older agent chat is relabelled on its next turn.
  4. A dedicated bot can neither verify nor poll the admin bot's token.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-admin-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-admin-brains-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"       # TestClient host (see test_workflow_runs_api.py)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
import chatbot_runtime  # noqa: E402
import javis_core  # noqa: E402
from routes import channels as channels_routes  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


def write_agent(brain, slug, name, body):
    d = Path(brain) / "agents"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(f"---\ntype: agent\nname: {name}\nrole: helper\n---\n{body}\n", encoding="utf-8")


BRAIN = str(main._default_brain_dir())
write_agent(BRAIN, "writer", "Writer", "WRITER ROLE BODY")
OWNER, STRANGER = "abc123", "fff999"
_s = main.cfgmod.read_settings()
_s["zalo_bot"] = {"enabled": False, "token": "111:zalo-admin", "chat_id": OWNER}
main.cfgmod.write_settings(_s)


class FakeClaude:
    runs = []

    def __init__(self, **kw):
        self.system_prompt = kw.get("system_prompt") or ""
        self.model = None
        self.session_id = None

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        FakeClaude.runs.append({"system_prompt": self.system_prompt, "prompt": prompt})
        yield {"type": "text", "content": "Done."}
        yield {"type": "final", "content": "Done.", "session_id": "fake-1", "tokens_in": 1, "tokens_out": 1,
               "cost_usd": 0}


class Recorder:
    def prepare(self, *a, **k):
        return SimpleNamespace(action="skip", system_prompt="")


async def _none(*a, **k):
    return None


main._FAST_PATH = Recorder()
main._get_adaptive_context = lambda: Recorder()
main.claude_engine = lambda **kw: FakeClaude(**kw)
main._apply_mcp = lambda *a, **k: None
main._chat_provider = lambda mcfg: ("anthropic-cli", "cli", "", "opus")
main.build_system_prompt = lambda *a, **k: "JAVIS MAIN PROMPT"
main.usage_store.record = lambda *a, **k: None
main.channel_context.collect_turn_files = lambda *a, **k: []
main._schedule_cancel_action = _none
main.learn_feature.enqueue = _none


def zalo(text, chat=OWNER):
    return asyncio.run(main._zalo_answer(text, {"chat_id": chat}))


def zcmd(cmd, arg="", chat=OWNER):
    return asyncio.run(main._zalo_command(cmd, arg, chat, {"chat_id": chat}))


store = main.get_store()


def channel_of(key):
    sid = main._TG_SID_MAP.get(key)
    return (store.get_session(sid) or {}).get("channel") if sid else None


# ================================================================
# 1. Agents on the Zalo admin bot
# ================================================================
check("an allowed Zalo chat counts as the owner's (prefixed key), a stranger does not, Telegram ids do not",
      main._tg_owner_chat("zalo:" + OWNER) and not main._tg_owner_chat("zalo:" + STRANGER)
      and not main._tg_owner_chat(OWNER))
out = zalo("@Writer draft a post")
check("@<agent> on Zalo: a turn of that agent, the reply names it",
      "WRITER ROLE BODY" in FakeClaude.runs[-1]["system_prompt"] and isinstance(out, dict)
      and out["text"].startswith("🤝 Writer"), out)
check("@<agent> on Zalo: the agent's own conversation, stored as zalo@writer",
      channel_of("zalo:" + OWNER + "@writer") == "zalo@writer", channel_of("zalo:" + OWNER + "@writer"))
out = zalo("plain question")
check("no mention: Javis answers, stored as plain zalo", "JAVIS MAIN PROMPT" in FakeClaude.runs[-1]["system_prompt"]
      and channel_of("zalo:" + OWNER) == "zalo", channel_of("zalo:" + OWNER))
pre = main._zalo_precheck("@Nobody hi", {"chat_id": OWNER})
check("unknown mention from the owner: the agent list before a turn", isinstance(pre, dict)
      and "Writer" in pre.get("reply", ""), pre)
check("plain message from the owner: precheck lets it through", main._zalo_precheck("hello", {"chat_id": OWNER}) is None)
pre = main._zalo_precheck("@Nobody hi", {"chat_id": STRANGER})
check("a stranger gets the pairing code, never the agent list", isinstance(pre, dict)
      and "Writer" not in pre.get("reply", "") and pre.get("reply"), pre)
zalo("@Writer hi", chat=STRANGER)
check("a stranger's mention never reaches an agent", "JAVIS MAIN PROMPT" in FakeClaude.runs[-1]["system_prompt"])

# ================================================================
# 2. Commands act on the session Zalo turns use
# ================================================================
res = zcmd("agent", "writer")
check("/agent on Zalo: picked on the zalo:<id> key", main._TG_AGENT_MAP.get("zalo:" + OWNER, {}).get("slug") == "writer"
      and OWNER not in main._TG_AGENT_MAP, res)
zalo("next message without a mention")
check("/agent on Zalo: a plain message now goes to the agent", "WRITER ROLE BODY" in FakeClaude.runs[-1]["system_prompt"])
zcmd("agent", "off")
check("/agent off on Zalo", "zalo:" + OWNER not in main._TG_AGENT_MAP)
check("before /reset the Zalo chat has a stored conversation", bool(main._TG_SID_MAP.get("zalo:" + OWNER)))
zcmd("reset")
check("/reset on Zalo starts the REAL Zalo session over (and its agent one)",
      not main._TG_SID_MAP.get("zalo:" + OWNER) and not main._TG_SID_MAP.get("zalo:" + OWNER + "@writer"))
_cancelled = []
_orig_cancel = main.cancel_all
main.cancel_all = lambda tag: _cancelled.append(tag)
zcmd("stop")
main.cancel_all = _orig_cancel
check("/stop on Zalo cancels the tag the Zalo turn runs under", _cancelled == ["telegram:zalo:" + OWNER], _cancelled)
_src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
_rz = _src[_src.index("def restart_zalo_bot():"):]
_rz = _rz[:_rz.index("\n\n\n")]
check("the Zalo admin bot is wired to _zalo_answer and _zalo_command", "_zalo_answer, _zalo_command" in _rz)

# ================================================================
# 3. Partners page histories
# ================================================================
from fastapi.testclient import TestClient  # noqa: E402

cl = TestClient(main.app)
bkey = main._brain_key(BRAIN)
web_core = store.create_session(brain=bkey, engine="cli", title="core web", channel=javis_core.CHANNEL)
web_writer = store.create_session(brain=bkey, engine="cli", title="writer web", channel="agent:writer")
zalo("@Writer second post")
zalo("plain again")
z_agent = main._TG_SID_MAP.get("zalo:" + OWNER + "@writer")
z_plain = main._TG_SID_MAP.get("zalo:" + OWNER)
tg_plain = store.create_session(brain=bkey, engine="cli", title="tg", channel="telegram")


def listed(channel, **extra):
    r = cl.get("/sessions", params={"brain": "brain", "channel": channel, "limit": 50, **extra}).json()["sessions"]
    return {x["id"] for x in r}


core_hist = listed(javis_core.CHANNEL, bots=1)
check("Javis Core's history holds the plain admin chats (Zalo, Telegram) and its own web chat",
      {web_core, z_plain, tg_plain} <= core_hist and z_agent not in core_hist, core_hist)
w_hist = listed("agent:writer", bots=1)
check("the agent's history holds the Zalo chat routed to it, not Javis's",
      {web_writer, z_agent} <= w_hist and z_plain not in w_hist and tg_plain not in w_hist, w_hist)
check("opening the agent (limit=1, no bots) still picks its own web chat, never the Zalo one",
      [x["id"] for x in cl.get("/sessions", params={"brain": "brain", "channel": "agent:writer", "limit": 1})
       .json()["sessions"]] == [web_writer])
main_list = {x["id"] for x in cl.get("/sessions", params={"brain": "brain", "limit": 50}).json()["sessions"]}
check("the Chats page still lists the admin chats as before", {z_plain, tg_plain, z_agent} <= main_list, main_list)

# An agent chat stored before this fix (plain "telegram") moves to the agent's label on its next turn.
old = store.create_session(brain=bkey, engine="cli", title="old agent chat", channel="telegram")
sess = main._tg_session("777@writer")
sess["sid"] = old
sid = main._tg_conv_sid(store, sess, BRAIN, "cli", "opus", channel="telegram@writer")
check("an older agent chat is relabelled telegram@writer and kept", sid == old
      and store.get_session(old)["channel"] == "telegram@writer", store.get_session(old))
plain = store.create_session(brain=bkey, engine="cli", title="plain tg", channel="telegram")
sess2 = main._tg_session("778")
sess2["sid"] = plain
main._tg_conv_sid(store, sess2, BRAIN, "cli", "opus", channel="telegram")
check("a plain admin chat keeps its label", store.get_session(plain)["channel"] == "telegram")
check("the stored label: <channel>@<slug> with an agent, the plain channel without",
      main._owner_store_channel("zalo", {"slug": "writer"}) == "zalo@writer"
      and main._owner_store_channel("zalo", None) == "zalo"
      and main._owner_store_channel("cli", {"slug": "writer"}) == "cli@writer")
_ui = (Path(ROOT) / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
check("history rows label an admin chat by its app and hide the @<slug> part",
      'rawCh.split("@")[0]' in _ui and '(kenhLoc && rawCh === kenhLoc) ? ""' in _ui)

# ================================================================
# 4. A dedicated bot never shares the admin bot's token
# ================================================================
channels_routes._DEPS = channels_routes.ChannelsDeps(bot_status=lambda b: {}, main_bot_token=lambda: "",
                                                     main_zalo_token=lambda: "111:zalo-admin")
r = asyncio.run(channels_routes.verify_token("zalo", "111:zalo-admin"))
check("verify: the Zalo admin token is refused for a dedicated bot", isinstance(r, dict) and r.get("ok") is False
      and "/agent" in r.get("error", ""), r)
_s = main.cfgmod.read_settings()
_s["zalo_bot"]["enabled"] = True
main.cfgmod.write_settings(_s)
check("admin tokens: only switched-on admin bots count", main._admin_bot_tokens() == {"zalo": "111:zalo-admin"},
      main._admin_bot_tokens())
chatbot_runtime._deps["admin_tokens"] = main._admin_bot_tokens
check("runtime: the admin token is recognised per channel", chatbot_runtime._admin_token("zalo") == "111:zalo-admin"
      and chatbot_runtime._admin_token("telegram") == "")
_rt = (Path(SERVER) / "chatbot_runtime.py").read_text(encoding="utf-8")
check("runtime: start_bot skips an account on the admin token, before making its poller",
      _rt.index("if token == _admin_token(kenh):") < _rt.index("        tb = Lop(\n"))
check("restarting an admin bot makes dedicated bots let go of its token",
      'chatbot_runtime.release_admin_token("zalo")' in _rz and "admin_tokens=_admin_bot_tokens" in _src)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
