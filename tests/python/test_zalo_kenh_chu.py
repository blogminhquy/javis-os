"""Kênh Zalo của CHỦ: ghép nối, định tuyến thông báo, và cửa "đủ điều kiện mới tạo lịch".

    python tests/python/test_zalo_kenh_chu.py

Không cần pytest, KHÔNG chạm mạng.

Hai chỗ đáng canh nhất, cả hai đều là chỗ chép nguyên nết Telegram sang sẽ SAI:

  1. **Danh sách rỗng = CHƯA AI được phép**, không phải "ai cũng được". Bên Telegram ô trống
     nghĩa là mở cho tất cả, và tài liệu đi kèm một câu dặn đừng để trống - vì bên đó user tự
     tra được id của mình bằng @userinfobot rồi điền TRƯỚC khi bật. Zalo không có công cụ đó,
     nên luồng đúng là bật bot với ô TRỐNG rồi tự nhắn cho nó. Nếu ô trống lại mở cho tất cả
     thì chính cái luồng giao diện đang hướng dẫn sẽ tạo ra một con bot ai nhắn cũng chạm được
     vào brain của chủ.
  2. **Việc giao TỪ Zalo phải báo VỀ Zalo.** Không có tiền tố `zalo:` thì kết quả rơi sang
     Telegram của chủ: người giao việc không bao giờ thấy nó, và máy chưa đấu Telegram thì
     mất hút hoàn toàn.

Xem docs/dev/2026-08-zalo-bot-spec.md.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import sys
import time
from pathlib import Path

import config as cfgmod
import main

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + repr(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


def dat_cau_hinh(**zalo):
    """Thay read_settings bằng bản giả - KHÔNG đụng settings.json thật của máy đang chạy."""
    z = {"enabled": False, "token": "", "chat_id": ""}
    z.update(zalo)
    main.cfgmod.read_settings = lambda: {"zalo_bot": z, "telegram": {}}
    return z


_read_that = cfgmod.read_settings
main._ZALO_CHO.clear()


# ---- 1. Cổng ghép nối: fail-closed ----

dat_cau_hinh(enabled=True, token="t", chat_id="")
me = {"chat_id": "6ede9afa66b88fe6d6a9", "user_name": "Ted"}
r1 = main._zalo_precheck("chào", me)
check("danh sách RỖNG thì người lạ vẫn bị chặn (fail-closed, khác Telegram)", r1 is not None)
check("và được cấp một mã ghép nối để chủ đối chiếu",
      "Mã ghép nối" in (r1 or {}).get("reply", ""), r1)
check("người đó vào hàng chờ kèm TÊN THẬT",
      any(v.get("ten") == "Ted" for v in main._ZALO_CHO.values()), main._ZALO_CHO)

r2 = main._zalo_precheck("alo", me)
check("nhắn tiếp thì vẫn CHẶN", r2 is not None)
check("nhưng IM, không lặp lại câu từ chối (chống người lạ bơm tin)",
      (r2 or {}).get("reply", "") == "", r2)
check("số lần nhắn được đếm lên cho chủ nhìn",
      any(v.get("lan", 0) >= 2 for v in main._ZALO_CHO.values()))

dat_cau_hinh(enabled=True, token="t", chat_id="6ede9afa66b88fe6d6a9")
check("id đã được cho phép thì đi thẳng, không qua hàng chờ",
      main._zalo_precheck("chào", me) is None)
check("người KHÁC vẫn bị chặn",
      main._zalo_precheck("hi", {"chat_id": "khac", "user_name": "Lạ"}) is not None)


# ---- 2. Hàng chờ có TRẦN và có hạn: hộp thư mở cho người lạ ----

main._ZALO_CHO.clear()
dat_cau_hinh(enabled=True, token="t", chat_id="")
for i in range(main._ZALO_CHO_MAX + 15):
    main._zalo_precheck("x", {"chat_id": f"id{i}", "user_name": f"N{i}"})
check("hàng chờ không phình quá trần", len(main._ZALO_CHO) <= main._ZALO_CHO_MAX,
      len(main._ZALO_CHO))

main._ZALO_CHO.clear()
main._zalo_precheck("x", {"chat_id": "cu", "user_name": "Cũ"})
main._ZALO_CHO["cu"]["ts"] = time.time() - main._ZALO_CHO_TTL - 10
main._zalo_don_cho()
check("mục quá hạn tự rụng", "cu" not in main._ZALO_CHO)


# ---- 3. Vỏ lượt: gắn tiền tố nhưng KHÔNG phá meta của lớp vận chuyển ----

goi = {}


async def _gia_answer(text, meta=None, progress=None, channel="telegram", bot=None):
    goi.update({"meta": meta, "channel": channel})
    return {"text": "ok"}


_that = main._tg_answer
main._tg_answer = _gia_answer
try:
    meta_goc = {"chat_id": "abc123", "user_name": "Ted"}
    asyncio.run(main._zalo_answer("hỏi", meta_goc))
    check("lõi nhận chat_id ĐÃ gắn tiền tố (khoá phiên + owner_chat)",
          goi["meta"]["chat_id"] == "zalo:abc123", goi["meta"])
    check("nhãn kênh là zalo", goi["channel"] == "zalo", goi["channel"])
    # Lớp vận chuyển dùng chính dict này để biết gửi tin về đâu. Sửa tại chỗ là bot gửi tới
    # một chat_id không tồn tại, và lỗi đó chỉ lộ ra ở đầu bên kia.
    check("KHÔNG sửa dict meta mà lớp vận chuyển đang cầm",
          meta_goc["chat_id"] == "abc123", meta_goc)
finally:
    main._tg_answer = _that


# ---- 4. Định tuyến thông báo theo tiền tố ----

da_gui = []


async def _gia_zalo_send(chat_id, text):
    da_gui.append((chat_id, text))
    return True, ""


_that_send = main._zalo_send_to
main._zalo_send_to = _gia_zalo_send
try:
    ok, err = asyncio.run(main._notify_owner("zalo:abc123", "kết quả"))
    check("_notify_owner: tiền tố zalo -> gửi qua bot Zalo", ok and da_gui, (ok, err))
    check("và BÓC tiền tố trước khi gửi (id thật, không kèm 'zalo:')",
          da_gui and da_gui[-1][0] == "abc123", da_gui[-1:] )
    da_gui.clear()
    asyncio.run(main._tg_send_to("zalo:abc123", "nhắc hẹn"))
    check("_tg_send_to: nhắc hẹn đặt từ Zalo cũng về Zalo",
          da_gui and da_gui[-1][0] == "abc123", da_gui[-1:])
finally:
    main._zalo_send_to = _that_send


# ---- 5. Soát kênh ngoài: Zalo phải được tính ngang Telegram ----
#
# Tới 0.48.x đây là một CÁI CỬA: chưa đấu kênh nào thì `_notify_ready` chặn không cho tạo
# nhắc hẹn, vì tới giờ chạy xong kết quả sẽ rơi vào hư không. Từ 0.49.0 hòm thư luôn nhận
# nên cửa đó mở hẳn, và phần soi Telegram/Zalo chuyển sang `_kenh_con_thieu` - dùng để HIỂN
# THỊ ("chưa có đường tới điện thoại") chứ không chặn nữa.
#
# Ý ĐỊNH GỐC của mục này vẫn nguyên: người chỉ đấu Zalo không được coi là "chưa có kênh".

main.cfgmod.read_settings = lambda: {"telegram": {}, "zalo_bot": {}}
co_ngoai, ly_do = main._kenh_con_thieu()
check("chưa đấu kênh nào -> báo là còn thiếu", not co_ngoai and ly_do, (co_ngoai, ly_do))
check("lý do nêu CẢ HAI kênh, không chỉ Telegram",
      "Telegram" in ly_do and "Zalo" in ly_do, ly_do)
san, _ = main._notify_ready()
check("nhưng KHÔNG còn chặn tạo nhắc hẹn nữa (hòm thư luôn nhận)", san is True, san)

main.cfgmod.read_settings = lambda: {
    "telegram": {}, "zalo_bot": {"enabled": True, "token": "t", "chat_id": "abc"}}
co_ngoai, ly_do = main._kenh_con_thieu()
check("chỉ đấu Zalo (không có Telegram) là ĐỦ, không kêu thiếu", co_ngoai, (co_ngoai, ly_do))

main.cfgmod.read_settings = _read_that


# ---- 6. Cấu hình: có khối riêng và token được mã hoá ----

check("settings có khối zalo_bot", "zalo_bot" in cfgmod._DEFAULT, list(cfgmod._DEFAULT)[:6])
check("mặc định TẮT", cfgmod._DEFAULT["zalo_bot"]["enabled"] is False)
check("token zalo nằm trong danh sách trường mã hoá at rest",
      "zalo_bot.token" in cfgmod._SECRET_PATHS, cfgmod._SECRET_PATHS)


# ---- 7. Khối ngữ cảnh kênh nói THẬT về giới hạn của Zalo ----

import channel_context

khoi = channel_context.build_channel_block(
    "zalo", {"chat_id": "zalo:abc", "user_name": "Ted", "chat_type": "private"},
    port=7777, brain_root="/b")
check("nhận diện đúng nguồn", "Nguồn tin nhắn này: Zalo" in khoi)
check("nói rõ CHƯA gửi được tài liệu, thay vì để Javis hứa hão",
      "CHƯA có API gửi tài liệu" in khoi, khoi[:0])
check("cấm nói 'em đã gửi file'", "không nói \"em đã gửi file\"" in khoi.lower()
      or "TUYỆT ĐỐI không nói" in khoi)
check("nhắc trần 2000 ký tự", "2000 KÝ TỰ" in khoi)
check("dặn giữ nguyên tiền tố zalo: khi giao việc nền", "zalo:" in khoi)
check("không dạy dùng bảng markdown", "đừng dùng bảng" in khoi)

# Quét ĐÚNG khối Zalo trong main.py chứ không quét cả file: main.py có một regex
# `[-–—]` để NHẬN DIỆN em dash người khác viết trong chỉ mục bộ nhớ, và đó là thứ đúng phải
# có. Luật của CLAUDE.md cấm VIẾT ra em dash, không cấm nhận ra nó.
_MAIN = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
_khoi_zalo = _MAIN[_MAIN.index("# Kênh Zalo Bot của CHỦ"):_MAIN.index("def restart_telegram():")]
check("khối Zalo không có em dash (luật CLAUDE.md)", "—" not in _khoi_zalo)
check("khối Zalo thật sự là phần mới, không rỗng", len(_khoi_zalo) > 3000, len(_khoi_zalo))


print()
if loi:
    print(f"{len(loi)} test ĐỎ: " + ", ".join(loi))
    sys.exit(1)
print("Tất cả test xanh.")
