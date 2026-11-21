"""Verify cancelled turns, delayed continuation races, and Stop paths clear queued work."""
from _paths import SERVER  # noqa: E402,F401
import ast, asyncio, os, sys, tempfile, time, types, uuid

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-stop-state-"))
os.environ.setdefault("BRAINS_DIR", tempfile.mkdtemp(prefix="javis-stop-brains-"))

import chat_runtime, limit_resume, localefmt, luot_dang_chay, nghe_sua, steer_inbox, tien_trinh_nen, turn_context  # noqa: E402
import main  # noqa: E402

_FAILS = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _FAILS.append(name)


_SRC = (SERVER / "main.py").read_text(encoding="utf-8")
_TREE = ast.parse(_SRC)
_find_fn = lambda name: next(n for n in ast.walk(_TREE) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
_RUN_TURN, _START_STEER, _START_FOLLOWUP = _find_fn("run_turn"), _find_fn("_start_steer_turn"), _find_fn("_start_followup_turn")


def _run_extracted_turn(cancel_turn):
    scheduled, frames, noop = [], [], (lambda *_a, **_kw: None)
    async def _send_raw(frame): frames.append(frame)
    async def _anop(*_a, **_kw): return None
    async def _fake_steer(sid, texts, brain, ids, stop_epoch=None): scheduled.append((sid, list(texts), brain, list(ids), stop_epoch))
    async def _do_turn(conv_sid, *_a, **_kw):
        steer_inbox.INBOX.put(conv_sid, "queued follow-up during turn")
        if cancel_turn: raise asyncio.CancelledError()
        return "done"
    ns = dict(
        asyncio=asyncio, sys=sys, time=time, nghe_sua=nghe_sua, localefmt=localefmt, turn_context=turn_context,
        luot_dang_chay=luot_dang_chay, WEB_CHAT_PREFIX="web:", _brain_root=lambda b: b, steer_inbox=steer_inbox,
        cfgmod=types.SimpleNamespace(read_settings=lambda: {"recall": {"enabled": False}}),
        store=types.SimpleNamespace(get_session=lambda _s: None), send_raw=_send_raw, _do_turn=_do_turn,
        _start_steer_turn=_fake_steer, _bao_luot_dai_xong=_anop, _resonance_turn_agent=noop, _session_assistant=lambda *_a: "",
        _resonance_after_turn=noop, _record_quality_shadow=noop, _CHAT_RUNTIME=chat_runtime.ChatRuntime(),
        tien_trinh_nen=types.SimpleNamespace(bo_tag=noop), _CONTEXT_RUNTIME=types.SimpleNamespace(finish=noop, note_error=noop),
        context_runtime=types.SimpleNamespace(bind_trace=noop, reset_trace=noop, event_fields=lambda *_a: {}),
        _engine_outcome_reset=noop, _engine_outcome_exception=noop, _engine_outcome_turn=noop, _engine_outcome_pop=lambda *_a: {},
    )
    exec(compile(ast.Module(body=[_RUN_TURN], type_ignores=[]), "main-run_turn", "exec"), ns)
    asyncio.run(ns["run_turn"]("sid-turn", "hi", "/tmp/b", "chat:sid-turn:t1", None, user_mid=1, user_text="hi"))
    return scheduled, frames


sched_c, frames_c = _run_extracted_turn(cancel_turn=True)
check("cancelled run_turn skips queued steer", sched_c == [] and not steer_inbox.INBOX.running("sid-turn") and any(f.get("type") == "system" for f in frames_c), (sched_c, frames_c))
sched_ok, _ = _run_extracted_turn(cancel_turn=False)
check("completed run_turn schedules unread steer with stop_epoch",
      len(sched_ok) == 1 and sched_ok[0][1] == ["queued follow-up during turn"] and sched_ok[0][4] == 0, sched_ok)


def _build_runners(rt, *, real_sleep=True):
    appended, started, depths = [], [], {}
    async def _fake_run(sid, msg, brain, tag, *_a, **_kw): started.append((sid, msg, brain, tag))
    async def _anop(*_a, **_kw): return None
    class _FastAsyncio:
        CancelledError, current_task, create_task = asyncio.CancelledError, staticmethod(asyncio.current_task), staticmethod(asyncio.create_task)
        @staticmethod
        async def sleep(_d): await asyncio.sleep(0.005)
    ns = dict(
        asyncio=asyncio if real_sleep else _FastAsyncio, uuid=uuid, _CHAT_RUNTIME=rt, _DO_SAU_NOI_TIEP=depths,
        _CONTEXT_RUNTIME=types.SimpleNamespace(start_turn=lambda *_a: types.SimpleNamespace(task_id="t", step_id="s")),
        run_turn=_fake_run, steer_inbox=steer_inbox, push_to_chat=_anop,
        store=types.SimpleNamespace(append_message=lambda sid, role, txt: appended.append((sid, role, txt))),
    )
    exec(compile(ast.Module(body=[_START_STEER, _START_FOLLOWUP], type_ignores=[]), "main-cont", "exec"), ns)
    return ns, appended, started


def _job(rt, sid, tag):
    ev = asyncio.Event()
    t = asyncio.create_task(ev.wait())
    rt.register_job(sid, t, tag)
    return ev, t


async def _check_continuation_races():
    rt = chat_runtime.ChatRuntime()
    ns, appended, started = _build_runners(rt, real_sleep=True)
    _, job = _job(rt, "s-wait", "chat:s-wait:1")
    t_s = asyncio.create_task(ns["_start_steer_turn"]("s-wait", ["later"], "brain", [1], stop_epoch=rt.stop_epoch("s-wait")))
    t_f = asyncio.create_task(ns["_start_followup_turn"]("s-wait", "follow up", "brain", 1, stop_epoch=rt.stop_epoch("s-wait")))
    await asyncio.sleep(0.02)
    check("waiting continuations tracked before stop", len(rt._waiters.get("s-wait", ())) == 2)
    tag = rt.cancel_session("s-wait")
    await asyncio.gather(job, t_s, t_f, return_exceptions=True)
    check("cancel_session cancels job and waiters", tag == "chat:s-wait:1" and rt.stop_epoch("s-wait") == 1 and not started and not appended and not rt._waiters.get("s-wait"))

    e0 = rt.stop_epoch("s-pre")
    p_s = asyncio.create_task(ns["_start_steer_turn"]("s-pre", ["stale"], "brain", [], stop_epoch=e0))
    p_f = asyncio.create_task(ns["_start_followup_turn"]("s-pre", "stale follow", "brain", 0, stop_epoch=e0))
    check("cancel_session without job still bumps epoch", rt.cancel_session("s-pre") is None and rt.stop_epoch("s-pre") == 1)
    await asyncio.gather(p_s, p_f)
    check("pre-start stop prevents continuation launch", not started and not appended and not rt._waiters.get("s-pre"))

    _, job_m = _job(rt, "s-match", "chat:s-match:9")
    m_s = asyncio.create_task(ns["_start_steer_turn"]("s-match", ["m1"], "brain", [], stop_epoch=rt.stop_epoch("s-match")))
    m_f = asyncio.create_task(ns["_start_followup_turn"]("s-match", "m2", "brain", 1, stop_epoch=rt.stop_epoch("s-match")))
    await asyncio.sleep(0.02)
    tags = rt.cancel_matching("chat:s-match:")
    await asyncio.gather(job_m, m_s, m_f, return_exceptions=True)
    check("cancel_matching stops job and waiters", tags == ["chat:s-match:9"] and rt.stop_epoch("s-match") == 1 and not started and not appended and not rt._waiters.get("s-match"))

    ns_fast, app_ok, start_ok = _build_runners(rt, real_sleep=False)
    gate_ok, job_ok = _job(rt, "s-wait", "chat:s-wait:2")
    ok_f = asyncio.create_task(ns_fast["_start_followup_turn"]("s-wait", "run next", "brain", 1, stop_epoch=rt.stop_epoch("s-wait")))
    await asyncio.sleep(0.02)
    gate_ok.set(); await job_ok; rt.finish_job("s-wait", job_ok); await ok_f
    await asyncio.create_task(ns_fast["_start_steer_turn"]("s-wait", ["steer next"], "brain", [7], stop_epoch=rt.stop_epoch("s-wait")))
    while rt.get_job("s-wait"):
        await rt.get_job("s-wait").task; rt.finish_job("s-wait", rt.get_job("s-wait").task)
    check("followup and steer queued after prior stop run once idle",
          app_ok == [("s-wait", "user", "run next")] and len(start_ok) == 2 and "steer next" in start_ok[1][1])
    rt_cap = chat_runtime.ChatRuntime()
    for i in range(2005): rt_cap.register_job(f"cap-{i}", job_ok, f"chat:cap-{i}:1")
    check("last_tags capped at 2000 entries", len(rt_cap._last_tags) == 2000 and "cap-0" not in rt_cap._last_tags)


async def _check_stop_endpoints():
    orig_rt, orig_cancel = main._CHAT_RUNTIME, main.cancel_all
    rt = chat_runtime.ChatRuntime()
    main._CHAT_RUNTIME, main.cancel_all = rt, (lambda tag=None: 0)
    try:
        ns, appended, started = _build_runners(rt, real_sleep=True)
        for sid, tag, body in (("s-rest", "chat:s-rest:1", {"session_id": "s-rest"}), ("s-tag", "chat:s-tag:2", {"tag": "chat:s-tag:"})):
            _, job = _job(rt, sid, tag)
            waiter = asyncio.create_task(ns["_start_followup_turn"](sid, "abort", "brain", 1, stop_epoch=rt.stop_epoch(sid)))
            tok = steer_inbox.INBOX.open(sid, tag); steer_inbox.INBOX.put(sid, "pending steer")
            limit_resume.REGISTRY.schedule(sid, time.time() + 10, lambda *_a: None, auto_default=True)
            tien_trinh_nen.dat_loi_dan(f"web:{sid}", "send summary")
            await asyncio.sleep(0.02)
            res = await main.stop(body)
            await asyncio.gather(job, waiter, return_exceptions=True)
            check(f"REST /stop {list(body)[0]} clears job, waiter, continuations",
                  res == {"ok": True, "cancelled": 1} and steer_inbox.INBOX.close(sid, tag, tok) == []
                  and limit_resume.REGISTRY.get(sid) is None and tien_trinh_nen._lay_loi_dan(f"web:{sid}") == "" and not started and not appended)

        for idx, mk_payload in enumerate((lambda s: {"tag": f"chat:{s[:12]}:oldhex"}, lambda s: {"tag": f"chat:{s[:12]}:"}, lambda _s: {})):
            sid = f"session-orphan-{idx}-abcdefghij"
            gate_fin, job_fin = _job(rt, sid, f"chat:{sid[:12]}:oldhex")
            waiter_w = asyncio.create_task(ns["_start_followup_turn"](sid, "orphan", "brain", 1, stop_epoch=rt.stop_epoch(sid)))
            await asyncio.sleep(0.02)
            gate_fin.set(); await job_fin; rt.finish_job(sid, job_fin)
            limit_resume.REGISTRY.schedule(sid, time.time() + 10, lambda *_a: None, auto_default=True)
            tien_trinh_nen.dat_loi_dan(f"web:{sid}", "orphan follow")
            check(f"unrelated tag skips orphan waiter ({idx})", rt.sessions_matching("chat:unrelated:") == [])
            res_o = await main.stop(mk_payload(sid))
            await asyncio.gather(waiter_w, return_exceptions=True)
            check(f"REST /stop orphan waiter ({idx}) cancels and reports >= 1",
                  res_o["ok"] and res_o["cancelled"] >= 1 and waiter_w.done() and rt.stop_epoch(sid) == 1
                  and limit_resume.REGISTRY.get(sid) is None and tien_trinh_nen._lay_loi_dan(f"web:{sid}") == "" and not started and not appended, res_o)

        noi_assign = next(n for n in ast.walk(_TREE) if isinstance(n, ast.Assign) and len(n.targets) == 1
                          and isinstance(n.targets[0], ast.Subscript) and getattr(n.targets[0].value, "id", None) == "_NOI_TIEP_WEB")
        exec(compile(ast.Module(body=[noi_assign], type_ignores=[]), "main-noi", "exec"),
             dict(_NOI_TIEP_WEB=main._NOI_TIEP_WEB, conv_sid="s-cb", brain="brain", _CHAT_RUNTIME=rt, _start_followup_turn=ns["_start_followup_turn"]))
        cb = main._NOI_TIEP_WEB["s-cb"]
        await main.stop({"session_id": "s-cb"})
        await asyncio.create_task(cb("late after stop", 1))
        check("_NOI_TIEP_WEB cleared on Stop and pre-stop callback ignores post-stop run",
              "s-cb" not in main._NOI_TIEP_WEB and rt.stop_epoch("s-cb") == 1 and not started and not appended)
    finally:
        main._CHAT_RUNTIME, main.cancel_all = orig_rt, orig_cancel


async def _check_channel_stop():
    orig_cancel, tg_cancelled = main.cancel_all, []
    main.cancel_all = lambda tag=None: (tg_cancelled.append(tag), 1)[1]
    try:
        tien_trinh_nen.dat_loi_dan("12345", "tg"); tien_trinh_nen.dat_loi_dan("zalo:z1", "zalo")
        tien_trinh_nen._VIEC["j-tg"] = {"id": "j-tg", "pgid": 999993, "chat_id": "12345", "trang_thai": "run", "noi_tiep": True, "sau_khi_xong": "tg", "bat_dau": time.time()}
        tien_trinh_nen._VIEC["j-zalo"] = {"id": "j-zalo", "pgid": 999994, "chat_id": "zalo:z1", "trang_thai": "run", "noi_tiep": True, "sau_khi_xong": "zalo", "bat_dau": time.time()}
        await main._tg_command("stop", "", chat="12345"); await main._zalo_command("stop", "", chat="z1")
        check("_tg_command and _zalo_command stop clear channel follow-ups",
              tg_cancelled == ["telegram:12345", "telegram:zalo:z1"] and tien_trinh_nen._lay_loi_dan("12345") == ""
              and tien_trinh_nen._lay_loi_dan("zalo:z1") == "" and not tien_trinh_nen._VIEC["j-tg"]["noi_tiep"] and not tien_trinh_nen._VIEC["j-zalo"]["noi_tiep"])
    finally:
        main.cancel_all = orig_cancel


asyncio.run(_check_continuation_races())
asyncio.run(_check_stop_endpoints())
with tien_trinh_nen._KHOA:
    tien_trinh_nen._LOI_DAN.clear(); tien_trinh_nen._VIEC.clear()
tien_trinh_nen.dat_loi_dan("web:s-stop", "send summary")
tien_trinh_nen._VIEC["j-web"] = {"id": "j-web", "pgid": 999991, "chat_id": "web:s-stop", "trang_thai": "run", "noi_tiep": True, "sau_khi_xong": "encode", "bat_dau": time.time()}
tien_trinh_nen._VIEC["j-other"] = {"id": "j-other", "pgid": 999992, "chat_id": "web:other", "trang_thai": "run", "noi_tiep": True, "sau_khi_xong": "keep", "bat_dau": time.time()}
tien_trinh_nen._VIEC["j-done"] = {"id": "j-done", "pgid": 999995, "chat_id": "web:s-stop", "trang_thai": "xong", "noi_tiep": True, "sau_khi_xong": "done", "bat_dau": time.time()}
cleared_ok = tien_trinh_nen.clear_followup_instruction("web:s-stop")
tien_trinh_nen._VIEC.clear(); tien_trinh_nen._nap()
check("clear_followup_instruction clears _LOI_DAN and active _VIEC and persists",
      cleared_ok and not tien_trinh_nen.clear_followup_instruction("web:s-stop") and not tien_trinh_nen.clear_followup_instruction("")
      and tien_trinh_nen._lay_loi_dan("web:s-stop") == "" and not tien_trinh_nen._VIEC["j-web"]["noi_tiep"]
      and tien_trinh_nen._VIEC["j-web"]["sau_khi_xong"] == "" and tien_trinh_nen._VIEC["j-done"]["noi_tiep"]
      and tien_trinh_nen._VIEC["j-other"]["sau_khi_xong"] == "keep")
asyncio.run(_check_channel_stop())
stop_if = next(n for n in ast.walk(_TREE) if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
               and getattr(n.test.left, "id", None) == "action" and any(isinstance(c, ast.Constant) and c.value == "stop" for c in n.test.comparators))
check("action == 'stop' calls _clear_session_continuations", "_clear_session_continuations(_sid)" in (ast.get_source_segment(_SRC, stop_if) or ""))
print(f"\n{'FAIL' if _FAILS else 'OK'}: {len(_FAILS)} failed")
raise SystemExit(1 if _FAILS else 0)
