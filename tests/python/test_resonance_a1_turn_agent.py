"""Resonance A1: host gắn agent của phiên vào ngữ cảnh lượt (`turn_context`), không lấy từ lời model.

    python tests/run.py resonance_a1_turn_agent -v

Kiểm ba tầng, không gọi model:
1. `turn_context.make` có thêm `session_id`, `message_id`, `agent`; bản đọc ra là bản sao sâu một bậc.
2. `main._resonance_turn_agent` phân giải từ dòng phiên đã lưu và sổ đăng ký: chat thường, agent chưa đăng
   ký, phiên của brain khác, phiên quy trình đều ra None; file agent mất thì sổ chuyển `missing`; chưa có kho
   thì không tạo kho chỉ để đọc.
3. Thân THẬT của `run_turn` (trích từ main.py) với kho phiên thật: `_do_turn` giả đọc `turn_context.current()`
   như tool sẽ đọc. Hai lượt của hai agent chạy xen nhau thì mỗi lượt chỉ thấy agent của mình.
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

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a1t-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import main  # noqa: E402
import luot_dang_chay  # noqa: E402
import localefmt  # noqa: E402
import nghe_sua  # noqa: E402
import resonance_store as RS  # noqa: E402
import sessions  # noqa: E402
import turn_context  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


# ───────────────────────────── 1. turn_context ─────────────────────────────
t = turn_context.make("dashboard", chat_id="s1", la_chu=True)
check("make: khoá mới có mặc định rỗng", t["session_id"] == "" and t["message_id"] == 0 and t["agent"] is None)
check("make: khoá cũ giữ nguyên", t["kenh"] == "dashboard" and t["la_chu"] is True and t["chat_id"] == "s1")
t = turn_context.make("dashboard", session_id=" s1 ", message_id="7",
                      agent={"key": "ag_x", "slug": "viet-bai", "config_version": 3, "la": "rác"})
check("make: chuẩn hoá phiên, id tin và agent (bỏ khoá lạ)",
      t["session_id"] == "s1" and t["message_id"] == 7
      and t["agent"] == {"key": "ag_x", "slug": "viet-bai", "config_version": 3}, t)
check("make: agent không có key thì là None", turn_context.make("x", agent={"slug": "a"})["agent"] is None)
check("make: id tin hỏng thì 0", turn_context.make("x", message_id="abc")["message_id"] == 0)
tok = turn_context.bind(t)
cur = turn_context.current()
cur["agent"]["key"] = "ag_gia"
check("current(): sửa agent của bản đọc không đổi lượt", turn_context.current()["agent"]["key"] == "ag_x")
key = turn_context.issue_key()
r1 = turn_context.resolve_key(key)
r1["agent"]["config_version"] = 99
check("resolve_key(): bản sao sâu, không sửa được bản trong bảng khoá",
      turn_context.resolve_key(key)["agent"]["config_version"] == 3)
turn_context.reset(tok)
check("hết lượt: khoá chết", turn_context.resolve_key(key) is None and turn_context.current() is None)

# ───────────────────────────── 2. _resonance_turn_agent ─────────────────────────────
BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a1t-")).resolve())
OTHER = str(Path(tempfile.mkdtemp(prefix="brain-a1t-b-")).resolve())
(Path(BRAIN) / "agents").mkdir()
for s in ("viet-bai", "kiem-tra", "chua-dk"):
    (Path(BRAIN) / "agents" / f"{s}.md").write_text(f"---\nname: {s}\n---\nAgent {s}\n", encoding="utf-8")
DB = Path(_STATE) / "resonance.sqlite3"


def row(channel, brain=BRAIN):
    # Mỗi ca dùng id phiên riêng: phiên được ghim vào mã agent ở lần phân giải đầu (review PR #590, P1-1).
    return lambda sid: {"id": sid, "channel": channel, "brain": brain, "created_at": time.time()}


check("chưa có kho: agent None", main._resonance_turn_agent("s1", BRAIN, row("agent:viet-bai")) is None)
check("chưa có kho: không tạo resonance.sqlite3 chỉ để đọc", not DB.exists())

OWNER = RS.Principal("owner", "owner", main._brain_key(BRAIN))
gs = main._resonance_store()
A = gs.agent_set_enabled(OWNER, "viet-bai", True)
B = gs.agent_set_enabled(OWNER, "kiem-tra", True)

got = main._resonance_turn_agent("s2", BRAIN, row("agent:viet-bai"))
check("phiên agent đã đăng ký: đúng mã, slug, version",
      got == {"key": A["agent_key"], "slug": "viet-bai", "config_version": A["config_version"]}, got)
check("chat thường: None", main._resonance_turn_agent("s3", BRAIN, row("web")) is None)
check("phiên không có dòng: None", main._resonance_turn_agent("s4", BRAIN, lambda sid: None) is None)
check("phiên quy trình cùng slug: None", main._resonance_turn_agent("s5", BRAIN, row("workflow:viet-bai")) is None)
check("agent có file nhưng chưa đăng ký: None", main._resonance_turn_agent("s6", BRAIN, row("agent:chua-dk")) is None)
check("phiên lưu ở brain khác: None",
      main._resonance_turn_agent("s7", BRAIN, row("agent:viet-bai", brain=OTHER)) is None)
check("lượt ở brain khác với phiên: None",
      main._resonance_turn_agent("s8", OTHER, row("agent:viet-bai")) is None)


def _boom(sid):
    raise RuntimeError("kho phiên hỏng")


check("đọc phiên lỗi: None, không làm hỏng lượt", main._resonance_turn_agent("s9", BRAIN, _boom) is None)
gs.agent_set_enabled(OWNER, "viet-bai", False)
off = main._resonance_turn_agent("s10", BRAIN, row("agent:viet-bai"))
check("agent đang tắt vẫn có danh tính (cổng ở tool nói lý do), version mới",
      off is not None and off["config_version"] == A["config_version"] + 1, off)
gs.agent_set_enabled(OWNER, "viet-bai", True)
(Path(BRAIN) / "agents" / "kiem-tra.md").unlink()
check("file agent mất: None", main._resonance_turn_agent("s11", BRAIN, row("agent:kiem-tra")) is None)
check("file agent mất: sổ chuyển missing", gs.agent(main._brain_key(BRAIN), "kiem-tra")["status"] == "missing")
(Path(BRAIN) / "agents" / "kiem-tra.md").write_text("---\nname: kiem-tra\n---\nkhác\n", encoding="utf-8")
check("file xuất hiện lại: vẫn None tới khi chủ dự án xác nhận",
      main._resonance_turn_agent("s12", BRAIN, row("agent:kiem-tra")) is None)
gs.agent_confirm(OWNER, B["agent_key"], True)
B2 = main._resonance_turn_agent("s13", BRAIN, row("agent:kiem-tra"))
check("xác nhận đúng trợ lý cũ: giữ mã", B2 is not None and B2["key"] == B["agent_key"], B2)

# ───────────────────────────── 3. thân thật của run_turn ─────────────────────────────
session_store = sessions.SessionStore(str(Path(_STATE) / "sessions.db"))
SID_A = session_store.create_session(brain=BRAIN, engine="test", model="test", channel="agent:viet-bai")
SID_B = session_store.create_session(brain=BRAIN, engine="test", model="test", channel="agent:kiem-tra")
SID_N = session_store.create_session(brain=BRAIN, engine="test", model="test")
MID_A = session_store.append_message(SID_A, "user", "Viết giúp anh bài giới thiệu")
MID_B = session_store.append_message(SID_B, "user", "Kiểm giúp anh bài này")
MID_N = session_store.append_message(SID_N, "user", "Mấy giờ rồi em?")

seen = {}


async def _noop(*a, **kw):
    pass


async def fake_do_turn(conv_sid, message, *a, user_mid=0, **kw):
    # Như tool gọi giữa lượt: đọc ngữ cảnh nhiều lần, xen với lượt kia.
    reads = []
    for _ in range(3):
        reads.append(turn_context.current())
        await asyncio.sleep(0.01)
    seen[conv_sid] = reads
    return "xong"


_ns = dict(asyncio=asyncio, sys=sys, time=time, uuid=uuid, nghe_sua=nghe_sua, localefmt=localefmt,
           turn_context=turn_context, store=session_store, send_raw=_noop, _persist_turn=_noop,
           _CHAT_RUNTIME=types.SimpleNamespace(finish_job=lambda *a: None),
           context_runtime=types.SimpleNamespace(bind_trace=lambda *a: None, reset_trace=lambda *a: None,
                                                 event_fields=lambda *a: {}),
           _CONTEXT_RUNTIME=types.SimpleNamespace(finish=lambda *a: None, note_error=lambda *a: None),
           luot_dang_chay=luot_dang_chay, WEB_CHAT_PREFIX="web:", _brain_root=main._brain_root,
           _do_turn=fake_do_turn, _resonance_after_turn=lambda *a: None, _record_quality_shadow=lambda *a: None,
           _resonance_turn_agent=main._resonance_turn_agent,
           tien_trinh_nen=types.SimpleNamespace(bo_tag=lambda *a: None),
           _engine_outcome_reset=lambda *a: None, _engine_outcome_exception=lambda *a: None,
           _engine_outcome_turn=lambda *a: None, _engine_outcome_pop=lambda *a: {})
_tree = ast.parse((SERVER / "main.py").read_text(encoding="utf-8"))
_rt = next(n for n in ast.walk(_tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_turn")
exec(compile(ast.Module(body=[_rt], type_ignores=[]), "main-run_turn", "exec"), _ns)


async def _run():
    await asyncio.gather(_ns["run_turn"](SID_A, "Viết giúp anh bài giới thiệu", BRAIN, "ta", None, user_mid=MID_A),
                         _ns["run_turn"](SID_B, "Kiểm giúp anh bài này", BRAIN, "tb", None, user_mid=MID_B),
                         _ns["run_turn"](SID_N, "Mấy giờ rồi em?", BRAIN, "tn", None, user_mid=MID_N))


asyncio.run(_run())
ra, rb, rn = seen.get(SID_A) or [None], seen.get(SID_B) or [None], seen.get(SID_N) or [None]
check("lượt agent A: mọi lần đọc đều là agent A, đúng phiên và id tin",
      all(x and x["agent"] and x["agent"]["key"] == A["agent_key"] and x["session_id"] == SID_A
          and x["message_id"] == MID_A for x in ra), ra[0])
check("lượt agent B chạy xen: chỉ thấy agent B",
      all(x and x["agent"] and x["agent"]["key"] == B["agent_key"] and x["message_id"] == MID_B for x in rb), rb[0])
check("lượt chat thường chạy xen: agent None, vẫn có phiên và id tin",
      all(x and x["agent"] is None and x["session_id"] == SID_N and x["message_id"] == MID_N for x in rn), rn[0])
check("lượt dashboard vẫn là của chủ dự án", all(x and x["la_chu"] and x["kenh"] == "dashboard" for x in ra + rn))
check("hết lượt: không còn ngữ cảnh", turn_context.current() is None)


# ───────────── vòng đời xoá, tạo lại, restart, đổi tên tay trên PHIÊN ĐÃ LƯU (review PR #590, P1-1) ─────────────
def turn_agent(sid, mid):
    seen.pop(sid, None)
    asyncio.run(_ns["run_turn"](sid, "tin", BRAIN, "tx", None, user_mid=mid))
    return (seen.get(sid) or [None])[0]["agent"]


AF = Path(BRAIN) / "agents" / "viet-bai.md"
gs.agent_retire(OWNER, "viet-bai")                       # xoá qua host
AF.unlink()
time.sleep(0.01)
AF.write_text("---\nname: viet-bai\n---\nTrợ lý khác, cùng tên file\n", encoding="utf-8")
A2 = gs.agent_set_enabled(OWNER, "viet-bai", True)
check("tạo lại cùng slug: mã mới", A2["agent_key"] != A["agent_key"])
check("phiên cũ của A (đã lưu, đã có lượt) KHÔNG nhận mã mới qua run_turn", turn_agent(SID_A, MID_A) is None)
SID_A2 = session_store.create_session(brain=BRAIN, engine="test", model="test", channel="agent:viet-bai")
MID_A2 = session_store.append_message(SID_A2, "user", "Chào trợ lý mới")
ag = turn_agent(SID_A2, MID_A2)
check("phiên mới của trợ lý mới: nhận đúng mã mới", ag and ag["key"] == A2["agent_key"], ag)
main._RESONANCE_STORE = None                             # như khởi động lại: mở kho mới từ đĩa
check("restart: phiên cũ vẫn không nhận mã mới", turn_agent(SID_A, MID_A) is None)
ag = turn_agent(SID_A2, MID_A2)
check("restart: phiên mới vẫn đúng mã mới", ag and ag["key"] == A2["agent_key"], ag)
AF.rename(AF.with_name("viet-bai-moi.md"))               # đổi tên tay
check("đổi tên tay: phiên mất danh tính", turn_agent(SID_A2, MID_A2) is None)
check("đổi tên tay: mã chuyển missing", main._resonance_store().agent_by_key(
    main._brain_key(BRAIN), A2["agent_key"])["status"] == "missing")
AF.with_name("viet-bai-moi.md").rename(AF)
check("đổi tên lại như cũ: vẫn không tự lấy lại quyền", turn_agent(SID_A2, MID_A2) is None)
main._resonance_store().agent_confirm(OWNER, A2["agent_key"], True)
ag = turn_agent(SID_A2, MID_A2)
check("chủ dự án xác nhận đúng trợ lý: phiên có lại danh tính", ag and ag["key"] == A2["agent_key"], ag)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
