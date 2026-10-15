"""Khối kênh của Zalo cá nhân khai đúng cuộc chat (0.166.0).

    python tests/run.py zalo_ca_nhan_danh_tinh      (KHÔNG mạng)

Ca thật 15/10/2026: file Agent có ngoại lệ cho một cuộc chat riêng theo threadId (chat của mẹ chủ), nhưng kênh Zalo cá
nhân không đưa threadId vào prompt, nên model không có cách nào biết đang ở cuộc chat đó và đối xử như với khách lạ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_context  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


b = channel_context.build_channel_block(
    "zalo_personal", {"chat_id": "111222333", "chat_type": "private", "user_name": "Nguyễn Văn A"})
check("chat riêng: khai threadId do gateway cấp", "threadId 111222333" in b, b[-500:])
check("chat riêng: ghi là chat riêng với người nhắn", "chat riêng với Nguyễn Văn A" in b, b[-500:])
check("dặn so threadId, không so tên hiển thị", "KHÔNG so tên hiển thị" in b)

g = channel_context.build_channel_block(
    "zalo_personal", {"chat_id": "999", "chat_type": "group", "chat_title": "Nhóm lớp", "user_name": "B"})
check("nhóm: khai tên nhóm và threadId nhóm", "nhóm 'Nhóm lớp'" in g and "threadId 999" in g, g[-400:])

check("không kéo theo hướng dẫn gửi file hay nhắc hẹn của kênh khác",
      "Gửi file" not in b.split("threadId trên do gateway")[-1] and "owner_chat" not in b.split("KÊNH HỘI THOẠI HIỆN TẠI")[-1].split("- Nguồn tin nhắn này")[-1])

z = channel_context.build_channel_block("zalo", {"chat_id": "zalo:1", "chat_type": "private", "user_name": "C"})
check("kênh Zalo Bot không đổi", "Zalo (chat riêng với C, chat_id zalo:1)" in z, z[-300:])

d1 = channel_context.build_channel_block("zalo_personal", {"chat_id": "1", "chat_type": "private", "user_name": "A"})
d2 = channel_context.build_channel_block("zalo_personal", {"chat_id": "1", "chat_type": "private", "user_name": "A"})
check("khối ổn định giữa các lượt cùng cuộc chat (giữ prompt cache)", d1 == d2)

print()
print("TẤT CẢ XANH" if not _fails else "ĐỎ: " + ", ".join(_fails))
sys.exit(1 if _fails else 0)
