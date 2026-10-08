"""Duyệt người xin vào nhóm Zalo (0.84.7, javis-zalo 1.2.0).

    python tests/run.py zalo_xin_vao_nhom      (KHÔNG mạng, MCP giả)

Chủ repo chọn hướng "anh ra lệnh, Javis làm": hỏi Javis ai đang xin vào nhóm, bảo duyệt hay từ chối thì Javis làm,
có người mới xin vào thì Javis báo chủ. Bot chuyên trách KHÔNG được tự quyết ai vào nhóm.

File này canh:
  1. Quyền: liệt kê là ĐỌC, duyệt/từ chối là NGUY HIỂM (đổi thành viên nhóm, không hoàn tác được).
  2. Tin `group.join_request` thành sự kiện xin vào nhóm trong Hộp thư, và KHÔNG tới bot.
  3. Chủ được báo MỘT lần cho mỗi nhóm trong một lô, có tên người xin và tên nhóm; tin trùng không báo lại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpxin-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import mcp_catalog  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Quyền của hai tool mới
# ============================================================
zalo = mcp_catalog.get("zalo")
check("liệt kê người xin vào là ĐỌC", mcp_catalog.classify(zalo, "zalo_list_join_requests") == "read")
check("CANARY: duyệt hay từ chối là NGUY HIỂM (đổi thành viên nhóm)",
      mcp_catalog.classify(zalo, "zalo_review_join_requests") == "danger")

# ============================================================
# 2 + 3. Vòng đọc: sự kiện vào Hộp thư, không tới bot, chủ được báo
# ============================================================
CONN = {"id": "zalo-1", "label": "Javis Vũ", "connector_id": "zalo"}
NHOM = "9990001"
KHO_TIN, BAO, BOT = [], [], []


async def _goi_gia(conn, tool, args):
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": NHOM, "name": "Zoom | Javis OS", "type": "group"}]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


async def _bao(owner_chat, text, **kw):
    BAO.append({"owner": owner_chat, "text": text, **kw})
    return True, ""


class _BotGia:
    async def xu_ly(self, ev):
        BOT.append(ev)


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.THU_LAI_TEN_GIAY = 0
zc.NOTIFY_OWNER = _bao
zc._BOTS["zalo-1"] = _BotGia()


def xin(uid, ten, mid):
    t = int((time.time() - 2) * 1000)
    return {"id": f"joinreq:{NHOM}:{uid}:{t}:{mid}", "threadId": NHOM, "threadType": "group", "senderId": uid,
            "senderName": ten, "text": f"[{ten} asked to join the group]", "timestamp": t,
            "type": "group.join_request", "attachment": None, "replyTo": None,
            "event": {"kind": "join_request", "totalPending": 2, "time": t}}


async def doc():
    await zc.doc_mot_lan(dict(CONN))
    t0 = time.time()
    while zc._VIEC and time.time() - t0 < 6:
        await asyncio.sleep(0.02)


async def chay():
    TEN = {NHOM: {"name": "Zoom | Javis OS", "type": "group"}}
    ev = zc.chuan_hoa_tin(dict(CONN), xin("7301", "Lan", "x"), TEN)
    md = (ev or {}).get("metadata", {})
    check("tin group.join_request thành sự kiện xin vào nhóm, người gửi là người xin",
          ev and md.get("join_request") and ev["sender_id"] == "7301" and ev["chat_type"] == "group", ev)
    check("Hộp thư ghi 'xin vào nhóm' chứ không phải câu tiếng Anh thô",
          ev and "Lan" in ev["text"] and ("xin vào nhóm" in ev["text"] or "asked to join" in ev["text"]), ev and ev["text"])
    check("không lẫn với sự kiện ĐÃ vào nhóm", "member_join" not in md)

    a, b = xin("7301", "Lan", "1"), xin("7302", "Minh", "2")
    KHO_TIN.extend([a, b])
    await doc()
    check("CANARY: bot KHÔNG nhận sự kiện xin vào nhóm (chủ quyết, không phải bot)", BOT == [], BOT)
    check("chủ được báo đúng MỘT lần cho cả lô của nhóm", len(BAO) == 1, BAO)
    cau = BAO[0]["text"] if BAO else ""
    check("câu báo có tên cả hai người và tên nhóm",
          "Lan" in cau and "Minh" in cau and "Zoom | Javis OS" in cau, cau)
    check("câu báo chỉ cách xử lý và điều kiện trưởng/phó nhóm",
          ("duyệt" in cau or "approve" in cau) and ("phó nhóm" in cau or "deputy" in cau), cau)
    check("báo vào hòm thư chung của chủ (không gắn hội thoại nào), loại hệ thống",
          BAO and BAO[0]["owner"] == "" and BAO[0].get("kind") == "system", BAO)

    KHO_TIN.extend([a, b])
    await doc()
    check("tin trùng (đọc lại) không báo lần nữa", len(BAO) == 1, len(BAO))

    names = [f"Người {i}" for i in range(15)]
    cau_dai = zc.cau_bao_xin_vao(CONN, "Nhóm", names)
    check("nhiều người thì liệt kê 10 tên rồi 'và 5 người khác'",
          "Người 9" in cau_dai and "Người 10" not in cau_dai and "5" in cau_dai, cau_dai)


asyncio.run(chay())

check("CANARY: main gắn cửa báo chủ cho kênh Zalo trước khi bật vòng đọc (thiếu là không ai được báo)",
      "zalo_personal_channel.NOTIFY_OWNER = _notify_owner" in (SERVER / "main.py").read_text(encoding="utf-8"))

if _fails:
    print(f"\nFAIL - test_zalo_xin_vao_nhom: {len(_fails)} lỗi: {_fails}")
    raise SystemExit(1)
print("\nOK - test_zalo_xin_vao_nhom: tất cả pass")
