"""Hộp thư hội thoại khách (Chatbot V2, bản V1): kho, adapter bot chuyên trách, adapter Zalo cá nhân.

    python tests/run.py hoi_thoai_khach      (KHÔNG mạng)

Cột sống của cả tính năng là một câu: MỘT tin Telegram hoặc Zalo đi vào Javis, được lưu đúng
Khách -> Hội thoại -> Tin, rồi mở trang Hội thoại đọc lại được. Test này canh đúng câu đó, ở
ba lớp:

1. **Kho** (`conversations.py`): sự kiện chuẩn vào là tài khoản kênh, khách, hội thoại, tin
   đều có; tin trùng id không sinh hai dòng; chưa đọc chỉ đếm tin KHÁCH; thống kê đúng; tên
   file kho KHÔNG đụng kho phiên (`conversations.db` là của sessions.py).
2. **Bot chuyên trách** (`chatbot_runtime`): một lượt ghi CẢ tin khách lẫn câu bot, kể cả khi
   engine gãy (khách vẫn thấy câu xin lỗi, nên câu xin lỗi cũng là hội thoại). Người thật tiếp
   quản thì bot IM nhưng tin khách vẫn vào kho. Lượt bị chặn ở tầng nhóm KHÔNG vào kho.
3. **Zalo cá nhân** (`zalo_personal_channel`): tin của MCP về đúng khuôn chung, chat riêng lấy
   tên từ bảng thread, tin do chính chủ gửi là tin người thật, cursor được lưu và gửi lại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-hoithoai-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import zalo_personal_channel as zp  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL kho không nằm trong thư mục tạm: {conversations.DB_PATH}. DỪNG.")
    sys.exit(1)

# ============================================================
# 1. Kho
# ============================================================
check("tên file kho KHÔNG phải conversations.db (tên đó là của kho phiên)",
      Path(conversations.DB_PATH).name != "conversations.db")

r = conversations.ghi_su_kien({
    "channel": "telegram", "account_id": "bot_1", "account_name": "Bot Bán Hàng", "bot_id": "bot_1",
    "external_chat_id": "1001", "chat_type": "private",
    "sender_type": "customer", "sender_id": "1001", "sender_name": "Nguyễn A",
    "text": "còn size 42 không?", "external_message_id": "m1",
})
check("ghi tin khách: ok, có id hội thoại và id khách",
      r.get("ok") and r.get("conversation_id") and r.get("customer_id"))
conv_id = r["conversation_id"]

r2 = conversations.ghi_su_kien({
    "channel": "telegram", "account_id": "bot_1", "bot_id": "bot_1",
    "external_chat_id": "1001", "sender_type": "ai", "sender_name": "Bot Bán Hàng",
    "text": "Dạ còn anh ạ.",
})
check("câu bot vào CÙNG hội thoại", r2.get("ok") and r2["conversation_id"] == conv_id)

r3 = conversations.ghi_su_kien({
    "channel": "telegram", "account_id": "bot_1", "bot_id": "bot_1",
    "external_chat_id": "1001", "sender_type": "customer", "sender_id": "1001",
    "text": "còn size 42 không?", "external_message_id": "m1",
})
check("tin trùng id kênh KHÔNG sinh dòng thứ hai", r3.get("ok") and r3.get("trung") is True)

ds = conversations.danh_sach()
check("danh sách có đúng một hội thoại", len(ds) == 1)
c = ds[0]
check("hội thoại mang tên khách, kênh, tin cuối là câu bot",
      c["title"] == "Nguyễn A" and c["channel"] == "telegram"
      and c["last_message"] == "Dạ còn anh ạ." and c["last_sender_type"] == "ai")
check("chưa đọc chỉ đếm tin KHÁCH (1), tổng tin là 2",
      c["unread_count"] == 1 and c["message_count"] == 2)

tin = conversations.tin_nhan(conv_id)
check("lịch sử tin cũ trước mới sau, đủ hai tin",
      [t["sender_type"] for t in tin] == ["customer", "ai"])

check("đánh dấu đã đọc về 0", conversations.danh_dau_da_doc(conv_id)
      and conversations.chi_tiet(conv_id)["unread_count"] == 0)

# Nhóm: khách là NGƯỜI GỬI, không phải cuộc chat
rg = conversations.ghi_su_kien({
    "channel": "telegram", "account_id": "bot_1", "bot_id": "bot_1",
    "external_chat_id": "-500", "chat_type": "supergroup", "chat_title": "Nhóm khách sỉ",
    "sender_type": "customer", "sender_id": "2002", "sender_name": "Minh B", "text": "giá sỉ?",
})
ctg = conversations.chi_tiet(rg["conversation_id"])
check("nhóm: tiêu đề là tên nhóm, loại group, khách là người gửi",
      ctg["title"] == "Nhóm khách sỉ" and ctg["chat_type"] == "group"
      and ctg["customer_name"] == "Minh B")

tk = conversations.thong_ke(bot_id="bot_1")
check("thống kê theo bot: 2 hội thoại, 1 chưa đọc, theo kênh telegram=2",
      tk["tong"] == 2 and tk["chua_doc"] == 1 and tk["theo_kenh"].get("telegram") == 2)
check("thống kê bot lạ trả 0", conversations.thong_ke(bot_id="khong_co")["tong"] == 0)

check("sự kiện thiếu kênh hợp lệ bị từ chối, KHÔNG ném",
      conversations.ghi_su_kien({"channel": "viber", "external_chat_id": "x"}).get("ok") is False)
check("chế độ mặc định là ai; đặt human rồi đọc lại đúng",
      conversations.che_do("telegram", "bot_1", "1001") == "ai"
      and conversations.dat_che_do(conv_id, "human")[0]
      and conversations.che_do("telegram", "bot_1", "1001") == "human")
check("chế độ lạ bị từ chối", conversations.dat_che_do(conv_id, "bay")[0] is False)
conversations.dat_che_do(conv_id, "ai")
check("tìm theo tên khách", len(conversations.danh_sach(q="nguyễn")) == 1)
check("loại tin đoán từ dòng gateway: ảnh -> image, chữ thường -> text",
      conversations.loai_tin_tu_chu("[Người dùng gửi ảnh qua Telegram, gateway đã tải về: /x.jpg]") == "image"
      and conversations.loai_tin_tu_chu("xin chào") == "text")

# ============================================================
# 2. Bot chuyên trách -> kho
# ============================================================
BRAIN = Path(tempfile.mkdtemp(prefix="javis-hoithoai-brain-"))
(BRAIN / "inbox" / "khach").mkdir(parents=True)
_dap = {"text": "Dạ shop còn size 42 ạ.", "files": []}


async def _answer_gia(text, meta=None, progress=None, channel="telegram", bot=None):
    return dict(_dap) if isinstance(_dap, dict) else _dap


chatbot_runtime.wire(answer=_answer_gia, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda b, s: ({"name": "Hoa"}, ""))
bid, err = chatbot_store.create_bot({"name": "Bot Giày", "agent_slug": "cskh", "brain": "b",
                                     "token": "1:x", "channel": "zalo"})
check("tạo được bot test", bool(bid) and not err)
fn = chatbot_runtime._make_answer_fn(bid)
meta = {"chat_id": "77", "chat_type": "private", "user_name": "Lan C", "user_id": "77",
        "message_id": 501, "platform": "zalo"}
ra = asyncio.run(fn("còn size 42?", meta))
check("lượt chạy bình thường trả câu bot", ra.get("text") == _dap["text"])
ds = conversations.danh_sach(bot_id=bid)
check("CANARY: lượt bot ghi thành MỘT hội thoại kênh Zalo Bot, có tên khách",
      len(ds) == 1 and ds[0]["channel"] == "zalo" and ds[0]["customer_name"] == "Lan C")
tin = conversations.tin_nhan(ds[0]["id"])
check("hội thoại có đủ tin khách rồi tin bot, đúng nội dung",
      [t["sender_type"] for t in tin] == ["customer", "ai"]
      and tin[0]["text"] == "còn size 42?" and tin[1]["text"] == _dap["text"]
      and tin[0]["external_message_id"] == "501")

# Engine gãy: khách nhận câu xin lỗi -> câu đó cũng phải nằm trong hội thoại, kèm lý do cho chủ
_dap = "⚠ Model 'x' không chạy được"
asyncio.run(fn("hỏi nữa", {**meta, "message_id": 502}))
tin = conversations.tin_nhan(ds[0]["id"])
check("lượt gãy: tin khách vẫn vào kho và câu xin lỗi là tin bot kèm lý do kỹ thuật",
      len(tin) == 4 and tin[3]["sender_type"] == "ai" and "trục trặc" in tin[3]["text"]
      and "không chạy được" in (tin[3]["metadata"] or {}).get("loi", ""))
_dap = {"text": "Dạ có ạ.", "files": []}

# Người thật tiếp quản: bot IM, tin khách vẫn vào
conversations.dat_che_do(ds[0]["id"], "human")
ra = asyncio.run(fn("có ship COD không?", {**meta, "message_id": 503}))
tin = conversations.tin_nhan(ds[0]["id"])
check("CANARY: người thật tiếp quản -> bot im (im_lang), tin khách vẫn vào kho",
      ra.get("im_lang") is True and not ra.get("text")
      and tin[-1]["sender_type"] == "customer" and tin[-1]["text"] == "có ship COD không?")
conversations.dat_che_do(ds[0]["id"], "ai")
ra = asyncio.run(fn("còn không?", {**meta, "message_id": 504}))
check("trả lại AI -> bot trả lời lại", ra.get("text") == "Dạ có ạ.")

# Nhóm chưa được cho phép: lớp hai trong answer_fn im lặng và KHÔNG ghi gì
truoc = conversations.thong_ke(bot_id=bid)["tin"]
ra = asyncio.run(fn("bot ơi", {"chat_id": "-9", "chat_type": "group", "user_name": "X",
                                "message_id": 9, "mentioned": True}))
check("nhóm chưa cho phép: bot im và KHÔNG ghi vào kho",
      ra.get("im_lang") is True and conversations.thong_ke(bot_id=bid)["tin"] == truoc)

# Lệnh cũng là hội thoại
cmd = chatbot_runtime._make_command_fn(chatbot_store.get_bot(bid))
res = asyncio.run(cmd("help", "", "77", {**meta, "message_id": 505}))
tin = conversations.tin_nhan(ds[0]["id"])
check("lệnh /help ghi cả câu lệnh lẫn câu bot đáp",
      res and res.get("reply") and tin[-2]["text"] == "/help" and tin[-1]["text"] == res["reply"])

# Thẻ bot: số hội thoại
tk = conversations.thong_ke(bot_id=bid)
check("thống kê cho thẻ bot: 1 hội thoại, có tin hôm nay", tk["tong"] == 1 and tk["hom_nay"] == 1)

# ============================================================
# 3. Zalo cá nhân: chuẩn hoá tin MCP và vòng đọc
# ============================================================
conn = {"id": "zl_1", "label": "Zalo Quý", "connector_id": "zalo"}
ten = {"u456": {"name": "Phúc", "type": "user"}, "g789": {"name": "Nhóm dự án", "type": "group"}}
ev = zp.chuan_hoa_tin(conn, {"id": "msg123", "threadId": "u456", "text": "Xin chào", "from": "u456",
                             "ts": 1710000000}, ten)
check("tin DM Zalo: kênh zalo_personal, khách lấy tên từ bảng thread, ts giây",
      ev["channel"] == "zalo_personal" and ev["chat_type"] == "private"
      and ev["sender_name"] == "Phúc" and ev["created_at"] == 1710000000
      and ev["external_message_id"] == "msg123" and ev["account_id"] == "zl_1")
ev2 = zp.chuan_hoa_tin(conn, {"msgId": "m2", "threadId": "g789", "threadType": 1, "senderName": "Minh",
                              "text": "ok anh", "timestamp": 1710000000000, "type": "text"}, ten)
check("tin nhóm Zalo: group, tiêu đề nhóm, tên người gửi, ts mili về giây",
      ev2["chat_type"] == "group" and ev2["chat_title"] == "Nhóm dự án"
      and ev2["sender_name"] == "Minh" and ev2["created_at"] == 1710000000)
ev3 = zp.chuan_hoa_tin(conn, {"id": "m3", "threadId": "u456", "text": "em gửi rồi", "isSelf": True}, ten)
check("tin chính chủ gửi từ điện thoại là tin NGƯỜI THẬT, không phải khách",
      ev3["sender_type"] == "human" and ev3["sender_id"] == "")
ev4 = zp.chuan_hoa_tin(conn, {"id": "m4", "threadId": "u456", "type": "image"}, ten)
check("tin ảnh không chữ vẫn có mô tả và loại image",
      ev4["message_type"] == "image" and "image" in ev4["text"])
check("tin không thread bị bỏ", zp.chuan_hoa_tin(conn, {"id": "x", "text": "?"}, ten) is None)

# Vòng đọc: giả MCP, kiểm cursor được gửi lại và lưu
_goi_log = []


async def _goi_gia(c, tool, args):
    _goi_log.append((tool, dict(args or {})))
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": "u456", "name": "Phúc", "type": "user"}]}
    return {"messages": [{"id": "z1", "threadId": "u456", "text": "Shop ơi", "from": "u456", "ts": 1710000001}],
            "nextCursor": "cur_abc", "hasMore": False}


zp._goi = _goi_gia
kq = asyncio.run(zp.doc_mot_lan(conn))
check("vòng đọc ghi 1 tin mới, lần đầu KHÔNG gửi cursor",
      kq["moi"] == 1 and _goi_log[0][0] == "zalo_get_messages" and "cursor" not in _goi_log[0][1])
check("cursor lưu vào sync_state", conversations.doc_trang_thai("zalo_personal:zl_1:cursor") == "cur_abc")
kq = asyncio.run(zp.doc_mot_lan(conn))
check("lần hai gửi lại cursor, tin cũ tính là trùng",
      _goi_log[-1][1].get("cursor") == "cur_abc" and kq["trung"] == 1 and kq["moi"] == 0)
dz = conversations.danh_sach(channel="zalo_personal")
check("hội thoại Zalo cá nhân hiện trong danh sách với tên Phúc",
      len(dz) == 1 and dz[0]["customer_name"] == "Phúc" and dz[0]["account_name"] == "Zalo Quý")

# Bật/tắt theo tài khoản: mặc định TẮT (giữ phiên Zalo sống 24/7 là lựa chọn của chủ)
check("mặc định KHÔNG ghi tài khoản Zalo nào", zp.dang_bat("zl_1") is False)
check("bật một id không tồn tại bị từ chối", zp.bat("khong_co", True).get("ok") is False)

# ============================================================
# 4. Đường vào giao diện: trang, bí danh, route
# ============================================================
import ui_targets  # noqa: E402
check("trang conversations có trong PAGES", "conversations" in ui_targets.PAGES)
check("bí danh 'hộp thư khách' về trang conversations, 'hội thoại' trần vẫn là chat",
      ui_targets.ALIASES.get("hop thu khach") == "conversations"
      and ui_targets.ALIASES.get("hoi thoai") == "chat")
_js = (ROOT / "dashboard" / "ui-actions.js").read_text(encoding="utf-8")
_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
_html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
check("ui-actions.js và console.js cùng biết trang conversations",
      '"conversations"' in _js and 'conversations: "messages-square"' in _console
      and 'renderConversations' in _console)
check("index.html nạp conversations.js TRƯỚC console.js",
      _html.find("/static/conversations.js") > 0
      and _html.find("/static/conversations.js") < _html.find("/static/console.js?v="))
import routes.conversations as rc  # noqa: E402
_src = (SERVER / "routes" / "conversations.py").read_text(encoding="utf-8")
check("router có đủ đường: danh sách, tin, đã đọc, chế độ, kênh, bật Zalo",
      all(x in _src for x in ('"/conversations"', '"/conversations/{conv_id}/messages"',
                              '"/conversations/{conv_id}/read"', '"/conversations/{conv_id}/mode"',
                              '"/conversations/channels"', '"/conversations/zalo/{conn_id}/watch"'))
      and not hasattr(rc, "main"))
_main = (SERVER / "main.py").read_text(encoding="utf-8")
check("main.py đăng ký router, bật vòng Zalo lúc khởi động và dừng lúc tắt",
      "conversations_routes.register(app" in _main
      and "zalo_personal_channel.start()" in _main and "zalo_personal_channel.stop()" in _main)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
