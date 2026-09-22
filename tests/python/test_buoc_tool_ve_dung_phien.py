"""Lượt Antigravity có gọi công cụ thì khung `tool_call` phải tới được khung chat.

    python tests/run.py buoc_tool_ve_dung_phien

Bối cảnh: bản 0.63.8 thêm khối tiến trình từng bước, chủ dự án thử bằng bộ não Antigravity và
báo "không thấy tiến trình nào cả". File này ra đời để tái hiện, và nó đã BÁC BỎ giả thuyết
đầu tiên chứ không xác nhận.

Giả thuyết đầu (SAI): nhánh Antigravity gửi `tool_call` thiếu `session_id`, mà `app.js` định
tuyến mọi khung theo trường đó (`const sid = data.session_id || null`), nên khung rơi xuống
đất. Chạy thật một lượt qua `main.websocket_endpoint` thì thấy khung nào cũng có `session_id`
đầy đủ: `_SendProxy` trong `main.py` đội lốt ws và tự gắn sid vào MỌI khung của lượt, nên
thiếu sid là chuyện không thể xảy ra ở tầng này.

Gốc rễ thật nằm sâu hơn một tầng, ở bộ đọc sự kiện của CLI - xem `test_agy_buoc_tool.py`.

Giữ file này lại vì nó khoá NGUYÊN chuỗi cho đúng engine người dùng đang chạy: engine nhả
sự kiện tool -> nhánh antigravity trong `_do_turn` -> khung ra WebSocket -> đủ trường để
dashboard dựng được mạch bước. Một khâu đứt ở bất kỳ đâu trong chuỗi đó là test này đỏ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-agy-"))

from fastapi import WebSocketDisconnect  # noqa: E402

import main  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402
from sessions import SessionStore  # noqa: E402

_fails = []

PHIEN = "phien-agy"


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if (not cond and them) else ""))
    if not cond:
        _fails.append(name)


class _WSGia:
    """Giống _WSGia của test_luot_chat_codex: ở lại nghe tới khi lượt chốt rồi mới ngắt."""

    cookies = {}

    def __init__(self, payload):
        self._payload = json.dumps(payload)
        self.sent = []

    async def accept(self):
        pass

    async def close(self, code=None):
        pass

    async def send_text(self, value):
        self.sent.append(json.loads(value))

    async def receive_text(self):
        if self._payload is not None:
            value, self._payload = self._payload, None
            return value
        for _ in range(400):
            if any(g.get("type") == "turn_done" for g in self.sent):
                break
            await asyncio.sleep(0.02)
        raise WebSocketDisconnect()


class _AgyGia:
    """Đủ bề mặt mà nhánh antigravity-cli trong _do_turn đụng tới, và CÓ gọi công cụ."""

    def __init__(self, cwd=None, model=None, tag=None, instructions=None):
        self.session_id = None
        self.mode = "full"

    def is_available(self):
        return True

    async def query(self, prompt):
        yield {"type": "tool_call", "name": "pos_statistics"}
        yield {"type": "tool_call", "name": "pos_order"}
        yield {"type": "final", "content": "Doanh thu hôm nay 2,4 triệu."}
        yield {"type": "usage", "input_tokens": 900, "output_tokens": 40}


def _chay_mot_luot(monkeypatch, tmpdir):
    runtime = ChatRuntime()
    store = SessionStore(tmpdir / "conversations.db")
    ws = _WSGia({"message": "Doanh thu hôm nay sao anh?", "brain": "brain",
                 "session_id": PHIEN})

    monkeypatch.setattr(main, "_CHAT_RUNTIME", runtime)
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(main.cfgmod, "gate_active", lambda: False)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: {"model": {}})
    monkeypatch.setattr(main, "_chat_provider",
                        lambda _cfg: ("antigravity-cli", "oauth", "", "gemini-3.8-flash-high"))
    monkeypatch.setattr(main, "_reasoning_level", lambda _cfg: "off")
    monkeypatch.setattr(main, "build_system_prompt", lambda *a, **k: "system")
    monkeypatch.setattr(main.channel_context, "build_channel_block", lambda *a, **k: "")
    monkeypatch.setattr(main, "claude_engine",
                        lambda **_kw: SimpleNamespace(session_id=None))
    monkeypatch.setattr(main.antigravity_cli, "AntigravityCLI", _AgyGia)
    monkeypatch.setattr(main, "_apply_antigravity_hub", lambda *a, **k: None)
    monkeypatch.setattr(main, "_schedule_registry_discovery_shadow", lambda *a, **k: None)
    monkeypatch.setattr(main, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(main.usage_store, "record", lambda *a, **k: None)

    async def khong_lam_gi(*_a, **_k):
        return None

    monkeypatch.setattr(main, "_schedule_cancel_action", khong_lam_gi)
    monkeypatch.setattr(main.learn_feature, "enqueue", khong_lam_gi)

    async def kich_ban():
        await main.websocket_endpoint(ws)
        for _ in range(60):
            if runtime.get_job(PHIEN) is None:
                break
            await asyncio.sleep(0.02)

    asyncio.run(kich_ban())
    return ws, store


def main_test(monkeypatch, tmp_path):
    ws, _store = _chay_mot_luot(monkeypatch, tmp_path)
    loi = [g for g in ws.sent if g.get("type") == "error"]
    goi_tool = [g for g in ws.sent if g.get("type") == "tool_call"]
    resp = [g for g in ws.sent if g.get("type") == "response"]

    check("lượt Antigravity chạy trọn, không gói lỗi nào", not loi,
          loi[0].get("content") if loi else "")

    # 1. Engine có gọi công cụ thì khung tool_call phải được gửi ra.
    check("có gửi khung tool_call ra dashboard", len(goi_tool) >= 2,
          [g.get("type") for g in ws.sent])
    check("khung tool_call mang đúng tên công cụ",
          [g.get("tool") for g in goi_tool][:2] == ["pos_statistics", "pos_order"],
          [g.get("tool") for g in goi_tool])

    # 2. LỖI GỐC: thiếu session_id thì app.js coi khung này không thuộc phiên nào và bỏ qua.
    thieu = [g for g in goi_tool if not g.get("session_id")]
    check("MỌI khung tool_call đều mang session_id", not thieu,
          "thiếu ở %d/%d khung" % (len(thieu), len(goi_tool)))
    check("session_id đúng bằng phiên đang mở",
          all(g.get("session_id") == PHIEN for g in goi_tool),
          [g.get("session_id") for g in goi_tool])

    # 3. Canary: khung response vốn ĐÃ có session_id. Nếu một ngày nó mất luôn thì cả câu trả
    #    lời cũng biến mất chứ không riêng tiến trình - phải đỏ to chứ không im lặng.
    check("khung response vẫn mang session_id (canary)",
          bool(resp) and resp[0].get("session_id") == PHIEN)

    # 4. Cùng luật cho tool_result: nó cũng đi vào đúng nhánh định tuyến theo session_id.
    ket_qua = [g for g in ws.sent if g.get("type") == "tool_result"]
    check("mọi khung tool_result (nếu có) đều mang session_id",
          all(g.get("session_id") for g in ket_qua),
          len(ket_qua))


def test_khung_tool_mang_session_id(monkeypatch, tmp_path):
    main_test(monkeypatch, tmp_path)
    assert not _fails, _fails


if __name__ == "__main__":
    import pathlib

    class _Patch:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, value):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)

    mp = _Patch()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="javis-agy-run-"))
    try:
        main_test(mp, tmp)
    finally:
        mp.undo()
    print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
    sys.exit(1 if _fails else 0)
