"""Zalo cá nhân: số phút bot nhường sau khi chủ nhắn tay là cài đặt của từng bot, 0 = không nhường (0.148.0).

    python tests/run.py nhuong_tay      (KHÔNG mạng, MCP giả)

Chủ nick MTM yêu cầu 14/10/2026: "tôi không muốn chặn tin nhắn trong 10 phút, bỏ lệnh này đi". Một tin nick gửi lúc 22:26
làm bot im cả nhóm 10 phút, kể cả khi được tag thẳng, vì `TAY_IM = 600` ghi cứng trong mã. Giờ mỗi bot có `nhuong_tay_phut`:
bot cũ không khai giữ 10 phút như trước, đặt 0 thì chủ nhắn tay không làm bot im ở đâu cả.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpnhuong-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import chatbot_store  # noqa: E402
import conversations  # noqa: E402,F401
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Cài đặt trong kho bot
# ============================================================
check("số phút hợp lệ 0..240", chatbot_store.clean_nhuong_tay("0") == 0 and chatbot_store.clean_nhuong_tay(10) == 10
      and chatbot_store.clean_nhuong_tay("240") == 240)
check("giá trị lạ là None", all(chatbot_store.clean_nhuong_tay(v) is None for v in ("", "abc", "-1", "241", None, "2.5")))

bid, err = chatbot_store.create_bot({"name": "Bot thử", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal"})
check("tạo bot không khai thì mặc định nhường 10 phút (như trước 0.148.0)",
      not err and (chatbot_store.get_bot(bid) or {}).get("nhuong_tay_phut") == 10, err)
ok, err = chatbot_store.update_bot(bid, {"nhuong_tay_phut": "0"})
check("sửa thành 0 (không nhường) lưu được", ok and chatbot_store.get_bot(bid)["nhuong_tay_phut"] == 0, err)
chatbot_store.update_bot(bid, {"nhuong_tay_phut": "abc"})
chatbot_store.update_bot(bid, {"nhuong_tay_phut": "999"})
check("CANARY: giá trị lạ GIỮ giá trị cũ, không bật lại cái nhường chủ đã tắt", chatbot_store.get_bot(bid)["nhuong_tay_phut"] == 0)
bid2, _ = chatbot_store.create_bot({"name": "Bot hai", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal",
                                     "nhuong_tay_phut": "5"})
check("tạo bot kèm số phút thì lưu đúng", chatbot_store.get_bot(bid2)["nhuong_tay_phut"] == 5)
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("form tạo bot nhận nhuong_tay_phut", 'nhuong_tay_phut: str = Form("")' in main_src
      and '"nhuong_tay_phut": nhuong_tay_phut' in main_src)

# ============================================================
# 2. Transport đọc cài đặt sống
# ============================================================
CFG = {"id": "bot-x", "reply_when": "mention"}


def lam_bot(cfg):
    return zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: cfg)


async def _answer(text, meta, progress):
    LUOT.append((text, dict(meta)))
    return {"text": "Dạ em đây ạ", "files": []}


check("bot cũ không khai: 600 giây như trước", lam_bot({}).tay_im() == 600)
check("0 phút: không nhường", lam_bot({"nhuong_tay_phut": 0}).tay_im() == 0)
check("5 phút: 300 giây", lam_bot({"nhuong_tay_phut": 5}).tay_im() == 300)

# ============================================================
# 3. Hành vi với MCP giả
# ============================================================
CONN = {"id": "zalo-1", "label": "Toán Thầy Thành", "connector_id": "zalo"}
GUI, KHO_TIN, LUOT = [], [], []
_id = [0]


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": t, "name": "Khách " + t, "type": "user"} for t in ("u1", "u2", "u3")]
                + [{"threadId": "g1", "name": "Nhóm", "type": "group"}]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.start = lambda: True


def tin(thread, text, giay_truoc, *, cua_minh=False, nhom=False, **them):
    _id[0] += 1
    m = {"threadId": thread, "from": "me" if cua_minh else (them.pop("from", None) or thread), "type": "text",
         "text": text, "id": f"m{_id[0]}", "ts": int((time.time() - giay_truoc) * 1000), "threadType": 1 if nhom else 0}
    if cua_minh:
        m["isSelf"] = True
    m.update(them)
    return m


async def doc(*ds):
    KHO_TIN.extend(ds)
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.2)


async def chay():
    # ---- bot đặt 0 phút: chủ nhắn tay không làm bot im ------------------------------------------------
    cfg0 = dict(CFG, nhuong_tay_phut=0)
    tb = lam_bot(cfg0)
    tb.start()
    check("tay_im_cua đọc cài đặt của bot đang trực", zc.tay_im_cua("zalo-1") == 0)
    await doc(tin("u1", "Để thầy xem", 30, cua_minh=True))
    check("CANARY: nhường 0: vừa nhắn tay mà chat riêng KHÔNG bị coi là đang nhường", not zc.chu_vua_nhan_tay("zalo-1", "u1"))
    await doc(tin("g1", "Cả nhà ơi", 30, nhom=True, cua_minh=True))
    check("CANARY: nhóm cũng không bị chặn (ca 22:26: tag thẳng mà bot im 10 phút)", not zc.chu_vua_nhan_tay("zalo-1", "g1"))
    await doc(tin("u1", "Thầy ơi cho em hỏi lịch học", 8))
    check("tin khách sau đó được trả lời như thường, không bị giữ chờ 10 phút",
          len(LUOT) == 1 and ("zalo-1", "u1") not in zc._CHO_CHU, (LUOT, list(zc._CHO_CHU)))
    LUOT.clear()
    await doc(tin("u2", "Thầy ơi", 3))
    check("đang gom chờ khách nhắn xong", ("zalo-1", "u2") in zc._GOM)
    await doc(tin("u2", "Thầy đang xem nhé", 1, cua_minh=True))
    check("nhường 0: chủ nhắn chen vào cũng không bỏ hàng gom (chủ đã chọn để bot trả lời)", ("zalo-1", "u2") in zc._GOM)
    tb.stop()

    # ---- bot không khai: giữ hành vi 10 phút --------------------------------------------------------
    LUOT.clear()
    tb = lam_bot(dict(CFG))
    tb.start()
    check("bot không khai: 600 giây", zc.tay_im_cua("zalo-1") == 600)
    await doc(tin("u3", "Chào chị", 30, cua_minh=True))
    check("bot không khai: vẫn nhường như trước", zc.chu_vua_nhan_tay("zalo-1", "u3"))
    tb.stop()

    # ---- bot 5 phút: nhường 5 phút, chờ chủ 5 phút rồi trả lời thay ---------------------------------
    LUOT.clear()
    tb = lam_bot(dict(CFG, nhuong_tay_phut=5))
    tb.start()
    zc._TAY.clear()
    await doc(tin("u3", "Chào chị", 30, cua_minh=True))
    await doc(tin("u3", "Học phí lớp 9 bao nhiêu ạ", 2))
    check("5 phút: tin khách được giữ", ("zalo-1", "u3") in zc._CHO_CHU)
    for k in list(zc._TAY):
        zc._TAY[k] -= 310
    for o in zc._CHO_CHU.values():
        o["dau"] -= 310
        for e in o["evs"]:
            e["created_at"] = float(e["created_at"]) - 310
    zc.xa_cho_chu("zalo-1", time.time())
    await asyncio.sleep(0.3)
    check("5 phút: chủ im đủ 5 phút thì bot trả lời thay (không chờ 10)",
          len(LUOT) == 1 and "sau 5 phút" in LUOT[0][0], LUOT)
    tb.stop()

    check("không có bot trực: mặc định TAY_IM", zc.tay_im_cua("zalo-khac") == zc.TAY_IM)

    # ---- nhóm: chủ đang nhường 3 phút, tin TAG thẳng nick vẫn được trả lời ngay -----------------------
    LUOT.clear()
    tb = lam_bot(dict(CFG, nhuong_tay_phut=3, reply_when="mention"))
    tb.start()
    zc._TAY[("zalo-1", "g1")] = time.time() - 30
    check("đang trong 3 phút nhường ở nhóm", zc.chu_vua_nhan_tay("zalo-1", "g1"))

    def ev_nhom(text, i):
        return {"chat_type": "group", "message_type": "text", "text": text, "external_chat_id": "g1",
                "sender_id": "u9", "sender_name": "Phụ huynh", "created_at": time.time(), "metadata": {},
                "external_message_id": f"g{i}", "sender_type": "customer"}

    await tb.xu_ly(ev_nhom("Mai lớp học mấy giờ vậy mọi người", 1))
    check("tin nhóm không gọi ai trong lúc nhường: bot vẫn im", not LUOT, LUOT)
    await tb.xu_ly(ev_nhom("@Toán Thầy Thành mai lớp học mấy giờ ạ", 2))
    check("CANARY: tin TAG thẳng nick trong lúc nhường: bot trả lời ngay (chủ chốt 14/10)", len(LUOT) == 1, LUOT)
    LUOT.clear()
    zc._TAY[("zalo-1", "u1")] = time.time() - 30
    await tb.xu_ly({"chat_type": "private", "message_type": "text", "text": "Thầy ơi", "external_chat_id": "u1",
                    "sender_id": "u1", "created_at": time.time(), "metadata": {}, "external_message_id": "p1"})
    check("chat riêng trong lúc nhường: vẫn im (chờ 3 phút rồi trả lời thay)", not LUOT, LUOT)
    tb.stop()


asyncio.run(chay())

js = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
check("form bot có ô nhường và gửi nhuong_tay_phut", 'id="cbNhuongTay"' in js and "nhuong_tay_phut:" in js)
check("không dùng em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
