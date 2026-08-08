"""Tin trạng thái Telegram: gửi im lặng, KHÔNG xoá, chốt thành dòng vết. Chạy tay / CI:

    python tests/python/test_tin_trang_thai_telegram.py

Không cần pytest, không chạm mạng (client HTTP giả), không đụng CSDL.

Bệnh (chủ repo báo 2026-08-08): mỗi lượt hỏi, bot gửi tin "🤔 Javis đang xử lý…" rồi XOÁ nó
đi và gửi câu trả lời. Hai chỗ sai: người dùng thấy một tin nhấp nháy rồi biến mất (đọc như
lỗi), và điện thoại nổ HAI thông báo mà cái đầu chỉ nói "đang xử lý".

Đã kiểm với tài liệu Telegram: KHÔNG có bề mặt nào hiện chữ tuỳ ý ngoài tin nhắn
(`sendChatAction` chỉ nhận một bộ hành động cố định, không nhận chữ). Nên "hiện trạng thái mà
không gửi tin" là bất khả; thứ sửa được là đừng để tin nào biến mất và đừng nổ thông báo thừa.

Bốn điều file này ghim lại:
  1. tin trạng thái gửi kèm `disable_notification` → không nổ chuông;
  2. KHÔNG bao giờ gọi `deleteMessage` nữa;
  3. lần sửa CUỐI biến nó thành dòng vết công cụ, và câu trả lời là một tin MỚI;
  4. tên công cụ được gom TRƯỚC cửa throttle, nên tool chạy nhanh không rụng khỏi dòng vết.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import sys

from bot_gateway import RE_TEN_TOOL
from telegram_bot import TelegramBot

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + repr(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


# ---- 1. Bóc tên công cụ từ ĐÚNG ba khuôn main.py đang bắn ra ----

MAU_CO_TOOL = [
    ("⚙ Đang gọi: pos_statistics", "pos_statistics"),                  # engine Claude
    ("⚙ Đang gọi công cụ: Read", "Read"),                              # engine API
    ("⚙ Đang dùng công cụ: mcp__pancake-pos__pos_order",
     "mcp__pancake-pos__pos_order"),                                   # nhánh còn lại
    ("⚙ Đang gọi: `Write`", "Write"),                                  # có backtick bao quanh
]
for chuoi, mong in MAU_CO_TOOL:
    m = RE_TEN_TOOL.match(chuoi)
    got = m.group(1).strip().strip("`").strip() if m else None
    check(f"bóc tên tool: {chuoi[:28]}", got == mong, got)

for chuoi in ("✓ Nhận kết quả - đang phân tích…", "✍ Đang soạn câu trả lời…", "⏳ Đang xử lý…"):
    check(f"KHÔNG bóc nhầm: {chuoi[:26]}", RE_TEN_TOOL.match(chuoi) is None)


# ---- 2. Dòng vết: lượt không gọi tool cũng phải nói được một điều thật ----

bot_tron = TelegramBot.__new__(TelegramBot)
check("không tool → nói rõ trả lời trực tiếp",
      bot_tron._dong_vet([], 3.2) == "✓ Trả lời trực tiếp · 3s", bot_tron._dong_vet([], 3.2))
check("có tool → liệt kê tên + thời gian",
      bot_tron._dong_vet(["pos_statistics", "Read"], 8.7) == "⚙ pos_statistics · Read · 9s",
      bot_tron._dong_vet(["pos_statistics", "Read"], 8.7))
check("quá 6 tool → gộp phần dư thành +n",
      bot_tron._dong_vet(list("abcdefgh"), 75.4) == "⚙ a · b · c · d · e · f +2 · 1m15s",
      bot_tron._dong_vet(list("abcdefgh"), 75.4))
check("lượt trên 1 phút → định dạng phút giây",
      bot_tron._dong_vet(["X"], 61) == "⚙ X · 1m01s", bot_tron._dong_vet(["X"], 61))


# ---- 3. Chạy trọn một lượt với client HTTP giả ----

class FakeResp:
    def __init__(self, data):
        self._d, self.status_code, self.content = data, 200, b"{}"
        self.text = str(data)

    def json(self):
        return self._d


class FakeClient:
    """Ghi lại mọi lời gọi. `post(url, json=...)` là đủ cho đường đi của _handle_turn."""

    def __init__(self):
        self.calls = []      # [(method, payload)]
        self._mid = 100

    async def post(self, url, json=None, data=None, files=None):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json or data or {}))
        if method == "sendMessage":
            self._mid += 1
            return FakeResp({"ok": True, "result": {"message_id": self._mid}})
        return FakeResp({"ok": True, "result": {}})

    def goi(self, method):
        return [p for m, p in self.calls if m == method]


def chay_luot(answer_fn, giau_trang_thai=False):
    bot = TelegramBot.__new__(TelegramBot)
    bot.token, bot.chat_ids, bot.giau_trang_thai = "t", ["7"], giau_trang_thai
    bot.answer_fn = answer_fn
    c = FakeClient()
    asyncio.run(bot._handle_turn(c, "7", "doanh thu tuần này?"))
    return c


async def _answer_hai_tool(text, meta, progress):
    # HAI tool trong cùng một khoảnh khắc: cửa throttle 2.5s sẽ nuốt lần sửa thứ hai, nhưng
    # TÊN thì không được phép rụng - đây đúng là con bọ mà việc gom-trước-throttle ngăn lại.
    await progress("⚙ Đang gọi: pos_statistics")
    await progress("⚙ Đang gọi: Read")
    await progress("✍ Đang soạn câu trả lời…")
    return {"text": "Doanh thu 12,4 triệu, tăng 8%."}


c = chay_luot(_answer_hai_tool)

check("KHÔNG còn gọi deleteMessage", not c.goi("deleteMessage"),
      [m for m, _ in c.calls])

gui = c.goi("sendMessage")
check("tin trạng thái gửi IM LẶNG", bool(gui) and gui[0].get("disable_notification") is True,
      gui[0] if gui else None)
check("tin trạng thái mở đầu bằng 'đang xử lý'",
      bool(gui) and "đang xử lý" in (gui[0].get("text") or "").lower(), gui[0] if gui else None)

check("câu trả lời là tin MỚI, không phải sửa tin cũ", len(gui) == 2, len(gui))
check("tin cuối cùng chính là câu trả lời",
      len(gui) == 2 and "12,4 triệu" in (gui[-1].get("text") or ""), gui[-1] if len(gui) > 1 else None)
check("câu trả lời KHÔNG bị tắt chuông",
      len(gui) == 2 and not gui[-1].get("disable_notification"), gui[-1] if len(gui) > 1 else None)

sua = c.goi("editMessageText")
check("có sửa tin trạng thái", len(sua) >= 1, len(sua))
vet = (sua[-1].get("text") or "") if sua else ""
check("lần sửa CUỐI là dòng vết công cụ", vet.startswith("⚙ "), vet)
check("dòng vết giữ ĐỦ hai tool dù throttle nuốt bớt lần sửa",
      "pos_statistics" in vet and "Read" in vet, vet)


# ---- 4. /stop: tin trạng thái ở lại nói rõ đã dừng, không biến mất ----

async def _answer_bi_cat(text, meta, progress):
    await progress("⚙ Đang gọi: pos_order")
    raise asyncio.CancelledError()


c2 = chay_luot(_answer_bi_cat)
check("/stop cũng KHÔNG xoá tin", not c2.goi("deleteMessage"), [m for m, _ in c2.calls])
sua2 = c2.goi("editMessageText")
check("/stop → tin trạng thái đổi thành 'Đã dừng'",
      bool(sua2) and "Đã dừng" in (sua2[-1].get("text") or ""), sua2[-1] if sua2 else None)
check("/stop → KHÔNG gửi thêm câu trả lời nào", len(c2.goi("sendMessage")) == 1,
      len(c2.goi("sendMessage")))


# ---- 5. Bot chuyên trách (nói với KHÁCH) không đổi: không tin trạng thái, không dòng vết ----

async def _answer_khach(text, meta, progress):
    await progress("⚙ Đang gọi: pos_product")
    return {"text": "Dạ bên em còn hàng ạ."}


c3 = chay_luot(_answer_khach, giau_trang_thai=True)
check("chế độ người thật: không tin trạng thái, chỉ 1 tin trả lời",
      len(c3.goi("sendMessage")) == 1, len(c3.goi("sendMessage")))
check("chế độ người thật: không sửa tin nào", not c3.goi("editMessageText"),
      c3.goi("editMessageText"))
check("chế độ người thật: có giữ chấm 'đang nhập'", len(c3.goi("sendChatAction")) >= 1,
      len(c3.goi("sendChatAction")))


print()
if loi:
    print(f"{len(loi)} test ĐỎ: " + ", ".join(loi))
    sys.exit(1)
print("Tất cả test xanh.")
