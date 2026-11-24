"""Stop on a web chat drops what the stopped turn left to start by itself, and nothing else (PR #1736 redone).

Before: messages typed while an answer ran started a new turn right after the owner pressed Stop, a javis_job op=then
instruction of the stopped turn stayed pending for up to an hour and attached to a later turn's job, and a scheduled
quota re-run of the chat still fired. The first fix cleared far more (every job's follow-up, GitHub fix rounds, waiting
follow-ups of earlier jobs), so this one is narrow:

- the stopped turn's queued typed messages do not run, and the page is told (`steer_dropped`); a normal finish still
  runs them, and a message queued without a steer id is named by its client id;
- the pending instruction of that chat goes, and so does the follow-up of a running job started during that turn; a
  job of an earlier turn, another chat, a GitHub fix round and an earlier follow-up waiting for the chat are untouched;
- the chat's quota re-run is cancelled with the same `resume`/`cancelled` event a new message sends;
- Telegram and Zalo /stop are unchanged.

Run:
    python tests/run.py stop_queued
"""
from _paths import SERVER  # noqa: E402,F401
import ast
import asyncio
import os
import sys
import tempfile
import time
import types
import uuid

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-stop-state-"))
os.environ.setdefault("BRAINS_DIR", tempfile.mkdtemp(prefix="javis-stop-brains-"))

import bot_gateway  # noqa: E402
import chat_runtime  # noqa: E402
import limit_resume  # noqa: E402
import localefmt  # noqa: E402
import luot_dang_chay  # noqa: E402
import nghe_sua  # noqa: E402
import steer_inbox  # noqa: E402
import tien_trinh_nen  # noqa: E402
import turn_context  # noqa: E402
import main  # noqa: E402

_FAILS = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _FAILS.append(name)


_SRC = (SERVER / "main.py").read_text(encoding="utf-8")
_TREE = ast.parse(_SRC)


def _fn(name):
    return next(n for n in ast.walk(_TREE) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)


def _noop(*_a, **_kw):
    return None


async def _anoop(*_a, **_kw):
    return None


class _FastAsyncio:
    """asyncio for the follow-up opener, whose poll sleeps 5 s a round."""
    CancelledError = asyncio.CancelledError
    current_task = staticmethod(asyncio.current_task)
    create_task = staticmethod(asyncio.create_task)
    to_thread = staticmethod(asyncio.to_thread)

    @staticmethod
    async def sleep(_d):
        await asyncio.sleep(0.01)


class _Runtime:
    """A real ChatRuntime with a page attached, installed as main._CHAT_RUNTIME for the Stop handlers."""

    def __init__(self):
        self.rt = chat_runtime.ChatRuntime()
        self.events = []

        async def _page(ev):
            self.events.append(ev)
        self.rt.add_client("page", _page)

    def __enter__(self):
        self._old = main._CHAT_RUNTIME, main.cancel_all
        self.killed = []
        main._CHAT_RUNTIME = self.rt
        main.cancel_all = lambda tag=None: (self.killed.append(tag), 1)[1]
        return self

    def __exit__(self, *_a):
        main._CHAT_RUNTIME, main.cancel_all = self._old

    def of(self, kind):
        return [e for e in self.events if e.get("type") == kind]


def _turn_namespace(rt, engine_calls, gates):
    """The real run_turn and _start_steer_turn of main.py, with a fake engine. gates[n] holds the n-th engine call."""
    async def _do_turn(conv_sid, user_message, *_a, **_kw):
        engine_calls.append(user_message)
        gate = gates.get(len(engine_calls))
        if gate is not None:
            await gate.wait()
        return "done"

    async def _send_raw(frame):
        await rt.publish(frame)

    ns = dict(
        asyncio=asyncio, sys=sys, time=time, uuid=uuid, nghe_sua=nghe_sua, localefmt=localefmt,
        turn_context=turn_context, luot_dang_chay=luot_dang_chay, steer_inbox=steer_inbox, WEB_CHAT_PREFIX="web:",
        _brain_root=lambda b: b, cfgmod=types.SimpleNamespace(read_settings=lambda: {"recall": {"enabled": False}}),
        store=types.SimpleNamespace(get_session=lambda _s: None), send_raw=_send_raw, _do_turn=_do_turn,
        _bao_luot_dai_xong=_anoop, _resonance_turn_agent=_noop, _session_assistant=lambda *_a: "",
        _resonance_after_turn=_noop, _record_quality_shadow=_noop, _CHAT_RUNTIME=rt,
        tien_trinh_nen=types.SimpleNamespace(bo_tag=_noop),
        _CONTEXT_RUNTIME=types.SimpleNamespace(finish=_noop, note_error=_noop, start_turn=lambda *_a: None),
        context_runtime=types.SimpleNamespace(bind_trace=_noop, reset_trace=_noop, event_fields=lambda *_a: {}),
        _engine_outcome_reset=_noop, _engine_outcome_exception=_noop, _engine_outcome_turn=_noop,
        _engine_outcome_pop=lambda *_a: {},
    )
    exec(compile(ast.Module(body=[_fn("run_turn"), _fn("_start_steer_turn")], type_ignores=[]), "main-turn", "exec"),
         ns)
    return ns


async def _start_turn(ns, rt, sid, text):
    tag = f"chat:{sid[:12]}:{uuid.uuid4().hex[:8]}"
    task = asyncio.create_task(ns["run_turn"](sid, text, "brain", tag, None, user_mid=1, user_text=text))
    rt.register_job(sid, task, tag)
    await asyncio.sleep(0.05)          # the turn opened its inbox and waits in the engine
    return task


async def _settle(rt, sid):
    """Past the steer waiter's 0.5 s poll, then until every turn it started is over."""
    await asyncio.sleep(0.8)
    while rt.get_job(sid):
        await rt.get_job(sid).task
        await asyncio.sleep(0.05)


# ---- 1. Stop during a turn: the typed messages do not run, the page is told ----
async def _stop_drops_typed_messages():
    with _Runtime() as R:
        calls, gates = [], {1: asyncio.Event()}
        ns = _turn_namespace(R.rt, calls, gates)
        sid = "sid-stop-typed"
        task = await _start_turn(ns, R.rt, sid, "make the video")
        a = steer_inbox.INBOX.put(sid, "also add subtitles")
        b = steer_inbox.INBOX.put(sid, "and send it to Lan")
        # A message past the pending cap waits on its own (steer action, no steer id): named by its client id.
        over = asyncio.create_task(ns["_start_steer_turn"](sid, ["one more"], "brain", [],
                                                            after=R.rt.get_job(sid), client_ids=["bs11-x"]))
        res = await main.stop({"session_id": sid})
        await task
        await _settle(R.rt, sid)
        await over
        dropped = R.of("steer_dropped")
        check("Stop: the stopped turn reports it was stopped and ends",
              any(e.get("type") == "system" for e in R.events) and R.of("turn_done") and res["cancelled"] == 1, R.events)
        check("Stop: messages typed meanwhile start no turn of their own", calls == ["make the video"]
              and not R.of("steer_turn"), calls)
        check("Stop: the page is told which messages will not run (steer ids and the client id)",
              any(e.get("ids") == [a["id"], b["id"]] and e.get("session_id") == sid for e in dropped)
              and any(e.get("client_ids") == ["bs11-x"] for e in dropped), dropped)
        check("Stop: the engine of the stopped turn is killed by its tag",
              len(R.killed) == 1 and str(R.killed[0]).startswith(f"chat:{sid[:12]}:"), R.killed)
        # A voice barge-in or a dictated message mid-turn is stopCurrent() then a new message: the chat is free for it
        # (no turn started by itself would refuse it as "still answering").
        check("Stop: the chat is free for what the person says next", R.rt.get_job(sid) is None)


# ---- 2. A normal finish still runs the typed messages ----
async def _finish_runs_typed_messages():
    with _Runtime() as R:
        calls, gates = [], {1: asyncio.Event()}
        ns = _turn_namespace(R.rt, calls, gates)
        sid = "sid-finish-typed"
        task = await _start_turn(ns, R.rt, sid, "make the video")
        a = steer_inbox.INBOX.put(sid, "also add subtitles")
        over = asyncio.create_task(ns["_start_steer_turn"](sid, ["one more"], "brain", [],
                                                            after=R.rt.get_job(sid), client_ids=["bs11-y"]))
        gates[1].set()
        await task
        await _settle(R.rt, sid)
        await over
        await _settle(R.rt, sid)
        # Two waiters (the turn's leftovers and the one queued on its own) each run once; their order was never fixed.
        check("finish: the typed messages run as turns of their own", len(calls) == 3
              and sum("also add subtitles" in c for c in calls[1:]) == 1 and sum("one more" in c for c in calls[1:]) == 1,
              calls)
        check("finish: the page hears it is being worked on, nothing is dropped",
              any(e.get("ids") == [a["id"]] for e in R.of("steer_turn")) and not R.of("steer_dropped"), R.events)


asyncio.run(_stop_drops_typed_messages())
asyncio.run(_finish_runs_typed_messages())


# ---- 3. Follow-ups: the stopped turn's go, an earlier turn's stay ----
def _job(jid, chat, started, then):
    return {"id": jid, "pgid": 990000 + len(tien_trinh_nen._VIEC), "chat_id": chat, "trang_thai": "run",
            "noi_tiep": True, "sau_khi_xong": then, "bat_dau": started, "mo_ta": jid}


async def _stop_followups():
    with tien_trinh_nen._KHOA:
        tien_trinh_nen._LOI_DAN.clear()
        tien_trinh_nen._VIEC.clear()
    with _Runtime() as R:
        sid = "sid-followups"
        tien_trinh_nen._VIEC["j-earlier"] = _job("j-earlier", f"web:{sid}", time.time() - 120,
                                                 "add audio and send")
        hold = asyncio.Event()
        task = asyncio.create_task(hold.wait())
        R.rt.register_job(sid, task, f"chat:{sid[:12]}:t2")
        started = R.rt.get_job(sid).started
        tien_trinh_nen._VIEC["j-this"] = _job("j-this", f"web:{sid}", started + 0.01, "upload it")
        tien_trinh_nen._VIEC["j-other"] = _job("j-other", "web:sid-other", started + 0.01, "keep mine")
        done = _job("j-done", f"web:{sid}", started + 0.01, "already done")
        done["trang_thai"] = "xong"
        tien_trinh_nen._VIEC["j-done"] = done
        tien_trinh_nen.dat_loi_dan(f"web:{sid}", "then send the summary")
        tien_trinh_nen.dat_loi_dan("web:sid-other", "other chat")
        await main.stop({"session_id": sid})
        await asyncio.gather(task, return_exceptions=True)
    with tien_trinh_nen._KHOA:
        tien_trinh_nen._VIEC.clear()
    tien_trinh_nen._nap()          # what was dropped is on disk too
    v = tien_trinh_nen._VIEC
    check("Stop: the chat's pending javis_job op=then instruction is gone",
          tien_trinh_nen._lay_loi_dan(f"web:{sid}") == "")
    check("Stop: another chat's pending instruction stays", tien_trinh_nen._lay_loi_dan("web:sid-other") == "other chat")
    check("Stop: a job started during the stopped turn keeps running but drops its follow-up",
          v["j-this"]["trang_thai"] == "run" and not v["j-this"]["noi_tiep"] and v["j-this"]["sau_khi_xong"] == "")
    check("Stop: a job started in an earlier turn keeps its follow-up",
          v["j-earlier"]["noi_tiep"] and v["j-earlier"]["sau_khi_xong"] == "add audio and send")
    check("Stop: another chat's job and a finished job are untouched",
          v["j-other"]["sau_khi_xong"] == "keep mine" and v["j-done"]["sau_khi_xong"] == "already done")
    # /stop with no turn running: only the pending instruction can go, no job qualifies.
    tien_trinh_nen.dat_loi_dan("web:sid-idle", "x")
    tien_trinh_nen._VIEC["j-idle"] = _job("j-idle", "web:sid-idle", time.time(), "keep")
    n = tien_trinh_nen.drop_stopped_followups("web:sid-idle", since=None)
    check("Stop with no running turn: the pending instruction only", n == 1
          and tien_trinh_nen._VIEC["j-idle"]["sau_khi_xong"] == "keep")
    check("empty chat id is a no-op", tien_trinh_nen.drop_stopped_followups("", since=0) == 0)


asyncio.run(_stop_followups())


# ---- 4. A GitHub fix round and an earlier job's follow-up waiting for the chat are untouched ----
async def _waiters_untouched():
    with _Runtime() as R:
        sid = "sid-github-round"
        started = []

        async def _fake_run(s, msg, *_a, **_kw):
            started.append(msg)
        ns = dict(asyncio=_FastAsyncio, uuid=uuid, _CHAT_RUNTIME=R.rt, _DO_SAU_NOI_TIEP={}, run_turn=_fake_run,
                  _CONTEXT_RUNTIME=types.SimpleNamespace(start_turn=lambda *_a: None), push_to_chat=_anoop,
                  store=types.SimpleNamespace(append_message=lambda *_a: None))
        exec(compile(ast.Module(body=[_fn("_start_followup_turn")], type_ignores=[]), "main-followup", "exec"), ns)
        runner = (lambda _t, _d, _s=sid: ns["_start_followup_turn"](_s, _t, "brain", _d))
        old_runner = main._NOI_TIEP_WEB.get(sid)
        main._NOI_TIEP_WEB[sid] = runner
        try:
            hold = asyncio.Event()
            task = asyncio.create_task(hold.wait())
            R.rt.register_job(sid, task, f"chat:{sid[:12]}:t3")
            ok = await main._github_start_turn(sid, "GitHub fix round: CI failed")
            earlier = asyncio.create_task(runner("Background job done: render. Continue: add audio", 1))
            await asyncio.sleep(0.05)
            await main.stop({"session_id": sid})
            await asyncio.gather(task, return_exceptions=True)
            for _ in range(200):
                if len(started) == 2:
                    break
                await asyncio.sleep(0.02)
            await earlier
            check("GitHub fix round: still opens its turn after the stopped one", ok and
                  "GitHub fix round: CI failed" in started, started)
            check("GitHub fix round: the chat keeps its follow-up opener", main._NOI_TIEP_WEB.get(sid) is runner)
            check("an earlier job's follow-up waiting for the chat still runs",
                  any("add audio" in m for m in started), started)
        finally:
            if old_runner is None:
                main._NOI_TIEP_WEB.pop(sid, None)
            else:
                main._NOI_TIEP_WEB[sid] = old_runner


asyncio.run(_waiters_untouched())


# ---- 5. The chat's quota re-run is cancelled with the event the page already knows ----
async def _quota_resume():
    with _Runtime() as R:
        sid = "sid-quota"
        ran = []

        async def _rerun(attempt):
            ran.append(attempt)
        limit_resume.REGISTRY.schedule(sid, time.time() + 600, _rerun, auto_default=True)
        limit_resume.REGISTRY.schedule("sid-quota-other", time.time() + 600, _rerun, auto_default=True)
        hold = asyncio.Event()
        task = asyncio.create_task(hold.wait())
        R.rt.register_job(sid, task, f"chat:{sid[:12]}:t4")
        await main.stop({"session_id": sid})
        await main.stop({"session_id": sid})      # the page stops over the socket and over HTTP
        await asyncio.gather(task, return_exceptions=True)
        ev = R.of("resume")
        check("Stop: the chat's quota re-run is cancelled", limit_resume.REGISTRY.get(sid) is None and not ran)
        check("Stop: the page gets resume/cancelled once, with why",
              ev == [{"type": "resume", "session_id": sid, "state": "cancelled", "reason": "stopped"}], ev)
        check("Stop: another chat's re-run stays", limit_resume.REGISTRY.get("sid-quota-other") is not None)
        limit_resume.REGISTRY.cancel("sid-quota-other")


asyncio.run(_quota_resume())


# ---- 6. Telegram and Zalo /stop are unchanged ----
class _Bot(bot_gateway.HangLuot):
    def __init__(self):
        self.command_fn, self.precheck_fn, self.giau_trang_thai = None, None, False
        self._current, self._cho, self._stop = {}, {}, False
        self.sent, self.commands = [], []

        async def _cmd(cmd, arg, chat, meta):
            self.commands.append((cmd, chat))
            return {"reply": "stopped"}
        self.command_fn = _cmd

    async def _send(self, client, chat, text, markup=None):
        self.sent.append(text)

    async def _handle_turn(self, client, chat, text, meta=None):
        await asyncio.Event().wait()


async def _channels():
    bot = _Bot()
    bot._chay_luot(None, "42", "first")
    await asyncio.sleep(0.02)
    steer_inbox.INBOX.put(bot._steer_sid("42"), "typed meanwhile")
    bot._xep_hang("42", "queued")
    task = bot._current["42"]
    await bot._dispatch(None, "42", "/stop")
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0.02)
    check("channel /stop: the turn is cancelled, its queue and typed messages dropped, nothing runs after",
          task.cancelled() and "42" not in bot._cho and not bot._current.get("42")
          and steer_inbox.INBOX.drop(bot._steer_sid("42")) == [] and bot.commands == [("stop", "42")])
    killed = []
    old = main.cancel_all
    main.cancel_all = lambda tag=None: (killed.append(tag), 1)[1]
    limit_resume.REGISTRY.schedule("sid-web-untouched", time.time() + 600, _anoop, auto_default=True)
    tien_trinh_nen.dat_loi_dan("web:sid-web-untouched", "web follow-up")
    try:
        tg = await main._tg_command("stop", "", chat="12345")
        zl = await main._zalo_command("stop", "", chat="z1")
    finally:
        main.cancel_all = old
    check("Telegram and Zalo /stop kill only their own chat's engine, as before",
          killed == ["telegram:12345", "telegram:zalo:z1"] and tg.get("reply") and zl.get("reply"), (killed, tg, zl))
    check("Telegram and Zalo /stop leave web chats alone",
          limit_resume.REGISTRY.get("sid-web-untouched") is not None
          and tien_trinh_nen._lay_loi_dan("web:sid-web-untouched") == "web follow-up")
    limit_resume.REGISTRY.cancel("sid-web-untouched")


asyncio.run(_channels())


# ---- wiring and hygiene ----
_stop_if = next(n for n in ast.walk(_TREE) if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                and getattr(n.test.left, "id", None) == "action"
                and any(isinstance(c, ast.Constant) and c.value == "stop" for c in n.test.comparators))
check("the socket's stop action goes through the same Stop as POST /stop",
      "await _stop_web_chat(_sid)" in (ast.get_source_segment(_SRC, _stop_if) or "")
      and "job_tag = await _stop_web_chat(session_id)" in _SRC)
_helper = ast.get_source_segment(_SRC, _fn("_stop_web_chat")) or ""
check("Stop leaves _NOI_TIEP_WEB (GitHub fix rounds, follow-up openers) alone", "_NOI_TIEP_WEB" not in _helper)
check("no per-session bookkeeping added to the chat runtime",
      set(vars(chat_runtime.ChatRuntime())) == {"_clients", "_jobs"})
_new = ast.get_source_segment(_SRC, _fn("_start_steer_turn")) + _helper
check("no test-only guards in the new production code", "hasattr(" not in _new and "globals()" not in _new)
for f in ("main.py", "chat_runtime.py", "tien_trinh_nen.py"):
    check(f"no long dashes in {f}", not any(c in (SERVER / f).read_text(encoding="utf-8") for c in "\u2013\u2014"))

print(f"\n{'FAIL' if _FAILS else 'PASS'} ({len(_FAILS)} failed)")
raise SystemExit(1 if _FAILS else 0)
