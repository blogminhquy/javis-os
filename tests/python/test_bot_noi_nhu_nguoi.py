"""Bot chuyên trách không được để lộ một dòng trạng thái nào của Javis.

    python tests/run.py bot_noi_nhu_nguoi      (KHÔNG mạng, Telegram giả lập)

Chủ repo gửi ảnh chụp một nhóm Telegram (2026-08-07): bot đang nói chuyện như người, rồi giữa
cuộc hiện ra "⏳ Đang xử lý câu trước. Gửi /stop để dừng rồi hỏi lại." trước mặt cả nhóm. Một
câu như vậy khai ngay đây là máy, và còn dạy người lạ một lệnh quản trị. Yêu cầu: "các phần
trạng thái của Javis anh không muốn để lộ ra như vậy, anh muốn ẩn đi để như cảm giác người thật
nói chứ ko phải bot."

Bốn chỗ rò, canh cả bốn:
  1. tin "🤔 Javis đang xử lý…" gửi trước mỗi lượt (và các bản cập nhật "⏳ …" của nó)
  2. câu "⏳ Đang xử lý câu trước. Gửi /stop…" khi có tin tới lúc bot đang bận
  3. "⚠ Lỗi: <TênLớpNgoạiLệ>: …" khi một lượt gãy
  4. "(không có nội dung)" khi câu trả lời rỗng

Và một luật đi kèm, quan trọng ngang việc giấu: giấu KHÔNG được phép làm rơi câu hỏi. Tin tới
lúc bot đang bận phải được xếp hàng rồi trả lời một thể, đúng như một người thật đọc nốt rồi
mới đáp. Bot của CHỦ giữ nguyên hành vi cũ - chủ cần thấy tiến trình và cần lệnh /stop.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-botnguoi-"))

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from telegram_bot import CAU_LOI_NGUOI_THAT, TelegramBot  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---------- Telegram giả lập: ghi lại đúng những gì bot ĐỊNH gửi đi ----------
class FakeResp:
    def __init__(self, data=None):
        self._d = data if data is not None else {"ok": True, "result": {"message_id": 7}}
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._d


class FakeTelegram:
    def __init__(self):
        self.calls = []

    async def post(self, url, json=None, **kw):
        self.calls.append((url.rsplit("/", 1)[-1], json or {}))
        return FakeResp()

    async def get(self, url, params=None, **kw):
        self.calls.append((url.rsplit("/", 1)[-1], params or {}))
        return FakeResp({"ok": True, "result": []})

    def texts(self):
        """Mọi câu bot thực sự gửi vào cuộc trò chuyện.

        `_send` gửi bản MarkdownV2 trước, nên chữ đi qua đây có dấu `\\` chèn trước mọi ký tự
        đặc biệt. Gỡ ra để so được với câu gốc.
        """
        return [j.get("text", "").replace("\\", "")
                for m, j in self.calls if m == "sendMessage"]

    def methods(self):
        return [m for m, _ in self.calls]


def bot_khach(answer_fn, **kw):
    return TelegramBot("TOKEN", "", answer_fn, giau_trang_thai=True, **kw)


def bot_chu(answer_fn, **kw):
    return TelegramBot("TOKEN", "", answer_fn, **kw)


async def cho_xong(bot, chat, vong=200):
    """Đợi lượt hiện tại + phần xếp hàng chạy hết (mọi thứ chạy trong RAM nên rất nhanh)."""
    for _ in range(vong):
        await asyncio.sleep(0.005)
        if not bot._busy(chat) and not bot._cho.get(chat):
            return
    return


# ============================================================
# 1. Không tin trạng thái nào, chỉ còn chấm "đang nhập…"
# ============================================================
async def t_khong_tin_trang_thai():
    async def answer(text, meta, progress):
        await progress("đang gọi công cụ pos_statistics")
        await progress("đang soạn câu trả lời")
        return "Dạ bên em còn hàng ạ."

    tg = FakeTelegram()
    b = bot_khach(answer)
    await b._handle_turn(tg, "42", "còn hàng không em")
    await asyncio.sleep(0)

    gui = tg.texts()
    check("khách: KHÔNG có tin '🤔 Javis đang xử lý…'",
          not any("đang xử lý" in t.lower() for t in gui))
    check("khách: KHÔNG có tin trạng thái '⏳' nào", not any("⏳" in t for t in gui))
    check("khách: không đụng tới editMessageText/deleteMessage của tin trạng thái",
          "editMessageText" not in tg.methods() and "deleteMessage" not in tg.methods())
    check("khách: vẫn có chấm 'đang nhập…' để đầu kia biết có người đang gõ",
          "sendChatAction" in tg.methods())
    check("khách: câu trả lời thật vẫn tới", gui == ["Dạ bên em còn hàng ạ."])

    # Bot của CHỦ giữ nguyên: chủ cần nhìn thấy Javis đang chạy tới đâu.
    tg2 = FakeTelegram()
    await bot_chu(answer)._handle_turn(tg2, "42", "còn hàng không em")
    check("chủ: vẫn gửi tin trạng thái như cũ",
          any("Javis đang xử lý" in t for t in tg2.texts()))
    # Từ 0.26.4 tin trạng thái KHÔNG bị xoá nữa, nó ở lại thành dòng vết công cụ. Chi tiết và
    # lý do ở tests/python/test_tin_trang_thai_telegram.py.
    check("chủ: KHÔNG xoá tin trạng thái nữa", "deleteMessage" not in tg2.methods())


# ============================================================
# 2. Bận thì XẾP HÀNG, không quay ra nói "đang xử lý câu trước"
# ============================================================
async def t_ban_thi_xep_hang():
    cong = asyncio.Event()
    thay = []

    async def answer(text, meta, progress):
        thay.append(text)
        if len(thay) == 1:
            await cong.wait()
        return "Dạ: " + text

    tg = FakeTelegram()
    b = bot_khach(answer)
    await b._dispatch(tg, "42", "anh có nói chuyện được với em không javis vũ", {})
    await b._dispatch(tg, "42", ":)", {})
    await b._dispatch(tg, "42", "alo", {})

    check("khách: KHÔNG có câu 'Đang xử lý câu trước'",
          not any("câu trước" in t for t in tg.texts()))
    check("khách: KHÔNG dạy người lạ lệnh /stop", not any("/stop" in t for t in tg.texts()))
    check("khách: tin tới lúc bận được giữ lại chứ không rơi mất",
          b._cho.get("42", {}).get("texts") == [":)", "alo"])

    cong.set()
    await cho_xong(b, "42")
    check("khách: trả lời xong lượt đầu thì gộp mấy câu chờ thành MỘT lượt",
          thay == ["anh có nói chuyện được với em không javis vũ", ":)\nalo"])
    check("khách: cả hai lượt đều có câu trả lời gửi đi", len(tg.texts()) == 2)

    # Chủ: giữ nguyên câu báo bận - đó là thông tin có ích cho người đang vận hành máy.
    cong2 = asyncio.Event()

    async def answer2(text, meta, progress):
        await cong2.wait()
        return "xong"

    tg2 = FakeTelegram()
    b2 = bot_chu(answer2)
    await b2._dispatch(tg2, "42", "câu 1", {})
    await b2._dispatch(tg2, "42", "câu 2", {})
    check("chủ: vẫn báo 'Đang xử lý câu trước' như cũ",
          any("Đang xử lý câu trước" in t for t in tg2.texts()))
    cong2.set()
    await cho_xong(b2, "42")


async def t_tran_hang_cho():
    cong = asyncio.Event()

    async def answer(text, meta, progress):
        await cong.wait()
        return "xong"

    tg = FakeTelegram()
    b = bot_khach(answer)
    await b._dispatch(tg, "42", "câu đầu", {})
    for i in range(30):
        await b._dispatch(tg, "42", f"spam {i}", {})
    check("hàng chờ có TRẦN, người lạ spam không làm phình bộ nhớ",
          len(b._cho["42"]["texts"]) <= 5)
    check("giữ mấy câu ĐẦU (câu hỏi thật thường nằm ở đó)",
          b._cho["42"]["texts"][0] == "spam 0")
    cong.set()
    await cho_xong(b, "42")


# ============================================================
# 3. Lượt gãy: xin lỗi bằng lời người, không đọc tên lớp ngoại lệ
# ============================================================
async def t_luot_gay():
    async def no(text, meta, progress):
        raise ValueError("engine bể")

    tg = FakeTelegram()
    await bot_khach(no)._handle_turn(tg, "42", "hỏi")
    await asyncio.sleep(0)
    gui = tg.texts()
    check("khách: không lộ tên lớp ngoại lệ",
          not any("ValueError" in t or "⚠" in t for t in gui))
    check("khách: xin lỗi bằng một câu người thật nói được", gui == [CAU_LOI_NGUOI_THAT])

    tg2 = FakeTelegram()
    await bot_chu(no)._handle_turn(tg2, "42", "hỏi")
    check("chủ: vẫn thấy nguyên lỗi kỹ thuật để còn sửa",
          any("ValueError" in t for t in tg2.texts()))


# ============================================================
# 4. Câu rỗng: im chứ không nói "(không có nội dung)"
# ============================================================
async def t_cau_rong():
    tg = FakeTelegram()
    b = bot_khach(None)
    await b._send(tg, "42", "")
    await b._send(tg, "42", "   ")
    check("khách: câu rỗng thì không gửi gì cả", tg.texts() == [])

    tg2 = FakeTelegram()
    await bot_chu(None)._send(tg2, "42", "")
    check("chủ: giữ '(không có nội dung)' để lỗi không bị nuốt",
          tg2.texts() == ["(không có nội dung)"])


# ============================================================
# 5. /stop cắt ngang thì bỏ luôn hàng chờ
# ============================================================
async def t_stop_bo_hang_cho():
    cong = asyncio.Event()
    thay = []

    async def answer(text, meta, progress):
        thay.append(text)
        await cong.wait()
        return "xong"

    tg = FakeTelegram()
    b = bot_khach(answer)
    await b._dispatch(tg, "42", "câu 1", {})
    await asyncio.sleep(0)      # để lượt 1 thật sự bắt đầu chạy rồi mới cắt
    await b._dispatch(tg, "42", "câu 2", {})
    await b._dispatch(tg, "42", "/stop", {})
    await cho_xong(b, "42")
    check("bảo dừng thì dừng hẳn, không trả lời nốt phần đang chờ", thay == ["câu 1"])
    check("khách: không lộ câu máy '⏹ Đã dừng.'", not any("⏹" in t for t in tg.texts()))


# ============================================================
# 6. Không được gọi thì không "đang nhập…", và không tốn lượt engine
# ============================================================
# Chủ repo báo 2026-08-07 kèm ảnh nhóm "Cười Sóng AI": "chat bất kỳ điều gì trong nhóm khi add
# bot vào nó đều typing". Gốc rễ nằm ở `_dispatch`: chốt chặn precheck trả `{}` để nói "chặn,
# đừng nói gì", mà cổng viết `if chan:` - dict rỗng falsy nên lượt vẫn chạy tiếp. Ngoài cái
# typing nhìn thấy được, mỗi tin trong nhóm còn tốn một lượt engine thật rồi bị vứt đi.
async def t_khong_goi_ten_thi_im():
    goi = []

    async def answer(text, meta, progress):
        goi.append(text)
        return "lẽ ra không được chạy"

    tg = FakeTelegram()
    b = bot_khach(answer, precheck_fn=lambda text, meta: {})     # {} = chặn, không nói gì
    await b._dispatch(tg, "-100", "hai người trong nhóm nói chuyện với nhau", {})
    await cho_xong(b, "-100")
    check("không gọi tên bot: KHÔNG tốn lượt engine", goi == [])
    check("không gọi tên bot: KHÔNG hiện 'đang nhập…'", "sendChatAction" not in tg.methods())
    check("không gọi tên bot: không gửi tin nào", tg.texts() == [])

    # Chặn KÈM một câu (nhóm chưa được bật) thì vẫn nói câu đó, nhưng vẫn không tốn lượt.
    tg2 = FakeTelegram()
    b2 = bot_khach(answer, precheck_fn=lambda text, meta: {"reply": "Em chưa được bật ạ."})
    await b2._dispatch(tg2, "-100", "javis ơi", {})
    await cho_xong(b2, "-100")
    check("nhóm chưa bật: nói đúng một câu, không gọi engine",
          goi == [] and tg2.texts() == ["Em chưa được bật ạ."])

    # None = cho chạy. Đây là ca duy nhất được phép hiện "đang nhập…".
    tg3 = FakeTelegram()
    b3 = bot_khach(answer, precheck_fn=lambda text, meta: None)
    await b3._dispatch(tg3, "-100", "@javis giá bao nhiêu", {})
    await cho_xong(b3, "-100")
    check("có gọi tên bot: mới chạy lượt và mới hiện 'đang nhập…'",
          goi == ["@javis giá bao nhiêu"] and "sendChatAction" in tg3.methods())

    # precheck NỔ thì phải chạy tiếp, không được nuốt câu của khách.
    def _no(text, meta):
        raise RuntimeError("precheck hỏng")

    tg4 = FakeTelegram()
    b4 = bot_khach(answer, precheck_fn=_no)
    await b4._dispatch(tg4, "-100", "câu của khách", {})
    await cho_xong(b4, "-100")
    check("precheck hỏng thì vẫn trả lời, không nuốt câu của khách",
          goi == ["@javis giá bao nhiêu", "câu của khách"])


def t_precheck_hop_dong():
    # Cổng precheck nằm ở `bot_gateway._dispatch` từ 0.26.5 (dùng chung Telegram + Zalo).
    src = (Path(SERVER) / "bot_gateway.py").read_text(encoding="utf-8")
    # So trên DÒNG MÃ thật, không so cả file: chuỗi "if chan:" còn nằm trong chú thích kể lại
    # con bọ, và một test bắt cả chú thích thì cấm luôn việc ghi lại vì sao đã sửa.
    dong_ma = [d.strip() for d in src.split("\n") if not d.strip().startswith("#")]
    check("cổng precheck so với None, không so truthy (dict rỗng vẫn phải chặn)",
          "if chan is not None:" in dong_ma and "if chan:" not in dong_ma)
    cb = (Path(SERVER) / "chatbot_runtime.py").read_text(encoding="utf-8")
    check("bot chuyên trách vẫn dùng {} để nói 'chặn mà không nói gì'",
          "return {}       # không ai gọi tên" in cb)


# ============================================================
# 7. Bot chuyên trách phải THẬT SỰ được bật chế độ này
# ============================================================
def t_noi_day():
    src = (Path(SERVER) / "chatbot_runtime.py").read_text(encoding="utf-8")
    check("chatbot_runtime bật giau_trang_thai cho bot khách", "giau_trang_thai=True" in src)
    tg_src = (Path(SERVER) / "telegram_bot.py").read_text(encoding="utf-8")
    check("mặc định của lớp TelegramBot vẫn là KHÔNG giấu (bot của chủ)",
          "giau_trang_thai=False" in tg_src)
    check("không dùng em dash trong câu nói với khách (luật CLAUDE.md)",
          "—" not in CAU_LOI_NGUOI_THAT)


async def main():
    await t_khong_tin_trang_thai()
    await t_ban_thi_xep_hang()
    await t_tran_hang_cho()
    await t_luot_gay()
    await t_cau_rong()
    await t_stop_bo_hang_cho()
    await t_khong_goi_ten_thi_im()
    t_precheck_hop_dong()
    t_noi_day()


asyncio.run(main())

if _fails:
    raise SystemExit(f"\nFAIL - test_bot_noi_nhu_nguoi: {len(_fails)} lỗi")
print("\nOK - test_bot_noi_nhu_nguoi: tất cả pass")
