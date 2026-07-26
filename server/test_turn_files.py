"""Test collect_turn_files bắt được file NHÚNG dạng đường dẫn TƯƠNG ĐỐI trong vault
(vd ảnh Javis tạo: ![](attachments/x.png)) để tự đính kèm về ĐÚNG phiên chat. Chạy tay / CI:

    cd server && python test_turn_files.py

KHÔNG mạng. Hồi quy cho lỗi: ảnh Javis tạo (lưu attachments/ dạng path tương đối) không
được auto-attach nên engine phải curl -> rơi về ID Telegram đầu tiên (chủ bot).
"""
import os
import sys
import tempfile
import time
import asyncio
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-turnfiles-"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import channel_context  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- Vault tạm với attachments/ + 1 ảnh vừa tạo ----
vault = Path(tempfile.mkdtemp(prefix="javis-vault-"))
adir = vault / "attachments"
adir.mkdir(parents=True, exist_ok=True)
img = adir / "javis-img-20260720-abc123.png"
img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)   # PNG giả, đủ để is_file + size > 0
img_abs = os.path.normpath(str(img))
t0 = time.time() - 1   # ảnh vừa tạo (mtime >= t0-2)

# ---- 1. NHÚNG đường dẫn tương đối trong vault -> resolve ra abs path ----
reply = f"Đã tạo ảnh con mèo cho anh nhé ![con mèo](attachments/{img.name})"
out = channel_context.collect_turn_files(reply, [], t0, cwd=os.getcwd(), vault_root=str(vault))
check("nhúng tương đối: bắt được ảnh trong attachments", img_abs in [os.path.normpath(p) for p in out])

# ---- 2. Không có vault_root -> KHÔNG đoán bừa (giữ hành vi cũ, an toàn) ----
out2 = channel_context.collect_turn_files(reply, [], t0, cwd=os.getcwd())
check("không vault_root: bỏ qua path tương đối", img_abs not in [os.path.normpath(p) for p in out2])

# ---- 3. Đường dẫn TUYỆT ĐỐI vẫn hoạt động như cũ (không hồi quy) ----
reply_abs = f"File nằm ở {img_abs}"
out3 = channel_context.collect_turn_files(reply_abs, [], t0, cwd=os.getcwd(), vault_root=str(vault))
check("path tuyệt đối vẫn bắt", img_abs in [os.path.normpath(p) for p in out3])

# ---- 4. URL http(s) trong markdown KHÔNG bị coi là file ----
reply_url = "Xem tại ![logo](https://example.com/logo.png) nhé"
out4 = channel_context.collect_turn_files(reply_url, [], t0, cwd=os.getcwd(), vault_root=str(vault))
check("URL không bị thu làm file", out4 == [])

# ---- 5. Chống thoát vault: ../ ra ngoài KHÔNG được nhận ----
outside = Path(tempfile.mkdtemp(prefix="javis-outside-")) / "secret.txt"
outside.write_text("bí mật", encoding="utf-8")
rel_escape = os.path.relpath(outside, vault).replace(os.sep, "/")
reply_escape = f"tài liệu ![x]({rel_escape})"
out5 = channel_context.collect_turn_files(reply_escape, [], t0, cwd=os.getcwd(), vault_root=str(vault))
check("chống thoát vault: ../ ra ngoài bị chặn", os.path.normpath(str(outside)) not in [os.path.normpath(p) for p in out5])

# ---- 6. File cũ (mtime trước lượt) KHÔNG bị gửi lại ----
old_img = adir / "cu.png"
old_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
os.utime(old_img, (t0 - 100, t0 - 100))
reply_old = f"ảnh cũ ![cu](attachments/{old_img.name})"
out6 = channel_context.collect_turn_files(reply_old, [], t0, cwd=os.getcwd(), vault_root=str(vault))
check("file cũ không auto-gửi lại", os.path.normpath(str(old_img)) not in [os.path.normpath(p) for p in out6])

# ---- 7. Hồi quy thật: folder "99 - Attachments" có khoảng trắng (ChatGPT/Codex Telegram) ----
numbered = vault / "99 - Attachments"
numbered.mkdir(parents=True, exist_ok=True)
social = numbered / "claude-workforce-vietnamese-4x5.png"
social.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 64)
reply_spaces = "![claude workforce tiếng việt](99 - Attachments/claude-workforce-vietnamese-4x5.png)"
out7 = channel_context.collect_turn_files(reply_spaces, [], t0, cwd=os.getcwd(), vault_root=str(vault))
social_abs = os.path.normpath(str(social))
check("markdown path có khoảng trắng được bắt", social_abs in [os.path.normpath(p) for p in out7])

# ---- 8. Khi file đã attach, bỏ Markdown local khỏi text để Telegram chỉ hiện ảnh thật ----
clean = channel_context.strip_attached_media(reply_spaces, out7, str(vault))
check("đã attach thì bỏ markdown ảnh local", clean == "")
mixed = "Đã tạo ảnh cho anh:\n" + reply_spaces
clean_mixed = channel_context.strip_attached_media(mixed, out7, str(vault))
check("giữ phần lời, chỉ bỏ markdown ảnh", clean_mixed == "Đã tạo ảnh cho anh:")

# ---- 9. Path bọc <> cũng hoạt động; ảnh URL/link thường không bị xoá ----
reply_angle = "![ảnh](<99 - Attachments/claude-workforce-vietnamese-4x5.png>)"
out8 = channel_context.collect_turn_files(reply_angle, [], t0, cwd=os.getcwd(), vault_root=str(vault))
check("markdown path có khoảng trắng bọc <> được bắt", social_abs in [os.path.normpath(p) for p in out8])
keep_url = channel_context.strip_attached_media(
    "![ảnh web](https://example.com/a.png)", out7, str(vault)
)
check("ảnh URL không bị xoá", keep_url == "![ảnh web](https://example.com/a.png)")
keep_link = channel_context.strip_attached_media(
    "[mở file](99 - Attachments/claude-workforce-vietnamese-4x5.png)", out7, str(vault)
)
check("link thường không bị xoá", keep_link.startswith("[mở file]"))

# ---- 10. Reply chỉ còn file: Telegram không gửi tin "(không có nội dung)" trước ảnh ----
sent_text, sent_files = [], []


async def _answer_file_only(text, meta, progress):
    return {"text": "", "files": [str(social)]}


bot = TelegramBot("fake-token", "123", _answer_file_only)


async def _noop(*args, **kwargs):
    return None


async def _capture_text(client, chat, text, reply_markup=None):
    sent_text.append(text)


async def _capture_file(path, caption="", chat=None):
    sent_files.append((path, chat))
    return True, ""


bot._typing = _noop
bot._send_status = _noop
bot._del_msg = _noop
bot._send = _capture_text
bot.send_file = _capture_file
asyncio.run(bot._handle_turn(object(), "123", "tạo ảnh", {"chat_id": "123"}))
check("reply chỉ có file: không gửi text rỗng", sent_text == [])
check("reply chỉ có file: vẫn gửi ảnh đúng chat", sent_files == [(str(social), "123")])

if _fails:
    print(f"\nFAIL - {len(_fails)} test: {_fails}")
    sys.exit(1)
print("\nOK - test_turn_files: tất cả pass")
