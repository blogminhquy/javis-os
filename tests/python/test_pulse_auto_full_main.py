"""Auto toàn quyền (2026-11-14), phần nối ở main.py.

    python tests/run.py pulse_auto_full_main -v

- `_pulse_tool_scan`: chat riêng của trợ lý chạy lượt có công cụ; nhóm thì không; JAVIS_PULSE_TOOLS=0 tắt hẳn.
- `_pulse_scan_context`: giờ của chủ (thứ, ngày, múi giờ), bộ nhớ về chủ, nhật ký hội thoại hôm nay, chat riêng gần đây
  (đánh dấu tin chủ động và phản hồi của chủ), mốc đang chờ.
- `_pulse_post`: nhắc nhở vào nhóm Nhắc lịch (khẩn), gợi ý vào nhóm Gợi ý của trợ lý (đáng chú ý); tin không loại giữ đường
  cũ; loại tin được giữ trên tin.
- `_pulse_engine_for`: lượt có công cụ chạy trong danh tính lượt `pulse` (việc nền chủ cho phép), báo về chat riêng.

Không model nào được gọi: chốt chặn làm test DỪNG NGAY nếu có đường nào dựng engine thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-auto-main-")
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
os.environ.pop("JAVIS_PULSE_TOOLS", None)
BR = Path(tempfile.mkdtemp(prefix="javis-auto-main-brain-"))
(BR / "agents").mkdir()
(BR / "agents" / "lan.md").write_text("---\nname: Lan\nrole: Trợ lý\n---\nBạn là Lan.\n", encoding="utf-8", newline="\n")

import main  # noqa: E402
import agent_pulse as AP  # noqa: E402
import resonance_store as RS  # noqa: E402
import turn_context  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class RealEngineUsed(AssertionError):
    pass


def _no_real_engine(*a, **k):
    raise RealEngineUsed("test tried to build a REAL engine")


main.team_engine.build = _no_real_engine
main.claude_engine = _no_real_engine
main.CodexCLI = _no_real_engine

rs = main._resonance_store()
BK = main._brain_key(str(BR))
lan = rs.agent_set_enabled(RS.Principal("owner", "owner", BK), "lan", True)
KEY = lan["agent_key"]
DM = f"dm:{KEY}"
ss = main.get_store()

# ═════ lượt có công cụ ở đâu ═════
check("chat riêng của trợ lý: lượt có công cụ", main._pulse_tool_scan(KEY, DM) is True)
check("nhóm: lượt chỉ chữ", main._pulse_tool_scan(KEY, "team:t1") is False)
check("chat riêng của trợ lý khác: không", main._pulse_tool_scan(KEY, "dm:khac") is False)
os.environ["JAVIS_PULSE_TOOLS"] = "0"
check("JAVIS_PULSE_TOOLS=0: tắt lượt có công cụ", main._pulse_tool_scan(KEY, DM) is False)
os.environ.pop("JAVIS_PULSE_TOOLS", None)

# ═════ khối ngữ cảnh ═════
mem = main._brain_memory_dir(BK)
(mem / "MEMORY.md").write_text("# Bộ nhớ\n- [Chạy bộ](facts/chay-bo.md) - chủ đăng ký 21 km ở Tràng An\n",
                               encoding="utf-8")
main.log_conversation(BK, "Mai anh chạy 21 km ở Tràng An, xuất phát 5h45", "Dạ, em nhớ rồi")
sid, _slug = main._pulse_dm_session(KEY)
m_user = ss.append_message(sid, "user", "Nhắc anh lấy BIB nhé")
m_said = ss.append_message(sid, "assistant", "Anh ơi, quầy BIB mở 9h-20h hôm nay.")
AP.record_proactive(rs, KEY, DM, sid, m_said)
ss.set_dm_reaction(sid, m_said, value="love", nonce="auto-love-1", agent_key=KEY)
AP.add_followups(rs, KEY, DM, [{"at": time.time() + 5 * 3600, "note": "Kiểm bãi gửi xe"}], at=time.time())
block = main._pulse_scan_context(KEY, DM, time.time())
check("ngữ cảnh: giờ của chủ có thứ, ngày và múi giờ", "## Giờ hiện tại của chủ" in block
      and main.localefmt.ten_tz() in block and any(w in block for w in main._PULSE_WEEKDAYS), block[:300])
check("ngữ cảnh: bộ nhớ về chủ", "21 km ở Tràng An" in block.split("## Chủ vừa")[0], block[:800])
check("ngữ cảnh: nhật ký hội thoại hôm nay, bọc là dữ liệu", "xuất phát 5h45" in block and "<chat_data>" in block, block)
check("ngữ cảnh: chat riêng gần đây, tin chủ động được đánh dấu", "Nhắc anh lấy BIB" in block
      and "Bạn (tin chủ động): Anh ơi, quầy BIB" in block, block[-900:])
check("ngữ cảnh: phản hồi của chủ trên tin chủ động", "[chủ phản hồi: love]" in block, block[-900:])
check("ngữ cảnh: mốc đang chờ kèm mã để huỷ", "Kiểm bãi gửi xe" in block and "#1" in block, block[-300:])
check("ngữ cảnh: không có ký tự gạch ngang dài do Javis thêm", "\u2014" not in block.replace(
    (mem / "MEMORY.md").read_text(encoding="utf-8"), ""))

# ═════ gửi: nhắc nhở và gợi ý vào đúng nhóm ═════
captured = []
orig_inbox, orig_loop = main._bo_vao_hom_thu, main._pulse_on_loop
main._bo_vao_hom_thu = lambda *a, **kw: {"args": a, **kw}
main._pulse_on_loop = lambda x: captured.append(x)
try:
    r1 = main._pulse_send(KEY, DM, "Anh ơi, mai 5h45 xuất phát.", {"source_ref": "followup:1", "kind": "reminder",
                                                                   "did": ["Thêm lịch"], "decision_id": None})
    r2 = main._pulse_send(KEY, DM, "Anh xem điều khoản referral.", {"source_ref": "pulse:x", "kind": "suggestion",
                                                                     "decision_id": 3})
    r3 = main._pulse_send(KEY, DM, "Tin kiểu cũ", {"source_ref": "goal:g1", "decision_id": 4})
finally:
    main._bo_vao_hom_thu, main._pulse_on_loop = orig_inbox, orig_loop
check("ba tin đều lưu vào chat riêng", all(r and r.get("message_id") for r in (r1, r2, r3)), (r1, r2, r3))
check("nhắc nhở: nhóm Nhắc lịch, mức khẩn", captured[0].get("group") == "reminder" and captured[0].get("level")
      == "urgent", captured[0])
check("gợi ý: nhóm Gợi ý của trợ lý, mức đáng chú ý", captured[1].get("group") == "suggest"
      and captured[1].get("level") == "important", captured[1])
check("tin không loại: giữ đường cũ (nhóm theo nguồn pulse)", captured[2].get("group") == ""
      and captured[2].get("source") == "pulse", captured[2])
meta = (ss.team_message(sid, int(r1["message_id"])) or {}).get("meta") or {}
check("loại tin và việc đã làm giữ trên tin", meta.get("kind") == "reminder" and meta.get("did") == ["Thêm lịch"]
      and meta.get("proactive") is True, meta)

# ═════ danh tính lượt của lượt có công cụ ═════
seen = {}


def fake_team_engine_for(team, key, role):
    async def execute(req):
        seen["turn"] = dict(turn_context.current() or {})
        seen["req"] = req
        return {"text": '{"action": "none"}', "tokens_in": 1, "tokens_out": 1}
    return "fake", "fake-model", execute


orig_tef = main._team_engine_for
main._team_engine_for = fake_team_engine_for
try:
    _p, _m, run = main._pulse_engine_for(KEY, DM, "scan")
    asyncio.run(run({"system": "s", "prompt": "p", "turn_id": "pulse:k:dm:1", "tool_turn": True,
                     "engine_started": None}))
    turn = seen.get("turn") or {}
    check("lượt có công cụ: danh tính lượt `pulse`, báo về chat riêng của trợ lý", turn.get("kenh") == "pulse"
          and turn.get("chat_id") == f"{main.WEB_CHAT_PREFIX}{sid}" and turn.get("session_id") == sid, turn)
    check("lượt có công cụ: khoá làm-đúng-một-lần theo mã lượt", turn.get("job") == "pulse:pulse:k:dm:1", turn)
    check("yêu cầu tới engine giữ tool_turn", seen["req"].get("tool_turn") is True, seen["req"])
    check("hết lượt: danh tính lượt được gỡ", turn_context.current() is None)
    seen.clear()
    asyncio.run(run({"system": "s", "prompt": "p", "turn_id": "pulse:k:dm:2", "engine_started": None}))
    check("lượt chỉ chữ: không gắn danh tính `pulse`", (seen.get("turn") or {}).get("kenh") != "pulse", seen)
finally:
    main._team_engine_for = orig_tef

import team_dispatch  # noqa: E402
check("lượt Auto được coi là việc nền chủ cho phép (giao việc cho nhóm như nhắc hẹn)",
      "pulse" in team_dispatch.SCHEDULED)

if fails:
    print(f"\n{len(fails)} FAIL")
    raise SystemExit(1)
print("\nTẤT CẢ OK")
