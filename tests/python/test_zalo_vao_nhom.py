"""Người mới vào nhóm Zalo (0.84.2, javis-zalo 1.1.0).

    python tests/run.py zalo_vao_nhom      (KHÔNG mạng, MCP và CLI giả)

Chủ repo muốn biết ai vừa vào nhóm và vào lúc nào, rồi để Agent của bot tự chào và tag người đó
theo chỉ dẫn chủ đã viết. Javis chỉ lo phần KHẢ NĂNG, không tự có lời chào nào. javis-zalo 1.1.0
đưa mỗi lượt vào nhóm vào luồng tin dưới dạng tin `group.join` do chính người mới "gửi".

File này canh bốn thứ:
  1. Tin `group.join` thành một sự kiện vào nhóm trong Hộp thư, mang đúng giờ Zalo báo.
  2. Sự kiện tới được Agent ở nhóm đã cho phép DÙ bot chỉ trả lời khi được gọi tên, và câu trả
     lời tag đúng người mới.
  3. Javis không tự chào: Agent không có chỉ dẫn thì trả [IM_LANG] và không gì được gửi.
  4. Không bao giờ thành câu lộ máy trước cả nhóm: nhóm chưa cho phép thì im và không tính là
     một lần gọi bot; quá hạn mức hay engine lỗi cũng im, không "nhắn hơi nhanh", không "trục trặc".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpjoin-")
os.environ["JAVIS_REPLY_POLICY_SHADOW"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import chatbot_tu_dong  # noqa: E402
import conversations  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Javis Vũ", "connector_id": "zalo", "env": {"HOME": "/state/zalo-1"}}
NHOM = "6660001"
NHOM_LA = "6660009"
THREADS = [{"threadId": NHOM, "name": "Zoom | Javis OS", "type": "group"},
           {"threadId": NHOM_LA, "name": "Nhóm lạ", "type": "group"}]
GUI, KHO_TIN, LUOT, CLI = [], [], [], []
TRA_LOI = {"v": "Chào bạn, mừng bạn vào nhóm!"}


def _ms(giay_truoc=0):
    return int((time.time() - giay_truoc) * 1000)


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [dict(t) for t in THREADS]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


async def _cli_gia(conn, command, positionals=None, options=None, timeout=120):
    CLI.append({"command": list(command), "pos": list(positionals or []), "opts": list(options or [])})
    return True, {"message": {"msgId": "m1"}}, ""


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.NHUONG_GIAY = 0.05
zc.THU_LAI_TEN_GIAY = 0
zalo_cli.run_cli = _cli_gia


async def _engine(text, meta, progress, *, channel="", bot=None):
    LUOT.append({"text": text, "meta": dict(meta or {})})
    if isinstance(TRA_LOI["v"], Exception):
        raise TRA_LOI["v"]
    return {"text": TRA_LOI["v"], "files": []}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-zpjoin-"))
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý nhóm"},
                                                  "Ai mới vào nhóm thì chào và hỏi họ đang làm nghề gì."))


def join_msg(uid, ten, mid, thread=NHOM, giay_truoc=2, added_by_me=False):
    """Đúng khuôn javis-zalo 1.1.0 (`joinToBufferMessage`)."""
    t = _ms(giay_truoc)
    return {"id": f"join:{thread}:{uid}:{t}", "threadId": thread, "threadType": "group", "senderId": uid,
            "senderName": ten, "text": f"[{ten} joined the group]", "timestamp": t, "type": "group.join",
            "attachment": None, "replyTo": None,
            "event": {"kind": "join", "groupName": "Zoom | Javis OS", "addedBy": "1" if added_by_me else None,
                      "addedByMe": added_by_me, "time": t}}


# ============================================================
# 1. Chuẩn hoá tin `group.join`
# ============================================================
TEN = {NHOM: {"name": "Zoom | Javis OS", "type": "group"}}
m = join_msg("7001", "Thu Hà", "j0", giay_truoc=60)
ev = zc.chuan_hoa_tin(dict(CONN), m, TEN)
md = (ev or {}).get("metadata", {}).get("member_join")
check("tin group.join thành sự kiện vào nhóm, người GỬI là người mới (để câu trả lời tag họ)",
      ev and ev["chat_type"] == "group" and ev["sender_id"] == "7001" and ev["sender_name"] == "Thu Hà"
      and ev["sender_type"] == "customer" and md is not None, ev)
check("giữ đúng giờ vào Zalo báo (giây)", md and abs(md["time"] - m["timestamp"] / 1000) < 0.01, md)
check("Hộp thư hiện 'vừa vào nhóm', không phải câu tiếng Anh thô của MCP",
      ev and ("vừa vào nhóm" in ev["text"] or "joined the group" in ev["text"]) and "Thu Hà" in ev["text"], ev and ev["text"])
check("tin thường KHÔNG mang cờ vào nhóm",
      "member_join" not in zc.chuan_hoa_tin(dict(CONN), {"threadId": NHOM, "from": "7001", "type": "text", "text": "hi",
                                                          "id": "x", "ts": _ms(1), "threadType": "group"}, TEN)["metadata"])

cau = zalo_personal.cau_vao_nhom(ev)
check("câu cho Agent nói rõ là sự kiện, có tên và giờ vào",
      "KHÔNG phải tin nhắn" in cau and "Thu Hà" in cau and "vừa vào nhóm lúc" in cau, cau)
check("CANARY: câu cho Agent dặn im bằng [IM_LANG] khi chỉ dẫn không nói gì về người mới (Javis không tự chào)",
      chatbot_runtime.IM_LANG in cau, cau)
ev_me = zc.chuan_hoa_tin(dict(CONN), join_msg("7002", "Nam", "j1", added_by_me=True), TEN)
check("người do chính tài khoản này thêm vào thì nói rõ",
      "chính tài khoản này thêm vào" in zalo_personal.cau_vao_nhom(ev_me))

# ============================================================
# 2. Cổng: sự kiện không phải chuyện trò
# ============================================================
cfg = {"audience": "nhom", "groups": [NHOM], "reply_when": "mention"}
check("nhóm đã cho phép, chế độ chỉ khi được gọi tên: sự kiện vào nhóm vẫn tới Agent",
      chatbot_runtime._ly_do_im(cfg, {"chat_type": "group", "chat_id": NHOM, "member_join": True}) == "")
check("còn tin thường không ai gọi tên thì vẫn im như cũ",
      chatbot_runtime._ly_do_im(cfg, {"chat_type": "group", "chat_id": NHOM}) == "khong_goi_ten")
check("nhóm chưa cho phép thì sự kiện vào nhóm cũng không qua",
      chatbot_runtime._ly_do_im(cfg, {"chat_type": "group", "chat_id": NHOM_LA, "member_join": True}) == "nhom_chua_bat")
check("chế độ Tự đánh giá không chấm sự kiện vào nhóm như một câu hỏi",
      not chatbot_tu_dong.can_danh_gia({"reply_when": "auto"}, {"chat_type": "group", "member_join": True}))

# ============================================================
# 3. Chạy thật qua vòng đọc + bot (MCP và CLI giả)
# ============================================================
bid, loi = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "account_ids": ["zalo-1"],
                                     "muc_quyen": "suggest", "reply_when": "mention", "groups": [NHOM]})
check("tạo được bot chỉ trả lời khi được gọi tên", bool(bid) and not loi, loi)


async def doc(cho=0.2):
    await zc.doc_mot_lan(dict(CONN))
    t0 = time.time()
    while zc._VIEC and time.time() - t0 < 6:
        await asyncio.sleep(0.02)
    await asyncio.sleep(cho)


async def chay():
    ok, err = chatbot_runtime.start_bot(bid)
    check("bật bot chạy được", ok, err)

    KHO_TIN.append(join_msg("7101", "Thu Hà", "a1"))
    await doc()
    check("người mới vào nhóm đã cho phép: Agent nhận đúng một lượt", len(LUOT) == 1, LUOT)
    check("lượt đó là câu sự kiện có tên người mới",
          LUOT and "vừa vào nhóm" in LUOT[-1]["text"] and "Thu Hà" in LUOT[-1]["text"], LUOT[-1:] and LUOT[-1]["text"])
    check("câu Agent viết được gửi vào nhóm và TAG đúng người mới",
          len(CLI) == 1 and CLI[0]["pos"][0] == NHOM and CLI[0]["pos"][1].startswith("@Thu Hà ")
          and "7101" in " ".join(CLI[0]["opts"]) and not GUI, (CLI, GUI))

    CLI.clear()
    TRA_LOI["v"] = "[IM_LANG]"
    KHO_TIN.append(join_msg("7102", "Bình", "a2"))
    await doc()
    check("Agent trả [IM_LANG] thì không gửi gì", not CLI and not GUI, (CLI, GUI))

    LUOT.clear()
    TRA_LOI["v"] = "Chào bạn!"
    KHO_TIN.append(join_msg("7103", "Lạ", "a3", thread=NHOM_LA))
    await doc()
    check("nhóm chưa cho phép: không tốn lượt model, không gửi gì", not LUOT and not CLI and not GUI, (LUOT, CLI))
    cho = [x for x in chatbot_runtime.nhom_cho(bid) if x["chat_id"] == NHOM_LA]
    check("CANARY: người vào nhóm lạ KHÔNG tính là một lần có người gọi bot",
          all(int(x.get("lan") or 0) == 0 for x in cho), cho)

    real = chatbot_runtime._qua_han_muc
    chatbot_runtime._qua_han_muc = lambda *a, **k: True
    KHO_TIN.append(join_msg("7104", "Đông", "a4"))
    await doc()
    chatbot_runtime._qua_han_muc = real
    check("quá hạn mức (nhiều người vào cùng lúc): im, không nói 'nhắn hơi nhanh' với người mới",
          not CLI and not GUI, (CLI, GUI))

    TRA_LOI["v"] = RuntimeError("engine hỏng")
    KHO_TIN.append(join_msg("7105", "Tây", "a5"))
    await doc()
    check("engine lỗi: im, không xin lỗi 'trục trặc' trước cả nhóm", not CLI and not GUI, (CLI, GUI))
    TRA_LOI["v"] = "Chào bạn!"

    LUOT.clear()
    KHO_TIN.append(join_msg("7106", "Cũ", "a6", giay_truoc=3600))
    await doc()
    check("sự kiện vào nhóm quá cũ (bộ đệm lúc mới bật) thì bỏ qua", not LUOT, LUOT)

    # 0.84.6: hạn mức trong nhóm tính THEO NGƯỜI. Trước đó cả nhóm chung một hạn mức, nên ai tag bot sau khi
    # người khác đã gọi đủ số lần đều nhận "Anh chị nhắn hơi nhanh..." kèm tag tên mình trước cả nhóm.
    chatbot_store.update_bot(bid, {"rate_limit": 1})
    chatbot_runtime._HITS.clear()
    CLI.clear()
    LUOT.clear()
    TRA_LOI["v"] = "Dạ em trả lời đây ạ"
    for i, (uid, ten) in enumerate((("7201", "An"), ("7202", "Vũ Hồng Sơn"))):
        KHO_TIN.append({"threadId": NHOM, "from": uid, "senderName": ten, "type": "text",
                        "text": "@Javis Vũ cho hỏi lịch học", "id": f"r{i}", "ts": _ms(1), "threadType": "group"})
        await doc()
    gui_ra = [c["pos"][1] for c in CLI]
    check("CANARY: hạn mức 1 câu/giờ, hai người KHÁC nhau cùng tag bot thì cả hai đều được trả lời",
          len(LUOT) == 2 and not any("nhắn hơi nhanh" in x for x in gui_ra), gui_ra)
    KHO_TIN.append({"threadId": NHOM, "from": "7202", "senderName": "Vũ Hồng Sơn", "type": "text",
                    "text": "@Javis Vũ hỏi thêm câu nữa", "id": "r9", "ts": _ms(1), "threadType": "group"})
    await doc()
    check("chính người đã hết hạn mức thì mới bị chặn", len(LUOT) == 2, len(LUOT))

    with conversations._conn() as cx:
        rows = [r[0] for r in cx.execute("SELECT text FROM messages").fetchall()]
    check("Hộp thư ghi lại người mới vào nhóm", any("Thu Hà" in r and ("vừa vào nhóm" in r or "joined" in r) for r in rows), rows)
    chatbot_runtime.stop_bot(bid)


asyncio.run(chay())

if _fails:
    print(f"\nFAIL - test_zalo_vao_nhom: {len(_fails)} lỗi: {_fails}")
    raise SystemExit(1)
print("\nOK - test_zalo_vao_nhom: tất cả pass")
