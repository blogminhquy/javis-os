"""ChatGPT Live out of quota: the call moves to the next ChatGPT account, then to the next call path.

    python tests/run.py voice_live_quota      (no network, no Codex)

Owner's report 06/11/2026: ChatGPT ran out ("You've hit your usage limit ... try again at 8:42 AM") during a call. The
call kept reopening ChatGPT Live and showed the same error twice, never moving to the plan's second account nor to
another path, even after the owner had switched the main model to Claude Max. Pins:
  - the ChatGPT error is read as "out of quota", with the reset time "try again at 8:42 AM";
  - during the handshake the error is reported ONCE (start_webrtc raises, no extra error event); mid-call it carries
    code "quota";
  - the route rests the account the call ran on (same store as chat) and answers with a "quota" frame;
  - with one account resting, a call runs on the next ChatGPT account, in that account's own CODEX_HOME;
  - with every account resting, the call path is no longer ChatGPT Live (api with a key, else basic), detail "quota";
  - one Codex app-server per account (the login lives in the CODEX_HOME it started with).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-live-quota-"))
os.environ.setdefault("JAVIS_STATE_DIR", str(_TMP / "state"))
_FAKE_HOME = _TMP / "home"
(_FAKE_HOME / ".codex").mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(_FAKE_HOME)
os.environ["USERPROFILE"] = str(_FAKE_HOME)
os.environ.pop("CODEX_HOME", None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import codex_realtime  # noqa: E402
import limit_learner  # noqa: E402
import model_routing  # noqa: E402
import plan_accounts  # noqa: E402
import voice_call  # noqa: E402
import voice_live  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


MSG = ("You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit "
       "https://chatgpt.com/settings/usage to purchase more credits or try again at 8:42 AM.")
PROV = "openai-oauth"

# ---- the error is "out of quota", with its reset time ----
now = time.time()
lim = limit_learner.parse_subscription_limit(MSG, "codex", now=now)
check("ChatGPT's usage-limit text is read as out of quota", lim is not None and lim.engine == "codex")
check("'try again at 8:42 AM' gives the reset time", bool(lim) and now < lim.reset_epoch <= now + 86400,
      getattr(lim, "reset_epoch", None))
check("'try again at' shows in the reset note", bool(lim) and "8:42" in (lim.reset_text or ""))
check("'try again in 45 minutes' still reads as a delay",
      abs(limit_learner.parse_subscription_limit("usage limit reached, try again in 45 minutes", "codex",
                                                 now=now).reset_epoch - (now + 2700)) < 1)
check("any other error is not a quota", voice_live.quota_error("thread does not support realtime conversation") is None)


# ---- ChatGPTLive: handshake error reported once, mid-call error carries code quota ----
class FakeServer:
    def __init__(self):
        self.queue = None

    async def request(self, method, params=None, timeout=30.0):
        return {"thread": {"id": "th-1"}} if method == "thread/start" else {}

    def subscribe(self, thread_id):
        self.queue = asyncio.Queue()
        return self.queue

    def unsubscribe(self, thread_id):
        pass


async def provider_checks():
    got = {}

    async def getter(home=None):
        got["home"] = home
        return FakeServer()

    p = voice_live.ChatGPTLive(app_server_getter=getter, account="acc2", codex_home="/x/acc2/codex")
    await p.connect()
    check("an extra account's call opens the app-server of its own CODEX_HOME", got.get("home") == "/x/acc2/codex")
    loop = asyncio.get_running_loop()
    p._sdp = loop.create_future()
    evs = p.translate({"method": "thread/realtime/error", "params": {"threadId": "th-1", "message": MSG}})
    check("handshake error: no second error event (one red box, not two)", evs == [], evs)
    check("handshake error: start_webrtc raises", p._sdp.done() and p._sdp.exception() is not None)
    check("handshake error: provider knows it is a quota", p.quota is not None)
    p2 = voice_live.ChatGPTLive(app_server_getter=getter)
    evs = p2.translate({"method": "thread/realtime/error", "params": {"threadId": "th-1", "message": MSG}})
    check("mid-call quota error carries code quota", len(evs) == 1 and evs[0].get("code") == "quota", evs)
    check("account 1 by default", p2.account == "main" and p2.codex_home == "")
    evs = p2.translate({"method": "thread/realtime/error", "params": {"threadId": "th-1", "message": "boom"}})
    check("other errors carry no code", len(evs) == 1 and "code" not in evs[0], evs)
    await p.close()
    await p2.close()


asyncio.run(provider_checks())

# ---- account rotation and the call path ----
codex_realtime.realtime_available = lambda cfg: (True, "")
cfg1 = {"model": {"openai_oauth": {"refresh_token": "r"}}, "voice": {}}
model_routing.clear_rest(PROV, plan_accounts.MAIN)
check("ChatGPT ready: the call path is ChatGPT Live", voice_call.select_call_engine(cfg1)["engine"] == "chatgpt")

model_routing.mark_rest(PROV, plan_accounts.MAIN, until=time.time() + 3600)
r = voice_call.select_call_engine(cfg1)
check("one account, out of quota: no longer ChatGPT Live, detail quota",
      r["engine"] == "basic" and r["detail"] == "quota", r)
cfg_key = {"model": {"openai_oauth": {"refresh_token": "r"}, "gemini_api_key": "g"}, "voice": {}}
r = voice_call.select_call_engine(cfg_key)
check("one account, out of quota, a Gemini key: Live with the API key", r["engine"] == "api" and r["live_provider"] == "gemini", r)

# A second ChatGPT account, signed in, in its own folder.
m2 = {"openai_oauth": {"refresh_token": "r"},
      "accounts": {PROV: [{"id": "main", "enabled": True}, {"id": "acc2", "label": "Work", "enabled": True}]}}
folder = plan_accounts.home(PROV, "acc2")
(folder / "auth.json").write_text(json.dumps({"tokens": {"refresh_token": "r2"}}), encoding="utf-8")
cfg2 = {"model": m2, "voice": {}}
r = voice_call.select_call_engine(cfg2)
check("account 1 out, account 2 ready: still ChatGPT Live", r["engine"] == "chatgpt", r)
acc = voice_live._chatgpt_account(cfg2)
check("the call runs on account 2, in its own CODEX_HOME",
      acc.get("account") == "acc2" and acc.get("codex_home") == str(folder), acc)
prov = voice_live._make_provider(dict(cfg2, voice={"live_provider": "chatgpt"}), "", "vi-VN", "")
check("make_provider hands account 2 to ChatGPT Live", prov.account == "acc2" and prov.codex_home == str(folder))
model_routing.mark_rest(PROV, "acc2", until=time.time() + 3600)
r = voice_call.select_call_engine(cfg2)
check("both accounts out: no longer ChatGPT Live", r["engine"] != "chatgpt" and r["detail"] == "quota", r)
model_routing.clear_rest(PROV, plan_accounts.MAIN)
check("account 1 back after its reset: account 1 runs again", voice_live._chatgpt_account(cfg2) == {})
model_routing.clear_rest(PROV, "acc2")


# ---- one app-server per account ----
class FakeProc:
    def __init__(self, env):
        self.env = env
        self.stdin = self
        self.stdout = self

    def write(self, s):
        for line in s.splitlines():
            msg = json.loads(line)
            if "id" in msg:
                self._reply = {"id": msg["id"], "result": {}}

    def flush(self):
        pass

    def readline(self):
        while not getattr(self, "_reply", None):
            time.sleep(0.01)
        r, self._reply = self._reply, None
        return json.dumps(r) + "\n"

    def poll(self):
        return None

    def kill(self):
        pass


spawned = []


def fake_popen(argv, **kw):
    p = FakeProc(kw.get("env") or {})
    spawned.append(p)
    return p


async def server_checks():
    codex_realtime._popen_factory = fake_popen
    codex_realtime._find_cli = lambda: "codex"
    codex_realtime._SERVER = None
    codex_realtime._EXTRA.clear()
    a = await codex_realtime.get_app_server()
    b = await codex_realtime.get_app_server(str(folder))
    check("account 2 gets its own app-server", a is not b and len(spawned) == 2)
    check("account 2's app-server runs with its CODEX_HOME", spawned[1].env.get("CODEX_HOME") == str(folder),
          spawned[1].env.get("CODEX_HOME"))
    check("account 1's app-server keeps ~/.codex", spawned[0].env.get("CODEX_HOME") != str(folder))
    check("a live app-server is reused per account", (await codex_realtime.get_app_server(str(folder))) is b)


asyncio.run(server_checks())

# ---- the route rests the account that ran out ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
seg = src[src.index("def _voice_quota_frame"):src.index("async def voice_live_ws")]
check("the route rests the account through the chat path's _note_pin_limit",
      '_note_pin_limit("codex"' in seg and "account=" in seg)
route = src[src.index("async def voice_live_ws"):]
route = route[:route.index("\n@app.")]
check("handshake and mid-call quota both answer with the quota frame", route.count("_voice_quota_frame(prov)") == 2)
check("no Live path now: the route tells the page to use the Basic path", '"code": "use_basic"' in route)
app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("the page changes path on a quota frame", 'code === "quota"' in app and "doiDuongGoi(" in app)
vl = (ROOT / "dashboard" / "voice-live.js").read_text(encoding="utf-8")
check("voice-live.js passes the error code on", 'emit("onError", d.message || "error", d.code || "")' in vl)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
