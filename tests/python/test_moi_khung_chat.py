"""Mọi khung chat của CHỦ có cùng một hộp công cụ, không riêng trang Code (0.259.0).

    python tests/run.py moi_khung_chat

Chủ repo, 2026-10-20: "không chỉ muốn lập trình được trong trang code đâu mà mọi chỗ đều phải có
các chức năng như nhau ở mọi khung chat". Phải giữ:
  - Khung chat thường: thư mục làm việc là thư mục đã ghim (nếu có) rồi tới gốc brain, mức Toàn
    quyền, nên có terminal, sửa và tìm file, mốc khôi phục, 150 vòng tool.
  - Trang Code vẫn theo chip quyền của phiên.
  - Telegram của chủ đi cùng đường; bot của khách (kể cả bot mức Toàn quyền) KHÔNG có terminal.
  - Ghi chú trong brain vẫn ghi như cũ: không bị chèn số dòng, không bị bắt đọc trước khi ghi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-moikhung-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import coding_store  # noqa: E402
import main  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


BRAIN = Path(_TMP) / "brain"
(BRAIN / "notes").mkdir(parents=True)
(BRAIN / "notes" / "a.md").write_text("dòng một\ndòng hai\n", encoding="utf-8")
GHIM = Path(_TMP) / "du-an-ghim"
GHIM.mkdir()
(GHIM / "app.py").write_text("print(1)\n", encoding="utf-8")
br = str(BRAIN.resolve())

# ---- 1. Ngữ cảnh của từng loại lượt ----
ctx = main._coding_ctx_luot({"id": "s-thuong", "channel": "web"}, br)
check("khung chat thường có ngữ cảnh, gốc là brain, mức full",
      ctx is not None and ctx.workspace_root == br and ctx.permission_mode == "full", ctx)
check("khung chat thường báo về đúng khung chat web", ctx.chat_id == "web:s-thuong")

rec = coding_store.them_thu_muc(str(GHIM), brain=br)
coding_store.dat_rang_buoc("s-ghim", thu_muc_id=rec["id"])
ctx = main._coding_ctx_luot({"id": "s-ghim", "channel": "web"}, br)
check("khung chat có ghim thư mục: thư mục ghim đứng đầu, brain vẫn trong danh sách",
      ctx.workspace_root == str(GHIM.resolve()) and br in ctx.workspace_roots, ctx)

coding_store.dat_rang_buoc("s-code", thu_muc_id=rec["id"], muc_quyen="auto")
ctx = main._coding_ctx_luot({"id": "s-code", "channel": coding_store.KENH}, br)
check("trang Code vẫn theo chip quyền", ctx.permission_mode == "auto" and ctx.workspace_root == str(GHIM.resolve()), ctx)

ctx = main._coding_ctx_luot(None, br, sid="tg-123", chat_id="123")
check("Telegram của chủ có ngữ cảnh, báo về chat id Telegram", ctx is not None and ctx.chat_id == "123"
      and ctx.permission_mode == "full", ctx)
check("không biết phiên nào thì không có ngữ cảnh", main._coding_ctx_luot(None, br) is None)

_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("đường dashboard truyền phiên của mọi khung chat (không riêng Coding)", "coding_row=_row0, owner_sid=conv_sid" in _src)
check("Telegram: bot của khách KHÔNG nhận ngữ cảnh (terminal không thuộc về người lạ)",
      "_chu_tg = not bot" in _src and 'owner_sid=(str(conv_sid or f"{channel}-{chat_id}") if _chu_tg else "")' in _src)
check("lượt /plan ở khung chat thường bị hạ xuống suggest", "mode=_muc_quyen_luot_chat(_row0, user_message)," in _src)

# ---- 2. Hộp công cụ của khung chat thường ----
ctx = main._coding_ctx_luot({"id": "s-thuong", "channel": "web"}, br)
tools, route = mcp_hub._builtin_tools("full", br, workspace_root=list(ctx.workspace_roots), coding_ctx_cua_phien=ctx)
co = set(route)
check("khung chat thường có terminal và quản lý tiến trình", {"javis_terminal", "javis_process"} <= co)
check("khung chat thường có sửa, tìm file và web", {"javis_edit_file", "javis_search_files",
                                                    "javis_web_search", "javis_web_fetch"} <= co)
_v, _ = mcp_hub._apply_lazy(tools, route, force=True)
check("sửa và tìm file hiện thẳng ở khung chat thường", {"javis_edit_file", "javis_search_files"}
      <= {x["fn"] for x in _v})
ra = asyncio.run(route["javis_read_file"]["call"]({"path": "notes/a.md"}))
check("ghi chú trong brain đọc như cũ, không bị chèn số dòng", ra == "dòng một\ndòng hai\n", ra)
ra = asyncio.run(route["javis_write_file"]["call"]({"path": "notes/a.md", "content": "mới"}))
check("ghi đè ghi chú trong brain không bị bắt đọc trước", ra.startswith("Đã ghi"), ra)
_, r_plan = mcp_hub._builtin_tools("suggest", br, workspace_root=list(ctx.workspace_roots), coding_ctx_cua_phien=ctx)
check("lượt /plan ở khung chat thường không có terminal", "javis_terminal" not in r_plan)

# Thư mục ghim NGOÀI brain thì có rào như trang Code.
ctx_g = main._coding_ctx_luot({"id": "s-ghim", "channel": "web"}, br)
_, r_g = mcp_hub._builtin_tools("full", br, workspace_root=list(ctx_g.workspace_roots), coding_ctx_cua_phien=ctx_g)
ra = asyncio.run(r_g["javis_write_file"]["call"]({"path": str(GHIM / "app.py"), "content": "x"}))
check("thư mục ghim ngoài brain: ghi đè file chưa đọc bị chặn", ra.startswith("ERROR"), ra)

if os.name != "nt":
    ra = asyncio.run(route["javis_terminal"]["call"]({"command": "pwd"}))
    check("terminal của khung chat thường đứng ở gốc brain", ra.rstrip().endswith(br), ra)
else:
    print("bỏ qua: chạy terminal thật cần bash (Windows CI)")

# ---- 3. Bot của khách ----
_, r_bot = mcp_hub._builtin_tools("full", br)
check("lượt không có ngữ cảnh (bot, việc nền) không có terminal", "javis_terminal" not in r_bot)
check("bot của khách không có tool web", {"javis_web_search", "javis_web_fetch"} <= mcp_hub.OWNER_ONLY_TOOLS)

# ---- 4. Hoàn tác ở mọi khung chat ----
_cd = (ROOT / "dashboard" / "coding.js").read_text(encoding="utf-8")
check("menu + của ô soạn tin có mục Hoàn tác", 'id: "undo"' in _cd and 'label: "cp.undo"' in _cd)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_moi_khung_chat: tất cả pass")
