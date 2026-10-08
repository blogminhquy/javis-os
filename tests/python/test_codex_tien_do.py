"""Codex hiện bước đang chạy NGAY lúc bắt đầu, không im tới khi xong (0.86.1).

    python tests/run.py codex_tien_do      (KHÔNG mạng, Codex giả)

Khách báo 08/10/2026: ra lệnh xong Javis "xử lý một lúc rồi đứng im". Một phần của chuyện đó:
nhánh Codex chỉ nghe `item.completed`, nên suốt lúc một lệnh dài chạy (cài thư viện, quét file),
khung chat không có gì mới, chỉ chữ "Javis đang suy nghĩ..." đếm giờ, trông như treo. Đo trên
Codex 0.160 thật: lệnh `ping` 5 giây có `item.started` ở giây 8,8, `item.completed` ở giây 14.

Điều được ghim:
  1. CodexCLI phát `progress` ngay lúc `item.started`, TRƯỚC khi bước đó xong; `tool_call` lúc xong
     vẫn y như cũ (Telegram, việc nền, workflow đọc nó), kèm `id` để ghép cặp.
  2. Lượt chat web: bước bắt đầu thành khung `tool_call` (bước đang chạy + chip "Chạy lệnh: ..."),
     bước xong thành `tool_result` (đánh dấu xong), không thành bước đôi.
  3. Bước không có `item.started` (bản CLI cũ) vẫn hiện như trước, một `tool_call` lúc xong.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import sys
import tempfile
import time

import test_luot_chat_codex as harness   # dựng WebSocket giả + đẩy một lượt qua websocket_endpoint
from claude_cli import CodexCLI

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


# ---- 1. CodexCLI: progress tới trước khi bước xong ----
cmd = {"id": "item_1", "type": "command_execution", "command": "npm install", "status": "in_progress"}
done = dict(cmd, status="completed", aggregated_output="added 312 packages")
script = "\n".join([
    "import json, time",
    f"print(json.dumps({json.dumps({'type': 'thread.started', 'thread_id': 't1'})}), flush=True)",
    f"print(json.dumps({json.dumps({'type': 'item.started', 'item': cmd})}), flush=True)",
    "time.sleep(1.2)",
    f"print(json.dumps({json.dumps({'type': 'item.completed', 'item': done})}), flush=True)",
    f"print(json.dumps({json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'xong'}})}), flush=True)",
    f"print(json.dumps({json.dumps({'type': 'turn.completed', 'usage': {}})}), flush=True)",
])
cli = CodexCLI(cwd=tempfile.gettempdir())
cli.cli_path = sys.executable
cli._build_args = lambda: [sys.executable, "-c", script]


async def _gom():
    t0, out = time.monotonic(), []
    async for e in cli.query("x"):
        out.append((round(time.monotonic() - t0, 2), e))
    return out


evs = asyncio.run(_gom())
loai = [e["type"] for _, e in evs]
prog = [(t, e) for t, e in evs if e["type"] == "progress"]
tc = [(t, e) for t, e in evs if e["type"] == "tool_call"]
check("Codex: item.started thành progress", len(prog) == 1 and prog[0][1]["name"] == "command_execution", loai)
check("Codex: progress mang câu lệnh và id", bool(prog) and prog[0][1]["item"].get("command") == "npm install"
      and prog[0][1]["id"] == "item_1")
check("Codex: progress tới TRƯỚC lúc bước xong (không đợi lệnh chạy hết)",
      bool(prog) and bool(tc) and tc[0][0] - prog[0][0] >= 1.0, [(t, e["type"]) for t, e in evs])
check("Codex: tool_call lúc xong vẫn như cũ, kèm cùng id",
      len(tc) == 1 and tc[0][1]["name"] == "command_execution" and tc[0][1]["id"] == "item_1")


# ---- 2. Lượt chat web: bắt đầu = bước đang chạy, xong = đánh dấu xong ----
class _CodexTienDo(harness._CodexGia):
    async def query(self, prompt):
        yield {"type": "progress", "name": "command_execution", "id": "i1",
               "item": {"id": "i1", "type": "command_execution", "command": "npm install"}}
        yield {"type": "tool_call", "name": "command_execution", "id": "i1",
               "item": {"id": "i1", "type": "command_execution", "command": "npm install",
                        "aggregated_output": "added 312 packages"}}
        # Bản CLI cũ không có item.started: vẫn phải hiện một bước lúc xong.
        yield {"type": "tool_call", "name": "pos_statistics", "id": "i2",
               "item": {"id": "i2", "type": "mcp_tool_call", "tool": "pos_statistics"}}
        yield {"type": "text", "content": "Xong rồi anh."}
        yield {"type": "final", "content": "Xong rồi anh.", "session_id": "thread-codex-1",
               "tokens_in": 10, "tokens_out": 2}


class _Patch:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, old in reversed(self._undo):
            setattr(obj, name, old)


harness._CodexGia = _CodexTienDo
mp = _Patch()
try:
    import pathlib
    ws, _store = harness._chay_mot_luot(mp, pathlib.Path(tempfile.mkdtemp(prefix="javis-codex-td-")))
finally:
    mp.undo()
khung = [(g.get("type"), g.get("tool") or g.get("content")) for g in ws.sent
         if g.get("type") in ("tool_call", "tool_result")]
check("web: bước bắt đầu thành tool_call, xong thành tool_result, không bước đôi",
      khung[:2] == [("tool_call", "command_execution"), ("tool_result", "added 312 packages")], khung)
check("web: bước không có item.started vẫn hiện một tool_call", khung[2:] == [("tool_call", "pos_statistics")], khung)
first = next((g for g in ws.sent if g.get("type") == "tool_call"), {})
check("web: bước đang chạy có chi tiết câu lệnh cho chip", "npm install" in str(first.get("detail") or ""), first)
check("web: lượt vẫn chạy trọn", any(g.get("type") == "response" and g.get("content") == "Xong rồi anh."
                                     for g in ws.sent) and not [g for g in ws.sent if g.get("type") == "error"])

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
