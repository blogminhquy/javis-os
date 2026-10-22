"""Ai thấy công cụ chạy lệnh nào (0.256.0).

    python tests/run.py quyen_cong_cu_coding

Bảng phải giữ, mỗi ô một phép thử:

    chat thường                không javis_run_command, không javis_terminal
    Coding mức Plan (suggest)  không công cụ chạy lệnh nào
    Coding mức Tự động (auto)  javis_run_command (allowlist, không shell), không terminal
    Coding mức Toàn quyền      javis_run_command + javis_terminal + javis_process
    Toàn quyền nhưng lượt /plan (hub mode suggest)   không terminal

Cộng: main.py thật sự truyền thư mục làm việc vào hub cho engine API (trước 0.256.0 không chỗ
nào truyền, nên engine API trong phiên Coding không đọc nổi file nào của repo), và cache tool
của hub tách theo phiên (terminal giữ cwd, biến môi trường, tiến trình nền của MỘT phiên).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-quyencd-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import mcp_hub  # noqa: E402
from coding_ctx import CodingToolContext  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


VAULT = Path(_TMP) / "brain"
WS = Path(_TMP) / "du-an"
VAULT.mkdir(parents=True)
WS.mkdir(parents=True)


def bo(mode, muc=None, sid="p1"):
    if muc is None:
        _t, r = mcp_hub._builtin_tools(mode, str(VAULT))
    else:
        ctx = CodingToolContext(session_id=sid, workspace_root=str(WS), workspace_roots=(str(WS),),
                                permission_mode=muc)
        _t, r = mcp_hub._builtin_tools(mode, str(VAULT), workspace_root=[str(WS)], coding_ctx_cua_phien=ctx)
    return set(r)


CHAY = {"javis_run_command", "javis_terminal", "javis_process"}
check("chat thường: không công cụ chạy lệnh nào", not (bo("full") & CHAY))
check("Coding Plan: không công cụ chạy lệnh nào", not (bo("suggest", "suggest") & CHAY))
check("Coding Tự động: chỉ javis_run_command", bo("auto", "auto") & CHAY == {"javis_run_command"})
check("Coding Toàn quyền: có cả terminal và process", bo("full", "full") & CHAY == CHAY)
check("Toàn quyền nhưng lượt /plan: không terminal", not (bo("suggest", "full") & {"javis_terminal", "javis_process"}))
check("mọi bậc đều có sửa và tìm file", all({"javis_edit_file", "javis_search_files"} <= bo(m, q)
                                          for m, q in (("full", None), ("auto", "auto"), ("full", "full"))))

# Terminal của phiên chạy thật được qua route, và chặn cứng vẫn chặn.
ctx = CodingToolContext(session_id="p-chay", workspace_root=str(WS), workspace_roots=(str(WS),),
                        permission_mode="full")
_t, r = mcp_hub._builtin_tools("full", str(VAULT), workspace_root=[str(WS)], coding_ctx_cua_phien=ctx)
if os.name != "nt":
    ra = asyncio.run(r["javis_terminal"]["call"]({"command": "echo xin-chao | tr a-z A-Z"}))
    check("terminal qua hub chạy được pipe", "XIN-CHAO" in ra)
    ra = asyncio.run(r["javis_terminal"]["call"]({"command": "sudo rm -rf /"}))
    check("terminal qua hub: chặn cứng vẫn chặn", ra.startswith("ERROR") and "chặn cứng" in ra)
else:
    print("bỏ qua: chạy terminal thật cần bash (Windows CI)")

# Route của terminal phải được cache theo phiên.
_src_hub = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
check("khoá cache của hub có mã phiên Coding", "_sid_ctx" in _src_hub and "str(_sid_ctx or \"\")" in _src_hub)
check("terminal có trong nhóm hạt nhân (không bị giấu sau tìm kiếm)",
      {"javis_terminal", "javis_process"} <= set(mcp_hub.CORE_TOOL_FNS))
# Sửa và tìm file: hạt nhân trong phiên Coding, nằm trong pool ở chat thường (trần token của
# test_prompt_budget không chừa chỗ cho chúng ở MỌI lượt chat).
_t_cd, _r_cd = mcp_hub._builtin_tools("full", str(VAULT), workspace_root=[str(WS)], coding_ctx_cua_phien=ctx)
_t_th, _r_th = mcp_hub._builtin_tools("full", str(VAULT))
_v_cd, _ = mcp_hub._apply_lazy(_t_cd, _r_cd, force=True)
_v_th, _ = mcp_hub._apply_lazy(_t_th, _r_th, force=True)
_ten = lambda ds: {x["fn"] for x in ds}
check("phiên Coding: sửa và tìm file luôn hiện thẳng", {"javis_edit_file", "javis_search_files"} <= _ten(_v_cd))
check("chat thường: sửa và tìm file nằm sau javis_search_tools",
      not ({"javis_edit_file", "javis_search_files"} & _ten(_v_th)) and "javis_search_tools" in _ten(_v_th))
check("terminal ghi nhật ký kiểm toán", '"conn_id": "javis-terminal"' in _src_hub)

# main.py nối phiên Coding vào hub.
_src_main = (SERVER / "main.py").read_text(encoding="utf-8")
check("main truyền thư mục làm việc vào hub cho engine API",
      "workspace_root=list(_cctx.workspace_roots)" in _src_main and "coding_ctx_cua_phien=_cctx" in _src_main)
check("đường chat dashboard truyền dòng phiên và mức quyền của phiên", "coding_row=_row0" in _src_main
      and "_muc_quyen_luot_chat(_row0, user_message)" in _src_main)
check("chỉ phiên trang Coding (kênh coding:) mới nhận ngữ cảnh Coding",
      'str(row.get("channel") or "").startswith("coding:")' in _src_main)
check("phiên Coding chạy vòng tool với trần riêng", "engine.chay_trong_phien_coding(" in _src_main)
check("xoá phiên thì dọn terminal và mốc", "coding_terminal.don_phien" in _src_main
      and "coding_checkpoint.don_phien" in _src_main)

# Trần vòng riêng cho Coding.
import engine  # noqa: E402


async def _thu():
    async def _gen():
        yield engine._max_tool_rounds()
        yield engine._clip_tool_result("x" * 20_000, ten="javis_terminal")
    ra = []
    async for v in engine.chay_trong_phien_coding(_gen):
        ra.append(v)
    return ra


vong, cat = asyncio.run(_thu())
check("trong phiên Coding: trần mặc định 150 vòng", vong == 150)
check("tool tự phân trang (terminal, đọc file, web): 20.000 ký tự không bị cắt", len(cat) == 20_000)
check("kết quả MCP vẫn cắt ở 8.000 kể cả trong phiên Coding (0.259.0)",
      len(engine._clip_tool_result("x" * 20_000, ten="pos_list_orders")) < 9_000)
check("ngoài phiên Coding: vẫn 30 vòng", engine._max_tool_rounds() == 30)
check("ngoài phiên Coding: vẫn cắt ở 8.000", len(engine._clip_tool_result("x" * 20_000)) < 9_000)
check("nhắc chốt việc khi còn 10 vòng", engine._nhac_sap_het(139, 150) != "" and engine._nhac_sap_het(10, 150) == "")
os.environ["JAVIS_MAX_TOOL_ROUNDS_CODING"] = "9999"


async def _thu2():
    async def _gen():
        yield engine._max_tool_rounds()
    async for v in engine.chay_trong_phien_coding(_gen):
        return v


check("JAVIS_MAX_TOOL_ROUNDS_CODING kẹp ở 500", asyncio.run(_thu2()) == 500)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_quyen_cong_cu_coding: tất cả pass")
