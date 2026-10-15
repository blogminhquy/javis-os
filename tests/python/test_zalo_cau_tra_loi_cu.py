"""Zalo cá nhân: khách nhắn thêm lúc bot đang soạn thì bỏ câu cũ, gộp lại trả lời MỘT lần (0.172.0).

    python tests/run.py cau_tra_loi_cu      (KHÔNG mạng, MCP giả)

Ca thật 15/10/2026: phụ huynh nhắn cách nhau 8 đến 15 giây, bot soạn mất 8 đến 18 giây. Tin kế tiếp tới LÚC ĐANG
SOẠN nên câu gửi đi lỗi thời ("chị gửi thêm số điện thoại" trong khi số vừa nhắn xong), rồi tin sau bị đáp thêm
một lượt riêng. Giờ lượt soạn xong mà khách đã nhắn thêm chữ thì câu đó không gửi, chữ khách được giữ cho lượt
kế tiếp đọc cùng tin mới.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpcu-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402,F401
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Zalo của tôi", "connector_id": "zalo"}
GUI = []
KHO_TIN = []
LUOT = []
CHAN = []           # sự kiện giữ lượt đang soạn (mỗi phần tử giữ một lượt, theo thứ tự)
_id = [0]


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": t, "name": "Khách " + t, "type": "user"} for t in ("u1", "u2", "u3", "u4")]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.start = lambda: True


def tin(thread, text, giay_truoc, loai="text"):
    _id[0] += 1
    return {"threadId": thread, "from": thread, "type": loai, "text": text, "id": f"m{_id[0]}",
            "ts": int((time.time() - giay_truoc) * 1000), "threadType": 0}


LOI = []        # lần sau gọi answer_fn thì ném lỗi


async def _answer(text, meta, progress):
    """Giống `chatbot_runtime._answer` ở đúng chỗ cần: kiểm `_luot_cu` sau khi soạn xong."""
    LUOT.append((text, dict(meta)))
    if CHAN:
        await CHAN.pop(0).wait()
    if LOI and LOI[0] in text:
        LOI.pop()
        raise RuntimeError("engine gãy")
    if chatbot_runtime._luot_cu(meta):
        return {"text": "", "files": [], "im_lang": True, "khach_nhan_them": True}
    return {"text": "Dạ em trả lời: " + text[-30:], "files": []}


def lam_bot():
    return zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: {"id": "bot-x", "reply_when": "mention"})


async def doc(*ds):
    KHO_TIN.extend(ds)
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.2)


async def xa(giay_sau):
    n = zc.xa_hang_cho("zalo-1", time.time() + giay_sau)
    await asyncio.sleep(0.2)
    return n


def don():
    GUI.clear()
    LUOT.clear()
    CHAN.clear()
    zc._BO_DO.clear()


async def chay():
    tb = lam_bot()
    tb.start()

    # ---- 1. ca thật: tin thứ hai tới lúc bot đang soạn lượt đầu ----------------------------------
    don()
    giu = asyncio.Event()
    CHAN.append(giu)
    await doc(tin("u1", "Con sinh ngày 15/05/2012", 20))
    await xa(30)
    check("lượt đầu đang soạn, chưa gửi gì", len(LUOT) == 1 and not GUI, (LUOT, GUI))
    check("lượt đầu mang dấu seq_cuoi = 1", LUOT[0][1].get("seq_cuoi") == 1, LUOT[0][1])
    await doc(tin("u1", "Hiền 0900000000", 2))
    n = await xa(30)
    check("tin thứ hai im đủ 5 giây: lượt thứ hai được giao, xếp hàng chờ khoá cuộc chat", n == 1 and len(LUOT) == 1, (n, LUOT))
    giu.set()
    await asyncio.sleep(0.5)
    check("lượt đầu soạn xong mà khách đã nhắn thêm: KHÔNG gửi câu cũ", len(GUI) == 1, GUI)
    check("lượt thứ hai chạy sau đó, đúng MỘT câu trả lời gửi đi", len(LUOT) == 2 and len(GUI) == 1, (LUOT, GUI))
    ghi = LUOT[1][1].get("ghi_chu_dau") or ""
    check("lượt thứ hai nhận ghi chú: câu trước chưa gửi + chữ khách của lượt đầu",
          "CHƯA được gửi" in ghi and "Con sinh ngày 15/05/2012" in ghi, ghi)
    check("chữ khách của lượt thứ hai vẫn nguyên, không dính ghi chú (Hộp thư sạch)",
          LUOT[1][0] == "Hiền 0900000000", LUOT[1][0])
    check("đếm số lần bỏ để có trần", LUOT[1][1].get("bo_do_n") == 1, LUOT[1][1])
    check("chữ giữ lại được dùng rồi thì xoá", ("zalo-1", "u1") not in zc._BO_DO)

    # ---- 2. không có tin mới thì gửi bình thường -------------------------------------------------
    don()
    await doc(tin("u2", "Cho em hỏi lịch học", 20))
    await xa(30)
    check("không ai nhắn thêm: trả lời bình thường, không ghi chú", len(GUI) == 1 and not LUOT[0][1].get("ghi_chu_dau"), (GUI, LUOT))

    # ---- 3. sticker không tính là tin có chữ: không làm câu trả lời thành cũ -------------------------
    don()
    giu = asyncio.Event()
    CHAN.append(giu)
    await doc(tin("u3", "Thầy ơi cho em hỏi học phí", 20))
    await xa(30)
    seq0 = zc._SEQ.get(("zalo-1", "u3"), 0)
    await doc(tin("u3", "[Zalo cá nhân: khách gửi sticker]", 2, loai="sticker"))
    check("sticker không tăng bộ đếm", zc._SEQ.get(("zalo-1", "u3"), 0) == seq0)
    giu.set()
    await asyncio.sleep(0.5)
    check("sticker trong lúc soạn thì câu trả lời vẫn gửi", len(GUI) == 1, GUI)

    # ---- 4. trần: bỏ liền 3 lần thì lần sau gửi dù khách còn nhắn ------------------------------------
    check("dưới trần thì có thể bỏ", chatbot_runtime._luot_cu({"seq_cuoi": 0, "bo_do_n": zc.MAX_BO_DO - 1,
                                                              "account_id": "zalo-1", "chat_id": "u1"}))
    check("tới trần thì gửi", not chatbot_runtime._luot_cu({"seq_cuoi": 0, "bo_do_n": zc.MAX_BO_DO,
                                                           "account_id": "zalo-1", "chat_id": "u1"}))
    check("lượt không có seq_cuoi (nhóm, Telegram, tắt chờ) không bao giờ bị bỏ",
          not chatbot_runtime._luot_cu({"account_id": "zalo-1", "chat_id": "u1"}))

    # ---- 5. chữ giữ lại nguội thì bỏ; lượt kế gãy thì trả lại chữ ------------------------------------
    zc._BO_DO.clear()
    zc.bo_do_gui("zalo-1", "u4", ["a", "b"], 2)
    o = zc.lay_bo_do("zalo-1", "u4")
    check("lấy chữ giữ lại đúng thứ tự và số lần, rồi xoá", o.get("texts") == ["a", "b"] and o.get("n") == 2
          and zc.lay_bo_do("zalo-1", "u4") == {}, o)
    zc.bo_do_gui("zalo-1", "u4", ["cũ"], 1)
    check("chữ giữ quá lâu thì bỏ, không trộn vào cuộc trò chuyện đã nguội",
          zc.lay_bo_do("zalo-1", "u4", now=time.time() + zc.BO_DO_TUOI + 5) == {})

    don()
    giu = asyncio.Event()
    CHAN.append(giu)
    await doc(tin("u4", "Cho em hỏi một chút", 20))
    await xa(30)
    await doc(tin("u4", "về lớp 9 ạ", 2))
    await xa(30)
    LOI.append("về lớp 9")        # lượt thứ hai (đang chờ khoá) sẽ gãy
    giu.set()
    await asyncio.sleep(0.5)
    check("lượt kế tiếp gãy thì chữ khách của lượt đã bỏ được trả lại, không mất",
          ("zalo-1", "u4") in zc._BO_DO and "Cho em hỏi một chút" in zc._BO_DO[("zalo-1", "u4")]["texts"], zc._BO_DO)
    tb.stop()


asyncio.run(chay())
print()
print("TẤT CẢ XANH" if not _fails else "ĐỎ: " + ", ".join(_fails))
sys.exit(1 if _fails else 0)
