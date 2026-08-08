"""Kênh Zalo Bot (API chính thức bot.zaloplatforms.com). Chạy tay / CI:

    python tests/python/test_zalo_bot.py

Không cần pytest, KHÔNG chạm mạng (client HTTP giả), không đụng CSDL.

Bốn chỗ Zalo khác Telegram, và cả bốn đều đổi HÀNH VI chứ không chỉ đổi tên hàm. File này
ghim đúng bốn chỗ đó, vì chúng là nơi một bản chép-từ-Telegram sẽ sai:

  1. Không sửa được tin, không xoá được tin → KHÔNG có tin trạng thái nào. Dòng vết công cụ
     đi KÈM câu trả lời, một tin cho cả lượt.
  2. Trần 2000 ký tự, không phải 4096.
  3. `getUpdates` không có offset lẫn update_id → phải TỰ chống trùng theo message_id.
  4. Khuôn phản hồi `getUpdates` chưa được tài liệu chốt → phải nhận nhiều khuôn, và khuôn
     lạ thì kêu ra chứ không im lặng bỏ hết tin (bot vẫn xanh mà không trả lời ai).

Xem docs/dev/2026-08-zalo-bot-spec.md.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import sys
from pathlib import Path

import chatbot_store
import zalo_bot
from zalo_bot import MAX_TIN, ZaloBot

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + repr(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


# ---- 1. Quy bảng chữ về MỘT: Zalo viết hoa, phần còn lại của Javis viết thường ----

check("PRIVATE -> private", zalo_bot._chat_type("PRIVATE") == "private")
check("GROUP -> group", zalo_bot._chat_type("GROUP") == "group")
check("thiếu chat_type thì coi là chat riêng", zalo_bot._chat_type(None) == "private")
check("chuỗi lạ cũng về private (fail-safe: bot chỉ im chứ không nói bậy trong nhóm)",
      zalo_bot._chat_type("linh tinh") == "private")


def bot(**kw):
    b = ZaloBot(kw.pop("token", "123:abc"), kw.pop("chat_id", ""), kw.pop("answer_fn", None), **kw)
    return b


# ---- 2. Chống trùng: không có update_id nên phải tự nhớ ----

b = bot()
check("lần đầu thấy id thì cho qua", b._da_thay("m1") is False)
check("lần hai thì chặn", b._da_thay("m1") is True)
check("id khác vẫn qua", b._da_thay("m2") is False)
check("tin KHÔNG có id thì không chặn (thà trả lời hai lần còn hơn nuốt câu hỏi)",
      b._da_thay("") is False and b._da_thay(None) is False)

b2 = bot()
for i in range(zalo_bot.MAX_DEDUPE + 50):
    b2._da_thay("x%d" % i)
check("bộ nhớ chống trùng có TRẦN, không phình mãi",
      len(b2._da_xu_ly) <= zalo_bot.MAX_DEDUPE, len(b2._da_xu_ly))


# ---- 3. Bóc sự kiện: tài liệu chưa chốt khuôn getUpdates nên phải nhận nhiều khuôn ----

MSG = {"message_id": "a1", "text": "chào", "chat": {"id": "c1", "chat_type": "PRIVATE"},
       "from": {"id": "c1", "display_name": "Ted", "is_bot": False}}

b3 = bot()
check("khuôn webhook: result là MỘT sự kiện",
      b3._boc_su_kien({"ok": True, "result": {"event_name": "message.text.received",
                                              "message": MSG}}) == [("message.text.received", MSG)])
check("khuôn danh sách: result là list sự kiện",
      len(b3._boc_su_kien({"ok": True, "result": [
          {"event_name": "message.text.received", "message": MSG},
          {"event_name": "message.text.received", "message": dict(MSG, message_id="a2")}]})) == 2)
check("khuôn bọc: result.updates là list",
      len(b3._boc_su_kien({"ok": True, "result": {"updates": [
          {"event_name": "message.text.received", "message": MSG}]}})) == 1)
check("khuôn phẳng: chính item là message",
      b3._boc_su_kien({"ok": True, "result": [MSG]}) == [("message.text.received", MSG)])
check("rỗng thì trả rỗng, không nổ", b3._boc_su_kien({"ok": True, "result": []}) == [])

b4 = bot()
b4._boc_su_kien({"ok": True, "result": [{"khong_biet": 1}]})
check("khuôn lạ thì BẬT cờ đã kêu (một lần), không im lặng nuốt tin", b4._da_bao_khuon_la)


# ---- 4. Gọi tên bot trong nhóm: Zalo không gửi entities nên chỉ còn so chuỗi ----

b5 = bot()
b5.bot_username = "Bot Shop"
check("gọi đúng tên thì nhận", b5._co_nhac_ten({"text": "Bot Shop ơi còn hàng không"}))
b6 = bot()
b6.bot_username = "BotShop"
check("tên dính liền chữ khác thì KHÔNG nhận vơ (BotShopVN không gọi BotShop)",
      not b6._co_nhac_ten({"text": "BotShopVN cho hỏi giá"}))
check("chưa biết tên mình thì không nhận bừa", not bot()._co_nhac_ten({"text": "Bot Shop"}))
# Hạn chế ĐÃ BIẾT, ghim lại để lần sau ai sửa cũng thấy đây là lựa chọn chứ không phải sót:
# tên hiển thị Zalo có khoảng trắng nên "Bot Shop VN" vẫn kích hoạt "Bot Shop". Chọn nhận hơi
# rộng vì hai kiểu sai không ngang giá: nhận nhầm là một câu thừa, bỏ sót là bot IM khi được
# gọi đúng tên - lỗi im lặng không ai dò ra.
check("nhận hơi rộng là CỐ Ý (tên nối bằng khoảng trắng vẫn tính là được gọi)",
      b5._co_nhac_ten({"text": "Bot Shop VN cho hỏi giá"}))


# ---- 5. Chạy trọn một lượt với client HTTP giả ----

class FakeResp:
    def __init__(self, d):
        self._d, self.status_code = d, 200

    def json(self):
        return self._d


class FakeClient:
    """Ghi lại mọi lời gọi. `tu_choi_md=True` giả cảnh Zalo từ chối parse_mode markdown."""

    def __init__(self, tu_choi_md=False):
        self.calls = []
        self.tu_choi_md = tu_choi_md

    async def post(self, url, json=None, data=None, files=None):
        method = url.rsplit("/", 1)[-1]
        p = json or data or {}
        self.calls.append((method, p))
        if method == "sendMessage" and self.tu_choi_md and p.get("parse_mode"):
            return FakeResp({"ok": False, "description": "parse error", "error_code": 400})
        return FakeResp({"ok": True, "result": {"message_id": "x", "date": 1}})

    def goi(self, method):
        return [p for m, p in self.calls if m == method]


def chay(answer_fn, **kw):
    b = bot(answer_fn=answer_fn, **kw)
    c = FakeClient(tu_choi_md=kw.pop("_tu_choi_md", False))
    asyncio.run(b._handle_turn(c, "c1", "doanh thu tuần này?"))
    return c


async def _tra_loi(text, meta, progress):
    await progress("⚙ Đang gọi: pos_statistics")
    await progress("⚙ Đang gọi: Read")
    return {"text": "Doanh thu 12,4 triệu."}


c = chay(_tra_loi)
check("KHÔNG có API sửa tin nào được gọi (Zalo không có editMessageText)",
      not c.goi("editMessageText") and not c.goi("deleteMessage"), [m for m, _ in c.calls])
gui = c.goi("sendMessage")
check("cả lượt chỉ MỘT tin nhắn", len(gui) == 1, len(gui))
noi_dung = (gui[0].get("text") or "") if gui else ""
check("tin đó chứa câu trả lời", "12,4 triệu" in noi_dung, noi_dung)
check("và chứa luôn dòng vết công cụ", "pos_statistics" in noi_dung and "Read" in noi_dung, noi_dung)
check("có giữ chấm 'đang nhập' (thứ DUY NHẤT báo được là đang làm)",
      len(c.goi("sendChatAction")) >= 1)

c2 = chay(_tra_loi, giau_trang_thai=True)
noi_dung2 = (c2.goi("sendMessage")[0].get("text") or "")
check("bot nói với KHÁCH: không lộ một tên công cụ nào",
      "pos_statistics" not in noi_dung2 and "⚙" not in noi_dung2, noi_dung2)
check("bot nói với KHÁCH vẫn trả lời bình thường", "12,4 triệu" in noi_dung2)


# ---- 6. Trần 2000 ký tự và đường lui khi markdown bị từ chối ----

async def _tra_loi_dai(text, meta, progress):
    return {"text": "x" * 4200}


c3 = chay(_tra_loi_dai)
gui3 = c3.goi("sendMessage")
check("câu trả lời dài bị chia nhỏ", len(gui3) >= 3, len(gui3))
check("không mẩu nào vượt trần 2000 của Zalo",
      all(len(p.get("text") or "") <= 2000 for p in gui3),
      max(len(p.get("text") or "") for p in gui3))
check("mẩu cắt đúng theo hằng số MAX_TIN", MAX_TIN <= 2000)


def chay_md_hong():
    b = bot(answer_fn=_tra_loi)
    c = FakeClient(tu_choi_md=True)
    asyncio.run(b._handle_turn(c, "c1", "hỏi"))
    return c


c4 = chay_md_hong()
gui4 = c4.goi("sendMessage")
check("markdown bị từ chối thì gửi lại CHỮ TRƠN, không mất câu trả lời",
      any(not p.get("parse_mode") for p in gui4) and
      any("12,4 triệu" in (p.get("text") or "") for p in gui4 if not p.get("parse_mode")),
      gui4)


# ---- 7. Gửi file: nói thật thay vì im lặng nuốt ----

tam = Path(ROOT) / "tests" / "python" / "_zalo_tam.pdf"
tam.write_bytes(b"%PDF-1.4 gia")
try:
    ok, err = asyncio.run(bot(chat_id="c1").send_file(str(tam)))
    check("PDF: từ chối và NÓI RÕ vì sao (Zalo chưa có API gửi tài liệu)",
          not ok and "gửi tài liệu" in err and "sendPhoto" in err, err)
finally:
    tam.unlink(missing_ok=True)

ok, err = asyncio.run(bot(chat_id="c1").send_file("khong-co-that.png"))
check("file không tồn tại thì báo đúng lý do", not ok and "không tồn tại" in err, err)


# ---- 8. Kho bot: kênh là trường thật, nhưng KHÔNG đổi được sau khi tạo ----

check("kho biết đúng hai kênh", chatbot_store.KENH == ("telegram", "zalo"))
check("kênh lạ rơi về Telegram chứ không lưu nguyên",
      chatbot_store._clean_kenh("messenger") == "telegram")
check("kênh zalo được nhận", chatbot_store._clean_kenh("Zalo") == "zalo")
check("channel KHÔNG nằm trong danh sách trắng sửa được",
      "channel" not in chatbot_store._PATCHABLE)
check("mỗi kênh có câu chỉ chỗ lấy token riêng",
      "Zalo Bot Manager" in chatbot_store.KENH_NGUON_TOKEN["zalo"] and
      "BotFather" in chatbot_store.KENH_NGUON_TOKEN["telegram"])
check("id cuộc chat Zalo (chuỗi hex) được nhận là id nhóm hợp lệ",
      chatbot_store._clean_groups("6ede9afa66b88fe6d6a9") == ["6ede9afa66b88fe6d6a9"])
check("id nhóm Telegram (số âm) vẫn nhận như cũ",
      chatbot_store._clean_groups("-1001234567890") == ["-1001234567890"])


# ---- 9. Bộ giám sát biết chọn lớp vận chuyển theo kênh ----

_RT = (Path(SERVER) / "chatbot_runtime.py").read_text(encoding="utf-8")
check("có bảng kênh -> lớp vận chuyển", '_LOP_KENH = {"telegram": TelegramBot, "zalo": ZaloBot}' in _RT)
check("bật bot thì tra bảng đó chứ không ghim cứng TelegramBot", "Lop = _LOP_KENH.get(kenh)" in _RT)
check("kênh không có lớp thì TỪ CHỐI kèm lý do", "chưa có lớp vận chuyển nào" in _RT)

_MAIN = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("kiểm token hỏi ĐÚNG nền tảng theo kênh",
      "bot-api.zaloplatforms.com/bot{tok}/getMe" in _MAIN)
check("chặn trùng token xét theo TỪNG kênh",
      "channel=kenh" in _MAIN and "def token_owner(username: str, exclude_id: str = \"\", channel"
      in (Path(SERVER) / "chatbot_store.py").read_text(encoding="utf-8"))

_ZL = (Path(SERVER) / "zalo_bot.py").read_text(encoding="utf-8")
check("không dùng em dash trong mã nguồn (luật CLAUDE.md)", "—" not in _ZL)


print()
if loi:
    print(f"{len(loi)} test ĐỎ: " + ", ".join(loi))
    sys.exit(1)
print("Tất cả test xanh.")
