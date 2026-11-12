"""A plan card that lost its sign-in moves the turn on, like one out of quota (2026-11-12).

    python tests/run.py signin_loss_route     (no network, no real CLI)

Owner's report, 12/11/2026, with a customer's screenshot: a bot whose agent runs on ChatGPT lost the ChatGPT sign-in at
11:13 and every turn after that failed ("when ChatGPT is signed out it does not move to the other routes to answer"),
while another model was signed in. Only a QUOTA refusal moved a turn on (spec 6.4, tests/python/test_chat_doi_duong.py).

Covered here:
  1. the detector (`signin_loss.is_signin_error`): the CLIs' own sentences, never an MCP server's 401 or a long answer;
  2. a REAL web turn through `main.websocket_endpoint` on a fake Codex CLI: account 1 refused for a lost sign-in before
     writing anything -> the turn runs again at once, no error bubble; after a tool call it never runs again;
  3. the mark: a signed-out card is skipped by MAIN and by a pinned chat (an agent's or a bot's model), is lifted by a
     sign-in, by choosing the card, and by itself after the retry window; the chip never calls it "out of quota";
  4. channel turns: the error strings a channel turn returns are recognised, and a customer bot hops too;
  5. a workflow step runs again on the route that can run; a team member's own model falls back to the main model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-signin-loss-"))

from fastapi import WebSocketDisconnect  # noqa: E402

import main  # noqa: E402
import model_routing  # noqa: E402
import plan_accounts  # noqa: E402
import signin_loss  # noqa: E402
import team_runner  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402
from sessions import SessionStore  # noqa: E402

_fails = []
# The real functions, put back after the web turns replaced them with fixed answers.
_REAL_CHAT_PROVIDER = main._chat_provider
_REAL_HAS_EXTRA = plan_accounts.has_extra
# What Codex CLI prints when its refresh token is dead (connect_health.py, incident of 2026-07-30).
LOST = ("Your access token could not be refreshed because your refresh token was already used. "
        "Please log out and sign in again.")
LIMIT = "You've hit your usage limit. Upgrade to Pro or try again later."
CHATGPT = "openai-oauth"


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if not cond and extra else ""))
    if not cond:
        _fails.append(name)


class _FakeSocket:
    cookies = {}

    def __init__(self, payload):
        self._payload = json.dumps(payload)
        self.sent = []

    async def accept(self):
        pass

    async def close(self, code=None):
        pass

    async def send_text(self, value):
        self.sent.append(json.loads(value))

    async def receive_text(self):
        if self._payload is not None:
            value, self._payload = self._payload, None
            return value
        for _ in range(400):
            if any(g.get("type") == "turn_done" for g in self.sent):
                break
            await asyncio.sleep(0.02)
        raise WebSocketDisconnect()


def _fake_codex(script):
    """A fake CodexCLI: account 1 (no codex_home) plays `script`, account 2 answers in full."""
    ran = []

    class _FakeCodex:
        def __init__(self, cwd=None, model=None, tag=None, instructions=None):
            self.session_id = None
            self.profile = None
            self.extra_config = []
            self.codex_home = None

        def is_available(self):
            return True

        async def query(self, prompt):
            acc = "acc2" if self.codex_home else "main"
            ran.append(acc)
            if acc == "main":
                for ev in script:
                    yield ev
                return
            yield {"type": "text", "content": "Account 2 answers here."}
            yield {"type": "final", "content": "Account 2 answers here.", "tokens_in": 10, "tokens_out": 5}

    return _FakeCodex, ran


def _two_accounts():
    return {"order": [CHATGPT], "main": {"provider": CHATGPT, "model": "gpt-5.6-luna"},
            "accounts": {CHATGPT: [{"id": "main", "label": "", "enabled": True},
                                   {"id": "acc2", "label": "", "enabled": True}]}}


def _sign_in_acc2():
    folder = plan_accounts.home(CHATGPT, "acc2")
    (folder / "auth.json").write_text(json.dumps({"tokens": {"access_token": "x", "refresh_token": "y"}}),
                                      encoding="utf-8")


def _reset():
    for acc in ("main", "acc2"):
        model_routing.clear_rest(CHATGPT, acc)
    for store in (main._PIN_LIMITED, main._SIGNED_OUT, main._SIGNED_OUT_TOLD):
        store.clear()


def _run_turn(mp, tmpdir, script, sid):
    _reset()
    _sign_in_acc2()
    runtime = ChatRuntime()
    store = SessionStore(tmpdir / f"{sid}.db")
    ws = _FakeSocket({"message": "Summarise this week's revenue", "brain": "brain", "session_id": sid})
    codex, ran = _fake_codex(script)
    mcfg = _two_accounts()
    mp.setattr(main, "_CHAT_RUNTIME", runtime)
    mp.setattr(main, "get_store", lambda: store)
    mp.setattr(main.cfgmod, "gate_active", lambda: False)
    mp.setattr(main.cfgmod, "read_settings", lambda: {"model": mcfg})
    mp.setattr(main, "_chat_provider", lambda _cfg: (CHATGPT, "oauth", "", "gpt-5.6-luna"))
    mp.setattr(main, "_routing_connected_ids", lambda _s: [CHATGPT])
    mp.setattr(main, "_reasoning_level", lambda _cfg: "off")
    mp.setattr(main, "_codex_safe_model", lambda m: m or "gpt-5.6-luna")
    mp.setattr(main, "build_system_prompt", lambda *a, **k: "system")
    mp.setattr(main.channel_context, "build_channel_block", lambda *a, **k: "")
    mp.setattr(main, "claude_engine", lambda **_kw: SimpleNamespace(session_id=None))
    mp.setattr(main, "CodexCLI", codex)
    mp.setattr(main, "_apply_codex_hub", lambda *a, **k: None)
    mp.setattr(main.openai_oauth, "write_codex_auth", lambda *a, **k: None)
    mp.setattr(main, "_schedule_registry_discovery_shadow", lambda *a, **k: None)
    mp.setattr(main, "log_conversation", lambda *a, **k: None)
    mp.setattr(main.usage_store, "record", lambda *a, **k: None)

    async def nothing(*_a, **_k):
        return None

    mp.setattr(main, "_schedule_cancel_action", nothing)
    mp.setattr(main.learn_feature, "enqueue", nothing)

    async def go():
        await main.websocket_endpoint(ws)
        for _ in range(60):
            if runtime.get_job(sid) is None:
                break
            await asyncio.sleep(0.02)

    asyncio.run(go())
    main.limit_resume.REGISTRY.cancel(sid)
    return ws, store, ran


def _frames(ws, kind):
    return [g for g in ws.sent if g.get("type") == kind]


def _detector():
    yes = signin_loss.is_signin_error
    check("detector: Codex's dead refresh token", yes(LOST))
    check("detector: Codex's error with its last log lines", yes("Codex lỗi (exit 1):\nstarting\n" + LOST))
    check("detector: the ChatGPT backend's 401", yes("⚠ ChatGPT 401: Unauthorized"))
    check("detector: Javis's own 'not signed in to ChatGPT' sentences",
          yes("⚠ Chưa đăng nhập được ChatGPT nên bot không gọi được model.")
          and yes("Not signed in to ChatGPT (OAuth). Go to Models to connect."))
    check("detector: Claude Code's line, as an error and as a short answer",
          yes("Not logged in · Please run /login") and yes("Not logged in · Please run /login", answer=True))
    check("detector: an MCP server's 401 is not the plan's sign-in",
          not yes("MCP client for `canva` failed to start: 401 Unauthorized"))
    check("detector: a quota sentence, a plain error and nothing are not a sign-in",
          not yes(LIMIT) and not yes("⚠ Engine returned nothing.") and not yes("") and not yes(None))
    long_answer = "When the CLI prints 'Not logged in', run the login again. " * 12
    check("detector: a long answer quoting the words is left alone", not yes(long_answer, answer=True))
    check("detector: ChatGPT 403 (a region block, a challenge page) is not read as a lost sign-in",
          not yes("ChatGPT 403: Forbidden"))
    check("main: only plan cards have a sign-in to lose",
          main._signin_lost_text(CHATGPT, LOST) and not main._signin_lost_text("groq", "401 Unauthorized"))
    check("main: a quota sentence is never a sign-in loss", not main._signin_lost_text(CHATGPT, LIMIT))


def _web_turns(mp, tmp):
    # ---- refused before a single word: the turn runs again at once on account 2 ----
    ws, store, ran = _run_turn(mp, tmp, [{"type": "error", "content": LOST}], "sess-a")
    check("web: account 1 is refused, account 2 runs the same turn", ran == ["main", "acc2"], str(ran))
    moved = _frames(ws, "reroute")
    check("web: ONE line says the route changed", len(moved) == 1, str(moved))
    if moved:
        line = moved[0].get("content") or ""
        check("web: the line names the sign-in, not quota",
              "ChatGPT" in line and ("mất đăng nhập" in line or "lost its sign-in" in line) and "hết lượt" not in line
              and "quota" not in line, line)
        check("web: the line has no long dash", "\u2014" not in line and "\u2013" not in line)
    check("web: the owner sees no error bubble", not _frames(ws, "error"), str(_frames(ws, "error")))
    answers = [g for g in _frames(ws, "response") if (g.get("content") or "").strip()]
    check("web: the answer is account 2's", len(answers) == 1 and answers[0]["content"] == "Account 2 answers here.")
    msgs = store.get_messages("sess-a")
    check("web: the session keeps the question and the real answer only",
          [(m["role"], m["content"]) for m in msgs] == [("user", "Summarise this week's revenue"),
                                                        ("assistant", "Account 2 answers here.")],
          str([(m["role"], m["content"][:30]) for m in msgs]))
    check("web: account 1 rests", model_routing.resting_until(CHATGPT, "main") > 0)
    check("web: the card is not marked signed out while account 2 can run", not main._signed_out_until(CHATGPT))
    check("web: nothing is marked out of quota", not main._pin_limited_until(CHATGPT))
    check("web: no 'run again' card", not _frames(ws, "resume"))

    # ---- refused after a tool call: never run again elsewhere ----
    ws, store, ran = _run_turn(mp, tmp, [{"type": "tool_call", "name": "zalo_send_message", "input": {}},
                                         {"type": "error", "content": LOST}], "sess-b")
    check("web, tool already called: no second run", ran == ["main"], str(ran))
    check("web, tool already called: no route line", not _frames(ws, "reroute"))
    errs = _frames(ws, "error")
    check("web, tool already called: the error says to sign in again, in words the owner reads",
          len(errs) == 1 and "ChatGPT" in errs[0]["content"] and "Models" in errs[0]["content"], str(errs))

    # ---- one account only and no other card: the refusal is shown, the card is marked ----
    _reset()
    mp.setattr(plan_accounts, "has_extra", lambda _m, _p: False)
    try:
        main._note_signin_lost(CHATGPT)
        check("one account: the card is marked signed out", main._signed_out_until(CHATGPT) > time.time())
        check("one account: nothing rests as if out of quota",
              not model_routing.resting_until(CHATGPT, "main") and not main._pin_limited_until(CHATGPT))
    finally:
        mp.setattr(plan_accounts, "has_extra", _REAL_HAS_EXTRA)
    _reset()


def _mark(mp):
    m = {"order": [CHATGPT, "groq", "anthropic-cli"], "main": {"provider": CHATGPT, "model": "gpt-5.6-luna"},
         "groq_api_key": "gsk_test", "profiles": {"groq": {"model": "llama-4", "reasoning": "off"}}}
    mp.setattr(main.cfgmod, "read_settings", lambda: {"model": m})
    mp.setattr(main, "_routing_connected_ids", lambda _s: [CHATGPT, "groq", "anthropic-cli"])
    mp.setattr(main, "_chat_provider", _REAL_CHAT_PROVIDER)
    _reset()
    check("mark: a card nobody marked can run", main._route_ready(m, CHATGPT))
    told = []
    mp.setattr(main.inbox, "add", lambda text, **kw: told.append((text, kw)) or {})
    main._note_signin_lost(CHATGPT)
    main._note_signin_lost(CHATGPT)
    check("mark: a signed-out card cannot take a turn", not main._route_ready(m, CHATGPT))
    check("mark: the owner is told once, not at every refusal",
          len(told) == 1 and "ChatGPT" in told[0][0] and "Models" in told[0][0], str(told))
    check("mark: MAIN signed out -> the chat starts on the next card that can run",
          main._chat_provider(m)[0] == "groq" and main._chat_provider(m)[3] == "llama-4", str(main._chat_provider(m)))

    # An agent's (or a bot's) own model is a pin: signed out, it runs on the main route instead of failing.
    m_pin = dict(m, order=["groq", CHATGPT, "anthropic-cli"], main={"provider": "groq", "model": "llama-4"})
    pinned = {"pinned_provider": CHATGPT, "pinned_model": "gpt-5.6-luna"}
    check("pin: an agent set to ChatGPT runs on the main model while ChatGPT is signed out",
          main._chat_provider_for_session(m_pin, pinned)[0] == "groq", str(main._chat_provider_for_session(m_pin, pinned)))
    mp.setattr(main, "_model_cua_agent", lambda _b, _s: {"provider": CHATGPT, "model": "gpt-5.6-luna"})
    bot = {"id": "b1", "agent": {"brain": "brain", "slug": "sales"}}
    check("pin: a customer bot on that agent runs on the main model too", main._chat_provider_bot(m_pin, bot)[0] == "groq")

    view = main._route_view(m_pin, pinned)
    check("chip: the fallback reason is the sign-in",
          view.get("fallback") is True and view.get("reason") == "signin" and view.get("provider") == "groq", str(view))
    check("chip: the card is listed as signed out and never as 'out of quota until'",
          view.get("signed_out") == [CHATGPT] and CHATGPT not in (view.get("limited") or {}), str(view))
    check("chip: the sentence says sign-in", "mất đăng nhập" in view.get("content", "")
          or "lost its sign-in" in view.get("content", ""), view.get("content"))

    nxt = main._chat_next_route(m, CHATGPT, reason="signin")
    check("next route: the next card of the usage order", bool(nxt) and nxt["route"][0] == "groq", str(nxt))
    check("next route: the status line says why", bool(nxt) and "Groq" in nxt["status"]
          and ("mất đăng nhập" in nxt["status"] or "lost its sign-in" in nxt["status"]), str(nxt.get("status")))

    # Lifting the mark.
    main._plan_main_signed_in(CHATGPT)
    check("lift: signing in again lifts the mark at once", not main._signed_out_until(CHATGPT) and main._route_ready(m, CHATGPT))
    check("lift: after a sign-in the pinned agent is back on its own model",
          main._chat_provider_for_session(m_pin, pinned)[0] == CHATGPT)
    main._note_signin_lost(CHATGPT)
    check("lift: a loss after a fresh sign-in is told again", len(told) == 2, str(len(told)))
    check("lift: choosing the card on purpose lifts it", main._clear_pin_limit(CHATGPT) is True
          and not main._signed_out_until(CHATGPT))
    main._note_signin_lost(CHATGPT, now=1000.0)
    check("lift: the mark stands inside the retry window", main._signed_out_until(CHATGPT, now=1000.0 + 60) > 0)
    check("lift: after the window one turn tries the card again",
          main._signed_out_until(CHATGPT, now=1000.0 + signin_loss.RETRY_S + 1) == 0)
    check("mark: an API card is never marked", main._note_signin_lost("groq") is None and not main._SIGNED_OUT.get("groq"))
    _reset()


def _channels(mp):
    m = {"order": [CHATGPT, "groq"], "main": {"provider": CHATGPT, "model": "gpt-5.6-luna"},
         "groq_api_key": "gsk_test", "profiles": {"groq": {"model": "llama-4", "reasoning": "off"}}}
    mp.setattr(main.cfgmod, "read_settings", lambda: {"model": m})
    mp.setattr(main, "_routing_connected_ids", lambda _s: [CHATGPT, "groq"])
    mp.setattr(main.inbox, "add", lambda text, **kw: {})
    _reset()
    check("channel: an ordinary error is not a sign-in loss and marks nothing",
          not main._tg_signin_out("⚠ Codex không trả về nội dung nào.", CHATGPT) and not main._SIGNED_OUT)
    check("channel: Codex's refusal is recognised and the card is marked",
          main._tg_signin_out("⚠ " + LOST, CHATGPT) and main._signed_out_until(CHATGPT) > 0)
    _reset()
    check("channel: the bot path's own sentence is recognised",
          main._tg_signin_out("⚠ Chưa đăng nhập được ChatGPT nên bot không gọi được model. "
                              "Vào trang Models kết nối lại tài khoản ChatGPT rồi nhắn lại.", CHATGPT))
    _reset()

    # A customer bot whose agent runs on ChatGPT: the refused turn is answered by the next card, in the same turn.
    calls, lines = [], []

    async def fake_engine(text, meta, progress, *, prov, **_kw):
        calls.append(prov)
        if prov == CHATGPT:
            return "⚠ ChatGPT 401: Unauthorized"
        return {"text": "Dạ, shop còn hàng ạ.", "files": []}

    async def progress(s):
        lines.append(s)

    mp.setattr(main, "_tg_answer_engine", fake_engine)
    mp.setattr(main, "_chat_provider_bot", lambda _m, _b: (CHATGPT, "oauth", "", "gpt-5.6-luna"))
    mp.setattr(main, "_record_quality_shadow", lambda *a, **k: None)
    bot = {"id": "b1", "slug": "shop", "brain": "brain", "agent": {"brain": "brain", "slug": "sales"}}
    out = asyncio.run(main._tg_answer("Shop còn hàng không?", {"chat_id": "c1"}, progress, channel="zalo", bot=bot,
                                      ghi_kho=False))
    check("bot: the turn ChatGPT refused is answered by the next card", calls == [CHATGPT, "groq"], str(calls))
    check("bot: the customer gets the real answer", isinstance(out, dict) and out.get("text") == "Dạ, shop còn hàng ạ.",
          str(out))
    check("bot: the customer never sees the routing line", not any("↻" in str(s) for s in lines), str(lines))
    check("bot: ChatGPT is marked, so the bot's next turns start elsewhere", main._signed_out_until(CHATGPT) > 0)
    _reset()

    # The owner's own channel turn hops as well, and is told why.
    calls.clear(), lines.clear()
    mp.setattr(main, "_chat_provider_kenh", lambda _m, _c, _k="": (CHATGPT, "oauth", "", "gpt-5.6-luna"))

    async def quiet(*_a, **_k):
        return ""

    mp.setattr(main, "_canh_bao_hua_suong", quiet)
    out = asyncio.run(main._tg_answer("Doanh thu hôm nay?", {"chat_id": "owner1"}, progress, channel="telegram",
                                      ghi_kho=False))
    check("owner channel: the turn moves to the next card", calls == [CHATGPT, "groq"] and isinstance(out, dict), str(calls))
    check("owner channel: one line says the sign-in was lost",
          sum(1 for s in lines if "↻" in str(s) and ("mất đăng nhập" in s or "lost its sign-in" in s)) == 1, str(lines))
    _reset()

    # After a tool ran ("⚙" line) nothing is run twice.
    calls.clear()

    async def acted_engine(text, meta, progress, *, prov, **_kw):
        calls.append(prov)
        await progress("⚙ Đang dùng công cụ: zalo_send_message")
        return "⚠ ChatGPT 401: Unauthorized"

    mp.setattr(main, "_tg_answer_engine", acted_engine)
    out = asyncio.run(main._tg_answer("Gửi báo giá", {"chat_id": "c2"}, progress, channel="zalo", bot=bot, ghi_kho=False))
    check("bot, tool already called: no second run", calls == [CHATGPT] and isinstance(out, str), str(calls))
    _reset()


def _steps_and_teams(mp):
    mp.setattr(main.inbox, "add", lambda text, **kw: {})
    _reset()

    def engine(prov, script, acc="main"):
        async def query(prompt):
            for ev in script:
                yield ev
        return SimpleNamespace(account_provider=prov, account_id=acc, query=query)

    def run(builds, prompt="go"):
        made = []

        def build():
            eng = builds[min(len(made), len(builds) - 1)]
            made.append(eng)
            return eng

        async def collect():
            return [ev async for ev in main._step_run(build, prompt)]

        return asyncio.run(collect()), made

    ok = [{"type": "text", "content": "Done."}, {"type": "final", "content": "Done."}]
    evs, made = run([engine(CHATGPT, [{"type": "error", "content": LOST}]), engine("anthropic-cli", ok)])
    check("step: refused for a lost sign-in -> runs again on the engine built next", len(made) == 2
          and [e["type"] for e in evs] == ["text", "final"], str(evs))
    check("step: the refusal is not shown when another route answered", not any(e["type"] == "error" for e in evs))
    check("step: the card is marked", main._signed_out_until(CHATGPT) > 0)
    _reset()

    evs, made = run([engine(CHATGPT, [{"type": "error", "content": LOST}])])
    check("step: no other route -> the refusal comes out as before",
          len(made) == 2 and [e["type"] for e in evs] == ["error"] and evs[0]["content"] == LOST, str(evs))
    _reset()

    evs, made = run([engine(CHATGPT, [{"type": "tool_call", "name": "zalo_send_message"},
                                      {"type": "error", "content": LOST}]), engine("anthropic-cli", ok)])
    check("step: a tool already ran -> never run twice", len(made) == 1
          and [e["type"] for e in evs] == ["tool_call", "error"], str(evs))
    check("step: an error after a tool call marks nothing here", not main._signed_out_until(CHATGPT))
    _reset()

    evs, made = run([engine(CHATGPT, ok)])
    check("step: a healthy plan engine passes through unchanged", len(made) == 1 and evs == ok, str(evs))
    evs, made = run([SimpleNamespace(query=engine("x", [{"type": "error", "content": LOST}]).query)])
    check("step: an engine that is not a plan card is left alone", len(made) == 1 and evs[0]["type"] == "error")
    _reset()

    evs, made = run([engine("anthropic-cli", [{"type": "final", "content": "Not logged in · Please run /login"}]),
                     engine(CHATGPT, ok)])
    check("step: Claude Code's 'Not logged in' printed as the answer is a refusal too",
          len(made) == 2 and [e["type"] for e in evs] == ["text", "final"] and main._signed_out_until("anthropic-cli") > 0,
          str(evs))
    _reset()

    # Source wiring: both step runners build their engine through `_step_run`, and `_mk` reads the mark.
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    check("wiring: both workflow step runners go through _step_run", src.count("async for ev in _step_run(") == 2)
    mk = src[src.index("    def _mk(sysprompt, model=None"):src.index("    def _agent_sysprompt(aslug")]
    check("wiring: _mk sends an ungated step off a signed-out card, and keeps a gated one on its safety rail",
          "_signed_out_until(prov)" in mk and "tools is not None and not signed_out" in mk)

    # A team member's own model on a signed-out card: the turn is built on the main model, with the reason.
    main._SIGNED_OUT[CHATGPT] = time.time() + 300
    ok_av, why = main._agent_spec_available({"provider": CHATGPT, "model": "gpt-5.6-luna"}, {})
    check("team: a signed-out card is not available for a member's own model", ok_av is False and "ChatGPT" in why, why)
    spec = main.team_engine.choose_spec("gpt-5.6-luna", CHATGPT, {"provider": "anthropic-cli", "model": "opus"},
                                        main._agent_model_provider, lambda sp: main._agent_spec_available(sp, {}))
    check("team: the turn runs on the main model and says why",
          spec["provider"] == "anthropic-cli" and spec["source"] == "main" and "đăng nhập" in spec["note"], str(spec))
    _reset()
    err = team_runner.EngineOutcomeError("error_event", LOST)
    check("team: a turn refused for a lost sign-in marks the card",
          main._team_quota_next(CHATGPT, SimpleNamespace(account_id="main"), err) == {}
          and main._signed_out_until(CHATGPT) > 0)
    _reset()


def main_test(mp, tmp):
    _detector()
    _web_turns(mp, tmp)
    _mark(mp)
    _channels(mp)
    _steps_and_teams(mp)


def test_signin_loss_route(monkeypatch, tmp_path):
    main_test(monkeypatch, tmp_path)
    assert not _fails, _fails


if __name__ == "__main__":
    class _Patch:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, value):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)

    mp = _Patch()
    tmp = Path(tempfile.mkdtemp(prefix="javis-signin-loss-run-"))
    try:
        main_test(mp, tmp)
    finally:
        mp.undo()
    print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
    sys.exit(1 if _fails else 0)
