"""Một lượt lập trình đầu-cuối của engine API trong phiên Coding mức Toàn quyền (0.256.0).

    python tests/run.py vong_lap_trinh_e2e

Model giả (thay httpx) gọi lần lượt: tìm code, đọc theo đoạn, sửa một đoạn, chạy test bằng
terminal có pipe, rồi trả lời. Mọi lời gọi đi qua ĐÚNG đường thật: vòng tool của engine
(`_cc_tool_loop`) -> `mcp_client.call_route` -> route builtin của hub dựng cho phiên Coding. Phép
thử này bắt lỗi ở chỗ nối giữa các mảnh mà test từng mảnh không thấy.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
# 0.438.5: vòng tool mặc định gọi model dạng stream. File này thử logic vòng tool trên đường non-stream
# (giả lập client.post / máy chủ trả JSON), đường đó vẫn là đường lui. Đường stream: test_api_stream_vong.py.
os.environ["JAVIS_API_STREAM_TOOLS"] = "0"
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-e2e-code-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import coding_checkpoint  # noqa: E402
import coding_terminal  # noqa: E402
import engine  # noqa: E402
import mcp_hub  # noqa: E402
from coding_ctx import CodingToolContext  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


if os.name == "nt" or not coding_terminal._git_bash():
    print("bỏ qua: cần bash (Windows CI)")
    print("OK - test_vong_lap_trinh_e2e: bỏ qua trên máy không có bash")
    sys.exit(0)

VAULT = Path(_TMP) / "brain"
WS = Path(_TMP) / "du-an"
VAULT.mkdir()
(WS / "src").mkdir(parents=True)
(WS / "src" / "tinh.py").write_text("def cong(a, b):\n    return a - b\n", encoding="utf-8")

ctx = CodingToolContext(session_id="e2e", workspace_root=str(WS), workspace_roots=(str(WS),),
                        permission_mode="full")
tools, route = mcp_hub._builtin_tools("full", str(VAULT), workspace_root=[str(WS)], coding_ctx_cua_phien=ctx)
coding_checkpoint.luot_moi("e2e")

KICH_BAN = [
    ("javis_search_files", {"pattern": "def cong"}),
    ("javis_read_file", {"path": "src/tinh.py", "offset": 1, "limit": 50}),
    ("javis_edit_file", {"path": "src/tinh.py", "old_string": "return a - b", "new_string": "return a + b"}),
    ("javis_terminal", {"command": "cd src && python3 -c 'import tinh; print(tinh.cong(2, 3))' | tr -d '\\n'"}),
]
gui = []


class _Resp:
    def __init__(self, d):
        self._d, self.status_code, self.text = d, 200, ""

    def json(self):
        return self._d

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        gui.append(json)
        i = len(gui) - 1
        if i < len(KICH_BAN):
            ten, args = KICH_BAN[i]
            return _Resp({"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"c{i}", "type": "function",
                 "function": {"name": ten, "arguments": __import__("json").dumps(args)}}]}}]})
        return _Resp({"choices": [{"message": {"role": "assistant", "content": "Đã sửa hàm cong."}}]})


engine.httpx.AsyncClient = _Client


async def chay():
    async def _vong():
        async for ev in engine._cc_tool_loop("http://x", {}, "m", [{"role": "user", "content": "sửa hàm cong"}],
                                             tools, route, {}, "test"):
            yield ev
    out = []
    async for ev in engine.chay_trong_phien_coding(_vong):
        out.append(ev)
    return out


out = asyncio.run(chay())
ket_qua = [m["content"] for m in gui[-1]["messages"] if m.get("role") == "tool"]
check("model gọi đủ 4 công cụ", [e["name"] for e in out if e.get("type") == "tool_call"] == [t for t, _ in KICH_BAN])
check("tìm thấy hàm trong repo", "src/tinh.py:1:def cong" in ket_qua[0])
check("đọc có số dòng", ket_qua[1].startswith("1|def cong"))
check("sửa đúng một chỗ, có diff", ket_qua[2].startswith("Đã sửa") and "+    return a + b" in ket_qua[2])
check("file trên đĩa đã đổi", "return a + b" in (WS / "src" / "tinh.py").read_text())
check("terminal chạy pipe và cd, ra đúng kết quả sau khi sửa", ket_qua[3].startswith("exit=0") and "5" in ket_qua[3])
check("lượt kết thúc bằng câu trả lời", any(e.get("type") == "text" and "Đã sửa" in e.get("content", "") for e in out))
moc = coding_checkpoint.danh_sach("e2e")
check("có đúng một mốc khôi phục cho lượt này", len(moc) == 1)
check("mốc giữ bản TRƯỚC khi sửa", "-    return a - b" in coding_checkpoint.diff_file("e2e", moc[0]["id"], "src/tinh.py"))
check("công cụ gửi lên model có đủ bộ lập trình",
      {t["function"]["name"] for t in gui[0]["tools"]} >= {"javis_read_file", "javis_edit_file",
                                                          "javis_search_files", "javis_terminal", "javis_process"})

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_vong_lap_trinh_e2e: tất cả pass")
