"""Hồi quy: phiên Codex (hoặc bất kỳ client MCP nào) gọi tool Javis mà KHÔNG tự chèn header.

Bối cảnh (sự cố 2026-09-21): hub chỉ biết brain qua header `X-Javis-Vault`, và chỗ DUY NHẤT
ghi header đó là khi CHÍNH Javis khởi động tiến trình engine (`mcp_hub.codex_vault_override`
nhét vào argv `-c`, các engine khác ghi file cấu hình riêng từng lượt). Profile dùng chung
`~/.codex/<tên>.config.toml` thì cố ý không mang header - nên MỌI phiên Codex do người dùng tự
mở đều tới hub với `vault_root = None`, và `javis_task` fail-closed với câu "chưa biết đang làm
việc trên brain nào". Người dùng không có cách nào biết thiếu cái gì.

Luật sau khi sửa:
  1. Có header hợp lệ  -> dùng header, KHÔNG thêm dòng ghi chú nào (đường cũ, không đổi).
  2. Không header      -> lấy brain của cuộc trò chuyện được cập nhật GẦN NHẤT ("brain đang mở"),
                          và MỌI kết quả tool của lượt đó kèm một dòng nói rõ đang chạy brain nào.
  3. Chưa có phiên nào -> nếu BRAINS_DIR chỉ có đúng MỘT brain thì dùng nó (không thể nhầm).
  4. Không suy ra được -> vẫn lỗi, nhưng lỗi phải NÊU ĐÍCH DANH việc thiếu header và cách chữa.

Chạy:
    python tests/run.py hub_brain_mac_dinh
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-hub-brain-"))
_BRAINS = _TMP / "brains"
(_BRAINS / "Brain Default" / "Javis").mkdir(parents=True, exist_ok=True)
(_BRAINS / "Brain Phu" / "Javis").mkdir(parents=True, exist_ok=True)

os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_SESSIONS_DB"] = str(_TMP / "conversations.db")
os.environ["BRAINS_DIR"] = str(_BRAINS)
(_TMP / "state").mkdir(parents=True, exist_ok=True)

import mcp_hub  # noqa: E402
import sessions  # noqa: E402
import tasks  # noqa: E402

fails = []

MAC_DINH = str((_BRAINS / "Brain Default").resolve())
PHU = str((_BRAINS / "Brain Phu").resolve())


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ── hàng đợi Kanban thật, nhưng nằm trong thư mục tạm ────────────────────────
tasks._FEATURE = tasks.TasksFeature(tasks.TasksDeps(
    brain_root=lambda b: b or MAC_DINH,
    atomic_write_text=lambda p, s: Path(p).write_text(s, encoding="utf-8"),
    execute_workflow=lambda *a, **k: None,
    workflows_dir=lambda b: Path(b) / "workflows",
    build_system_prompt=lambda b: "",
    aux_model=lambda: None,
    safe_tools=[],
    state_dir=_TMP / "state",
))


class Req:
    """Đủ giống Request của starlette cho `mcp_hub.handle_http`."""

    def __init__(self, vault, body):
        self.headers = {"authorization": f"Bearer {mcp_hub.hub_token()}",
                        "x-javis-mode": "full"}
        if vault is not None:
            self.headers["x-javis-vault"] = vault
        self._body = body

    async def json(self):
        return self._body


def _goi_body(name, args):
    # Lazy đang bật (nhiều connector) thì tool plugin nấp sau `javis_run_tool`; gọi thẳng qua
    # meta-tool cho cả hai chế độ đều chạy một đường.
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "javis_run_tool", "arguments": {"name": name, "args": args}}}


async def goi(vault, name, args):
    mcp_hub.invalidate_cache()
    mcp_hub.quen_brain_dang_mo()
    resp = await mcp_hub.handle_http(Req(vault, _goi_body(name, args)))
    data = json.loads(resp.body.decode("utf-8"))
    con = (data.get("result") or {}).get("content") or []
    return con[0]["text"] if con else json.dumps(data, ensure_ascii=False)


async def chay():
    # ── 1. Chưa có phiên chat nào, BRAINS_DIR có 2 brain -> không đoán bừa ──
    ra = await goi(None, "javis_task", {"op": "list"})
    check("nhiều brain + chưa có phiên nào -> vẫn từ chối, không chạy nhầm brain",
          ra.startswith("ERROR:"))
    check("lỗi nêu đích danh header còn thiếu", "X-Javis-Vault" in ra)
    check("lỗi chỉ ra nguồn gây thiếu (cấu hình MCP phía client)", "cấu hình MCP" in ra)

    # ── 2. Có header -> chạy, và KHÔNG kèm dòng ghi chú brain ──
    ra = await goi(MAC_DINH, "javis_task", {"op": "list"})
    check("có header -> qua được cổng brain", not ra.startswith("ERROR: chưa biết"))
    check("có header -> không thêm dòng ghi chú thừa", "brain đang mở" not in ra)

    # ── 3. Không header, đã có phiên chat -> lấy brain của phiên gần nhất ──
    store = sessions.get_store()
    sid_cu = store.create_session(brain=PHU)
    store.append_message(sid_cu, "user", "cuộc cũ")
    await asyncio.sleep(0.02)
    sid_moi = store.create_session(brain=MAC_DINH)
    store.append_message(sid_moi, "user", "cuộc đang nói")
    # Ghim cuộc CŨ: `list_sessions` xếp mục ghim lên đầu, nên đây là bẫy mà một cách làm
    # "lấy phiên đầu danh sách" sẽ rơi vào - nó trả Brain Phu thay vì brain đang nói.
    store.set_pinned(sid_cu, True)

    ra = await goi(None, "javis_task", {"op": "list"})
    check("không header -> chạy được bằng brain đang mở", not ra.startswith("ERROR:"))
    check("nói rõ đang chạy trên brain nào", "Brain Default" in ra)
    check("mục ghim không cướp mất brain đang mở", "Brain Phu" not in ra)

    # ── 4. op=add cũng phải chạy (tiêu chí nghiệm thu của sự cố) ──
    ra = await goi(None, "javis_task", {"op": "add", "title": "việc thử từ phiên Codex"})
    check("op=add chạy được mà không cần người dùng tự chèn header",
          "Mã việc:" in ra or "Đã giao việc" in ra)
    check("op=add cũng nói rõ brain", "Brain Default" in ra)

    # ── 5. Header trỏ vào thư mục không tồn tại -> vẫn rơi về, và nói rõ header hỏng ──
    ra = await goi(str(_TMP / "khong-co-that"), "javis_task", {"op": "list"})
    check("header trỏ đường dẫn không có thật -> không chết câm",
          not ra.startswith("ERROR: chưa biết"))
    check("báo rõ header có gửi nhưng không dùng được", "không có thật" in ra or "không dùng được" in ra)


asyncio.run(chay())


# ── 6. BRAINS_DIR chỉ có MỘT brain -> rơi về chính nó, không cần phiên nào ──
async def chay_mot_brain():
    mot = _TMP / "brains-don"
    (mot / "Brain Default").mkdir(parents=True, exist_ok=True)
    os.environ["BRAINS_DIR"] = str(mot)
    # Kho phiên RỖNG: `SessionStore.__init__` chốt db_path mặc định từ lúc import nên đổi
    # `sessions.DB_PATH` không có tác dụng, phải dựng store trỏ thẳng vào DB trống.
    cu = sessions._store
    sessions._store = sessions.SessionStore(_TMP / "trong.db")
    try:
        mcp_hub.quen_brain_dang_mo()
        root, nguon, _ = mcp_hub.resolve_vault("")
        check("đúng một brain -> rơi về chính nó",
              root and Path(root).resolve() == (mot / "Brain Default").resolve())
        check("ghi nhận nguồn là 'duy-nhat'", nguon == "duy-nhat")
    finally:
        sessions._store = cu
        os.environ["BRAINS_DIR"] = str(_BRAINS)
        mcp_hub.quen_brain_dang_mo()


asyncio.run(chay_mot_brain())

print(("ĐỎ: " + str(len(fails))) if fails else "XANH: tất cả đều qua")
sys.exit(1 if fails else 0)
