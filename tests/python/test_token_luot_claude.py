"""Bớt token mỗi lượt chat trên Claude Code (0.345.0).

    python tests/run.py token_luot_claude

Đo thật 27/10/2026 (bộ não Claude Code, brain nằm trong repo như bản cài thường): một câu "chào em"
tốn 60.808 token. Ba thứ ghim ở đây:
  1. CLAUDE.md của repo LÀ prompt Javis, đã gắn qua --append-system-prompt-file. Claude Code đi ngược từ
     cwd lên và nạp nó thêm lần nữa (~12.300 token). `claudeMdExcludes` loại đúng file đó.
  2. Claude Code giữ system prompt của lượt ĐẦU khi nối phiên, nên giờ trong system prompt đông cứng
     (đo thật: hỏi lúc 08:53, Javis trả 08:51). Lượt nối phiên mang giờ gửi tin ở đầu prompt.
  3. Khung chat tách phần token chỉ đọc lại từ cache (`ctx_cache`), để "60k token" không bị đọc như
     60k token mới.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import datetime
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tokluot-"))
import context_compiler  # noqa: E402
import fast_mode  # noqa: E402
import main  # noqa: E402
from claude_sdk_engine import ClaudeSDK  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---- 1. CLAUDE.md của Javis không nạp hai lần ----
CLAUDE_MD = (ROOT / "CLAUDE.md").resolve()
e = ClaudeSDK(tag="chat")
cfg = json.loads(e._options().settings)
check("settings loại đúng CLAUDE.md của repo (prompt Javis)", str(CLAUDE_MD) in cfg.get("claudeMdExcludes", []),
      cfg)
check("chỉ loại MỘT file đó, không loại CLAUDE.md của người dùng hay của brain",
      {os.path.basename(p) for p in cfg["claudeMdExcludes"]} == {"CLAUDE.md"}
      and all(p.replace("\\\\", "/").startswith(str(ROOT).replace("\\\\", "/")) for p in cfg["claudeMdExcludes"]),
      cfg["claudeMdExcludes"])
check("main.CLAUDE_MD_PATH trỏ cùng file đã loại (đổi chỗ prompt thì phải đổi cả hai)",
      main.CLAUDE_MD_PATH.resolve() == CLAUDE_MD)
check("vẫn giữ fastMode false mặc định", cfg.get("fastMode") is False, cfg)
e.fast_settings = fast_mode.claude_sdk_settings("claude-opus-5-5", True)
cfg2 = json.loads(e._options().settings)
check("chế độ nhanh vẫn đi cùng danh sách loại", cfg2.get("fastMode") is True and cfg2.get("claudeMdExcludes"), cfg2)
g = ClaudeSDK(tag="loop", allowed_tools=["Read"])
check("lượt nền khoá quyền cũng loại (cùng cwd brain trong repo)",
      str(CLAUDE_MD) in json.loads(g._options().settings).get("claudeMdExcludes", []))

# ---- 2. Giờ gửi tin cho lượt nối phiên ----
now = datetime.datetime(2026, 10, 27, 8, 53, tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
ngan = context_compiler.dong_ho_ngan(now=now, lang="vi")
check("dòng giờ có giờ:phút, thứ, ngày", "08:53" in ngan and "Thứ Ba" in ngan and "27/10/2026" in ngan, ngan)
check("dòng giờ ngắn (nằm lại trong lịch sử phiên, mỗi lượt một dòng)", len(ngan) < 90, len(ngan))
check("tiếng Anh có nhãn tiếng Anh", "sent at" in context_compiler.dong_ho_ngan(now=now, lang="en"))


class _Cli:
    def __init__(self, sid):
        self.session_id = sid


p1 = main._gio_luot_noi_mach(_Cli("abc"), "mấy giờ rồi", "vi")
check("nối phiên: giờ gửi tin đứng đầu, câu người dùng giữ nguyên ở sau",
      p1.startswith("[") and p1.endswith("\nmấy giờ rồi"), p1)
check("phiên mới: không gắn (system prompt vừa dựng đã có giờ đúng)",
      main._gio_luot_noi_mach(_Cli(None), "mấy giờ rồi", "vi") == "mấy giờ rồi")
SRC = (SERVER / "main.py").read_text(encoding="utf-8")
check("lượt dashboard và lượt Telegram trên Claude Code đều gắn giờ",
      SRC.count("_gio_luot_noi_mach(cli, _cli_do_sau(cli, reasoning,") == 2)

# ---- 3. Token đọc từ cache tách riêng ----
f = main._ctx_frame(None, 60808, 13357)
check("khung chat nhận ctx_cache", f.get("ctx_in") == 60808 and f.get("ctx_cache") == 13357, f)
check("không có cache thì không thêm khoá", "ctx_cache" not in main._ctx_frame(None, 500), main._ctx_frame(None, 500))
check("cache không bao giờ vượt tổng", main._ctx_frame(None, 100, 999).get("ctx_cache") == 100)
check("mọi khung kết thúc lượt chat mang theo cache",
      SRC.count("_ctx_frame(runtime_trace, _ctx_in, _ctx_cache)") >= 10
      and "_ctx_frame(runtime_trace, _ctx_in)" not in SRC)
ENG = (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8")
check("engine Claude Code báo tokens_cache_read", '"tokens_cache_read": u.get("cache_read_input_tokens")' in ENG)
STEER = (SERVER / "codex_steer.py").read_text(encoding="utf-8")
check("Codex cộng cachedInputTokens", 'tok_cache += int(lu.get("cachedInputTokens")' in STEER
      and '"tokens_cache_read": tok_cache' in STEER)
APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("dashboard vẽ phần từ cache", "data.ctx_cache" in APP and 'window.t("app.ctx_cached"' in APP)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"i18n {lang}: có chữ cho cache và chú thích", "{n}" in d.get("app.ctx_cached", "")
          and d.get("app.ctx_hint_tokens"))

print()
if fails:
    raise SystemExit(f"FAIL {len(fails)}: " + "; ".join(fails[:4]))
print("Tất cả xanh.")
