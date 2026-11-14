"""Model ghim theo TỪNG phiên chat: phiên nhớ model cuối user đổi trong phiên đó.

    python tests/run.py model_theo_phien     (KHÔNG mạng)

Yêu cầu chủ repo (16/08, hai vòng): trước đây model là GLOBAL tuyệt đối - đổi model ở
tab/phiên khác là model của phiên đang mở đổi theo, vì mọi phiên đọc chung
settings.json. Vòng 1: đổi model NGAY TRONG một phiên = ghim cho riêng phiên đó (cột
pinned_provider/pinned_model trong bảng sessions). Vòng 2 (đóng dấu từ tin đầu): MỌI
phiên dashboard được tự đóng dấu model đang chạy ngay lượt đầu tiên, nên chat cũ tuyệt
đối không bị mặc định chung kéo nữa, kể cả khi chưa từng đổi tay. Chỉ phiên chưa có
lượt chat nào (và phiên Telegram) còn theo mặc định chung.

Bẫy đã né mà test phải ghim chặt:
- KHÔNG tái dùng cột engine/model sẵn có - chúng là nhật ký lượt cuối, bị get_or_create
  ghi đè MỖI lượt. Trộn nghĩa là phiên "tự ghim" chính nó ngay sau tin đầu tiên.
- Ghim hỏng (provider bị gỡ key / không tồn tại) phải rơi về mặc định chung, không
  được chết lượt chat.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


from sessions import SessionStore  # noqa: E402
import main  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    store = SessionStore(db_path=Path(td) / "conv.db")

    # ---- 1. Ghim / gỡ ghim ở tầng lưu trữ ----
    sid = store.create_session(brain="brain-a")
    check("phiên mới KHÔNG có ghim (theo mặc định chung)",
          not (store.get_session(sid) or {}).get("pinned_provider"))

    check("ghim được model cho phiên", store.set_pinned_model(sid, "groq", "qwen3-32b"))
    row = store.get_session(sid)
    check("CANARY: ghim nằm trong row phiên",
          row["pinned_provider"] == "groq" and row["pinned_model"] == "qwen3-32b")

    # get_or_create (chạy MỖI lượt chat) không được đè mất ghim - đây chính là lý do
    # không tái dùng cột engine/model.
    store.get_or_create(sid, brain="brain-a", engine="cli", model="opus")
    row = store.get_session(sid)
    check("CANARY: get_or_create mỗi lượt KHÔNG đè mất ghim",
          row["pinned_provider"] == "groq" and row["pinned_model"] == "qwen3-32b")
    check("cột engine/model vẫn là nhật ký lượt cuối như cũ",
          row["engine"] == "cli" and row["model"] == "opus")

    check("gỡ ghim bằng provider rỗng", store.set_pinned_model(sid, "", "gi-do"))
    row = store.get_session(sid)
    check("gỡ là gỡ CẢ CẶP (model mồ côi không định tuyến được)",
          row["pinned_provider"] is None and row["pinned_model"] is None)

    # Phiên chưa tồn tại: có brain thì tự tạo hàng (user đổi model trước tin đầu tiên).
    check("phiên chưa tồn tại + không brain → False",
          not store.set_pinned_model("chua-co", "groq", "m"))
    check("phiên chưa tồn tại + có brain → tự tạo hàng rồi ghim",
          store.set_pinned_model("chua-co", "groq", "m", brain="brain-a"))
    check("hàng tự tạo mang đúng brain",
          (store.get_session("chua-co") or {}).get("brain") == "brain-a")

    ds = store.list_sessions(limit=10)
    check("list_sessions trả kèm cột ghim (UI vẽ badge được)",
          any("pinned_provider" in r for r in ds))

    # ---- 2. Định tuyến theo phiên ----
    MCFG = {"main": {"provider": "anthropic-cli", "model": "opus"},
            "groq_api_key": "gsk_test", "openrouter_key": ""}

    prov, kind, key, model = main._chat_provider_for_session(MCFG, {})
    check("không ghim → y hệt mặc định chung", prov == "anthropic-cli" and model == "opus")

    prov, kind, key, model = main._chat_provider_for_session(
        MCFG, {"pinned_provider": "groq", "pinned_model": "qwen3-32b"})
    check("CANARY: phiên ghim groq thì lượt chat đi groq, mặc định chung kệ nó",
          prov == "groq" and kind == "api" and key == "gsk_test" and model == "qwen3-32b")

    prov, _, _, model = main._chat_provider_for_session(
        MCFG, {"pinned_provider": "openrouter", "pinned_model": "x/y"})
    check("ghim provider api mà key ĐÃ BỊ GỠ → rơi về mặc định chung, không chết lượt",
          prov == "anthropic-cli" and model == "opus")

    prov, _, _, _ = main._chat_provider_for_session(
        MCFG, {"pinned_provider": "provider-ma", "pinned_model": "m"})
    check("ghim provider không tồn tại → rơi về mặc định chung", prov == "anthropic-cli")

# ---- 3. Đối chiếu dây nối trong mã nguồn ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: _do_turn định tuyến theo phiên (chỗ thật sự quyết định engine)",
      "_chat_provider_for_session(mcfg, _row0)" in src)
check("vòng nhận WS suy engine_label từ provider hiệu lực của phiên",
      "_chat_provider_for_session(mcfg, _prow)" in src)
check("có endpoint ghim model theo phiên", '/sessions/{session_id}/model' in src)
check("endpoint meta nhẹ cho model bar", '/sessions/{session_id}/meta' in src)

# Ghim hỏng phải NÓI THẬT: meta trả cờ pin_ok cho UI, còn ở lượt chat thì cơ chế
# đóng dấu bên dưới tự THAY ghim hỏng bằng model đang chạy thật.
check("meta trả cờ pin_ok (ghim còn chạy được không)", '"pin_ok"' in src)

# ĐÓNG DẤU từ tin đầu (chủ chốt 16/08, vòng 2): mỗi lượt dashboard bảo đảm ghim của
# phiên == model đang chạy thật. Phiên mới/chưa ghim được đóng dấu ngay lượt đầu nên
# đổi mặc định chung KHÔNG BAO GIỜ đổi ngược cuộc đang dở; ghim hỏng được thay bằng
# model thật; ghim lành là no-op (không ghi DB mỗi lượt).
# Issue 1336: the decision moved into `_pin_to_stamp`, which also keeps a resting pin (test_pin_survives_fallback).
check("CANARY: vòng WS đóng dấu model đang chạy cho phiên",
      "_stamp = _pin_to_stamp(mcfg, _prow, prov, api_model)" in src
      and "store.set_pinned_model(conv_sid, *_stamp)" in src)
check("đóng dấu chỉ ghi khi LỆCH (ghim lành không bị ghi lại mỗi lượt)",
      main._pin_to_stamp({"main": {"provider": "groq", "model": "m"}, "groq_api_key": "k"},
                         {"pinned_provider": "groq", "pinned_model": "m"}, "groq", "m") is None)

mp = (ROOT / "dashboard" / "model-picker.js").read_text(encoding="utf-8")
check("model bar: đổi model trong phiên là ghim cho phiên", "pinToSession" in mp)
check("model bar: vẽ lại khi đổi phiên", "javis:sessions-changed" in mp)
check("model bar: chat trống chọn model xong mint id là ghim theo", "claimPending" in mp)
check("model bar: ghim hỏng hiện đúng trạng thái, không nói dối",
      "pin_ok === false" in mp and "ghim hỏng" in mp)
check("model bar: gửi tin là biết phiên vừa được đóng dấu (noteStamped)",
      "noteStamped" in mp)

app_js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
check("app.js gọi noteStamped lúc gửi tin", "noteStamped(sid)" in app_js)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_model_theo_phien: tat ca pass")
