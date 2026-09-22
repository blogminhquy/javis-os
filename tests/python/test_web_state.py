"""Sổ trạng thái engine Web: phân loại lỗi, cooldown, và phanh chống thử lại vô hạn.

    python tests/run.py web_state

Hai phép thử nặng nhất ở đây:
  - **Trong cooldown thì phải từ chối TRƯỚC khi mở trình duyệt.** Mở Chromium mất vài giây và
    để lại tiến trình; mở ra chỉ để nhận lại đúng câu "hết lượt" là phí hai lần.
  - **Không bịa mốc reset.** Nhà cung cấp không nói thì phải đánh dấu là ƯỚC, để giao diện
    không hiện một con giờ nghe như thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-webstate-")

import web_state as ws  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


T0 = 1_700_000_000.0


def moi():
    ws.dat_lai()


# ---- 1. Phân loại lỗi từ chữ nhà cung cấp trả về ----

check("nhận ra hết lượt",
      ws.phan_loai("You've reached your limit for GPT-5.") == ws.USAGE_LIMITED)
check("nhận ra hết lượt (biến thể)",
      ws.phan_loai("Message limit reached") == ws.USAGE_LIMITED)
check("nhận ra Cloudflare",
      ws.phan_loai("Just a moment... Checking your browser") == ws.CHALLENGE_REQUIRED)
check("nhận ra captcha",
      ws.phan_loai("Please complete the captcha") == ws.CHALLENGE_REQUIRED)
check("nhận ra mất đăng nhập",
      ws.phan_loai("Your session expired, please log in") == ws.AUTH_REQUIRED)
check("nhận ra transport gãy",
      ws.phan_loai("composer not found") == ws.TRANSPORT_BROKEN)
check("hết lượt NẶNG hơn mất đăng nhập khi câu có cả hai",
      ws.phan_loai("usage limit reached, please sign in again") == ws.USAGE_LIMITED)
check("không nhận ra thì trả UNKNOWN, không đoán bừa",
      ws.phan_loai("ECONNRESET") == ws.UNKNOWN)
check("chuỗi rỗng trả UNKNOWN", ws.phan_loai("") == ws.UNKNOWN)


# ---- 2. Chạy trót lọt ----

moi()
t = ws.ghi_thanh_cong(thread_id="thread-abc", now=T0)
check("thành công -> READY", t.state == ws.READY)
check("thành công -> không còn nghỉ", not t.dang_nghi(T0))
check("thành công -> nhớ luồng web", t.active_thread_id == "thread-abc")
check("thành công -> đếm lượt trong ngày", t.so_luot_trong_ngay == 1)
ws.ghi_thanh_cong(now=T0 + 10)
check("hai lượt thì đếm thành 2", ws.doc().so_luot_trong_ngay == 2)
check("chạy được ngay sau khi thành công", ws.co_chay_duoc(T0 + 20).ok)


# ---- 3. Hết lượt: nhà cung cấp NÓI mốc thì tin, không nói thì ƯỚC ----

moi()
t = ws.ghi_hong("You've reached your limit", retry_after=1800, now=T0)
check("hết lượt -> USAGE_LIMITED", t.state == ws.USAGE_LIMITED)
check("nhà cung cấp nói mốc -> cooldown đúng bằng mốc đó",
      abs(t.cooldown_until - (T0 + 1800)) < 1)
check("nhà cung cấp nói mốc -> KHÔNG đánh dấu là ước", t.cooldown_uoc is False)

moi()
t = ws.ghi_hong("You've reached your limit", now=T0)
check("không nói mốc -> vẫn có cooldown mặc định", t.cooldown_until > T0)
check("không nói mốc -> PHẢI đánh dấu là ước", t.cooldown_uoc is True)

moi()
t = ws.ghi_hong("hết lượt", kind=ws.USAGE_LIMITED, retry_after=10 * 24 * 3600, now=T0)
check("mốc xa vô lý bị kẹp ở trần 24h",
      t.cooldown_until <= T0 + ws.COOLDOWN_TOI_DA + 1)


# ---- 4. Trong cooldown thì TỪ CHỐI TRƯỚC khi mở trình duyệt ----

moi()
ws.ghi_hong("You've reached your limit", retry_after=1800, now=T0)
c = ws.co_chay_duoc(T0 + 60)
check("đang nghỉ -> không cho chạy", not c.ok)
check("đang nghỉ -> nói đúng loại", c.kind == ws.USAGE_LIMITED)
check("đang nghỉ -> câu nói được, có số phút", "phút" in c.message)
check("đang nghỉ -> gợi ý đổi model", "model" in c.message.lower())
check("nhà cung cấp nói mốc thì KHÔNG gắn chữ 'ước'", "ước" not in c.message)

c2 = ws.co_chay_duoc(T0 + 1800 + 5)
check("hết cooldown -> chạy lại được", c2.ok)

moi()
ws.ghi_hong("hết lượt", kind=ws.USAGE_LIMITED, now=T0)
c = ws.co_chay_duoc(T0 + 60)
check("mốc do Javis ước thì phải nói rõ là ước", "ước" in c.message)


# ---- 5. Mất đăng nhập ----

moi()
t = ws.ghi_hong("session expired, please log in", now=T0)
check("mất đăng nhập -> AUTH_REQUIRED", t.state == ws.AUTH_REQUIRED)
check("mất đăng nhập -> auth_state expired", t.auth_state == "expired")
c = ws.co_chay_duoc(T0 + 1)
check("mất đăng nhập -> chặn", not c.ok and c.kind == ws.AUTH_REQUIRED)
check("mất đăng nhập -> chỉ đúng nút bấm", "Mở cửa sổ đăng nhập" in c.message)

ws.ghi_dang_nhap(True, now=T0 + 100)
check("đăng nhập lại -> chạy được", ws.co_chay_duoc(T0 + 101).ok)
check("đăng nhập lại -> xoá đếm hỏng", ws.doc().failure_count == 0)

# Đăng nhập lại KHÔNG giải quyết hết lượt, nên không được xoá cooldown đó.
moi()
ws.ghi_hong("You've reached your limit", retry_after=1800, now=T0)
ws.ghi_dang_nhap(True, now=T0 + 10)
check("đăng nhập lại KHÔNG xoá cooldown của hết lượt",
      not ws.co_chay_duoc(T0 + 20).ok)


# ---- 6. Phanh chống thử lại vô hạn (lỗ mà _FallbackChain đang có) ----

moi()
for i in range(ws.NGUONG_NGAT):
    ws.ghi_hong("ECONNRESET", now=T0 + i)
t = ws.doc()
check(f"hỏng {ws.NGUONG_NGAT} lần liên tiếp -> đếm đúng", t.failure_count == ws.NGUONG_NGAT)
check("chạm ngưỡng -> vào cooldown dài dù lỗi vốn nhẹ",
      t.cooldown_until >= T0 + ws.COOLDOWN_NGAT - 5)
check("chạm ngưỡng -> chặn chạy", not ws.co_chay_duoc(T0 + 60).ok)

ws.ghi_thanh_cong(now=T0 + ws.COOLDOWN_NGAT + 10)
check("một lần thành công xoá sạch đếm hỏng", ws.doc().failure_count == 0)
check("một lần thành công xoá cooldown", ws.co_chay_duoc(T0 + ws.COOLDOWN_NGAT + 11).ok)


# ---- 7. Lỗi lạ không được ném ra ngoài ----

moi()
t = ws.ghi_hong("", now=T0)
check("message rỗng không nổ, rơi về TEMPORARY_ERROR", t.state == ws.TEMPORARY_ERROR)
t = ws.ghi_hong("x" * 5000, now=T0)
check("message dài bị cắt, không phình sổ", len(t.last_error) <= 600)


# ---- 8. Tóm tắt cho giao diện: không bịa phần trăm ----

moi()
ws.ghi_thanh_cong(now=T0)
tt = ws.tom_tat()
check("tóm tắt khai nguồn quota là gói web", tt["quota_source"] == "web_subscription")
check("tóm tắt khai THẲNG là không quan sát được quota",
      tt["quota_visibility"] == "unknown")
check("tóm tắt KHÔNG có trường phần trăm nào",
      not any("percent" in k or "phan_tram" in k for k in tt))
check("tóm tắt có bộ đếm lượt (thứ duy nhất đo được)", "so_luot_trong_ngay" in tt)


# ---- 9. Sổ hỏng / file lạ thì không được làm gãy lượt chat ----

moi()
ws.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
ws.STORE_PATH.write_text("{ đây không phải json", encoding="utf-8")
check("sổ hỏng vẫn đọc được, rơi về mặc định", ws.doc().state == ws.UNKNOWN)
check("sổ hỏng vẫn cho chạy", ws.co_chay_duoc(T0).ok)

ws.STORE_PATH.write_text('{"state": "READY", "truong_la_cua_ban_sau": 1}', encoding="utf-8")
check("trường lạ của bản sau không làm vỡ bản trước", ws.doc().state == ws.READY)


# ---- 10. Ranh giới module ----

_src = (SERVER / "web_state.py").read_text(encoding="utf-8")
for cam in ("import main", "from main", "fastapi", "playwright"):
    check(f"module thuần, không '{cam}'", cam not in _src)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_web_state: tất cả pass")
