"""Zalo cá nhân: chủ vừa nhắn tay thì bot nhường, nhưng chủ chưa trả lời tin khách sau 10 phút thì bot trả lời thay (0.136.0).

    python tests/run.py chu_chua_tra_loi      (KHÔNG mạng, MCP giả)

Chủ nick yêu cầu 14/10/2026: "nếu tôi không rep sau 10 phút thì cứ tự động trả lời sao cho hợp lí nhất". Ca thật cùng ngày:
chủ nhắn "Mẹ nhắn tin gì vào đây đi" lúc 11:51, khách gửi một file .docx và một ảnh lúc 11:52. Bot nhường 10 phút vì chủ vừa
nhắn tay, hết 10 phút thì tin đã cũ quá 3 phút (`TUOI_TOI_DA`) nên bị bỏ hẳn: không ai trả lời cả.

Test KHÔNG chờ giờ thật: `lui_gio` dời mọi mốc giờ đã nhớ (giờ chủ nhắn, giờ tin đang giữ) về quá khứ như thể thời gian đã trôi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpchu-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import conversations  # noqa: E402,F401
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Toán Thầy Thành", "connector_id": "zalo"}
GUI = []            # mọi lần gọi zalo_send_message
KHO_TIN = []        # tin "MCP" trả ở lần đọc kế tiếp
LUOT = []           # mọi lượt bot (chữ, meta) tới answer_fn
_id = [0]


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": t, "name": "Khách " + t, "type": "user"} for t in ("u1", "u2", "u3", "u4", "u5")]
                + [{"threadId": "g1", "name": "Nhóm", "type": "group"}]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.start = lambda: True     # không chạy vòng đọc nền song song với các bước tay


def tin(thread, text, giay_truoc, *, cua_minh=False, nhom=False, loai="text", **them):
    _id[0] += 1
    m = {"threadId": thread, "from": "me" if cua_minh else (them.pop("from", None) or thread), "type": loai,
         "text": text, "id": f"m{_id[0]}", "ts": int((time.time() - giay_truoc) * 1000),
         "threadType": 1 if nhom else 0}
    if cua_minh:
        m["isSelf"] = True
    m.update(them)
    return m


async def _answer(text, meta, progress):
    LUOT.append((text, dict(meta)))
    return {"text": "Dạ em nhận được rồi ạ, thầy sẽ xem và phản hồi mình sớm nhé.", "files": []}


CFG = {"id": "bot-x", "reply_when": "mention"}     # cấu hình SỐNG của bot: một phần test đặt `nhuong_tay_phut` rồi gỡ ra


def lam_bot():
    return zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: CFG)


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


async def xa():
    n = zc.xa_cho_chu("zalo-1", time.time())
    await asyncio.sleep(0.3)
    return n


def don():
    GUI.clear()
    LUOT.clear()


async def chay():
    check("mặc định chờ chủ 10 phút, bằng đúng quãng bot nhường khi chủ nhắn tay",
          zc.CHO_CHU_TRA_LOI == 600 and zc.TAY_IM == 600)
    tb = lam_bot()
    tb.start()

    # ---- 1. ca thật 14/10: chủ nhắn tay, khách gửi file + ảnh không chữ, chủ im 10 phút ------------
    await doc(tin("u1", "Mẹ nhắn tin gì vào đây đi", 50, cua_minh=True))
    await doc(tin("u1", "Ke-hoach-sinh-hoat-chuyen-de-quy-4.docx", 3, loai="share.file",
                  fileName="Ke-hoach-sinh-hoat-chuyen-de-quy-4.docx"),
              tin("u1", "", 2, loai="chat.photo", url="https://photo.zdn.vn/a.jpg"))
    check("chủ vừa nhắn tay: tin khách được GIỮ, bot chưa trả lời", ("zalo-1", "u1") in zc._CHO_CHU and not LUOT and not GUI,
          (zc._CHO_CHU.keys(), LUOT))
    lui_gio(400)
    check("mới 6-7 phút: chưa tới lượt bot", await xa() == 0 and not LUOT)
    lui_gio(200)
    n = await xa()
    check("CANARY: chủ im đủ 10 phút: bot trả lời đúng MỘT lần", n == 1 and len(LUOT) == 1 and len(GUI) == 1, (n, LUOT, GUI))
    text, meta = LUOT[0] if LUOT else ("", {})
    check("Agent được báo chủ đã 10 phút không nhắn thêm kể từ tin nhắn tay cuối (0.172.0)",
          "chủ nick nhắn tay lần cuối lúc" in text and "rồi 10 phút không nhắn thêm gì" in text, text)
    check("và khách gửi kèm gì (tên file, một ảnh), để đáp hợp cảnh thay vì im vì tin không có chữ",
          "file Ke-hoach-sinh-hoat-chuyen-de-quy-4.docx" in text and "một ảnh" in text, text)
    check("ghi chú nói rõ không phải lời khách", "không phải lời khách" in text, text)
    check("lượt mang ảnh để bot nhìn được", meta.get("co_anh") and meta.get("image_url") == "https://photo.zdn.vn/a.jpg", meta)
    check("trả lời đúng người, chat riêng", GUI and GUI[0]["threadId"] == "u1" and GUI[0]["threadType"] == 0, GUI)
    check("xong thì hết giữ", ("zalo-1", "u1") not in zc._CHO_CHU)
    await xa()
    check("không trả lời lần hai", len(LUOT) == 1)

    # ---- 2. chủ trả lời tay trước 10 phút: bot không xen vào --------------------------------------
    don()
    await doc(tin("u2", "Để thầy xem", 30, cua_minh=True))
    await doc(tin("u2", "Dạ thầy xem giúp con lịch học ạ", 2))
    check("đang giữ", ("zalo-1", "u2") in zc._CHO_CHU)
    await doc(tin("u2", "Lịch con thứ 3, 5 nhé", 1, cua_minh=True))
    check("chủ trả lời tay: bỏ tin đang giữ", ("zalo-1", "u2") not in zc._CHO_CHU)
    lui_gio(700)
    await xa()
    check("CANARY: chủ đã trả lời thì 10 phút sau bot vẫn im", not LUOT and not GUI, (LUOT, GUI))

    # ---- 3. chủ trả lời từ Hộp thư (tiếng vọng bị lọc ở vòng đọc): Hộp thư tự báo -----------------
    don()
    await doc(tin("u3", "Chào chị", 30, cua_minh=True))
    await doc(tin("u3", "Học phí lớp 9 bao nhiêu ạ", 2))
    check("đang giữ", ("zalo-1", "u3") in zc._CHO_CHU)
    zc.bo_cho_chu("zalo-1", "u3")
    lui_gio(700)
    await xa()
    check("bo_cho_chu: bot không trả lời tin đã có người đáp", not LUOT and not GUI, (LUOT, GUI))
    src = (SERVER / "routes" / "conversations.py").read_text(encoding="utf-8")
    check("Hộp thư gọi bo_cho_chu sau khi gửi được vào chat Zalo cá nhân",
          "zc.bo_cho_chu(raw" in src and src.index("zc.bo_cho_chu(raw") > src.index("kq = await channels.gui("))

    # ---- 4. nhiều tin chờ: gộp một lượt, đủ ý, đúng thứ tự ----------------------------------------
    don()
    await doc(tin("u4", "Alo", 30, cua_minh=True))
    await doc(tin("u4", "Thầy ơi", 4), tin("u4", "con em học lớp 8", 3), tin("u4", "còn chỗ không ạ", 2))
    lui_gio(610)
    await xa()
    check("ba tin chờ thành MỘT lượt, giữ thứ tự, kèm ghi chú ở cuối",
          len(LUOT) == 1 and LUOT[0][0].startswith("Thầy ơi\ncon em học lớp 8\ncòn chỗ không ạ\n[Ghi chú của Javis"), LUOT)
    check("không có file thì ghi chú không nhắc file", LUOT and "gửi kèm" not in LUOT[0][0], LUOT)

    # ---- 5. chủ không nhắn tay: đường cũ (chờ khách 5 giây) không đổi ------------------------------
    don()
    await doc(tin("u5", "Cho em hỏi lịch học", 8))
    check("không có chủ nhắn tay thì không giữ, trả lời như thường", ("zalo-1", "u5") not in zc._CHO_CHU and len(LUOT) == 1,
          (zc._CHO_CHU.keys(), LUOT))

    # ---- 6a. nhóm, bot CHƯA ĐẶT số phút nhường: như trước 0.172.0, không giữ gì ---------------------------
    don()
    await doc(tin("g1", "Cả nhà ơi", 30, nhom=True, cua_minh=True))
    await doc(tin("g1", "Thầy ơi mai học không ạ", 2, nhom=True, **{"from": "u9"}))
    check("nhóm, bot chưa đặt: không giữ tin chờ chủ", ("zalo-1", "g1") not in zc._CHO_CHU and not LUOT, LUOT)
    zc._TAY.pop(("zalo-1", "g1"), None)

    # ---- 6. nhóm, bot ĐÃ ĐẶT số phút (0.172.0): tag thẳng trả lời ngay, tin khác chờ hết quãng rồi mỗi người một lượt
    don()
    CFG["nhuong_tay_phut"] = 10
    await doc(tin("g1", "Cả nhà ơi", 30, nhom=True, cua_minh=True))
    await doc(tin("g1", "Thầy ơi mai học không ạ", 3, nhom=True, **{"from": "u9"}),
              tin("g1", "Con em nghỉ buổi mai ạ", 2, nhom=True, **{"from": "u8"}))
    check("nhóm: tin không gọi ai được giữ chờ chủ", ("zalo-1", "g1") in zc._CHO_CHU and not LUOT, LUOT)
    zc._ID_MINH["zalo-1"] = {"uid": "me", "ten": "Toán Thầy Thành"}
    await doc(tin("g1", "@Toán Thầy Thành lớp mai học mấy giờ ạ", 1, nhom=True, **{"from": "u7"}))
    check("nhóm: tin TAG thẳng nick trả lời ngay, không chờ", len(LUOT) == 1 and "lớp mai học mấy giờ" in LUOT[0][0], LUOT)
    LUOT.clear()
    lui_gio(610)
    n = await xa()
    check("nhóm: hết quãng nhường, mỗi người một lượt (hai người, hai lượt)", n == 2 and len(LUOT) == 2, (n, LUOT))
    check("nhóm: lượt mang ghi chú chủ không nhắn thêm từ tin nhắn tay cuối",
          all("chủ nick nhắn tay lần cuối lúc" in x[0] for x in LUOT), LUOT)
    CFG.pop("nhuong_tay_phut", None)

    # ---- 6b. mốc chờ là TIN NHẮN TAY, không phải tin khách đầu tiên (chủ chốt 14/10) --------------------
    don()
    zc._TAY.pop(("zalo-1", "u2"), None)
    await doc(tin("u2", "Để thầy xem", 500, cua_minh=True))
    check("tin nhắn tay 500 giây trước: còn trong 10 phút nhường", zc.chu_vua_nhan_tay("zalo-1", "u2"))
    await doc(tin("u2", "Dạ vâng ạ", 2))
    lui_gio(110)
    await xa()
    check("đủ 10 phút tính từ tin nhắn tay thì trả lời, dù tin khách mới chờ 2 phút",
          len(LUOT) == 1 and "Dạ vâng ạ" in LUOT[0][0], LUOT)

    # ---- 7. rào: tin cũ của bộ đệm, tắt tính năng, tắt bot ----------------------------------------
    don()
    zc._TAY[("zalo-1", "u6")] = time.time()
    zc._giu_cho_chu("zalo-1", {"external_chat_id": "u6", "created_at": time.time() - zc.TUOI_TOI_DA - 5,
                               "message_type": "text", "text": "tin hôm qua"})
    check("tin cũ của bộ đệm lúc mới bật không bị giữ (không trả lời câu hỏi hôm qua)", ("zalo-1", "u6") not in zc._CHO_CHU)

    await doc(tin("u2", "Thầy đây", 20, cua_minh=True))
    zc.CHO_CHU_TRA_LOI = 0
    try:
        await doc(tin("u2", "Thầy ơi", 2))
        check("CHO_CHU_TRA_LOI = 0: như trước 0.136.0, không giữ", ("zalo-1", "u2") not in zc._CHO_CHU)
    finally:
        zc.CHO_CHU_TRA_LOI = 600

    await doc(tin("u2", "Thầy ơi", 2))
    check("đang giữ", ("zalo-1", "u2") in zc._CHO_CHU)
    tb.stop()
    lui_gio(700)
    await xa()
    check("tắt bot thì tới hạn cũng không gửi, hàng giữ bị bỏ", not LUOT and not GUI and ("zalo-1", "u2") not in zc._CHO_CHU,
          (LUOT, GUI))

    check("trạng thái vòng đọc báo thời gian chờ chủ", zc.trang_thai().get("cho_chu_tra_loi") == 600)

    # ---- file đi theo lượt (0.133.0): bot có quyền ghi thì tải được, nên ghi chú không được nói "không mở được" ----
    f = zc.chuan_hoa_tin(dict(CONN), {"threadId": "u9", "from": "u9", "type": "share.file", "id": "f9",
                                      "ts": int(time.time() * 1000), "threadType": 0, "text": "Bang-diem.xlsx",
                                      "attachment": {"url": "https://files.zdn.vn/x", "description": "Bang-diem.xlsx"}}, {})
    t = dict(f, message_type="text", text="thầy xem giúp con", metadata={}, external_message_id="t9")
    luot = zc.gop_cho_chu([f, t])
    check("lượt chờ chủ mang file theo để xu_ly tải (metadata.attachments)",
          [a.get("name") for a in (luot.get("metadata") or {}).get("attachments") or []] == ["Bang-diem.xlsx"], luot)
    check("ghi chú kể đúng tên file lấy từ attachment", "file Bang-diem.xlsx" in luot["text"], luot["text"])
    check("ghi chú không đoán bot mở được hay không (xu_ly tự ghi kết quả tải)",
          "không mở được" not in luot["text"], luot["text"])
    check("giờ trong ghi chú theo múi giờ Cài đặt, không theo đồng hồ máy chủ",
          "localefmt.tz()" in (SERVER / "zalo_personal_channel.py").read_text(encoding="utf-8"))
    check("không dùng em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read()
          and chr(0x2014) not in (SERVER / "zalo_personal_channel.py").read_text(encoding="utf-8"))


asyncio.run(chay())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
