"""Ghim model riêng cho kênh Telegram: web đổi model không kéo điện thoại theo.

    python tests/run.py ghim_model_telegram      (KHÔNG mạng)

Chủ repo hỏi 02/09: "anh muốn ghim model ở telegram, khi đổi model trên web thì model telegram
không bị đổi". Soi code thì thấy nó dính nhau CẢ HAI chiều: `_tg_answer` đọc model.main, và
lệnh /model trên Telegram ghi thẳng vào model.main - tức đổi trên điện thoại cũng đổi luôn web.

Dáng đã chốt: mặc định "theo model chính" (không đổi gì cho người đang dùng), ghim chỉ khi
chọn. Ghim rồi thì /model trên Telegram sửa ô Telegram, /status nói rõ đang ghim - vì điện
thoại không có banner như web, một ghim chết mà không ai nói là hỏng câm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tgghim-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def chay(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _dat(main_prov="anthropic-cli", main_model="sonnet", tg_prov="", tg_model="", key=""):
    s = cfgmod.read_settings()
    s["model"]["main"] = {"provider": main_prov, "model": main_model}
    s["model"]["telegram"] = {"provider": tg_prov, "model": tg_model}
    if key:
        s["model"]["openrouter_key"] = key
    cfgmod.write_settings(s)
    return cfgmod.read_settings()["model"]


# ---- 1. Mặc định: theo model chính, không ai thấy gì khác -----------------------
m = cfgmod.read_settings()["model"]
check("settings có ô telegram, mặc định rỗng = theo model chính",
      "telegram" in m and not (m["telegram"] or {}).get("provider"), m.get("telegram"))
m = _dat("anthropic-cli", "opus")
check("chưa ghim: Telegram dùng đúng model chính",
      main._chat_provider_kenh(m, "telegram")[0] == "anthropic-cli"
      and main._chat_provider_kenh(m, "telegram")[3] == "opus")

# ---- 2. Ghim: web đổi mặc kệ ----------------------------------------------------
m = _dat("anthropic-cli", "opus", "openrouter", "openai/gpt-4o-mini", key="sk-or-test")
prov, kind, key, model = main._chat_provider_kenh(m, "telegram")
check("đã ghim: Telegram chạy model ghim, không phải model chính",
      prov == "openrouter" and model == "openai/gpt-4o-mini", (prov, model))
m = _dat("anthropic-cli", "haiku", "openrouter", "openai/gpt-4o-mini", key="sk-or-test")
check("CANARY: đổi model chính trên web KHÔNG kéo Telegram theo",
      main._chat_provider_kenh(m, "telegram")[3] == "openai/gpt-4o-mini")
# Ghim là của RIÊNG kênh Telegram. Web, CLI, Zalo vẫn theo model chính.
check("web/CLI/Zalo vẫn theo model chính, không ăn theo ghim Telegram",
      main._chat_provider_kenh(m, "cli")[0] == "anthropic-cli"
      and main._chat_provider_kenh(m, "zalo")[0] == "anthropic-cli")

# ---- 3. Ghim hỏng thì rơi về model chính, không chết kênh ---------------------
m = _dat("anthropic-cli", "opus", "openrouter", "openai/gpt-4o-mini", key="")
s = cfgmod.read_settings(); s["model"]["openrouter_key"] = ""; cfgmod.write_settings(s)
m = cfgmod.read_settings()["model"]
check("CANARY: key của provider ghim bị xoá thì lui về model chính, không chết lượt chat",
      main._chat_provider_kenh(m, "telegram")[0] == "anthropic-cli")
m = _dat("anthropic-cli", "opus", "gemini-cli", "gemini-2.5-pro")
check("CANARY: provider đã gỡ khỏi app thì ô ghim tự về rỗng lúc đọc settings",
      not (cfgmod.read_settings()["model"]["telegram"] or {}).get("provider"))

# ---- 4. Lệnh trên Telegram ghi vào đúng ô -----------------------------------
_dat("anthropic-cli", "opus")
r = chay(main._tg_command("model", "ghim", chat="1"))
mm = cfgmod.read_settings()["model"]
check("/model ghim khoá Telegram vào model ĐANG DÙNG",
      mm["telegram"] == {"provider": "anthropic-cli", "model": "opus"}, mm["telegram"])
check("và câu trả lời nói web đổi không còn kéo theo", "không còn kéo" in (r or {}).get("reply", ""))
# Đang ghim: /model <tên> chỉ đổi Telegram, model chính đứng yên.
r = chay(main._tg_command("model", "sonnet", chat="1"))
mm = cfgmod.read_settings()["model"]
check("CANARY: đang ghim thì /model <tên> đổi ô Telegram, KHÔNG đụng model chính",
      mm["telegram"]["model"] == "sonnet" and mm["main"]["model"] == "opus",
      (mm["telegram"], mm["main"]))
r = chay(main._tg_command("status", "", chat="1"))
check("/status nói rõ đang ghim riêng cho Telegram", "ghim riêng" in (r or {}).get("reply", ""))
check("/model (menu) cũng nói đang ghim", "GHIM" in main._model_header())
r = chay(main._tg_command("model", "theo", chat="1"))
mm = cfgmod.read_settings()["model"]
check("/model theo bỏ ghim", not mm["telegram"].get("provider"))
check("và /status nói theo model chính",
      "theo model chính" in (chay(main._tg_command("status", "", chat="1")) or {}).get("reply", ""))
# Chưa ghim: hành vi CŨ giữ nguyên - /model <tên> đổi model chính (và web đổi theo).
r = chay(main._tg_command("model", "haiku", chat="1"))
mm = cfgmod.read_settings()["model"]
check("chưa ghim thì /model <tên> vẫn đổi model chính như trước", mm["main"]["model"] == "haiku")

# ---- 5. Ràng buộc kiến trúc ---------------------------------------------------
_src = (SERVER / "main.py").read_text(encoding="utf-8")
_tg = _src.split("async def _tg_answer(", 1)[1].split("\ndef _tg_ket(", 1)[0]
check("CANARY: lượt chủ trên Telegram đi qua _chat_provider_kenh", "_chat_provider_kenh(mcfg, channel)" in _tg)
check("CANARY: bot chuyên trách KHÔNG ăn theo ghim của chủ", "_chat_provider(mcfg) if bot" in _tg)
_cb = _src.split("async def _tg_callback(", 1)[1].split("\nasync def _tg_command(", 1)[0]
check("nút chọn model trên Telegram cũng ghi qua _tg_dat_model", "_tg_dat_model(s, pid, mdl)" in _cb)
_help = chay(main._tg_help_text("brain"))
check("/help có nhắc /model ghim", "/model ghim" in _help)
_js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("trang Models có khối Model Telegram", 'id="tgCard"' in _js and 'telegram: { provider: prov, model: mod }' in _js)
check("bỏ ghim trên web ghi provider rỗng (= theo model chính)", 'telegram: { provider: "", model: "" }' in _js)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails))
    raise SystemExit(1)
print("Tất cả xanh.")
