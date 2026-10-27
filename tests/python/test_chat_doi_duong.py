"""Chat tự chuyển đường khi hết lượt (0.354.0, docs/dev/2026-10-model-routing-spec.md 6.4).

    python tests/run.py chat_doi_duong

Chủ repo chốt: lượt chat hỏng vì hết lượt TRƯỚC khi có chữ hoặc công cụ nào thì chạy lại ngay bằng
đường kế tiếp (tài khoản kế của cùng thẻ, rồi thẻ kế trong Thứ tự dùng), kèm một dòng "Đang dùng ChatGPT
vì Claude hết lượt". Hỏng giữa chừng thì dừng, có nút "Chạy lại". Đã gọi công cụ thì không bao giờ tự
chạy lại (tránh gửi tin, đăng bài hai lần).

File này đẩy lượt THẬT qua `main.websocket_endpoint` với một Codex CLI giả có hai tài khoản:
  1. tài khoản 1 hết lượt ngay từ đầu -> lượt chạy lại bằng tài khoản 2, người dùng không thấy lỗi;
  2. tài khoản 1 viết dở rồi hết lượt -> giữ câu trả lời dở, có thẻ "Chạy lại" (không tự chạy);
  3. tài khoản 1 gọi công cụ rồi hết lượt -> không chạy lại bằng đường khác;
và kiểm hàm chọn đường kế tiếp, lượt Telegram, cùng dây nối trong mã nguồn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-doiduong-"))

from fastapi import WebSocketDisconnect  # noqa: E402

import main  # noqa: E402
import model_routing  # noqa: E402
import plan_accounts  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402
from sessions import SessionStore  # noqa: E402

_fails = []
LIMIT = "You've hit your usage limit. Upgrade to Pro or try again later."


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{them}]" if not cond and them else ""))
    if not cond:
        _fails.append(name)


class _WSGia:
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


def _codex_gia(kich_ban):
    """CodexCLI giả: tài khoản 1 (không có codex_home) chạy `kich_ban`, tài khoản 2 trả lời trọn."""
    chay = []

    class _CodexGia:
        def __init__(self, cwd=None, model=None, tag=None, instructions=None):
            self.session_id = None
            self.profile = None
            self.extra_config = []
            self.codex_home = None

        def is_available(self):
            return True

        async def query(self, prompt):
            acc = "acc2" if self.codex_home else "main"
            chay.append(acc)
            if acc == "main":
                for ev in kich_ban:
                    yield ev
                return
            yield {"type": "text", "content": "Tài khoản 2 trả lời đây."}
            yield {"type": "final", "content": "Tài khoản 2 trả lời đây.", "tokens_in": 10, "tokens_out": 5}

    return _CodexGia, chay


def _mcfg():
    return {"order": ["openai-oauth"], "accounts": {"openai-oauth": [
        {"id": "main", "label": "", "enabled": True}, {"id": "acc2", "label": "", "enabled": True}]}}


def _dang_nhap_acc2():
    folder = plan_accounts.home("openai-oauth", "acc2")
    (folder / "auth.json").write_text(json.dumps({"tokens": {"access_token": "x", "refresh_token": "y"}}),
                                      encoding="utf-8")


def _xoa_nghi():
    model_routing.clear_rest("openai-oauth", "main")
    model_routing.clear_rest("openai-oauth", "acc2")
    main._PIN_LIMITED.pop("openai-oauth", None)


def _chay_mot_luot(mp, tmpdir, kich_ban, sid):
    _xoa_nghi()
    _dang_nhap_acc2()
    runtime = ChatRuntime()
    store = SessionStore(tmpdir / f"{sid}.db")
    ws = _WSGia({"message": "Tóm tắt giúp anh doanh thu tuần này", "brain": "brain", "session_id": sid})
    codex, chay = _codex_gia(kich_ban)
    mcfg = _mcfg()
    mp.setattr(main, "_CHAT_RUNTIME", runtime)
    mp.setattr(main, "get_store", lambda: store)
    mp.setattr(main.cfgmod, "gate_active", lambda: False)
    mp.setattr(main.cfgmod, "read_settings", lambda: {"model": mcfg})
    mp.setattr(main, "_chat_provider", lambda _cfg: ("openai-oauth", "oauth", "", "gpt-5.6-luna"))
    mp.setattr(main, "_routing_connected_ids", lambda _s: ["openai-oauth"])
    mp.setattr(main, "_reasoning_level", lambda _cfg: "off")
    mp.setattr(main, "_codex_safe_model", lambda m: m or "gpt-5.6-luna")
    mp.setattr(main, "build_system_prompt", lambda *a, **k: "system")
    mp.setattr(main.channel_context, "build_channel_block", lambda *a, **k: "")
    mp.setattr(main, "claude_engine", lambda **_kw: SimpleNamespace(session_id=None))
    mp.setattr(main, "CodexCLI", codex)
    mp.setattr(main, "_apply_codex_hub", lambda *a, **k: None)
    mp.setattr(main.openai_oauth, "write_codex_auth", lambda *a, **k: None)
    mp.setattr(main, "_schedule_registry_discovery_shadow", lambda *a, **k: None)
    mp.setattr(main, "log_conversation", lambda *a, **k: None)
    mp.setattr(main.usage_store, "record", lambda *a, **k: None)

    async def khong_lam_gi(*_a, **_k):
        return None

    mp.setattr(main, "_schedule_cancel_action", khong_lam_gi)
    mp.setattr(main.learn_feature, "enqueue", khong_lam_gi)

    async def chay_luot():
        await main.websocket_endpoint(ws)
        for _ in range(60):
            if runtime.get_job(sid) is None:
                break
            await asyncio.sleep(0.02)

    asyncio.run(chay_luot())
    main.limit_resume.REGISTRY.cancel(sid)
    return ws, store, chay


def _cua(ws, loai):
    return [g for g in ws.sent if g.get("type") == loai]


def main_test(mp, tmp):
    # ---- 1. hết lượt trước chữ nào: chạy lại ngay bằng tài khoản 2 ----
    ws, store, chay = _chay_mot_luot(mp, tmp, [{"type": "error", "content": LIMIT}], "phien-a")
    check("tài khoản 1 chạy trước, rồi tài khoản 2 chạy lại đúng lượt đó", chay == ["main", "acc2"], str(chay))
    doi = _cua(ws, "reroute")
    check("có MỘT dòng báo đổi đường", len(doi) == 1, str(doi))
    if doi:
        c = doi[0].get("content") or ""
        check("dòng báo nói rõ đang dùng gì và vì sao", "ChatGPT" in c and "2" in c and "1" in c, c)
        check("dòng báo không có gạch ngang dài", "—" not in c and "–" not in c)
    check("người dùng không thấy bong bóng lỗi hết lượt", not _cua(ws, "error"), str(_cua(ws, "error")))
    check("không có thẻ hẹn chạy lại", not _cua(ws, "resume"))
    resp = [g for g in _cua(ws, "response") if (g.get("content") or "").strip()]
    check("câu trả lời là của tài khoản 2", len(resp) == 1 and resp[0]["content"] == "Tài khoản 2 trả lời đây.")
    check("không có khung response rỗng nào lọt ra", all((g.get("content") or "").strip() for g in _cua(ws, "response")))
    tin = store.get_messages("phien-a")
    check("kho phiên chỉ có câu hỏi và câu trả lời thật (không lưu câu báo hết lượt)",
          [(m["role"], m["content"]) for m in tin] == [("user", "Tóm tắt giúp anh doanh thu tuần này"),
                                                      ("assistant", "Tài khoản 2 trả lời đây.")],
          str([(m["role"], m["content"][:30]) for m in tin]))
    check("tài khoản 1 đang nghỉ", model_routing.resting_until("openai-oauth", "main") > 0)
    check("thẻ ChatGPT không bị tính là hết lượt (còn tài khoản 2)", not main._pin_limited_until("openai-oauth"))
    i_doi = next(i for i, g in enumerate(ws.sent) if g.get("type") == "reroute") if doi else -1
    i_rep = next((i for i, g in enumerate(ws.sent) if g.get("type") == "response"), -1)
    check("dòng đổi đường tới trước câu trả lời", 0 <= i_doi < i_rep)

    # ---- 2. viết dở rồi hết lượt: giữ câu dở, thẻ Chạy lại, không tự chạy ----
    ws, store, chay = _chay_mot_luot(mp, tmp, [{"type": "text", "content": "Doanh thu tuần này đạt "},
                                               {"type": "error", "content": LIMIT}], "phien-b")
    check("viết dở: không chạy lại bằng đường khác", chay == ["main"], str(chay))
    check("viết dở: không có dòng đổi đường", not _cua(ws, "reroute"))
    check("viết dở: câu báo hết lượt vẫn hiện", bool(_cua(ws, "error")))
    res = _cua(ws, "resume")
    check("viết dở: có thẻ Chạy lại (partial, không tự chạy)",
          len(res) == 1 and res[0].get("reason") == "partial" and res[0].get("auto") is False, str(res))
    tin = store.get_messages("phien-b")
    check("viết dở: câu trả lời dở được lưu", bool(tin) and tin[-1]["role"] == "assistant"
          and tin[-1]["content"].startswith("Doanh thu tuần này"))

    # ---- 3. gọi công cụ rồi hết lượt: không bao giờ chạy lại bằng đường khác ----
    ws, store, chay = _chay_mot_luot(mp, tmp, [{"type": "tool_call", "name": "zalo_send_message", "input": {}},
                                               {"type": "error", "content": LIMIT}], "phien-c")
    check("đã gọi công cụ: không chạy lại", chay == ["main"], str(chay))
    check("đã gọi công cụ: không có dòng đổi đường", not _cua(ws, "reroute"))
    check("đã gọi công cụ: câu báo hết lượt hiện ra", bool(_cua(ws, "error")))
    _xoa_nghi()

    # ---- 4. hàm chọn đường kế tiếp ----
    m = {"order": ["openai-oauth", "groq", "anthropic-cli"], "groq_api_key": "gsk_test",
         "profiles": {"groq": {"model": "llama-4", "reasoning": "off"}}}
    mp.setattr(main, "_routing_connected_ids", lambda _s: ["openai-oauth", "groq", "anthropic-cli"])
    main._PIN_LIMITED["openai-oauth"] = 9e12
    nxt = main._chat_next_route(m, "openai-oauth")
    check("hết thẻ ChatGPT thì sang thẻ kế trong Thứ tự dùng (Groq)",
          bool(nxt) and nxt["route"][0] == "groq" and nxt["route"][3] == "llama-4", str(nxt))
    check("dòng báo: Đang dùng Groq vì ChatGPT hết lượt",
          bool(nxt) and "Groq" in nxt["status"] and "ChatGPT" in nxt["status"], str(nxt.get("status")))
    nxt2 = main._chat_next_route(m, "groq", "gsk_test", nxt["tried"])
    check("đường đã thử trong lượt không được chọn lại", bool(nxt2) and nxt2["route"][0] == "anthropic-cli",
          str(nxt2.get("route")))
    nxt3 = main._chat_next_route(m, "anthropic-cli", "", nxt2["tried"])
    check("hết đường thì trả rỗng (lượt dừng và báo như cũ)", nxt3 == {}, str(nxt3))
    main._PIN_LIMITED.pop("openai-oauth", None)

    # ---- 5. Telegram: nhận ra câu hết lượt và cho tài khoản đó nghỉ ----
    model_routing.clear_rest("groq", "-")
    m2 = {"groq_api_key": "gsk_test"}
    check("Telegram: câu 429 của nhà API là hết lượt",
          main._tg_quota_out("⚠ Error 429: rate limit reached", "groq", "api", "gsk_test", m2))
    check("Telegram: lỗi thường không phải hết lượt",
          not main._tg_quota_out("⚠ Engine không trả về nội dung nào.", "groq", "api", "gsk_test", m2))

    # ---- 6. dây nối trong mã nguồn ----
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    rt = src[src.index("        async def run_turn("):src.index("        async def run_workflow_turn(")]
    check("run_turn cho phép tối đa 3 lần đổi đường", "_hops_left=3," in rt and "_hops_left=3 - _hop" in rt)
    check("run_turn gửi khung reroute trước khi chạy lại", rt.index('"type": "reroute"') < rt.index("_route=_nxt[\"route\"]"))
    dt = src[src.index("        async def _do_turn("):src.index("        async def run_turn(")]
    check("_do_turn chỉ đổi đường khi chưa có chữ hay công cụ nào", "ws.untouched()" in dt and "_hops_left > 0" in dt)
    check("quyết định đổi đường nằm TRƯỚC chỗ lưu câu báo và hẹn chạy lại",
          dt.index("_chat_next_route(") < dt.index("_persist_limit_notice(store, conv_sid"))
    check("lượt không đổi đường thì nhả các khung đã giữ", "await ws.flush()" in dt)
    tg = src[src.index("async def _tg_answer(text"):src.index("async def _tg_answer_engine(")]
    check("Telegram: bot chuyên trách không đổi đường, đã gọi công cụ cũng không",
          "not bot and not _hop_acted[0]" in tg)


def test_chat_doi_duong(monkeypatch, tmp_path):
    main_test(monkeypatch, tmp_path)
    assert not _fails, _fails


if __name__ == "__main__":
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
    tmp = Path(tempfile.mkdtemp(prefix="javis-doiduong-run-"))
    try:
        main_test(mp, tmp)
    finally:
        mp.undo()
    print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
    sys.exit(1 if _fails else 0)
