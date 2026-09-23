"""Một lượt chat THẬT qua nhánh ChatGPT Web, cộng những cái bẫy quanh nó.

    python tests/run.py luot_chat_web

Vì sao chạy THẬT một lượt chứ không chỉ tìm chữ trong mã: bản 0.13.0 đã làm hỏng mọi lượt
chat của người dùng gói ChatGPT bằng đúng một dòng thiếu `nonlocal`, và cả CI lẫn test tìm
chữ đều cho qua (xem test_luot_chat_codex). Nhánh Web viết theo cùng khuôn nên dính cùng loại
bẫy, nên nó cũng phải được đẩy trọn một lượt qua `websocket_endpoint`.

Ba nhóm bất biến, và cả ba đều là chỗ đã suýt hỏng:

  1. **`chatgpt-web` KHÔNG bị coerce.** `_codex_safe_model` là hàm Javis gọi để ép một model
     lạ về model Codex hợp lệ, VÀ chỗ gọi nó ghi đè luôn cài đặt lẫn model ghim của phiên.
     Không chừa `chatgpt-web` ra thì chủ máy chọn nó một lần là bị đổi ngược và MẤT LUÔN lựa
     chọn - im lặng, không báo gì.
  2. **Đường Web không đụng Codex.** Chọn engine Web chính là để không tiêu quota Codex, nên
     một lượt Web mà gọi `CodexCLI` hay `write_codex_auth` là hỏng đúng mục đích của nó.
  3. **Đường nào KHÔNG chạy được trình duyệt thì phải đổi về model Codex thật**, chứ không
     gửi chuỗi "chatgpt-web" cho API Responses - nhà cung cấp không biết id đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-web-luot-"))
os.environ["JAVIS_ENABLE_WEB_CHAT"] = "true"

from fastapi import WebSocketDisconnect  # noqa: E402

import main  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402
from sessions import SessionStore  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1) Cái bẫy coerce - phần nguy hiểm nhất, và nó THUẦN nên test được ngay
# ============================================================

_cat_that = ["gpt-5.6-luna", "gpt-5.6-codex", main.MODEL_WEB]
main.cfgmod.read_settings = lambda: {"model": {"catalog": {"openai-oauth": list(_cat_that)}}}

check("la_model_web nhận đúng id", main.la_model_web("chatgpt-web"))
check("la_model_web không phân biệt hoa thường / khoảng trắng",
      main.la_model_web("  ChatGPT-Web "))
check("la_model_web KHÔNG bắt oan model Codex", not main.la_model_web("gpt-5.6-codex"))
check("la_model_web với rỗng/None thì False",
      not main.la_model_web("") and not main.la_model_web(None))

check("BẪY CHÍNH: _codex_safe_model KHÔNG đổi chatgpt-web thành model khác",
      main._codex_safe_model("chatgpt-web") == "chatgpt-web")
check("bẫy chính: chừa cả khi viết hoa", main._codex_safe_model("ChatGPT-Web") == "ChatGPT-Web")
check("model API thường vẫn bị coerce như cũ (không nới lỏng cái gì)",
      main._codex_safe_model("gpt-4o") == "gpt-5.6-luna")
check("model Codex hợp lệ vẫn giữ nguyên",
      main._codex_safe_model("gpt-5.6-codex") == "gpt-5.6-codex")

# Máy KHÔNG cài Codex CLI: catalog chỉ còn mỗi chatgpt-web. Không lọc thì cat[0] đưa một
# model chạy bằng trình duyệt cho Codex thực thi.
main.cfgmod.read_settings = lambda: {"model": {"catalog": {"openai-oauth": [main.MODEL_WEB]}}}
check("catalog chỉ còn mỗi chatgpt-web: KHÔNG lấy nó làm model Codex mặc định",
      main._codex_safe_model("gpt-4o") == "")
check("_model_codex_thay_the KHÔNG bao giờ trả về model web",
      not main.la_model_web(main._model_codex_thay_the("chatgpt-web")))
main.cfgmod.read_settings = lambda: {"model": {"catalog": {"openai-oauth": list(_cat_that)}}}
check("_model_codex_thay_the đổi web về model Codex thật",
      main._model_codex_thay_the("chatgpt-web") == "gpt-5.6-luna")
check("_model_codex_thay_the không đụng model Codex bình thường",
      main._model_codex_thay_the("gpt-5.6-codex") == "gpt-5.6-codex")


# ============================================================
# 2) Catalog và trạng thái sẵn sàng của thẻ ChatGPT
# ============================================================

async def _cat(ds_codex):
    main.openai_oauth.list_models = lambda *_a, **_k: ds_codex
    main.openai_oauth.valid_creds = lambda: {"access_token": "x"}
    return await main._fetch_provider_models("openai-oauth", {})


# Giả lập máy ĐỦ ĐỒ cho cả khối này: phép thử chạy trên CI không có trình duyệt, mà điều
# đang soi là cách Javis nối danh mục, không phải máy CI có Chromium hay không.
_kha_dung_goc = main.web_transport.kha_dung
main.web_transport.kha_dung = lambda: (True, "")

ds = asyncio.run(_cat(["gpt-5.6-luna"]))
check("catalog có nối chatgpt-web khi máy dùng được engine Web", main.MODEL_WEB in (ds or []))
check("chatgpt-web nằm CUỐI, không chen lên làm mặc định", ds and ds[-1] == main.MODEL_WEB)

# Máy không cài Codex CLI -> list_models trả None. Đây ĐÚNG là máy mà engine Web phục vụ.
ds_none = asyncio.run(_cat(None))
check("Codex không trả được gì (None) thì vẫn có chatgpt-web",
      ds_none == [main.MODEL_WEB])

main.web_transport.kha_dung = lambda: (False, "giả vờ tắt")
ds_tat = asyncio.run(_cat(["gpt-5.6-luna"]))
check("engine Web không dùng được thì catalog không có chatgpt-web",
      main.MODEL_WEB not in (ds_tat or []))
check("và danh sách Codex giữ nguyên, không bị bọc lại",
      ds_tat == ["gpt-5.6-luna"])
main.web_transport.kha_dung = lambda: (True, "")

main.find_codex_cli = lambda *a, **k: ""
main.web_transport.kha_dung = lambda: (True, "")
check("máy không có Codex CLI nhưng dùng được engine Web -> thẻ ChatGPT vẫn SẴN SÀNG",
      main._vi_sao_khong_co_model("openai-oauth", {}) == "")
# Trả lại hàm THẬT trước khi soi nhánh ép tắt: đang soi chính `kha_dung`, giả lập nó ở đây
# là phép thử tự trả lời câu hỏi của mình.
main.web_transport.kha_dung = _kha_dung_goc
os.environ["JAVIS_ENABLE_WEB_CHAT"] = "0"
main.web_transport.dat_lai_do()
check("ép tắt engine Web thì vẫn báo thiếu Codex CLI như cũ",
      "Codex CLI" in main._vi_sao_khong_co_model("openai-oauth", {}))
os.environ.pop("JAVIS_ENABLE_WEB_CHAT", None)
main.web_transport.dat_lai_do()


# ============================================================
# 2b) Ô chọn model và engine phải trả lời GIỐNG NHAU
# ============================================================
#
# Bẫy của 0.64.0: `_web_bat` đọc biến môi trường còn engine lại tự dò thư viện. Máy có đặt
# biến mà THIẾU playwright thì model nằm trong ô chọn, người dùng chọn nó, rồi lượt chat
# hỏng. Hai câu trả lời cho cùng một câu hỏi thì sớm muộn cũng lệch; giờ chỉ còn một nguồn.

_kq_gia = {"v": (False, "giả vờ thiếu đồ")}
_kha_dung_that = main.web_transport.kha_dung
main.web_transport.kha_dung = lambda: _kq_gia["v"]
try:
    check("máy THIẾU đồ -> model KHÔNG vào ô chọn", not main._web_bat())
    _ds_thieu = asyncio.run(_cat(["gpt-5.6-luna"]))
    check("máy thiếu đồ -> catalog cũng không có chatgpt-web",
          main.MODEL_WEB not in (_ds_thieu or []))
    _kq_gia["v"] = (True, "")
    check("máy ĐỦ đồ -> model vào ô chọn, không cần khai báo biến nào", main._web_bat())
    _ds_du = asyncio.run(_cat(["gpt-5.6-luna"]))
    check("máy đủ đồ -> catalog có chatgpt-web", main.MODEL_WEB in (_ds_du or []))
finally:
    main.web_transport.kha_dung = _kha_dung_that


# ============================================================
# 3) Kho phiên: luồng web có cột RIÊNG
# ============================================================

with tempfile.TemporaryDirectory() as _td:
    from pathlib import Path
    _st = SessionStore(Path(_td) / "c.db")
    _sid = _st.create_session(brain="b")
    _st.set_web_thread_id(_sid, "conv-abc")
    check("lưu được luồng web", (_st.get_session(_sid) or {}).get("web_thread_id") == "conv-abc")
    _st.set_codex_thread_id(_sid, "thread-codex")
    check("luồng web và mạch Codex là HAI cột khác nhau",
          (_st.get_session(_sid) or {}).get("web_thread_id") == "conv-abc"
          and (_st.get_session(_sid) or {}).get("codex_thread_id") == "thread-codex")
    _da_don = _st.clear_native_threads(_sid, keep="chatgpt-web")
    check("engine Web chen lượt vào: mạch Codex bị dọn", "codex" in _da_don)
    check("engine Web chen lượt vào: luồng WEB được giữ",
          (_st.get_session(_sid) or {}).get("web_thread_id") == "conv-abc")
    _st.clear_native_threads(_sid, keep="codex")
    check("engine khác chen vào: luồng web thành stale",
          not (_st.get_session(_sid) or {}).get("web_thread_id"))


# ============================================================
# 4) Một lượt chat THẬT qua dashboard
# ============================================================

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


_da_goi_codex = []


class _CodexCam:
    """Codex GIẢ chỉ để bắt quả tang. Lượt Web chạm vào nó là hỏng đúng mục đích của nó."""

    def __init__(self, *a, **k):
        _da_goi_codex.append(("CodexCLI", k))
        self.session_id = None
        self.profile = None
        self.extra_config = []

    def is_available(self):
        return True

    async def query(self, prompt):
        yield {"type": "final", "content": "CODEX ĐÃ CHẠY - ĐÁNG LẼ KHÔNG"}


class _WebEngineGia:
    def __init__(self, **kw):
        self.kw = kw
        self.session_id = kw.get("session_id") or ""

    def is_available(self):
        return True

    async def query(self, prompt):
        _da_goi_codex.append(("prompt", prompt))
        yield {"type": "session", "session_id": "conv-web-1"}
        yield {"type": "tool_call", "name": "javis_read_file"}
        yield {"type": "text", "content": "Vâng anh, Javis chạy bằng bản web."}
        yield {"type": "final", "content": "Vâng anh, Javis chạy bằng bản web.",
               "session_id": "conv-web-1"}


def _chay_mot_luot(monkeypatch, tmpdir):
    runtime = ChatRuntime()
    store = SessionStore(tmpdir / "conversations.db")
    ws = _WSGia({"message": "Chào Javis", "brain": "brain", "session_id": "phien-web"})

    monkeypatch.setattr(main, "_CHAT_RUNTIME", runtime)
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(main.cfgmod, "gate_active", lambda: False)
    monkeypatch.setattr(main.cfgmod, "read_settings", lambda: {"model": {}})
    monkeypatch.setattr(main, "_chat_provider",
                        lambda _cfg: ("openai-oauth", "oauth", "", main.MODEL_WEB))
    monkeypatch.setattr(main, "_reasoning_level", lambda _cfg: "off")
    monkeypatch.setattr(main, "build_system_prompt", lambda *a, **k: "system")
    monkeypatch.setattr(main.channel_context, "build_channel_block", lambda *a, **k: "")
    monkeypatch.setattr(main, "claude_engine",
                        lambda **_kw: SimpleNamespace(session_id=None))
    # Codex bị theo dõi, KHÔNG bị chặn: phải thấy được nếu nhánh Web lỡ rơi xuống Codex.
    monkeypatch.setattr(main, "CodexCLI", _CodexCam)
    monkeypatch.setattr(main.openai_oauth, "write_codex_auth",
                        lambda *a, **k: _da_goi_codex.append(("write_codex_auth", None)))

    async def _dung(*a, **k):
        return _WebEngineGia(**k)

    monkeypatch.setattr(main, "_dung_web_engine", _dung)
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
            if runtime.get_job("phien-web") is None:
                break
            await asyncio.sleep(0.02)

    asyncio.run(kich_ban())
    return ws, store


def main_test(monkeypatch, tmp_path):
    _da_goi_codex.clear()
    ws, store = _chay_mot_luot(monkeypatch, tmp_path)
    loai = [g.get("type") for g in ws.sent]
    loi = [g for g in ws.sent if g.get("type") == "error"]
    resp = [g for g in ws.sent if g.get("type") == "response"]

    check("lượt Web chạy trọn, không gói lỗi nào", not loi)
    if loi:
        print("     -> " + str(loi[0].get("content"))[:300])

    check("có đúng một gói 'response'", len(resp) == 1)
    if resp:
        check("gói response mang đúng câu trả lời",
              resp[0].get("content") == "Vâng anh, Javis chạy bằng bản web.")
        check("gói response khai engine chatgpt-web, KHÔNG phải codex",
              resp[0].get("engine") == "chatgpt-web")
        check("model khai đúng là chatgpt-web", resp[0].get("model") == main.MODEL_WEB)
    check("có stream chữ ra trước khi chốt", "stream" in loai)
    check("tool_call có bay lên giao diện", "tool_call" in loai)

    # BẤT BIẾN LỚN NHẤT: lượt Web không đụng Codex một mili-giây nào.
    _codex = [x for x in _da_goi_codex if x[0] in ("CodexCLI", "write_codex_auth")]
    check("lượt Web KHÔNG dựng CodexCLI và KHÔNG ghi auth Codex", not _codex)
    if _codex:
        print("     -> đã đụng: " + str([x[0] for x in _codex]))

    tin = store.get_messages("phien-web")
    check("lượt được lưu đủ cả hỏi lẫn đáp",
          [m["role"] for m in tin] == ["user", "assistant"])
    check("luồng web được ghi lại để lượt sau gõ tiếp đúng cuộc đó",
          (store.get_session("phien-web") or {}).get("web_thread_id") == "conv-web-1")

    # Lượt ĐẦU chưa có luồng nên phải mồi transcript; ở đây transcript rỗng nên chỉ cần
    # chắc chắn câu hỏi của người dùng có mặt.
    _prompt = next((x[1] for x in _da_goi_codex if x[0] == "prompt"), "")
    check("câu hỏi tới được engine Web", "Chào Javis" in _prompt)


# ============================================================
# 5) Ranh giới trong mã nguồn
# ============================================================

def _soi_ma_nguon():
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    check("nhánh Web nằm TRƯỚC nhánh Codex trong chuỗi dispatch dashboard",
          src.index('elif prov == "openai-oauth" and la_model_web(api_model):')
          < src.index('elif prov == "openai-oauth":\n                # ===== ChatGPT subscription qua CODEX CLI'))
    check("có nhánh Web cho Telegram",
          'if prov == "openai-oauth" and la_model_web(api_model):' in src)
    check("đường tắt Fast Path chừa model Web ra (dashboard + Telegram)",
          src.count("not la_model_web(api_model)") >= 2)
    check("stream không tool dùng model thay thế, không gửi id web cho Responses",
          "_model_codex_thay_the(model), messages, reasoning)" in src)
    check("nhánh Web mở gốc file sang thư mục làm việc của phiên Coding",
          "workspace_root=list(_web_ctx.workspace_roots)" in src)
    check("chỉ cấp coding_ctx khi phiên THẬT SỰ là phiên coding",
          "coding_ctx=_web_ctx if _web_ctx.active else None" in src)
    check("có endpoint trạng thái cho trang Models", '@app.get("/web-chat/status")' in src)
    # 0.64.12 bỏ /web-chat/login (màn đăng nhập chụp màn hình): nó chỉ vẽ ra khi máy đã cài
    # đủ đồ, tức vắng mặt đúng lúc cần nhất. 0.64.13 bỏ nốt /web-chat/reset cùng nút "Đóng
    # trình duyệt" cho thẻ gọn; việc của nó (đóng trình duyệt, xoá sổ nghỉ) dời vào chính
    # đường dán cookie, xem test_trang_code_dien_thoai.js.
    for ep in ("/web-chat/cookie", "/web-chat/check"):
        check(f"có endpoint {ep}", f'"{ep}"' in src)
    check("endpoint /web-chat/reset đã bỏ", '"/web-chat/reset"' not in src)
    # Không bịa quota: trang chat không nói ra con số nào, nên mọi phần trăm vẽ ra đều là
    # bịa. Soi CHÍNH câu trả lời của endpoint chứ không tìm chữ trong mã nguồn.
    # Từ 0.64.8 nhóm /web-chat đòi PHIÊN ĐĂNG NHẬP THẬT (không nhận API token), vì đường đó
    # mở trình duyệt trên máy chủ và nhận cookie phiên ChatGPT của chủ máy. Nên gọi thẳng hàm
    # thì phải đưa một request có phiên - xem test_web_mot_thread cho phần khoá cái cổng đó.
    _vs_that = main.cfgmod.valid_session
    main.cfgmod.valid_session = lambda *_a, **_k: True
    try:
        d = main.web_chat_status(SimpleNamespace(cookies={"javis_session": "x"}))
    finally:
        main.cfgmod.valid_session = _vs_that
    check("trạng thái nói THẲNG là không quan sát được quota",
          d.get("quota_visibility") == "unknown")
    check("không có khoá phần trăm quota nào trong câu trả lời",
          not [k for k in d if "percent" in k.lower() or "phan_tram" in k.lower()])
    check("trạng thái có nhắc Memory / custom instructions làm nhiễu câu trả lời",
          "Memory" in (d.get("canh_bao") or ""))
    check("trạng thái khai đúng model id", d.get("model_id") == main.MODEL_WEB)


def test_luot_chat_web_khong_no(monkeypatch, tmp_path):
    main_test(monkeypatch, tmp_path)
    _soi_ma_nguon()
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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="javis-web-luot-run-"))
    try:
        main_test(mp, tmp)
    finally:
        mp.undo()
    _soi_ma_nguon()

    print()
    if _fails:
        print(f"THẤT BẠI {len(_fails)}: {_fails}")
        sys.exit(1)
    print("OK - test_luot_chat_web: tất cả pass")
