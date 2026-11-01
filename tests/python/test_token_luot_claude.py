"""Bớt token mỗi lượt chat trên Claude Code (0.345.0).

    python tests/run.py token_luot_claude

Đo thật 27/10/2026 (bộ não Claude Code, brain nằm trong repo như bản cài thường): một câu "chào em"
tốn 60.808 token. Ba thứ ghim ở đây:
  1. CLAUDE.md của repo LÀ prompt Javis, đã gắn qua --append-system-prompt-file. Claude Code đi ngược từ
     cwd lên và nạp nó thêm lần nữa (~12.300 token). `claudeMdExcludes` loại đúng file đó.
  2. Claude Code giữ system prompt của lượt ĐẦU khi nối phiên, nên giờ trong system prompt đông cứng
     (đo thật: hỏi lúc 08:53, Javis trả 08:51). Lượt nối phiên mang giờ gửi tin ở đầu prompt.
  3. Engine báo phần token chỉ đọc lại từ cache (`tokens_cache_read`). Khung chat từng hiện số token mới dưới
     mỗi câu trả lời; từ 0.374.0 chủ repo bỏ hẳn số đó khỏi khung chat (xem trang Mức dùng).
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
import claude_cli  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---- 1. CLAUDE.md của Javis không nạp hai lần ----
# claude_sdk_engine.py bị ghim băm bởi bằng chứng kiểm định native, nên việc này làm ở factory
# claude_cli.claude_engine (mọi engine Claude đều dựng qua đó) và ở main._cli_fast (lượt chat).
CLAUDE_MD = (ROOT / "CLAUDE.md").resolve()
e = claude_cli.claude_engine(tag="chat")
cfg = json.loads(e._options().settings)
check("settings loại đúng CLAUDE.md của repo (prompt Javis)", str(CLAUDE_MD) in cfg.get("claudeMdExcludes", []),
      cfg)
check("chỉ loại MỘT file đó, không loại CLAUDE.md của người dùng hay của brain",
      {os.path.basename(p) for p in cfg["claudeMdExcludes"]} == {"CLAUDE.md"}
      and all(p.replace("\\", "/").startswith(str(ROOT).replace("\\", "/")) for p in cfg["claudeMdExcludes"]),
      cfg["claudeMdExcludes"])
check("main.CLAUDE_MD_PATH trỏ cùng file đã loại (đổi chỗ prompt thì phải đổi cả hai)",
      main.CLAUDE_MD_PATH.resolve() == CLAUDE_MD)
check("vẫn giữ fastMode false mặc định", cfg.get("fastMode") is False, cfg)
tok = fast_mode.use(True)
e.model = "claude-opus-5-5"
main._cli_fast(e)
fast_mode.CURRENT.reset(tok)
cfg2 = json.loads(e._options().settings)
check("chế độ nhanh vẫn đi cùng danh sách loại", cfg2.get("fastMode") is True
      and str(CLAUDE_MD) in cfg2.get("claudeMdExcludes", []), cfg2)
g = claude_cli.claude_engine(tag="loop", allowed_tools=["Read"])
check("lượt nền khoá quyền cũng loại (cùng cwd brain trong repo)",
      str(CLAUDE_MD) in json.loads(g._options().settings).get("claudeMdExcludes", []))
check("danh sách loại sẵn có được giữ, không trùng",
      json.loads(claude_cli.javis_claude_settings('{"claudeMdExcludes": ["/x/CLAUDE.md"]}'))["claudeMdExcludes"][0]
      == "/x/CLAUDE.md"
      and len(json.loads(claude_cli.javis_claude_settings(claude_cli.javis_claude_settings()))["claudeMdExcludes"])
      == len(json.loads(claude_cli.javis_claude_settings())["claudeMdExcludes"]))
check("settings hỏng thì vẫn ra JSON hợp lệ", json.loads(claude_cli.javis_claude_settings("{hỏng")).get("fastMode") is False)
# Native compaction window (0.345.0): measured effectiveWindow=980000 by default on a 1M model,
# 180000 with autoCompactWindow=200000 (a number: the string "200k" is ignored in settings).
check("every Claude run compacts natively near 200k", cfg.get("autoCompactWindow") == 200_000, cfg)
check("...also with fast mode on", cfg2.get("autoCompactWindow") == 200_000, cfg2)
for env, want in (("auto", None), ("150k", 150_000), ("50000", 100_000), ("5000000", 1_000_000), ("rác", 200_000)):
    os.environ["JAVIS_CLAUDE_COMPACT_WINDOW"] = env
    got = json.loads(claude_cli.javis_claude_settings()).get("autoCompactWindow")
    check(f"JAVIS_CLAUDE_COMPACT_WINDOW={env} -> {want}", got == want, got)
os.environ.pop("JAVIS_CLAUDE_COMPACT_WINDOW", None)

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
# Engine Claude Code: bọc map_message từ ngoài (như plan_limits), chạy trên ResultMessage THẬT của SDK.
import claude_sdk_engine as ENG  # noqa: E402
from claude_agent_sdk import ResultMessage  # noqa: E402


def _chuoi_boc():
    f, n = ENG.map_message, 0
    while f is not None:
        n += 1
        f = getattr(f, "__wrapped__", None)
    return n


claude_cli.claude_engine(tag="chat")
n1 = _chuoi_boc()
claude_cli.claude_engine(tag="chat")
# 4 lớp: gốc, chữ chảy (0.438.4), đếm cache, hạn mức gói.
check("dựng engine nhiều lần không chồng thêm lớp bọc", _chuoi_boc() == n1 == 4, (n1, _chuoi_boc()))
kq = ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                   session_id="s-tok", result="Chào anh", usage={
                       "input_tokens": 9, "cache_read_input_tokens": 13357, "cache_creation_input_tokens": 47442,
                       "output_tokens": 30})
ev, _sid = ENG.map_message(kq)
fin = [x for x in ev if x.get("type") == "final"]
check("engine Claude Code báo tokens_cache_read trên sự kiện final",
      fin and fin[0].get("tokens_cache_read") == 13357 and fin[0].get("tokens_in") == 60808, fin)
STEER = (SERVER / "codex_steer.py").read_text(encoding="utf-8")
check("Codex cộng cachedInputTokens", 'tok_cache += int(lu.get("cachedInputTokens")' in STEER
      and '"tokens_cache_read": tok_cache' in STEER)
APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
# 0.374.0, chủ repo 28/10/2026: dòng dưới câu trả lời KHÔNG hiện số token nữa (trước đó, 0.345.0, nó hiện token mới
# trừ phần cache). Engine vẫn báo tokens_cache_read như trên; con số chỉ còn ở trang Mức dùng.
ctx = APP[APP.index("function _renderCtxLine"):APP.index("async function refreshTgStatus")]
check("dòng dưới câu trả lời không còn số token", '" token"' not in ctx and "ctx_in" not in ctx and "_fmtTok" not in ctx)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"i18n {lang}: bỏ hai chú thích token không còn dùng", "app.ctx_hint_tokens" not in d
          and "app.ctx_hint_tokens_new" not in d)

print()
if fails:
    raise SystemExit(f"FAIL {len(fails)}: " + "; ".join(fails[:4]))
print("Tất cả xanh.")
