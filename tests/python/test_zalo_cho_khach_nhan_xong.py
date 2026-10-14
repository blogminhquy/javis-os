"""Zalo cá nhân: bot chờ khách nhắn xong rồi mới trả lời MỘT lần (0.128.0).

    python tests/run.py cho_khach_nhan_xong      (KHÔNG mạng, MCP giả)

Chủ nick yêu cầu 14/10/2026: khách hay nhắn một ý thành mấy tin liền ("Thầy ơi" / "cho em hỏi" /
"lớp 9 còn chỗ không ạ"). Giao từng tin ngay thì bot đáp câu chào trước khi câu hỏi tới, lộ ngay
là máy. Từ 0.128.0 tin khách chat riêng được gom theo cuộc chat và chỉ giao khi khách đã im
`CHO_KHACH_IM` giây, xác nhận bằng một lượt đọc.

Test KHÔNG chờ giờ thật: giờ tin đặt lùi về quá khứ, và mốc xả hàng chờ truyền tay vào `xa_hang_cho`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpcho-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_gateway  # noqa: E402
import channels  # noqa: E402,F401
import conversations  # noqa: E402,F401
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Zalo của tôi", "connector_id": "zalo"}
GUI = []            # mọi lần gọi zalo_send_message
KHO_TIN = []        # tin "MCP" trả ở lần đọc kế tiếp
LUOT = []           # mọi lượt bot (chữ, meta) tới answer_fn
_id = [0]


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": t, "name": "Khách " + t, "type": "user"} for t in ("u1", "u2", "u3", "u4")]
                + [{"threadId": "g1", "name": "Nhóm", "type": "group"}]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
# Vòng đọc nền không chạy song song với các bước tay bên dưới (nó cũng lấy tin trong KHO_TIN). Mục 8 chạy
# chính vòng đó, có kiểm soát.
_start_that = zc.start
zc.start = lambda: True


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
    return {"text": "Dạ thầy chào anh chị ạ", "files": []}


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


async def chay():
    check("mặc định chờ 5 giây, đọc dày 2 giây khi có khách vừa nhắn",
          zc.CHO_KHACH_IM == 5 and zc.NHIP_NHANH == 2 and zc.NHIP == 20)
    tb = lam_bot()
    tb.start()

    # ---- 1. ba tin liền nhau trong 5 giây: MỘT lượt, đủ ba ý, đúng thứ tự ---------------------
    await doc(tin("u1", "Thầy ơi", 4), tin("u1", "cho em hỏi", 3), tin("u1", "lớp 9 còn chỗ không ạ", 1))
    check("tin vừa tới, khách mới im 3 giây: bot CHƯA trả lời", not LUOT and not GUI, LUOT)
    check("cuộc chat đang chờ làm tài khoản đọc theo nhịp dày", zc._nhip_cua("zalo-1") == zc.NHIP_NHANH)
    check("nhưng chưa đủ 5 giây im thì vẫn chưa xả", await xa(2) == 0 and not LUOT)
    n = await xa(5)
    check("khách im đủ 5 giây: đúng MỘT lượt", n == 1 and len(LUOT) == 1 and len(GUI) == 1, (n, LUOT, GUI))
    check("lượt gộp đủ ba tin theo đúng thứ tự, nối bằng xuống dòng như hàng chờ bot_gateway",
          LUOT and LUOT[0][0] == "Thầy ơi\ncho em hỏi\nlớp 9 còn chỗ không ạ", LUOT[:1])
    check("lượt mang mã tin CUỐI (Hộp thư nhận ra tin đã có, không ghi trùng)",
          LUOT and LUOT[0][1]["message_id"] == f"m{_id[0]}", LUOT[:1])
    check("trả lời đúng người, chat riêng", GUI and GUI[0]["threadId"] == "u1" and GUI[0]["threadType"] == 0, GUI)
    check("xả rồi thì hàng chờ trống", not any(k[0] == "zalo-1" for k in zc._GOM))

    # ---- 2. hai tin cách nhau 8 giây: HAI lượt -------------------------------------------------
    don()
    # Nhịp đọc dày 2 giây nên giữa hai tin có một lượt đọc thấy khách đã im đủ 5 giây.
    await doc(tin("u2", "Cho em xin lịch học", 14))
    check("tin đầu đã im 14 giây khi được đọc: xả ngay sau lượt đọc đó", len(LUOT) == 1, LUOT)
    await doc(tin("u2", "À thêm học phí nữa ạ", 6))
    check("tin thứ hai, 8 giây sau: lượt thứ hai riêng", len(LUOT) == 2 and len(GUI) == 2, LUOT)
    check("mỗi lượt đúng một tin", [x[0] for x in LUOT] == ["Cho em xin lịch học", "À thêm học phí nữa ạ"], LUOT)

    # ---- 3. chủ nhắn tay trong cửa sổ: bot im ---------------------------------------------------
    don()
    await doc(tin("u3", "Thầy ơi", 3), tin("u3", "con em học lớp 8", 2))
    check("đang chờ khách nhắn xong", ("zalo-1", "u3") in zc._GOM)
    await doc(tin("u3", "Để thầy gọi lại cho chị nhé", 1, cua_minh=True))
    check("chủ tự nhắn: bỏ hàng chờ của cuộc chat đó", ("zalo-1", "u3") not in zc._GOM)
    await xa(30)
    check("chủ nhắn tay trong cửa sổ thì bot im, không tốn lượt model", not LUOT and not GUI, (LUOT, GUI))
    await doc(tin("u3", "Dạ vâng ạ", 1))
    await xa(30)
    check("khách nhắn tiếp trong lúc chủ đang nói chuyện: bot vẫn nhường", not LUOT and not GUI, (LUOT, GUI))

    # ---- 4. tắt bot giữa chừng: không gửi; lưu cài đặt (khởi động lại bot): vẫn trả lời -----------
    don()
    await doc(tin("u4", "Cho em hỏi", 3), tin("u4", "học phí bao nhiêu ạ", 2))
    check("đang chờ", ("zalo-1", "u4") in zc._GOM)
    tb.stop()
    check("không còn bot thì về nhịp đọc thường", zc._nhip_cua("zalo-1") == zc.NHIP)
    await xa(30)
    check("tắt bot: tới lượt xả mà không còn bot thì hàng chờ bị bỏ",
          not any(k[0] == "zalo-1" for k in zc._GOM))
    tb2 = lam_bot()
    tb2.start()
    await xa(30)
    check("tắt bot giữa chừng thì không gửi gì, kể cả khi bật lại bot sau đó", not LUOT and not GUI, (LUOT, GUI))
    don()
    await doc(tin("u5", "Cho em hỏi", 3), tin("u5", "lớp 9 còn chỗ không ạ", 2))
    tb2.stop()          # lưu cài đặt bot = start_bot: dừng rồi đăng ký lại ngay
    tb3 = lam_bot()
    tb3.start()
    await xa(30)
    check("CANARY: lưu cài đặt bot giữa lúc khách đang nhắn thì khách vẫn được trả lời đúng một lần",
          len(LUOT) == 1 and "lớp 9 còn chỗ không ạ" in LUOT[0][0], LUOT)
    tb2 = tb3

    # ---- 5. nhóm không gom, ảnh + chữ gộp thành câu hỏi kèm ảnh ---------------------------------
    don()
    check("gộp ảnh trơn rồi chữ: lượt là tin ảnh mang link, chữ là câu hỏi",
          (lambda e: e["message_type"] == "image" and e["metadata"]["image_url"] == "https://x/a.jpg"
           and e["text"] == "xem giúp em bài này")(zc.gop_tin([
               {"message_type": "image", "text": "https://x/a.jpg", "metadata": {"image_url": "https://x/a.jpg"},
                "external_message_id": "a"},
               {"message_type": "text", "text": "xem giúp em bài này", "metadata": {}, "external_message_id": "b"}])))
    check("tiếng/sticker chỉ tính là còn đang nhắn, không góp chữ",
          zc.gop_tin([{"message_type": "sticker", "text": "[Zalo cá nhân: khách gửi sticker]", "metadata": {}},
                      {"message_type": "text", "text": "ạ", "metadata": {}}])["text"] == "ạ")
    check("CANARY: khách mở bằng nhiều câu chào thì câu hỏi thật (tin cuối) vẫn tới bot",
          bot_gateway.noi_tin(["Thầy ơi"] * 6 + ["lớp 9 còn chỗ không ạ"]).endswith("lớp 9 còn chỗ không ạ"))
    check("gộp giữ đúng thứ tự và trần ký tự của hàng chờ bot_gateway",
          bot_gateway.noi_tin([str(i) for i in range(9)]) == "\n".join(str(i) for i in range(9))
          and len(bot_gateway.noi_tin(["x" * 3000, "y" * 3000])) <= bot_gateway.MAX_CHO_KY_TU)
    zc._ID_MINH.pop("zalo-1", None)
    goc = zc._GOM.copy()
    await doc(tin("g1", "Cả nhà ơi", 2, nhom=True, **{"from": "u9"}))
    check("tin NHÓM không vào hàng chờ (đi thẳng như trước)", zc._GOM == goc)

    # ---- 6. tắt cửa sổ (0) thì giao từng tin ngay như trước 0.128.0 -----------------------------
    don()
    zc.CHO_KHACH_IM = 0
    try:
        await doc(tin("u1", "Alo", 1))
        check("CHO_KHACH_IM = 0: trả lời ngay, không gom", len(LUOT) == 1 and not zc._GOM, (LUOT, zc._GOM))
        check("và không đọc dày", zc._nhip_cua("zalo-1") == zc.NHIP)
    finally:
        zc.CHO_KHACH_IM = 5

    # ---- 7. nhịp đọc: chỉ tài khoản nóng, hết nóng thì về 20 giây -------------------------------
    zc._NONG["zalo-1"] = time.time() - zc.NONG_GIAY - 1
    check("khách im quá 60 giây và không còn gì chờ: về nhịp 20 giây", zc._nhip_cua("zalo-1") == zc.NHIP)
    check("tài khoản không có bot không bao giờ đọc dày", zc._nhip_cua("zalo-khac") == zc.NHIP)
    check("vòng ngủ 20 giây khi không tài khoản nào nóng", zc._nhip_vong() == zc.NHIP)

    # ---- 8. vòng đọc thật (nhịp thu nhỏ): chỉ tài khoản nóng đọc dày ---------------------------
    # zalo-1 có bot và vừa có tin khách chat riêng; zalo-2 chỉ bật ghi Hộp thư, không bot.
    dem = {"zalo-1": 0, "zalo-2": 0}
    goi_cu, ket_noi_cu, cau_hinh_cu = zc._goi, zc._ket_noi, zc._cau_hinh
    nhip_cu = (zc.NHIP, zc.NHIP_NHANH)

    async def _goi_dem(conn, tool, args):
        if tool == "zalo_get_messages":
            dem[conn["id"]] += 1
            return {"messages": [], "nextCursor": "1"}
        return await goi_cu(conn, tool, args)

    zc._goi = _goi_dem
    zc._ket_noi = lambda: [dict(CONN), {"id": "zalo-2", "label": "Zalo hai", "connector_id": "zalo"}]
    zc._cau_hinh = lambda: {"zalo-2": True}
    zc.NHIP, zc.NHIP_NHANH = 1.0, 0.25
    zc._NONG["zalo-1"] = time.time()
    try:
        _start_that()
        await asyncio.sleep(2.2)
    finally:
        zc.stop()
        zc._goi, zc._ket_noi, zc._cau_hinh = goi_cu, ket_noi_cu, cau_hinh_cu
        zc.NHIP, zc.NHIP_NHANH = nhip_cu
    check("tài khoản nóng đọc theo nhịp dày (khoảng 4 lần mỗi nhịp thường)", dem["zalo-1"] >= 6, dem)
    check("tài khoản không nóng vẫn đọc theo nhịp thường, không bị kéo theo", 2 <= dem["zalo-2"] <= 4, dem)
    tb2.stop()


asyncio.run(chay())
print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
