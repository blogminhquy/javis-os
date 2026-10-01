"""Zalo: tin ảnh có CHÚ THÍCH tag bot thì bot phải trả lời (0.65.13).

    python tests/run.py zalo_anh_chu_thich      (KHÔNG mạng)

Chủ dự án (01/10/2026), từ báo cáo của một Agent trong nhóm: anh Ngô Văn Ngợi gửi ảnh kèm chú thích "@Javis Vũ <câu hỏi>" mà bot im, trong khi hai tin chữ
có tag thì được trả lời. Nguyên nhân: `Transport.xu_ly` bỏ MỌI tin không phải chữ, nên tag nằm trong chú thích của ảnh không bao giờ tới bot.

Dạng tin ảnh THẬT của MCP đọc từ mã nguồn zalo-agent-cli v1.6.2 (`normalizeMessage` ở `src/commands/mcp.js`): `type` = "chat.photo", và
`text = content.title || content.href || "[chat.photo]"`: ảnh CÓ chú thích thì `text` là chú thích; ảnh trơn thì `text` là đường dẫn ảnh hoặc "[chat.photo]". Bộ đệm
của MCP KHÔNG có trường `mentions`, nên tag chỉ nhận ra được bằng chữ "@Tên" trong chú thích.

Những chỗ phải đúng:
  1. Chú thích thật thì lấy; đường dẫn ảnh, "[chat.photo]" và chữ giữ chỗ của Javis thì KHÔNG phải lời của người gửi (bot không được trả lời một đường dẫn).
  2. Ảnh có chú thích đi vào bot như tin chữ (cả nhận tag lẫn trả lời), và model được báo tin có kèm ảnh mà nó không xem được.
  3. Ảnh trơn vẫn bị bỏ qua.
  4. Lượt chủ nhờ bot trả lời từ Hòm thư cũng hiểu tin ảnh.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-anh-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


# ============================================================
# 1. Chú thích thật hay chữ "nền"
# ============================================================
ct = conversations.chu_thich_anh
check("chú thích thật được giữ nguyên", ct("@Javis Vũ lỗi này xử lý sao ạ?") == "@Javis Vũ lỗi này xử lý sao ạ?")
check("khoảng trắng và xuống dòng được gộp", ct("  @Javis Vũ \n xem giúp  ") == "@Javis Vũ xem giúp")
check("CANARY: đường dẫn ảnh (ảnh trơn, MCP lấy content.href) KHÔNG phải chú thích", ct("https://f55-zpc.zdn.vn/abc/def.jpg") == "" and ct("http://x.vn/a.png") == "")
check("CANARY: chữ giữ chỗ '[chat.photo]' của MCP KHÔNG phải chú thích", ct("[chat.photo]") == "" and ct("[photo]") == "" and ct("[image]") == "")
check("chữ giữ chỗ do Javis tự thêm cũng không phải chú thích", ct("[Zalo cá nhân: khách gửi image]") == "")
check("rỗng và None thì rỗng", ct("") == "" and ct(None) == "" and ct("   ") == "")
check("chú thích CÓ chứa đường dẫn vẫn là chú thích (chỉ loại khi cả tin chỉ là đường dẫn)", ct("xem ảnh này https://x.vn/a.jpg nhé") == "xem ảnh này https://x.vn/a.jpg nhé")
check("chú thích bắt đầu bằng '[' nhưng là lời thật vẫn giữ", ct("[Gấp] @Javis Vũ trả lời giúp") == "[Gấp] @Javis Vũ trả lời giúp")

# ============================================================
# 2. Chuẩn hoá tin ảnh đúng dạng MCP
# ============================================================
conn = {"id": "zalo-1", "label": "Javis Vũ"}
ten = {"G1": {"name": "Zoom | Javis OS", "type": "group"}}
anh = {"id": "m1", "threadId": "G1", "from": "7770555", "senderName": "Ngô Văn Ngợi", "type": "chat.photo",
       "text": "@Javis Vũ hướng dẫn thao tác tạo Agent", "threadType": 1, "ts": 1790000000000}
ev = zc.chuan_hoa_tin(conn, anh, ten)
check("tin ảnh có chú thích: loại 'image', text là chú thích (không mất)", ev["message_type"] == "image" and ev["text"] == "@Javis Vũ hướng dẫn thao tác tạo Agent", ev)
check("vẫn là tin của khách trong nhóm, đủ người gửi", ev["chat_type"] == "group" and ev["sender_type"] == "customer" and ev["sender_name"] == "Ngô Văn Ngợi")
tro = zc.chuan_hoa_tin(conn, dict(anh, id="m2", text="https://f55.zdn.vn/x.jpg"), ten)
check("ảnh trơn: vẫn là 'image' nhưng chú thích rỗng", tro["message_type"] == "image" and ct(tro["text"]) == "")
check("nhận ra tag bot trong chú thích ảnh (nhan_dien_goi dựa vào chữ '@Tên')", zc.nhan_dien_goi("zalo-1", ev, ("Javis Vũ",)) == (True, False), zc.nhan_dien_goi("zalo-1", ev, ("Javis Vũ",)))

# ============================================================
# 3. Báo cho model biết tin có kèm ảnh
# ============================================================
g = chatbot_runtime.gan_nhan_anh
check("tin ảnh: model được báo có ảnh mà nó không xem được, chú thích vẫn còn nguyên",
      g("[Lan] câu hỏi", {"co_anh": True}).startswith("(tin này kèm một ảnh") and g("[Lan] câu hỏi", {"co_anh": True}).endswith("[Lan] câu hỏi"))
check("tin chữ: không đổi gì", g("[Lan] câu hỏi", {}) == "[Lan] câu hỏi" and g("x", None) == "x")

# ============================================================
# 4. Lượt chủ nhờ bot trả lời từ Hòm thư
# ============================================================
conv = {"id": 1, "channel_account_id": "zalo_personal:zalo-1", "external_chat_id": "G1", "chat_type": "group", "title": "Zoom", "channel": "zalo_personal"}
m_anh = chatbot_runtime.manual_meta(conv, {"sender_id": "7770555", "sender_name": "Ngợi", "external_message_id": "m1", "created_at": 1.0, "message_type": "image"})
m_chu = chatbot_runtime.manual_meta(conv, {"sender_id": "7770555", "sender_name": "Ngợi", "external_message_id": "m3", "created_at": 1.0, "message_type": "text"})
check("manual_meta đánh dấu tin ảnh, tin chữ thì không", m_anh.get("co_anh") is True and "co_anh" not in m_chu)

import asyncio  # noqa: E402
r = asyncio.run(chatbot_runtime.manual_answer({"id": 7, "bot_id": "khong-co"}, [{"sender_type": "customer", "message_type": "image", "text": "[chat.photo]"}]))
check("(nền) không có bot thì báo no_bot trước", r.get("code") == "no_bot", r)

src = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("lượt chủ nhờ bot: ảnh trơn bị coi là chưa có tin để trả lời, ảnh có chú thích thì lấy chú thích",
      "conversations.chu_thich_anh(last.get(\"text\")) if (last or {}).get(\"message_type\") == \"image\"" in src and "text = chu_khach" in src)
tp = (SERVER / "channels" / "zalo_personal.py").read_text(encoding="utf-8")
check("Transport nhận cả 'text' lẫn 'image', ảnh lấy chú thích, và đánh dấu co_anh vào meta",
      'kieu not in ("text", "image")' in tp and "conversations.chu_thich_anh(ev.get(\"text\"))" in tp and 'meta["co_anh"] = True' in tp)

check("không dùng em dash trong file này", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if fails:
    print("\nFAIL - test_zalo_anh_chu_thich: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_zalo_anh_chu_thich: tất cả pass")
