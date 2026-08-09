"""Bot Zalo đang RẢNH thì thẻ phải sạch, và tai phải mở.

    python tests/run.py zalo_ranh      (KHÔNG mạng, Zalo giả lập)

Chủ repo gửi ảnh thẻ bot "Javis Vũ" (2026-08-09): chấm đỏ **Lỗi**, kèm một ô xám ghi đúng hai
chữ "Request timeout". Con bot đó vẫn sống, vẫn trả lời được (thẻ ghi "1 lượt trả lời").

Gốc rễ: `getUpdates` của Zalo KHÔNG cư xử như Telegram. Telegram hết giờ chờ thì trả
`ok: true` với danh sách rỗng; Zalo trả `ok: false` kèm `description: "Request timeout"`. Đó
là nhịp bình thường của long-poll - 25 giây không ai nhắn thì đúng là không có gì để trả về.

Vòng lặp đọc nhầm nhịp đó thành hỏng, và cái giá có hai phần:

1. **Thẻ nói dối.** Bot rảnh là thẻ đỏ, mà rảnh là trạng thái thường trực của một con bot
   chăm sóc khách. Thẻ đỏ thường trực thì lần bot hỏng THẬT sẽ không ai nhìn ra.
2. **Bot điếc 10 giây mỗi vòng.** Nhánh lỗi ngủ 10 giây rồi mới poll lại. Tin nhắn rơi vào
   khoảng đó không mất, nhưng phải chờ tới vòng sau mới được đọc.

Phần khó của bản sửa không nằm ở chỗ nhận ra chữ "timeout", mà ở chỗ KHÔNG nuốt nhầm lỗi
thật: máy chủ Javis mất mạng cũng đẻ ra một chuỗi có chữ timeout, và đó là hỏng thật. Ranh
giới là ai đang nói: Zalo đáp bằng một body JSON, còn mất mạng thì chỉ có ngoại lệ phía mình.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-zaloranh-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import zalo_bot  # noqa: E402
from zalo_bot import ZaloBot, _la_het_gio_cho  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Phân biệt "hết giờ chờ" với "hỏng thật"
# ============================================================
check("Zalo đáp Request timeout -> nhịp rảnh",
      _la_het_gio_cho({"ok": False, "description": "Request timeout"}) is True)
check("viết hoa thường kiểu gì cũng nhận",
      _la_het_gio_cho({"ok": False, "description": "REQUEST TIMEOUT"}) is True)

# Ranh giới quan trọng nhất của cả file. `_api` gắn `loi_mang` cho dict sinh từ ngoại lệ; thiếu
# dấu đó thì máy chủ mất mạng sẽ được đọc thành "bot đang rảnh" và thẻ xanh mãi mãi.
check("CANARY: mất mạng phía mình -> KHÔNG phải nhịp rảnh",
      _la_het_gio_cho({"ok": False, "description": "ReadTimeout: quá lâu",
                       "loi_mang": True}) is False)
for _ma in (401, 403, 404, 429):
    check(f"mã {_ma} -> lỗi thật, dù chữ có nói gì",
          _la_het_gio_cho({"ok": False, "description": "Request timeout",
                           "error_code": _ma}) is False)
for _mo_ta in ("Unauthorized", "Bot not found", ""):
    check(f"'{_mo_ta or '(rỗng)'}' -> lỗi thật",
          _la_het_gio_cho({"ok": False, "description": _mo_ta}) is False)

# Bản đầu của bản vá loại MỌI phản hồi có `error_code`, dựa trên phỏng đoán rằng nhịp hết giờ
# của Zalo không gắn mã. Tài liệu Zalo không nói gì về chuyện đó, và đoán sai theo hướng ấy thì
# bản vá im lặng không chạy - người dùng lại thấy đúng thẻ đỏ cũ mà không hiểu vì sao.
for _ma in (408, 504):
    check(f"mã hết giờ {_ma} kèm chữ timeout -> vẫn là nhịp rảnh",
          _la_het_gio_cho({"ok": False, "description": "Request timeout",
                           "error_code": _ma}) is True)
check("mã lạ ngoài hai nhóm trên -> không đoán bừa là rảnh",
      _la_het_gio_cho({"ok": False, "description": "Request timeout",
                       "error_code": 500}) is False)

# `_api` phải THẬT SỰ gắn dấu, nếu không hàm trên chỉ đúng trên giấy.
_src = (ROOT / "server" / "zalo_bot.py").read_text(encoding="utf-8")
check("CANARY: _api gắn loi_mang cho nhánh ngoại lệ", '"loi_mang": True' in _src)


# ============================================================
# 2. Vòng lặp thật: rảnh thì thẻ sạch và poll lại ngay
# ============================================================
class _ClientGia:
    async def post(self, *a, **kw):
        raise AssertionError("test này không được chạm mạng")


def _bot():
    b = ZaloBot("TOKEN", "", lambda *a, **kw: None)
    b.status = "polling"
    return b


async def _mot_vong(bot, phan_hoi):
    """Chạy đúng MỘT vòng của `_loop` với phản hồi getUpdates dựng sẵn, trả danh sách giấc ngủ.

    `_loop` gọi getUpdates hai lần trước khi vào việc thật: một lần hâm nóng để nuốt tin tồn,
    rồi mới tới vòng lặp. Chỉ lần thứ hai mới nhận kịch bản, và nhận xong là dừng luôn.
    """
    lan_poll = [0]

    async def _api(client, method, **payload):
        if method != "getUpdates":
            return {"ok": True, "result": []}
        lan_poll[0] += 1
        if lan_poll[0] == 1:
            return {"ok": True, "result": []}     # vòng hâm nóng
        bot._stop = True                          # chạy đúng một vòng thật rồi thoát
        return phan_hoi

    async def _hoi_danh_tinh(*a, **kw):
        return True

    da_ngu = []

    async def _sleep(giay, *a, **kw):
        da_ngu.append(giay)

    bot._api = _api
    bot._hoi_danh_tinh = _hoi_danh_tinh
    bot._boc_su_kien = lambda d: []
    goc = zalo_bot.asyncio.sleep
    zalo_bot.asyncio.sleep = _sleep
    try:
        await bot._loop()
    finally:
        zalo_bot.asyncio.sleep = goc
    return da_ngu


# Nhịp rảnh: thẻ phải SẠCH và không có giấc ngủ 10 giây nào.
_b = _bot()
_b.last_error = "lỗi từ vòng trước"
_ngu = asyncio.run(_mot_vong(_b, {"ok": False, "description": "Request timeout"}))
check("rảnh: trạng thái vẫn là đang chạy", _b.status == "polling")
check("rảnh: thẻ KHÔNG còn dòng lỗi nào", _b.last_error == "")
check("rảnh: xoá luôn lỗi cũ (vòng này là bằng chứng đường đi vẫn thông)",
      "lỗi từ vòng trước" not in _b.last_error)
check("CANARY: rảnh thì KHÔNG ngủ 10 giây (bot điếc 10s mỗi vòng là lỗi gốc)",
      all(g < 10 for g in _ngu))

# Lỗi thật: giữ nguyên hành vi cũ. Nới cho nhịp rảnh không được phép làm lỗi thật im lặng.
_b2 = _bot()
_ngu2 = asyncio.run(_mot_vong(_b2, {"ok": False, "description": "Unauthorized",
                                    "error_code": 401}))
check("CANARY: lỗi thật vẫn đỏ thẻ", _b2.status == "error")
check("lỗi thật vẫn ghi đúng lý do", "Unauthorized" in _b2.last_error)
check("lỗi thật vẫn nghỉ một nhịp dài trước khi thử lại", any(g >= 10 for g in _ngu2))

_b3 = _bot()
_ngu3 = asyncio.run(_mot_vong(_b3, {"ok": False, "description": "Too many requests",
                                    "error_code": 429}))
check("429 của Zalo vẫn nghỉ hẳn 60 giây", any(g >= 60 for g in _ngu3))

# Zalo đáp gần như tức thì (không tôn trọng `timeout`) thì phải tự ghìm, kẻo vòng lặp nện API
# vài lần mỗi giây rồi ăn 429 thật - tức là tự tạo ra đúng cái lỗi vừa sửa xong ở trên.
check("Zalo đáp tức thì thì vẫn ghìm lại một nhịp ngắn", any(0 < g <= 5 for g in _ngu))


# ============================================================
# 3. Gãy vì lý do KHÔNG rõ: chỉ đỏ thẻ khi nó lặp lại
# ============================================================
# Một vòng gãy lẻ là chuyện của đường truyền chứ không phải chuyện của người chủ. Đỏ thẻ vì nó
# thì cái thẻ mất giá trị đúng như hồi nó đỏ vì mỗi vòng rảnh - và đó là cả cái bệnh đang chữa.
_LA = {"ok": False, "description": "Internal error", "error_code": 500}

_b4 = _bot()
asyncio.run(_mot_vong(_b4, _LA))
check("gãy lần đầu vì lý do lạ -> CHƯA đỏ thẻ", _b4.status == "polling")
check("và chưa dán lỗi lên thẻ", _b4.last_error == "")

_b5 = _bot()
for _ in range(3):
    _b5._stop = False
    asyncio.run(_mot_vong(_b5, _LA))
check("gãy 3 vòng LIÊN TIẾP -> đỏ thẻ", _b5.status == "error")
check("và nói rõ là gãy liên tiếp mấy vòng", "liên tiếp" in _b5.last_error)
check("kèm nguyên văn lý do gốc", "Internal error" in _b5.last_error)

# Một vòng chạy được là xoá sạch bộ đếm: hai lần gãy cách nhau một tiếng không phải là hỏng.
_b6 = _bot()
for _ in range(2):
    _b6._stop = False
    asyncio.run(_mot_vong(_b6, _LA))
_b6._stop = False
asyncio.run(_mot_vong(_b6, {"ok": True, "result": []}))
check("một vòng chạy được thì xoá bộ đếm gãy", _b6._gay_lien_tiep == 0)
_b6._stop = False
asyncio.run(_mot_vong(_b6, _LA))
check("nên lần gãy sau đó lại tính từ đầu, chưa đỏ thẻ", _b6.status == "polling")

# Nhịp rảnh cũng phải xoá bộ đếm, vì nó là bằng chứng đường đi vẫn thông.
_b7 = _bot()
for _ in range(2):
    _b7._stop = False
    asyncio.run(_mot_vong(_b7, _LA))
_b7._stop = False
asyncio.run(_mot_vong(_b7, {"ok": False, "description": "Request timeout"}))
check("nhịp rảnh cũng xoá bộ đếm gãy", _b7._gay_lien_tiep == 0)

check("không dùng em dash trong mã nguồn (luật CLAUDE.md)", "—" not in _src)

if _fails:
    raise SystemExit(f"\nFAIL - test_zalo_ranh_khong_phai_loi: {len(_fails)} lỗi")
print("\nOK - test_zalo_ranh_khong_phai_loi: tất cả pass")
