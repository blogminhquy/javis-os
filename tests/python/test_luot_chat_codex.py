"""Một lượt chat THẬT qua nhánh Codex (gói ChatGPT) phải chạy trọn, không nổ giữa chừng.

    python tests/run.py luot_chat_codex

Vì sao cần test HÀNH VI chứ không chỉ test tĩnh. Bản 0.13.0 làm mọi lượt chat của người dùng
gói ChatGPT hỏng bằng một dòng duy nhất: hàm con `_consume_codex` cộng dồn `_ctx_in` mà thiếu
`nonlocal`, nên tới lúc Codex trả lời xong thì Python ném

    UnboundLocalError: cannot access local variable '_ctx_in'

Người dùng nhìn thấy câu trả lời hiện dần ra rồi biến thành "Lỗi xử lý", và lượt đó không
được lưu vào lịch sử. Cả CI lẫn test kiểu tìm chữ đều cho qua: cú pháp đúng, và số lần
`_ctx_in +=` vẫn đủ ba như test cũ đếm. Chỉ có CHẠY THẬT nhánh đó mới lộ.

File này dựng một WebSocket giả và một Codex CLI giả, rồi đẩy trọn một lượt qua
`main.websocket_endpoint`, đúng đường mà dashboard đi. Nó soi ba thứ mà lỗi kia phá:
  1. Không có gói `error` nào.
  2. Có gói `response` kèm số token vào (`ctx_in`) - tức bộ đếm đã cộng được.
  3. Câu trả lời được LƯU vào kho phiên (`_persist_turn` nằm sau chỗ nổ, nên lỗi kia làm
     lượt biến mất khỏi lịch sử).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-codex-"))

from fastapi import WebSocketDisconnect  # noqa: E402

import main  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402
from sessions import SessionStore  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


class _WSGia:
    """Gửi đúng MỘT tin, ở lại nghe cho tới khi lượt chốt xong, rồi mới ngắt.

    Phải ở lại: các gói của một lượt đi qua _CHAT_RUNTIME tới những client ĐANG đăng ký, mà
    ngắt sớm là máy chủ gỡ đăng ký ngay - lượt vẫn chạy nốt và vẫn lưu, nhưng không gói nào
    rơi vào đây để mà soi.
    """
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
        for _ in range(400):        # tối đa ~8 giây, đủ rộng cho máy CI chậm
            if any(g.get("type") == "turn_done" for g in self.sent):
                break
            await asyncio.sleep(0.02)
        raise WebSocketDisconnect()


class _CodexGia:
    """Đủ bề mặt mà nhánh Codex trong _do_turn đụng tới."""

    def __init__(self, cwd=None, model=None, tag=None, instructions=None):
        self.session_id = None
        self.profile = None
        self.extra_config = []

    def is_available(self):
        return True

    async def query(self, prompt):
        yield {"type": "text", "content": "Vâng anh, Javis đây."}
        # Gói 'final' CÓ tokens_in chính là gói kích hoạt dòng `_ctx_in += ...`.
        yield {"type": "final", "content": "Vâng anh, Javis đây.",
               "session_id": "thread-codex-1", "tokens_in": 1234, "tokens_out": 56}


def _chay_mot_luot(monkeypatch, tmpdir):
    runtime = ChatRuntime()
    store = SessionStore(tmpdir / "conversations.db")
    ws = _WSGia({"message": "Chào buổi chiều javis", "brain": "brain",
                 "session_id": "phien-codex"})

    monkeypatch.setattr(main, "_CHAT_RUNTIME", runtime)
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(main.cfgmod, "gate_active", lambda: False)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: {"model": {}})
    # Đúng cấu hình người dùng đang gặp lỗi: gói ChatGPT, chạy qua Codex.
    monkeypatch.setattr(main, "_chat_provider",
                        lambda _cfg: ("openai-oauth", "oauth", "", "gpt-5.6-luna"))
    monkeypatch.setattr(main, "_reasoning_level", lambda _cfg: "off")
    monkeypatch.setattr(main, "_codex_safe_model", lambda m: m or "gpt-5.6-luna")
    monkeypatch.setattr(main, "build_system_prompt", lambda *a, **k: "system")
    monkeypatch.setattr(main.channel_context, "build_channel_block", lambda *a, **k: "")
    monkeypatch.setattr(main, "claude_engine",
                        lambda **_kw: SimpleNamespace(session_id=None))
    monkeypatch.setattr(main, "CodexCLI", _CodexGia)
    monkeypatch.setattr(main, "_apply_codex_hub", lambda *a, **k: None)
    monkeypatch.setattr(main.openai_oauth, "write_codex_auth", lambda *a, **k: None)
    monkeypatch.setattr(main, "_schedule_registry_discovery_shadow", lambda *a, **k: None)
    monkeypatch.setattr(main, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(main.usage_store, "record", lambda *a, **k: None)

    async def khong_lam_gi(*_a, **_k):
        return None

    monkeypatch.setattr(main, "_schedule_cancel_action", khong_lam_gi)
    monkeypatch.setattr(main.learn_feature, "enqueue", khong_lam_gi)

    async def kich_ban():
        await main.websocket_endpoint(ws)
        for _ in range(60):          # job sống tiếp sau khi socket đóng
            if runtime.get_job("phien-codex") is None:
                break
            await asyncio.sleep(0.02)

    asyncio.run(kich_ban())
    return ws, store


def main_test(monkeypatch, tmp_path):
    ws, store = _chay_mot_luot(monkeypatch, tmp_path)
    loai = [g.get("type") for g in ws.sent]
    loi = [g for g in ws.sent if g.get("type") == "error"]
    resp = [g for g in ws.sent if g.get("type") == "response"]

    # 1. Không được có gói lỗi nào. Trước bản vá, đây là chỗ "Lỗi xử lý: UnboundLocalError".
    check("lượt Codex chạy trọn, không gói lỗi nào",
          not loi)
    if loi:
        print("     -> " + str(loi[0].get("content"))[:200])

    # 2. Có câu trả lời, kèm số token vào - tức bộ đếm đã cộng được thật.
    check("có gói 'response' trả về", len(resp) == 1)
    if resp:
        check("gói response mang đúng câu trả lời",
              resp[0].get("content") == "Vâng anh, Javis đây.")
        check("gói response khai đúng engine codex", resp[0].get("engine") == "codex")
        # 1234 là tokens_in của gói 'final' giả. Con số này chỉ tới được đây nếu dòng
        # `_ctx_in += ...` chạy được, tức đúng dòng từng nổ UnboundLocalError.
        check("bộ đếm token vào cộng được (ctx_in = 1234)",
              resp[0].get("ctx_in") == 1234)
        check("có ghi lượt này đi đường nào", bool(resp[0].get("ctx_path")))

    # 3. Câu trả lời phải được LƯU. _persist_turn nằm SAU chỗ nổ, nên lỗi cũ làm cả lượt
    #    biến mất khỏi lịch sử dù chữ đã hiện trên màn hình.
    tin = store.get_messages("phien-codex")
    check("lượt được lưu đủ cả hỏi lẫn đáp",
          [m["role"] for m in tin] == ["user", "assistant"])
    check("nội dung lưu đúng là câu trả lời",
          bool(tin) and tin[-1]["content"] == "Vâng anh, Javis đây.")
    check("thread Codex được ghi lại để lượt sau resume",
          (store.get_session("phien-codex") or {}).get("codex_thread_id") == "thread-codex-1")
    check("có stream chữ ra trước khi chốt", "stream" in loai)


def test_luot_chat_codex_khong_no(monkeypatch, tmp_path):
    main_test(monkeypatch, tmp_path)
    assert not _fails, _fails


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script. Không có pytest thì tự dựng monkeypatch/tmp_path tối
    # thiểu để test vẫn chạy thật, thay vì thoát 0 mà chưa kiểm gì.
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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="javis-codex-run-"))
    try:
        main_test(mp, tmp)
    finally:
        mp.undo()
    print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
    sys.exit(1 if _fails else 0)
