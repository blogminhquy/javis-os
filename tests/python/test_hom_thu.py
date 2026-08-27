"""Hòm thư: mọi kết quả chạy nền phải để lại một mẩu thư BỀN ở server.

    python tests/python/test_hom_thu.py

Vì sao có file này
==================
Trước 0.49.0 kết quả việc nền tìm đường về người dùng bằng ba lối, lối nào cũng hụt:

  - việc Kanban / loop: đẩy vào ĐÚNG khung chat web đã giao việc. Tin còn sau F5, nhưng
    đang mở hội thoại KHÁC hoặc đã đóng tab thì không có gì báo là kết quả đã về;
  - nhắc hẹn: CHỈ đi Telegram, và chưa đấu bot thì `reminders.py` chặn không cho tạo;
  - chuông "Thông báo": kênh phát tin chung (changelog + tin cộng đồng), không phải thư riêng.

Hòm thư đóng cả ba bằng một ý: kết quả nào cũng để lại một mẩu thư, BẤT KỂ gửi bằng kênh gì.
Cái đáng khoá lại nhất là chỗ MÓC: nếu ai đó sau này thêm một nguồn việc nền mới mà không đi
qua `_notify_owner`, nguồn đó lại rơi vào im lặng như nhắc hẹn ngày xưa.
"""
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-homthu-"))

from _paths import ROOT, SERVER  # noqa: E402,F401

import inbox  # noqa: E402
import main   # noqa: E402

fails = []


def check(name, cond, extra=None):
    print(("PASS: " if cond else "FAIL: ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        fails.append(name)


# ─────────── 1. Kho thư: thêm, đọc, đếm ───────────
it = inbox.add("Báo cáo doanh thu\nHôm nay 12 đơn.", kind="report", session_id="sid-1",
               source="loop", label="bao-cao-sang")
check("thêm thư trả về id", bool(it.get("id")))
check("tiêu đề lấy từ dòng đầu có chữ", it["title"] == "Báo cáo doanh thu", it["title"])
check("thư mới luôn CHƯA đọc", it["read"] is False)
check("giữ địa chỉ hội thoại để còn quay về", it["session_id"] == "sid-1")
check("đếm chưa đọc", inbox.so_chua_doc() == 1, inbox.so_chua_doc())

inbox.add("# Xong việc rồi nhé", kind="answer", session_id="sid-2")
check("thư mới nhất đứng đầu", inbox.danh_sach()[0]["title"] == "Xong việc rồi nhé")
check("tiêu đề bỏ dấu markdown mở đầu", inbox.danh_sach()[0]["title"][0] != "#")
check("đếm chưa đọc = 2", inbox.so_chua_doc() == 2)

check("đọc một mẩu", inbox.danh_dau_doc(it["id"]) and inbox.so_chua_doc() == 1)
check("đọc mẩu không có thật trả False", inbox.danh_dau_doc("khong-co") is False)

# Đây là luật chống ĐẾM HAI LẦN: đã đọc nội dung trong khung chat rồi thì chuông phải tắt.
inbox.add("Thêm một tin nữa của cùng hội thoại", session_id="sid-2")
check("mở hội thoại nào thì thư của hội thoại đó coi như đã đọc",
      inbox.doc_theo_phien("sid-2") == 2 and inbox.so_chua_doc() == 0)
check("đọc theo phiên rỗng thì không đụng gì", inbox.doc_theo_phien("") == 0)

inbox.add("còn nợ một tin")
check("đọc tất cả", inbox.doc_het() == 1 and inbox.so_chua_doc() == 0)

# ─────────── 2. Trần số thư: cắt thư ĐÃ ĐỌC trước ───────────
# Thư chưa đọc là thứ người dùng còn nợ; cắt nó đi là cắt đúng cái đáng giữ nhất.
truoc = len(inbox.danh_sach(10_000))
for i in range(inbox.MAX_ITEMS + 20):
    inbox.add(f"thư số {i}")
tat_ca = inbox.danh_sach(10_000)
check("không vượt trần MAX_ITEMS", len(tat_ca) <= inbox.MAX_ITEMS, len(tat_ca))
check("CANARY: cắt bớt nhưng KHÔNG xoá thư chưa đọc",
      sum(1 for x in tat_ca if not x.get("read")) >= inbox.MAX_ITEMS - truoc - 1)

# ─────────── 3. Móc vào _notify_owner - cửa DUY NHẤT của mọi việc nền ───────────
# Dọn hòm trước khi đo: mục 2 vừa đẩy nó chạm trần, nên "thêm một mẩu" sẽ không làm SỐ
# LƯỢNG đổi (thêm một, cắt một) và phép đếm mất ý nghĩa.
inbox.STORE.unlink(missing_ok=True)
n0 = len(inbox.danh_sach(10_000))
gui = []


async def _gia_kenh(owner_chat, text):
    gui.append((owner_chat, text))
    return True, ""


that_kenh = main._gui_qua_kenh
main._gui_qua_kenh = _gia_kenh
try:
    ok, err = asyncio.get_event_loop().run_until_complete(
        main._notify_owner("web:phien-abc", "Việc xong rồi\nchi tiết ở đây", kind="answer"))
finally:
    main._gui_qua_kenh = that_kenh

check("_notify_owner vẫn gửi qua kênh như cũ", len(gui) == 1 and gui[0][0] == "web:phien-abc")
check("_notify_owner trả ok", ok is True and err == "")
moi = inbox.danh_sach(10_000)
check("CANARY: mọi lượt báo đều để lại MỘT mẩu thư", len(moi) == n0 + 1, f"{n0} -> {len(moi)}")
check("thư bóc đúng mã phiên từ tiền tố web:", moi[0]["session_id"] == "phien-abc", moi[0]["session_id"])

# Kênh hỏng (chưa đấu Telegram) mà thư vẫn vào hòm thì lượt báo vẫn tính là TỚI ĐƯỢC người
# dùng. Thiếu luật này thì nhắc hẹn trên máy chưa đấu bot bị ghi "failed" trong khi nội
# dung đang nằm sẵn trong hòm - đúng cảnh khó hiểu mà bản này sinh ra để bỏ.
async def _kenh_hong(owner_chat, text):
    return False, "Bot Telegram chưa bật hoặc chưa có chat_id"


main._gui_qua_kenh = _kenh_hong
try:
    ok2, err2 = asyncio.get_event_loop().run_until_complete(
        main._notify_owner("", "Nhắc bạn: họp lúc 3h", kind="report", source="reminder"))
finally:
    main._gui_qua_kenh = that_kenh
check("CANARY: kênh hỏng nhưng vào được hòm thì vẫn tính là đã báo", ok2 is True, (ok2, err2))
check("thư của nhắc hẹn vào đúng nhóm báo cáo", inbox.danh_sach()[0]["kind"] == "report")

# ─────────── 4. Chấm đỏ phải nhảy NGAY, không đợi tải lại trang ───────────
su_kien = []


async def _bat_publish(ev):
    su_kien.append(ev)


that_publish = main._CHAT_RUNTIME.publish
main._CHAT_RUNTIME.publish = _bat_publish
main._gui_qua_kenh = _gia_kenh
try:
    asyncio.get_event_loop().run_until_complete(
        main._notify_owner("web:phien-xyz", "Xong rồi nhé"))
finally:
    main._CHAT_RUNTIME.publish = that_publish
    main._gui_qua_kenh = that_kenh

inbox_ev = [e for e in su_kien if e.get("type") == "inbox"]
check("CANARY: có thư mới thì bắn sự kiện WebSocket cho chuông cập nhật ngay",
      len(inbox_ev) == 1, [e.get("type") for e in su_kien])
check("sự kiện mang mã phiên để khung chat đang mở tự đánh dấu đã đọc",
      inbox_ev and inbox_ev[0].get("session_id") == "phien-xyz")


# ─────────── 5. Nhắc hẹn phải đi qua cùng một cửa ───────────
check("CANARY: reminders dùng _bao_nhac_hen (qua _notify_owner), không gọi thẳng Telegram nữa",
      main.reminders_feature.deps.send_telegram is main._bao_nhac_hen)
san_sang, _ = main._notify_ready()
check("hòm thư luôn có nên không còn chặn tạo nhắc hẹn", san_sang is True)

if fails:
    print(f"\nFAIL - test_hom_thu: {len(fails)} lỗi: {', '.join(fails)}")
    raise SystemExit(1)
print("\nOK - test_hom_thu: tất cả pass")
