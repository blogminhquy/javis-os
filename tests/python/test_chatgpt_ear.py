"""The ChatGPT plan hears the voice, and the ear follows the main brain's vendor (2026-11-08).

    python tests/run.py chatgpt_ear      (no network: HTTP and the login are faked)

Owner, 2026-11-08: "if the subscription has a Whisper, use it", then "no setting, it sorts itself by the main model in
use: on ChatGPT use that plan's Whisper, the same for Claude, Antigravity and Grok". Of the four plans only ChatGPT gives
Javis an ear (the dictation endpoint of the ChatGPT and Codex Desktop apps, on the login Javis already holds). Locks:
  - the ChatGPT ear is available as soon as ChatGPT is connected on the Models page, no key;
  - auto puts the main brain's own vendor first (ChatGPT plan, Groq, OpenAI), then Groq, ChatGPT, OpenAI;
  - Claude, Antigravity and Grok brains get the best ear the machine has;
  - a failing ear hands the sentence to the next one, silence does not;
  - the request the ChatGPT ear sends: endpoint, bearer, account id, file, language;
  - voice messages (Telegram, Zalo) use the same order and the ChatGPT login;
  - an agent hears with its own model's vendor: a dedicated bot, a partner's chat, a chat pinned to a model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-gpt-ear-"))

import main  # noqa: E402
import stt  # noqa: E402
import voice_ear  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


GPT = {"openai_oauth": {"access_token": "tok", "refresh_token": "rt", "account_id": "acct_1"}}
GROQ = {"groq_api_key": "gsk_test"}
OAI = {"openai_api_key": "sk-test"}


def cfg(*parts, **voice):
    m = {}
    for p in parts:
        m.update(p)
    return {"model": m, "voice": dict(voice)}


# ============================================================
# 1. Choosing: the ear follows the main brain
# ============================================================
check("ChatGPT connected -> the ChatGPT ear is available with no key",
      voice_ear.availability(cfg(GPT))["chatgpt"] is True)
check("only a refresh token (access expired) still counts as connected",
      voice_ear.availability(cfg({"openai_oauth": {"refresh_token": "rt"}}))["chatgpt"] is True)
check("ChatGPT not connected -> no ChatGPT ear", voice_ear.availability(cfg(GROQ))["chatgpt"] is False)

r = voice_ear.select_ear(cfg(GPT, GROQ, OAI), "openai-oauth")
check("ChatGPT brain -> ChatGPT plan ear first, same vendor",
      r["provider"] == "chatgpt" and r["kind"] == "upload" and r["reason"] == voice_ear.REASON_SAME_VENDOR, r)
check("... with the other ears behind it, best first", r["fallbacks"] == ["groq", "openai"], r["fallbacks"])

r = voice_ear.select_ear(cfg(GPT, GROQ), "groq")
check("Groq brain -> Groq ear first, ChatGPT plan behind", r["provider"] == "groq" and r["fallbacks"] == ["chatgpt"], r)

for brain in ("anthropic-cli", "antigravity-cli", "grok-cli"):
    r = voice_ear.select_ear(cfg(GPT), brain)
    check(f"{brain} brain, ChatGPT connected only -> ChatGPT plan ear (no ear on that plan)",
          r["provider"] == "chatgpt" and r["reason"] == voice_ear.REASON_BEST, r)
    r = voice_ear.select_ear(cfg(GPT, GROQ, OAI), brain)
    check(f"{brain} brain with every ear -> Groq, then ChatGPT plan, then the paid OpenAI key",
          r["provider"] == "groq" and r["fallbacks"] == ["chatgpt", "openai"], r)

r = voice_ear.select_ear(cfg(GPT, OAI), "anthropic-cli")
check("the plan the owner already pays for goes before the OpenAI key", r["provider"] == "chatgpt", r)

r = voice_ear.select_ear(cfg(GROQ, ear="chatgpt"), "openai-oauth")
check("ChatGPT chosen by hand but not connected -> no ear, reason chosen_unavailable",
      r["provider"] == "" and r["reason"] == voice_ear.REASON_CHOSEN_UNAVAILABLE, r)
r = voice_ear.select_ear(cfg(GPT, GROQ, ear="chatgpt"), "anthropic-cli")
check("ChatGPT chosen by hand -> ChatGPT, the rest stay as fallbacks",
      r["provider"] == "chatgpt" and r["reason"] == voice_ear.REASON_CHOSEN and r["fallbacks"] == ["groq"], r)
r = voice_ear.select_ear(cfg(GPT, ear="off"), "openai-oauth")
check("off still wins over the plan", r["provider"] == "" and r["reason"] == voice_ear.REASON_OFF)
check("voice messages pass choice=auto, so off on the mic does not silence them",
      voice_ear.order(cfg(GPT, ear="off"), "openai-oauth", "auto") == ["chatgpt"])
check("'chatgpt' is a value the settings route accepts", "chatgpt" in voice_ear.CHOICES)

# ============================================================
# 2. The request the ChatGPT ear sends
# ============================================================
SENT = []
REPLY = {"status": 200, "json": {"text": "Mở Claude Code giúp anh nhé"}}


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, data=None, files=None, json=None):
        SENT.append({"url": url, "headers": headers or {}, "data": data or {}, "files": files or {}})
        return FakeResponse(REPLY["status"], REPLY["json"])


_real_client = stt.httpx.AsyncClient
stt.httpx.AsyncClient = FakeClient
try:
    webm = b"\x1aE\xdf\xa3" + b"\x00" * 64
    res = run(stt.chatgpt_nghe(webm, "voice.webm", "tok", "acct_1", ""))
    sent = SENT[-1]
    check("ChatGPT ear: hears and returns the text", res.get("ok") and res.get("text") == "Mở Claude Code giúp anh nhé",
          res)
    check("... on the plan's dictation endpoint", sent["url"] == stt.CHATGPT_STT_URL == (
        "https://chatgpt.com/backend-api/transcribe"))
    check("... with the plan's bearer token and account id",
          sent["headers"].get("Authorization") == "Bearer tok" and sent["headers"].get("ChatGPT-Account-Id") == "acct_1")
    f = sent["files"].get("file") or ()
    check("... the audio as the multipart file, named and typed as webm",
          f[0] == "voice.webm" and f[1] == webm and f[2] == "audio/webm", f[:1] + f[2:])
    check("... no language hint when the mic is on Multilingual (the model detects it)", "language" not in sent["data"])
    check("... no prompt field: the endpoint takes none", "prompt" not in sent["data"])

    run(stt.chatgpt_nghe(webm, "voice.webm", "tok", "", "vi"))
    check("language hint 'vi' is passed on", SENT[-1]["data"].get("language") == "vi")
    check("no account id -> header left out", "ChatGPT-Account-Id" not in SENT[-1]["headers"])

    ogg = b"OggS" + b"\x00" * 64
    run(stt.chatgpt_nghe(ogg, "voice.oga", "tok", "acct_1", None))
    f = SENT[-1]["files"]["file"]
    check("a Telegram .oga goes as ogg, default language 'vi' as for every ear",
          f[2] == "audio/ogg" and SENT[-1]["data"].get("language") == "vi", (f[0], f[2], SENT[-1]["data"]))

    n = len(SENT)
    res = run(stt.chatgpt_nghe(webm, "voice.webm", "", "", ""))
    check("no login -> thieu_key, nothing sent", res.get("ly_do") == "thieu_key" and len(SENT) == n)

    REPLY.update(status=401, json={"detail": "Unauthorized"})
    res = run(stt.chatgpt_nghe(webm, "voice.webm", "tok", "acct_1", ""))
    check("vendor refuses -> loi (the next ear takes over)", res.get("ly_do") == "loi" and not res.get("ok"), res)

    REPLY.update(status=200, json={"text": "Hãy subscribe cho kênh Ghiền Mì Gõ để không bỏ lỡ những video hấp dẫn"})
    res = run(stt.chatgpt_nghe(webm, "voice.webm", "tok", "acct_1", ""))
    check("a made-up YouTube outro is cut like for every ear -> khong_nghe_ro", res.get("ly_do") == "khong_nghe_ro",
          res)
finally:
    stt.httpx.AsyncClient = _real_client

# ============================================================
# 3. A failing ear hands the sentence on, silence does not
# ============================================================
CALLS = []
ANSWERS = {}


def fake(name):
    async def ear(*a, **kw):
        CALLS.append(name)
        return ANSWERS.get(name) or {"ok": True, "text": f"nghe bằng {name}", "model": name}
    return ear


_saved = (stt.groq_nghe, stt.openai_nghe, stt.chatgpt_nghe, stt.gemini_nghe, voice_ear.chatgpt_creds)
stt.groq_nghe, stt.openai_nghe, stt.chatgpt_nghe, stt.gemini_nghe = (fake("groq"), fake("openai"), fake("chatgpt"),
                                                                       fake("gemini"))


async def fake_creds():
    return {"access_token": "tok", "account_id": "acct_1"}

voice_ear.chatgpt_creds = fake_creds
try:
    keys = {"groq": "g", "openai": "o", "gemini": "m", "chatgpt": {"access_token": "tok"}}
    CALLS.clear()
    res = run(stt.listen_any(b"x", "a.ogg", keys, order=["chatgpt"]))
    check("voice message: the order given puts the ChatGPT plan first", CALLS == ["chatgpt"] and res["ear"] == "chatgpt")
    CALLS.clear()
    run(stt.listen_any(b"x", "a.ogg", {"groq": "g", "chatgpt": {"access_token": "tok"}}))
    check("no order given: Groq first, as before", CALLS == ["groq"])
    CALLS.clear()
    ANSWERS["chatgpt"] = {"ok": False, "ly_do": "loi", "noi_voi_javis": "x"}
    res = run(stt.listen_any(b"x", "a.ogg", keys, order=["chatgpt"]))
    check("ChatGPT ear down -> the next ear hears the voice message",
          CALLS == ["chatgpt", "groq"] and res["ear"] == "groq", CALLS)
    CALLS.clear()
    run(stt.listen_any(b"x", "a.ogg", {"groq": "g", "chatgpt": {}}, order=["chatgpt"]))
    check("ChatGPT not connected -> skipped, no call", CALLS == ["groq"], CALLS)

    CALLS.clear()
    res = run(voice_ear.transcribe_upload(cfg(GPT, GROQ), b"x", "v.webm", "auto", "", provider="chatgpt",
                                          fallbacks=["groq"]))
    check("dashboard mic: ChatGPT ear down -> Groq hears the sentence",
          CALLS == ["chatgpt", "groq"] and res["ok"] and res["text"] == "nghe bằng groq", (CALLS, res))
    CALLS.clear()
    ANSWERS["chatgpt"] = {"ok": False, "ly_do": "khong_nghe_ro", "noi_voi_javis": "x"}
    res = run(voice_ear.transcribe_upload(cfg(GPT, GROQ), b"x", "v.webm", "auto", "", provider="chatgpt",
                                          fallbacks=["groq"]))
    check("silence is silence: no second ear, the browser keeps its text",
          CALLS == ["chatgpt"] and not res["ok"], (CALLS, res))
    ANSWERS.clear()

    # ---- the routes ----
    _real_cfg = main.cfgmod.read_settings
    try:
        main.cfgmod.read_settings = lambda: dict(cfg(GPT, GROQ), **{"model": dict(
            GPT, **GROQ, main={"provider": "openai-oauth", "model": ""})})
        r = client.get("/voice/ear").json()
        check("/voice/ear: ChatGPT main brain -> ChatGPT plan ear, upload",
              r["provider"] == "chatgpt" and r["kind"] == "upload", r)
        CALLS.clear()
        r = client.post("/stt", files={"file": ("v.webm", b"\x1aE\xdf\xa3", "audio/webm")}, data={"lang": "auto"})
        check("/stt: the ChatGPT plan hears the dictation", r.json()["ok"] and CALLS == ["chatgpt"], (CALLS, r.json()))
        CALLS.clear()
        res = run(main._stt_nghe(b"OggS", "voice.oga"))
        check("Telegram/Zalo voice message on a ChatGPT brain: the plan hears it first",
              res.get("ok") and CALLS[:1] == ["chatgpt"] and res.get("ear") == "chatgpt", (CALLS, res))

        main.cfgmod.read_settings = lambda: {"model": dict(GPT, **GROQ, main={"provider": "anthropic-cli"}),
                                             "voice": {"ear": "off"}}
        CALLS.clear()
        res = run(main._stt_nghe(b"OggS", "voice.oga"))
        check("voice message, Claude brain, mic ear off -> still heard, Groq first", CALLS[:1] == ["groq"], CALLS)
    finally:
        main.cfgmod.read_settings = _real_cfg

    # ============================================================
    # 4. Agents: the agent's own model's vendor, not the main model's
    # ============================================================
    # Owner, 2026-11-08: "an agent on a vendor's model uses that vendor's ear, not the main model's".
    AGENT_MODELS = {"seller": {"provider": "openai-oauth", "model": "gpt-5.1"}, "writer": {}}
    _real = (main.cfgmod.read_settings, main._model_cua_agent, main.get_store)
    main._model_cua_agent = lambda brain, slug: dict(AGENT_MODELS.get(slug) or {})
    SESSIONS = {}

    class FakeStore:
        def get_session(self, sid):
            return SESSIONS.get(sid)

    main.get_store = lambda: FakeStore()
    try:
        groq_main = {"model": dict(GPT, **GROQ, main={"provider": "groq"}), "voice": {}}
        main.cfgmod.read_settings = lambda: groq_main
        check("agent on a ChatGPT model -> its ear is the ChatGPT plan's, the main brain is Groq",
              main._ear_brain_provider(groq_main, agent={"brain": "brain", "slug": "seller"}) == "openai-oauth")
        check("agent left on Default -> the main model's ear",
              main._ear_brain_provider(groq_main, agent={"brain": "brain", "slug": "writer"}) == "groq")
        check("no agent, no chat -> the main model's ear", main._ear_brain_provider(groq_main) == "groq")

        CALLS.clear()
        res = run(main._stt_nghe(b"OggS", "voice.oga", agent={"brain": "brain", "slug": "seller"}))
        check("voice message to a ChatGPT agent (dedicated bot) -> ChatGPT plan first, not the main Groq",
              CALLS[:1] == ["chatgpt"], CALLS)
        CALLS.clear()
        run(main._stt_nghe(b"OggS", "voice.oga"))
        check("the same voice message to Javis itself -> Groq, the main model's vendor", CALLS[:1] == ["groq"], CALLS)

        SESSIONS["s-agent"] = {"channel": "agent:seller", "brain": "brain"}
        SESSIONS["s-pinned"] = {"channel": "web", "pinned_provider": "groq", "pinned_model": "llama"}
        SESSIONS["s-plain"] = {"channel": "web"}
        CALLS.clear()
        r = client.post("/stt", files={"file": ("v.webm", b"\x1aE\xdf\xa3", "audio/webm")},
                        data={"lang": "auto", "session": "s-agent"})
        check("dictating in a partner's chat (agent on ChatGPT) -> the ChatGPT plan hears it",
              r.json()["ok"] and CALLS == ["chatgpt"], (CALLS, r.json()))
        CALLS.clear()
        client.post("/stt", files={"file": ("v.webm", b"\x1aE\xdf\xa3", "audio/webm")},
                    data={"lang": "auto", "session": "s-plain"})
        check("dictating in a normal chat -> the main model's vendor (Groq)", CALLS == ["groq"], CALLS)
        CALLS.clear()
        client.post("/stt", files={"file": ("v.webm", b"\x1aE\xdf\xa3", "audio/webm")},
                    data={"lang": "auto", "session": "nope"})
        check("an unknown session id -> the main model's ear, no error", CALLS == ["groq"], CALLS)

        chatgpt_main = {"model": dict(GPT, **GROQ, main={"provider": "openai-oauth"}), "voice": {}}
        main.cfgmod.read_settings = lambda: chatgpt_main
        CALLS.clear()
        client.post("/stt", files={"file": ("v.webm", b"\x1aE\xdf\xa3", "audio/webm")},
                    data={"lang": "auto", "session": "s-pinned"})
        check("a chat pinned to Groq on a ChatGPT machine -> Groq hears it (the model that answers)",
              CALLS == ["groq"], CALLS)

        # ---- the dedicated bot hands its agent to the ear ----
        import chatbot_runtime as cr
        got = {}

        async def ear_with_agent(data, name, agent=None):
            got["agent"] = agent
            return {"ok": True, "text": "x"}

        async def ear_plain(data, name):
            got["plain"] = True
            return {"ok": True, "text": "x"}

        _real_dep = cr._deps.get("transcribe")
        try:
            cr._deps["transcribe"] = ear_with_agent
            run(cr._hear_for({"agent": {"brain": "b", "slug": "seller"}})(b"x", "v.m4a"))
            check("dedicated bot: the ear is told which agent it hears for", got.get("agent") == {"brain": "b",
                                                                                                  "slug": "seller"})
            check("bot without an agent: the ear unchanged", cr._hear_for({}) is ear_with_agent)
            cr._deps["transcribe"] = ear_plain
            run(cr._hear_for({"agent": {"brain": "b", "slug": "seller"}})(b"x", "v.m4a"))
            check("an ear that takes no agent still works", got.get("plain") is True)
        finally:
            cr._deps["transcribe"] = _real_dep
    finally:
        main.cfgmod.read_settings, main._model_cua_agent, main.get_store = _real
finally:
    stt.groq_nghe, stt.openai_nghe, stt.chatgpt_nghe, stt.gemini_nghe, voice_ear.chatgpt_creds = _saved

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - chatgpt_ear")
