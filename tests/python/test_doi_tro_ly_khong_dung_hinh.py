"""Đổi trợ lý giữa lúc một lượt đang chạy không được làm dashboard đứng hình.

    python tests/run.py doi_tro_ly

Chủ repo báo 23/09 kèm ảnh: trợ lý chạy Gemini qua Antigravity CLI đang trả lời, bấm sang
trợ lý khác thì màn hình không đổi một lúc lâu. Trang Cộng sự đổi trợ lý bằng ba request nối
nhau (/sessions?channel=..., /sessions/new, /sessions/{id}), nên hễ event loop của server bị
chặn là cả ba xếp hàng chờ. Test này khoá bốn chỗ từng chặn loop:

1. aux_engine.availability hỏi thẳng `agy models` (tới 80 giây) từ code async của việc nền
   (học sau lượt chat, Kanban, nhắc hẹn, loop).
2. Ba route phiên là `async def` làm sqlite đồng bộ ngay trên loop.
3. Hub dò MCP (giải mã kho kết nối, đọc mọi SKILL.md, nạp plugin) chạy đồng bộ trên loop, mà
   mỗi lượt agy là một tiến trình mới gọi lại hub.
4. Engine agy đọc hết stdout rồi mới đọc stderr: stderr đầy ống là lượt treo.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import inspect
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-doitroly-"))

import antigravity_cli  # noqa: E402
import aux_engine  # noqa: E402

fails = []


def check(name, cond):
    print(("  OK   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


# ---- 1. availability không bao giờ gọi bản chặn ----
_goc = (antigravity_cli.find_antigravity_cli, antigravity_cli.auth_status,
        antigravity_cli.auth_status_nen)
da_goi_chan = []


def _chan(*a, **k):
    da_goi_chan.append(1)
    return {"connected": True}


try:
    antigravity_cli.find_antigravity_cli = lambda: "/usr/bin/agy"
    antigravity_cli.auth_status = _chan
    antigravity_cli.auth_status_nen = lambda: {"connected": True}
    ok, _ = aux_engine.availability({"provider": aux_engine.ANTIGRAVITY}, {})
    check("đã đăng nhập (theo cache) thì khả dụng", ok)
    check("CANARY: không gọi auth_status() chặn loop", not da_goi_chan)

    antigravity_cli.auth_status_nen = lambda: {"connected": False, "error": "", "dang_kiem": True}
    ok, _ = aux_engine.availability({"provider": aux_engine.ANTIGRAVITY}, {})
    check("mới khởi động, cache đang kiểm: cứ cho chạy", ok)

    antigravity_cli.auth_status_nen = lambda: {"connected": False, "error": "chưa đăng nhập"}
    ok, why = aux_engine.availability({"provider": aux_engine.ANTIGRAVITY}, {})
    check("chưa đăng nhập thật thì vẫn báo không khả dụng", not ok and "chưa đăng nhập" in why)
finally:
    (antigravity_cli.find_antigravity_cli, antigravity_cli.auth_status,
     antigravity_cli.auth_status_nen) = _goc

# ---- 2. route phiên chạy ở threadpool ----
import main  # noqa: E402

for ten in ("sessions_list", "sessions_new", "sessions_get"):
    check(f"{ten} là def thường (FastAPI chạy ở threadpool, không chặn loop)",
          not inspect.iscoroutinefunction(getattr(main, ten)))
_vo = inspect.getsource(main.voice_options)
check("/voice/options hỏi `agy models` ở luồng phụ",
      "asyncio.to_thread(antigravity_cli.list_models)" in _vo)

# ---- 3. hub dò MCP: phần đồng bộ ra luồng phụ ----
import mcp_hub  # noqa: E402

_dis = inspect.getsource(mcp_hub.discover_all)
check("giải mã kho kết nối ở luồng phụ", "asyncio.to_thread(mcp_store.resolved" in _dis)
check("dựng tool builtin (đọc mọi SKILL.md) ở luồng phụ", "_builtin_tools, mode" in _dis
      and "asyncio.to_thread(\n        _builtin_tools" in _dis)
check("nạp plugin ở luồng phụ", "asyncio.to_thread(plugins_host.plugin_tools" in _dis)

# ---- 4. agy: stderr đọc song song ----
_ml = inspect.getsource(antigravity_cli.AntigravityCLI._mot_luot) \
    if hasattr(antigravity_cli, "AntigravityCLI") else inspect.getsource(antigravity_cli)
check("stderr đọc ở luồng riêng, không chờ stdout đóng",
      "iter(proc.stderr.readline" in _ml and "proc.stderr.read()" not in _ml)

if fails:
    raise SystemExit(f"\nFAIL - test_doi_tro_ly_khong_dung_hinh: {len(fails)} lỗi")
print("\nOK - test_doi_tro_ly_khong_dung_hinh: tất cả pass")
