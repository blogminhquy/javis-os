"""Ba lỗi người dùng thật báo ngày 2026-08-12, sau khi cài Javis lên một máy macOS mới.

    python tests/run.py mac_va_telegram      (KHÔNG mạng)

Cả ba đều thuộc loại "chạy trên máy dev không đời nào lộ ra", vì máy dev đã có sẵn đúng cái
trạng thái che mất lỗi:

1. KẾT NỐI CHATGPT XONG, THẺ HIỆN "0 MODEL". Con số trên thẻ đọc từ `model.catalog` trong
   settings, mà catalog chỉ được ghi SAU một lần lấy live thành công. ChatGPT là provider DUY
   NHẤT không có catalog mặc định (danh sách model do Codex quyết, Javis cố ý không ghim
   version), nên trên máy mới nó là danh sách rỗng và không có ai đi hỏi cho tới khi người dùng
   tự mở hộp chọn model. Máy cũ không thấy lỗi chỉ vì catalog đã có từ lần trước.

2. HỎNG XONG KHÔNG NÓI VÌ SAO. Mọi đường lấy model hỏng theo kiểu trả `None` chứ không ném lỗi,
   nên hộp chọn chỉ có một câu chung chung "provider chưa kết nối hoặc không có model" - đọc
   xong vẫn không biết phải làm gì. Trên macOS nguyên nhân thường là chưa cài Codex CLI.

3. TELEGRAM KHÔNG SỔ RA DANH SÁCH LỆNH KHI GÕ "/". `setMyCommands` bị gọi trần trong try/except:
   Telegram từ chối là trả HTTP 200 kèm `{"ok": false}` chứ không ném lỗi mạng, nên không có gì
   để bắt và code đi tiếp như đã đặt xong. Cộng thêm: chỉ đặt phạm vi mặc định, mà Telegram chọn
   menu theo phạm vi HẸP nhất đang có, nên một danh sách cũ đặt cho `all_private_chats` che mất
   danh sách mặc định vĩnh viễn.

Kèm luôn cái chốt cho nguyên nhân macOS ở tầng dưới: tiến trình nền trên macOS nhận PATH tối
giản của launchd, nên `claude`/`codex` cài bằng Homebrew (Apple Silicon: /opt/homebrew/bin) hay
nvm đều "không tìm thấy" dù gõ trong Terminal vẫn chạy.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-mactest-")

import claude_cli          # noqa: E402
import config as c         # noqa: E402
import main                # noqa: E402
import telegram_bot        # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def _noi_chatgpt():
    cfg = c.read_settings()
    cfg["model"]["openai_oauth"] = {"access_token": "tok", "refresh_token": "r",
                                    "account_id": "acc", "plan": "plus"}
    cfg["model"].setdefault("catalog", {})["openai-oauth"] = []
    c.write_settings(cfg)


# ============================================================
# 1. Đúng cái người dùng thấy: kết nối xong, thẻ hiện 0 model
# ============================================================
_noi_chatgpt()
_pv = {p["id"]: p for p in main._providers_view(c.read_settings())}
check("dựng lại được hiện trường: ChatGPT đã kết nối nhưng chưa có model nào",
      _pv["openai-oauth"]["configured"] is True and _pv["openai-oauth"]["models"] == [])
check("CANARY: provider khác vẫn có catalog dự phòng nên không bao giờ ra 0 model",
      all(len(_pv[k]["models"]) > 0 for k in ("anthropic-cli", "anthropic-api", "openai", "gemini")))

# Dashboard phải TỰ đi hỏi khi gặp đúng cảnh này, thay vì để con số 0 nằm im.
_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("trang Models tự hỏi danh sách model cho provider đã kết nối mà đang rỗng",
      "hoiModelConNo" in _console and "p.configured && !(p.models || []).length" in _console)
check("gọi ngay trong renderModels, không đợi ai mở hộp chọn model",
      _console.index("hoiModelConNo(el, provList)") < _console.index("async function hoiModelConNo("))
check("CANARY: hỏi hụt thì THÔI, không vẽ lại rồi hỏi lại thành vòng vô tận",
      "_daHoiModel" in _console and "_daHoiModel.add(p.id)" in _console)
check("đăng nhập ChatGPT xong thì cho phép hỏi lại (bộ nhớ 'đã hỏi' không khoá luôn)",
      _console.count('_daHoiModel.delete("openai-oauth")') >= 2)


# ============================================================
# 2. Rỗng thì phải nói VÌ SAO, và nói được câu dùng được
# ============================================================
_m = c.read_settings()["model"]
_ly_do = main._vi_sao_khong_co_model("openai-oauth", _m)
check("đã kết nối + không thấy Codex CLI -> chỉ đúng việc phải làm",
      "Codex" in _ly_do and ("npm i -g @openai/codex" in _ly_do),
      _ly_do)
check("và nhắc được cả lối thoát cho máy cài chỗ lạ", "JAVIS_CODEX_BIN" in _ly_do)

_cu = main.openai_oauth.valid_creds
try:
    main.openai_oauth.valid_creds = lambda: {}
    _ly_do2 = main._vi_sao_khong_co_model("openai-oauth", _m)
finally:
    main.openai_oauth.valid_creds = _cu
check("chưa kết nối thì nói chưa kết nối, không đổ cho Codex",
      "Chưa kết nối ChatGPT" in _ly_do2 and "npm i" not in _ly_do2, _ly_do2)

check("provider API thiếu key -> nói thiếu key",
      "API key" in main._vi_sao_khong_co_model("openrouter", {}))
check("không có gì để nói thì im, không bịa lý do",
      main._vi_sao_khong_co_model("anthropic-cli", _m) == "")

# Lý do phải ĐI RA TỚI người dùng, không dừng ở server.
_r = asyncio.get_event_loop().run_until_complete(
    main.provider_models_index("openai-oauth", refresh=True))
check("/provider/models trả kèm lý do khi danh sách rỗng",
      _r.get("live") is False and bool(_r.get("error")), _r)
check("hộp chọn model hiện đúng lý do đó thay vì câu chung chung",
      "error: (res && res.error)" in _console
      and "liveCache[selProv].error" in _console)


# ============================================================
# 3. Telegram: menu lệnh "/" phải đặt được, và đặt hụt thì phải nói ra
# ============================================================
class _FakeResp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status

    def json(self):
        return self._p


class _FakeClient:
    """Ghi lại mọi lời gọi setMyCommands và trả lời theo kịch bản."""

    def __init__(self, tra_loi):
        self.tra_loi = tra_loi
        self.goi = []

    async def post(self, url, json=None):
        self.goi.append((url, json))
        return _FakeResp(self.tra_loi)


def _bot(commands=None):
    return telegram_bot.TelegramBot("123:ABC", "", answer_fn=None, commands=commands)


_b = _bot()
_cl = _FakeClient({"ok": True})
asyncio.get_event_loop().run_until_complete(_b._day_menu_lenh(_cl))
_scopes = [(g.get("scope") or {}).get("type", "default") for _, g in _cl.goi]
check("đặt menu cho CẢ BA phạm vi, không chỉ mặc định",
      _scopes == ["default", "all_private_chats", "all_group_chats"], _scopes)
check("CANARY: có all_private_chats - phạm vi hẹp CHE mất mặc định là ca hỏng thật",
      "all_private_chats" in _scopes)
check("đủ lệnh trong mỗi lần đặt",
      all(len(g["commands"]) == len(telegram_bot.BOT_COMMANDS) for _, g in _cl.goi))
check("đặt trót lọt thì không báo lỗi gì", _b.loi_menu_lenh == "")

# Telegram từ chối = HTTP 200 + ok:false. Đây đúng là chỗ bản cũ nuốt mất.
_b2 = _bot()
_cl2 = _FakeClient({"ok": False, "description": "BOT_COMMAND_INVALID"})
asyncio.get_event_loop().run_until_complete(_b2._day_menu_lenh(_cl2))
check("CANARY: ok:false (HTTP 200, không có exception) vẫn bị bắt là hỏng",
      bool(_b2.loi_menu_lenh) and "BOT_COMMAND_INVALID" in _b2.loi_menu_lenh, _b2.loi_menu_lenh)
check("câu báo nói rõ hậu quả: bot vẫn chạy, chỉ là không tự sổ danh sách",
      "gõ tay" in _b2.loi_menu_lenh)


class _ClientNo:
    async def post(self, url, json=None):
        raise OSError("mạng rớt")


_b3 = _bot()
asyncio.get_event_loop().run_until_complete(_b3._day_menu_lenh(_ClientNo()))
check("mạng rớt cũng vào cùng một chỗ báo lỗi, không nổ ra ngoài",
      "OSError" in _b3.loi_menu_lenh)

_src_tg = (SERVER / "telegram_bot.py").read_text(encoding="utf-8")
check("CANARY: không còn chỗ nào gọi setMyCommands mà bỏ qua kết quả",
      _src_tg.count("setMyCommands") == 2   # 1 trong _day_menu_lenh + 1 trong câu log
      and 'd.get("ok")' in _src_tg)
check("vòng khởi động bot đi qua đúng hàm đó", "await self._day_menu_lenh(client)" in _src_tg)

# Lỗi phải ra tới giao diện, cả bot của chủ lẫn bot chuyên trách.
check("/telegram/status khai lỗi menu lệnh", '"loi_menu_lenh"' in (SERVER / "main.py").read_text(encoding="utf-8"))
check("trang Chatbot cũng khai", "loi_menu_lenh" in (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8"))
_app_js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("khối Telegram trong Cài đặt hiện lỗi đó", "loi_menu_lenh" in _app_js)
check("thẻ bot chuyên trách hiện lỗi đó",
      "loi_menu_lenh" in (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8"))

# Bot chuyên trách vẫn phải giữ menu RIÊNG của khách, không bị kéo về menu quản trị.
_b4 = _bot(commands=[{"command": "help", "description": "Bot này giúp được gì"}])
_cl4 = _FakeClient({"ok": True})
asyncio.get_event_loop().run_until_complete(_b4._day_menu_lenh(_cl4))
check("CANARY: menu truyền riêng vào không bị thay bằng menu quản trị",
      all(len(g["commands"]) == 1 for _, g in _cl4.goi))


# ============================================================
# 4. macOS: tìm binary ngoài PATH tối giản của tiến trình nền
# ============================================================
_path_cu = os.environ.get("PATH", "")
_tmp = tempfile.mkdtemp(prefix="javis-brew-")
try:
    # Giả lập đúng cảnh macOS: PATH của launchd, còn binary nằm ở thư mục Homebrew.
    os.environ["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    check("CANARY: PATH tối giản thì shutil.which KHÔNG thấy - đây là gốc của lỗi",
          __import__("shutil").which("codex") is None)
    _duong = claude_cli._duong_dan_tim_binary()
    for _d in ("/opt/homebrew/bin", "/usr/local/bin"):
        check(f"đường tìm có {_d}", _d in _duong)
    check("có cả thư mục cài của người dùng (~/.local/bin)",
          str((claude_cli._home_dir() / ".local" / "bin")) in _duong or "/.local/bin" in _duong)
    check("PATH thật vẫn đứng TRƯỚC, không đảo ưu tiên",
          _duong.startswith("/usr/bin:/bin:/usr/sbin:/sbin"))

    # Có binary thật trong một thư mục ngoài PATH thì phải tìm ra.
    from pathlib import Path as _P
    _fake = _P(_tmp) / "codex"
    _fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    _fake.chmod(0o755)
    _cu_dirs = claude_cli._THU_MUC_BIN_THEM
    try:
        claude_cli._THU_MUC_BIN_THEM = (_tmp,)
        check("tim_binary soi được thư mục cài ngoài PATH",
              claude_cli.tim_binary("codex") == str(_fake))
    finally:
        claude_cli._THU_MUC_BIN_THEM = _cu_dirs
    check("không có thật thì vẫn trả None, không bịa đường dẫn",
          claude_cli.tim_binary("khong-ton-tai-dau-ca") is None)
finally:
    os.environ["PATH"] = _path_cu

_src_cli = (SERVER / "claude_cli.py").read_text(encoding="utf-8")
check("CANARY: cả claude lẫn codex đều dùng đường tìm mở rộng",
      'tim_binary("claude")' in _src_cli and 'tim_binary("codex")' in _src_cli)
check("CANARY: không còn shutil.which trần cho hai binary đó",
      'shutil.which("claude")' not in _src_cli and 'shutil.which("codex")' not in _src_cli)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test mac_va_telegram đã qua.")
