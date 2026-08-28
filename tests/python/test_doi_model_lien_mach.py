# -*- coding: utf-8 -*-
"""Đổi bộ não giữa chừng thì hội thoại phải LIỀN MẠCH.

    python tests/run.py doi_model

Lỗi thật (người dùng báo 22/08/2026): đang chat, đổi sang model khác, Javis không nhớ đoạn
đang nói và trả lời một câu không liên quan.

Nguyên nhân, hai lỗi chồng nhau, đều nằm ở chỗ VÔ HIỆU MẠCH NATIVE:

  1. Ba engine giữ mạch riêng của mình (Claude Code `cli_session_id`, Codex
     `codex_thread_id`, Grok Build `grok_session_id`), nhưng chỗ đổi engine trên dashboard
     chỉ dọn ĐÚNG MỘT cái là Codex. Nên đổi Claude Code -> model khác -> quay lại Claude Code
     là nó `--resume` đúng cái mạch KHÔNG chứa mấy lượt ở giữa, rồi nói như chưa hề có chúng.

  2. Đường tắt (fast path) gọi `set_cli_session_id(sid, "")` với ý định XOÁ mạch Claude, kèm
     hẳn một comment giải thích vì sao phải xoá. Nhưng hàm đó `return` ngay khi giá trị rỗng,
     nên nó là một LỆNH RỖNG, im lặng. Mạch Claude không bao giờ được dọn ở ca đó.

BẤT BIẾN được khoá ở đây: một mạch native chỉ còn đúng khi nó chứa TOÀN BỘ hội thoại. Ngay
khi một lượt do engine khác xử lý, mạch của mọi engine còn lại phải bị vô hiệu.

Không chạm mạng, không cần engine thật: kiểm trên chính kho phiên (SQLite) cộng vài bất biến
cấu trúc của main.py.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-mach-test-"))

from sessions import SessionStore  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (f"  [{them}]" if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


def _kho():
    return SessionStore(os.path.join(tempfile.mkdtemp(), "c.db"))


def _dat_ca_ba(s, sid):
    s.set_cli_session_id(sid, "claude-mach")
    s.set_codex_thread_id(sid, "codex-thread")
    s.set_grok_session_id(sid, "grok-mach")


def _doc(s, sid):
    r = s.get_session(sid) or {}
    return (r.get("cli_session_id") or "", r.get("codex_thread_id") or "",
            r.get("grok_session_id") or "")


# ============================================================
# 1. Kho phiên: giữ đúng mạch của engine đang chạy, dọn sạch phần còn lại
# ============================================================
for nhan, giu in (("cli", 0), ("codex", 1), ("grok-cli", 2)):
    s = _kho()
    sid = s.get_or_create(None, brain="brain", engine=nhan, model="m")
    _dat_ca_ba(s, sid)
    da_don = s.clear_native_threads(sid, keep=nhan)
    sau = _doc(s, sid)
    check(f"engine {nhan}: giữ mạch của chính nó", bool(sau[giu]), sau)
    check(f"engine {nhan}: dọn mạch hai engine kia",
          sum(1 for i, v in enumerate(sau) if v and i != giu) == 0, sau)
    check(f"engine {nhan}: báo lại đúng thứ đã dọn", len(da_don) == 2, da_don)

# Engine KHÔNG giữ mạch riêng (Antigravity, mọi engine API) -> dọn sạch cả ba.
# Đây chính là ca người dùng gặp: đang Claude Code, đổi sang một model API.
for nhan in ("antigravity-cli", "openrouter", "gemini", "groq", "ollama", ""):
    s = _kho()
    sid = s.get_or_create(None, brain="brain", engine="cli", model="m")
    _dat_ca_ba(s, sid)
    s.clear_native_threads(sid, keep=nhan)
    check(f"engine {nhan or '(trống)'}: dọn sạch cả ba mạch", _doc(s, sid) == ("", "", ""))

# Gọi khi không có mạch nào -> không nổ, không báo đã dọn gì
s = _kho()
sid = s.get_or_create(None, brain="brain", engine="cli", model="m")
check("phiên mới: không có gì để dọn", s.clear_native_threads(sid, keep="cli") == [])

# ============================================================
# 2. LỖI LỆNH RỖNG: dọn mạch Claude Code phải THẬT SỰ xoá
# ============================================================
s = _kho()
sid = s.get_or_create(None, brain="brain", engine="cli", model="m")
s.set_cli_session_id(sid, "claude-mach")
s.clear_cli_session_id(sid)
check("clear_cli_session_id xoá thật", _doc(s, sid)[0] == "")

# và cái bẫy cũ vẫn phải là no-op CÓ CHỦ Ý (không được lỡ tay ghi rỗng đè lên mạch đang chạy)
s.set_cli_session_id(sid, "mach-moi")
s.set_cli_session_id(sid, "")
check("set_cli_session_id('') không đè mất mạch đang chạy", _doc(s, sid)[0] == "mach-moi")

# ============================================================
# 3. Bất biến CẤU TRÚC trong main.py: không được quay lại kiểu dọn từng engine một
# ============================================================
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
# Bỏ dòng chú thích trước khi dò LỆNH THẬT: mấy chỗ này có ghi chú lịch sử nhắc lại nguyên
# văn lệnh cũ, dò thô là bắt nhầm chính lời giải thích vì sao đã bỏ nó.
code = "\n".join(d for d in src.split("\n") if not d.lstrip().startswith("#"))

check("dashboard dọn mạch qua clear_native_threads(keep=engine_label)",
      "store.clear_native_threads(conv_sid, keep=engine_label)" in code)
check("đường tắt dọn CẢ BA mạch bằng một lệnh",
      "store.clear_native_threads(conv_sid)" in code)
check("không còn ai gọi set_cli_session_id với chuỗi rỗng để XOÁ",
      'set_cli_session_id(conv_sid, "")' not in code)

# Bên Telegram cũng vậy: MỘT chỗ dọn cho mọi engine, không rải lệnh theo từng nhánh.
#
# 0.50.1 gom vòng lặp cũ thành `_tg_ngat_mach` + bảng `_TG_ENGINE_MACH`, vì cùng danh sách
# engine đó phải đúng ở BA chỗ (đổi provider, /reset, đổi brain) và liệt tay ba lần thì có
# ngày sót: `cli` từng sót ở chỗ đổi provider, `antigravity` sót ở cả ba.
i = code.find("_TG_ENGINE_MACH = (")
check("telegram: có BẢNG engine giữ mạch dùng chung", i > 0)
if i > 0:
    vung = code[i:i + 400]
    for nhan in ('"cli"', '"codex"', '"grok-cli"', '"antigravity-cli"'):
        check(f"telegram: bảng có phủ {nhan}", nhan in vung)
check("telegram: đổi provider thì tha engine ĐANG chạy, dọn phần còn lại",
      "_tg_ngat_mach(sess, tru=engine_label)" in code)
check("telegram: /reset và đổi brain dọn SẠCH (không tha ai)",
      code.count("_tg_ngat_mach(sess)") >= 2, code.count("_tg_ngat_mach(sess)"))

# Nhánh nào của dashboard cũng phải đi qua một lệnh dọn, không được có nhánh tự dọn lẻ
check("dashboard không còn nhánh dọn lẻ chỉ mỗi Codex khi đổi engine",
      'if engine_label != "codex":' not in code)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_doi_model_lien_mach: tất cả assertion pass")
