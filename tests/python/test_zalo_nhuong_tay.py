"""Zalo cá nhân: số phút bot nhường sau khi chủ nhắn tay là cài đặt của từng bot, 0 = không nhường (0.172.0).

    python tests/run.py nhuong_tay      (KHÔNG mạng, MCP giả)

Chủ nick MTM yêu cầu 14/10/2026: "tôi không muốn chặn tin nhắn trong 10 phút, bỏ lệnh này đi". Một tin nick gửi lúc 22:26
làm bot im cả nhóm 10 phút, kể cả khi được tag thẳng, vì `TAY_IM = 600` ghi cứng trong mã. Giờ mỗi bot có `nhuong_tay_phut`.

Review of PR #652 (maintainer, 5522960488) locked in here:
  1. 0 means "do not go quiet", NOT "repeat what the owner just answered": an owner message still clears the gathering
     queue, and a private message the owner answered by hand is never answered again by the bot.
  2. "Unset" and "set to 10" are different states. A bot that never saved the setting (every bot older than 0.172.0)
     keeps the old group behaviour: silent for the whole window, tags included, nothing held. Only an explicit value
     opts groups into the new logic (tag answered at once, other messages held and released per person).
  3. A tagged / reply-to-bot group message carrying a file during the yield is downloaded and handled (explicit bots).
  4. The note to the Agent says how long it has been since the owner's LAST hand-typed message, with the real minutes.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-zpnhuong-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import chatbot_store  # noqa: E402
import conversations  # noqa: E402,F401
import zalo_attachments  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Cài đặt trong kho bot: "chưa đặt" khác "đặt 10"
# ============================================================
check("số phút hợp lệ 0..240", chatbot_store.clean_nhuong_tay("0") == 0 and chatbot_store.clean_nhuong_tay(10) == 10
      and chatbot_store.clean_nhuong_tay("240") == 240)
check("giá trị lạ là None", all(chatbot_store.clean_nhuong_tay(v) is None for v in ("", "abc", "-1", "241", None, "2.5")))

bid, err = chatbot_store.create_bot({"name": "Bot thử", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal"})
check("CANARY: tạo bot không khai thì lưu CHƯA ĐẶT (None), không phải 10",
      not err and (chatbot_store.get_bot(bid) or {}).get("nhuong_tay_phut") is None, err)
ok, err = chatbot_store.update_bot(bid, {"nhuong_tay_phut": "0"})
check("sửa thành 0 (không nhường) lưu được", ok and chatbot_store.get_bot(bid)["nhuong_tay_phut"] == 0, err)
chatbot_store.update_bot(bid, {"nhuong_tay_phut": "abc"})
chatbot_store.update_bot(bid, {"nhuong_tay_phut": "999"})
check("CANARY: giá trị lạ GIỮ giá trị cũ, không bật lại cái nhường chủ đã tắt", chatbot_store.get_bot(bid)["nhuong_tay_phut"] == 0)
chatbot_store.update_bot(bid, {"nhuong_tay_phut": ""})
check("để trống thì về CHƯA ĐẶT (mặc định của kênh)", chatbot_store.get_bot(bid)["nhuong_tay_phut"] is None)
chatbot_store.update_bot(bid, {"name": "Bot thử 2"})
check("sửa trường khác không đụng tới cài đặt nhường", chatbot_store.get_bot(bid)["nhuong_tay_phut"] is None)
bid2, _ = chatbot_store.create_bot({"name": "Bot hai", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal",
                                     "nhuong_tay_phut": "5"})
check("tạo bot kèm số phút thì lưu đúng", chatbot_store.get_bot(bid2)["nhuong_tay_phut"] == 5)

# ---- 1b. qua đúng API mà form bot gọi (thay cho kiểm chữ trong main.py) ----
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
FORM = {"name": "Bot form", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal"}
r = cl.post("/chatbots", data=dict(FORM, nhuong_tay_phut=""))
id_trong = (r.json() or {}).get("id")
check("POST /chatbots ô trống: bot CHƯA ĐẶT", r.status_code == 200 and id_trong
      and chatbot_store.get_bot(id_trong).get("nhuong_tay_phut") is None, r.text)
r = cl.post("/chatbots", data=dict(FORM, name="Bot form 7", nhuong_tay_phut="7"))
id_bay = (r.json() or {}).get("id")
check("POST /chatbots nhuong_tay_phut=7 lưu 7", r.status_code == 200 and id_bay
      and chatbot_store.get_bot(id_bay).get("nhuong_tay_phut") == 7, r.text)
r = cl.post("/chatbots/" + id_bay + "/update", data={"nhuong_tay_phut": "3"})
check("POST /update đổi sang 3", r.status_code == 200 and chatbot_store.get_bot(id_bay)["nhuong_tay_phut"] == 3, r.text)
cl.post("/chatbots/" + id_bay + "/update", data={"nhuong_tay_phut": "abc"})
check("POST /update giá trị lạ giữ 3", chatbot_store.get_bot(id_bay)["nhuong_tay_phut"] == 3)
cl.post("/chatbots/" + id_bay + "/update", data={"nhuong_tay_phut": ""})
check("POST /update ô trống về CHƯA ĐẶT", chatbot_store.get_bot(id_bay)["nhuong_tay_phut"] is None)
cl.post("/chatbots/" + id_bay + "/update", data={"name": "Bot form đổi tên"})
check("POST /update không gửi ô nhường thì không đổi gì", chatbot_store.get_bot(id_bay)["nhuong_tay_phut"] is None)

# ============================================================
# 2. Transport đọc cài đặt sống
# ============================================================
CFG = {"id": "bot-x", "reply_when": "mention"}
LUOT = []


def lam_bot(cfg, **kw):
    return zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: cfg, **kw)


async def _answer(text, meta, progress):
    LUOT.append((text, dict(meta)))
    return {"text": "Dạ em đây ạ", "files": []}


check("bot cũ không khai: 600 giây, chưa đặt", lam_bot({}).tay_im() == 600 and not lam_bot({}).yield_explicit())
check("lưu None (chưa đặt): như bot cũ", lam_bot({"nhuong_tay_phut": None}).tay_im() == 600
      and not lam_bot({"nhuong_tay_phut": None}).yield_explicit())
check("0 phút: không nhường, đã đặt", lam_bot({"nhuong_tay_phut": 0}).tay_im() == 0
      and lam_bot({"nhuong_tay_phut": 0}).yield_explicit())
check("5 phút: 300 giây, đã đặt", lam_bot({"nhuong_tay_phut": 5}).tay_im() == 300
      and lam_bot({"nhuong_tay_phut": 5}).yield_explicit())
check("đặt đúng 10: cùng 600 giây nhưng là ĐÃ ĐẶT", lam_bot({"nhuong_tay_phut": 10}).tay_im() == 600
      and lam_bot({"nhuong_tay_phut": 10}).yield_explicit())

# ============================================================
# 3. Hành vi với MCP giả
# ============================================================
CONN = {"id": "zalo-1", "label": "Toán Thầy Thành", "connector_id": "zalo"}
GUI, KHO_TIN = [], []
_id = [0]


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": t, "name": "Khách " + t, "type": "user"} for t in ("u1", "u2", "u3", "u4")]
                + [{"threadId": t, "name": "Nhóm " + t, "type": "group"} for t in ("g1", "g2", "g3")]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.start = lambda: True
zc._ID_MINH["zalo-1"] = {"uid": "me", "ten": "Toán Thầy Thành"}


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


def lui_gio(giay):
    """Như thể `giay` giây đã trôi qua: dời giờ chủ nhắn tay và giờ các tin đang giữ về quá khứ."""
    for k in list(zc._TAY):
        zc._TAY[k] -= giay
    for o in zc._CHO_CHU.values():
        o["dau"] -= giay
        for e in o["evs"]:
            e["created_at"] = float(e.get("created_at") or time.time()) - giay


def don():
    GUI.clear()
    LUOT.clear()
    zc._TAY.clear()
    zc._GOM.clear()
    zc._CHO_CHU.clear()


def ev_nhom(thread, text, i, nguoi="u9", **md):
    return {"chat_type": "group", "message_type": "text", "text": text, "external_chat_id": thread,
            "sender_id": nguoi, "sender_name": "Phụ huynh " + nguoi, "created_at": time.time(), "metadata": dict(md),
            "external_message_id": f"{thread}-{i}", "sender_type": "customer", "account_id": "zalo-1"}


async def chay():
    # ---- bot đặt 0 phút: chủ nhắn tay không làm bot im ------------------------------------------------
    don()
    tb = lam_bot(dict(CFG, nhuong_tay_phut=0))
    tb.start()
    check("tay_im_cua đọc cài đặt của bot đang trực", zc.tay_im_cua("zalo-1") == 0)
    await doc(tin("u1", "Để thầy xem", 30, cua_minh=True))
    check("CANARY: nhường 0: vừa nhắn tay mà chat riêng KHÔNG bị coi là đang nhường", not zc.chu_vua_nhan_tay("zalo-1", "u1"))
    await doc(tin("g1", "Cả nhà ơi", 30, nhom=True, cua_minh=True))
    check("CANARY: nhóm cũng không bị chặn (ca 22:26: tag thẳng mà bot im 10 phút)", not zc.chu_vua_nhan_tay("zalo-1", "g1"))
    await doc(tin("u1", "Thầy ơi cho em hỏi lịch học", 8))
    check("tin khách SAU tin nhắn tay được trả lời như thường, không bị giữ chờ 10 phút",
          len(LUOT) == 1 and ("zalo-1", "u1") not in zc._CHO_CHU, (LUOT, list(zc._CHO_CHU)))

    # Review point 1: customer asks, the owner answers within CHO_KHACH_IM, the bot must NOT answer it again.
    LUOT.clear()
    GUI.clear()
    await doc(tin("u2", "Học phí bao nhiêu ạ", 3))
    check("đang gom chờ khách nhắn xong", ("zalo-1", "u2") in zc._GOM)
    await doc(tin("u2", "200k nhé", 1, cua_minh=True))
    check("CANARY: nhường 0: chủ trả lời tay thì hàng gom bị bỏ", ("zalo-1", "u2") not in zc._GOM)
    zc.xa_hang_cho("zalo-1", time.time() + zc.CHO_KHACH_IM + 1)
    await asyncio.sleep(0.3)
    check("CANARY: nhường 0: bot KHÔNG trả lời lại câu chủ đã đáp (không gửi gì dưới tên chủ)", not LUOT and not GUI,
          (LUOT, GUI))

    # Same race when the customer message goes straight to the bot (no gathering): owner reply in the same read batch.
    LUOT.clear()
    cu = zc.CHO_KHACH_IM
    zc.CHO_KHACH_IM = 0
    try:
        await doc(tin("u3", "Mai có học không ạ", 3), tin("u3", "Mai nghỉ em nhé", 1, cua_minh=True))
    finally:
        zc.CHO_KHACH_IM = cu
    check("nhường 0, không gom: chủ đáp ngay sau trong cùng lượt đọc thì bot không trả lời tin đó", not LUOT, LUOT)
    await doc(tin("u3", "Dạ vâng ạ, cảm ơn thầy", 0))
    zc.xa_hang_cho("zalo-1", time.time() + zc.CHO_KHACH_IM + 1)
    await asyncio.sleep(0.3)
    check("tin khách mới SAU câu chủ đáp vẫn được trả lời", len(LUOT) == 1 and "cảm ơn thầy" in LUOT[0][0], LUOT)
    tb.stop()

    # ---- bot không khai: giữ hành vi 10 phút --------------------------------------------------------
    don()
    tb = lam_bot(dict(CFG))
    tb.start()
    check("bot không khai: 600 giây", zc.tay_im_cua("zalo-1") == 600 and not zc.yield_explicit("zalo-1"))
    await doc(tin("u3", "Chào chị", 30, cua_minh=True))
    check("bot không khai: vẫn nhường như trước", zc.chu_vua_nhan_tay("zalo-1", "u3"))
    tb.stop()

    # ---- bot 5 phút: nhường 5 phút, chờ chủ 5 phút rồi trả lời thay ---------------------------------
    don()
    tb = lam_bot(dict(CFG, nhuong_tay_phut=5))
    tb.start()
    await doc(tin("u3", "Chào chị", 30, cua_minh=True))
    await doc(tin("u3", "Học phí lớp 9 bao nhiêu ạ", 2))
    check("5 phút: tin khách được giữ", ("zalo-1", "u3") in zc._CHO_CHU)
    lui_gio(240)
    check("4 phút sau tin nhắn tay: chưa tới lượt bot", zc.xa_cho_chu("zalo-1", time.time()) == 0)
    lui_gio(70)
    tay = zc._TAY[("zalo-1", "u3")]
    zc.xa_cho_chu("zalo-1", time.time())
    await asyncio.sleep(0.3)
    from datetime import datetime
    import localefmt
    gio_tay = datetime.fromtimestamp(tay, localefmt.tz()).strftime("%H:%M")
    check("5 phút: chủ im đủ 5 phút thì bot trả lời thay (không chờ 10)", len(LUOT) == 1, LUOT)
    check("ghi chú nói đúng giờ tin nhắn tay cuối và số phút đã cài (review point 4)",
          LUOT and f"chủ nick nhắn tay lần cuối lúc {gio_tay} rồi 5 phút không nhắn thêm gì" in LUOT[0][0], LUOT)
    check("ghi chú không còn câu cũ 'chưa trả lời sau 10 phút'", LUOT and "sau 10 phút" not in LUOT[0][0], LUOT)
    tb.stop()

    check("không có bot trực: mặc định TAY_IM, chưa đặt", zc.tay_im_cua("zalo-khac") == zc.TAY_IM
          and not zc.yield_explicit("zalo-khac"))

    # ---- nhóm, bot CHƯA ĐẶT (review point 2): giữ đúng hành vi trước 0.172.0 --------------------------
    # reply_when=always so a silent bot really is the yield at work, not the "only when tagged" rule.
    don()
    tb = lam_bot(dict(CFG, reply_when="always"))
    tb.start()
    await doc(tin("g2", "Cả nhà ơi", 30, nhom=True, cua_minh=True))
    await doc(tin("g2", "Mai lớp học mấy giờ vậy mọi người", 2, nhom=True, **{"from": "u9"}))
    check("chưa đặt, nhóm 'luôn trả lời': tin không gọi ai trong lúc nhường bị bỏ, KHÔNG giữ",
          not LUOT and ("zalo-1", "g2") not in zc._CHO_CHU, (LUOT, list(zc._CHO_CHU)))
    await doc(tin("g2", "@Toán Thầy Thành mai lớp học mấy giờ ạ", 1, nhom=True, **{"from": "u7"}))
    check("CANARY: chưa đặt: tin TAG thẳng trong lúc nhường vẫn im như trước 0.172.0", not LUOT, LUOT)
    lui_gio(610)
    n = zc.xa_cho_chu("zalo-1", time.time())
    await asyncio.sleep(0.3)
    check("chưa đặt: hết quãng nhường không có loạt trả lời tin cũ", n == 0 and not LUOT, (n, LUOT))
    await doc(tin("g2", "Mai lớp học mấy giờ ạ", 1, nhom=True, **{"from": "u9"}))
    check("hết quãng nhường thì nhóm trả lời như thường", len(LUOT) == 1, LUOT)
    tb.stop()

    # ---- nhóm, bot ĐẶT 10 phút (cùng số phút): luật nhóm mới ------------------------------------------
    don()
    tb = lam_bot(dict(CFG, reply_when="always", nhuong_tay_phut=10))
    tb.start()
    await doc(tin("g3", "Cả nhà ơi", 30, nhom=True, cua_minh=True))
    await doc(tin("g3", "Mai lớp học mấy giờ vậy mọi người", 2, nhom=True, **{"from": "u9"}))
    check("đặt 10, nhóm 'luôn trả lời': tin không gọi ai bị GIỮ, chưa trả lời",
          not LUOT and ("zalo-1", "g3") in zc._CHO_CHU, (LUOT, list(zc._CHO_CHU)))
    await doc(tin("g3", "@Toán Thầy Thành mai lớp học mấy giờ ạ", 1, nhom=True, **{"from": "u7"}))
    check("CANARY: đặt 10: tin TAG thẳng trả lời ngay", len(LUOT) == 1 and "mai lớp học mấy giờ ạ" in LUOT[0][0], LUOT)
    LUOT.clear()
    lui_gio(610)
    n = zc.xa_cho_chu("zalo-1", time.time())
    await asyncio.sleep(0.3)
    check("đặt 10: hết quãng nhường, tin đang giữ được trả lời một lượt", n == 1 and len(LUOT) == 1, (n, LUOT))
    tb.stop()

    # ---- gọi thẳng xu_ly: nhóm 'luôn trả lời', 3 phút nhường -------------------------------------------
    don()
    tb = lam_bot(dict(CFG, nhuong_tay_phut=3, reply_when="always"))
    tb.start()
    zc._TAY[("zalo-1", "g1")] = time.time() - 30
    check("đang trong 3 phút nhường ở nhóm", zc.chu_vua_nhan_tay("zalo-1", "g1"))
    await tb.xu_ly(ev_nhom("g1", "Mai lớp học mấy giờ vậy mọi người", 1))
    check("CANARY: tin nhóm không gọi ai trong lúc nhường: bot im dù nhóm 'luôn trả lời'", not LUOT, LUOT)
    await tb.xu_ly(ev_nhom("g1", "@Toán Thầy Thành mai lớp học mấy giờ ạ", 2))
    check("CANARY: tin TAG thẳng nick trong lúc nhường: bot trả lời ngay (chủ chốt 14/10)", len(LUOT) == 1, LUOT)
    LUOT.clear()
    zc._TAY[("zalo-1", "u1")] = time.time() - 30
    await tb.xu_ly({"chat_type": "private", "message_type": "text", "text": "Thầy ơi", "external_chat_id": "u1",
                    "sender_id": "u1", "created_at": time.time(), "metadata": {}, "external_message_id": "p1"})
    check("chat riêng trong lúc nhường: vẫn im (chờ 3 phút rồi trả lời thay)", not LUOT, LUOT)
    tb.stop()

    # ---- review point 3: tin trả lời tin của nick, mang FILE, trong lúc nhường -------------------------
    inbox = Path(tempfile.mkdtemp(prefix="javis-zpfile-")) / "inbox" / "khach"
    inbox.mkdir(parents=True)
    TAI = []

    async def _fetch(att, thu_muc):
        TAI.append(att.get("name"))
        p = Path(thu_muc) / str(att.get("name"))
        p.write_text("lop,diem\n9A,8.5", encoding="utf-8")
        return p, ""

    async def _pre(text, meta):
        return None

    cu_fetch = zalo_attachments.fetch_file
    zalo_attachments.fetch_file = _fetch
    try:
        def ev_file(i):
            e = ev_nhom("g1", "Bang-diem.csv", i, nguoi="u5", replyTo={"senderId": "me", "text": "Gửi bảng điểm nhé"},
                        attachment={"url": "https://files.zdn.vn/x", "name": "Bang-diem.csv", "size": 20})
            e["message_type"] = "file"
            return e

        for dat, mong in ((None, False), (3, True)):
            don()
            TAI.clear()
            cfg = dict(CFG, reply_when="mention", muc_quyen="auto")
            if dat is not None:
                cfg["nhuong_tay_phut"] = dat
            tb = lam_bot(cfg, precheck_fn=_pre, download_dir=lambda chat: str(inbox))
            tb.start()
            zc._TAY[("zalo-1", "g1")] = time.time() - 30
            await tb.xu_ly(ev_file(10 + (dat or 0)))
            if mong:
                check("CANARY: đặt 3 phút: file trả lời tin của nick trong lúc nhường được TẢI và đưa cho bot",
                      TAI == ["Bang-diem.csv"] and len(LUOT) == 1 and "9A,8.5" in LUOT[0][0], (TAI, LUOT))
            else:
                check("chưa đặt: file trong lúc nhường vẫn bị bỏ như trước 0.172.0 (không tải, không trả lời)",
                      not TAI and not LUOT, (TAI, LUOT))
            tb.stop()
    finally:
        zalo_attachments.fetch_file = cu_fetch


asyncio.run(chay())

check("không dùng em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
