"""Resonance M2: id tin và lời người dùng đi đúng qua các nhánh giọng nói và lượt chạy lại (review PR #567).

    python tests/run.py resonance_mvp_handoff -v

Không chỉ đọc AST: trích NGUYÊN các hàm `run_turn`, `run_voice_turn`, `_start_resumed_turn` từ main.py rồi
chạy chúng với dịch vụ giả (bộ não giọng, _do_turn, runtime). `_do_turn` giả gọi tool javis_goal thật như
bộ não chính sẽ gọi, nên kiểm được sổ lượt và tool nhận đúng id tin, đúng lời người dùng (đã bóc khối ngữ cảnh
giao diện, không kèm ghi chú host), và cùng một tin chỉ tạo một mục tiêu. Cách dựng theo script kiểm độc lập
của ChatGPT ở vòng review 2. Không gọi model, micro hay dịch vụ giọng nói thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import ast
import asyncio
import os
import sys
import tempfile
import time
import types
import uuid
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m2h-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import localefmt  # noqa: E402
import luot_dang_chay  # noqa: E402
import nghe_sua  # noqa: E402
import plugins_host  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import sessions  # noqa: E402
import voice_brain  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-h-")).resolve())
(Path(BRAIN) / "Javis").mkdir(parents=True)
(Path(BRAIN) / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
_, routes = plugins_host.plugin_tools("full", BRAIN, scope_vault=False)
call = routes["javis_goal"]["call"]
P = RS.Principal("agent", "javis", BRAIN)
goals = RS.GoalStore()

ORIGINAL = "Theo dõi hồ sơ đến ngày 11/10/2026, cần đủ 10 hồ sơ."
PROPOSAL = {"understanding": "Theo dõi hồ sơ", "stage": "delivery", "relevant_quote": "Theo dõi hồ sơ",
            "criteria": [{"description": "Anh xác nhận báo cáo", "evaluator": "human_confirmation"}],
            "horizon": {"kind": "deadline", "at_iso": "2026-10-11T23:00:00+07:00", "from_user": True,
                        "quote": "đến ngày 11/10/2026"},
            "targets": [{"text": "10 hồ sơ", "quote": "cần đủ 10 hồ sơ"}]}

session_store = sessions.SessionStore(str(Path(_STATE) / "sessions.db"))
SID = session_store.get_or_create(None, brain=BRAIN, engine="test", model="test")
PROMPT = "[NGỮ CẢNH GIAO DIỆN: trang=chat]\n\n" + ORIGINAL
MID = session_store.append_message(SID, "user", PROMPT)

seen, jobs, tool_outs = [], [], []


async def _noop(*a, **kw):
    pass


async def fake_do_turn(conv_sid, message, *a, user_mid=0, user_text=None, **kw):
    live = luot_dang_chay.doan_luot(BRAIN) or {}
    seen.append({"live_mid": live.get("msg_id"), "live_text": live.get("user_text"), "mid": user_mid,
                 "text": user_text, "message": message})
    tool_outs.append(await call({"op": "create", **PROPOSAL}))
    return "xong"


async def _silent_stream(*a):
    yield "JAVIS_BO_QUA: tạp âm"


async def _brain_ok(*a):
    return types.SimpleNamespace(stream=_silent_stream, provider="test", model="test")


async def _brain_broken(*a):
    raise RuntimeError("giả lập bộ não giọng không dùng được")


proxy = types.SimpleNamespace(**vars(voice_brain))
proxy.get_brain = _brain_ok
proxy.xoa_loi_lan_nhanh = lambda *a: None
proxy.ghi_loi_lan_nhanh = lambda *a: None
runtime = types.SimpleNamespace(finish_job=lambda *a: None, get_job=lambda *a: None,
                                register_job=lambda sid, task, *a, **kw: jobs.append(task))
import turn_context  # noqa: E402  - run_turn gắn danh tính lượt cho hook tool (0.85.8)
namespace = dict(asyncio=asyncio, sys=sys, time=time, uuid=uuid, voice_brain=proxy, nghe_sua=nghe_sua, turn_context=turn_context,
                 localefmt=localefmt, store=session_store, send_raw=_noop, _persist_turn=_noop,
                 _CHAT_RUNTIME=runtime,
                 context_runtime=types.SimpleNamespace(bind_trace=lambda *a: None, reset_trace=lambda *a: None,
                                                       event_fields=lambda *a: {}),
                 _CONTEXT_RUNTIME=types.SimpleNamespace(finish=lambda *a: None, note_error=lambda *a: None,
                                                        start_turn=lambda *a: None),
                 luot_dang_chay=luot_dang_chay, WEB_CHAT_PREFIX="web:", _brain_root=lambda b: b,
                 _do_turn=fake_do_turn, _resonance_after_turn=lambda *a: None,
                 _resonance_turn_agent=lambda *a: None,  # A1: test riêng ở test_resonance_a1_turn_agent
                 # Kết cục engine gửi kèm turn_done (pilot lần 4): test riêng ở test_turn_engine_status.
                 _engine_outcome_reset=lambda *a: None, _engine_outcome_exception=lambda *a: None,
                 _engine_outcome_pop=lambda *a: {}, _engine_outcome_turn=lambda *a: None,
                 _record_quality_shadow=lambda *a: None, tien_trinh_nen=types.SimpleNamespace(bo_tag=lambda *a: None))
_tree = ast.parse((SERVER / "main.py").read_text(encoding="utf-8"))
_nodes = [next(n for n in ast.walk(_tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
          for name in ("run_turn", "run_voice_turn", "_start_resumed_turn")]
exec(compile(ast.Module(body=_nodes, type_ignores=[]), "main-nested-handlers", "exec"), namespace)


def _ok(i, label):
    s = seen[i] if len(seen) > i else {}
    check(f"{label}: sổ lượt và _do_turn nhận đúng id tin gốc",
          s.get("live_mid") == MID and s.get("mid") == MID)
    check(f"{label}: lời người dùng đúng nguyên văn, đã bóc khối ngữ cảnh giao diện, không kèm ghi chú host",
          s.get("live_text") == ORIGINAL and s.get("text") == ORIGINAL)
    check(f"{label}: tool javis_goal chạy được trong lượt (không bị từ chối vì thiếu id)",
          len(tool_outs) > i and not tool_outs[i].startswith("ERROR"))


async def _run():
    # Bộ não giọng bảo bỏ qua (giữ câu gốc): chuyển bộ não chính kèm ghi chú câu nghe.
    await namespace["run_voice_turn"](SID, PROMPT, BRAIN, "tag", None, {}, user_mid=MID)
    _ok(0, "giọng nói, giữ câu gốc")
    check("giọng nói, giữ câu gốc: prompt gửi bộ não chính CÓ ghi chú câu nghe, nhưng lời căn cứ thì không",
          len(seen) > 0 and voice_brain.GHI_CHU_CAU_NGHE in seen[0]["message"]
          and voice_brain.GHI_CHU_CAU_NGHE not in seen[0]["text"])
    # Bộ não giọng hỏng: rơi về bộ não chính.
    proxy.get_brain = _brain_broken
    await namespace["run_voice_turn"](SID, PROMPT, BRAIN, "tag", None, {}, user_mid=MID)
    _ok(1, "giọng nói, rơi về bộ não chính")
    # Chạy lại sau hạn mức với id và lời của lượt gốc.
    await namespace["_start_resumed_turn"](SID, PROMPT, BRAIN, 1, "hết hạn mức", user_mid=MID, user_text=ORIGINAL)
    await asyncio.gather(*jobs)
    _ok(2, "chạy lại sau hạn mức")
    check("ba lượt trên cùng một tin chỉ tạo MỘT mục tiêu",
          len(goals.list_open(P)) == 1 and goals.find_by_key(P, R.message_ref(SID, MID)) is not None)
    # Lượt không có id (kênh chưa hỗ trợ, hay chữ do host tự mở): tool từ chối, không tạo gì.
    await namespace["run_turn"](SID, "Theo dõi hồ sơ giúp anh", BRAIN, "tag", None)
    check("run_turn không có id tin: tool từ chối, không tạo mục tiêu",
          tool_outs[-1].startswith("ERROR") and len(goals.list_open(P)) == 1)


try:
    asyncio.run(_run())
finally:
    session_store._conn.close()

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
