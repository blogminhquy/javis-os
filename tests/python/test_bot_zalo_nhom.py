"""Bot chuyên trách trong NHÓM Zalo cá nhân + chế độ "Tự đánh giá" (0.64.82).

    python tests/run.py bot_zalo_nhom      (KHÔNG mạng, MCP giả)

Chủ repo thử ngày 29/09/2026: thả nick Javis Vũ vào nhóm "Digital Wave - Nội bộ", tag @Javis Vũ
và KHÔNG có gì xảy ra. Nguyên nhân là 0.64.80 cố ý bỏ mọi tin nhóm (`chat_type != "private"`),
nên tag hay không thì bot cũng không nhận. Chủ muốn thêm: không cần tag, bot tự đánh giá tin nào
đáng trả lời (câu hỏi mà tài liệu của nó trả lời được) thì mới lên tiếng.

Bốn thứ file này canh, mỗi thứ một kiểu hỏng:

  1. NHÓM ĐI QUA ĐÚNG CỬA. Nhóm chưa cho phép thì im TUYỆT ĐỐI (đây là nick người thật, một câu
     "em chưa được bật" trước mặt cả nhóm là khai ra mình là máy) nhưng phải hiện lên hàng chờ
     để chủ bấm Cho phép. Trả lời trong nhóm thì gửi type=1, không phải type=0.
  2. NHẬN RA MÌNH ĐƯỢC GỌI. Tag bằng tên trong chữ, bằng `mentions`, hay reply vào tin của bot.
     Tag người khác thì KHÔNG phải gọi bot.
  3. TỰ ĐÁNH GIÁ rẻ tới đắt: không giống câu hỏi thì bỏ, không có tài liệu thì bỏ (kèm lý do
     trong nhật ký), qua hết mới tốn một lượt model. Tag thì trả lời luôn, không qua bộ đánh giá.
  4. KHÔNG THÀNH MÁY PHÁT THANH. Chờ để nhường người đang nhắn tay, giới hạn số lần tự trả lời
     mỗi nhóm/mỗi người, và tin bị bỏ qua không được làm lệch thống kê của bot.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zpnhom-")
# Từ 0.65.1 chế độ Tự đánh giá do BỘ PHÁN XỬ quyết. File này khoá LUẬT CŨ (cửa từ khoá, hạn mức, mã bỏ qua) mà
# người vận hành còn dùng ở chế độ Chạy thử, nên ép chế độ đó: luật cũ quyết, bộ phán xử chỉ ghi.
os.environ["JAVIS_REPLY_POLICY_SHADOW"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402
import chatbot_log  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Javis Vũ", "connector_id": "zalo"}
NHOM = "5550001"        # nhóm chủ sẽ cho phép
NHOM_LA = "5550009"     # nhóm chưa ai cho phép
HV = "5550002"          # chat riêng với một học viên
UID_BOT = "5559999"     # id Zalo của chính nick bot

THREADS = [{"threadId": NHOM, "name": "Lớp Javis OS", "type": "group"},
           {"threadId": NHOM_LA, "name": "Nhóm lạ", "type": "group"},
           {"threadId": HV, "name": "Học viên A", "type": "user"}]
LIST_CALLS = []         # mỗi lần hỏi zalo_list_threads
GUI = []                # mọi lần gọi zalo_send_message
KHO_TIN = []            # tin "MCP" sẽ trả ở lần đọc kế tiếp
TRA_LOI = {"v": "Dạ để em hướng dẫn nhé"}
LUOT_ENGINE = []


def _ms(giay_truoc=0):
    return int((time.time() - giay_truoc) * 1000)


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        LIST_CALLS.append(1)
        return {"threads": [dict(t) for t in THREADS]}
    if tool == "zalo_get_messages":
        tin = list(KHO_TIN)
        KHO_TIN.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _goi_gia
zc.NHUONG_GIAY = 0.05       # test không chờ 20 giây thật
zc.THU_LAI_TEN_GIAY = 0        # và làm mới bảng cuộc chat được ngay, không chờ 15 giây


async def _engine(text, meta, progress, *, channel="", bot=None):
    LUOT_ENGINE.append({"text": text, "channel": channel, "meta": dict(meta or {}),
                        "prompt": chatbot_runtime.build_bot_prompt(bot)})
    return {"text": TRA_LOI["v"], "files": []}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-zpnhom-"))
(BRAIN / "cai-dat.md").write_text(
    "# Hướng dẫn cài đặt Javis\n\n"
    "## Lỗi cổng 7777 đang được dùng\n\n"
    "Nếu Javis báo lỗi cổng 7777 đang được dùng, hãy tắt tiến trình Javis cũ rồi khởi động lại "
    "bằng file start-javis.bat.\n\n"
    "## Đổi bộ não của Javis\n\n"
    "Vào trang Models, chọn bộ não mới ở mục Model chính rồi bấm Lưu. Đổi bộ não không làm mất "
    "bộ nhớ của Javis.\n",
    encoding="utf-8")

chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý lớp Javis OS"},
                                                  "Trả lời ngắn gọn, thân thiện."))

# ============================================================
# 0. Bộ đánh giá tầng 1: một hàm thuần, thử trực tiếp
# ============================================================
import chatbot_tu_dong as td  # noqa: E402

CAU_HOI = [
    "Javis báo lỗi cổng 7777 đang bị dùng thì làm sao ạ?",
    "cho mình hỏi cách đổi bộ não với",
    "khong vao duoc trang models, huong dan giup em",
    "Bước cài đặt Node như nào mọi người",
    "có ai biết vì sao bị lỗi không",
]
KHONG_PHAI = [
    "ok", "haha đúng rồi cả nhà ơi", "cảm ơn anh nhiều nha", "https://youtu.be/abc123xyz",
    "@Nam ơi mai họp lúc mấy giờ?", "?", "", "   ",
]
for c in CAU_HOI:
    check(f"tầng 1 nhận ra câu hỏi: {c[:40]}", td.nhin_nhu_cau_hoi(c)[0], td.nhin_nhu_cau_hoi(c))
for c in KHONG_PHAI:
    check(f"tầng 1 bỏ tin không phải câu hỏi: {c[:40]!r}", not td.nhin_nhu_cau_hoi(c)[0],
          td.nhin_nhu_cau_hoi(c))

# ============================================================
# 1. Bot gắn Zalo cá nhân, form bot bây giờ có phần nhóm
# ============================================================
zp = next(k for k in channels.cho_giao_dien() if k["id"] == "zalo_personal")
check("form bot hiện phần nhóm cho Zalo cá nhân (0.64.82 bot đứng được trong nhóm)", zp["co_nhom"], zp)

bid, loi = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b",
                                     "account_ids": ["zalo-1"], "muc_quyen": "suggest",
                                     "reply_when": "auto"})
check("tạo được bot với reply_when=auto", bool(bid) and not loi, loi)
check("reply_when=auto được lưu", chatbot_store.get_bot(bid)["reply_when"] == "auto")
chatbot_store.update_bot(bid, {"reply_when": "khong-ro"})
check("giá trị lạ bị bỏ qua, giữ nguyên auto", chatbot_store.get_bot(bid)["reply_when"] == "auto")
chatbot_store.update_bot(bid, {"reply_when": "mention"})


def _guis():
    return [g for g in GUI]


def _tin_tho():
    with conversations._conn() as cx:
        return [(r[0], r[1]) for r in cx.execute("SELECT text, sender_type FROM messages ORDER BY id").fetchall()]


def nhom_msg(text, mid, nguoi="Học viên A", uid="7770001", thread=NHOM, giay_truoc=2, **them):
    m = {"threadId": thread, "from": uid, "senderName": nguoi, "type": "text", "text": text,
         "id": mid, "ts": _ms(giay_truoc), "threadType": 1}
    m.update(them)
    return m


async def doc(cho=0.3):
    await zc.doc_mot_lan(dict(CONN))
    # Máy CI chậm thì lượt trả lời chạy nền chưa xong sau một mốc ngủ cố định (đã đỏ một lần trên CI ở 0.65.3, cùng SHA xanh
    # ở lần chạy kia). Chờ đúng các lượt đang chạy (`_VIEC`) xong, tối đa 6 giây, rồi mới ngủ thêm `cho`.
    t0 = time.time()
    while zc._VIEC and time.time() - t0 < 6:
        await asyncio.sleep(0.02)
    await asyncio.sleep(cho)


async def chay():
    ok, err = chatbot_runtime.start_bot(bid)
    check("bật bot chạy được", ok, err)

    # ---------- 1. nhóm CHƯA cho phép: im tuyệt đối nhưng hiện lên hàng chờ ------------------
    KHO_TIN.append(nhom_msg("@Javis Vũ cho hỏi lỗi cổng 7777", "a1", thread=NHOM_LA))
    KHO_TIN.append(nhom_msg("haha", "a2", thread=NHOM_LA))
    n0 = len(LUOT_ENGINE)
    await doc()
    check("nhóm chưa cho phép: KHÔNG gửi gì vào nhóm (nick thật, không khai mình là máy)",
          not GUI, GUI)
    check("và không tốn một lượt model", len(LUOT_ENGINE) == n0)
    cho = chatbot_runtime.nhom_cho(bid)
    check("nhưng nhóm hiện lên hàng chờ để chủ bấm Cho phép",
          any(x["chat_id"] == NHOM_LA for x in cho), cho)
    check("kèm tên nhóm thật", any(x.get("ten") == "Nhóm lạ" for x in cho), cho)

    # ---------- 2. nhóm đã cho phép, chế độ "được gọi tên" -----------------------------------
    chatbot_store.update_bot(bid, {"groups": [NHOM]})
    KHO_TIN.append(nhom_msg("Javis báo lỗi cổng 7777 đang bị dùng thì làm sao ạ?", "b1"))
    n0 = len(LUOT_ENGINE)
    await doc()
    check("không tag thì bot im (mặc định chỉ khi được gọi tên)", not GUI and len(LUOT_ENGINE) == n0, GUI)

    KHO_TIN.append(nhom_msg("@Javis Vũ đổi bộ não ở đâu vậy", "b2"))
    await doc()
    check("tag tên bot trong chữ thì bot trả lời đúng một lần", len(GUI) == 1, GUI)
    check("gửi vào ĐÚNG nhóm và là tin nhóm (type=1), không phải chat riêng",
          GUI and GUI[0]["threadId"] == NHOM and GUI[0]["type"] == 1, GUI)
    check("model biết ai đang hỏi trong nhóm (tên đứng đầu tin)",
          LUOT_ENGINE and LUOT_ENGINE[-1]["text"].startswith("[Học viên A]"),
          LUOT_ENGINE[-1:] and LUOT_ENGINE[-1]["text"])
    check("lượt tag thật KHÔNG bị dạy đoạn 'không ai gọi tên bạn'",
          "không ai gọi tên bạn" not in LUOT_ENGINE[-1]["prompt"])

    # tiếng vọng của câu bot vừa gửi trong nhóm: không tính là người thật nhắn tay
    KHO_TIN.append({"threadId": NHOM, "from": UID_BOT, "senderName": "Javis Vũ", "type": "text",
                    "isSelf": True, "text": GUI[0]["text"], "id": "e1", "ts": _ms(1), "threadType": 1})
    await doc(0.1)
    check("CANARY: tiếng vọng câu bot ở nhóm không thành 'chủ tự nhắn' (không thì bot tự khoá miệng)",
          not zc.chu_vua_nhan_tay("zalo-1", NHOM))
    check("và không ghi thành tin 'người thật'", ("human" not in [r[1] for r in _tin_tho()]))

    # học được id + tên của chính nick từ tin của nó, rồi nhận tag bằng `mentions`
    KHO_TIN.append({"threadId": NHOM, "from": UID_BOT, "senderName": "Javis Vũ", "type": "text",
                    "isSelf": True, "text": "Mọi người nhớ nộp bài nhé", "id": "e2", "ts": _ms(1),
                    "threadType": 1})
    await doc(0.1)
    zc._TAY.clear()     # tin trên là người tự nhắn tay, đừng để nó chặn các ca sau
    check("học được id Zalo của chính nick từ tin của nó",
          (zc._ID_MINH.get("zalo-1") or {}).get("uid") == UID_BOT, zc._ID_MINH)

    GUI.clear()
    KHO_TIN.append(nhom_msg("giá bao nhiêu vậy", "b3", mentions=[UID_BOT]))
    await doc()
    check("tag bằng `mentions` (không có tên trong chữ) vẫn nhận ra", len(GUI) == 1, GUI)

    GUI.clear()
    KHO_TIN.append(nhom_msg("cho hỏi thêm", "b4", mentions=[{"uid": UID_BOT, "pos": 0, "len": 5}]))
    await doc()
    check("`mentions` dạng object cũng nhận ra", len(GUI) == 1, GUI)

    GUI.clear()
    KHO_TIN.append(nhom_msg("vậy còn bước sau thì sao", "b5",
                            replyTo={"senderName": "Javis Vũ", "text": "Dạ để em hướng dẫn nhé",
                                     "msgId": "x"}))
    await doc()
    check("reply vào tin của bot thì bot trả lời", len(GUI) == 1, GUI)

    GUI.clear()
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg("@Nam ơi mai họp lúc mấy giờ", "b6"))
    KHO_TIN.append(nhom_msg("cảm ơn bạn nhé", "b7", replyTo={"senderName": "Nam", "text": "ok"}))
    await doc()
    check("tag người KHÁC, hoặc reply vào người khác, không phải gọi bot",
          not GUI and len(LUOT_ENGINE) == n0, GUI)

    # ---------- 2a. bot TỰ TAG người đang hỏi (0.65.7) ---------------------------------------
    # Tin có tag đi bằng CLI (`msg send --mention`) chứ không qua MCP. CLI giả ở đây; test_bot_zalo_tag.py canh chi tiết lệnh.
    import zalo_cli
    cli_goi = []
    real_cli = zalo_cli.run_cli

    async def _cli_gia(conn, command, positionals=None, options=None, timeout=120):
        cli_goi.append({"conn": dict(conn), "command": list(command), "pos": list(positionals or []), "opts": list(options or [])})
        return True, {"message": {"msgId": "t1"}}, ""

    zalo_cli.run_cli = _cli_gia
    CONN["env"] = {"HOME": "/state/zalo-1"}
    GUI.clear()
    zc._TAY.clear()
    KHO_TIN.append(nhom_msg("@Javis Vũ đổi bộ não ở đâu vậy", "t1", nguoi="Minh Quý", uid="7770777"))
    await doc()
    check("bot trả lời trong nhóm bằng tin CÓ TAG người hỏi (qua CLI), không gửi thêm bản thường qua MCP",
          len(cli_goi) == 1 and GUI == [], (cli_goi, GUI))
    check("tin mở đầu bằng '@Tên' của đúng người hỏi, tag đúng uid và đúng vị trí",
          cli_goi and cli_goi[0]["pos"] == [NHOM, "@Minh Quý " + TRA_LOI["v"]] and cli_goi[0]["opts"] == ["-t", "1", "--mention", "0:7770777:9"],
          cli_goi)
    cau_tag = cli_goi[0]["pos"][1] if cli_goi else ""
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg(cau_tag, "t2", uid="5551234", nguoi=""))
    await doc()
    check("CANARY: tiếng vọng của tin CÓ TAG (không cờ isSelf) không làm bot tự trả lời chính nó, cũng không ghi thành tin khách",
          len(LUOT_ENGINE) == n0 and (cau_tag, "customer") not in _tin_tho(), (len(LUOT_ENGINE) - n0,))
    # Mỗi tin gửi đi chỉ có MỘT tiếng vọng, nên thử kiểu có cờ isSelf trên một lượt trả lời mới.
    cli_goi.clear()
    zc._TAY.clear()
    KHO_TIN.append(nhom_msg("@Javis Vũ hướng dẫn giúp em cách đổi bộ não", "t3", nguoi="Minh Quý", uid="7770777"))
    await doc()
    cau_tag = cli_goi[0]["pos"][1] if cli_goi else ""
    KHO_TIN.append({"threadId": NHOM, "from": UID_BOT, "senderName": "Javis Vũ", "type": "text", "isSelf": True,
                    "text": cau_tag, "id": "t4", "ts": _ms(1), "threadType": 1})
    await doc(0.1)
    check("CANARY: tiếng vọng có cờ isSelf của tin CÓ TAG không thành 'chủ tự nhắn' (không thì bot im 10 phút)",
          not zc.chu_vua_nhan_tay("zalo-1", NHOM))
    zalo_cli.run_cli = real_cli
    CONN.pop("env", None)
    zc._TAY.clear()

    # ---------- 2a2. ẢNH kèm chú thích có tag (0.65.13) -------------------------------------------
    # Dạng tin ảnh THẬT của MCP (zalo-agent-cli normalizeMessage): type "chat.photo", text = chú thích, hoặc đường dẫn ảnh, hoặc "[chat.photo]" khi
    # ảnh trơn. Trước 0.65.13 mọi tin không phải chữ bị bỏ nên tag nằm trong chú thích ảnh không bao giờ tới bot (báo cáo 01/10/2026).
    GUI.clear()
    zc._TAY.clear()
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg("@Javis Vũ hướng dẫn thao tác tạo Agent giúp em", "ph1", type="chat.photo", nguoi="Ngô Văn Ngợi", uid="7770555"))
    await doc()
    check("CANARY: ảnh có chú thích TAG bot thì bot trả lời (trước đây mọi tin ảnh bị bỏ)", len(GUI) == 1 and len(LUOT_ENGINE) == n0 + 1, (GUI, len(LUOT_ENGINE) - n0))
    check("gửi vào đúng nhóm, kiểu nhóm", GUI and GUI[0]["threadId"] == NHOM and GUI[0]["type"] == 1, GUI)
    check("model nhận CHÚ THÍCH làm nội dung tin, kèm tên người gửi", LUOT_ENGINE[-1]["text"].startswith("[Ngô Văn Ngợi]") or "tạo Agent giúp em" in LUOT_ENGINE[-1]["text"],
          LUOT_ENGINE[-1]["text"])
    check("meta đánh dấu tin có ảnh, và vẫn là lượt được gọi tên", LUOT_ENGINE[-1]["meta"].get("co_anh") is True and LUOT_ENGINE[-1]["meta"].get("mentioned") is True,
          LUOT_ENGINE[-1]["meta"])
    check("model được báo tin có kèm ảnh mà nó không xem được", "kèm một ảnh" in LUOT_ENGINE[-1]["text"] and "tạo Agent giúp em" in LUOT_ENGINE[-1]["text"],
          LUOT_ENGINE[-1]["text"])
    check("Hộp thư ghi tin đó là ảnh (loại 'image') kèm chú thích", ("@Javis Vũ hướng dẫn thao tác tạo Agent giúp em", "customer") in _tin_tho())

    GUI.clear()
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg("https://f55-zpc.zdn.vn/abc/def.jpg", "ph2", type="chat.photo", nguoi="Ngô Văn Ngợi", uid="7770555"))
    KHO_TIN.append(nhom_msg("[chat.photo]", "ph3", type="chat.photo", nguoi="Ngô Văn Ngợi", uid="7770555"))
    await doc()
    check("CANARY: ảnh TRƠN (đường dẫn hoặc '[chat.photo]') vẫn bị bỏ, bot không trả lời một đường dẫn", not GUI and len(LUOT_ENGINE) == n0, (GUI, len(LUOT_ENGINE) - n0))

    GUI.clear()
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg("ảnh chụp màn hình lỗi, ai biết cách sửa không", "ph4", type="chat.photo", nguoi="Ngô Văn Ngợi", uid="7770555"))
    await doc()
    check("ảnh có chú thích nhưng KHÔNG gọi bot thì im như tin chữ (chế độ chỉ khi được gọi tên)", not GUI and len(LUOT_ENGINE) == n0, (GUI, len(LUOT_ENGINE) - n0))

    # ---------- 2b. tiếng vọng KHÔNG có cờ "của mình" -----------------------------------------
    # Ví dụ trong tài liệu của MCP không có cờ isSelf. Nếu câu bot vừa gửi quay về như tin của một
    # khách thì trong nhóm bot sẽ tự trả lời chính nó, và Hộp thư ghi câu bot nói thành tin khách.
    GUI.clear()
    zc._TAY.clear()
    TRA_LOI["v"] = "Dạ bạn vào trang Models, chọn bộ não mới ở mục Model chính rồi bấm Lưu nhé"
    KHO_TIN.append(nhom_msg("@Javis Vũ đổi bộ não thế nào vậy", "v1"))
    await doc()
    check("(chuẩn bị) bot trả lời câu tag", len(GUI) == 1, GUI)
    cau_bot = GUI[0]["text"] if GUI else ""
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg(cau_bot, "v2", uid="5551234", nguoi=""))
    await doc()
    check("CANARY: tiếng vọng không có cờ isSelf thì bot KHÔNG tự trả lời chính nó",
          len(GUI) == 1 and len(LUOT_ENGINE) == n0, (GUI, len(LUOT_ENGINE) - n0))
    check("và không bị ghi thành tin khách trong Hộp thư",
          (cau_bot, "customer") not in _tin_tho())
    KHO_TIN.append(nhom_msg("@Javis Vũ hỏi nhanh giá bao nhiêu vậy", "v3", uid=UID_BOT))
    await doc()
    check("tin từ chính id của nick (đã học) không bao giờ là khách, dù không có cờ",
          len(GUI) == 1 and len(LUOT_ENGINE) == n0, (GUI, len(LUOT_ENGINE) - n0))
    KHO_TIN.append(nhom_msg("Dạ", "v4", uid="5551235"))
    await doc(0.2)
    check("nhưng tin NGẮN của khách trùng chữ bot vừa nói ('Dạ') vẫn là tin khách",
          ("Dạ", "customer") in _tin_tho())
    TRA_LOI["v"] = "Dạ để em hướng dẫn nhé"

    # ---------- 2c. cuộc chat CHƯA BIẾT là nhóm hay chat riêng ----------------------------------
    # `zalo_get_messages` không có threadType (ví dụ của MCP chỉ có id, threadId, text, from, ts),
    # loại cuộc chat chỉ biết qua bảng `zalo_list_threads` làm mới mỗi vài phút. Nhóm nick vừa vào
    # sau lần làm mới chưa có trong bảng; nhận nhầm nó là chat riêng thì bot trả lời MỌI tin trong
    # nhóm như chat riêng và gửi sai kiểu.
    def _khong_loai(text, mid, thread, uid="7770901"):
        return {"threadId": thread, "from": uid, "senderName": "Ai đó", "type": "text",
                "text": text, "id": mid, "ts": _ms(2)}

    GUI.clear()
    NHOM_MOI, NHOM_MO = "5550055", "5550066"
    THREADS.append({"threadId": NHOM_MOI, "name": "Nhóm mới vào", "type": "group"})
    n_list = len(LIST_CALLS)
    KHO_TIN.append(_khong_loai("@Javis Vũ cho hỏi lỗi cổng 7777", "u1", NHOM_MOI))
    n0 = len(LUOT_ENGINE)
    await doc()
    check("cuộc chat lạ chưa có trong bảng thì HỎI LẠI bảng ngay, không chờ hết hạn",
          len(LIST_CALLS) > n_list, (len(LIST_CALLS), n_list))
    check("và nhận ra đó là NHÓM (hiện lên hàng chờ với tên thật), không lọt thành chat riêng",
          any(x["chat_id"] == NHOM_MOI and x.get("ten") == "Nhóm mới vào"
              for x in chatbot_runtime.nhom_cho(bid)), chatbot_runtime.nhom_cho(bid))
    check("nhóm chưa cho phép nên bot không nói gì", not GUI and len(LUOT_ENGINE) == n0, GUI)

    KHO_TIN.append(_khong_loai("Chào em, cho anh hỏi giá", "u2", NHOM_MO))
    await doc()
    check("CANARY fail-closed: hỏi lại bảng rồi mà vẫn không biết loại thì bot KHÔNG trả lời "
          "(đoán là chat riêng nghĩa là trả lời mọi tin của một nhóm)",
          not GUI and len(LUOT_ENGINE) == n0, (GUI, len(LUOT_ENGINE) - n0))
    check("nhưng tin vẫn vào Hộp thư", ("Chào em, cho anh hỏi giá", "customer") in _tin_tho())

    # ---------- 3. chế độ TỰ ĐÁNH GIÁ ----------------------------------------------------------
    chatbot_store.update_bot(bid, {"reply_when": "auto"})
    td.reset_cho_test()
    GUI.clear()
    truoc_log = len(chatbot_log.doc(bid, 500))

    KHO_TIN.append(nhom_msg("Javis báo lỗi cổng 7777 đang bị dùng thì làm sao ạ?", "c1",
                            uid="7770101", nguoi="Học viên B"))
    n0 = len(LUOT_ENGINE)
    await doc(0.4)
    check("Tự đánh giá: câu hỏi tài liệu trả lời được thì bot trả lời dù không tag",
          len(GUI) == 1 and len(LUOT_ENGINE) == n0 + 1, (GUI, len(LUOT_ENGINE) - n0))
    check("gửi vào nhóm (type=1)", GUI and GUI[0]["type"] == 1 and GUI[0]["threadId"] == NHOM, GUI)
    check("model được dạy đây là tin nhóm không ai gọi tên và quyền im lặng",
          "không ai gọi tên bạn" in LUOT_ENGINE[-1]["prompt"] and "[IM_LANG]" in LUOT_ENGINE[-1]["prompt"])
    check("và có TÀI LIỆU tra sẵn trong prompt (căn cứ để trả lời)",
          "7777" in LUOT_ENGINE[-1]["prompt"])

    # câu hỏi nhưng tài liệu không có: im, ghi lý do
    GUI.clear()
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg("Ai biết quán cà phê nào ngon gần Landmark không?", "c2", uid="7770102"))
    await doc(0.4)
    check("câu hỏi ngoài tài liệu: bot im và không tốn lượt model",
          not GUI and len(LUOT_ENGINE) == n0, (GUI, len(LUOT_ENGINE) - n0))
    ds = chatbot_log.doc(bid, 500)
    bo = [r for r in ds if r.get("bo_qua")]
    check("nhật ký ghi lý do bỏ qua để chủ chỉnh tài liệu",
          bo and bo[0]["bo_qua"] == "khong_co_tai_lieu" and "Landmark" in bo[0]["hoi"], bo[:1])
    check("lý do viết bằng tiếng Việt có dấu, người đọc hiểu",
          bo and "tài liệu" in bo[0]["dap"], bo[:1])

    # tin trò chuyện: bỏ ngay ở tầng 1, không ghi nhật ký (nhóm đông sẽ tràn nhật ký)
    dem_log = len(chatbot_log.doc(bid, 500))
    KHO_TIN.append(nhom_msg("haha đúng rồi cả nhà ơi", "c3", uid="7770103"))
    await doc(0.3)
    check("tin trò chuyện: im, và KHÔNG ghi nhật ký cho từng câu",
          not GUI and len(chatbot_log.doc(bid, 500)) == dem_log)

    # tag thì trả lời luôn, kể cả lạc đề (không qua bộ đánh giá)
    GUI.clear()
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg("@Javis Vũ hôm nay trời đẹp nhỉ", "c4", uid="7770104"))
    await doc(0.3)
    check("được tag thì trả lời luôn, không qua bộ đánh giá",
          len(GUI) == 1 and len(LUOT_ENGINE) == n0 + 1, (GUI, len(LUOT_ENGINE) - n0))
    check("lượt tag không bị dạy đoạn 'không ai gọi tên bạn'",
          "không ai gọi tên bạn" not in LUOT_ENGINE[-1]["prompt"])

    # chat riêng không đổi dù đang ở chế độ Tự đánh giá
    GUI.clear()
    KHO_TIN.append({"threadId": HV, "from": HV, "senderName": "Học viên A", "type": "text",
                    "text": "Chào em", "id": "p1", "ts": _ms(2), "threadType": 0})
    await doc()
    check("chat riêng vẫn luôn trả lời, đúng type=0",
          len(GUI) == 1 and GUI[0]["type"] == 0 and GUI[0]["threadId"] == HV, GUI)

    # bot tự chọn im (IM_LANG) trong lượt tự đánh giá
    GUI.clear()
    TRA_LOI["v"] = "[IM_LANG]"
    td.reset_cho_test()
    KHO_TIN.append(nhom_msg("Đổi bộ não của Javis ở đâu vậy mọi người?", "c5", uid="7770105"))
    await doc(0.4)
    check("bot viết [IM_LANG] thì không gửi gì", not GUI, GUI)
    check("và lượt im không tốn hạn mức tự trả lời của nhóm",
          td.duoc_tra_loi(bid, NHOM, "7770105") == "")
    TRA_LOI["v"] = "Dạ để em hướng dẫn nhé"

    # ---------- 4. nhường người đang nhắn tay ------------------------------------------------
    GUI.clear()
    td.reset_cho_test()
    zc.NHUONG_GIAY = 0.4
    KHO_TIN.append(nhom_msg("Javis báo lỗi cổng 7777 đang bị dùng thì làm sao ạ?", "d1", uid="7770106"))
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.1)
    KHO_TIN.append({"threadId": NHOM, "from": UID_BOT, "senderName": "Javis Vũ", "type": "text",
                    "isSelf": True, "text": "Để mình trả lời bạn ngay đây", "id": "d2", "ts": _ms(0),
                    "threadType": 1})
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.7)
    check("người đang nhắn tay trong lúc bot chờ thì bot NHƯỜNG, không nói chồng", not GUI, GUI)
    zc.NHUONG_GIAY = 0.05
    zc._TAY.clear()

    # tắt bot đúng lúc nó đang chờ: nút Tắt phải có tác dụng NGAY, kể cả với lượt đang ngủ
    GUI.clear()
    td.reset_cho_test()
    zc.NHUONG_GIAY = 0.4
    KHO_TIN.append(nhom_msg("Đổi bộ não của Javis ở đâu vậy mọi người?", "s1", uid="7770902"))
    await zc.doc_mot_lan(dict(CONN))
    await asyncio.sleep(0.1)
    chatbot_runtime.stop_bot(bid)
    await asyncio.sleep(0.7)
    check("CANARY: tắt bot trong lúc lượt đang chờ thì lượt đó KHÔNG được nói nữa", not GUI, GUI)
    ok, err = chatbot_runtime.start_bot(bid)
    check("bật lại được", ok and zc.co_bot("zalo-1"), err)
    zc.NHUONG_GIAY = 0.05
    zc._TAY.clear()

    # ---------- 4b. tiếng vọng trong chế độ Tự đánh giá -----------------------------------------
    # Câu bot có dấu hỏi và nói đúng chủ đề tài liệu, nên nếu nó quay về như tin khách thì bộ đánh
    # giá sẽ cho qua và bot tự trả lời chính nó. Tắt khoảng nghỉ để canary này không dựa vào nó.
    GUI.clear()
    td.reset_cho_test()
    td.TRAN_NHOM_GIO, td.TRAN_NGUOI_GIO, td.KHOANG_CACH_GIAY = 50, 50, 0
    zc._TAY.clear()
    TRA_LOI["v"] = ("Bạn thử đổi bộ não ở trang Models của Javis nhé, còn lỗi cổng 7777 thì bạn "
                    "đã tắt tiến trình cũ chưa?")
    KHO_TIN.append(nhom_msg("Đổi bộ não của Javis ở đâu vậy mọi người?", "w1", uid="7770401"))
    await doc(0.4)
    check("(chuẩn bị) bot tự trả lời câu hỏi", len(GUI) == 1, GUI)
    n0 = len(LUOT_ENGINE)
    KHO_TIN.append(nhom_msg(GUI[0]["text"] if GUI else "x", "w2", uid="5551299"))
    await doc(0.4)
    check("CANARY: tiếng vọng câu bot (có dấu hỏi, đúng chủ đề tài liệu) không kéo bot tự trả lời "
          "chính nó", len(GUI) == 1 and len(LUOT_ENGINE) == n0, (GUI, len(LUOT_ENGINE) - n0))
    TRA_LOI["v"] = "Dạ để em hướng dẫn nhé"

    # ---------- 5. hạn mức: không thành máy phát thanh --------------------------------------
    GUI.clear()
    td.reset_cho_test()
    td.TRAN_NHOM_GIO, td.TRAN_NGUOI_GIO, td.KHOANG_CACH_GIAY = 2, 5, 0
    for i, uid in enumerate(("7770201", "7770202", "7770203")):
        KHO_TIN.append(nhom_msg("Đổi bộ não của Javis ở đâu vậy mọi người?", f"cap{i}", uid=uid))
        await doc(0.4)
    check("mỗi nhóm chỉ tự trả lời tối đa TRAN_NHOM_GIO lần mỗi giờ", len(GUI) == 2, GUI)
    bo = [r for r in chatbot_log.doc(bid, 500) if r.get("bo_qua") == "het_han_muc"]
    check("lượt bị chặn vì hạn mức có ghi lý do", bool(bo), chatbot_log.doc(bid, 3))

    GUI.clear()
    td.reset_cho_test()
    td.TRAN_NHOM_GIO, td.TRAN_NGUOI_GIO = 50, 1
    for i in range(2):
        KHO_TIN.append(nhom_msg("Đổi bộ não của Javis ở đâu vậy mọi người?", f"f{i}", uid="7770301"))
        await doc(0.4)
    check("một người chỉ được bot tự trả lời TRAN_NGUOI_GIO lần mỗi giờ", len(GUI) == 1, GUI)
    check("người khác trong cùng nhóm vẫn được",
          (KHO_TIN.append(nhom_msg("Đổi bộ não của Javis ở đâu vậy mọi người?", "f9", uid="7770302")) or True)
          and (await doc(0.4) or True) and len(GUI) == 2, GUI)

    # ---------- 6. thống kê không bị tin bỏ qua làm lệch ----------------------------------
    tt = chatbot_log.tom_tat(bid)
    ds = chatbot_log.doc(bid, 500)
    n_bo = sum(1 for r in ds if r.get("bo_qua"))
    check("tóm tắt tách riêng số tin bỏ qua", tt.get("bo_qua") == n_bo and n_bo >= 2, tt)
    check("và không tính chúng vào số lượt", tt["luot"] == len(ds) - n_bo, (tt, len(ds), n_bo))
    check("cũng không làm loãng tỉ lệ bí", tt["bi"] == 0 and tt["ty_le_bi"] == 0.0, tt)

    chatbot_runtime.stop_bot(bid)


asyncio.run(chay())

# ============================================================
# 7. Luật im ở tầng chung: auto không bị `_ly_do_im` chặn nhầm, nhóm lạ vẫn bị chặn
# ============================================================
_cfg = {"id": "b", "groups": [NHOM], "reply_when": "auto"}
_nhom = {"chat_type": "group", "chat_id": NHOM}
check("auto + nhóm đã cho phép + không tag: cho đi tiếp (bộ đánh giá quyết sau)",
      chatbot_runtime._ly_do_im(_cfg, _nhom) == "")
check("auto nhưng nhóm chưa cho phép vẫn im",
      chatbot_runtime._ly_do_im(dict(_cfg, groups=[]), _nhom) == "nhom_chua_bat")
check("mention + không tag vẫn im như cũ",
      chatbot_runtime._ly_do_im(dict(_cfg, reply_when="mention"), _nhom) == "khong_goi_ten")
check("CANARY fail-closed: giá trị reply_when lạ thì im, không mở",
      chatbot_runtime._ly_do_im(dict(_cfg, reply_when="tu-dong-di"), _nhom) == "khong_goi_ten")
check("chỉ 'auto' đúng chữ mới bật bộ đánh giá",
      td.can_danh_gia(_cfg, _nhom) and not td.can_danh_gia(dict(_cfg, reply_when="always"), _nhom)
      and not td.can_danh_gia(_cfg, dict(_nhom, mentioned=True))
      and not td.can_danh_gia(_cfg, dict(_nhom, reply_to_bot=True))
      and not td.can_danh_gia(_cfg, {"chat_type": "private", "chat_id": HV}))

# ============================================================
# 8. Học id của chính nick: sai id còn tệ hơn không có id
# ============================================================
zc._ID_MINH.clear()
zc._hoc_danh_tinh("c1", {"threadId": "5550777", "from": "5550777", "senderName": "Khách", "isSelf": True})
check("CANARY: id trùng id cuộc chat thì KHÔNG học (không thì cả khách đó bị bỏ rơi)",
      not (zc._ID_MINH.get("c1") or {}).get("uid"), zc._ID_MINH)
zc._hoc_danh_tinh("c2", {"threadId": "5550001", "from": "5559999"})
check("một id nhất quán thì tin", zc._ID_MINH["c2"]["uid"] == "5559999")
zc._hoc_danh_tinh("c2", {"threadId": "5550002", "from": "5558888"})
check("hai id khác nhau cho cùng một nick nghĩa là cờ 'của mình' không đáng tin: bỏ id",
      zc._ID_MINH["c2"]["uid"] == "", zc._ID_MINH["c2"])
check("nhận diện tag không dựa vào id đã bị bỏ",
      zc.nhan_dien_goi("c2", {"text": "hi", "metadata": {"mentions": ["5559999"]}}) == (False, False))

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
